import {
  X509Certificate,
  createHash,
  generateKeyPairSync,
  randomBytes,
  sign as cryptoSign,
  verify as cryptoVerify,
} from "node:crypto";

export const OFFLINE_LEASE_FORMAT = "compact_jws_rs256_v1";
export const OFFLINE_LEASE_ALGORITHM = "RS256";
export const OFFLINE_LEASE_TYPE = "RRGH-OFFLINE-ENTITLEMENT-LEASE";
export const OFFLINE_LEASE_SCHEMA_VERSION = 1;
export const OFFLINE_LEASE_POLICY_VERSION = 1;
export const OFFLINE_LEASE_POLICY_ID = "LEG-DEC-0035";
export const OFFLINE_LEASE_MAX_PAID_MS = 90 * 24 * 60 * 60 * 1000;
export const OFFLINE_LEASE_RENEWAL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

const CANONICAL_GRANTS = Object.freeze(["base", "backpacking", "off_trail"]);
const KEY_CACHE_MS = 60 * 60 * 1000;
let productionKeyCache = null;
let emulatorSigner = null;

function iso(ms) {
  return new Date(ms).toISOString();
}

function base64urlJson(value) {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

function entitlementRevisionForState(uid, state) {
  const material = {
    uid,
    accountStatus: state.accountStatus ?? "active",
    entitlements: {
      base: state.entitlements?.base ?? "none",
      backpacking: state.entitlements?.backpacking ?? "none",
      off_trail: state.entitlements?.off_trail ?? "none",
    },
    trial: {
      consumed: state.trial?.base?.consumed === true,
      startedAt: state.trial?.base?.startedAt ?? null,
      endsAt: state.trial?.base?.endsAt ?? null,
    },
  };

  return "sha256:" + createHash("sha256")
    .update(JSON.stringify(material), "utf8")
    .digest("hex");
}

function permanentGrantSet(state) {
  const basePermanent = state.entitlements?.base === "active";
  if (!basePermanent) return [];

  const grants = ["base"];
  if (state.entitlements?.backpacking === "active") grants.push("backpacking");
  if (state.entitlements?.off_trail === "active") grants.push("off_trail");
  return grants;
}

export function buildOfflineLeaseClaims({
  uid,
  accountState,
  nowMs = Date.now(),
  leaseId = randomBytes(18).toString("base64url"),
} = {}) {
  if (typeof uid !== "string" || uid.length === 0) {
    throw new Error("offline-lease-uid-required");
  }
  if (!accountState || accountState.accountStatus !== "active") {
    return {
      issued: false,
      reason: "account_not_active",
      claims: null,
    };
  }

  const permanentGrants = permanentGrantSet(accountState);
  const permanentBase = permanentGrants.includes("base");
  const trial = accountState.trial?.base ?? null;
  const trialEndsAtMs = Number(trial?.endsAtMs);
  const trialActive =
    !permanentBase &&
    accountState.access?.base === true &&
    trial?.consumed === true &&
    Number.isFinite(trialEndsAtMs) &&
    nowMs < trialEndsAtMs;

  let grants;
  let validUntilMs;
  let renewAfterMs = null;
  let trialMarker = false;
  let trialEndsAt = null;

  if (permanentBase) {
    grants = permanentGrants;
    validUntilMs = nowMs + OFFLINE_LEASE_MAX_PAID_MS;
    renewAfterMs = validUntilMs - OFFLINE_LEASE_RENEWAL_WINDOW_MS;
  } else if (trialActive) {
    grants = ["base"];
    validUntilMs = Math.min(nowMs + OFFLINE_LEASE_MAX_PAID_MS, trialEndsAtMs);
    trialMarker = true;
    trialEndsAt = iso(trialEndsAtMs);
  } else {
    return {
      issued: false,
      reason: "no_effective_access",
      claims: null,
    };
  }

  return {
    issued: true,
    reason: null,
    claims: {
      schemaVersion: OFFLINE_LEASE_SCHEMA_VERSION,
      policyVersion: OFFLINE_LEASE_POLICY_VERSION,
      policyId: OFFLINE_LEASE_POLICY_ID,
      leaseId,
      uid,
      issuedAt: iso(nowMs),
      validUntil: iso(validUntilMs),
      renewAfter: renewAfterMs === null ? null : iso(renewAfterMs),
      grants,
      trial: trialMarker,
      trialEndsAt,
      entitlementRevision: entitlementRevisionForState(uid, accountState),
    },
  };
}

export async function signOfflineLeaseClaims(claims, signer) {
  if (typeof signer !== "function") {
    throw new Error("offline-lease-signer-required");
  }

  const header = {
    alg: OFFLINE_LEASE_ALGORITHM,
    typ: OFFLINE_LEASE_TYPE,
    v: OFFLINE_LEASE_SCHEMA_VERSION,
  };
  const encodedHeader = base64urlJson(header);
  const encodedPayload = base64urlJson(claims);
  const signingInput = encodedHeader + "." + encodedPayload;

  const signed = await signer(Buffer.from(signingInput, "utf8"));
  if (
    !signed ||
    typeof signed.keyId !== "string" ||
    signed.keyId.length === 0 ||
    typeof signed.signatureBase64url !== "string" ||
    signed.signatureBase64url.length === 0 ||
    !Array.isArray(signed.verificationKeys) ||
    signed.verificationKeys.length === 0
  ) {
    throw new Error("offline-lease-signer-invalid-response");
  }

  const key = signed.verificationKeys.find((item) => item.keyId === signed.keyId);
  if (
    !key ||
    key.algorithm !== OFFLINE_LEASE_ALGORITHM ||
    typeof key.publicKeySpkiBase64 !== "string" ||
    key.publicKeySpkiBase64.length === 0
  ) {
    throw new Error("offline-lease-signing-key-unavailable");
  }

  return {
    format: OFFLINE_LEASE_FORMAT,
    algorithm: OFFLINE_LEASE_ALGORITHM,
    keyId: signed.keyId,
    signedToken: signingInput + "." + signed.signatureBase64url,
    verificationKeys: signed.verificationKeys
      .map((item) => ({
        keyId: item.keyId,
        algorithm: item.algorithm,
        publicKeySpkiBase64: item.publicKeySpkiBase64,
      }))
      .sort((a, b) => a.keyId.localeCompare(b.keyId)),
  };
}

function parseCompactJws(token) {
  if (typeof token !== "string") throw new Error("lease_malformed");
  const parts = token.split(".");
  if (parts.length !== 3 || parts.some((part) => part.length === 0)) {
    throw new Error("lease_malformed");
  }

  let header;
  let payload;
  try {
    header = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
    payload = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
  } catch {
    throw new Error("lease_malformed");
  }

  return {
    header,
    payload,
    signingInput: parts[0] + "." + parts[1],
    signature: Buffer.from(parts[2], "base64url"),
  };
}

export function validateOfflineLeaseClaims(
  claims,
  {
    expectedUid,
    nowMs = Date.now(),
  } = {},
) {
  if (!claims || typeof claims !== "object" || Array.isArray(claims)) {
    return { valid: false, reason: "lease_malformed" };
  }
  if (
    claims.schemaVersion !== OFFLINE_LEASE_SCHEMA_VERSION ||
    claims.policyVersion !== OFFLINE_LEASE_POLICY_VERSION ||
    claims.policyId !== OFFLINE_LEASE_POLICY_ID
  ) {
    return { valid: false, reason: "lease_policy_unsupported" };
  }
  if (
    typeof claims.leaseId !== "string" ||
    claims.leaseId.length < 16 ||
    typeof claims.uid !== "string" ||
    claims.uid.length === 0 ||
    typeof claims.entitlementRevision !== "string" ||
    !claims.entitlementRevision.startsWith("sha256:")
  ) {
    return { valid: false, reason: "lease_malformed" };
  }
  if (typeof expectedUid === "string" && claims.uid !== expectedUid) {
    return { valid: false, reason: "lease_uid_mismatch" };
  }
  if (
    !Array.isArray(claims.grants) ||
    claims.grants.length === 0 ||
    claims.grants.some((grant) => !CANONICAL_GRANTS.includes(grant)) ||
    new Set(claims.grants).size !== claims.grants.length ||
    !claims.grants.includes("base")
  ) {
    return { valid: false, reason: "lease_entitlement_mismatch" };
  }
  if (
    (claims.grants.includes("backpacking") || claims.grants.includes("off_trail")) &&
    !claims.grants.includes("base")
  ) {
    return { valid: false, reason: "lease_entitlement_mismatch" };
  }

  const issuedAtMs = Date.parse(claims.issuedAt);
  const validUntilMs = Date.parse(claims.validUntil);
  if (
    !Number.isFinite(issuedAtMs) ||
    !Number.isFinite(validUntilMs) ||
    validUntilMs <= issuedAtMs
  ) {
    return { valid: false, reason: "lease_malformed" };
  }
  if (nowMs >= validUntilMs) {
    return { valid: false, reason: "lease_expired" };
  }

  if (claims.trial === true) {
    if (
      claims.grants.length !== 1 ||
      claims.grants[0] !== "base" ||
      claims.renewAfter !== null ||
      typeof claims.trialEndsAt !== "string"
    ) {
      return { valid: false, reason: "lease_entitlement_mismatch" };
    }
    const trialEndsAtMs = Date.parse(claims.trialEndsAt);
    if (
      !Number.isFinite(trialEndsAtMs) ||
      validUntilMs > trialEndsAtMs ||
      nowMs >= trialEndsAtMs
    ) {
      return { valid: false, reason: "lease_expired" };
    }
  } else {
    if (claims.trial !== false || claims.trialEndsAt !== null) {
      return { valid: false, reason: "lease_malformed" };
    }
    const renewAfterMs = Date.parse(claims.renewAfter);
    if (
      !Number.isFinite(renewAfterMs) ||
      renewAfterMs < issuedAtMs ||
      renewAfterMs > validUntilMs
    ) {
      return { valid: false, reason: "lease_malformed" };
    }
  }

  return {
    valid: true,
    reason: null,
    claims,
  };
}

export function verifyOfflineLeaseToken({
  signedToken,
  keyId,
  verificationKeys,
  expectedUid,
  nowMs = Date.now(),
} = {}) {
  let parsed;
  try {
    parsed = parseCompactJws(signedToken);
  } catch {
    return { valid: false, reason: "lease_malformed" };
  }

  if (
    parsed.header?.alg !== OFFLINE_LEASE_ALGORITHM ||
    parsed.header?.typ !== OFFLINE_LEASE_TYPE ||
    parsed.header?.v !== OFFLINE_LEASE_SCHEMA_VERSION
  ) {
    return { valid: false, reason: "lease_policy_unsupported" };
  }

  if (
    typeof keyId !== "string" ||
    !Array.isArray(verificationKeys)
  ) {
    return { valid: false, reason: "lease_key_unavailable" };
  }

  const key = verificationKeys.find(
    (item) =>
      item?.keyId === keyId &&
      item?.algorithm === OFFLINE_LEASE_ALGORITHM &&
      typeof item?.publicKeySpkiBase64 === "string",
  );
  if (!key) return { valid: false, reason: "lease_key_unavailable" };

  let verified = false;
  try {
    verified = cryptoVerify(
      "RSA-SHA256",
      Buffer.from(parsed.signingInput, "utf8"),
      {
        key: Buffer.from(key.publicKeySpkiBase64, "base64"),
        format: "der",
        type: "spki",
      },
      parsed.signature,
    );
  } catch {
    return { valid: false, reason: "lease_signature_invalid" };
  }
  if (!verified) return { valid: false, reason: "lease_signature_invalid" };

  return validateOfflineLeaseClaims(parsed.payload, {
    expectedUid,
    nowMs,
  });
}

async function runtimeServiceAccountEmail() {
  const configured = process.env.RRGH_OFFLINE_LEASE_SIGNER_SERVICE_ACCOUNT;
  if (configured) return configured;

  const response = await fetch(
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
    {
      headers: {
        "Metadata-Flavor": "Google",
      },
      signal: AbortSignal.timeout(5_000),
    },
  );
  if (!response.ok) {
    throw new Error("offline-lease-runtime-identity-unavailable");
  }
  const email = (await response.text()).trim();
  if (!email.includes("@")) {
    throw new Error("offline-lease-runtime-identity-invalid");
  }
  return email;
}

async function googleAccessToken() {
  const response = await fetch(
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
    {
      headers: {
        "Metadata-Flavor": "Google",
      },
      signal: AbortSignal.timeout(5_000),
    },
  );
  if (!response.ok) {
    throw new Error("offline-lease-google-access-token-unavailable");
  }
  const token = await response.json();
  if (typeof token?.access_token !== "string" || token.access_token.length === 0) {
    throw new Error("offline-lease-google-access-token-invalid");
  }
  return token.access_token;
}

function certMapToVerificationKeys(certMap) {
  return Object.entries(certMap ?? {}).map(([keyId, pem]) => {
    const certificate = new X509Certificate(pem);
    const spki = certificate.publicKey.export({
      format: "der",
      type: "spki",
    });
    return {
      keyId,
      algorithm: OFFLINE_LEASE_ALGORITHM,
      publicKeySpkiBase64: Buffer.from(spki).toString("base64"),
    };
  });
}

async function serviceAccountVerificationKeys(email, forceRefresh = false) {
  if (
    !forceRefresh &&
    productionKeyCache?.email === email &&
    Date.now() - productionKeyCache.fetchedAtMs < KEY_CACHE_MS
  ) {
    return productionKeyCache.keys;
  }

  const response = await fetch(
    "https://www.googleapis.com/service_accounts/v1/metadata/x509/" +
      encodeURIComponent(email),
    {
      signal: AbortSignal.timeout(10_000),
    },
  );
  if (!response.ok) {
    throw new Error("offline-lease-verification-keys-unavailable");
  }
  const keys = certMapToVerificationKeys(await response.json());
  if (keys.length === 0) {
    throw new Error("offline-lease-verification-keys-empty");
  }
  productionKeyCache = {
    email,
    fetchedAtMs: Date.now(),
    keys,
  };
  return keys;
}

async function iamSignBlob(email, bytes) {
  const token = await googleAccessToken();
  const response = await fetch(
    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/" +
      encodeURIComponent(email) +
      ":signBlob",
    {
      method: "POST",
      headers: {
        authorization: "Bearer " + token,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        payload: Buffer.from(bytes).toString("base64"),
      }),
      signal: AbortSignal.timeout(10_000),
    },
  );
  if (!response.ok) {
    throw new Error(
      "offline-lease-signing-failed-http-" + response.status,
    );
  }
  const body = await response.json();
  if (
    typeof body.keyId !== "string" ||
    typeof body.signedBlob !== "string"
  ) {
    throw new Error("offline-lease-signing-response-invalid");
  }
  return {
    keyId: body.keyId,
    signatureBase64url: Buffer.from(body.signedBlob, "base64").toString("base64url"),
  };
}

export async function googleServiceAccountLeaseSigner(bytes) {
  const email = await runtimeServiceAccountEmail();
  const signed = await iamSignBlob(email, bytes);
  let verificationKeys = await serviceAccountVerificationKeys(email);
  if (!verificationKeys.some((item) => item.keyId === signed.keyId)) {
    verificationKeys = await serviceAccountVerificationKeys(email, true);
  }
  if (!verificationKeys.some((item) => item.keyId === signed.keyId)) {
    throw new Error("offline-lease-signing-key-not-published");
  }
  return {
    ...signed,
    verificationKeys,
  };
}

export function createEphemeralEmulatorLeaseSigner() {
  if (emulatorSigner) return emulatorSigner;

  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  const keyId = "emulator-" +
    createHash("sha256")
      .update(publicKey.export({ format: "der", type: "spki" }))
      .digest("hex")
      .slice(0, 24);
  const verificationKeys = [
    {
      keyId,
      algorithm: OFFLINE_LEASE_ALGORITHM,
      publicKeySpkiBase64: publicKey
        .export({ format: "der", type: "spki" })
        .toString("base64"),
    },
  ];

  emulatorSigner = async (bytes) => ({
    keyId,
    signatureBase64url: cryptoSign(
      "RSA-SHA256",
      bytes,
      privateKey,
    ).toString("base64url"),
    verificationKeys,
  });
  return emulatorSigner;
}

export function leaseSignerForRuntime() {
  const emulator =
    process.env.FUNCTIONS_EMULATOR === "true" &&
    (process.env.GCLOUD_PROJECT ?? "").startsWith("demo-");
  return emulator
    ? createEphemeralEmulatorLeaseSigner()
    : googleServiceAccountLeaseSigner;
}
