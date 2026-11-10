"""Real1418 receipt -> native second-attempt pilot -> synthetic settled hold."""
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
import rrgh_native_repair as n
from rrgh_dispatch_audit import audit_run
from rrgh_expanded_production import read_region

ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve()
f=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1418-audit-input.json.z.b64').read_bytes())))
audit=audit_run(f['run'],f['jobs'],f['recovery'],f['producer'],expected_dispatch=f['state'])
for k in ('completionPolicy','crosswavePolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled'):
    audit[k]=f['state'][k]
audit['nativeRepairPolicy']=n.POLICY
old_dir,old,_=d.config(source);old_region=read_region(old_dir)
old_bytes=(old_dir/'PLAN.json').read_bytes()
assert d.digest(d.canonical(old))==n.BASELINE
parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()

def prepare(report):
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'audit.json';p.write_text(json.dumps(report))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),str(source),str(p)],
            check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

prepare(audit)
state=dict(sourceSHA=parent,planSHA256=n.BASELINE,sequence=1418,epoch=1)
_,sha,plan,entries=d.candidate_entries(source,audit,state)
folder,_,_=d.config(source);region=read_region(folder)
n.validate_publication(old,old_region,plan,region,audit)
assert plan['approvedJobIDs']==n.JOBS and sum(len(j['outputTiles']) for j in region['jobs'])==31
assert (old_dir/'PLAN.json').read_bytes()==old_bytes
assert all(plan['priorAttemptCounts'][j]==1 for j in n.JOBS)
assert plan['campaign']['sourcePixelGapQuarantines']==old['campaign']['sourcePixelGapQuarantines']
assert plan['campaign']['carry']==audit['nextCarry']

for fault in ('attempt_reset','attempt_three','accepted_output','source','quarantine','other_history','budget','receipt','scope','policy','tile_geometry'):
    bad=copy.deepcopy(plan);r=copy.deepcopy(region);a=copy.deepcopy(audit)
    if fault=='attempt_reset':bad['priorAttemptCounts'][n.JOBS[0]]=0
    elif fault=='attempt_three':bad['priorAttemptCounts'][n.JOBS[0]]=2
    elif fault=='accepted_output':bad['completedJobIDs'].append(n.JOBS[0])
    elif fault=='source':r['jobs'][0]['sourceIDs'].reverse()
    elif fault=='quarantine':bad['campaign']['sourcePixelGapQuarantines'].remove(n.JOBS[0])
    elif fault=='other_history':bad['priorAttemptCounts'].pop(old['completedJobIDs'][-1])
    elif fault=='budget':bad['slots'][1]['sourceBytes']+=1
    elif fault=='receipt':bad['campaign']['previousRecovery']['generation']='999'
    elif fault=='scope':bad['approvedJobIDs'].append('hiking-16-17535-25326')
    elif fault=='policy':a['nativeRepairPolicy']['maxGlobalAttempts']=3
    else:r['jobs'][0]['outputTiles'].pop()
    try:n.validate_publication(old,old_region,bad,r,a)
    except ValueError:pass
    else:raise AssertionError('Unsafe repair publication passed: '+fault)

sys.path.insert(0,str(source/'backend/scripts'))
from gorge_checkpoint import validate_plan
validate_plan(plan)
bad=copy.deepcopy(plan);bad['priorAttemptCounts'][n.JOBS[0]]=2
try:validate_plan(bad)
except ValueError as error:assert 'Two-attempt' in str(error)
else:raise AssertionError('Native runtime accepted a third attempt')

subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC native repair pilot fixture'],check=True)
report=copy.deepcopy(audit)
report.update(wave=1419,planSHA256=sha,jobsNew=3,tilesNew=31,acceptedJobs=33686,acceptedRasterTiles=273868,
    overviewPilotVerification=None,sourceCompletedJobIDs=[],sourcePixelGapJobs=[])
report['receiptRef']=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/receipt.json',
    bytes=2000,generation='90001',sha256='a'*64)
report['receiptSHA256']='a'*64
report['nextCarry']['priorCompletedJobs']=33686;report['nextCarry']['priorRasterTiles']=273868
summary=n.waiting_summary(plan,region,report)
assert summary['remainingRasterTiles']==4410 and summary['resolvedNativeJobs']==n.JOBS
assert summary['totalConsumedAttempts']==dict.fromkeys(n.JOBS,2)
partial=copy.deepcopy(report)
partial.update(jobsNew=2,tilesNew=10,acceptedJobs=33685,acceptedRasterTiles=273847,
    sourceCompletedJobIDs=n.JOBS[:2],sourcePixelGapJobs=n.JOBS[2:])
partial_summary=n.waiting_summary(plan,region,partial)
assert partial_summary['unresolvedNativeJobs']==n.JOBS[2:] and partial_summary['remainingRasterTiles']==4431
bad=copy.deepcopy(report);bad['tilesNew']=32
try:n.waiting_summary(plan,region,bad)
except ValueError:pass
else:raise AssertionError('Invented accepted tile passed')
prepare(report)
assert json.loads((source/'RRGH-COMPLETION-WAIT.json').read_bytes())==summary
changed=subprocess.check_output(['git','-C',str(source),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
assert changed==['RRGH-COMPLETION-WAIT.json'],changed
print(json.dumps(dict(verified='real1418 settlement to bounded attempt2 pilot and independently settled hold',
    actualBaselineTiles=273837,pilotJobs=3,pilotTiles=31,unsafeMutationCasesRejected=12,
    historicalQuarantinesPreserved=True,priorAttemptsPreserved=True,resourceLimitsUnchanged=True,
    sourceQualityUnchanged=True,liveProduction=False)))
