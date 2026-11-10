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
    from rrgh_final_overviews import scope as final_scope
    return final_scope(plan,region,job)


def read_dependencies(slot,plan,region,destination):
    from rrgh_final_dependencies import read
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
    return dict(format='rrgh-final-overview-bootstrap-proof-v1',phaseSHA256=hashlib.sha256(canonical(plan['finalOverviewPhase'])).hexdigest(),proofs=proofs)


def attach_proof(plan,region,receipt,initial):
    job=next(j for j in region['jobs'] if j['id']==receipt['job']);scope(plan,region,job)
    initial=initial.get('overviewPilot') or {}
    require(initial.get('format')=='rrgh-final-overview-bootstrap-proof-v1' and
        initial.get('phaseSHA256')==hashlib.sha256(canonical(plan['finalOverviewPhase'])).hexdigest(),'Verified bootstrap dependencies missing')
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
    from rrgh_final_overview_render import render
    results=[]
    for binding,proof in zip(p['bindings'],bootstrap['proofs'],strict=True):
        job=binding['job'];selected=[r for r in records if r['job']==job['id']]
        require(len(selected)==1,'Overview has no complete independent checkpoint')
        original=selected[0]['result']['originalReceipt']
        require(original.get('overviewProof')==proof,'Producer and independent child evidence differ')
        result=render(region,job,proof['children'],childroot,root/('recomputed-'+job['id']),source_root)
        require(result['receipt']['outputs']==original['outputs'],'Independent parent pixels/hash differ')
        results.append(dict(job=job['id'],allRequiredChildrenHashAndPixelVerified=True,
            independentParentRecomputationMatches=True,officialSourceRequests=0,
            sourceQualityUnchanged=True,childProof=proof))
    if plan['finalOverviewPhase'].get('format')=='rrgh-final-overview-phase-v1':
        from rrgh_final_overviews import digest,VERIFY
        from gorge_campaign import save_large
        detail=dict(format='rrgh-final-overview-independent-detail-v1',phaseSHA256=digest(plan['finalOverviewPhase']),
            planSHA256=digest(plan),bindings=copy.deepcopy(p['bindings']),parents=results)
        reference=save_large(slot,detail,limit=4*2**20)
        summary=[]
        for record in records:
            out=record['result']['originalReceipt']['outputs']
            require(len(out)==1,'One exact overview output required')
            summary.append(dict(job=record['job'],outputSHA256=out[0]['sha256'],outputBytes=out[0]['bytes']))
        return dict(format=VERIFY,phaseSHA256=detail['phaseSHA256'],planSHA256=detail['planSHA256'],
            allChildrenHashAndPixelVerified=True,allParentsIndependentlyRecomputed=True,
            allCoverageMasksVerified=True,seedAuthoritySHA256=plan['finalOverviewPhase']['authority']['seedAuthoritySHA256'],
            priorChildrenUnmodified=True,sourceQualityUnchanged=True,officialSourceRequests=0,
            parents=summary,detailRef=reference,detailSHA256=digest(detail))
    raise ValueError('Unreviewed final overview verification format')

