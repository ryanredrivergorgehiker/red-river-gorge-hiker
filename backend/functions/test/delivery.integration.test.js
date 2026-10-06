import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { initializeApp, getApps } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import { getStorage } from "firebase-admin/storage";
import {
  createProtectedPackageDelivery,
  hashCapabilityToken,
} from "../src/delivery.js";
import { authorizeProtectedPackageForUid } from "../src/store.js";

const projectId = "demo-rrgh-entitlements";
const bucketName = "demo-rrgh-entitlements.appspot.com";
const downloadUrl =
  "http://127.0.0.1:5001/demo-rrgh-entitlements/us-east5/rrghPackageDownload";

if (
  !process.env.FIRESTORE_EMULATOR_HOST ||
  !process.env.FIREBASE_STORAGE_EMULATOR_HOST
) {
  throw new Error("Delivery tests require Firestore and Storage emulators.");
}

if (getApps().length === 0) {
  initializeApp({ projectId, storageBucket: bucketName });
}

const db = getFirestore();
const storage = getStorage();

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

async function seedObjectAndCatalog({
  packageId,
  requiredEntitlement,
  payload,
  packageType = "route_geojson",
  offlineManifest = null,
}) {
  const version = "test-v1";
  const objectName = `synthetic/${packageId}/${version}/payload.bin`;
  const digest = sha256(payload);

  await storage.bucket(bucketName).file(objectName).save(payload, {
    resumable: false,
    metadata: {
      contentType: "application/octet-stream",
      metadata: {
        "rrgh-sha256": digest,
        "rrgh-package-id": packageId,
        "rrgh-version": version,
      },
    },
  });

  await db.collection("packageCatalog").doc(packageId).set({
    active: true,
    lifecycle: "active",
    deliveryState: "ready",
    packageType,
    version,
    sha256: digest,
    byteCount: payload.length,
    requiredEntitlement,
    storageBucket: bucketName,
    objectName,
    contentType: "application/octet-stream",
    offlineManifest,
    policyVersion: 1,
  });

  return { version, objectName, digest };
}

async function authorize(uid, packageId) {
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

test("Base trial can retrieve exact protected bytes with five-minute capability", async () => {
  const uid = "delivery-base-trial";
  const now = Timestamp.now();
  const payload = Buffer.from(
    JSON.stringify({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            routeId: "TEST-RTE-001",
            title: "Synthetic Test Route",
            version: "test-v1",
          },
          geometry: {
            type: "LineString",
            coordinates: [
              [-83.0, 37.0],
              [-83.001, 37.001],
            ],
          },
        },
      ],
    }),
    "utf8",
  );

  await db.collection("accounts").doc(uid).set({
    status: "active",
    createdAt: now,
    policyVersion: 1,
    trial: {
      base: {
        consumed: true,
        startedAt: now,
        endsAt: Timestamp.fromMillis(now.toMillis() + 60_000),
      },
    },
  });

  const seeded = await seedObjectAndCatalog({
    packageId: "synthetic-route-base",
    requiredEntitlement: "base",
    payload,
  });

  const auth = await authorize(uid, "synthetic-route-base");
  assert.equal(auth.authorized, true);
  assert.equal(auth.package.packageId, "synthetic-route-base");
  assert.equal(auth.package.version, seeded.version);
  assert.equal(auth.package.sha256, seeded.digest);
  assert.equal(auth.package.byteCount, payload.length);
  assert.equal(auth.delivery.ready, true);
  assert.equal(auth.delivery.method, "capability_https");
  assert.equal(auth.delivery.httpMethod, "GET");
  assert.equal(auth.delivery.url, downloadUrl);
  assert.equal(auth.delivery.authorizationScheme, "Bearer");
  assert.ok(auth.delivery.authorizationToken.length >= 32);

  const response = await fetch(auth.delivery.url, {
    headers: {
      authorization: `Bearer ${auth.delivery.authorizationToken}`,
    },
  });
  assert.equal(response.status, 200);

  const downloaded = Buffer.from(await response.arrayBuffer());
  assert.deepEqual(downloaded, payload);
  assert.equal(downloaded.length, payload.length);
  assert.equal(sha256(downloaded), seeded.digest);
  assert.equal(
    response.headers.get("x-rrgh-package-id"),
    "synthetic-route-base",
  );
  assert.equal(
    response.headers.get("x-rrgh-package-version"),
    seeded.version,
  );
});

test("authorization fails closed for unavailable and ineligible package states", async () => {
  const uid = "delivery-fail-closed";
  const now = Timestamp.now();
  await db.collection("accounts").doc(uid).set({
    status: "active",
    createdAt: now,
    policyVersion: 1,
  });

  const unknown = await authorize(uid, "synthetic-unknown");
  assert.equal(unknown.authorized, false);
  assert.equal(unknown.reason, "package_not_found");
  assert.equal(unknown.delivery, null);

  await db.collection("packageCatalog").doc("synthetic-not-ready").set({
    active: true,
    lifecycle: "active",
    deliveryState: "building",
    packageType: "offline_base",
    version: "test-v1",
    sha256: "test-only",
    byteCount: 1,
    requiredEntitlement: "base",
  });

  const denied = await authorize(uid, "synthetic-not-ready");
  assert.equal(denied.authorized, false);
  assert.equal(denied.reason, "not_entitled");

  await db.collection("accounts").doc(uid).set({
    trial: {
      base: {
        consumed: true,
        startedAt: now,
        endsAt: Timestamp.fromMillis(now.toMillis() + 60_000),
      },
    },
  }, { merge: true });

  const notReady = await authorize(uid, "synthetic-not-ready");
  assert.equal(notReady.authorized, true);
  assert.equal(notReady.delivery.ready, false);
  assert.equal(notReady.delivery.reason, "package_not_ready");
  assert.equal(notReady.delivery.authorizationToken, null);

  await db.collection("packageCatalog").doc("synthetic-superseded").set({
    active: false,
    lifecycle: "superseded",
    deliveryState: "not_ready",
    packageType: "route_geojson",
    version: "old",
    sha256: "old",
    byteCount: 1,
    requiredEntitlement: "base",
  });

  const superseded = await authorize(uid, "synthetic-superseded");
  assert.equal(superseded.authorized, false);
  assert.equal(superseded.reason, "package_superseded");
});

test("paid extensions require permanent Base and deletion-pending denies capabilities", async () => {
  const uid = "delivery-extension-gates";
  const payload = Buffer.from("synthetic extension bytes", "utf8");

  await db.collection("accounts").doc(uid).set({
    status: "active",
    createdAt: Timestamp.now(),
    policyVersion: 1,
    trial: {
      base: {
        consumed: true,
        startedAt: Timestamp.fromMillis(Date.now() - 1_000),
        endsAt: Timestamp.fromMillis(Date.now() + 60_000),
      },
    },
  });
  await db.collection("accounts").doc(uid)
    .collection("entitlements").doc("backpacking").set({ state: "active" });
  await db.collection("accounts").doc(uid)
    .collection("entitlements").doc("off_trail").set({ state: "active" });

  await seedObjectAndCatalog({
    packageId: "synthetic-backpacking",
    requiredEntitlement: "backpacking",
    payload,
  });
  await seedObjectAndCatalog({
    packageId: "synthetic-off-trail",
    requiredEntitlement: "off_trail",
    payload,
  });

  const bpTrialOnly = await authorize(uid, "synthetic-backpacking");
  const otTrialOnly = await authorize(uid, "synthetic-off-trail");
  assert.equal(bpTrialOnly.authorized, false);
  assert.equal(bpTrialOnly.reason, "not_entitled");
  assert.equal(otTrialOnly.authorized, false);
  assert.equal(otTrialOnly.reason, "not_entitled");

  await db.collection("accounts").doc(uid)
    .collection("entitlements").doc("base").set({ state: "active" });

  const bpPermanentBase = await authorize(uid, "synthetic-backpacking");
  const otPermanentBase = await authorize(uid, "synthetic-off-trail");
  assert.equal(bpPermanentBase.authorized, true);
  assert.equal(bpPermanentBase.delivery.ready, true);
  assert.equal(otPermanentBase.authorized, true);
  assert.equal(otPermanentBase.delivery.ready, true);

  await db.collection("accounts").doc(uid).set(
    { status: "deletion_pending" },
    { merge: true },
  );
  const afterDeletion = await authorize(uid, "synthetic-backpacking");
  assert.equal(afterDeletion.authorized, false);
  assert.equal(afterDeletion.reason, "account_not_active");
  assert.equal(afterDeletion.delivery, null);
});

test("expired capability cannot remain an indefinite download path", async () => {
  const uid = "delivery-expiry";
  const payload = Buffer.from("synthetic expiring bytes", "utf8");
  await db.collection("accounts").doc(uid).set({
    status: "active",
    createdAt: Timestamp.now(),
    policyVersion: 1,
  });
  await db.collection("accounts").doc(uid)
    .collection("entitlements").doc("base").set({ state: "active" });

  await seedObjectAndCatalog({
    packageId: "synthetic-expiry",
    requiredEntitlement: "base",
    payload,
  });

  const auth = await authorize(uid, "synthetic-expiry");
  assert.equal(auth.delivery.ready, true);

  const token = auth.delivery.authorizationToken;
  await db.collection("packageCapabilities")
    .doc(hashCapabilityToken(token))
    .update({
      expiresAt: Timestamp.fromMillis(Date.now() - 1_000),
    });

  const response = await fetch(auth.delivery.url, {
    headers: { authorization: `Bearer ${token}` },
  });
  assert.equal(response.status, 410);
  const body = await response.json();
  assert.equal(body.error.reason, "delivery_capability_expired");
});

test("offline Base descriptor carries exact iOS manifest shape", async () => {
  const uid = "delivery-offline-manifest";
  const payload = Buffer.from("synthetic base archive", "utf8");
  const sourceBytes = Buffer.from("synthetic source bytes", "utf8");
  const manifest = {
    packageID: "synthetic-gorge-base",
    version: "test-v1",
    byteCount: payload.length,
    sha256: sha256(payload),
    sources: [
      {
        sourceID: "synthetic-source",
        sourceURL: "https://example.test/synthetic-source",
        provider: "Synthetic Test Fixture",
        vintageOrRetrievedAt: "2026-10-06T00:00:00Z",
        areaOfInterestOrSourceObjects: "Synthetic test-only AOI",
        processingMethod: "Synthetic fixture; not RRGH route/source data.",
        rightsBasis: "Test fixture only",
        attributionOrDisclaimer: "Synthetic test fixture only",
        outputVersion: "test-v1",
        integritySHA256: sha256(sourceBytes),
      },
    ],
  };

  await db.collection("accounts").doc(uid).set({
    status: "active",
    createdAt: Timestamp.now(),
    policyVersion: 1,
  });
  await db.collection("accounts").doc(uid)
    .collection("entitlements").doc("base").set({ state: "active" });

  await seedObjectAndCatalog({
    packageId: "synthetic-gorge-base",
    requiredEntitlement: "base",
    payload,
    packageType: "offline_base",
    offlineManifest: manifest,
  });

  const auth = await authorize(uid, "synthetic-gorge-base");
  assert.equal(auth.authorized, true);
  assert.equal(auth.package.packageType, "offline_base");
  assert.deepEqual(auth.package.offlineManifest, manifest);
});
