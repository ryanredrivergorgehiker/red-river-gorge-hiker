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
  firestoreRules.includes("allow read, write: if false;"),
  "Direct Firestore client access must remain deny-all.",
);
assert(
  storageRules.includes("allow read, write: if false;"),
  "Direct Firebase Storage client access must remain deny-all.",
);
assert(
  !/firebaseStorageDownloadTokens|token=|alt=media/i.test(
    index + "\n" + delivery,
  ),
  "Permanent Firebase download-token patterns are prohibited.",
);
assert(
  !/userTracks|uploadTrack|syncTrack|exportGpx/i.test(index),
  "No user-track or GPX server API is allowed.",
);

console.log("Lane 20 non-production delivery guardrails: PASS");
