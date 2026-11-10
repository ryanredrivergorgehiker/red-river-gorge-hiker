import { activeCatalog, requireValue, same } from './rrgh-final-catalog-contract.mjs';

function releaseRef(db, id) {
  requireValue(/^[a-f0-9]{16}-[1-9][0-9]*$/.test(id), 'Invalid final map release identity');
  return db.collection('mapPackageReleases').doc(id);
}

export async function claimDeliveryAllowance(db, meta, timestamp) {
  const ref = db.collection('mapPackageReleaseRequests').doc(meta.requestSHA256);
  requireValue(/^[a-f0-9]{64}$/.test(meta.requestSHA256), 'Invalid reserved delivery request');
  return db.runTransaction(async tx => {
    const current = await tx.get(ref);
    requireValue(!current.exists, 'This final delivery allowance has already been consumed');
    tx.create(ref, { requestSHA256: meta.requestSHA256, releaseId: meta.releaseId,
      runID: meta.runID, reservedAt: timestamp, reservedUSD: '0.75', refundable: false });
    return { allowanceClaimed: true };
  }, { maxAttempts: 1 });
}

export async function verifyDeliveryClaim(db, meta) {
  const value = (await db.collection('mapPackageReleaseRequests').doc(meta.requestSHA256).get()).data();
  requireValue(value?.requestSHA256 === meta.requestSHA256 && value.releaseId === meta.releaseId &&
    value.runID === meta.runID && value.reservedUSD === '0.75' && value.refundable === false,
    'Final delivery allowance belongs to another attempt');
}

export async function activateCatalogs(db, document, meta, timestamp) {
  const release = releaseRef(db, meta.releaseId), rows = document.catalogs;
  requireValue(rows.length >= 6 && rows.length <= 195, 'Bounded complete catalog transaction required');
  const refs = rows.map(c => db.collection('packageCatalog').doc(c.packageId));
  return db.runTransaction(async tx => {
    const originalRelease = await tx.get(release);
    requireValue(!originalRelease.exists, 'A release attempt cannot be replayed');
    const prior = await tx.getAll(...refs);
    const estimatedBytes = rows.reduce((n, row, i) => n +
      2 * Buffer.byteLength(JSON.stringify(row)) + Buffer.byteLength(JSON.stringify(prior[i].data() ?? null)) + 8192, 0);
    requireValue(estimatedBytes <= 8 * 1024 * 1024, 'Atomic catalog request exceeds conservative Firestore size bound');
    const previousIds = [...new Set(prior.map(s => s.data()?.rrghFinalMapRelease).filter(Boolean))];
    for (const id of previousIds) {
      const previous = await tx.get(releaseRef(db, id));
      requireValue(previous.exists && previous.data().status === 'verified', 'An earlier unverified catalog release must be resolved first');
    }
    const identities = rows.map(c => ({ packageId: c.packageId, version: c.version, sha256: c.sha256 }));
    tx.create(release, { format: 'rrgh-final-map-release-v1', status: 'validating',
      requestSHA256: meta.requestSHA256, authoritySHA256: document.authoritySHA256,
      catalogCandidates: meta.catalogCandidates, verifiedCheckpoint: meta.verifiedCheckpoint,
      runID: meta.runID, identities, createdAt: timestamp,
      finalPackageDeliveryComplete: false, physicalIPhoneTestComplete: false });
    for (let i = 0; i < rows.length; i++) {
      // Firestore retains native timestamps in the backups; JSON conversion
      // would silently change the old catalog's value types during rollback.
      const published = { ...activeCatalog(rows[i], meta.releaseId), updatedAt: timestamp };
      tx.create(release.collection('previousDocs').doc(rows[i].packageId), {
        packageId: rows[i].packageId, requestSHA256: meta.requestSHA256,
        existed: prior[i].exists, data: prior[i].exists ? prior[i].data() : null, published });
      tx.set(refs[i], published);
    }
    return { activated: rows.length, releaseId: meta.releaseId, priorCatalogsRetained: true,
      finalPackageDeliveryComplete: false };
  }, { maxAttempts: 1 });
}

export async function rollbackCatalogs(db, meta, timestamp) {
  const release = releaseRef(db, meta.releaseId);
  return db.runTransaction(async tx => {
    const snapshot = await tx.get(release);
    if (!snapshot.exists) return { rollbackNeeded: false, reason: 'No catalog activation committed' };
    const saved = snapshot.data();
    requireValue(saved.format === 'rrgh-final-map-release-v1' && saved.requestSHA256 === meta.requestSHA256 &&
      saved.runID === meta.runID, 'Rollback cannot modify another release');
    if (saved.status === 'rolled-back') return { rollbackNeeded: false, reason: 'Original catalog already restored' };
    requireValue(saved.status === 'validating', 'A successfully verified release cannot be rolled back by a failed older job');
    const refs = saved.identities.map(c => db.collection('packageCatalog').doc(c.packageId));
    const backups = saved.identities.map(c => release.collection('previousDocs').doc(c.packageId));
    const current = await tx.getAll(...refs), previous = await tx.getAll(...backups);
    for (let i = 0; i < refs.length; i++) {
      const c = current[i].data(), b = previous[i].data(), expected = saved.identities[i];
      requireValue(current[i].exists && c.rrghFinalMapRelease === meta.releaseId &&
        c.version === expected.version && c.sha256 === expected.sha256 && previous[i].exists &&
        b.packageId === expected.packageId && b.requestSHA256 === meta.requestSHA256 && same(c, b.published) &&
        typeof b.existed === 'boolean', 'A competing catalog owner or missing backup prevents rollback');
    }
    for (let i = 0; i < refs.length; i++) {
      const b = previous[i].data();
      if (b.existed) tx.set(refs[i], b.data); else tx.delete(refs[i]);
    }
    tx.update(release, { status: 'rolled-back', rolledBackAt: timestamp,
      finalPackageDeliveryComplete: false, physicalIPhoneTestComplete: false });
    return { rolledBack: refs.length, releaseId: meta.releaseId, originalCatalogRestored: true };
  }, { maxAttempts: 1 });
}

export async function markDeliveryVerified(db, meta, report, timestamp) {
  const release = releaseRef(db, meta.releaseId);
  return db.runTransaction(async tx => {
    const snapshot = await tx.get(release), value = snapshot.data();
    requireValue(snapshot.exists && value.status === 'validating' && value.requestSHA256 === meta.requestSHA256 &&
      value.runID === meta.runID && report.requestSHA256 === meta.requestSHA256 &&
      report.authoritySHA256 === value.authoritySHA256 && report.authenticatedIndexes === 3 &&
      report.authenticatedPackages === value.identities.length && report.fullyHashedSampleParts === 3 &&
      report.everyPackageIdentityAndRangeVerified === true && report.offlineLeaseVerified === true &&
      report.currentStorageGenerationsVerified === true &&
      report.unauthenticatedDeliveryDenied === true && report.physicalIPhoneTestComplete === false,
      'Authenticated delivery validation is incomplete');
    const refs = value.identities.map(c => db.collection('packageCatalog').doc(c.packageId));
    const current = await tx.getAll(...refs);
    const backups = await tx.getAll(...value.identities.map(c => release.collection('previousDocs').doc(c.packageId)));
    for (let i = 0; i < refs.length; i++) {
      const c = current[i].data(), expected = value.identities[i];
      requireValue(current[i].exists && c.rrghFinalMapRelease === meta.releaseId && c.active === true &&
        c.deliveryState === 'ready' && c.version === expected.version && c.sha256 === expected.sha256 &&
        backups[i].exists && same(c, backups[i].data().published),
        'Catalog moved during independent authenticated verification');
    }
    tx.update(release, { status: 'verified', verifiedAt: timestamp, verification: report,
      finalPackageDeliveryComplete: true, physicalIPhoneTestComplete: false });
    return { releaseId: meta.releaseId, finalPackageDeliveryComplete: true, physicalIPhoneTestComplete: false };
  }, { maxAttempts: 1 });
}
