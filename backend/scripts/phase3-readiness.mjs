import fs from "node:fs";

const firebaseConfig = JSON.parse(fs.readFileSync(new URL("../firebase.json", import.meta.url)));
const index = fs.readFileSync(new URL("../functions/src/index.js", import.meta.url), "utf8");
const rules = fs.readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(firebaseConfig.firestore?.rules === "firestore.rules", "Firestore rules must remain explicit.");
assert(!("storage" in firebaseConfig), "Cloud Storage must not be provisioned in Phase 3 yet.");
assert(index.includes('region: "us-east5"'), "Function must be pinned to us-east5.");
assert(index.includes("minInstances: 0"), "Non-production function must scale to zero.");
assert(index.includes("maxInstances: 2"), "Non-production function maxInstances must remain 2.");
assert(index.includes('cpu: "gcf_gen1"'), "Non-production function must use fractional/Gen1 CPU allocation.");
assert(index.includes("enforceAppCheck: false"), "App Check must stay observe-only until clients are enrolled.");
assert(rules.includes("allow read, write: if false;"), "Direct Firestore client access must remain deny-all.");
assert(!/userTracks|uploadTrack|syncTrack|exportGpx/i.test(index), "No user-track or GPX server API is allowed.");

console.log("Phase 3 readiness guardrails: PASS");
