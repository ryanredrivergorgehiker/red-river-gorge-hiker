"""Validate native shared dependencies against immutable content receipts."""
import json
import re
from pathlib import Path
from shapely.geometry import box
from shapely.ops import unary_union
from cached_cog_source import digest
from benchmark_gorge_pipeline import AOI

VECTORS={'hydro-flowline','hydro-waterbody','local-roads','forest-service-trails','state-park-trails','forest-service-roads','forest-ownership','wilderness','special-management','national-forest-land','county-boundaries','community-informal','oil-gas-wells'}

def validate_sun(root, accepted_manifest_sha256=None):
    root=Path(root);p=root/'data/map/rrg-lidar-sun-mobile-manifest.json';m=json.loads(p.read_text())
    if accepted_manifest_sha256 is not None and digest(p.read_bytes())!=accepted_manifest_sha256:
        raise ValueError('Accepted Sunlight manifest changed')
    if (m.get('boundsWgs84')!=AOI or not m.get('fullGorgeCoverageVerified') or m.get('minimumElevationFeet')!=1100
        or not m.get('acceptedHardLipReusedVerbatim') or m.get('acceptedSectorsPreserved')!=30):raise ValueError('Full accepted Sunlight lineage required')
    sectors=m['sectors']
    if len(sectors)!=80 or len({s['id'] for s in sectors})!=80:raise ValueError('Invalid Sunlight sector inventory')
    if box(*AOI).difference(unary_union([box(*s['boundsWgs84']) for s in sectors])).area>1e-10:raise ValueError('Sunlight coverage gap')
    files=[]
    for s in sectors:
        for detail in ['overview','detail']:
            for kind in ['sunrise','sunset']:
                e=s['variants'][detail][kind];path=root/e['file']
                if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():raise ValueError('Unsafe Sunlight path')
                raw=path.read_bytes()
                if len(raw)!=e['bytes'] or digest(raw)!=e['sha256']:raise ValueError('Sunlight hash mismatch')
                from PIL import Image
                with Image.open(path) as im:im.load()
                files.append(e)
        if 'hardFile' in s:
            authoring=root/s['hardFile']
            if authoring.exists():
                if digest(authoring.read_bytes())!=s['sourceHardSha256']:raise ValueError('Hard-rim receipt mismatch')
            elif accepted_manifest_sha256 is None or not re.fullmatch('[0-9a-f]{64}',s.get('sourceHardSha256','')):
                raise ValueError('Missing authoring geometry requires the pinned accepted raster manifest')
    files.append({'file':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())})
    return files


def validate_shared(entries):
    files={e['path']:e for e in entries}; descriptor=files.get('shared/SHARED-MAP.json')
    if not descriptor:raise ValueError('Regional core requires verified shared native descriptor')
    m=json.loads(Path(descriptor['source']).read_text())
    if set(v['id'] for v in m['vectors'])!=VECTORS or len(m['vectors'])!=13:raise ValueError('Required vector inventory mismatch')
    if m['boundsWgs84']!=dict(zip(['west','south','east','north'],AOI)):raise ValueError('Shared AOI mismatch')
    if not m['sunPotentialManifest']['sourceCommit'] or m['sunPotentialManifest']['sourceCommit']!=m['weatherManifest']['sourceCommit']:raise ValueError('Shared source lineage mismatch')
    for e in m['vectors']+m['staticAssets']+[m['sunPotentialManifest'],m['weatherManifest']]:
        f=files.get(e['path'])
        if not f or f['sha256']!=e['sha256'] or digest(Path(f['source']).read_bytes())!=e['sha256']:raise ValueError('Unverified shared dependency')
    sun=json.loads(Path(files[m['sunPotentialManifest']['path']]['source']).read_text())
    if (not sun.get('fullGorgeCoverageVerified') or sun.get('minimumElevationFeet')!=1100 or not sun.get('acceptedHardLipReusedVerbatim')
        or sun.get('boundsWgs84')!=AOI or box(*AOI).difference(unary_union([box(*s['boundsWgs84']) for s in sun['sectors']])).area>1e-10):raise ValueError('Shared Sunlight incomplete')
    prefix=m['websiteAssetsRoot'].rstrip('/')+'/'
    for s in sun['sectors']:
        for variant in s['variants'].values():
            for e in variant.values():
                if files.get(prefix+e['file'],{}).get('sha256')!=e['sha256']:raise ValueError('Missing Sunlight member')
    weather=json.loads(Path(files[m['weatherManifest']['path']]['source']).read_text())
    # Native weather manifest references must all resolve inside the verified static set.
    def check_refs(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='file' and isinstance(item,str) and prefix+item not in files:raise ValueError('Missing weather member')
                check_refs(item)
        elif isinstance(value,list):
            for item in value:check_refs(item)
    check_refs(weather)
    return True
