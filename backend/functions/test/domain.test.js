import test from "node:test";
import assert from "node:assert/strict";
import {
  ALLOWED_OPERATIONS,
  deriveAccess,
  deriveCanonicalEntitlementFromEvidence,
} from "../src/domain.js";

test("Base trial unlocks Base and Day Hikes only", () => {
  const now = Date.now();
  const access = deriveAccess({
    trial: {
      consumed: true,
      endsAtMs: now + 60_000,
    },
    entitlementStates: {
      base: "none",
      backpacking: "active",
      off_trail: "active",
    },
    nowMs: now,
  });

  assert.deepEqual(access, {
    base: true,
    day_hikes: true,
    backpacking: false,
    off_trail: false,
  });
});

test("Permanent Base is required for paid extensions", () => {
  const access = deriveAccess({
    trial: null,
    entitlementStates: {
      base: "active",
      backpacking: "active",
      off_trail: "revoked",
    },
  });

  assert.deepEqual(access, {
    base: true,
    day_hikes: true,
    backpacking: true,
    off_trail: false,
  });
});

test("Deletion-pending account has no effective access", () => {
  const access = deriveAccess({
    accountStatus: "deletion_pending",
    trial: {
      consumed: true,
      endsAtMs: Date.now() + 60_000,
    },
    entitlementStates: {
      base: "active",
      backpacking: "active",
      off_trail: "active",
    },
  });

  assert.deepEqual(access, {
    base: false,
    day_hikes: false,
    backpacking: false,
    off_trail: false,
  });
});

test("One valid store record keeps a canonical entitlement active", () => {
  const result = deriveCanonicalEntitlementFromEvidence([
    { evidenceId: "apple-1", store: "apple", state: "refunded" },
    { evidenceId: "google-1", store: "google_play", state: "validated" },
  ]);

  assert.deepEqual(result, {
    state: "active",
    supportingEvidenceIds: ["google-1"],
    sourcePlatforms: ["google_play"],
  });
});

test("No valid evidence revokes the canonical entitlement", () => {
  const result = deriveCanonicalEntitlementFromEvidence([
    { evidenceId: "apple-1", store: "apple", state: "refunded" },
    { evidenceId: "google-1", store: "google_play", state: "revoked" },
  ]);

  assert.deepEqual(result, {
    state: "revoked",
    supportingEvidenceIds: [],
    sourcePlatforms: [],
  });
});

test("No customer track operation exists in the callable contract", () => {
  assert.deepEqual(ALLOWED_OPERATIONS, [
    "getAccountState",
    "startBaseTrial",
    "getEntitlements",
    "authorizeProtectedPackage",
    "initiateAccountDeletion",
  ]);
  assert.equal(ALLOWED_OPERATIONS.some((name) => /track|gpx|upload|sync/i.test(name)), false);
});


test("Permanent Base unlocks both extension entitlements when purchased", () => {
  const access = deriveAccess({
    entitlementStates: {
      base: "active",
      backpacking: "active",
      off_trail: "active",
    },
  });

  assert.deepEqual(access, {
    base: true,
    day_hikes: true,
    backpacking: true,
    off_trail: true,
  });
});
