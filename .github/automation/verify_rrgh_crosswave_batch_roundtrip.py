"""Actual1357 receipt -> bounded batch -> synthetic successor; no Cloud access."""
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib
import rrgh_dispatcher as d
import rrgh_crosswave_batch as c
from rrgh_dispatch_audit import audit_run
from rrgh_expanded_production import read_region

ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve()
f=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1357-audit-input.json.z.b64').read_bytes())))
audit=audit_run(f['run'],f['jobs'],f['recovery'],f['producer'],expected_dispatch=f['state'],allow_failed_controller=True)
for k in ('completionPolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled'):audit[k]=f['state'][k]
audit['crosswavePolicy']=c.POLICY
old_dir,old,_=d.config(source);assert d.digest(d.canonical(old))==c.POLICY['baselinePlanSHA256']
old_bytes=(old_dir/'PLAN.json').read_bytes()

def prepare(report):
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'audit.json';p.write_text(json.dumps(report))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),str(source),str(p)],check=True,
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

def candidate(report):
    parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    state=dict(sourceSHA=parent,planSHA256=report['planSHA256'],sequence=report['wave'],epoch=1)
    prepare(report)
    return d.candidate_entries(source,report,state)

_,sha,plan,entries=candidate(audit)
folder,_,_=d.config(source);region=read_region(folder)
assert 1<len(plan['approvedJobIDs'])<=128
assert plan['campaign']['carry']==audit['nextCarry'] and plan['campaign']['carry']['priorRasterTiles']==267476
c.validate_funding(old,plan);c.validate_history(old,read_region(old_dir),plan,audit)
assert (old_dir/'PLAN.json').read_bytes()==old_bytes
assert sum(v['seconds'] for v in plan['jobPolicies'].values())<=7680
assert all(v['sourceBytes']==v['sourceRequests']==0 for v in plan['jobPolicies'].values())
assert plan['crosswaveHistory'][0]['recovery']==c.POLICY['verifiedPilotRecovery']
for fault in ('binding','attempt','source','history','budget'):
    bad=copy.deepcopy(plan)
    if fault=='binding':bad['crosswavePhase']['sources'][next(iter(bad['crosswavePhase']['sources']))]['recovery']['generation']='9999'
    elif fault=='attempt':bad['priorAttemptCounts'][bad['approvedJobIDs'][0]]=1
    elif fault=='source':bad['jobPolicies'][bad['approvedJobIDs'][0]]['sourceRequests']=1
    elif fault=='history':bad['crosswaveHistory'][0]['recovery']['generation']='9999'
    else:bad['slots'][0]['egressBytes']+=1
    try:
        c.validate_plan(bad,region,c.POLICY);c.validate_history(old,read_region(old_dir),bad,audit);c.validate_funding(old,bad)
    except ValueError:pass
    else:raise AssertionError('Invalid publication accepted: '+fault)

subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC first batch fixture'],check=True)
print(json.dumps(dict(verified='actual1357 to first batch via trusted publisher',acceptedBaseline=267476,
    selectedParents=len(plan['approvedJobIDs']),readBounds=plan['crosswavePhase']['readBounds'],sourceRequests=0,
    oldPlansUnchanged=True,aggregateLimitsUnchanged=True,liveProduction=False)))

# Structurally valid synthetic receipt tests succession; never treated as live acceptance.
report=copy.deepcopy(audit);n=len(plan['approvedJobIDs'])
proof=dict(format=c.VERIFY,phaseSHA256=c.digest(plan['crosswavePhase']),planSHA256=sha,
    allChildrenHashAndPixelVerified=True,allParentsIndependentlyRecomputed=True,priorChildrenUnmodified=True,
    sourceQualityUnchanged=True,officialSourceRequests=0,detailSHA256='f'*64,
    detailRef=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/indexes/detail',generation='321',bytes=100,sha256='e'*64),
    parents=[dict(job=j,outputSHA256='a'*64,outputBytes=100) for j in plan['approvedJobIDs']])
report.update(wave=1358,planSHA256=sha,jobsNew=n,tilesNew=n,acceptedJobs=audit['acceptedJobs']+n,
    acceptedRasterTiles=267476+n,overviewPilotVerification=proof)
report['receiptRef']=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/receipt.json',generation='322',bytes=1000,sha256='b'*64)
report['receiptSHA256']=report['receiptRef']['sha256'];report['nextCarry']['priorCompletedJobs']+=n;report['nextCarry']['priorRasterTiles']+=n
_,sha2,p2,entries2=candidate(report)
assert not set(p2['approvedJobIDs'])&set(plan['approvedJobIDs'])
assert len(p2['crosswaveHistory'])==2 and p2['completedJobIDs']==plan['completedJobIDs']+plan['approvedJobIDs']
assert all(p2['priorAttemptCounts'][j]==1 for j in plan['approvedJobIDs'])
c.validate_funding(plan,p2)
sys.path.insert(0,str(source/'backend/scripts'))
from gorge_checkpoint import encode_record,COMPACT_RECEIPT
encoded=encode_record(dict(result=dict(overviewPilotVerification=proof)),COMPACT_RECEIPT,True)
assert len(encoded)<COMPACT_RECEIPT//2
print(json.dumps(dict(verified='nonoverlapping second batch, exact history, bounded compact receipt',
    firstBatch=n,secondBatch=len(p2['approvedJobIDs']),syntheticReceiptBytes=len(encoded),liveProduction=False)))
