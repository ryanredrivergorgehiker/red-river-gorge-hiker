import fs from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";

const requireFromFunctions = createRequire(
  new URL("../functions/package.json", import.meta.url),
);
const { applicationDefault, initializeApp } = requireFromFunctions("firebase-admin/app");
const { getFirestore, FieldValue } = requireFromFunctions("firebase-admin/firestore");

const projectId = process.env.GCLOUD_PROJECT || "rrgh-nonproduction";
const bucket = process.env.RRGH_PACKAGE_BUCKET;
const routeDir = process.env.RRGH_ROUTE_PACKAGE_DIR;
const basePackagePath = process.env.RRGH_BASE_PACKAGE_PATH;
const baseManifestPath = process.env.RRGH_BASE_MANIFEST_PATH;

function required(name, value) {
  if (!value) throw new Error(`Missing required environment value: ${name}`);
  return value;
}

required("RRGH_PACKAGE_BUCKET", bucket);
required("RRGH_ROUTE_PACKAGE_DIR", routeDir);
required("RRGH_BASE_PACKAGE_PATH", basePackagePath);
required("RRGH_BASE_MANIFEST_PATH", baseManifestPath);

function digest(path) {
  return createHash("sha256").update(fs.readFileSync(path)).digest("hex");
}

function size(path) {
  return fs.statSync(path).size;
}

function assertExactFile(path, expectedSha, expectedBytes) {
  const actualSha = digest(path);
  const actualBytes = size(path);
  if (actualSha !== expectedSha) {
    throw new Error(`SHA-256 mismatch for ${path}: ${actualSha}`);
  }
  if (actualBytes !== expectedBytes) {
    throw new Error(`Byte-count mismatch for ${path}: ${actualBytes}`);
  }
}

function validateOfflineManifest(manifest) {
  const fields = ["packageID", "version", "sha256"];
  for (const field of fields) {
    if (typeof manifest[field] !== "string" || manifest[field].length === 0) {
      throw new Error(`Offline manifest missing ${field}`);
    }
  }
  if (!Number.isSafeInteger(manifest.byteCount) || manifest.byteCount <= 0) {
    throw new Error("Offline manifest byteCount must be a positive integer.");
  }
  if (!Array.isArray(manifest.sources) || manifest.sources.length === 0) {
    throw new Error("Offline manifest requires at least one source record.");
  }

  const sourceFields = [
    "sourceID",
    "sourceURL",
    "provider",
    "vintageOrRetrievedAt",
    "areaOfInterestOrSourceObjects",
    "processingMethod",
    "rightsBasis",
    "attributionOrDisclaimer",
    "outputVersion",
    "integritySHA256",
  ];
  for (const source of manifest.sources) {
    for (const field of sourceFields) {
      if (typeof source[field] !== "string" || source[field].trim().length === 0) {
        throw new Error(`Offline source ${source.sourceID ?? "unknown"} missing ${field}`);
      }
    }
    if (!/^[0-9a-f]{64}$/.test(source.integritySHA256)) {
      throw new Error(`Offline source ${source.sourceID} has invalid integrity SHA-256.`);
    }
  }
}

const routePackages = [
  {
    packageId: "route-rte-0001",
    routeId: "RTE-0001",
    version: "1",
    requiredEntitlement: "base",
    path: `${routeDir}/route-rte-0001.geojson`,
    sha256: "123fdb57e1142299f86c714367cc466b70f18fa90cfbaabb92b0d9ced157dc66",
    byteCount: 8201,
    objectName: "packages/routes/route-rte-0001/1/route.geojson",
  },
  {
    packageId: "route-rte-0002",
    routeId: "RTE-0002",
    version: "1",
    requiredEntitlement: "base",
    path: `${routeDir}/route-rte-0002.geojson`,
    sha256: "ced314bb34392750b0f823c9a11bc95a48e6fa52c59830d4ee83619f615d6602",
    byteCount: 6533,
    objectName: "packages/routes/route-rte-0002/1/route.geojson",
  },
];

for (const route of routePackages) {
  assertExactFile(route.path, route.sha256, route.byteCount);
}

const baseManifest = JSON.parse(fs.readFileSync(baseManifestPath, "utf8"));
validateOfflineManifest(baseManifest);
if (baseManifest.packageID !== "gorge-base") {
  throw new Error("Unexpected Gorge Base packageID.");
}
if (baseManifest.version !== "2026.10.06.1") {
  throw new Error("Unexpected Gorge Base package version.");
}
assertExactFile(
  basePackagePath,
  baseManifest.sha256,
  baseManifest.byteCount,
);

const app = initializeApp({
  credential: applicationDefault(),
  projectId,
});
const db = getFirestore(app);

const baseObjectName =
  `packages/offline/gorge-base/${baseManifest.version}/gorge-base.rrghpkg`;

const writes = [
  ...routePackages.map((route) => ({
    id: route.packageId,
    data: {
      active: true,
      lifecycle: "active",
      deliveryState: "ready",
      packageType: "route_geojson",
      routeId: route.routeId,
      version: route.version,
      sha256: route.sha256,
      byteCount: route.byteCount,
      requiredEntitlement: route.requiredEntitlement,
      storageBucket: bucket,
      objectName: route.objectName,
      contentType: "application/geo+json",
      offlineManifest: null,
      policyVersion: 2,
      updatedAt: FieldValue.serverTimestamp(),
    },
  })),
  {
    id: "gorge-base",
    data: {
      active: true,
      lifecycle: "active",
      deliveryState: "ready",
      packageType: "offline_base",
      version: baseManifest.version,
      sha256: baseManifest.sha256,
      byteCount: baseManifest.byteCount,
      requiredEntitlement: "base",
      storageBucket: bucket,
      objectName: baseObjectName,
      contentType: "application/octet-stream",
      offlineManifest: baseManifest,
      policyVersion: 2,
      updatedAt: FieldValue.serverTimestamp(),
    },
  },
];

const batch = db.batch();
for (const entry of writes) {
  batch.set(
    db.collection("packageCatalog").doc(entry.id),
    entry.data,
    { merge: true },
  );
}
await batch.commit();

for (const entry of writes) {
  const snapshot = await db.collection("packageCatalog").doc(entry.id).get();
  if (!snapshot.exists || snapshot.data()?.deliveryState !== "ready") {
    throw new Error(`Package catalog verification failed for ${entry.id}`);
  }
  console.log(
    `Catalog ready: ${entry.id} / ${snapshot.data().version} / ${snapshot.data().byteCount} bytes / ${snapshot.data().sha256}`,
  );
}

console.log("Protected/offline package catalog seeding: PASS");
