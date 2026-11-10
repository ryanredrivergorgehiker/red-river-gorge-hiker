import { createHash } from 'node:crypto';
import { inflateSync } from 'node:zlib';

export const BUCKET = 'rrgh-nonproduction-protected-packages';
export const IDS = { core: 'gorge-core', 'leaf-on': 'gorge-aerial-leaf-on', 'leaf-off': 'gorge-aerial-leaf-off' };
export const PROFILE = { core: { hiking: 17, terrain: 17, 'usgs-topo': 16 }, 'leaf-on': { 'leaf-on': 18 }, 'leaf-off': { 'leaf-off': 18 } };
const SOURCE_FIELDS = ['sourceID', 'sourceURL', 'provider', 'vintageOrRetrievedAt',
  'areaOfInterestOrSourceObjects', 'processingMethod', 'rightsBasis',
  'attributionOrDisclaimer', 'outputVersion', 'integritySHA256'];
export function requireValue(ok, message) { if (!ok) throw new Error(message); }
export function sha256(raw) { return createHash('sha256').update(raw).digest('hex'); }
export function ordered(value) {
  if (Array.isArray(value)) return value.map(ordered);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, ordered(value[k])]));
  return value;
}
export function same(a, b) { return JSON.stringify(ordered(a)) === JSON.stringify(ordered(b)); }
export function canonicalSHA(value) { return sha256(Buffer.from(JSON.stringify(ordered(value)) + '\n')); }
function money(value) {
  requireValue(typeof value === 'string' && /^\d{1,3}(\.\d{1,40})?$/.test(value), 'Invalid finite campaign amount');
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * (10n ** 40n) + BigInt(fraction.padEnd(40, '0'));
}
export function checkRef(ref, maximum = 1048576) {
  requireValue(ref && /^engineering\/map-production\/plans\/[a-f0-9]{64}\/slots\/\d{5}\/(indexes|packs)\/[a-f0-9]{64}$/.test(ref.key) &&
    /^[a-f0-9]{64}$/.test(ref.sha256) && /^[1-9][0-9]*$/.test(ref.generation) &&
    Number.isSafeInteger(ref.bytes) && ref.bytes > 0 && ref.bytes <= maximum, 'Unbounded or foreign delivery reference');
  return ref;
}
export function decodeRecord(raw, ref, decodedLimit = 4194304) {
  checkRef(ref);
  requireValue(raw.length === ref.bytes && sha256(raw) === ref.sha256, 'Immutable delivery record hash changed');
  const magic = Buffer.from('RRGH-CHECKPOINT-Z1\n');
  const decoded = raw.subarray(0, magic.length).equals(magic) ?
    inflateSync(raw.subarray(magic.length), { maxOutputLength: decodedLimit }) : raw;
  requireValue(decoded.length <= decodedLimit, 'Decoded delivery record exceeds bound');
  return JSON.parse(decoded.toString('utf8'));
}
export function validateOwner(state, request, run, jobs) {
  const p = state.package, last = p?.lastVerified, progress = state.completionProgress;
  const { requestSHA256, ...body } = request;
  requireValue(canonicalSHA(body) === requestSHA256 && request.format === 'rrgh-final-catalog-request-v1' && request.authorizedBy === 'ryanredrivergorgehiker' &&
    request.projectId === 'rrgh-nonproduction' && request.bucket === BUCKET &&
    request.action === 'activate-and-verify' && request.automaticRollback === true,
    'Exact nonproduction catalog authorization required');
  requireValue(state.owner === 'autonomous-v1' && state.enabled === true &&
    state.status === 'package-validation-waiting' && state.mode === 'package' &&
    progress?.format === 'rrgh-raster-complete-package-wait-v1' && progress.fullRasterCoverageComplete === true &&
    progress.acceptedRasterTiles === 278278 && progress.remainingRasterTiles === 0 &&
    p.status === 'verified-awaiting-catalog' && p.authoritySHA256 === request.authoritySHA256 &&
    last?.runID === state.runID && last.planSHA256 === request.packagePlanSHA256 &&
    last.packageBytesIndependentlyVerified === true && last.verifiedIndexes === 3 &&
    same(last.catalogCandidates, request.catalogCandidates) && same(last.checkpoint, request.verifiedCheckpoint) &&
    same(p.verifiedCheckpoint, request.verifiedCheckpoint), 'Final package acceptance differs from owner request');
  requireValue(run.id === state.runID && run.status === 'completed' && run.conclusion === 'success' &&
    run.repository?.full_name === 'ryanredrivergorgehiker/red-river-gorge-hiker' &&
    run.head_branch === 'lane20/offline-production-preflight-20261029' && run.run_attempt === 1 &&
    run.event === 'workflow_dispatch' && run.actor?.login === 'github-actions[bot]' &&
    run.path === '.github/workflows/offline-map-restricted-dispatch.yml' &&
    run.display_title === `RRGH package ${state.sequence} ${state.dispatchID}`,
    'Final package workflow identity or conclusion differs');
  for (const name of ['package-stage', 'package-verify', 'package-advance']) {
    const selected = jobs.filter(j => j.name === name);
    requireValue(selected.length === 1 && selected[0].status === 'completed' && selected[0].conclusion === 'success',
      'Incomplete final package workflow verification');
  }
  const reserved = state.finalDeliveryReservation;
  requireValue(reserved?.format === 'rrgh-final-delivery-reservation-v1' &&
    reserved.authorizedBy === 'ryanredrivergorgehiker' && reserved.requestSHA256 === request.requestSHA256 &&
    reserved.sourceCarrySHA256 === request.sourceCarrySHA256 && request.sourceCarrySHA256 === canonicalSHA(p.carry) &&
    reserved.reservedUSD === '0.75' && money(reserved.chargedBeforeUSD) === money(p.carry.chargedUSD) &&
    money(reserved.chargedAfterUSD) === money(reserved.chargedBeforeUSD) + money('0.75') &&
    money(reserved.chargedAfterUSD) <= money('123') && reserved.refundable === false &&
    reserved.maxReadBytes === 1073741824 && reserved.maxStorageRequests === 1000 &&
    reserved.maxFirestoreOperations === 5000, 'Complete final delivery reservation missing or changed');
  checkRef(request.catalogCandidates);checkRef(request.verifiedCheckpoint);
  return true;
}
export function validateCatalogs(document, checkpoint, request) {
  requireValue(document.format === 'rrgh-final-package-catalog-candidates-v1' &&
    document.authoritySHA256 === request.authoritySHA256 && document.active === false && document.contentReady === false &&
    document.physicalIPhoneTestComplete === false && Array.isArray(document.catalogs) &&
    document.catalogs.length >= 6 && document.catalogs.length <= 195,
    'Complete inactive nonproduction catalog candidate required');
  requireValue(checkpoint.format === 'rrgh-final-package-checkpoint-v1' &&
    checkpoint.authoritySHA256 === request.authoritySHA256 && checkpoint.rasterTiles === 278278 &&
    checkpoint.sharedFiles === 340 && checkpoint.finalPackageDeliveryComplete === false &&
    same(checkpoint.catalogCandidates, request.catalogCandidates) && checkpoint.indexes.length === 3,
    'Catalog candidate is not the independently verified final checkpoint');
  const refs = new Map();
  requireValue(checkpoint.parts.reduce((n, p) => n + p.rasterTiles, 0) === 278278 &&
    checkpoint.parts.reduce((n, p) => n + p.sharedFiles, 0) === 340 &&
    checkpoint.parts.filter(p => p.sharedReferencesVerified === true).length === 1,
    'Full regional and shared package verification required');
  for (const part of checkpoint.parts) {
    requireValue(part.allMemberHashesVerified === true && part.allRasterPixelsVerified === true &&
      part.fullRemoteSHA256ReadbackVerified === true &&
      part.part.fileCount === part.rasterTiles + part.sharedFiles + 1, 'An unverified part cannot be activated');
    refs.set(part.part.packageID, part.object);
  }
  for (const index of checkpoint.indexes) refs.set(index.identity.packageID, index.object);
  requireValue(refs.size === document.catalogs.length && refs.size === checkpoint.parts.length + 3,
    'Duplicated or missing catalog object');
  const seen = new Set();
  for (const c of document.catalogs) {
    const isIndex = Object.values(IDS).includes(c.packageId);
    requireValue(!seen.has(c.packageId) && refs.has(c.packageId), 'Unknown or duplicate delivery package');seen.add(c.packageId);
    requireValue(c.active === false && c.contentReady === false && c.storageBucket === BUCKET &&
      c.packageType === 'offline_base' && c.requiredEntitlement === 'base' &&
      /^[a-f0-9]{64}$/.test(c.sha256) && Number.isSafeInteger(c.byteCount) && c.byteCount > 0 &&
      c.byteCount <= (isIndex ? 1048576 : 256000000), 'Invalid protected package bounds or entitlement');
    requireValue(isIndex ? c.version === '2026.11.10.regional.' + request.authoritySHA256.slice(0, 16) :
      Object.values(IDS).some(id => c.packageId === id + '-' + c.sha256) && c.version === c.sha256.slice(0, 24),
      'Catalog identity is not the accepted immutable package identity');
    const ref = checkRef(refs.get(c.packageId), isIndex ? 1048576 : 256000000);
    requireValue(c.objectName === ref.key && c.objectGeneration === ref.generation && c.sha256 === ref.sha256 && c.byteCount === ref.bytes &&
      same(c.objectMetadata, { 'rrgh-sha256': c.sha256, 'rrgh-package-id': c.packageId, 'rrgh-version': c.version }),
      'Catalog storage object differs from verified receipt');
    const m = c.offlineManifest;
    requireValue(m?.packageID === c.packageId && m.version === c.version && m.sha256 === c.sha256 && m.byteCount === c.byteCount &&
      Array.isArray(m.sources) && m.sources.length > 0 && m.sources.length <= 32,
      'Native offline manifest differs from verified catalog');
    for (const source of m.sources) requireValue(SOURCE_FIELDS.every(k => typeof source[k] === 'string' && source[k].trim()) &&
      /^[a-f0-9]{64}$/.test(source.integritySHA256), 'Native source provenance is incomplete');
  }
  requireValue(Object.values(IDS).every(id => seen.has(id)), 'Three regional indexes are required');
  return refs;
}
export function validateIndex(index, candidate, catalogs) {
  const group = index.group, allowed = catalogs.filter(c => c.packageId.startsWith(IDS[group] + '-'));
  requireValue(IDS[group] === candidate.packageId && index.format === 'rrgh-map-bundle-v1' &&
    index.packageID === candidate.packageId && index.release === candidate.version && index.coverageScope === 'regional' &&
    index.regionalReady === true && index.provenanceComplete === true && index.required === (group === 'core') &&
    index.minimumZoom === 10 && same(index.maximumZoomByLayer, PROFILE[group]) &&
    same(index.boundsWGS84, [-83.8, 37.65, -83.4, 37.95]) &&
    same(index.sources, candidate.offlineManifest.sources) && index.fullSunlightCoverageVerified === (group === 'core') &&
    Array.isArray(index.parts) && index.parts.length > 0 && index.parts.length <= 64 &&
    index.parts.length === allowed.length, 'Native regional index contract differs');
  const seen = new Set();
  for (const part of index.parts) {
    const match = allowed.find(c => c.packageId === part.packageID);
    requireValue(match && !seen.has(part.packageID) && part.version === match.version && part.sha256 === match.sha256 &&
      part.byteCount === match.byteCount && part.packageType === 'offline_base' && part.requiredEntitlement === 'base' &&
      Number.isSafeInteger(part.fileCount) && part.fileCount >= 2 && part.fileCount <= 60000 &&
      Number.isSafeInteger(part.extractedByteCount) && part.extractedByteCount > 0 && part.extractedByteCount < part.byteCount &&
      /^[a-f0-9]{64}$/.test(part.manifestSHA256), 'Native index contains an unverified or oversized part');
    seen.add(part.packageID);
  }
  return true;
}
export function activeCatalog(candidate, releaseId) {
  return { active: true, lifecycle: 'active', deliveryState: 'ready', packageType: 'offline_base',
    version: candidate.version, sha256: candidate.sha256, byteCount: candidate.byteCount,
    requiredEntitlement: 'base', storageBucket: BUCKET, objectName: candidate.objectName,
    objectGeneration: candidate.objectGeneration, contentType: 'application/octet-stream',
    offlineManifest: candidate.offlineManifest, policyVersion: 2, rrghFinalMapRelease: releaseId };
}
