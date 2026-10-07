import { createHash } from "node:crypto";
import { createRequire } from "node:module";

const requireFromFunctions = createRequire(
  new URL("../functions/package.json", import.meta.url),
);
const { applicationDefault, initializeApp } = requireFromFunctions("firebase-admin/app");
const { getAuth } = requireFromFunctions("firebase-admin/auth");
const { getFirestore, Timestamp } = requireFromFunctions("firebase-admin/firestore");

const projectId = process.env.GCLOUD_PROJECT || "rrgh-nonproduction";
const functionUrl = process.env.RRGH_FUNCTION_URL;
const apiKey = process.env.FIREBASE_API_KEY;
const serviceAccountId = process.env.RRGH_DEPLOY_SERVICE_ACCOUNT;
const smokeUid = "github-ci-smoke";

function requireValue(name, value) {
  if (!value) throw new Error("Missing required environment value: " + name);
  return value;
}

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

function capabilityHash(token) {
  return sha256(Buffer.from(token, "utf8"));
}

const PACKAGE_RANGE_BYTES = 8 * 1024 * 1024;

async function fetchPackageBytesInRanges(
  delivery,
  descriptor,
) {
  const chunks = [];
  let offset = 0;
  let packageIdHeader = null;
  let versionHeader = null;

  while (offset < descriptor.byteCount) {
    const end = Math.min(
      descriptor.byteCount - 1,
      offset + PACKAGE_RANGE_BYTES - 1,
    );

    const response = await fetch(delivery.url, {
      method: "GET",
      headers: {
        authorization:
          "Bearer " +
          delivery.authorizationToken,
        range: `bytes=${offset}-${end}`,
      },
    });

    if (response.status !== 206) {
      throw new Error(
        "Authorized ranged package download failed for " +
          descriptor.packageId +
          ": HTTP " +
          response.status,
      );
    }

    const expectedContentRange =
      `bytes ${offset}-${end}/${descriptor.byteCount}`;
    if (
      response.headers.get("content-range") !==
        expectedContentRange
    ) {
      throw new Error(
        "Protected range response mismatch for " +
          descriptor.packageId +
          ": expected " +
          expectedContentRange +
          ", got " +
          response.headers.get("content-range"),
      );
    }

    const chunk =
      Buffer.from(
        await response.arrayBuffer(),
      );
    const expectedLength =
      end - offset + 1;
    if (chunk.length !== expectedLength) {
      throw new Error(
        "Protected range byte-count mismatch for " +
          descriptor.packageId,
      );
    }

    const returnedPackageId =
      response.headers.get(
        "x-rrgh-package-id",
      );
    const returnedVersion =
      response.headers.get(
        "x-rrgh-package-version",
      );
    if (
      returnedPackageId !==
        descriptor.packageId ||
      returnedVersion !==
        descriptor.version
    ) {
      throw new Error(
        "Protected range identity header mismatch for " +
          descriptor.packageId,
      );
    }

    packageIdHeader = returnedPackageId;
    versionHeader = returnedVersion;
    chunks.push(chunk);
    offset = end + 1;
  }

  return {
    bytes: Buffer.concat(chunks),
    packageIdHeader,
    versionHeader,
  };
}

async function readJson(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    throw new Error("Expected JSON from " + response.url + "; got HTTP " + response.status);
  }
}

async function callApi(operation, idToken, extra = {}) {
  const headers = { "content-type": "application/json" };
  if (idToken) headers.authorization = "Bearer " + idToken;

  const response = await fetch(functionUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ data: { operation, ...extra } }),
  });
  const body = await readJson(response);
  return {
    response,
    body,
    result: body.result ?? null,
  };
}

async function deleteCollectionDocs(querySnapshot) {
  if (querySnapshot.empty) return;
  const batch = db.batch();
  for (const doc of querySnapshot.docs) batch.delete(doc.ref);
  await batch.commit();
}

async function resetSmokeAccount() {
  const account = db.collection("accounts").doc(smokeUid);
  await deleteCollectionDocs(await account.collection("entitlements").get());
  await deleteCollectionDocs(await account.collection("purchaseEvidence").get());
  await deleteCollectionDocs(
    await db.collection("packageCapabilities").where("uid", "==", smokeUid).get(),
  );
  await account.delete().catch(() => {});
  await db.collection("accountDeletionRequests").doc(smokeUid).delete().catch(() => {});
}

async function assertPackageDownload(idToken, packageId) {
  const authorization = await callApi(
    "authorizeProtectedPackage",
    idToken,
    { packageId },
  );
  if (
    !authorization.response.ok ||
    authorization.result?.authorized !== true ||
    authorization.result?.delivery?.ready !== true
  ) {
    throw new Error(
      "Package authorization failed for " +
        packageId +
        ": " +
        JSON.stringify(authorization.body),
    );
  }

  const descriptor = authorization.result.package;
  const delivery = authorization.result.delivery;
  if (
    descriptor.packageId !== packageId ||
    !descriptor.version ||
    !/^[0-9a-f]{64}$/.test(descriptor.sha256 ?? "") ||
    !Number.isSafeInteger(descriptor.byteCount) ||
    descriptor.byteCount <= 0 ||
    delivery.method !== "capability_https" ||
    delivery.httpMethod !== "GET" ||
    delivery.authorizationScheme !== "Bearer" ||
    typeof delivery.authorizationToken !== "string" ||
    delivery.authorizationToken.length < 32 ||
    typeof delivery.expiresAt !== "string"
  ) {
    throw new Error("Invalid protected package contract for " + packageId);
  }

  const noCapability = await fetch(delivery.url);
  if (noCapability.status !== 401) {
    throw new Error(
      "Download endpoint must deny requests without a capability; got HTTP " +
        noCapability.status,
    );
  }

  const download =
    await fetchPackageBytesInRanges(
      delivery,
      descriptor,
    );
  const bytes = download.bytes;

  if (bytes.length !== descriptor.byteCount) {
    throw new Error(
      "Downloaded byte-count mismatch for " +
        packageId,
    );
  }
  if (sha256(bytes) !== descriptor.sha256) {
    throw new Error(
      "Downloaded SHA-256 mismatch for " +
        packageId,
    );
  }

  if (
    download.packageIdHeader !== packageId
  ) {
    throw new Error(
      "Downloaded package ID header mismatch for " +
        packageId,
    );
  }
  if (
    download.versionHeader !==
      descriptor.version
  ) {
    throw new Error(
      "Downloaded package version header mismatch for " +
        packageId,
    );
  }

  return authorization.result;
}

requireValue("RRGH_FUNCTION_URL", functionUrl);
requireValue("FIREBASE_API_KEY", apiKey);
requireValue("RRGH_DEPLOY_SERVICE_ACCOUNT", serviceAccountId);

const unauthenticated = await callApi("getAccountState", null);
if (
  unauthenticated.response.status !== 401 ||
  unauthenticated.body?.error?.status !== "UNAUTHENTICATED"
) {
  throw new Error(
    "Unauthenticated callable check failed: HTTP " +
      unauthenticated.response.status +
      " / " +
      JSON.stringify(unauthenticated.body),
  );
}
console.log("Remote unauthenticated denial: PASS");

const app = initializeApp({
  credential: applicationDefault(),
  projectId,
  serviceAccountId,
});
const db = getFirestore(app);
await resetSmokeAccount();

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

const initial = await callApi("getAccountState", idToken);
if (!initial.response.ok || initial.result?.uid !== smokeUid) {
  throw new Error(
    "Authenticated callable check failed: " + JSON.stringify(initial.body),
  );
}
console.log("Remote authenticated callable: PASS");

const unknown = await callApi(
  "authorizeProtectedPackage",
  idToken,
  { packageId: "not-a-real-rrgh-package" },
);
if (
  unknown.result?.authorized !== false ||
  unknown.result?.reason !== "package_not_found" ||
  unknown.result?.delivery !== null
) {
  throw new Error("Unknown package fail-closed check failed.");
}
console.log("Remote unknown package denial: PASS");

const trial = await callApi("startBaseTrial", idToken);
if (
  !trial.response.ok ||
  trial.result?.trial?.started !== true ||
  trial.result?.account?.access?.base !== true ||
  trial.result?.account?.access?.day_hikes !== true ||
  trial.result?.account?.access?.backpacking !== false ||
  trial.result?.account?.access?.off_trail !== false
) {
  throw new Error("Remote Base trial contract check failed.");
}
console.log("Remote Base-trial access contract: PASS");

const skybridge = await assertPackageDownload(
  idToken,
  "route-rte-0001",
);
console.log(
  "Remote exact route bytes: PASS / route-rte-0001 / " +
    skybridge.package.version +
    " / " +
    skybridge.package.byteCount +
    " bytes",
);

const princess = await assertPackageDownload(
  idToken,
  "route-rte-0002",
);
console.log(
  "Remote exact route bytes: PASS / route-rte-0002 / " +
    princess.package.version +
    " / " +
    princess.package.byteCount +
    " bytes",
);

const gorgeBase = await assertPackageDownload(
  idToken,
  "gorge-base",
);
if (
  gorgeBase.package.packageType !== "offline_base" ||
  gorgeBase.package.offlineManifest?.packageID !== "gorge-base" ||
  gorgeBase.package.offlineManifest?.version !== gorgeBase.package.version ||
  gorgeBase.package.offlineManifest?.byteCount !== gorgeBase.package.byteCount ||
  gorgeBase.package.offlineManifest?.sha256 !== gorgeBase.package.sha256 ||
  !Array.isArray(gorgeBase.package.offlineManifest?.sources) ||
  gorgeBase.package.offlineManifest.sources.length < 1
) {
  throw new Error("Remote Gorge Base manifest contract check failed.");
}
console.log(
  "Remote Gorge Base bytes + manifest: PASS / " +
    gorgeBase.package.version +
    " / " +
    gorgeBase.package.byteCount +
    " bytes",
);

const expiring = await callApi(
  "authorizeProtectedPackage",
  idToken,
  { packageId: "route-rte-0001" },
);
const expiringToken = expiring.result?.delivery?.authorizationToken;
if (!expiringToken) throw new Error("Missing capability for expiry test.");
await db
  .collection("packageCapabilities")
  .doc(capabilityHash(expiringToken))
  .update({
    expiresAt: Timestamp.fromMillis(Date.now() - 1_000),
  });
const expiredResponse = await fetch(expiring.result.delivery.url, {
  headers: { authorization: "Bearer " + expiringToken },
});
const expiredBody = await readJson(expiredResponse);
if (
  expiredResponse.status !== 410 ||
  expiredBody?.error?.reason !== "delivery_capability_expired"
) {
  throw new Error("Expired package capability check failed.");
}
console.log("Remote expired capability denial: PASS");

const deletion = await callApi("initiateAccountDeletion", idToken);
if (
  deletion.result?.deletion?.state !== "pending" ||
  deletion.result?.account?.accountStatus !== "deletion_pending"
) {
  throw new Error("Remote account-deletion state check failed.");
}
const afterDeletion = await callApi(
  "authorizeProtectedPackage",
  idToken,
  { packageId: "route-rte-0001" },
);
if (
  afterDeletion.result?.authorized !== false ||
  afterDeletion.result?.reason !== "account_not_active" ||
  afterDeletion.result?.delivery !== null
) {
  throw new Error("Deletion-pending package denial failed.");
}
console.log("Remote deletion-pending package denial: PASS");

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

await resetSmokeAccount();
console.log("RRGH non-production protected delivery smoke: PASS");
