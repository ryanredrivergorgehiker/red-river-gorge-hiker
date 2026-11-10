// Synthetic contract fixture; never production acceptance or byte evidence.
import { IDS, PROFILE, BUCKET, canonicalSHA } from './rrgh-final-catalog-contract.mjs';

function fixture() {
  const authoritySHA256 = 'a'.repeat(64), version = '2026.11.10.regional.' + 'a'.repeat(16);
  let serial = 1;
  function ref(bytes = 1000) {
    const sha = (serial++).toString(16).padStart(64, '0');
    return { key: 'engineering/map-production/plans/' + 'f'.repeat(64) + '/slots/00000/packs/' + sha,
      sha256: sha, bytes, generation: '123' };
  }
  const sources = [{ sourceID: 'synthetic-test-only', sourceURL: 'https://example.invalid', provider: 'Fixture',
    vintageOrRetrievedAt: 'synthetic', areaOfInterestOrSourceObjects: 'synthetic', processingMethod: 'synthetic',
    rightsBasis: 'synthetic', attributionOrDisclaimer: 'synthetic', outputVersion: version, integritySHA256: 'b'.repeat(64) }];
  const catalogs = [], parts = [], indexes = [], parsed = {};
  function catalog(packageId, object, v) {
    const c = { packageId, version: v, byteCount: object.bytes, sha256: object.sha256,
      active: false, contentReady: false, packageType: 'offline_base', requiredEntitlement: 'base', storageBucket: BUCKET,
      objectName: object.key, objectGeneration: object.generation,
      objectMetadata: { 'rrgh-sha256': object.sha256, 'rrgh-package-id': packageId, 'rrgh-version': v },
      offlineManifest: { packageID: packageId, version: v, byteCount: object.bytes, sha256: object.sha256, sources } };
    catalogs.push(c);return c;
  }
  for (const group of Object.keys(IDS)) {
    const members = [];
    for (let i = 0; i < 2; i++) {
      const object = ref(200000000), packageID = IDS[group] + '-' + object.sha256;
      const rasterTiles = group === 'core' ? 30719 : 54210;
      const sharedFiles = group === 'core' && i === 0 ? 340 : 0;
      const part = { packageID, version: object.sha256.slice(0, 24), byteCount: object.bytes, sha256: object.sha256,
        packageType: 'offline_base', requiredEntitlement: 'base', manifestSHA256: 'c'.repeat(64),
        fileCount: rasterTiles + sharedFiles + 1, extractedByteCount: 190000000 };
      members.push(part);catalog(packageID, object, part.version);
      parts.push({ partID: group + '-' + i, group, part, object, rasterTiles, sharedFiles,
        sharedReferencesVerified: sharedFiles > 0, allMemberHashesVerified: true, allRasterPixelsVerified: true,
        fullRemoteSHA256ReadbackVerified: true });
    }
    const object = ref(), c = catalog(IDS[group], object, version);
    indexes.push({ group, identity: c.offlineManifest, object });
    parsed[group] = { format: 'rrgh-map-bundle-v1', group, packageID: IDS[group], release: version,
      coverageScope: 'regional', regionalReady: true, provenanceComplete: true, required: group === 'core',
      minimumZoom: 10, maximumZoomByLayer: PROFILE[group], boundsWGS84: [-83.8, 37.65, -83.4, 37.95],
      fullSunlightCoverageVerified: group === 'core', sources, parts: members };
  }
  const catalogCandidates = ref(), verifiedCheckpoint = ref();
  const document = { format: 'rrgh-final-package-catalog-candidates-v1', authoritySHA256,
    active: false, contentReady: false, physicalIPhoneTestComplete: false, catalogs };
  const checkpoint = { format: 'rrgh-final-package-checkpoint-v1', authoritySHA256,
    rasterTiles: 278278, sharedFiles: 340, finalPackageDeliveryComplete: false, catalogCandidates, parts, indexes };
  const carry = { chargedUSD: '99.123456789012345678901234', storedBytes: 44000000000, priorRasterTiles: 278278 };
  const body = { format: 'rrgh-final-catalog-request-v1', authorizedBy: 'ryanredrivergorgehiker',
    projectId: 'rrgh-nonproduction', bucket: BUCKET, action: 'activate-and-verify', automaticRollback: true,
    authoritySHA256, sourceCarrySHA256: canonicalSHA(carry), packagePlanSHA256: 'd'.repeat(64),
    catalogCandidates, verifiedCheckpoint };
  const request = { ...body, requestSHA256: canonicalSHA(body) };
  const state = { owner: 'autonomous-v1', enabled: true, status: 'package-validation-waiting', mode: 'package',
    runID: 123, sequence: 1461, dispatchID: 'e'.repeat(64),
    completionProgress: { format: 'rrgh-raster-complete-package-wait-v1', fullRasterCoverageComplete: true,
      acceptedRasterTiles: 278278, remainingRasterTiles: 0 },
    package: { status: 'verified-awaiting-catalog', authoritySHA256, carry, verifiedCheckpoint,
      lastVerified: { runID: 123, planSHA256: body.packagePlanSHA256, packageBytesIndependentlyVerified: true,
        verifiedIndexes: 3, catalogCandidates, checkpoint: verifiedCheckpoint } },
    finalDeliveryReservation: { format: 'rrgh-final-delivery-reservation-v1', authorizedBy: 'ryanredrivergorgehiker',
      requestSHA256: request.requestSHA256, sourceCarrySHA256: body.sourceCarrySHA256, reservedUSD: '0.75',
      chargedBeforeUSD: carry.chargedUSD, chargedAfterUSD: '99.873456789012345678901234', refundable: false,
      maxReadBytes: 1073741824, maxStorageRequests: 2000, maxFirestoreOperations: 10000 } };
  const run = { id: 123, status: 'completed', conclusion: 'success',
    repository: { full_name: 'ryanredrivergorgehiker/red-river-gorge-hiker' },
    head_branch: 'lane20/offline-production-preflight-20261029', run_attempt: 1, event: 'workflow_dispatch',
    actor: { login: 'github-actions[bot]' }, path: '.github/workflows/offline-map-restricted-dispatch.yml',
    display_title: 'RRGH package 1461 ' + state.dispatchID };
  const jobs = ['package-stage', 'package-verify', 'package-advance'].map(name => ({ name, status: 'completed', conclusion: 'success' }));
  return { document, checkpoint, request, state, run, jobs, parsed };
}

export { fixture };
