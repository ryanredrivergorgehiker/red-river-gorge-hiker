"""Real 1322 evidence, then SYNTHETIC USGS results; never counts Cloud output."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import rrgh_dispatcher as d
from rrgh_completion_phase import POLICY,PHASE

ROOT=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1]).resolve()
audit=json.loads((ROOT/'.github/automation/fixtures/wave1322-audit.json').read_bytes())
audit['completionPolicy']=POLICY
state=json.loads((ROOT/d.STATE).read_bytes())
state.update(sourceSHA=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
    planSHA256=audit['planSHA256'],sequence=1322,completionPolicy=POLICY)
old_dir,old,_=d.config(source)
old_bytes=(old_dir/'PLAN.json').read_bytes()


def prepare_and_validate(report,state):
    with tempfile.TemporaryDirectory() as tmp:
        payload=Path(tmp)/'audit.json';payload.write_text(json.dumps(report))
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),
            str(source),str(payload)],check=True,env=env)
    return d.candidate_entries(source,report,state)


for sequence in (1323,1324):
    parent,sha,plan,entries=prepare_and_validate(audit,state)
    assert plan['campaign']['sequence']==sequence
    assert plan['completionPhase']==PHASE
    assert len(plan['approvedJobIDs'])==12
    assert plan['campaign']['carry']==audit['nextCarry']
    assert (old_dir/'PLAN.json').read_bytes()==old_bytes
    assert all(plan['priorAttemptCounts'][j]==n for j,n in old['priorAttemptCounts'].items())
    assert not set(plan['approvedJobIDs']).intersection(old['completedJobIDs']+old['approvedJobIDs'])
    assert set(e['path'] for e in entries)=={
        'backend/scripts/gorge_campaign.py',
        *[f'backend/config/gorge-campaign-wave-{sequence}-20261102/{n}' for n in
            ('PLAN.json','ALLOWANCE.json','REGION-PLAN.json.z.b64')]}
    subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid',
        'commit','-qm','SYNTHETIC completion phase roundtrip'],check=True)
    if sequence==1323:
        previous=audit
        audit=copy.deepcopy(audit)
        audit.update(wave=1323,planSHA256=sha,jobsNew=12,tilesNew=12,
            acceptedJobs=audit['acceptedJobs']+12,acceptedRasterTiles=audit['acceptedRasterTiles']+12)
        audit['receiptRef']={**audit['receiptRef'],'key':'engineering/map-production/plans/'+sha+'/slots/00002/receipt.json',
            'sha256':'a'*64,'generation':'1234567890'}
        audit['receiptSHA256']=audit['receiptRef']['sha256']
        audit['nextCarry']=copy.deepcopy(audit['nextCarry'])
        audit['nextCarry']['priorCompletedJobs']+=12;audit['nextCarry']['priorRasterTiles']+=12
        state.update(sequence=1323,planSHA256=sha,
            sourceSHA=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip())
print(json.dumps(dict(verified='1322-to-1323-to-1324 planning and trusted publication',
    actualBaselineTiles=265702,syntheticSuccessorTiles=24,liveProduction=False,
    acceptedHistoryPreserved=True,consumedAttemptsPreserved=True,engineUnchanged=True)))

# Exercise the real planner and settlement at the final queue boundary using
# synthetic accepted lower tiles. This fixture is never published or counted.
from rrgh_completion_phase import lower_usgs_index
from rrgh_expanded_production import read_region
folder,plan,_=d.config(source)
index=lower_usgs_index(read_region(folder))
before=set(plan['completedJobIDs'])
extra=sorted(set(index)-before-set(plan['approvedJobIDs']))
plan['completedJobIDs']+=extra
plan['priorAttemptCounts'].update(dict.fromkeys(extra,1))
plan['campaign']['carry']['priorCompletedJobs']+=len(extra)
plan['campaign']['carry']['priorRasterTiles']+=len(extra)
(folder/'PLAN.json').write_bytes(d.canonical(plan))
sha=d.digest(d.canonical(plan))
allowance=json.loads((folder/'ALLOWANCE.json').read_bytes())
allowance['cloudStorageAllowance']['planSHA256']=sha
(folder/'ALLOWANCE.json').write_bytes(d.canonical(allowance))
subprocess.run(['git','-C',str(source),'add',str(folder/'PLAN.json'),str(folder/'ALLOWANCE.json')],check=True)
subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid',
    'commit','-qm','SYNTHETIC final lower-zoom coverage fixture'],check=True)
parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
audit.update(wave=1324,planSHA256=sha,jobsNew=12,tilesNew=12,
    acceptedJobs=len(plan['completedJobIDs'])+12,
    acceptedRasterTiles=plan['campaign']['carry']['priorRasterTiles']+12)
audit['receiptRef']={**audit['receiptRef'],'key':'engineering/map-production/plans/'+sha+'/slots/00002/receipt.json'}
audit['nextCarry']=copy.deepcopy(plan['campaign']['carry'])
audit['nextCarry']['priorCompletedJobs']+=12;audit['nextCarry']['priorRasterTiles']+=12
state.update(sourceSHA=parent,planSHA256=sha,sequence=1324)
with tempfile.TemporaryDirectory() as tmp:
    payload=Path(tmp)/'audit.json';payload.write_text(json.dumps(audit))
    subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),
        str(source),str(payload)],check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

class PhaseAPI:
    def call(self,method,path,payload=None):
        assert method=='GET'
        if path.startswith('actions/runs?'):return dict(total_count=0,workflow_runs=[])
        assert path=='git/ref/heads/'+d.SOURCE
        return {'object':{'sha':parent}}
    def cas(self,old,value,message):
        assert old=='expected-state-blob'
        self.value=copy.deepcopy(value)

api=PhaseAPI()
result=d.settle_completion_wait(api,ROOT,source,'expected-state-blob',state,audit)
assert api.value['status']=='completion-waiting'
assert api.value['lastRecovered']['acceptedRasterTiles']==267472
assert api.value['completionProgress']['remainingRasterTiles']==10806
assert api.value['completionProgress']['verifiedLowerUSGSTiles']==1770
assert api.value['completionProgress']['fullRasterCoverageComplete'] is False
assert not (source/'backend/config/gorge-campaign-wave-1325-20261102').exists()
print(json.dumps(dict(verified='finite queue settled without empty successor or Cloud replay',
    syntheticFinalRasterTiles=267472,remainingRasterTiles=10806,liveProduction=False)))
