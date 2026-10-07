import { createHash, randomBytes } from "node:crypto";
import { Timestamp } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";

export const DELIVERY_METHOD = "capability_https";
export const DELIVERY_AUTHORIZATION_SCHEME = "Bearer";
export const DEFAULT_CAPABILITY_TTL_SECONDS = 300;

function capabilityCollection(db) {
  return db.collection("packageCapabilities");
}

export function hashCapabilityToken(token) {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

export function parseBearerToken(value) {
  if (typeof value !== "string") return null;
  const match = value.match(/^Bearer\s+([^\s]+)$/i);
  return match?.[1] ?? null;
}

export function packageDownloadUrl(projectId = process.env.GCLOUD_PROJECT) {
  const explicit = process.env.RRGH_PACKAGE_DOWNLOAD_URL;
  if (explicit) return explicit;

  const resolvedProjectId = projectId || "rrgh-nonproduction";
  if (
    process.env.FUNCTIONS_EMULATOR === "true" ||
    process.env.FIRESTORE_EMULATOR_HOST ||
    process.env.FIREBASE_STORAGE_EMULATOR_HOST
  ) {
    return `http://127.0.0.1:5001/${resolvedProjectId}/us-east5/rrghPackageDownload`;
  }

  return `https://us-east5-${resolvedProjectId}.cloudfunctions.net/rrghPackageDownload`;
}

function objectMetadataValue(metadata, key) {
  return metadata?.metadata?.[key] ?? null;
}

export async function validatePackageObject(
  packageId,
  packageData,
  storage = getStorage(),
) {
  const bucketName = packageData.storageBucket;
  const objectName = packageData.objectName;
  if (
    typeof bucketName !== "string" ||
    bucketName.length === 0 ||
    typeof objectName !== "string" ||
    objectName.length === 0
  ) {
    return { ready: false, reason: "package_object_unavailable" };
  }

  try {
    const file = storage.bucket(bucketName).file(objectName);
    const [metadata] = await file.getMetadata();
    const expectedByteCount = Number(packageData.byteCount);
    const actualByteCount = Number(metadata.size);
    const expectedSha256 = String(packageData.sha256 ?? "").toLowerCase();
    const objectSha256 = String(
      objectMetadataValue(metadata, "rrgh-sha256") ?? "",
    ).toLowerCase();
    const objectPackageId = objectMetadataValue(metadata, "rrgh-package-id");
    const objectVersion = objectMetadataValue(metadata, "rrgh-version");

    if (
      !Number.isSafeInteger(expectedByteCount) ||
      expectedByteCount <= 0 ||
      actualByteCount !== expectedByteCount ||
      !expectedSha256 ||
      objectSha256 !== expectedSha256 ||
      objectPackageId !== packageId ||
      objectVersion !== packageData.version
    ) {
      return { ready: false, reason: "package_object_mismatch" };
    }

    return {
      ready: true,
      file,
      metadata,
    };
  } catch (error) {
    if (error?.code === 404) {
      return { ready: false, reason: "package_object_unavailable" };
    }
    return { ready: false, reason: "backend_temporarily_unavailable" };
  }
}

export async function createProtectedPackageDelivery({
  db,
  uid,
  packageId,
  packageData,
  storage = getStorage(),
  now = Timestamp.now(),
  ttlSeconds = DEFAULT_CAPABILITY_TTL_SECONDS,
}) {
  const object = await validatePackageObject(packageId, packageData, storage);
  if (!object.ready) {
    return {
      ready: false,
      reason: object.reason,
      method: null,
      httpMethod: null,
      url: null,
      expiresAt: null,
      authorizationScheme: null,
      authorizationToken: null,
    };
  }

  const boundedTtlSeconds = Math.min(
    Math.max(Number(ttlSeconds) || DEFAULT_CAPABILITY_TTL_SECONDS, 30),
    900,
  );
  const token = randomBytes(32).toString("base64url");
  const tokenHash = hashCapabilityToken(token);
  const expiresAt = Timestamp.fromMillis(
    now.toMillis() + boundedTtlSeconds * 1000,
  );

  await capabilityCollection(db).doc(tokenHash).set({
    uid,
    packageId,
    packageVersion: packageData.version,
    requiredEntitlement: packageData.requiredEntitlement,
    storageBucket: packageData.storageBucket,
    objectName: packageData.objectName,
    issuedAt: now,
    expiresAt,
    state: "active",
    policyVersion: 1,
  });

  return {
    ready: true,
    reason: null,
    method: DELIVERY_METHOD,
    httpMethod: "GET",
    url: packageDownloadUrl(),
    expiresAt: expiresAt.toDate().toISOString(),
    authorizationScheme: DELIVERY_AUTHORIZATION_SCHEME,
    authorizationToken: token,
  };
}

export const MAX_PROXY_RANGE_BYTES = 8 * 1024 * 1024;

export function resolveProtectedPackageRange(
  rangeHeader,
  totalBytes,
  maxBytes = MAX_PROXY_RANGE_BYTES,
) {
  const total = Number(totalBytes);
  const maximum = Number(maxBytes);

  if (
    !Number.isSafeInteger(total) ||
    total <= 0 ||
    !Number.isSafeInteger(maximum) ||
    maximum <= 0
  ) {
    return {
      valid: false,
      reason: "invalid_range_configuration",
    };
  }

  if (rangeHeader == null || rangeHeader === "") {
    if (total <= maximum) {
      return {
        valid: true,
        partial: false,
        start: 0,
        end: total - 1,
        length: total,
      };
    }

    return {
      valid: false,
      reason: "range_required",
    };
  }

  if (typeof rangeHeader !== "string") {
    return {
      valid: false,
      reason: "invalid_range",
    };
  }

  const match = rangeHeader.match(/^bytes=(\d+)-(\d*)$/);
  if (!match) {
    return {
      valid: false,
      reason: "invalid_range",
    };
  }

  const start = Number(match[1]);
  if (
    !Number.isSafeInteger(start) ||
    start < 0 ||
    start >= total
  ) {
    return {
      valid: false,
      reason: "range_not_satisfiable",
    };
  }

  const requestedEnd =
    match[2] === ""
      ? Math.min(total - 1, start + maximum - 1)
      : Number(match[2]);

  if (
    !Number.isSafeInteger(requestedEnd) ||
    requestedEnd < start
  ) {
    return {
      valid: false,
      reason: "invalid_range",
    };
  }

  const end = Math.min(requestedEnd, total - 1);
  const length = end - start + 1;

  if (length > maximum) {
    return {
      valid: false,
      reason: "range_too_large",
    };
  }

  return {
    valid: true,
    partial: true,
    start,
    end,
    length,
  };
}

export async function resolvePackageCapability(
  db,
  token,
  now = Timestamp.now(),
) {
  if (typeof token !== "string" || token.length < 32 || token.length > 256) {
    return { valid: false, reason: "delivery_capability_invalid" };
  }

  const ref = capabilityCollection(db).doc(hashCapabilityToken(token));
  const snapshot = await ref.get();
  if (!snapshot.exists) {
    return { valid: false, reason: "delivery_capability_invalid" };
  }

  const data = snapshot.data() ?? {};
  const expiresAtMs =
    typeof data.expiresAt?.toMillis === "function"
      ? data.expiresAt.toMillis()
      : NaN;

  if (
    data.state !== "active" ||
    !Number.isFinite(expiresAtMs)
  ) {
    return { valid: false, reason: "delivery_capability_invalid" };
  }

  if (now.toMillis() >= expiresAtMs) {
    return {
      valid: false,
      reason: "delivery_capability_expired",
      capabilityRef: ref,
    };
  }

  return {
    valid: true,
    capability: data,
    capabilityRef: ref,
  };
}
