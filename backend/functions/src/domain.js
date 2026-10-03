export const ENTITLEMENTS = Object.freeze({
  BASE: "base",
  BACKPACKING: "backpacking",
  OFF_TRAIL: "off_trail",
});

export const ACCESS_KEYS = Object.freeze({
  BASE: "base",
  DAY_HIKES: "day_hikes",
  BACKPACKING: "backpacking",
  OFF_TRAIL: "off_trail",
});

export const ALLOWED_OPERATIONS = Object.freeze([
  "getAccountState",
  "startBaseTrial",
  "getEntitlements",
  "authorizeProtectedPackage",
  "initiateAccountDeletion",
]);

export const TRIAL_DURATION_MS = 7 * 24 * 60 * 60 * 1000;

export function normalizeEntitlementState(value) {
  return value === "active" ? "active" : value === "revoked" ? "revoked" : "none";
}

export function isTrialActive(trial, nowMs = Date.now()) {
  if (!trial?.consumed || !Number.isFinite(trial?.endsAtMs)) return false;
  return nowMs < trial.endsAtMs;
}

export function deriveAccess({
  accountStatus = "active",
  trial = null,
  entitlementStates = {},
  nowMs = Date.now(),
}) {
  const denied = {
    [ACCESS_KEYS.BASE]: false,
    [ACCESS_KEYS.DAY_HIKES]: false,
    [ACCESS_KEYS.BACKPACKING]: false,
    [ACCESS_KEYS.OFF_TRAIL]: false,
  };

  if (accountStatus !== "active") {
    return denied;
  }

  const basePurchased =
    normalizeEntitlementState(entitlementStates[ENTITLEMENTS.BASE]) === "active";
  const trialActive = isTrialActive(trial, nowMs);
  const baseAccess = basePurchased || trialActive;

  return {
    [ACCESS_KEYS.BASE]: baseAccess,
    [ACCESS_KEYS.DAY_HIKES]: baseAccess,
    [ACCESS_KEYS.BACKPACKING]:
      basePurchased &&
      normalizeEntitlementState(entitlementStates[ENTITLEMENTS.BACKPACKING]) ===
        "active",
    [ACCESS_KEYS.OFF_TRAIL]:
      basePurchased &&
      normalizeEntitlementState(entitlementStates[ENTITLEMENTS.OFF_TRAIL]) ===
        "active",
  };
}

export function canonicalEntitlementFromPackageRequirement(value) {
  if (Object.values(ENTITLEMENTS).includes(value)) return value;
  throw new Error("unsupported-package-entitlement");
}

export function evidenceSupportsEntitlement(evidence) {
  return evidence?.state === "validated";
}

export function deriveCanonicalEntitlementFromEvidence(evidenceRecords = []) {
  const valid = evidenceRecords.filter(evidenceSupportsEntitlement);
  if (valid.length === 0) {
    return {
      state: "revoked",
      supportingEvidenceIds: [],
      sourcePlatforms: [],
    };
  }

  return {
    state: "active",
    supportingEvidenceIds: [...new Set(valid.map((item) => item.evidenceId))].sort(),
    sourcePlatforms: [...new Set(valid.map((item) => item.store))].sort(),
  };
}
