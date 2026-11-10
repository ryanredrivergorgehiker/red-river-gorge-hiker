"""Complete accepted-job lineage for final packages, without any Cloud operation.

The overview dependency index intentionally excluded completed USGS work. Final
packages include every layer, the explicit original seeds and all salvage types.
No consumed attempt is promoted to acceptance by this metadata-only adapter.
"""
import base64
import copy
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import zlib

from rrgh_crosswave_batch import original_index, SOURCE_KEYS
from rrgh_seed_children import AUTHORITY as SEEDS, AUTHORITY_SHA as SEED_SHA
from rrgh_overview_coverage import BOUNDS

PROFILE = {'hiking':17, 'terrain':17, 'usgs-topo':16, 'leaf-on':18, 'leaf-off':18}
RASTER_COUNT = 278278
JOB_COUNT = 34750
FORMAT = 'rrgh-final-package-acceptance-authority-v1'


def canonical(v):
    return (json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(v):
    return hashlib.sha256(canonical(v)).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


@lru_cache(maxsize=9)
def grid(z):
    require(type(z) is int and 10 <= z <= 18, 'Unsupported package zoom')
    def xy(lon, lat):
        n = 2**z
        return (math.floor((lon+180)/360*n),
                math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n))
    left, bottom = xy(BOUNDS[0], BOUNDS[1])
    right, top = xy(BOUNDS[2], BOUNDS[3])
    return left, top, right, bottom


def inside(z, x, y):
    left, top, right, bottom = grid(z)
    return left <= x <= right and top <= y <= bottom


def geometry(jid):
    layer, z, x, y = jid.rsplit('-', 3)
    z, x, y = map(int, (z, x, y))
    require(layer in PROFILE and 10 <= z <= 16 and inside(z, x, y),
            'Unexpected accepted job identity')
    require(jid == f'{layer}-{z}-{x}-{y}', 'Noncanonical accepted job identity')
    levels = range(16, PROFILE[layer]+1) if z == 16 else [z]
    result = set()
    for zz in levels:
        scale = 2**(zz-z)
        result.update((layer, zz, xx, yy)
                      for xx in range(x*scale, (x+1)*scale)
                      for yy in range(y*scale, (y+1)*scale)
                      if inside(zz, xx, yy))
    return result


def required_jobs():
    result = set()
    for layer in PROFILE:
        for z in range(10, 17):
            left, top, right, bottom = grid(z)
            result.update(f'{layer}-{z}-{x}-{y}'
                          for x in range(left, right+1)
                          for y in range(top, bottom+1))
    require(len(result) == JOB_COUNT, 'Fixed regional job denominator changed')
    return result


def read_plan(source, sequence, plan_sha=None):
    candidates = []
    for path in sorted((Path(source)/'backend/config').glob(f'gorge-campaign-wave-{sequence:03d}-*/PLAN.json')):
        plan = json.loads(path.read_bytes())
        if plan['campaign']['sequence'] == sequence and (plan_sha is None or digest(plan) == plan_sha):
            candidates.append((path.parent, plan))
    require(len(candidates) == 1, 'Missing or ambiguous exact historical plan')
    return candidates[0]


def historical_usgs(source):
    """Walk the actual 1357 predecessor chain to the frozen 1322 boundary."""
    from rrgh_completion_phase import lower_usgs_index, BOUNDS
    directory, next_plan = read_plan(source, 1357)
    expected = set(lower_usgs_index({'boundsWGS84':BOUNDS, 'profiles':{'core':{'usgs-topo':16}}}))
    require(expected <= set(next_plan['completedJobIDs']), 'USGS completion boundary is absent')
    remaining = set(expected)
    waves = []
    for sequence in range(1356, 1322, -1):
        recovery = next_plan['campaign']['previousRecovery']
        plan_sha = recovery['key'].split('/')[3]
        directory, plan = read_plan(source, sequence, plan_sha)
        require(recovery['key'] == f'engineering/map-production/plans/{plan_sha}/slots/00002/receipt.json',
                'USGS acceptance requires its original independent receipt')
        before = set(plan['completedJobIDs'])
        after = set(next_plan['completedJobIDs'])
        require(before <= after, 'Historical accepted jobs removed')
        delta = after-before
        require(delta <= remaining and delta <= set(plan['approvedJobIDs']),
                'Unaccepted or duplicate USGS completion work')
        dec = zlib.decompressobj()
        raw = dec.decompress(base64.b64decode((directory/'REGION-PLAN.json.z.b64').read_bytes()), 8*2**20)
        require(dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'USGS region bound exceeded')
        region = json.loads(raw)
        require(digest(region) == plan['regionPlanSHA256'] and
                {j['id'] for j in region['jobs']} == set(plan['approvedJobIDs']),
                'Historical USGS rendering scope changed')
        jobs = {j['id']:j for j in region['jobs']}
        require(all(jobs[j]['operation'] == 'usgs-tile' and
                    {('usgs-topo', *t) for t in jobs[j]['outputTiles']} == geometry(j) for j in delta),
                'USGS original-zoom output geometry changed')
        if delta:
            waves.append(dict(sequence=sequence, sourcePlanSHA256=plan_sha,
                recovery=copy.deepcopy(recovery),
                recipeSHA256=hashlib.sha256((json.dumps(region,sort_keys=True,indent=2)+'\n').encode()).hexdigest(),
                acceptedJobIDs=sorted(delta), sourceJobCount=len(delta), expectedTiles=len(delta),
                acceptanceKind='ordinary' if delta == set(plan['approvedJobIDs']) else 'partial-needs-typed-receipt'))
        remaining -= delta
        next_plan = plan
    require(not remaining and sum(w['sourceJobCount'] for w in waves) == 1770,
            'Missing USGS original-zoom acceptance')
    require(next_plan['campaign']['previousRecovery'] == original_index()['waves'][0]['recovery'],
            'USGS chain is detached from the original acceptance boundary')
    return waves


def build(source, accepted, crosswave, native, final, final_recovery):
    """Construct scope only; real immutable metadata/bytes must be verified later."""
    require(len(accepted) == len(set(accepted)) and set(accepted) == required_jobs(),
            'Every required regional job must be independently accepted')
    waves = copy.deepcopy(original_index()['waves']) + historical_usgs(source)
    waves += [dict({k:copy.deepcopy(w[k]) for k in SOURCE_KEYS},
                   acceptanceKind=w.get('acceptanceKind', 'ordinary')) for w in crosswave]
    for w in native:
        require(w['acceptanceKind'] == 'ordinary' and not w['pixelGapJobIDs'] and
                w['attemptedJobIDs'] == w['acceptedJobIDs'], 'Unresolved native repair remains')
        waves.append(dict(sequence=w['sequence'], sourcePlanSHA256=w['planSHA256'],
            recovery=copy.deepcopy(w['recoveryReceipt']), recipeSHA256=w['recipeSHA256'],
            sourceJobCount=w['sourceJobCount'], expectedTiles=w['expectedTiles'],
            acceptedJobIDs=copy.deepcopy(w['acceptedJobIDs']), acceptanceKind='ordinary'))
    waves += [dict({k:copy.deepcopy(w[k]) for k in SOURCE_KEYS}, acceptanceKind='ordinary') for w in final]
    waves = [{k:copy.deepcopy(w[k]) for k in (*SOURCE_KEYS, 'acceptanceKind')}
             for w in waves if w['sourceJobCount']]
    require(final and final[-1]['recovery'] == final_recovery, 'Exact final independent acceptance required')
    authority = dict(format=FORMAT, seedAuthoritySHA256=SEED_SHA,
        finalRecovery=copy.deepcopy(final_recovery), waves=sorted(waves, key=lambda w:w['sequence']),
        acceptedJobs=sorted(accepted), rasterTiles=RASTER_COUNT,
        protectedByteReadbackPerformed=False, finalPackageDeliveryComplete=False)
    validate(authority)
    return authority


def validate(authority):
    require(authority['format'] == FORMAT and authority['seedAuthoritySHA256'] == SEED_SHA and
            authority['rasterTiles'] == RASTER_COUNT and
            authority['protectedByteReadbackPerformed'] is False and
            authority['finalPackageDeliveryComplete'] is False, 'Package authority changed')
    all_jobs = set(SEEDS['jobs'])
    tile_count = sum(len(geometry(j)) for j in all_jobs)
    require(tile_count == 436, 'Accepted seed geometry changed')
    plans = set()
    for w in authority['waves']:
        jobs = w['acceptedJobIDs']
        require(w['acceptanceKind'] in ('ordinary', 'partial-needs-typed-receipt',
                'wave289-consumed-recovery', 'wave011-salvage') and
                w['sourcePlanSHA256'] not in plans and
                0 < len(jobs) == len(set(jobs)) == w['sourceJobCount'] <= 512 and
                not all_jobs.intersection(jobs), 'Duplicated or unreviewed accepted source')
        tiles = sum(len(geometry(j)) for j in jobs)
        require(tiles == w['expectedTiles'], 'Accepted wave geometry/count mismatch')
        tile_count += tiles
        plans.add(w['sourcePlanSHA256'])
        all_jobs.update(jobs)
    require(all_jobs == required_jobs() == set(authority['acceptedJobs']) and
            len(authority['acceptedJobs']) == JOB_COUNT and tile_count == RASTER_COUNT,
            'Final accepted inventory has a gap or duplicate')
    return dict(acceptedJobs=JOB_COUNT, rasterTiles=tile_count,
                sourceWaves=len(plans), seedJobs=len(SEEDS['jobs']))
