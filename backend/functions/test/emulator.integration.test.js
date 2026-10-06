import test from "node:test";
import assert from "node:assert/strict";
import { initializeApp, getApps } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import {
  upsertPurchaseEvidenceForEmulator,
} from "../src/store.js";

const projectId = "demo-rrgh-entitlements";
const functionUrl =
  "http://127.0.0.1:5001/demo-rrgh-entitlements/us-east5/rrghAccountApi";
const authBase = "http://127.0.0.1:9099";

if (!process.env.FIRESTORE_EMULATOR_HOST || !process.env.FIREBASE_AUTH_EMULATOR_HOST) {
  throw new Error("Integration tests require Firebase Auth and Firestore emulators.");
}

if (getApps().length === 0) {
  initializeApp({ projectId });
}
const db = getFirestore();

async function signUp(email, password) {
  const response = await fetch(
    `${authBase}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake-api-key`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        returnSecureToken: true,
      }),
    },
  );
  const body = await response.json();
  assert.equal(response.ok, true, JSON.stringify(body));
  return {
    uid: body.localId,
    idToken: body.idToken,
  };
}

async function callApi(operation, idToken, extra = {}) {
  const headers = {
    "content-type": "application/json",
  };
  if (idToken) {
    headers.authorization = `Bearer ${idToken}`;
  }

  const response = await fetch(functionUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      data: {
        operation,
        ...extra,
      },
    }),
  });
  const body = await response.json();

  return {
    response,
    body,
    result: body.result ?? body.data ?? body.response ?? null,
  };
}

test("emulator contract enforces account-level trial and cross-store entitlement portability", async () => {
  const unauthenticated = await callApi("getAccountState", null);
  assert.equal(unauthenticated.response.status, 401);
  assert.equal(unauthenticated.body?.error?.status, "UNAUTHENTICATED");

  const { uid, idToken } = await signUp("phase3@example.test", "Phase3-Test-Password-123!");

  const initial = await callApi("getAccountState", idToken);
  assert.equal(initial.response.ok, true, JSON.stringify(initial.body));
  assert.equal(initial.result.access.base, false);
  assert.equal(initial.result.access.backpacking, false);
  assert.equal(initial.result.trial.base.consumed, false);

  const firstTrial = await callApi("startBaseTrial", idToken);
  assert.equal(firstTrial.response.ok, true, JSON.stringify(firstTrial.body));
  assert.equal(firstTrial.result.trial.started, true);
  assert.equal(firstTrial.result.account.access.base, true);
  assert.equal(firstTrial.result.account.access.day_hikes, true);
  assert.equal(firstTrial.result.account.access.backpacking, false);
  const firstStart = firstTrial.result.trial.startedAt;
  const firstEnd = firstTrial.result.trial.endsAt;

  const secondTrial = await callApi("startBaseTrial", idToken);
  assert.equal(secondTrial.response.ok, true, JSON.stringify(secondTrial.body));
  assert.equal(secondTrial.result.trial.started, false);
  assert.equal(secondTrial.result.trial.reason, "already_consumed");
  assert.equal(secondTrial.result.trial.startedAt, firstStart);
  assert.equal(secondTrial.result.trial.endsAt, firstEnd);

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "google-backpacking-1",
    store: "google_play",
    platformProductId: "rrgh.backpacking",
    canonicalEntitlementId: "backpacking",
    state: "validated",
  });

  const extensionWithoutPermanentBase = await callApi("getEntitlements", idToken);
  assert.equal(extensionWithoutPermanentBase.result.entitlements.backpacking, "active");
  assert.equal(extensionWithoutPermanentBase.result.access.backpacking, false);

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "apple-base-1",
    store: "apple",
    platformProductId: "rrgh.base",
    canonicalEntitlementId: "base",
    state: "validated",
  });

  const appleBase = await callApi("getEntitlements", idToken);
  assert.equal(appleBase.result.entitlements.base, "active");
  assert.equal(appleBase.result.access.backpacking, true);

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "google-base-1",
    store: "google_play",
    platformProductId: "rrgh.base",
    canonicalEntitlementId: "base",
    state: "validated",
  });

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "apple-base-1",
    store: "apple",
    platformProductId: "rrgh.base",
    canonicalEntitlementId: "base",
    state: "refunded",
  });

  const stillSupported = await callApi("getEntitlements", idToken);
  assert.equal(stillSupported.result.entitlements.base, "active");
  assert.equal(stillSupported.result.access.backpacking, true);

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "google-base-1",
    store: "google_play",
    platformProductId: "rrgh.base",
    canonicalEntitlementId: "base",
    state: "revoked",
  });

  const account = db.collection("accounts").doc(uid);
  await account.set(
    {
      trial: {
        base: {
          consumed: true,
          startedAt: Timestamp.fromMillis(Date.now() - 8 * 24 * 60 * 60 * 1000),
          endsAt: Timestamp.fromMillis(Date.now() - 24 * 60 * 60 * 1000),
        },
      },
    },
    { merge: true },
  );

  const revokedEverywhere = await callApi("getEntitlements", idToken);
  assert.equal(revokedEverywhere.result.entitlements.base, "revoked");
  assert.equal(revokedEverywhere.result.access.base, false);
  assert.equal(revokedEverywhere.result.access.backpacking, false);

  const consumedTrial = await callApi("startBaseTrial", idToken);
  assert.equal(consumedTrial.result.trial.started, false);
  assert.equal(consumedTrial.result.trial.reason, "already_consumed");

  await db.collection("packageCatalog").doc("base-demo").set({
    active: true,
    lifecycle: "active",
    deliveryState: "building",
    packageType: "test_fixture",
    version: "emulator-v1",
    sha256: "emulator-only-no-route-content",
    byteCount: 1,
    requiredEntitlement: "base",
  });
  await db.collection("packageCatalog").doc("backpacking-demo").set({
    active: true,
    lifecycle: "active",
    deliveryState: "building",
    packageType: "test_fixture",
    version: "emulator-v1",
    sha256: "emulator-only-no-route-content",
    byteCount: 1,
    requiredEntitlement: "backpacking",
  });

  const deniedPackage = await callApi("authorizeProtectedPackage", idToken, {
    packageId: "base-demo",
  });
  assert.equal(deniedPackage.result.authorized, false);
  assert.equal(deniedPackage.result.reason, "not_entitled");

  await upsertPurchaseEvidenceForEmulator(db, {
    uid,
    evidenceId: "google-base-1",
    store: "google_play",
    platformProductId: "rrgh.base",
    canonicalEntitlementId: "base",
    state: "validated",
  });

  const allowedBasePackage = await callApi("authorizeProtectedPackage", idToken, {
    packageId: "base-demo",
  });
  assert.equal(allowedBasePackage.result.authorized, true);
  assert.equal(allowedBasePackage.result.delivery.ready, false);
  assert.equal(allowedBasePackage.result.delivery.reason, "package_not_ready");

  const allowedBackpackingPackage = await callApi("authorizeProtectedPackage", idToken, {
    packageId: "backpacking-demo",
  });
  assert.equal(allowedBackpackingPackage.result.authorized, true);

  const deletion = await callApi("initiateAccountDeletion", idToken);
  assert.equal(deletion.result.deletion.state, "pending");
  assert.equal(deletion.result.account.accountStatus, "deletion_pending");
  assert.equal(deletion.result.account.access.base, false);
  assert.equal(deletion.result.account.access.backpacking, false);

  const afterDeletionPackage = await callApi("authorizeProtectedPackage", idToken, {
    packageId: "base-demo",
  });
  assert.equal(afterDeletionPackage.result.authorized, false);

  const trackCollection = await db.collection("userTracks").limit(1).get();
  assert.equal(trackCollection.empty, true);
});
