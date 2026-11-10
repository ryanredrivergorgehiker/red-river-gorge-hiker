"""Native indexes and inactive catalog candidates from fully verified parts."""
import copy
import hashlib
import json

from rrgh_package_authority import require


def release(authority_sha):
    return '2026.11.10.regional.'+authority_sha[:16]


def build(layout,checkpoint):
    from build_gorge_map_bundles import IDS,PROFILE,AOI,json_bytes
    require(len(checkpoint['parts'])==len(layout['parts']) and
        sum(p['rasterTiles'] for p in checkpoint['parts'])==278278 and
        sum(p['sharedFiles'] for p in checkpoint['parts'])==340 and
        sum(p['sharedReferencesVerified'] for p in checkpoint['parts'])==1,
        'All regional pixels and shared references must pass fresh remote verification')
    version=release(layout['authoritySHA256']);indexes={};candidates=[]
    def candidate(identity,reference,sources):
        package_id=identity['packageID'];sha=identity['sha256']
        require(reference['sha256']==sha and reference['bytes']==identity['byteCount'],
                'Catalog object differs from verified package')
        offline={k:identity[k] for k in ('packageID','version','byteCount','sha256')}
        offline['sources']=copy.deepcopy(sources)
        return dict(packageId=package_id,packageType='offline_base',requiredEntitlement='base',
            version=identity['version'],byteCount=identity['byteCount'],sha256=sha,
            offlineManifest=offline,active=False,contentReady=False,
            storageBucket='rrgh-nonproduction-protected-packages',objectName=reference['key'],
            objectGeneration=reference['generation'],
            objectMetadata={'rrgh-sha256':sha,'rrgh-package-id':package_id,'rrgh-version':identity['version']})
    for group in PROFILE:
        sources=layout['sources'][group];parts=[]
        require(bool(sources),'Native provenance is required')
        for verified,expected in zip(checkpoint['parts'],layout['parts'],strict=True):
            require(verified['partID']==expected['id'] and verified['group']==expected['group'] and
                verified['rasterTiles']==expected['rasterTiles'] and verified['sharedFiles']==expected['sharedFiles'],
                'Verified part set differs from regional layout')
            if verified['group']!=group:continue
            p=verified['part'];require(p['packageID']==IDS[group]+'-'+p['sha256'] and
                p['version']==p['sha256'][:24], 'Native part identity changed')
            parts.append(copy.deepcopy(p));candidates.append(candidate(p,verified['object'],sources))
        require(0<len(parts)<=64,'Native part limit exceeded')
        value=dict(format='rrgh-map-bundle-v1',group=group,packageID=IDS[group],release=version,
            coverageScope='regional',boundsWGS84=AOI,required=group=='core',minimumZoom=10,
            maximumZoomByLayer=PROFILE[group],parts=parts,regionalReady=True,
            fullSunlightCoverageVerified=group=='core',sources=sources,provenanceComplete=True,
            architecture='existing private GCS + authenticated backend + existing Base entitlement and offline lease')
        raw=json_bytes(value);require(0<len(raw)<=2**20,'Native index limit exceeded')
        identity=dict(packageID=IDS[group],version=version,byteCount=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        indexes[group]=dict(value=value,raw=raw,identity=identity)
    return indexes,candidates,candidate
