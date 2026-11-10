"""Read immutable accepted output metadata for bounded final package assembly.

No source rendering, object listing, acceptance mutation or implicit credentials.
The caller supplies an already funded Slot and a plan-pinned complete authority.
"""
import copy
import hashlib
import re

from rrgh_package_authority import geometry, require, digest, validate
from rrgh_seed_children import AUTHORITY as SEEDS, inventory as seed_inventory

TILE = re.compile(r'tiles/(hiking|terrain|usgs-topo|leaf-on|leaf-off)/(\d+)/(\d+)/(\d+)\.(jpg|png)\Z')
MAX_TILE = 512*1024
FORMAT = 'rrgh-final-package-inventory-v1'


def bounded(value, prefix, maximum, exact=False):
    from rrgh_verified_tile_catalog import ref
    ref(value)
    require((value['key'] == prefix if exact else value['key'].startswith(prefix)) and
            value['bytes'] <= maximum, 'Package reference exceeds accepted scope')
    return value


def resolve_wave(slot, source):
    from gorge_second_stage import record
    from gorge_campaign import load_large, WAVE011_SALVAGE, WAVE011_PRODUCER
    from rrgh_typed_child_receipts import resolve
    kind = source['acceptanceKind']
    if kind in ('partial-needs-typed-receipt', 'wave289-consumed-recovery'):
        return resolve(slot, source)
    sha = source['sourcePlanSHA256']
    prefix = f'engineering/map-production/plans/{sha}/slots/'
    if kind == 'wave011-salvage':
        require(source['sequence'] == 11 and source['recovery'] == WAVE011_SALVAGE and
                source['sourceJobCount'] == source['expectedTiles'] == 64 and
                all(j.startswith('usgs-topo-16-') for j in source['acceptedJobIDs']),
                'Unreviewed Wave011 acceptance')
        recovered = record(slot, WAVE011_SALVAGE)
        r = recovered['result']
        require(recovered['slot'] == 1 and recovered['planSHA256'] == WAVE011_SALVAGE['key'].split('/')[3] and
                r.get('status') == 'verified' and r.get('sourceWave') == 11 and
                r.get('sourceProducer') == WAVE011_PRODUCER and
                r.get('newlyAcceptedJobs') == r.get('newlyAcceptedTiles') == 64 and
                all(r.get(k) is True for k in ('recoveryOnly','ambiguousFirstLeafOnNotAccepted',
                    'hashesPixelsEdgesSourceLedgersVerified','packageChunksIndependentReadback',
                    'oldWaveProductionNotRepeated')), 'Wave011 independent acceptance changed')
        worker_ref = WAVE011_PRODUCER
        worker = record(slot, worker_ref)
        require(worker['planSHA256'] == sha and worker['slot'] == 1 and
                worker['result']['status'] == 'failed' and worker['result']['jobs'] == 64,
                'Wave011 original failed producer identity changed')
        detail_ref = worker['result']['detailRef']
    else:
        require(kind == 'ordinary', 'Unreviewed acceptance type')
        recovered = record(slot, bounded(source['recovery'],prefix+'00002/receipt.json',16384,True))
        r = recovered['result']
        require(recovered['planSHA256'] == sha and recovered['slot'] == 2 and
                r['status'] == 'verified' and r['jobs'] == source['sourceJobCount'] and
                r['tiles'] == source['expectedTiles'] and
                r['settlement']['sequence'] == source['sequence'] and
                r['settlement']['planSHA256'] == sha and
                r['settlement']['independentRecoveryComplete'] is True and
                all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified',
                    'allNewPackageChunksReadBack','allExistingCachesPreserved')),
                'Incomplete ordinary independent acceptance')
        worker_ref = bounded(r['workerReceipt'],prefix+'00001/receipt.json',16384,True)
        worker = record(slot, worker_ref)
        require(worker['planSHA256'] == sha and worker['slot'] == 1 and
                worker['result']['status'] in ('complete','bounded-stop') and
                worker['result']['detailRef'] == r['detailRef'], 'Accepted producer lineage changed')
        detail_ref = r['detailRef']
    detail = load_large(slot, bounded(detail_ref,prefix+'00001/indexes/',256*1024),limit=256*1024)
    refs = detail['completedJobReceipts']
    expected = {prefix+'00001/jobs/'+j+'.json' for j in source['acceptedJobIDs']}
    require(len(refs) == len(expected) and {r['key'] for r in refs} == expected,
            'Accepted job receipt inventory changed')
    for reference in refs:
        bounded(reference,prefix+'00001/jobs/',64*1024)
    return {r['key']:r for r in refs}


def job_outputs(row, reference, source):
    """Bind every output to its exact accepted job and immutable pack extent."""
    sha = source['sourcePlanSHA256']
    prefix = f'engineering/map-production/plans/{sha}/slots/00001/'
    jid = row['job']
    require(jid in source['acceptedJobIDs'] and row['format'] == 'rrgh-checkpoint-job-v1' and
            row['slot'] == 1 and row['planSHA256'] == sha and
            reference['key'] == prefix+'jobs/'+jid+'.json', 'Foreign checkpoint job')
    receipt = row['result']['originalReceipt']
    require(receipt['job'] == jid and receipt['validated'] is True and
            receipt['recipeSHA256'] == source['recipeSHA256'], 'Accepted renderer recipe changed')
    packed = {}
    for pack in row['result']['outputPacks']:
        bounded(pack['ref'],prefix+'outputs/',64*2**20)
        for member in pack['members']:
            require(member['path'] not in packed, 'Duplicate checkpoint member')
            packed[member['path']] = (member, pack['ref'])
    require(len(receipt['outputs']) == len(packed) and
            {e['path'] for e in receipt['outputs']} == set(packed), 'Checkpoint output set differs')
    output = []
    for entry in receipt['outputs']:
        member, obj = packed[entry['path']]
        require(all(entry[k] == member[k] for k in ('path','bytes','sha256')),
                'Accepted output/member hash changed')
        output.append(dict(output=copy.deepcopy(entry),member=copy.deepcopy(member),object=copy.deepcopy(obj)))
    validate_job(jid, output)
    return output


def validate_job(jid, outputs):
    actual = set()
    for entry in outputs:
        out, member, obj = (entry[k] for k in ('output','member','object'))
        match = TILE.fullmatch(out['path'])
        require(match is not None, 'Invalid raster member path')
        layer, z, x, y, ext = match.groups()
        key = (layer,int(z),int(x),int(y))
        require(key not in actual and out['path'] == f'tiles/{layer}/{int(z)}/{int(x)}/{int(y)}.{ext}',
                'Duplicated or noncanonical raster position')
        actual.add(key)
        require(type(out['bytes']) is int and 0 < out['bytes'] <= MAX_TILE and
                re.fullmatch('[0-9a-f]{64}',out['sha256']) and
                all(member[k] == out[k] for k in ('path','bytes','sha256')) and
                type(member['offset']) is int and 0 <= member['offset'] and
                member['offset']+out['bytes'] <= obj['bytes'], 'Invalid accepted extent')
        from rrgh_verified_tile_catalog import ref
        ref(obj)
    require(actual == geometry(jid), 'Accepted job is missing or adding raster positions')


def read(slot, authority, start=0, stop=None, progress=None):
    """Metadata inventory only; package assembly independently reads all pixels."""
    from gorge_second_stage import record
    validate(authority)
    phase = slot.plan.get('finalPackagePhase',{})
    stop = min(start+96,len(authority['waves'])) if stop is None else stop
    require(type(start) is int and type(stop) is int and 0 <= start < stop <= len(authority['waves']) and
            stop-start <= 96 and phase.get('inventorySlice') == [start,stop] and
            phase.get('authoritySHA256') == digest(authority), 'Exact bounded inventory slice is not plan-pinned')
    objects=[]; object_map={}; files=[]; jobs={}; seen_paths=set()

    def add(jid, entries, proof):
        validate_job(jid,entries)
        require(jid not in jobs, 'Duplicate accepted package job')
        jobs[jid] = copy.deepcopy(proof)
        for entry in entries:
            out,member,obj = (entry[k] for k in ('output','member','object'))
            key = (obj['key'],obj['generation'],obj['sha256'],obj['bytes'])
            if key not in object_map:
                object_map[key] = len(objects); objects.append(copy.deepcopy(obj))
            require(out['path'] not in seen_paths, 'Duplicate final package member')
            seen_paths.add(out['path'])
            files.append(dict(path=out['path'],bytes=out['bytes'],sha256=out['sha256'],
                              job=jid,object=object_map[key],offset=member['offset']))

    seeds = seed_inventory(slot,SEEDS,{}) if start == 0 else {}
    for jid in sorted(seeds):
        entry=seeds[jid]
        add(jid,entry['outputs'],dict(kind=entry['kind'],acceptance=entry['acceptance'],proof=entry['proof']))
    for wave in authority['waves'][start:stop]:
        refs=resolve_wave(slot,wave)
        prefix=f"engineering/map-production/plans/{wave['sourcePlanSHA256']}/slots/00001/jobs/"
        for jid in wave['acceptedJobIDs']:
            reference=refs[prefix+jid+'.json']
            row=record(slot,reference,'rrgh-checkpoint-job-v1')
            add(jid,job_outputs(row,reference,wave),dict(kind=wave['acceptanceKind'],
                acceptance=wave['recovery'],proof=reference))
        if progress:progress(dict(sequence=wave['sequence'],acceptedJobsInventoried=len(jobs),tilesInventoried=len(files)))
    expected={j for wave in authority['waves'][start:stop] for j in wave['acceptedJobIDs']}
    if start == 0:expected.update(SEEDS['jobs'])
    require(set(jobs) == expected and len(files) == sum(len(geometry(j)) for j in expected),
            'Incomplete metadata slice')
    raster_count=len(files)
    # Shared bytes remain the original accepted vector/weather/Sunlight data.
    proof=record(slot,SEEDS['history']['proof'],'rrgh-stage-input-proof-v1') if start == 0 else None
    shared=[e for e in proof['files'] if e['kind']=='shared'] if proof else []
    require((len(shared),sum(e['bytes'] for e in shared)) == ((340,73865407) if start == 0 else (0,0)),
            'Original shared input inventory changed')
    for entry in shared:
        obj=proof['checkpointRefs'][entry['checkpointIndex']]
        from rrgh_verified_tile_catalog import ref
        ref(obj)
        key=(obj['key'],obj['generation'],obj['sha256'],obj['bytes'])
        if key not in object_map:object_map[key]=len(objects);objects.append(copy.deepcopy(obj))
        path='shared/'+entry['path']
        require(path not in seen_paths and entry['offset']>=0 and
                entry['offset']+entry['bytes']<=obj['bytes'], 'Invalid shared input extent')
        seen_paths.add(path)
        files.append(dict(path=path,bytes=entry['bytes'],sha256=entry['sha256'],
                          job=None,object=object_map[key],offset=entry['offset']))
    return dict(format=FORMAT,authoritySHA256=digest(authority),inventorySlice=[start,stop],objects=objects,
        files=sorted(files,key=lambda e:e['path']),jobs=jobs,
        rasterTiles=raster_count,sharedFiles=len(shared),sharedBytes=sum(e['bytes'] for e in shared),
        protectedPixelReadbackPerformed=False,finalPackageDeliveryComplete=False)


def merge(authority, slices):
    """Pure join of exactly the pinned independently retained metadata slices."""
    validate(authority)
    cursor=0;objects=[];object_map={};files=[];jobs={};paths=set()
    raster_count=shared_count=shared_bytes=0
    for value in slices:
        require(value['format']==FORMAT and value['authoritySHA256']==digest(authority) and
                value['protectedPixelReadbackPerformed'] is False and
                value['finalPackageDeliveryComplete'] is False and
                value['inventorySlice'][0]==cursor and
                value['inventorySlice'][1]==min(cursor+96,len(authority['waves'])),
                'Missing, reordered or foreign metadata slice')
        stop=value['inventorySlice'][1]
        expected={j for w in authority['waves'][cursor:stop] for j in w['acceptedJobIDs']}
        if cursor==0:expected.update(SEEDS['jobs'])
        require(set(value['jobs'])==expected and not set(jobs).intersection(expected),
                'Metadata slice accepted jobs differ')
        index={}
        for i,obj in enumerate(value['objects']):
            from rrgh_verified_tile_catalog import ref
            ref(obj);key=(obj['key'],obj['generation'],obj['sha256'],obj['bytes'])
            if key not in object_map:object_map[key]=len(objects);objects.append(copy.deepcopy(obj))
            index[i]=object_map[key]
        groups={j:[] for j in expected};local_shared=[]
        for entry in value['files']:
            require(entry['path'] not in paths and entry['object'] in index,'Duplicate package path or missing object')
            paths.add(entry['path'])
            out={k:entry[k] for k in ('path','bytes','sha256')}
            if entry['job'] is not None:
                require(entry['job'] in groups,'Foreign metadata job')
                groups[entry['job']].append(dict(output=out,member=dict(out,offset=entry['offset']),
                    object=value['objects'][entry['object']]))
            else:
                from build_gorge_map_bundles import safe_path
                safe_path(entry['path'])
                require(cursor==0 and entry['path'].startswith('shared/') and type(entry['bytes']) is int and
                        entry['bytes']>0 and re.fullmatch('[0-9a-f]{64}',entry['sha256']) and
                        type(entry['offset']) is int and entry['offset']>=0 and
                        entry['offset']+entry['bytes']<=value['objects'][entry['object']]['bytes'],
                        'Foreign or invalid shared input')
                local_shared.append(entry)
            files.append(dict(entry,object=index[entry['object']]))
        for jid,entries in groups.items():validate_job(jid,entries)
        tiles=sum(len(es) for es in groups.values())
        require(tiles==value['rasterTiles'] and len(local_shared)==value['sharedFiles'] and
                sum(e['bytes'] for e in local_shared)==value['sharedBytes'], 'Slice totals differ')
        raster_count+=tiles;shared_count+=len(local_shared);shared_bytes+=value['sharedBytes']
        jobs.update(copy.deepcopy(value['jobs']));cursor=stop
    require(cursor==len(authority['waves']) and set(jobs)==set(authority['acceptedJobs']) and
            (raster_count,shared_count,shared_bytes)==(278278,340,73865407),
            'Final metadata inventory incomplete')
    return dict(format=FORMAT,authoritySHA256=digest(authority),inventorySlice=[0,cursor],
        objects=objects,files=sorted(files,key=lambda e:e['path']),jobs=jobs,
        rasterTiles=raster_count,sharedFiles=shared_count,sharedBytes=shared_bytes,
        protectedPixelReadbackPerformed=False,finalPackageDeliveryComplete=False)
