"""One exact overview from four independently accepted immutable child tiles.

No official source request. Existing output objects are read by generation and
hash. The current finite allocation pays for all reads and the fresh parent.
"""
import copy
import json
from pathlib import Path


def require(ok,message):
    if not ok:raise ValueError(message)


def job_for(m):
    return dict(id=m['job'],layer=m['layer'],z=m['z'],x=m['x'],y=m['y'],
                operation='overview',sourceIDs=[],outputTiles=[[m['z'],m['x'],m['y']]])


def validate_scope(plan,region,job):
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_runtime import scope as crosswave
        return crosswave(plan,region,job)
    m=plan.get('overviewPilot')
    require(isinstance(m,dict) and m.get('format')=='rrgh-verified-child-overview-pilot-v1' and
            job==job_for(m) and job['layer']=='leaf-on' and job['z']==15 and
            region['boundsWGS84']==m['boundsWGS84'],'Exact overview scope changed')
    require(job['id'] in plan['approvedJobIDs'] and job['id'] not in plan['completedJobIDs'] and
            plan['priorAttemptCounts'].get(job['id'],0)==0 and
            plan['jobPolicies'][job['id']]==dict(seconds=600,sourceBytes=0,sourceRequests=0),
            'Overview attempt or zero-source boundary changed')
    expected=[f"leaf-on-16-{2*job['x']+dx}-{2*job['y']+dy}" for dx in range(2) for dy in range(2)]
    require(m['children']==expected and set(expected)<=set(plan['completedJobIDs']),
            'Four accepted child jobs required')
    require(sum(j['operation']=='overview' for j in region['jobs'])==1,'Only one overview pilot allowed')
    return m


def read_dependencies(slot,plan,region,destination):
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_runtime import read_dependencies as crosswave
        return crosswave(slot,plan,region,destination)
    from gorge_checkpoint import Ref,digest
    from gorge_campaign import load_large
    from gorge_second_stage import record,recover_catalogs
    from PIL import Image,ImageStat
    m=plan.get('overviewPilot')
    if m is None:return None
    job=next(j for j in region['jobs'] if j['id']==m['job']);validate_scope(plan,region,job)
    from orchestrate_gorge_region import tile_coords
    coords=set(tile_coords(16))
    require(all(tuple(map(int,j.rsplit('-',2)[1:])) in coords for j in m['children']),
            'Boundary overview with missing required children refused')
    prior=record(slot,m['recovery'])
    r=prior['result'];prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
    require(m['recovery']['key']==prefix+'slots/00002/receipt.json' and
            prior['planSHA256']==m['sourcePlanSHA256'] and prior['slot']==2 and
            r['status']=='verified' and r['jobs']==m['sourceJobCount'] and
            r['settlement']['sequence']==m['sourceSequence'] and
            r['settlement']['independentRecoveryComplete'] is True and
            all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified','allNewPackageChunksReadBack','allExistingCachesPreserved')),
            'Child source wave lacks complete independent acceptance')
    worker=record(slot,r['workerReceipt'])
    require(worker['planSHA256']==m['sourcePlanSHA256'] and worker['slot']==1 and
            worker['result']['detailRef']==r['detailRef'] and worker['result']['status']=='complete',
            'Original accepted worker changed')
    details=load_large(slot,r['detailRef'])
    refs={entry['key']:entry for entry in details['completedJobReceipts']}
    require(len(refs)==len(details['completedJobReceipts'])==m['sourceJobCount'],'Original accepted checkpoint inventory changed')
    children=[]
    for child_job in m['children']:
        key=prefix+'slots/00001/jobs/'+child_job+'.json'
        require(key in refs,'Missing accepted child checkpoint')
        reference=refs[key];row=record(slot,reference,'rrgh-checkpoint-job-v1');receipt=row['result']['originalReceipt']
        require(row['job']==receipt['job']==child_job and row['slot']==1 and row['planSHA256']==m['sourcePlanSHA256'] and
                receipt['validated'] is True and receipt['recipeSHA256']==m['sourceRecipeSHA256'],
                'Original child rendering recipe changed')
        x,y=map(int,child_job.rsplit('-',2)[1:]);base=f'tiles/leaf-on/16/{x}/{y}.'
        outputs=[e for e in receipt['outputs'] if e['path'].startswith(base)]
        require(len(outputs)==1 and outputs[0]['path'].rsplit('.',1)[-1] in ('jpg','png'),'One native child tile required')
        out=outputs[0];packs=row['result']['outputPacks']
        members=[(p,e) for p in packs for e in p['members'] if e['path']==out['path']]
        require(len(members)==1,'Child checkpoint member ambiguous')
        pack,entry=members[0]
        require(all(entry[k]==out[k] for k in ('path','bytes','sha256')),'Child output/pack mismatch')
        # The checkpoint reader atomically publishes into a NEW directory.
        # Bootstrap already created the worker directory, and four children
        # cannot each recover into the same destination. Keep each immutable
        # range read separate, then exclusively publish its verified tile.
        recovered=Path(destination)/('overview-readback-'+child_job)
        recover_catalogs(slot,[pack],[out['path']],recovered)
        raw=(recovered/out['path']).read_bytes()
        require(len(raw)==out['bytes'] and digest(raw)==out['sha256'],'Child byte readback mismatch')
        with Image.open(recovered/out['path']) as image:
            image.load();require(image.size==(256,256) and
                (image.mode!='RGBA' or image.getextrema()[3]==(255,255)) and
                max(ImageStat.Stat(image.convert('RGB')).stddev)>=0.1,'Incomplete child pixels')
        target=Path(destination)/out['path'];target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        children.append(dict(tile=['leaf-on',16,x,y],path=out['path'],bytes=out['bytes'],sha256=out['sha256'],
            job=child_job,jobReceipt=reference,checkpointObject=pack['ref'],checkpointOffset=entry['offset'],
            pixelReadbackVerified=True))
    return dict(format='rrgh-overview-dependency-proof-v1',job=m['job'],
        originalIndependentRecovery=m['recovery'],sourceRecipeSHA256=m['sourceRecipeSHA256'],children=children,
        officialSourceRequests=0,priorChildrenUnmodified=True)


def attach_proof(plan,region,receipt,initial):
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_runtime import attach_proof as crosswave
        return crosswave(plan,region,receipt,initial)
    job=next(j for j in region['jobs'] if j['id']==receipt['job'])
    if job['operation']!='overview':return receipt
    m=validate_scope(plan,region,job);proof=initial.get('overviewPilot')
    require(proof and proof['job']==m['job'] and len(proof['children'])==4,'Bootstrap child proof missing')
    usage=receipt['execution']['sourceUsage']
    require(receipt['sourceEvidence']==[] and usage['actual']['operations']==0 and
            usage['actual']['receivedBodyBytes']==0 and usage['reserved']['sourceRequests']==0 and
            usage['reserved']['sourceBytes']==0,'Overview contacted an official source')
    receipt['overviewProof']=copy.deepcopy(proof)
    return receipt


def verify(slot,plan,region,records,root,source_root):
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_runtime import verify as crosswave
        return crosswave(slot,plan,region,records,root,source_root)
    m=plan.get('overviewPilot')
    if m is None:return None
    selected=[r for r in records if r['job']==m['job']]
    require(len(selected)==1,'Overview pilot is not independently complete')
    original=selected[0]['result']['originalReceipt'];root=Path(root)
    proof=read_dependencies(slot,plan,region,root/'overview-children')
    require(original.get('overviewProof')==proof,'Producer and fresh-runner child evidence differ')
    from rrgh_verified_overview import render
    job=next(j for j in region['jobs'] if j['id']==m['job'])
    recomputed=render(region,job,proof['children'],root/'overview-children',root/'overview-independent',source_root)
    require(recomputed['receipt']['outputs']==original['outputs'],'Independent overview recomputation differs')
    return dict(job=m['job'],fourChildrenHashAndPixelVerified=True,independentParentRecomputationMatches=True,
        officialSourceRequests=0,childProof=proof,sourceQualityUnchanged=True)
