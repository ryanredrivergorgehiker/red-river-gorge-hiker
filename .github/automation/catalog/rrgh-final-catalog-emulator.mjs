import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { fixture } from './rrgh-final-catalog-fixture.mjs';
import { claimDeliveryAllowance, verifyDeliveryClaim, activateCatalogs, rollbackCatalogs,
  markDeliveryVerified } from './rrgh-final-catalog-publish.mjs';

assert.equal(process.env.FIRESTORE_EMULATOR_HOST, '127.0.0.1:8080', 'Local emulator only');
const requireBackend = createRequire(pathToFileURL(process.cwd() + '/backend/functions/package.json'));
const { initializeApp, deleteApp } = requireBackend('firebase-admin/app');
const { getFirestore, Timestamp } = requireBackend('firebase-admin/firestore');
const app = initializeApp({ projectId: 'demo-rrgh-final-map' }), db = getFirestore(app);
try {
  const f = fixture(), original = { active: true, version: 'original', updatedAt: Timestamp.fromMillis(1234567890), nested: { retain: [1, 'two'] } };
  const core = db.collection('packageCatalog').doc('gorge-core');await core.set(original);
  await db.collection('packageCatalog').doc('gorge-base').set({ untouched: true });
  const meta = { releaseId: 'a'.repeat(16) + '-123', runID: 123, requestSHA256: f.request.requestSHA256,
    catalogCandidates: f.request.catalogCandidates, verifiedCheckpoint: f.request.verifiedCheckpoint };
  await claimDeliveryAllowance(db, meta, Timestamp.now());await verifyDeliveryClaim(db, meta);
  await assert.rejects(claimDeliveryAllowance(db, meta, Timestamp.now()));
  await activateCatalogs(db, f.document, meta, Timestamp.now());
  assert.equal((await core.get()).data().rrghFinalMapRelease, meta.releaseId);
  await rollbackCatalogs(db, meta, Timestamp.now());
  assert.deepEqual((await core.get()).data(), original);
  assert.equal((await db.collection('packageCatalog').doc(f.document.catalogs[0].packageId).get()).exists, false);
  assert.deepEqual((await db.collection('packageCatalog').doc('gorge-base').get()).data(), { untouched: true });
  const newer = { ...meta, runID: 124, releaseId: 'a'.repeat(16) + '-124', requestSHA256: 'c'.repeat(64) };
  await claimDeliveryAllowance(db, newer, Timestamp.now());
  await activateCatalogs(db, f.document, newer, Timestamp.now());
  await core.update({ unrelatedConcurrentField: true });
  await assert.rejects(rollbackCatalogs(db, newer, Timestamp.now()));
  assert.equal((await core.get()).data().unrelatedConcurrentField, true);
  const backup = await db.collection('mapPackageReleases').doc(newer.releaseId).collection('previousDocs').doc('gorge-core').get();
  await core.set(backup.data().published);
  const report = { requestSHA256: newer.requestSHA256, authoritySHA256: f.request.authoritySHA256,
    authenticatedIndexes: 3, authenticatedPackages: f.document.catalogs.length, fullyHashedSampleParts: 3,
    everyPackageIdentityAndRangeVerified: true, offlineLeaseVerified: true,
    currentStorageGenerationsVerified: true, requiredDayHikesVerified: true,
    authenticatedDayHikes: ['RTE-0001', 'RTE-0002'].map(routeID => ({ routeID,
      packageID: 'route-' + routeID.toLowerCase(), version: '1', sha256: 'a'.repeat(64), byteCount: 100 })),
    unauthenticatedDeliveryDenied: true, physicalIPhoneTestComplete: false };
  assert.equal((await markDeliveryVerified(db, newer, report, Timestamp.now())).finalPackageDeliveryComplete, true);
  await assert.rejects(rollbackCatalogs(db, newer, Timestamp.now()));
  console.log('Local Firestore SDK transaction, exact timestamp rollback, competing writes and final acceptance: PASS');
} finally { await deleteApp(app); }
