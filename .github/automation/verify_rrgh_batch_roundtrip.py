"""Synthetic full migration, larger allocation, partial continuation and fallback.

Uses actual pinned source/configuration and isolated credential-free publisher.
No source requests or Cloud writes; these are not live acceptance receipts.
"""
import base64
import copy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib
import rrgh_dispatcher as d
from rrgh_dispatch_audit import audit_run
from rrgh_prepare_dispatch_successor import prepare
from rrgh_batch_contract import CLOSURE,sha

root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root/'backend/scripts'))
from gorge_campaign import configuration

def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()

enabled=True
for iteration in range(7):
    folder,plan,_=d.config(root);configuration(folder)
    region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    jobs=plan['approvedJobIDs'];accepted=jobs;attempted=jobs;quarantine=[]
    if iteration==5:
        attempted=jobs[:4];accepted=attempted[:3];quarantine=attempted[3:]
    tiles=sum(len(j['outputTiles']) for j in region['jobs'] if j['id'] in accepted)
    carry=copy.deepcopy(plan['campaign']['carry']);carry['chargedUSD']=str(Decimal(carry['chargedUSD'])+Decimal('.08'))
    carry['storedBytes']+=40*2**20;carry['priorCompletedJobs']+=len(accepted);carry['priorRasterTiles']+=tiles
    plan_hash=sha(plan);seq=plan['campaign']['sequence'];rid=9900+iteration
    ref=dict(bytes=3000,generation=str(rid),sha256='e'*64,key='engineering/map-production/plans/'+plan_hash+'/slots/00002/receipt.json')
    workerref={**ref,'key':ref['key'].replace('00002','00001')}
    result=dict(status='verified',jobs=len(accepted),tiles=tiles,allOutputHashesAndPixelsVerified=True,
        allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,sourcePixelGapJobs=[],pixelGapAttemptsConsumed=0,
        adjacentEdgesMeasured=10,nextCarry=carry,workerReceipt=workerref,settlement=dict(independentRecoveryComplete=True,
        ambiguousAllocationRetained=False,campaignID=plan['campaign']['id'],sequence=seq,ceilingUSD='125.00',
        planSHA256=plan_hash,chargedUSD=carry['chargedUSD'],storedBytes=carry['storedBytes'],
        storageEstimateUSDPerMonth='1.10',remainingAuthorityUSD='85.00'))
    producer=[]
    if plan.get('resumableBatch'):
        c=dict(format=CLOSURE,planSHA256=plan_hash,allocationSHA256=sha(jobs),attemptedJobIDs=attempted,
               acceptedJobIDs=accepted,quarantinedJobIDs=quarantine,unattemptedJobIDs=jobs[len(attempted):],
               allChildrenJoined=True,sourceLedgersMerged=True,fallbackRequired=bool(quarantine),
               stopReason='synthetic child failure' if quarantine else None,workers=2,producerSeconds=100,childWallSeconds=150)
        result['batchClosure']=c
        producer=[dict(job=j,completedJobs=n,durableJobReceipt={**ref,'key':ref['key'].replace('00002/receipt.json','00001/jobs/'+j+'.json')})
                  for n,j in enumerate(accepted,1)]
        producer.append(dict(phase='production',batchClosure=c,receiptRef=workerref,jobs=len(accepted),
                             status='bounded-stop' if quarantine else 'complete'))
    state=dict(sequence=seq,runID=rid,dispatchID='f'*64,planSHA256=plan_hash,sourceSHA=git('rev-parse','HEAD'),epoch=1)
    run=dict(id=rid,run_attempt=1,head_branch=d.WORKER,event='workflow_dispatch',status='in_progress',conclusion=None,
             path='.github/workflows/'+d.WORKFLOW,actor=dict(login='github-actions[bot]'),repository=dict(full_name=d.REPO),
             display_title=f'RRGH production {seq} '+state['dispatchID'],created_at='2026-11-03T12:00:00Z')
    js=[dict(name=n,status='completed',conclusion='success',completed_at='2026-11-03T12:05:00Z')
        for n in ('bounded-stage','independent-recovery')]
    report=audit_run(run,js,[json.dumps(dict(phase='independent-recovery',receiptRef=ref,result=result))],
                     [json.dumps(x) for x in producer],expected_dispatch=state)
    # This synthetic timing variation is explicit: rollout tests require an
    # improvement; only actual GitHub timestamps can satisfy the live gate.
    report['cycleTilesPerSecond']=1.0 if iteration==0 else 1.2
    report.update(batchPilotEnabled=enabled,sourcePolicyMode='expanded',overviewPilotEnabled=False)
    oldbytes=(folder/'PLAN.json').read_bytes();prepare(root,report)
    with tempfile.TemporaryDirectory() as t:
        payload=Path(t)/'input.json';payload.write_text(json.dumps(dict(audit=report,state=state)))
        code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import rrgh_dispatcher as d
p=json.loads(Path(sys.argv[3]).read_bytes())
print(json.dumps(d.candidate_entries(Path(sys.argv[2]),p['audit'],p['state'])))
'''
        parent,new_hash,new,entries=json.loads(subprocess.check_output([sys.executable,'-I','-c',code,
            str(Path(__file__).resolve().parent),str(root),str(payload)],text=True))
    assert (folder/'PLAN.json').read_bytes()==oldbytes
    assert new['completedJobIDs']==plan['completedJobIDs']+accepted
    assert new['campaign']['carry']==carry and new['campaign']['previousRecovery']==ref
    for j in attempted:assert new['priorAttemptCounts'][j]==1
    for j in jobs[len(attempted):]:assert new['priorAttemptCounts'].get(j,0)==0
    if iteration==0:assert new['resumableBatch']['stage']=='pilot12'
    if iteration==2:assert new['resumableBatch']['stage']=='pilot24' and len(new['approvedJobIDs'])==24
    if iteration==4:assert new['resumableBatch']['stage']=='active24'
    if iteration==5:
        assert new['resumableBatch'] is None and len(new['approvedJobIDs'])<=12
        assert new['campaign']['batchQuarantines']==quarantine
        enabled=False
    if iteration==6:assert new['resumableBatch'] is None and len(new['campaign']['batchQuarantines'])==1
    git('add',*[e['path'] for e in entries]);git('-c','user.name=Offline QA','-c','user.email=offline@example.invalid',
        'commit','-qm',f'SYNTHETIC batch roundtrip {iteration}')
    print(json.dumps(dict(test='SYNTHETIC_BATCH_ROUNDTRIP',iteration=iteration,nextSequence=new['campaign']['sequence'],
        jobs=len(new['approvedJobIDs']),stage=(new.get('resumableBatch') or {}).get('stage','serial-fallback'),
        acceptedHistoryPreserved=True,liveProduction=False)))
