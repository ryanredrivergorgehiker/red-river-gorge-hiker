import { initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { HttpsError, onCall, onRequest } from "firebase-functions/v2/https";
import { ALLOWED_OPERATIONS, ENTITLEMENTS } from "./domain.js";
import {
  createProtectedPackageDelivery,
  parseBearerToken,
  resolvePackageCapability,
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

const functionOptions = Object.freeze({
  region: "us-east5",
  minInstances: 0,
  maxInstances: 2,
  memory: "256MiB",
  cpu: "gcf_gen1",
});

function requireAuthenticatedUid(request) {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "An authenticated RRGH account is required.");
  }
  return uid;
}

function sendDeliveryError(response, status, reason) {
  response
    .status(status)
    .set("Cache-Control", "private, no-store, max-age=0")
    .json({ error: { reason } });
}

function accessKeyForRequirement(requirement) {
  return requirement === ENTITLEMENTS.BASE ? "base" : requirement;
}

export const rrghAccountApi = onCall(
  {
    ...functionOptions,
    timeoutSeconds: 15,
    cors: true,

    // App Check remains observe-only until the Apple Team ID is available,
    // the exact clients are enrolled, and legitimate traffic is observed.
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
          createDelivery: ({ packageId: resolvedPackageId, packageData }) =>
            createProtectedPackageDelivery({
              db,
              uid,
              packageId: resolvedPackageId,
              packageData,
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
    ...functionOptions,
    timeoutSeconds: 60,
    cors: false,
  },
  async (request, response) => {
    if (request.method !== "GET") {
      response.set("Allow", "GET");
      sendDeliveryError(response, 405, "method_not_allowed");
      return;
    }

    const token = parseBearerToken(request.get("authorization"));
    if (!token) {
      sendDeliveryError(response, 401, "delivery_capability_invalid");
      return;
    }

    let resolved;
    try {
      resolved = await resolvePackageCapability(db, token);
    } catch {
      sendDeliveryError(response, 503, "backend_temporarily_unavailable");
      return;
    }

    if (!resolved.valid) {
      sendDeliveryError(
        response,
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
      sendDeliveryError(response, 409, "package_superseded");
      return;
    }

    const packageData = packageSnapshot.data() ?? {};
    if (
      packageData.active !== true ||
      packageData.lifecycle !== "active" ||
      packageData.deliveryState !== "ready" ||
      packageData.version !== capability.packageVersion ||
      packageData.storageBucket !== capability.storageBucket ||
      packageData.objectName !== capability.objectName
    ) {
      sendDeliveryError(response, 409, "package_superseded");
      return;
    }

    const account = await getAccountStateForUid(db, capability.uid);
    if (account.accountStatus !== "active") {
      sendDeliveryError(response, 403, "account_not_active");
      return;
    }

    const requirement = packageData.requiredEntitlement;
    if (!Object.values(ENTITLEMENTS).includes(requirement)) {
      sendDeliveryError(response, 409, "package_configuration_invalid");
      return;
    }

    const accessKey = accessKeyForRequirement(requirement);
    if (account.access?.[accessKey] !== true) {
      sendDeliveryError(response, 403, "not_entitled");
      return;
    }

    const object = await validatePackageObject(
      capability.packageId,
      packageData,
    );
    if (!object.ready) {
      const status =
        object.reason === "backend_temporarily_unavailable"
          ? 503
          : object.reason === "package_object_mismatch"
            ? 409
            : 404;
      sendDeliveryError(response, status, object.reason);
      return;
    }

    response.status(200);
    response.set("Cache-Control", "private, no-store, max-age=0");
    response.set("Content-Type", packageData.contentType ?? "application/octet-stream");
    response.set("Content-Length", String(packageData.byteCount));
    response.set("X-RRGH-Package-Id", capability.packageId);
    response.set("X-RRGH-Package-Version", packageData.version);
    response.set("X-RRGH-Package-SHA256", packageData.sha256);
    response.set(
      "Content-Disposition",
      `attachment; filename="${capability.packageId}-${packageData.version}.rrghpkg"`,
    );

    await new Promise((resolve, reject) => {
      const stream = object.file.createReadStream();
      stream.on("error", reject);
      response.on("finish", resolve);
      response.on("close", resolve);
      stream.pipe(response);
    }).catch(() => {
      if (!response.headersSent) {
        sendDeliveryError(response, 503, "backend_temporarily_unavailable");
      } else {
        response.destroy();
      }
    });
  },
);
