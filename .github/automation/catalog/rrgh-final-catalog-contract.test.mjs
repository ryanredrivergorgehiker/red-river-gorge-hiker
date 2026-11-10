import test from 'node:test';
import assert from 'node:assert/strict';
import { deflateSync } from 'node:zlib';
import { IDS, PROFILE, BUCKET, sha256, canonicalSHA, decodeRecord, validateOwner,
  validateCatalogs, validateIndex, activeCatalog } from './rrgh-final-catalog-contract.mjs';

import { fixture } from './rrgh-final-catalog-fixture.mjs';

test('only exact completed package ownership and retained delivery allowance qualify', () => {
  const f = fixture();assert.equal(validateOwner(f.state, f.request, f.run, f.jobs), true);
  f.state.finalDeliveryReservation.chargedAfterUSD = '99.873456789012345678901233';
  assert.throws(() => validateOwner(f.state, f.request, f.run, f.jobs));
});
test('changed request, wrong actor, failed verifier and incomplete coverage are rejected', () => {
  for (const change of ['request', 'actor', 'job', 'coverage', 'reservation']) {
    const f = fixture();
    if (change === 'request') f.request.automaticRollback = false;
    if (change === 'actor') f.run.actor.login = 'someone-else';
    if (change === 'job') f.jobs[1].conclusion = 'failure';
    if (change === 'coverage') f.state.completionProgress.remainingRasterTiles = 1;
    if (change === 'reservation') f.state.finalDeliveryReservation.refundable = true;
    assert.throws(() => validateOwner(f.state, f.request, f.run, f.jobs), change);
  }
});
test('all verified parts and three native indexes join exact scoped catalog records', () => {
  const f = fixture();assert.equal(validateCatalogs(f.document, f.checkpoint, f.request).size, 9);
  for (const group of Object.keys(IDS)) {
    const c = f.document.catalogs.find(c => c.packageId === IDS[group]);
    assert.equal(validateIndex(f.parsed[group], c, f.document.catalogs), true);
    const active = activeCatalog(c, 'test-release');
    assert.equal(active.deliveryState, 'ready');assert.equal(active.requiredEntitlement, 'base');
    assert.equal(active.objectName, c.objectName);assert.equal(active.rrghFinalMapRelease, 'test-release');
  }
});
test('unverified pixels, changed storage identity, entitlement and duplicate catalogs fail', () => {
  for (const change of ['pixels', 'generation', 'entitlement', 'duplicate', 'missing', 'count']) {
    const f = fixture();
    if (change === 'pixels') f.checkpoint.parts[0].allRasterPixelsVerified = false;
    if (change === 'generation') f.document.catalogs[0].objectGeneration = '999';
    if (change === 'entitlement') f.document.catalogs[0].requiredEntitlement = 'backpacking';
    if (change === 'duplicate') f.document.catalogs.push(f.document.catalogs[0]);
    if (change === 'missing') f.document.catalogs.pop();
    if (change === 'count') f.checkpoint.parts[0].rasterTiles--;
    assert.throws(() => validateCatalogs(f.document, f.checkpoint, f.request), change);
  }
});
test('index cannot claim different region, missing part, source provenance or native bounds', () => {
  for (const change of ['region', 'part', 'provenance', 'size']) {
    const f = fixture(), index = f.parsed.core, c = f.document.catalogs.find(c => c.packageId === IDS.core);
    if (change === 'region') index.boundsWGS84[0] -= 0.1;
    if (change === 'part') index.parts.pop();
    if (change === 'provenance') index.sources = [];
    if (change === 'size') index.parts[0].fileCount = 60001;
    assert.throws(() => validateIndex(index, c, f.document.catalogs), change);
  }
});
test('protected compressed metadata is hash-bound and decoded-size bounded', () => {
  const raw = Buffer.concat([Buffer.from('RRGH-CHECKPOINT-Z1\n'), deflateSync(Buffer.from('{"value":"test"}'))]);
  const ref = { key: 'engineering/map-production/plans/' + 'a'.repeat(64) + '/slots/00001/indexes/' + sha256(raw),
    sha256: sha256(raw), bytes: raw.length, generation: '123' };
  assert.deepEqual(decodeRecord(raw, ref), { value: 'test' });
  assert.throws(() => decodeRecord(Buffer.concat([raw, Buffer.from('!')]), ref));
  assert.throws(() => decodeRecord(raw, ref, 3));
});

