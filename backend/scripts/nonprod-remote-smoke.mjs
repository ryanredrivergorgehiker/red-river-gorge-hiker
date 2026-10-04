import { createRequire } from "node:module";

const requireFromFunctions = createRequire(
  new URL("../functions/package.json", import.meta.url),
);
const { applicationDefault, initializeApp } = requireFromFunctions("firebase-admin/app");
const { getAuth } = requireFromFunctions("firebase-admin/auth");

const projectId = process.env.GCLOUD_PROJECT || "rrgh-nonproduction";
const functionUrl = process.env.RRGH_FUNCTION_URL;
const apiKey = process.env.FIREBASE_API_KEY;
const serviceAccountId = process.env.RRGH_DEPLOY_SERVICE_ACCOUNT;
const smokeUid = "github-ci-smoke";

function requireValue(name, value) {
  if (!value) throw new Error("Missing required environment value: " + name);
  return value;
}

async function readJson(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    throw new Error("Expected JSON from " + response.url + "; got HTTP " + response.status);
  }
}

requireValue("RRGH_FUNCTION_URL", functionUrl);
requireValue("FIREBASE_API_KEY", apiKey);
requireValue("RRGH_DEPLOY_SERVICE_ACCOUNT", serviceAccountId);

const unauthenticated = await fetch(functionUrl, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ data: { operation: "getAccountState" } }),
});
const unauthenticatedBody = await readJson(unauthenticated);
if (
  unauthenticated.status !== 401 ||
  unauthenticatedBody?.error?.status !== "UNAUTHENTICATED"
) {
  throw new Error(
    "Unauthenticated callable check failed: HTTP " +
      unauthenticated.status +
      " / " +
      JSON.stringify(unauthenticatedBody),
  );
}
console.log("Remote unauthenticated denial: PASS");

const app = initializeApp({
  credential: applicationDefault(),
  projectId,
  serviceAccountId,
});

const customToken = await getAuth(app).createCustomToken(smokeUid, {
  purpose: "rrgh-nonproduction-github-smoke",
});

const signInResponse = await fetch(
  "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=" +
    encodeURIComponent(apiKey),
  {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      token: customToken,
      returnSecureToken: true,
    }),
  },
);
const signInBody = await readJson(signInResponse);
if (!signInResponse.ok || !signInBody.idToken) {
  throw new Error(
    "Firebase custom-token sign-in failed: HTTP " +
      signInResponse.status +
      " / " +
      JSON.stringify({ error: signInBody?.error?.message ?? "unknown" }),
  );
}
const idToken = signInBody.idToken;
console.log("Remote Firebase authenticated session: PASS");

const callableResponse = await fetch(functionUrl, {
  method: "POST",
  headers: {
    authorization: "Bearer " + idToken,
    "content-type": "application/json",
  },
  body: JSON.stringify({ data: { operation: "getAccountState" } }),
});
const callableBody = await readJson(callableResponse);
if (!callableResponse.ok || callableBody?.result?.uid !== smokeUid) {
  throw new Error(
    "Authenticated callable check failed: HTTP " +
      callableResponse.status +
      " / " +
      JSON.stringify(callableBody),
  );
}
console.log("Remote authenticated callable: PASS");

const firestoreResponse = await fetch(
  "https://firestore.googleapis.com/v1/projects/" +
    projectId +
    "/databases/(default)/documents/accounts/" +
    smokeUid,
  {
    headers: {
      authorization: "Bearer " + idToken,
    },
  },
);
if (firestoreResponse.status !== 403) {
  throw new Error(
    "Direct Firestore client denial failed: expected HTTP 403, got " +
      firestoreResponse.status,
  );
}
console.log("Remote direct Firestore denial: PASS");
console.log("RRGH non-production remote smoke: PASS");
