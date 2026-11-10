"""Read every required final child with exact edge coverage and typed seed proofs.

This helper is not enrolled in production. Its caller must independently bind
the manifest to reviewed acceptance history and a fresh funded plan. It never
lists objects, writes Cloud objects, calls a source service or accepts a parent.
Special salvage/partial namespaces remain explicitly unsupported here.
"""
import copy
from pathlib import Path
import re

LAYERS=('hiking','terrain','leaf-on','leaf-off')
FORMAT='rrgh-final-overview-dependencies-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def child_ids(job):
    from rrgh_final_overviews import children
    return children(job)


def read(slot,job,binding,accepted,destination,wave_cache=None):
    from gorge_checkpoint import Ref,digest
    from gorge_second_stage import record,recover_catalogs
    from gorge_campaign import load_large
    from rrgh_verified_tile_catalog import ref as validate_ref
    from orchestrate_gorge_region import tile_coords
    from PIL import Image,ImageStat
    from rrgh_overview_coverage import verify as verify_coverage
    wanted=child_ids(job)
    require(binding.get('format')==FORMAT and binding.get('job')==job and
        [c.get('job') for c in binding['children']]==wanted and
        set(wanted)<=set(accepted),'Reviewed dependency binding changed')
    allowed=set(tile_coords(job['z']+1))
    require(all(tuple(map(int,j.rsplit('-',2)[1:])) in allowed for j in wanted),
        'Boundary children need a separately verified edge policy')
    destination=Path(destination)
    require(not destination.exists(),'Fresh dependency destination required')
    destination.mkdir(parents=True,mode=0o700)
    waves={} if wave_cache is None else wave_cache;children=[];used_waves=set()

    def bounded_ref(value,prefix,limit):
        validate_ref(value)
        require(value['key'].startswith(prefix) and value['bytes']<=limit,'Dependency reference scope/size changed')
        return value

    for child in binding['children']:
        jid=child['job'];source=child['source']
        if source.get('acceptanceKind')=='accepted-seed-authority-v1':
            from rrgh_seed_children import AUTHORITY,AUTHORITY_SHA,read as read_seed
            require(source==dict(acceptanceKind='accepted-seed-authority-v1',authoritySHA256=AUTHORITY_SHA),
                'Unreviewed accepted seed authority')
            private=destination/('seed-readback-'+jid)
            proof=read_seed(slot,AUTHORITY,jid,private,waves)
            raw=(private/proof['path']).read_bytes();target=destination/proof['path']
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(raw)
            children.append(proof);used_waves.add('seed:'+AUTHORITY_SHA)
            continue
        sha=source['sourcePlanSHA256'];used_waves.add(sha)
        require(re.fullmatch('[0-9a-f]{64}',sha) is not None and
            type(source['sequence']) is int and source['sequence']>0 and
            type(source['sourceJobCount']) is int and 0<source['sourceJobCount']<=512 and
            len(set(source['acceptedJobIDs']))==len(source['acceptedJobIDs'])==source['sourceJobCount'] and
            jid in source['acceptedJobIDs'] and re.fullmatch('[0-9a-f]{64}',source['recipeSHA256']) is not None,
            'Malformed child acceptance authority')
        prefix='engineering/map-production/plans/'+sha+'/slots/'
        recovery=source['recovery']
        typed=source.get('acceptanceKind') is not None
        if not typed:
            bounded_ref(recovery,prefix+'00002/receipt.json',16384)
            require(recovery['key']==prefix+'00002/receipt.json','Ordinary independent recovery required')
        if sha in waves:
            prior_source,refs=waves[sha]
            require(prior_source==source,'Conflicting acceptance pins for one wave')
        elif typed:
            from rrgh_typed_child_receipts import resolve
            refs=resolve(slot,source)
            waves[sha]=(copy.deepcopy(source),refs)
        else:
            prior=record(slot,recovery);r=prior['result'];settlement=r['settlement']
            require(prior['planSHA256']==sha and prior['slot']==2 and r['status']=='verified' and
                r['jobs']==source['sourceJobCount'] and r['tiles']==source['expectedTiles'] and
                settlement['sequence']==source['sequence'] and settlement['planSHA256']==sha and
                settlement['independentRecoveryComplete'] is True and
                all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified',
                    'allNewPackageChunksReadBack','allExistingCachesPreserved')),
                'Child wave lacks complete independent acceptance')
            worker_ref=bounded_ref(r['workerReceipt'],prefix+'00001/receipt.json',16384)
            require(worker_ref['key']==prefix+'00001/receipt.json','Original worker receipt required')
            worker=record(slot,worker_ref)
            require(worker['planSHA256']==sha and worker['slot']==1 and worker['result']['status']=='complete' and
                worker['result']['detailRef']==r['detailRef'],'Accepted producer lineage changed')
            detail_ref=bounded_ref(r['detailRef'],prefix+'00001/indexes/',256*1024)
            detail=load_large(slot,detail_ref,limit=256*1024)
            refs={v['key']:v for v in detail['completedJobReceipts']}
            expected={prefix+'00001/jobs/'+j+'.json' for j in source['acceptedJobIDs']}
            require(len(refs)==len(detail['completedJobReceipts'])==source['sourceJobCount'] and set(refs)==expected,
                'Accepted checkpoint inventory changed')
            waves[sha]=(copy.deepcopy(source),refs)
        job_key=prefix+'00001/jobs/'+jid+'.json'
        reference=bounded_ref(refs[job_key],job_key,64*1024)
        require(reference['key']==job_key,'Exact child checkpoint required')
        row=record(slot,reference,'rrgh-checkpoint-job-v1');receipt=row['result']['originalReceipt']
        require(row['job']==receipt['job']==jid and row['slot']==1 and row['planSHA256']==sha and
            receipt['validated'] is True and receipt['recipeSHA256']==source['recipeSHA256'],
            'Accepted child renderer/recipe changed')
        layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y))
        names={f'tiles/{layer}/{z}/{x}/{y}.{ext}' for ext in ('jpg','png')}
        outputs=[v for v in receipt['outputs'] if v['path'] in names]
        require(len(outputs)==1,'Exactly one child position required')
        out=outputs[0]
        require(type(out['bytes']) is int and 0<out['bytes']<=512*1024,'Child tile size exceeds original envelope')
        matches=[(p,e) for p in row['result']['outputPacks'] for e in p['members'] if e['path']==out['path']]
        require(len(matches)==1,'Ambiguous child output member')
        pack,entry=matches[0]
        bounded_ref(pack['ref'],prefix+'00001/outputs/',64*2**20)
        require(all(entry[k]==out[k] for k in ('path','bytes','sha256')),'Child output/member identity differs')
        recovered=destination/('readback-'+jid)
        recover_catalogs(slot,[pack],[out['path']],recovered)
        raw=(recovered/out['path']).read_bytes()
        require(len(raw)==out['bytes'] and digest(raw)==out['sha256'],'Child bytes changed')
        with Image.open(recovered/out['path']) as im:
            im.load()
            coverage=verify_coverage(im,z,x,y)
            require(max(ImageStat.Stat(im.convert('RGB')).stddev)>=0.1,'Child pixels incomplete')
        target=destination/out['path'];target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        children.append(dict(tile=[layer,z,x,y],path=out['path'],bytes=out['bytes'],sha256=out['sha256'],
            job=jid,jobReceipt=reference,checkpointObject=pack['ref'],checkpointOffset=entry['offset'],
            pixelReadbackVerified=True,coverage=coverage,independentRecovery=recovery,sourceRecipeSHA256=source['recipeSHA256']))
    return dict(format=FORMAT,job=job['id'],children=children,sourceWaves=len(used_waves),
        officialSourceRequests=0,priorChildrenUnmodified=True,productionAccepted=False)
