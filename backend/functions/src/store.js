import { Timestamp } from "firebase-admin/firestore";
import {
  ENTITLEMENTS,
  TRIAL_DURATION_MS,
  deriveAccess,
  deriveCanonicalEntitlementFromEvidence,
} from "./domain.js";

function timestampToMillis(value) {
  if (!value) return null;
  if (typeof value.toMillis === "function") return value.toMillis();
  if (typeof value === "number") return value;
  return null;
}

function timestampToIso(value) {
  const ms = timestampToMillis(value);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : null;
}

function accountRef(db, uid) {
  return db.collection("accounts").doc(uid);
}

function entitlementRef(db, uid, entitlementId) {
  return accountRef(db, uid).collection("entitlements").doc(entitlementId);
}

function purchaseEvidenceCollection(db, uid) {
  return accountRef(db, uid).collection("purchaseEvidence");
}

function unavailableDelivery(reason) {
  return {
    ready: false,
    reason,
    method: null,
    httpMethod: null,
    url: null,
    expiresAt: null,
    authorizationScheme: null,
    authorizationToken: null,
  };
}

function packageDescriptor(packageId, packageData, requirement) {
  return {
    packageId,
    packageType: packageData.packageType ?? null,
    version: packageData.version ?? null,
    sha256: packageData.sha256 ?? null,
    byteCount: Number.isSafeInteger(Number(packageData.byteCount))
      ? Number(packageData.byteCount)
      : null,
    requiredEntitlement: requirement,
    offlineManifest: packageData.offlineManifest ?? null,
  };
}

export async function ensureAccount(db, uid, now = Timestamp.now()) {
  const ref = accountRef(db, uid);
  const snapshot = await ref.get();
  if (snapshot.exists) return snapshot.data();

  const initial = {
    status: "active",
    createdAt: now,
    policyVersion: 1,
  };
  await ref.set(initial, { merge: true });
  return initial;
}

export async function readEntitlementStates(db, uid) {
  const ids = Object.values(ENTITLEMENTS);
  const snapshots = await Promise.all(ids.map((id) => entitlementRef(db, uid, id).get()));
  return Object.fromEntries(
    snapshots.map((snapshot, index) => [
      ids[index],
      snapshot.exists ? snapshot.data()?.state ?? "none" : "none",
    ]),
  );
}

function trialFromAccount(account) {
  const baseTrial = account?.trial?.base;
  if (!baseTrial?.consumed) {
    return {
      consumed: false,
      startedAtMs: null,
      endsAtMs: null,
      startedAt: null,
      endsAt: null,
    };
  }

  return {
    consumed: true,
    startedAtMs: timestampToMillis(baseTrial.startedAt),
    endsAtMs: timestampToMillis(baseTrial.endsAt),
    startedAt: timestampToIso(baseTrial.startedAt),
    endsAt: timestampToIso(baseTrial.endsAt),
  };
}

export async function getAccountStateForUid(db, uid, nowMs = Date.now()) {
  await ensureAccount(db, uid);
  const [accountSnapshot, entitlementStates] = await Promise.all([
    accountRef(db, uid).get(),
    readEntitlementStates(db, uid),
  ]);
  const account = accountSnapshot.data() ?? {};
  const trial = trialFromAccount(account);

  return {
    uid,
    accountStatus: account.status ?? "active",
    trial: {
      base: trial,
    },
    entitlements: entitlementStates,
    access: deriveAccess({
      accountStatus: account.status ?? "active",
      trial,
      entitlementStates,
      nowMs,
    }),
  };
}

export async function startBaseTrialForUid(db, uid) {
  const account = accountRef(db, uid);
  const baseEntitlement = entitlementRef(db, uid, ENTITLEMENTS.BASE);
  const now = Timestamp.now();

  return db.runTransaction(async (transaction) => {
    const [accountSnapshot, baseSnapshot] = await Promise.all([
      transaction.get(account),
      transaction.get(baseEntitlement),
    ]);

    const accountData = accountSnapshot.exists
      ? accountSnapshot.data()
      : { status: "active", createdAt: now, policyVersion: 1 };

    if ((accountData.status ?? "active") !== "active") {
      return {
        started: false,
        reason: "account_not_active",
      };
    }

    if (baseSnapshot.exists && baseSnapshot.data()?.state === "active") {
      return {
        started: false,
        reason: "base_already_owned",
      };
    }

    const existing = accountData?.trial?.base;
    if (existing?.consumed) {
      return {
        started: false,
        reason: "already_consumed",
        startedAt: timestampToIso(existing.startedAt),
        endsAt: timestampToIso(existing.endsAt),
      };
    }

    const endsAt = Timestamp.fromMillis(now.toMillis() + TRIAL_DURATION_MS);
    transaction.set(
      account,
      {
        status: "active",
        createdAt: accountData.createdAt ?? now,
        policyVersion: accountData.policyVersion ?? 1,
        trial: {
          ...(accountData.trial ?? {}),
          base: {
            consumed: true,
            startedAt: now,
            endsAt,
          },
        },
      },
      { merge: true },
    );

    return {
      started: true,
      reason: "started",
      startedAt: now.toDate().toISOString(),
      endsAt: endsAt.toDate().toISOString(),
    };
  });
}

export async function initiateAccountDeletionForUid(db, uid) {
  const now = Timestamp.now();
  const account = accountRef(db, uid);
  const requestRef = db.collection("accountDeletionRequests").doc(uid);

  await db.runTransaction(async (transaction) => {
    const snapshot = await transaction.get(account);
    const current = snapshot.exists ? snapshot.data() : {};

    transaction.set(
      account,
      {
        status: "deletion_pending",
        createdAt: current.createdAt ?? now,
        deletionRequestedAt: current.deletionRequestedAt ?? now,
        policyVersion: current.policyVersion ?? 1,
      },
      { merge: true },
    );

    transaction.set(
      requestRef,
      {
        uid,
        state: "pending",
        requestedAt: now,
        policyVersion: 1,
      },
      { merge: true },
    );
  });

  return {
    state: "pending",
    requestedAt: now.toDate().toISOString(),
  };
}

export async function authorizeProtectedPackageForUid(
  db,
  uid,
  packageId,
  { createDelivery = null } = {},
) {
  const state = await getAccountStateForUid(db, uid);
  if (state.accountStatus !== "active") {
    return {
      authorized: false,
      reason: "account_not_active",
      requiredEntitlement: null,
      package: null,
      delivery: null,
    };
  }

  const packageSnapshot = await db.collection("packageCatalog").doc(packageId).get();
  if (!packageSnapshot.exists) {
    return {
      authorized: false,
      reason: "package_not_found",
      requiredEntitlement: null,
      package: null,
      delivery: null,
    };
  }

  const packageData = packageSnapshot.data() ?? {};
  if (packageData.lifecycle === "superseded") {
    return {
      authorized: false,
      reason: "package_superseded",
      requiredEntitlement: packageData.requiredEntitlement ?? null,
      package: null,
      delivery: null,
    };
  }

  if (packageData.active !== true || packageData.lifecycle !== "active") {
    return {
      authorized: false,
      reason: "package_not_ready",
      requiredEntitlement: packageData.requiredEntitlement ?? null,
      package: null,
      delivery: null,
    };
  }

  const requirement = packageData.requiredEntitlement;
  if (!Object.values(ENTITLEMENTS).includes(requirement)) {
    return {
      authorized: false,
      reason: "package_configuration_invalid",
      requiredEntitlement: null,
      package: null,
      delivery: null,
    };
  }

  const accessKey = requirement === ENTITLEMENTS.BASE ? "base" : requirement;
  const authorized = state.access?.[accessKey] === true;

  if (!authorized) {
    return {
      authorized: false,
      reason: "not_entitled",
      requiredEntitlement: requirement,
      package: null,
      delivery: null,
    };
  }

  const descriptor = packageDescriptor(packageId, packageData, requirement);

  if (packageData.deliveryState !== "ready") {
    return {
      authorized: true,
      reason: null,
      requiredEntitlement: requirement,
      package: descriptor,
      delivery: unavailableDelivery("package_not_ready"),
    };
  }

  if (typeof createDelivery !== "function") {
    return {
      authorized: true,
      reason: null,
      requiredEntitlement: requirement,
      package: descriptor,
      delivery: unavailableDelivery("backend_temporarily_unavailable"),
    };
  }

  let delivery;
  try {
    delivery = await createDelivery({ packageId, packageData });
  } catch {
    delivery = unavailableDelivery("backend_temporarily_unavailable");
  }

  return {
    authorized: true,
    reason: null,
    requiredEntitlement: requirement,
    package: descriptor,
    delivery,
  };
}

// Emulator/internal service seam only. This is intentionally not exported as a
// callable client operation. Production store validation is gated by LEG-Q-0020.
export async function upsertPurchaseEvidenceForEmulator(db, {
  uid,
  evidenceId,
  store,
  platformProductId,
  canonicalEntitlementId,
  state,
}) {
  if (!["apple", "google_play"].includes(store)) {
    throw new Error("unsupported-store");
  }
  if (!Object.values(ENTITLEMENTS).includes(canonicalEntitlementId)) {
    throw new Error("unsupported-entitlement");
  }
  if (!["validated", "refunded", "revoked", "invalid"].includes(state)) {
    throw new Error("unsupported-evidence-state");
  }

  const now = Timestamp.now();
  const ref = purchaseEvidenceCollection(db, uid).doc(evidenceId);
  const current = await ref.get();

  await ref.set(
    {
      uid,
      evidenceId,
      store,
      platformProductId,
      canonicalEntitlementId,
      state,
      firstSeenAt: current.exists ? current.data()?.firstSeenAt ?? now : now,
      updatedAt: now,
      policyVersion: 1,
    },
    { merge: true },
  );

  return reconcileEntitlementFromEvidence(db, uid, canonicalEntitlementId);
}

export async function reconcileEntitlementFromEvidence(db, uid, entitlementId) {
  const evidenceSnapshots = await purchaseEvidenceCollection(db, uid)
    .where("canonicalEntitlementId", "==", entitlementId)
    .get();

  const evidenceRecords = evidenceSnapshots.docs.map((snapshot) => snapshot.data());
  const derived = deriveCanonicalEntitlementFromEvidence(evidenceRecords);
  const now = Timestamp.now();

  await entitlementRef(db, uid, entitlementId).set(
    {
      entitlementId,
      state: derived.state,
      supportingEvidenceIds: derived.supportingEvidenceIds,
      sourcePlatforms: derived.sourcePlatforms,
      updatedAt: now,
      policyVersion: 1,
    },
    { merge: true },
  );

  return {
    entitlementId,
    ...derived,
  };
}
