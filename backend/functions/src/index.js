import { initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";
import { HttpsError, onCall, onRequest } from "firebase-functions/v2/https";
import { ALLOWED_OPERATIONS } from "./domain.js";
import {
  createProtectedPackageDelivery,
  MAX_PROXY_RANGE_BYTES,
  parseBearerToken,
  resolvePackageCapability,
  resolveProtectedPackageRange,
  validatePackageObject,
} from "./delivery.js";
import {
  authorizeProtectedPackageForUid,
  getAccountStateForUid,
  initiateAccountDeletionForUid,
  startBaseTrialForUid,
} from "./store.js";

initializeApp();
const db = getFirestore();
const storage = getStorage();

function requireAuthenticatedUid(request) {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "An authenticated RRGH account is required.");
  }
  return uid;
}

function accessKeyForRequirement(requirement) {
  return requirement === "base" ? "base" : requirement;
}

function packageError(res, status, reason) {
  res
    .status(status)
    .set("Cache-Control", "private, no-store, max-age=0")
    .json({
      error: {
        reason,
      },
    });
}

export const rrghAccountApi = onCall(
  {
    region: "us-east5",
    minInstances: 0,
    maxInstances: 2,
    memory: "256MiB",
    cpu: "gcf_gen1",
    timeoutSeconds: 15,
    cors: true,
    enforceAppCheck: false,
  },
  async (request) => {
    const uid = requireAuthenticatedUid(request);
    const operation = request.data?.operation;

    if (!ALLOWED_OPERATIONS.includes(operation)) {
      throw new HttpsError("invalid-argument", "Unsupported backend operation.");
    }

    switch (operation) {
      case "getAccountState":
      case "getEntitlements":
        return getAccountStateForUid(db, uid);

      case "startBaseTrial": {
        const trial = await startBaseTrialForUid(db, uid);
        return {
          trial,
          account: await getAccountStateForUid(db, uid),
        };
      }

      case "authorizeProtectedPackage": {
        const packageId = request.data?.packageId;
        if (typeof packageId !== "string" || packageId.length < 1 || packageId.length > 128) {
          throw new HttpsError("invalid-argument", "A valid packageId is required.");
        }

        return authorizeProtectedPackageForUid(db, uid, packageId, {
          createDelivery: ({ packageId: id, packageData }) =>
            createProtectedPackageDelivery({
              db,
              uid,
              packageId: id,
              packageData,
              storage,
            }),
        });
      }

      case "initiateAccountDeletion": {
        const deletion = await initiateAccountDeletionForUid(db, uid);
        return {
          deletion,
          account: await getAccountStateForUid(db, uid),
        };
      }

      default:
        throw new HttpsError("invalid-argument", "Unsupported backend operation.");
    }
  },
);

export const rrghPackageDownload = onRequest(
  {
    region: "us-east5",
    minInstances: 0,
    maxInstances: 2,
    memory: "256MiB",
    cpu: "gcf_gen1",
    timeoutSeconds: 60,
    cors: false,
    enforceAppCheck: false,
  },
  async (req, res) => {
    if (req.method !== "GET") {
      packageError(res, 405, "method_not_allowed");
      return;
    }

    const token = parseBearerToken(req.get("authorization"));
    if (!token) {
      packageError(res, 401, "delivery_capability_invalid");
      return;
    }

    const resolved = await resolvePackageCapability(db, token);
    if (!resolved.valid) {
      packageError(
        res,
        resolved.reason === "delivery_capability_expired" ? 410 : 401,
        resolved.reason,
      );
      return;
    }

    const capability = resolved.capability;
    const packageSnapshot = await db
      .collection("packageCatalog")
      .doc(capability.packageId)
      .get();

    if (!packageSnapshot.exists) {
      packageError(res, 409, "package_superseded");
      return;
    }

    const packageData = packageSnapshot.data() ?? {};
    if (
      packageData.active !== true ||
      packageData.lifecycle === "superseded" ||
      packageData.deliveryState !== "ready" ||
      packageData.version !== capability.packageVersion ||
      packageData.requiredEntitlement !== capability.requiredEntitlement ||
      packageData.storageBucket !== capability.storageBucket ||
      packageData.objectName !== capability.objectName
    ) {
      packageError(res, 409, "package_version_superseded");
      return;
    }

    const account = await getAccountStateForUid(db, capability.uid);
    if (account.accountStatus !== "active") {
      packageError(res, 403, "account_not_active");
      return;
    }

    const accessKey = accessKeyForRequirement(
      packageData.requiredEntitlement,
    );
    if (account.access?.[accessKey] !== true) {
      packageError(res, 403, "not_entitled");
      return;
    }

    const object = await validatePackageObject(
      capability.packageId,
      packageData,
      storage,
    );
    if (!object.ready) {
      packageError(
        res,
        object.reason === "backend_temporarily_unavailable" ? 503 : 409,
        object.reason,
      );
      return;
    }

    const range = resolveProtectedPackageRange(
      req.get("range"),
      packageData.byteCount,
    );

    if (!range.valid) {
      res
        .status(416)
        .set("Cache-Control", "private, no-store, max-age=0")
        .set("Accept-Ranges", "bytes")
        .set("Content-Range", `bytes */${packageData.byteCount}`)
        .set(
          "X-RRGH-Max-Range-Bytes",
          String(MAX_PROXY_RANGE_BYTES),
        )
        .json({
          error: {
            reason: range.reason,
          },
        });
      return;
    }

    const status = range.partial ? 206 : 200;
    res.status(status);
    res.set("Cache-Control", "private, no-store, max-age=0");
    res.set("Accept-Ranges", "bytes");
    res.set("Content-Type", packageData.contentType ?? "application/octet-stream");
    res.set("Content-Length", String(range.length));
    res.set("X-RRGH-Max-Range-Bytes", String(MAX_PROXY_RANGE_BYTES));
    res.set("X-RRGH-Package-Id", capability.packageId);
    res.set("X-RRGH-Package-Version", packageData.version);
    res.set("X-RRGH-Package-SHA256", packageData.sha256);

    if (range.partial) {
      res.set(
        "Content-Range",
        `bytes ${range.start}-${range.end}/${packageData.byteCount}`,
      );
    }

    const stream = object.file.createReadStream({
      start: range.start,
      end: range.end,
    });

    stream.on("error", () => {
      if (!res.headersSent) {
        packageError(res, 503, "backend_temporarily_unavailable");
      } else {
        res.destroy();
      }
    });
    stream.pipe(res);
  },
);
