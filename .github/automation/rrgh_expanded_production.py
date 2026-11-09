"""Forward-only source expansion. No credentials, network calls, or replay.

Every native window still passes the existing full-mask renderer and separate
pixel/hash/package recovery. Metadata availability is never output acceptance.
Legacy rollback changes future source selection only; accepted history survives.
"""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import unquote
import zlib

from rrgh_source_window_intake import load_catalog, CATALOG_SHA
from rrgh_required_inventory import canonical, require

ROOT = Path(__file__).resolve().parents[2]
CATALOG = 'backend/config/official-source-intake-20261102/official-source-candidates.json'
TEMPLATE = '.github/automation/source-templates/benchmark_gorge_pipeline.py'
RIGHTS = '.github/automation/expanded-source-rights-20261102.json'
ENGINE = 'backend/scripts/benchmark_gorge_pipeline.py'
# Actual reviewed legacy renderer; separate from old/new CONFIG pointers.
OLD_ENGINE_SHA = '0c52b61f5bf97ced76923119b9f2e4aaebbcf07d5f3446223035e746be10c60e'
MARKER = 'rrgh-expanded-original-sources-v1'
LIMITS = {'hiking': 4, 'terrain': 4, 'leaf-off': 4}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def catalog_inventory(legacy, controller_root=ROOT):
    root = Path(controller_root)
    rights = json.loads((root/RIGHTS).read_bytes())
    require(rights['catalogSHA256'] == CATALOG_SHA and
            rights['use'] == 'attributed-commercial-offline-derivatives' and
            rights['sourceFamilies'] == ['hiking', 'dem', 'leaf-off'] and
            rights['ownerAuthorizationDate'] == '2026-11-02', 'Source rights record mismatch')
    catalog = load_catalog(root/CATALOG)
    require({k: len(v) for k,v in legacy['sources'].items()} ==
            {'dem':22,'hiking':1,'leaf-off':22,'leaf-on':1}, 'Original source inventory changed')
    inventory = copy.deepcopy(legacy)
    for family, rows in catalog.items():
        original = {s['id']:s for s in legacy['sources'][family]}
        require(set(original) <= {s['id'] for s in rows}, 'Pinned original source omitted')
        merged = []
        for row in rows:
            if row['id'] in original:
                old = original[row['id']]
                require(unquote(old['url']) == unquote(row['url']) and
                        all(abs(a-b)<1e-9 for a,b in zip(old['bbox'],row['bbox'])),
                        'Original source identity or geometry changed')
                merged.append(copy.deepcopy(old))
            else:
                merged.append({**row, 'provider':'KyFromAbove',
                    'expandedNativePolicy':family,
                    'sourceLicense':'Public Domain with Attribution; CC BY for maps',
                    'rightsReference':'RRGH-EXPANDED-SOURCE-RIGHTS-20261102',
                    'attribution':'Kentucky Division of Geographic Information / KyFromAbove; RRGH reprojected derivative.',
                    'catalogSHA256':CATALOG_SHA})
        inventory['sources'][family] = merged
    return inventory


def migration(region, mode='expanded', controller_root=ROOT):
    require(mode in ('expanded','legacy'), 'Unknown production source policy')
    marker = region.get('expandedSourceProduction')
    if marker:
        require(marker['format'] == MARKER and marker['catalogSHA256'] == CATALOG_SHA,
                'Unreviewed inventory migration')
        legacy = region['legacyInventory']
        require(sha(canonical(legacy)) == marker['legacyInventorySHA256'], 'Rollback inventory changed')
    else:
        legacy = copy.deepcopy(region['inventory'])
    expanded = catalog_inventory(legacy,controller_root)
    region['legacyInventory'] = legacy
    region['expandedSourceProduction'] = dict(format=MARKER,catalogSHA256=CATALOG_SHA,
        legacyInventorySHA256=sha(canonical(legacy)),mode=mode,
        nativeValidation='per-object metadata and complete per-window masks',
        allRegionalPixelsVerified=False)
    region['inventory'] = expanded if mode == 'expanded' else copy.deepcopy(legacy)
    region['inventorySHA256'] = sha(canonical(region['inventory']))
    region['regionalPixelCoverageVerified'] = False
    return region


def install_engine(source_root, controller_root=ROOT):
    path = Path(source_root)/ENGINE
    expected = (Path(controller_root)/TEMPLATE).read_bytes()
    require(sha(path.read_bytes()) in (OLD_ENGINE_SHA,sha(expected)), 'Unreviewed renderer predecessor')
    path.write_bytes(expected)


def build_index(region):
    # The credential-bearing publisher must never import production-checkout code.
    # Reconstruct the fixed reviewed geometry entirely in trusted controller code.
    bounds=[-83.8,37.65,-83.4,37.95]
    PROFILES={'core':{'hiking':17,'terrain':17,'usgs-topo':16},
              'leaf-on':{'leaf-on':18},'leaf-off':{'leaf-off':18}}
    require(region['boundsWGS84']==bounds and region['profiles']==PROFILES,
            'Unreviewed geographic bounds or profiles')
    def xy(lon,lat,z):
        n=2**z
        return math.floor((lon+180)/360*n),math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
    def coords(z):
        left,bottom=xy(bounds[0],bounds[1],z);right,top=xy(bounds[2],bounds[3],z)
        return {(x,y) for x in range(left,right+1) for y in range(top,bottom+1)}
    def bbox(z,x,y,halo=0):
        n=2**z
        lon=lambda a:a/n*360-180
        lat=lambda a:math.degrees(math.atan(math.sinh(math.pi*(1-2*a/n))))
        return [lon(x-halo),lat(y+1+halo),lon(x+1+halo),lat(y-halo)]
    def intersects(a,b):
        return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
    grids = {z:coords(z) for z in (16,17,18)}
    index, missing = {}, {}
    for group, layers in PROFILES.items():
        for layer,maxz in layers.items():
            family = 'dem' if layer == 'terrain' else layer
            sources = region['inventory']['sources'].get(family,[])
            gaps = 0
            for x,y in sorted(grids[16]):
                rect = bbox(16,x,y,1/512 if layer == 'terrain' else 0)
                ids = [] if layer == 'usgs-topo' else [s['id'] for s in sources if intersects(s['bbox'],rect)]
                if layer != 'usgs-topo' and not ids:
                    gaps += 1
                    continue
                tiles = []
                for z in range(16,maxz+1):
                    n = 2**(z-16)
                    tiles += [[z,x*n+dx,y*n+dy] for dx in range(n) for dy in range(n)
                              if (x*n+dx,y*n+dy) in grids[z]]
                jid = f'{layer}-16-{x}-{y}'
                index[jid] = dict(id=jid,layer=layer,group=group,z=16,x=x,y=y,
                    operation='usgs-tile' if layer=='usgs-topo' else 'source-window',
                    sourceIDs=ids,dependencies=[],outputTiles=tiles,preservedComplete=False)
            missing[layer] = gaps
    return index,missing


def read_region(folder):
    return json.loads(zlib.decompress(base64.b64decode((Path(folder)/'REGION-PLAN.json.z.b64').read_bytes())))


def validate_publication(source_root, old_dir, new_dir, plan, audit, controller_root=ROOT):
    """Trusted publisher independently reconstructs prospective source selection."""
    root=Path(source_root);old=read_region(old_dir);new=read_region(new_dir)
    mode=audit.get('sourcePolicyMode','expanded')
    expected=migration(copy.deepcopy(old),mode,controller_root)
    for key in ('inventory','inventorySHA256','legacyInventory','expandedSourceProduction'):
        require(new[key]==expected[key], 'Published source expansion differs: '+key)
    require(new['boundsWGS84']==old['boundsWGS84'] and new['profiles']==old['profiles'],
            'Geographic scope or quality profiles changed')
    index,_=build_index(new)
    from rrgh_overview_integration import pilot_job,manifest as pilot_manifest,validate_modules,validate_previous
    validate_modules(root)
    validate_previous(plan,new)
    completion=plan.get('completionPhase') is not None
    if completion:
        from rrgh_completion_phase import validate_plan,lower_usgs_index
        validate_plan(plan,new,audit.get('completionPolicy'))
        index=lower_usgs_index(new)
    native=[j for j in new['jobs'] if j['operation']!='overview']
    overviews=[j for j in new['jobs'] if j['operation']=='overview']
    require(native==[index[j['id']] for j in native], 'Unreviewed source window publication')
    require([j['id'] for j in new['jobs']]==plan['approvedJobIDs'], 'Job ordering differs from plan')
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_phase import validate_plan as validate_crosswave
        validate_crosswave(plan,new,audit.get('crosswavePolicy'))
    require(not overviews or plan.get('crosswavePhase') or (audit.get('overviewPilotEnabled') is True and len(overviews)==1 and
        overviews==[pilot_job(overviews[0]['id'])] and
        plan.get('overviewPilot')==pilot_manifest(overviews[0]['id']) and len(new['jobs'])<=12), 'Unreviewed overview allocation')
    require(bool(overviews)==bool(plan.get('overviewPilot') or plan.get('crosswavePhase')), 'Unused overview authority')
    from rrgh_batch_integration import validate as validate_batch, installed as batch_installed, MODULES as BATCH_MODULES
    old_plan=json.loads((Path(old_dir)/'PLAN.json').read_bytes())
    if plan.get('crosswavePhase',{}).get('format')=='rrgh-crosswave-batch-phase-v2':
        from rrgh_crosswave_batch import validate_history,validate_funding
        validate_history(old_plan,old,plan,audit);validate_funding(old_plan,plan)
    batch=validate_batch(root,old_plan,plan,audit)
    require(not batch or not overviews,'Pair production cannot claim overview work')
    limits={k:(batch['targetJobs']//3 if batch else v) for k,v in LIMITS.items()}
    if completion:limits={'usgs-topo':plan['completionPhase']['authority']['maxJobs']}
    counts={layer:sum(j['layer']==layer for j in native) for layer in limits}
    require(all(n<=limits[layer] for layer,n in counts.items()) and sum(counts.values())==len(native),
            'Expanded allocation exceeds reviewed finite limits')
    # Twelve worst-case 600-second children leave 1800 seconds in the unchanged
    # 9000-second producer slot, even when every window is a consumed pixel gap.
    producer=plan['slots'][1]
    for key in (('sourceBytes','sourceRequests') if batch else ('seconds','sourceBytes','sourceRequests')):
        require(sum(v[key] for v in plan['jobPolicies'].values())<=producer[key],
                'Expanded child reservations exceed producer slot: '+key)
    require((root/ENGINE).read_bytes()==(Path(controller_root)/TEMPLATE).read_bytes(),
            'Renderer differs from reviewed template')
    from rrgh_recovery_catalog_integration import validate as validate_catalog, MODULE as CATALOG_MODULE
    validate_catalog(root,controller_root)
    wanted=copy.deepcopy(old['engineHashes'])
    for name in ('gorge_campaign.py','benchmark_gorge_pipeline.py',CATALOG_MODULE,'run_gorge_checkpoint_slot.py','rrgh_wif_credentials.py','rrgh_overview_pilot.py','rrgh_verified_overview.py','rrgh_crosswave_dependencies.py','rrgh_crosswave_runtime.py','rrgh_crosswave_batch.py','rrgh_typed_child_receipts.py'):
        wanted[name]=sha((root/'backend/scripts'/name).read_bytes())
    if batch_installed(root):
        for name in BATCH_MODULES:wanted[name]=sha((root/'backend/scripts'/name).read_bytes())
    require(new['engineHashes']==wanted, 'Unexpected engine mutation')

