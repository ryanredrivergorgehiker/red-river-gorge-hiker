import { initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";
import { HttpsError, onCall, onRequest } from "firebase-functions/v2/https";
import { ALLOWED_OPERATIONS } from "./domain.js";
import { handlePackageDownload } from "./packageDelivery.js";
import {
  authorizeProtectedPackageForUid,
  getAccountStateForUid,
  initiateAccountDeletionForUid,
  startBaseTrialForUid,
} from "./store.js";

initializeApp();
const db = getFirestore();

const FUNCTION_REGION = "us-east5";
const PACKAGE_BUCKET = "rrgh-nonproduction-protected-packages-843975209563";
const projectId = process.env.GCLOUD_PROJECT || "rrgh-nonproduction";
const PACKAGE_DOWNLOAD_URL =
  `https://${FUNCTION_REGION}-${projectId}.cloudfunctions.net/rrghPackageDownload`;
const packageBucket = getStorage().bucket(PACKAGE_BUCKET);

function requireAuthenticatedUid(request) {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "An authenticated RRGH account is required.");
  }
  return uid;
}

export const rrghAccountApi = onCall(
  {
    region: FUNCTION_REGION,
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
          bucket: packageBucket,
          deliveryUrl: PACKAGE_DOWNLOAD_URL,
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
    region: FUNCTION_REGION,
    minInstances: 0,
    maxInstances: 2,
    memory: "256MiB",
    cpu: "gcf_gen1",
    timeoutSeconds: 60,
    cors: false,
    enforceAppCheck: false,
  },
  async (req, res) => {
    await handlePackageDownload({
      req,
      res,
      db,
      bucket: packageBucket,
      getAccountStateForUid,
    });
  },
);
