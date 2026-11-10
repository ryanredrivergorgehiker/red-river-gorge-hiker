import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './rrgh-final-catalog-fixture.mjs';
import { activateCatalogs, rollbackCatalogs, markDeliveryVerified, claimDeliveryAllowance, verifyDeliveryClaim } from './rrgh-final-catalog-publish.mjs';

class MemoryFirestore {
  constructor() { this.values = new Map();this.failCommit = false; }
  collection(name) {
    const doc = path => ({ path, get: async () => ({ exists: this.values.has(path), data: () => this.values.get(path) }),
      collection: suffix => ({ doc: name => doc(path + '/' + suffix + '/' + name) }) });
    return { doc: id => doc(name + '/' + id) };
  }
  async runTransaction(fn, options) {
    assert.equal(options.maxAttempts, 1);
    const draft = new Map(structuredClone([...this.values])), get = async ref => ({ exists: draft.has(ref.path), data: () => draft.get(ref.path) });
    const tx = { get, getAll: (...refs) => Promise.all(refs.map(get)),
      create: (ref, data) => { assert.equal(draft.has(ref.path), false);draft.set(ref.path, structuredClone(data)); },
      set: (ref, data) => draft.set(ref.path, structuredClone(data)),
      update: (ref, data) => draft.set(ref.path, { ...draft.get(ref.path), ...structuredClone(data) }),
      delete: ref => draft.delete(ref.path) };
    const result = await fn(tx);
    if (this.failCommit) throw new Error('simulated atomic commit failure');
    this.values = draft;return result;
  }
}
function setup() {
  const f = fixture(), db = new MemoryFirestore(), meta = { releaseId: 'a'.repeat(16) + '-123', runID: 123,
    requestSHA256: f.request.requestSHA256, catalogCandidates: f.request.catalogCandidates, verifiedCheckpoint: f.request.verifiedCheckpoint };
  db.values.set('packageCatalog/gorge-core', { version: 'original-working-core', active: true, preserved: ['all', 'fields'] });
  db.values.set('packageCatalog/gorge-base', { version: '2026.10.08.1', unrelated: true });
  db.values.set('packageCatalog/route-rte-0001', { version: '1', unrelated: true });
  return { ...f, db, meta };
}
test('atomic catalog failure changes no current or backup document', async () => {
  const f = setup(), before = structuredClone([...f.db.values]);f.db.failCommit = true;
  await assert.rejects(activateCatalogs(f.db, f.document, f.meta, 'now'));
  assert.deepEqual([...f.db.values], before);
});
test('delivery allowance is consumed once and cannot be reused by another workflow', async () => {
  const f = setup();await claimDeliveryAllowance(f.db, f.meta, 'now');await verifyDeliveryClaim(f.db, f.meta);
  await assert.rejects(claimDeliveryAllowance(f.db, f.meta, 'later'));
  await assert.rejects(verifyDeliveryClaim(f.db, { ...f.meta, runID: 456 }));
  assert.equal(f.db.values.get('mapPackageReleaseRequests/' + f.meta.requestSHA256).refundable, false);
});
test('rollback restores old catalogs exactly and removes only newly created scoped entries', async () => {
  const f = setup(), before = structuredClone([...f.db.values]);
  const result = await activateCatalogs(f.db, f.document, f.meta, 'now');assert.equal(result.activated, 9);
  assert.equal(f.db.values.get('packageCatalog/gorge-core').version, f.document.catalogs.find(c => c.packageId === 'gorge-core').version);
  const rollback = await rollbackCatalogs(f.db, f.meta, 'later');assert.equal(rollback.originalCatalogRestored, true);
  assert.deepEqual([...f.db.values].filter(([key]) => key.startsWith('packageCatalog/')), before);
  assert.equal((await rollbackCatalogs(f.db, f.meta, 'again')).rollbackNeeded, false);
});
test('a competing catalog owner blocks rollback without changing any document', async () => {
  const f = setup();await activateCatalogs(f.db, f.document, f.meta, 'now');
  f.db.values.get('packageCatalog/gorge-core').rrghFinalMapRelease = 'someone-else';
  const before = structuredClone([...f.db.values]);
  await assert.rejects(rollbackCatalogs(f.db, f.meta, 'later'));assert.deepEqual([...f.db.values], before);
});
test('release cannot be replayed or called phone-tested without evidence', async () => {
  const f = setup();await activateCatalogs(f.db, f.document, f.meta, 'now');
  await assert.rejects(activateCatalogs(f.db, f.document, f.meta, 'again'));
  await assert.rejects(markDeliveryVerified(f.db, f.meta, { physicalIPhoneTestComplete: true }, 'later'));
  const report = { requestSHA256: f.meta.requestSHA256, authoritySHA256: f.request.authoritySHA256,
    authenticatedIndexes: 3, authenticatedPackages: 9, fullyHashedSampleParts: 3,
    everyPackageIdentityAndRangeVerified: true, offlineLeaseVerified: true,
    unauthenticatedDeliveryDenied: true, physicalIPhoneTestComplete: false };
  assert.equal((await markDeliveryVerified(f.db, f.meta, report, 'later')).finalPackageDeliveryComplete, true);
  await assert.rejects(rollbackCatalogs(f.db, f.meta, 'stale-failure'));
});

export { MemoryFirestore };
