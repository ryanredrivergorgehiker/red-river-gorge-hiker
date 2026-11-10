import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './rrgh-final-catalog-fixture.mjs';
import { IDS, sha256 } from './rrgh-final-catalog-contract.mjs';
import { ReadBudget } from './rrgh-final-catalog-read.mjs';
import { verifyDelivery } from './rrgh-final-catalog-smoke.mjs';

function networkFixture(mutation = '') {
  const f = fixture(), data = new Map(), catalogs = f.document.catalogs;
  for (const group of Object.keys(IDS)) {
    const parts = catalogs.filter(c => c.packageId.startsWith(IDS[group] + '-'));
    for (let i = 0; i < parts.length; i++) {
      const c = parts[i], bytes = Buffer.alloc(4096 + i, group.length + i), hash = sha256(bytes);
      c.packageId = IDS[group] + '-' + hash;c.sha256 = hash;c.byteCount = bytes.length;c.version = hash.slice(0, 24);
      Object.assign(c.offlineManifest, { packageID: c.packageId, sha256: hash, byteCount: bytes.length, version: c.version });
      Object.assign(f.parsed[group].parts[i], { packageID: c.packageId, sha256: hash, byteCount: bytes.length,
        version: c.version, extractedByteCount: 100 });data.set(c.packageId, bytes);
    }
    const c = catalogs.find(c => c.packageId === IDS[group]), bytes = Buffer.from(JSON.stringify(f.parsed[group]));
    c.sha256 = sha256(bytes);c.byteCount = bytes.length;
    Object.assign(c.offlineManifest, { sha256: c.sha256, byteCount: bytes.length });data.set(c.packageId, bytes);
  }
  const calls = [], end = '2030-01-01T00:00:00Z';
  const fetcher = async (url, options) => {
    calls.push({ url, method: options.method, range: options.headers?.range });
    if (url === 'https://account.example.invalid') {
      const { operation, packageId } = JSON.parse(options.body).data;let result;
      if (operation === 'getAccountState') result = { uid: 'test-user' };
      if (operation === 'startBaseTrial') result = { trial: { started: true, endsAt: end }, account: { access: { base: true } } };
      if (operation === 'issueOfflineAccessLease') result = { issued: true,
        lease: { format: 'compact_jws_rs256_v1', algorithm: 'RS256', signedToken: 'fake', keyId: 'test' }, verificationKeys: [] };
      if (operation === 'authorizeProtectedPackage') {
        const c = catalogs.find(c => c.packageId === packageId);
        result = { authorized: true, package: { ...c }, delivery: { ready: true, method: 'capability_https', httpMethod: 'GET',
          authorizationScheme: 'Bearer', authorizationToken: 'synthetic-capability-token-prefix-' + packageId, expiresAt: end,
          url: 'https://us-east5-rrgh-nonproduction.cloudfunctions.net/rrghPackageDownload' } };
        if (mutation === 'descriptor') result.package.sha256 = '0'.repeat(64);
        if (mutation === 'foreign-url') result.delivery.url = 'https://attacker.invalid';
      }
      return Response.json({ result });
    }
    if (!options.headers?.authorization) return new Response('denied', { status: mutation === 'public' ? 200 : 401 });
    const id = options.headers.authorization.slice(7 + 'synthetic-capability-token-prefix-'.length), c = catalogs.find(c => c.packageId === id);
    const [start, finish] = options.headers.range.slice(6).split('-').map(Number);
    const bytes = Buffer.from(data.get(id).subarray(start, finish + 1));
    if (mutation === 'hash') bytes[0] ^= 1;
    return new Response(bytes, { status: 206, headers: {
      'content-range': `bytes ${start}-${finish}/${c.byteCount}`,
      'x-rrgh-package-id': mutation === 'identity' ? 'wrong' : id, 'x-rrgh-package-version': c.version } });
  };
  const budget = new ReadBudget({ bytes: 10485760, requests: 100 }, fetcher);
  const options = { budget, document: f.document, request: f.request, functionUrl: 'https://account.example.invalid',
    idToken: 'test-token', uid: 'test-user', verifyLease: () => ({ valid: mutation !== 'lease',
      claims: { trial: true, grants: ['base'], trialEndsAt: end, validUntil: end } }) };
  return { options, calls };
}
test('fresh authenticated verification checks all indexes, all parts and full largest parts', async () => {
  const { options, calls } = networkFixture();const result = await verifyDelivery(options);
  assert.equal(result.authenticatedIndexes, 3);assert.equal(result.authenticatedPackages, 9);
  assert.equal(result.fullyHashedSampleParts, 3);assert.equal(result.physicalIPhoneTestComplete, false);
  assert.equal(calls.filter(c => c.range).length, 12);
});
test('changed bytes, identity, public access, foreign endpoints and invalid leases stop delivery acceptance', async () => {
  for (const change of ['hash', 'identity', 'public', 'foreign-url', 'descriptor', 'lease']) {
    const { options } = networkFixture(change);await assert.rejects(verifyDelivery(options), undefined, change);
  }
});
