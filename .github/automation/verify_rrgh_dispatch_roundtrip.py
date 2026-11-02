"""Two offline successor roundtrips with explicitly SYNTHETIC recovery evidence.

Runs in a disposable checkout; never authenticates to Cloud or contacts GitHub.
Validates real engine pins, exact source publication, inventory, allocation and
budget logic. This is not evidence that two live production waves succeeded.
"""
import base64
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib
import rrgh_dispatcher as d
from rrgh_dispatch_audit import audit_run,Halt
from rrgh_prepare_dispatch_successor import prepare

root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'backend/scripts'))
from gorge_campaign import configuration


def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


for iteration in range(2):
    folder,plan,_=d.config(root)
    # Engine admission evaluates actual immutable pins and full-quality profiles.
    configuration(folder)
    region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    plan_hash=d.digest(d.canonical(plan));seq=plan['campaign']['sequence'];rid=9000+iteration
    carry=copy.deepcopy(plan['campaign']['carry'])
    carry['chargedUSD']=str(Decimal(carry['chargedUSD'])+Decimal('0.25'))
    carry['storedBytes']+=40*2**20
    carry['priorCompletedJobs']+=len(plan['approvedJobIDs'])
    carry['priorRasterTiles']+=sum(len(j['outputTiles']) for j in region['jobs'])
    receipt=dict(bytes=1500,generation=str(9000+iteration),sha256=str(iteration+1)*64,
        key='engineering/map-production/plans/'+plan_hash+'/slots/00002/receipt.json')
    result=dict(status='verified',jobs=len(plan['approvedJobIDs']),allOutputHashesAndPixelsVerified=True,
        allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,sourcePixelGapJobs=[],
        adjacentEdgesMeasured=12,nextCarry=carry,settlement=dict(independentRecoveryComplete=True,
        ambiguousAllocationRetained=False,campaignID=plan['campaign']['id'],sequence=seq,ceilingUSD='125.00',
        planSHA256=plan_hash,chargedUSD=carry['chargedUSD'],storedBytes=carry['storedBytes'],
        storageEstimateUSDPerMonth='0.90',remainingAuthorityUSD='100.00'))
    if plan.get('overviewPilot'):
        from test_rrgh_overview_production import synthetic_proof
        result['overviewPilotVerification']=synthetic_proof()
    state=dict(sequence=seq,runID=rid,dispatchID='e'*64,planSHA256=plan_hash,sourceSHA=git('rev-parse','HEAD'),epoch=1)
    run=dict(id=rid,run_attempt=1,head_branch=d.WORKER,event='workflow_dispatch',status='in_progress',
        conclusion=None,path='.github/workflows/'+d.WORKFLOW,actor=dict(login='github-actions[bot]'),
        repository=dict(full_name=d.REPO),display_title=f'RRGH production {seq} '+state['dispatchID'])
    jobs=[dict(name=n,status='completed',conclusion='success') for n in ('bounded-stage','independent-recovery')]
    # Other controller jobs are still active; only the finished independent worker is accepted.
    jobs.append(dict(name='advance',status='in_progress',conclusion=None))
    lines=[json.dumps(dict(phase='independent-recovery',receiptRef=receipt,result=result),sort_keys=True)]
    audit=audit_run(run,jobs,lines,[],expected_dispatch=state)
    audit['overviewPilotEnabled']=os.environ.get('RRGH_TEST_OVERVIEW_PILOT')=='1'
    for field,value in [('event','push'),('run_attempt',2),('display_title','forged')]:
        try:audit_run({**run,field:value},jobs,lines,[],expected_dispatch=state)
        except Halt:pass
        else:raise AssertionError('Identity audit accepted '+field)
    broken=copy.deepcopy(jobs);broken[1]['conclusion']='failure'
    try:audit_run(run,broken,lines,[],expected_dispatch=state)
    except Halt:pass
    else:raise AssertionError('Failed independent recovery accepted')
    frozen=(folder/'PLAN.json').read_bytes()
    output=prepare(root,audit)
    # Reproduce the publisher's separate process: no source checkout imports or
    # native dependencies are available to its credential-bearing validation.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        payload=Path(temp)/'input.json';payload.write_text(json.dumps(dict(audit=audit,state=state)))
        code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import rrgh_dispatcher as d
p=json.loads(Path(sys.argv[3]).read_bytes())
print(json.dumps(d.candidate_entries(Path(sys.argv[2]),p['audit'],p['state'])))
'''
        parent,new_hash,new_plan,entries=json.loads(subprocess.check_output(
            [sys.executable,'-I','-c',code,str(Path(__file__).resolve().parent),str(root),str(payload)],text=True))
    assert (folder/'PLAN.json').read_bytes()==frozen
    assert new_plan['campaign']['previousRecovery']==receipt
    assert new_plan['campaign']['carry']==carry
    assert set(new_plan['completedJobIDs'])==set(plan['completedJobIDs']+plan['approvedJobIDs'])
    assert set(new_plan['approvedJobIDs']).isdisjoint(plan['approvedJobIDs'])
    assert all(new_plan[k]==plan[k] for k in ('cachePolicy','maxConcurrency','automaticRetryPermitted','deleteAllowed'))
    assert new_hash==output['nextPlanSHA256'] and 4 <= len(entries) <= 10
    from rrgh_recovery_catalog_integration import validate as validate_catalog
    validate_catalog(root)
    git('add',*[entry['path'] for entry in entries])
    git('-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm',f'SYNTHETIC offline successor {seq+1}')
    print(json.dumps(dict(test='SYNTHETIC_OFFLINE_ROUNDTRIP',fromSequence=seq,toSequence=seq+1,
        sourcePublicationValidated=True,independentRecoveryGuardValidated=True,liveProduction=False)))
