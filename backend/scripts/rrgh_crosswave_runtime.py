"""Production bootstrap and independent recomputation of the exact four parents."""
import copy
import hashlib
import json
from pathlib import Path

# Filled from the already acquired immutable four-layer binding by the build.
PHASE_SHA='53b5b36c4104d154a6e3826e862c047cd3754e85752f05a4a141708d19bcd0f3'
JOB_POLICY=dict(seconds=600,sourceBytes=0,sourceRequests=0)


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def scope(plan,region,job=None):
    p=plan.get('crosswavePhase')
    if isinstance(p,dict) and p.get('format')=='rrgh-crosswave-batch-phase-v2':
        from rrgh_crosswave_batch import scope as batch
        return batch(plan,region,job)
    require(isinstance(p,dict) and hashlib.sha256(canonical(p)).hexdigest()==PHASE_SHA,
        'Exact immutable cross-wave phase changed')
    jobs=[b['job'] for b in p['bindings']]
    require(region['jobs']==jobs and region['boundsWGS84']==[-83.8,37.65,-83.4,37.95] and
        plan['approvedJobIDs']==[j['id'] for j in jobs] and plan.get('overviewPilot') is None and
        plan.get('completionPhase') is None and not plan.get('resumableBatch') and
        all(j['id'] not in plan['completedJobIDs'] and plan['priorAttemptCounts'].get(j['id'],0)==0
            and plan['jobPolicies'].get(j['id'])==JOB_POLICY for j in jobs),
        'Cross-wave job scope or fresh attempt changed')
    from rrgh_crosswave_dependencies import child_ids
    require(all(set(child_ids(j))<=set(plan['completedJobIDs']) for j in jobs),'Missing accepted child')
    if job is not None:require(job in jobs,'Unallocated overview')
    return p


def read_dependencies(slot,plan,region,destination):
    from rrgh_crosswave_dependencies import read
    p=scope(plan,region);destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    proofs=[];wave_cache={}
    for binding in p['bindings']:
        job=binding['job'];private=destination/('crosswave-readback-'+job['id'])
        proof=read(slot,job,binding,plan['completedJobIDs'],private,wave_cache)
        for child in proof['children']:
            raw=(private/child['path']).read_bytes();target=destination/child['path']
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():require(not target.is_symlink() and target.read_bytes()==raw,'Child collision')
            else:
                with target.open('xb') as stream:stream.write(raw)
        proofs.append(proof)
    return dict(format='rrgh-crosswave-bootstrap-proof-v1',phaseSHA256=hashlib.sha256(canonical(plan['crosswavePhase'])).hexdigest(),proofs=proofs)


def attach_proof(plan,region,receipt,initial):
    job=next(j for j in region['jobs'] if j['id']==receipt['job']);scope(plan,region,job)
    initial=initial.get('overviewPilot') or {}
    require(initial.get('format')=='rrgh-crosswave-bootstrap-proof-v1' and
        initial.get('phaseSHA256')==hashlib.sha256(canonical(plan['crosswavePhase'])).hexdigest(),'Verified bootstrap dependencies missing')
    selected=[p for p in initial['proofs'] if p['job']==job['id']]
    require(len(selected)==1,'Exact child proof missing')
    usage=receipt['execution']['sourceUsage']
    require(receipt['sourceEvidence']==[] and usage['actual']['operations']==0 and
        usage['actual']['receivedBodyBytes']==0 and usage['reserved']['sourceRequests']==0 and
        usage['reserved']['sourceBytes']==0,'Overview contacted an official source')
    receipt['overviewProof']=copy.deepcopy(selected[0]);return receipt


def verify(slot,plan,region,records,root,source_root):
    p=scope(plan,region);root=Path(root);childroot=root/'crosswave-independent-children'
    require(not childroot.exists(),'Fresh independent child readback required')
    bootstrap=read_dependencies(slot,plan,region,childroot)
    from rrgh_verified_overview import render
    results=[]
    for binding,proof in zip(p['bindings'],bootstrap['proofs'],strict=True):
        job=binding['job'];selected=[r for r in records if r['job']==job['id']]
        require(len(selected)==1,'Overview has no complete independent checkpoint')
        original=selected[0]['result']['originalReceipt']
        require(original.get('overviewProof')==proof,'Producer and independent child evidence differ')
        result=render(region,job,proof['children'],childroot,root/('recomputed-'+job['id']),source_root)
        require(result['receipt']['outputs']==original['outputs'],'Independent parent pixels/hash differ')
        results.append(dict(job=job['id'],fourChildrenHashAndPixelVerified=True,
            independentParentRecomputationMatches=True,officialSourceRequests=0,
            sourceQualityUnchanged=True,childProof=proof))
    if plan['crosswavePhase'].get('format')=='rrgh-crosswave-batch-phase-v2':
        from rrgh_crosswave_batch import digest,VERIFY
        from gorge_campaign import save_large
        detail=dict(format='rrgh-crosswave-independent-detail-v2',phaseSHA256=digest(plan['crosswavePhase']),
            planSHA256=digest(plan),bindings=copy.deepcopy(p['bindings']),parents=results)
        reference=save_large(slot,detail,limit=4*2**20)
        summary=[]
        for record in records:
            out=record['result']['originalReceipt']['outputs']
            require(len(out)==1,'One exact overview output required')
            summary.append(dict(job=record['job'],outputSHA256=out[0]['sha256'],outputBytes=out[0]['bytes']))
        return dict(format=VERIFY,phaseSHA256=detail['phaseSHA256'],planSHA256=detail['planSHA256'],
            allChildrenHashAndPixelVerified=True,allParentsIndependentlyRecomputed=True,
            priorChildrenUnmodified=True,sourceQualityUnchanged=True,officialSourceRequests=0,
            parents=summary,detailRef=reference,detailSHA256=digest(detail))
    return dict(format='rrgh-crosswave-verification-v1',phaseSHA256=PHASE_SHA,
        bindings=copy.deepcopy(p['bindings']),parents=results)


def validate_verification(value):
    from rrgh_verified_tile_catalog import ref
    from rrgh_crosswave_dependencies import child_ids,FORMAT
    require(isinstance(value,dict) and value.get('format')=='rrgh-crosswave-verification-v1' and
        value.get('phaseSHA256')==PHASE_SHA,'Missing independent cross-wave verification')
    # Audit receives the binding in the closed recovery receipt, and matches the
    # entire exact phase hash, including owner authority and every historical pin.
    from rrgh_crosswave_phase import POLICY
    p=dict(format='rrgh-crosswave-pilot-phase-v1',authority=POLICY,bindings=value['bindings'])
    require(hashlib.sha256(canonical(p)).hexdigest()==PHASE_SHA,'Audited child authority changed')
    require(len(value['parents'])==len(value['bindings'])==4,'All four layers must verify')
    for binding,parent in zip(value['bindings'],value['parents'],strict=True):
        job=binding['job'];ids=child_ids(job);proof=parent.get('childProof',{})
        require(parent.get('job')==job['id'] and all(parent.get(k) is True for k in
            ('fourChildrenHashAndPixelVerified','independentParentRecomputationMatches','sourceQualityUnchanged'))
            and parent.get('officialSourceRequests')==0 and proof.get('format')==FORMAT and
            proof.get('job')==job['id'] and proof.get('officialSourceRequests')==0 and
            proof.get('priorChildrenUnmodified') is True and
            [c.get('job') for c in proof.get('children',[])]==ids,'Incomplete four-child verification')
        for child,bound in zip(proof['children'],binding['children'],strict=True):
            source=bound['source'];prefix='engineering/map-production/plans/'+source['sourcePlanSHA256']+'/slots/00001/'
            layer,z,x,y=child['job'].rsplit('-',3);z,x,y=map(int,(z,x,y))
            obj=ref(child['checkpointObject']);jr=ref(child['jobReceipt'])
            require(child['tile']==[layer,z,x,y] and child['path'] in
                (f'tiles/{layer}/{z}/{x}/{y}.png',f'tiles/{layer}/{z}/{x}/{y}.jpg') and
                child.get('pixelReadbackVerified') is True and child['independentRecovery']==source['recovery'] and
                child['sourceRecipeSHA256']==source['recipeSHA256'] and jr['key']==prefix+'jobs/'+child['job']+'.json' and
                obj['key'].startswith(prefix+'outputs/') and type(child['bytes']) is int and 0<child['bytes']<=512*1024 and
                type(child['checkpointOffset']) is int and 0<=child['checkpointOffset'] and
                child['checkpointOffset']+child['bytes']<=obj['bytes'] and len(child['sha256'])==64 and
                all(c in '0123456789abcdef' for c in child['sha256']),'Child lineage or byte range changed')
    return value
