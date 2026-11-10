import { createHash } from 'node:crypto';
import { IDS, requireValue, same, validateIndex } from './rrgh-final-catalog-contract.mjs';

const RANGE = 8 * 1024 * 1024;
const DOWNLOAD_URL = 'https://us-east5-rrgh-nonproduction.cloudfunctions.net/rrghPackageDownload';

export async function verifyDelivery({ budget, document, request, functionUrl, idToken, uid, verifyLease, verifyCurrentObject }) {
  requireValue(new URL(functionUrl).protocol === 'https:', 'HTTPS account endpoint required');
  requireValue(typeof verifyCurrentObject === 'function', 'Fresh current-generation verification required');
  async function api(operation, extra = {}) {
    const { bytes } = await budget.request(functionUrl, { method: 'POST', maximum: 131072,
      storageRequests: operation === 'authorizeProtectedPackage' ? 1 : 0,
      firestoreOperations: operation === 'startBaseTrial' ? 20 : operation === 'authorizeProtectedPackage' ? 8 : 10,
      headers: { 'content-type': 'application/json', authorization: 'Bearer ' + idToken },
      body: JSON.stringify({ data: { operation, ...extra } }) });
    const body = JSON.parse(bytes.toString('utf8'));requireValue(body.result && !body.error, 'Authenticated account operation failed');
    return body.result;
  }
  const initial = await api('getAccountState');requireValue(initial.uid === uid, 'Synthetic session identity changed');
  const trial = await api('startBaseTrial');
  requireValue(trial.trial?.started === true && trial.account?.access?.base === true, 'Synthetic Base trial did not start');
  const lease = await api('issueOfflineAccessLease');
  requireValue(lease.issued === true && lease.lease?.format === 'compact_jws_rs256_v1' &&
    lease.lease?.algorithm === 'RS256' && Array.isArray(lease.verificationKeys), 'Offline lease was not issued');
  const verified = verifyLease({ signedToken: lease.lease.signedToken, keyId: lease.lease.keyId,
    verificationKeys: lease.verificationKeys, expectedUid: uid });
  requireValue(verified.valid === true && verified.claims?.trial === true &&
    same(verified.claims?.grants, ['base']) && verified.claims?.trialEndsAt === trial.trial.endsAt &&
    Date.parse(verified.claims.validUntil) <= Date.parse(trial.trial.endsAt), 'Signed offline Base lease failed verification');
  const samples = new Set(Object.values(IDS).map(id => {
    const choices = document.catalogs.filter(c => c.packageId.startsWith(id + '-'));
    requireValue(choices.length > 0, 'Missing sample group');
    // The largest part exercises the native size/range boundary.
    return choices.sort((a, b) => b.byteCount - a.byteCount || a.packageId.localeCompare(b.packageId))[0].packageId;
  }));
  let indexes = 0, fullParts = 0, authenticated = 0, denied = false;
  for (const candidate of document.catalogs) {
    await verifyCurrentObject(candidate);
    const result = await api('authorizeProtectedPackage', { packageId: candidate.packageId });
    const p = result.package, delivery = result.delivery;
    requireValue(result.authorized === true && delivery?.ready === true && p?.packageId === candidate.packageId &&
      p.version === candidate.version && p.sha256 === candidate.sha256 && p.byteCount === candidate.byteCount &&
      p.packageType === 'offline_base' && p.requiredEntitlement === 'base' &&
      same(p.offlineManifest, candidate.offlineManifest), 'Authenticated package descriptor differs from verified catalog');
    requireValue(delivery.method === 'capability_https' && delivery.httpMethod === 'GET' &&
      delivery.authorizationScheme === 'Bearer' && delivery.url === DOWNLOAD_URL &&
      typeof delivery.authorizationToken === 'string' && delivery.authorizationToken.length >= 32 &&
      Date.parse(delivery.expiresAt) > Date.now(), 'Protected delivery capability is invalid');
    if (!denied) {
      await budget.request(delivery.url, { maximum: 16384, expectedStatus: 401 });denied = true;
    }
    async function range(start, end) {
      const { bytes, response } = await budget.request(delivery.url, { maximum: end - start + 1, expectedStatus: 206,
        storageRequests: 2, firestoreOperations: 8,
        headers: { authorization: 'Bearer ' + delivery.authorizationToken, range: `bytes=${start}-${end}` } });
      requireValue(response.headers.get('content-range') === `bytes ${start}-${end}/${p.byteCount}` &&
        response.headers.get('x-rrgh-package-id') === p.packageId &&
        response.headers.get('x-rrgh-package-version') === p.version && bytes.length === end - start + 1,
        'Authenticated package range or identity header differs');
      return bytes;
    }
    const isIndex = Object.values(IDS).includes(p.packageId);
    if (isIndex || samples.has(p.packageId)) {
      const hash = createHash('sha256'), chunks = [];
      for (let start = 0; start < p.byteCount; start += RANGE) {
        const bytes = await range(start, Math.min(p.byteCount - 1, start + RANGE - 1));
        hash.update(bytes);if (isIndex) chunks.push(bytes);
      }
      requireValue(hash.digest('hex') === p.sha256, 'Authenticated download SHA-256 mismatch');
      if (isIndex) { validateIndex(JSON.parse(Buffer.concat(chunks).toString('utf8')), candidate, document.catalogs);indexes++; }
      else fullParts++;
    } else {
      await range(0, Math.min(1023, p.byteCount - 1));
      await range(Math.max(0, p.byteCount - 1024), p.byteCount - 1);
    }
    authenticated++;
  }
  return { format: 'rrgh-final-authenticated-delivery-v1', requestSHA256: request.requestSHA256,
    authoritySHA256: document.authoritySHA256, authenticatedIndexes: indexes,
    authenticatedPackages: authenticated, fullyHashedSampleParts: fullParts,
    everyPackageIdentityAndRangeVerified: true, currentStorageGenerationsVerified: true, offlineLeaseVerified: true,
    unauthenticatedDeliveryDenied: denied, physicalIPhoneTestComplete: false, readBudget: budget.summary() };
}
