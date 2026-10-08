import fs from "node:fs";

const firebaseConfig = JSON.parse(
  fs.readFileSync(new URL("../firebase.json", import.meta.url)),
);
const index = fs.readFileSync(
  new URL("../functions/src/index.js", import.meta.url),
  "utf8",
);
const delivery = fs.readFileSync(
  new URL("../functions/src/delivery.js", import.meta.url),
  "utf8",
);
const offlineLease = fs.readFileSync(
  new URL("../functions/src/offlineLease.js", import.meta.url),
  "utf8",
);
const firestoreRules = fs.readFileSync(
  new URL("../firestore.rules", import.meta.url),
  "utf8",
);
const storageRules = fs.readFileSync(
  new URL("../storage.rules", import.meta.url),
  "utf8",
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(
  firebaseConfig.firestore?.rules === "firestore.rules",
  "Firestore rules must remain explicit.",
);
assert(
  firebaseConfig.storage?.rules === "storage.rules",
  "Storage client rules must remain explicit.",
);
assert(
  index.includes('region: "us-east5"'),
  "Functions must be pinned to us-east5.",
);
assert(
  index.includes("minInstances: 0"),
  "Non-production functions must scale to zero.",
);
assert(
  index.includes("maxInstances: 2"),
  "Non-production functions maxInstances must remain 2.",
);
assert(
  index.includes('cpu: "gcf_gen1"'),
  "Non-production functions must use fractional/Gen1 CPU allocation.",
);
assert(
  index.includes("enforceAppCheck: false"),
  "App Check must stay observe-only until the Apple Team ID/client gate closes.",
);
assert(
  index.includes("rrghPackageDownload"),
  "Protected package retrieval must remain on the governed server endpoint.",
);
assert(
  delivery.includes("packageCapabilities"),
  "Short-lived package capability state must be present.",
);
assert(
  delivery.includes("DEFAULT_CAPABILITY_TTL_SECONDS = 300"),
  "Package capability TTL must remain five minutes unless the contract is revised.",
);
assert(
  index.includes('"issueOfflineAccessLease"'),
  "LEG-DEC-0035 offline lease issuance must remain an authenticated callable operation.",
);
assert(
  offlineLease.includes('OFFLINE_LEASE_MAX_PAID_MS = 90 * 24 * 60 * 60 * 1000'),
  "Permanent offline lease duration must remain bounded to 90 days.",
);
assert(
  offlineLease.includes('OFFLINE_LEASE_RENEWAL_WINDOW_MS = 30 * 24 * 60 * 60 * 1000'),
  "Paid lease proactive renewal window must begin by 30 days remaining.",
);
assert(
  offlineLease.includes('OFFLINE_LEASE_POLICY_ID = "LEG-DEC-0035"'),
  "Offline lease payload must remain bound to LEG-DEC-0035.",
);
assert(
  offlineLease.includes('"backend-secrets/offline-lease/keyring-v1.json"'),
  "Offline lease signing must read the private keyring only from the existing protected bucket.",
);
assert(
  offlineLease.includes("privateKeyPkcs8Base64"),
  "Offline lease signing must keep private signing material server-side.",
);
assert(
  !offlineLease.includes("iamcredentials.googleapis.com"),
  "Offline lease signing must not depend on IAM Token Creator or paid KMS infrastructure.",
);
assert(
  !/BEGIN (RSA )?PRIVATE KEY|PRIVATE KEY-----/.test(offlineLease),
  "No offline lease private key may be committed to source.",
);
assert(
  firestoreRules.includes("allow read, write: if false;"),
  "Direct Firestore client access must remain deny-all.",
);
assert(
  storageRules.includes("allow read, write: if false;"),
  "Direct Firebase Storage client access must remain deny-all.",
);
assert(
  !/firebaseStorageDownloadTokens|token=|alt=media/i.test(
    index + "\n" + delivery + "\n" + offlineLease,
  ),
  "Permanent Firebase download-token patterns are prohibited.",
);
assert(
  !/userTracks|uploadTrack|syncTrack|exportGpx/i.test(index),
  "No user-track or GPX server API is allowed.",
);

console.log("Lane 20 non-production delivery + offline lease guardrails: PASS");
