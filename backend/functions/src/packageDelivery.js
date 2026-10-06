import { randomBytes, createHash } from "node:crypto";
import { getAuth } from "firebase-admin/auth";
import { Timestamp } from "firebase-admin/firestore";

export const PACKAGE_DELIVERY_METHOD = "rrgh_authenticated_https_capability_v1";
export const PACKAGE_CAPABILITY_HEADER = "X-RRGH-Package-Capability";
export const PACKAGE_CAPABILITY_TTL_MS = 5 * 60 * 1000;

function sha256Hex(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function packageDescriptor(packageId, packageData) {
  return {
    packageId,
    version: packageData.version ?? null,
    sha256: packageData.sha256 ?? null,
    byteCount: Number.isFinite(packageData.byteCount) ? packageData.byteCount : null,
    requiredEntitlement: packageData.requiredEntitlement,
    kind: packageData.kind ?? null,
    routeId: packageData.routeId ?? null,
    mediaType: packageData.mediaType ?? null,
    manifest: packageData.manifest ?? null,
  };
}

export async function verifyGovernedObject(bucket, packageData) {
  if (
    packageData.deliveryReady !== true ||
    !packageData.objectPath ||
    !packageData.sha256 ||
    !Number.isFinite(packageData.byteCount)
  ) {
    return {
      ready: false,
      reason: packageData.unavailableReason ?? "package_not_ready",
    };
  }

  try {
    const [metadata] = await bucket.file(packageData.objectPath).getMetadata();
    const objectSize = Number(metadata.size);
    const custom = metadata.metadata ?? {};

    if (
      objectSize !== packageData.byteCount ||
      String(custom.rrghSha256 ?? "").toLowerCase() !== packageData.sha256.toLowerCase() ||
      custom.rrghPackageId !== packageData.packageId ||
      custom.rrghPackageVersion !== packageData.version
    ) {
      return {
        ready: false,
        reason: "package_object_metadata_mismatch",
      };
    }

    return { ready: true, reason: null };
  } catch (error) {
    if (error?.code === 404) {
      return { ready: false, reason: "package_object_missing" };
    }
    return { ready: false, reason: "package_temporarily_unavailable" };
  }
}

export async function issuePackageCapability(
  db,
  {
    uid,
    packageId,
    version,
    requiredEntitlement,
    objectPath,
    deliveryUrl,
    nowMs = Date.now(),
  },
) {
  const capability = randomBytes(32).toString("base64url");
  const capabilityHash = sha256Hex(capability);
  const expiresAtMs = nowMs + PACKAGE_CAPABILITY_TTL_MS;
  const expiresAt = Timestamp.fromMillis(expiresAtMs);

  await db.collection("packageDeliveryCapabilities").doc(capabilityHash).set({
    uid,
    packageId,
    version,
    requiredEntitlement,
    objectPath,
    createdAt: Timestamp.fromMillis(nowMs),
    expiresAt,
    policyVersion: 1,
  });

  return {
    ready: true,
    reason: null,
    method: PACKAGE_DELIVERY_METHOD,
    url: deliveryUrl,
    expiresAt: new Date(expiresAtMs).toISOString(),
    capability,
    capabilityHeader: PACKAGE_CAPABILITY_HEADER,
  };
}

function bearerToken(req) {
  const value = req.get("authorization") ?? "";
  const match = value.match(/^Bearer\s+(.+)$/i);
  return match?.[1] ?? null;
}

function writeJson(res, status, reason) {
  res
    .status(status)
    .set("Cache-Control", "no-store")
    .json({ ok: false, reason });
}

export async function handlePackageDownload({
  req,
  res,
  db,
  bucket,
  getAccountStateForUid,
}) {
  if (req.method !== "GET") {
    res.set("Allow", "GET");
    writeJson(res, 405, "method_not_allowed");
    return;
  }

  const idToken = bearerToken(req);
  const capability = req.get(PACKAGE_CAPABILITY_HEADER);

  if (!idToken) {
    writeJson(res, 401, "authentication_required");
    return;
  }
  if (!capability) {
    writeJson(res, 403, "retrieval_capability_required");
    return;
  }

  let decoded;
  try {
    decoded = await getAuth().verifyIdToken(idToken);
  } catch {
    writeJson(res, 401, "authentication_invalid");
    return;
  }

  const capabilityHash = sha256Hex(capability);
  const capabilityRef = db.collection("packageDeliveryCapabilities").doc(capabilityHash);
  const capabilitySnapshot = await capabilityRef.get();

  if (!capabilitySnapshot.exists) {
    writeJson(res, 403, "retrieval_capability_invalid");
    return;
  }

  const capabilityData = capabilitySnapshot.data() ?? {};
  const expiresAtMs = capabilityData.expiresAt?.toMillis?.() ?? 0;

  if (capabilityData.uid !== decoded.uid) {
    writeJson(res, 403, "retrieval_capability_invalid");
    return;
  }
  if (!Number.isFinite(expiresAtMs) || Date.now() >= expiresAtMs) {
    writeJson(res, 410, "retrieval_capability_expired");
    return;
  }

  const packageSnapshot = await db
    .collection("packageCatalog")
    .doc(capabilityData.packageId)
    .get();

  if (!packageSnapshot.exists) {
    writeJson(res, 404, "package_not_found");
    return;
  }

  const packageData = packageSnapshot.data() ?? {};
  if (packageData.active !== true) {
    writeJson(res, 409, "package_superseded");
    return;
  }
  if (packageData.version !== capabilityData.version) {
    writeJson(res, 409, "package_version_superseded");
    return;
  }

  const account = await getAccountStateForUid(db, decoded.uid);
  if (account.accountStatus !== "active") {
    writeJson(res, 403, "account_not_active");
    return;
  }

  const requirement = packageData.requiredEntitlement;
  const accessKey = requirement === "base" ? "base" : requirement;
  if (account.access?.[accessKey] !== true) {
    writeJson(res, 403, "not_entitled");
    return;
  }

  const governedObject = await verifyGovernedObject(bucket, {
    ...packageData,
    packageId: capabilityData.packageId,
  });
  if (!governedObject.ready) {
    writeJson(res, 503, "package_temporarily_unavailable");
    return;
  }

  const file = bucket.file(packageData.objectPath);

  res.status(200);
  res.set("Cache-Control", "private, no-store, max-age=0");
  res.set("Content-Type", packageData.mediaType ?? "application/octet-stream");
  res.set("Content-Length", String(packageData.byteCount));
  res.set("X-RRGH-Package-Id", capabilityData.packageId);
  res.set("X-RRGH-Package-Version", packageData.version);
  res.set("X-RRGH-Package-SHA256", packageData.sha256);

  const stream = file.createReadStream();
  stream.on("error", () => {
    if (!res.headersSent) {
      writeJson(res, 503, "package_temporarily_unavailable");
    } else {
      res.destroy();
    }
  });
  stream.pipe(res);
}
