import test from 'node:test';
import assert from 'node:assert/strict';
import { ReadBudget, ProtectedReader } from './rrgh-final-catalog-read.mjs';
import { BUCKET, sha256 } from './rrgh-final-catalog-contract.mjs';

test('failed attempts remain charged and exhausted allowance prevents network access', async () => {
  let calls = 0;
  const budget = new ReadBudget({ bytes: 8, requests: 1 }, async () => { calls++;return new Response('no', { status: 503 }); });
  await assert.rejects(budget.request('https://example.invalid', { maximum: 8 }), /503/);
  await assert.rejects(budget.request('https://example.invalid', { maximum: 1 }), /allowance/);
  assert.equal(calls, 1);assert.equal(budget.bytes, 8);
});
test('streamed overflow and content length overflow are bounded without retry', async () => {
  for (const headers of [{}, { 'content-length': '9' }]) {
    const budget = new ReadBudget({ bytes: 8, requests: 2 }, async (_url, options) => {
      assert.equal(options.redirect, 'error');return new Response('123456789', { headers });
    });
    await assert.rejects(budget.request('https://example.invalid', { maximum: 8 }), /exceeds/);
    assert.equal(budget.requests, 1);
  }
});
test('private reads pin the exact generation and reject changed immutable bytes', async () => {
  const bytes = Buffer.from('accepted'), sha = sha256(bytes);
  const ref = { key: 'engineering/map-production/plans/' + 'a'.repeat(64) + '/slots/00001/indexes/' + sha,
    bytes: bytes.length, sha256: sha, generation: '123' };
  let corrupt = false;
  const budget = new ReadBudget({ bytes: 100, requests: 3 }, async (url, options) => {
    assert.equal(new URL(url).searchParams.get('generation'), '123');
    assert.match(url, new RegExp(BUCKET));assert.equal(options.headers.authorization, 'Bearer secret');
    return new Response(corrupt ? 'changed!' : bytes);
  });
  const reader = new ProtectedReader(budget, async () => 'secret');
  assert.deepEqual(await reader.read(ref), bytes);corrupt = true;
  await assert.rejects(reader.read(ref), /differs/);
});
test('indirect proxy storage and document work is reserved before making the request', async () => {
  let calls = 0;
  const budget = new ReadBudget({ bytes: 100, requests: 5, storageRequests: 2, firestoreOperations: 8 }, async () => {
    calls++;return new Response('ok');
  });
  await budget.request('https://example.invalid', { maximum: 2, storageRequests: 2, firestoreOperations: 8 });
  await assert.rejects(budget.request('https://example.invalid', { maximum: 2, storageRequests: 1 }), /indirect/);
  assert.equal(calls, 1);assert.equal(budget.firestoreOperations, 8);
});
