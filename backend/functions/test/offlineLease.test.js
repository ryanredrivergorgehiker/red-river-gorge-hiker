import test from "node:test";
import assert from "node:assert/strict";
import {
  createHash,
  generateKeyPairSync,
  sign as cryptoSign,
} from "node:crypto";
import {
  OFFLINE_LEASE_ALGORITHM,
  OFFLINE_LEASE_MAX_PAID_MS,
  OFFLINE_LEASE_RENEWAL_WINDOW_MS,
  buildOfflineLeaseClaims,
  signOfflineLeaseClaims,
  validateOfflineLeaseClaims,
  verifyOfflineLeaseToken,
} from "../src/offlineLease.js";

function accountState({
  status = "active",
  base = "none",
  backpacking = "none",
  offTrail = "none",
  trialConsumed = false,
  trialEndsAtMs = null,
  baseAccess = false,
} = {}) {
  return {
    accountStatus: status,
    entitlements: {
      base,
      backpacking,
      off_trail: offTrail,
    },
    trial: {
      base: {
        consumed: trialConsumed,
        startedAt: trialConsumed ? "2026-10-01T00:00:00.000Z" : null,
        endsAt: Number.isFinite(trialEndsAtMs)
          ? new Date(trialEndsAtMs).toISOString()
          : null,
        startedAtMs: trialConsumed ? Date.parse("2026-10-01T00:00:00.000Z") : null,
        endsAtMs: trialEndsAtMs,
      },
    },
    access: {
      base: baseAccess || base === "active",
      day_hikes: baseAccess || base === "active",
      backpacking: base === "active" && backpacking === "active",
      off_trail: base === "active" && offTrail === "active",
    },
  };
}

function testSigner(label) {
  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  const spki = publicKey.export({ format: "der", type: "spki" });
  const keyId =
    "test-" +
    label +
    "-" +
    createHash("sha256").update(spki).digest("hex").slice(0, 16);
  const key = {
    keyId,
    algorithm: OFFLINE_LEASE_ALGORITHM,
    publicKeySpkiBase64: Buffer.from(spki).toString("base64"),
  };

  return {
    key,
    sign: async (bytes) => ({
      keyId,
      signatureBase64url: cryptoSign(
        "RSA-SHA256",
        bytes,
        privateKey,
      ).toString("base64url"),
      verificationKeys: [key],
    }),
  };
}

test("permanent Base lease carries canonical paid grants for exactly 90 days", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const result = buildOfflineLeaseClaims({
    uid: "paid-user",
    nowMs,
    leaseId: "lease-paid-000000000001",
    accountState: accountState({
      base: "active",
      backpacking: "active",
      offTrail: "active",
    }),
  });

  assert.equal(result.issued, true);
  assert.deepEqual(result.claims.grants, [
    "base",
    "backpacking",
    "off_trail",
  ]);
  assert.equal(result.claims.trial, false);
  assert.equal(result.claims.trialEndsAt, null);
  assert.equal(
    Date.parse(result.claims.validUntil) - nowMs,
    OFFLINE_LEASE_MAX_PAID_MS,
  );
  assert.equal(
    Date.parse(result.claims.validUntil) -
      Date.parse(result.claims.renewAfter),
    OFFLINE_LEASE_RENEWAL_WINDOW_MS,
  );
});

test("paid extensions never survive without permanent Base", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const result = buildOfflineLeaseClaims({
    uid: "extension-user",
    nowMs,
    leaseId: "lease-extension-00000001",
    accountState: accountState({
      backpacking: "active",
      offTrail: "active",
      baseAccess: false,
    }),
  });

  assert.equal(result.issued, false);
  assert.equal(result.reason, "no_effective_access");
});

test("Base trial lease is Base-only and never outlives authoritative trialEndsAt", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const trialEndsAtMs = nowMs + 36 * 60 * 60 * 1000;
  const result = buildOfflineLeaseClaims({
    uid: "trial-user",
    nowMs,
    leaseId: "lease-trial-00000000001",
    accountState: accountState({
      backpacking: "active",
      offTrail: "active",
      trialConsumed: true,
      trialEndsAtMs,
      baseAccess: true,
    }),
  });

  assert.equal(result.issued, true);
  assert.deepEqual(result.claims.grants, ["base"]);
  assert.equal(result.claims.trial, true);
  assert.equal(result.claims.trialEndsAt, new Date(trialEndsAtMs).toISOString());
  assert.equal(result.claims.validUntil, result.claims.trialEndsAt);
  assert.equal(result.claims.renewAfter, null);
});

test("expired trial and inactive account fail closed", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const expired = buildOfflineLeaseClaims({
    uid: "trial-expired",
    nowMs,
    accountState: accountState({
      trialConsumed: true,
      trialEndsAtMs: nowMs - 1,
      baseAccess: false,
    }),
  });
  assert.deepEqual(
    { issued: expired.issued, reason: expired.reason },
    { issued: false, reason: "no_effective_access" },
  );

  const inactive = buildOfflineLeaseClaims({
    uid: "deleted-user",
    nowMs,
    accountState: accountState({
      status: "deletion_pending",
      base: "active",
    }),
  });
  assert.deepEqual(
    { issued: inactive.issued, reason: inactive.reason },
    { issued: false, reason: "account_not_active" },
  );
});

test("signed paid lease verifies without any backend dependency", async () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const decision = buildOfflineLeaseClaims({
    uid: "offline-paid",
    nowMs,
    leaseId: "lease-offline-paid-000001",
    accountState: accountState({ base: "active" }),
  });
  const signer = testSigner("offline-paid");
  const signed = await signOfflineLeaseClaims(decision.claims, signer.sign);

  const verification = verifyOfflineLeaseToken({
    signedToken: signed.signedToken,
    keyId: signed.keyId,
    verificationKeys: signed.verificationKeys,
    expectedUid: "offline-paid",
    nowMs: nowMs + 24 * 60 * 60 * 1000,
  });
  assert.equal(verification.valid, true);
  assert.equal(verification.claims.uid, "offline-paid");
});

test("wrong UID, forged payload, malformed signature and expiry fail closed", async () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const decision = buildOfflineLeaseClaims({
    uid: "uid-a",
    nowMs,
    leaseId: "lease-security-000000001",
    accountState: accountState({ base: "active" }),
  });
  const signer = testSigner("security");
  const signed = await signOfflineLeaseClaims(decision.claims, signer.sign);

  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: signed.signedToken,
      keyId: signed.keyId,
      verificationKeys: signed.verificationKeys,
      expectedUid: "uid-b",
      nowMs,
    }).reason,
    "lease_uid_mismatch",
  );

  const parts = signed.signedToken.split(".");
  const forgedPayload = {
    ...decision.claims,
    grants: ["base", "backpacking", "off_trail"],
  };
  const forged =
    parts[0] +
    "." +
    Buffer.from(JSON.stringify(forgedPayload), "utf8").toString("base64url") +
    "." +
    parts[2];
  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: forged,
      keyId: signed.keyId,
      verificationKeys: signed.verificationKeys,
      expectedUid: "uid-a",
      nowMs,
    }).reason,
    "lease_signature_invalid",
  );

  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: parts[0] + "." + parts[1] + ".not-a-real-signature",
      keyId: signed.keyId,
      verificationKeys: signed.verificationKeys,
      expectedUid: "uid-a",
      nowMs,
    }).reason,
    "lease_signature_invalid",
  );

  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: signed.signedToken,
      keyId: signed.keyId,
      verificationKeys: signed.verificationKeys,
      expectedUid: "uid-a",
      nowMs: Date.parse(decision.claims.validUntil),
    }).reason,
    "lease_expired",
  );
});

test("unsupported schema or policy version fails closed even when correctly signed", async () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const decision = buildOfflineLeaseClaims({
    uid: "policy-user",
    nowMs,
    leaseId: "lease-policy-0000000001",
    accountState: accountState({ base: "active" }),
  });
  const signer = testSigner("policy");

  const unsupported = {
    ...decision.claims,
    policyVersion: 999,
  };
  const signed = await signOfflineLeaseClaims(unsupported, signer.sign);
  const result = verifyOfflineLeaseToken({
    signedToken: signed.signedToken,
    keyId: signed.keyId,
    verificationKeys: signed.verificationKeys,
    expectedUid: "policy-user",
    nowMs,
  });
  assert.equal(result.valid, false);
  assert.equal(result.reason, "lease_policy_unsupported");
});

test("key rotation keeps already-issued leases verifiable while their signing key is cached", async () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const claimsA = buildOfflineLeaseClaims({
    uid: "rotation-user",
    nowMs,
    leaseId: "lease-rotation-a-000001",
    accountState: accountState({ base: "active" }),
  }).claims;
  const signerA = testSigner("rotation-a");
  const signerB = testSigner("rotation-b");
  const signedA = await signOfflineLeaseClaims(claimsA, signerA.sign);

  const combined = [signerA.key, signerB.key];
  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: signedA.signedToken,
      keyId: signedA.keyId,
      verificationKeys: combined,
      expectedUid: "rotation-user",
      nowMs,
    }).valid,
    true,
  );
  assert.equal(
    verifyOfflineLeaseToken({
      signedToken: signedA.signedToken,
      keyId: signedA.keyId,
      verificationKeys: [signerB.key],
      expectedUid: "rotation-user",
      nowMs,
    }).reason,
    "lease_key_unavailable",
  );
});

test("trial claim validation enforces Base-only and trialEndsAt", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const claim = buildOfflineLeaseClaims({
    uid: "trial-validation",
    nowMs,
    leaseId: "lease-trial-validation-1",
    accountState: accountState({
      trialConsumed: true,
      trialEndsAtMs: nowMs + 60_000,
      baseAccess: true,
    }),
  }).claims;

  assert.equal(
    validateOfflineLeaseClaims(claim, {
      expectedUid: "trial-validation",
      nowMs,
    }).valid,
    true,
  );

  const invalid = {
    ...claim,
    grants: ["base", "backpacking"],
  };
  assert.equal(
    validateOfflineLeaseClaims(invalid, {
      expectedUid: "trial-validation",
      nowMs,
    }).reason,
    "lease_entitlement_mismatch",
  );
});

test("offline lease claims contain no recorded-track or location history data", () => {
  const nowMs = Date.parse("2026-10-08T12:00:00.000Z");
  const claims = buildOfflineLeaseClaims({
    uid: "privacy-user",
    nowMs,
    leaseId: "lease-privacy-000000001",
    accountState: accountState({ base: "active" }),
  }).claims;
  assert.equal(/track|gpx|location|latitude|longitude/i.test(JSON.stringify(claims)), false);
});
