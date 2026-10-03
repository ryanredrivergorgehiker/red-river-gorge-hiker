import { initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import { ALLOWED_OPERATIONS } from "./domain.js";
import {
  authorizeProtectedPackageForUid,
  getAccountStateForUid,
  initiateAccountDeletionForUid,
  startBaseTrialForUid,
} from "./store.js";

initializeApp();
const db = getFirestore();

function requireAuthenticatedUid(request) {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "An authenticated RRGH account is required.");
  }
  return uid;
}

export const rrghAccountApi = onCall(
  {
    // Phase 3 non-production cost/placement guardrails.
    // Firestore will be provisioned in the same regional location.
    region: "us-east5",
    minInstances: 0,
    maxInstances: 2,
    memory: "256MiB",
    cpu: "gcf_gen1",
    timeoutSeconds: 15,

    cors: true,

    // App Check is registered and observed before enforcement. Enforcement is
    // deliberately false until Website/iOS/Android clients are enrolled and
    // verified so we do not lock ourselves out during non-production setup.
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
        return authorizeProtectedPackageForUid(db, uid, packageId);
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
