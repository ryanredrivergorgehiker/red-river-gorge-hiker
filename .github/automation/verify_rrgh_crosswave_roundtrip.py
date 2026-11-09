"""Real settled1356 plan -> fresh pilot -> SYNTHETIC closure, no Cloud access."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import rrgh_dispatcher as d
import rrgh_crosswave_phase as c
from rrgh_expanded_production import read_region
from rrgh_crosswave_runtime import PHASE_SHA

ROOT=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1]).resolve()
audit=json.loads((ROOT/'.github/automation/fixtures/wave1356-audit.json').read_bytes())
old_dir,old,_=d.config(source)
assert d.digest(d.canonical(old))==c.POLICY['baselinePlanSHA256']
old_bytes=(old_dir/'PLAN.json').read_bytes()
parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
state=dict(sourceSHA=parent,planSHA256=audit['planSHA256'],sequence=1356,epoch=1)


def prepare(report):
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'audit.json';p.write_text(json.dumps(report))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),
            str(source),str(p)],check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})


prepare(audit)
_,sha,plan,entries=d.candidate_entries(source,audit,state)
assert plan['approvedJobIDs']==[b['job']['id'] for b in c.phase()['bindings']]
assert plan['campaign']['carry']==audit['nextCarry']
assert plan['campaign']['carry']['priorRasterTiles']==267472
assert plan['limits']==dict(old['limits'],attempts=4)
assert plan['slots']==[old['slots'][0],dict(old['slots'][1],attempts=4),old['slots'][2]]
assert all(plan['priorAttemptCounts'][j]==n for j,n in old['priorAttemptCounts'].items())
assert (old_dir/'PLAN.json').read_bytes()==old_bytes
folder,_,_=d.config(source);region=read_region(folder)
for fault in ('binding','attempt','source'):
    bad=copy.deepcopy(plan)
    if fault=='binding':bad['crosswavePhase']['bindings'][0]['children'][0]['source']['recovery']['generation']='9999'
    elif fault=='attempt':bad['priorAttemptCounts'][bad['approvedJobIDs'][0]]=1
    else:bad['jobPolicies'][bad['approvedJobIDs'][0]]['sourceRequests']=1
    try:c.validate_plan(bad,region,c.POLICY)
    except ValueError:pass
    else:raise AssertionError('Invalid publication accepted: '+fault)

subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid',
    'commit','-qm','SYNTHETIC pilot plan roundtrip'],check=True)
print(json.dumps(dict(verified='actual1356-to1357 planner and trusted publisher',
    acceptedBaseline=267472,selectedParents=4,oldPlansUnchanged=True,aggregateLimitsUnchanged=True,liveProduction=False)))

# This structurally valid report is explicitly synthetic. Physical child readback,
# four-layer rendering and independent recomputation are tested separately.
proof=dict(format='rrgh-crosswave-verification-v1',phaseSHA256=PHASE_SHA,
    bindings=copy.deepcopy(plan['crosswavePhase']['bindings']),parents=[])
for binding in proof['bindings']:
    job=binding['job'];children=[]
    for child in binding['children']:
        jid=child['job'];s=child['source'];layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y))
        prefix='engineering/map-production/plans/'+s['sourcePlanSHA256']+'/slots/00001/'
        jr=dict(key=prefix+'jobs/'+jid+'.json',generation='123',bytes=100,sha256='a'*64)
        obj=dict(key=prefix+'outputs/'+'b'*64,generation='124',bytes=200,sha256='b'*64)
        children.append(dict(job=jid,tile=[layer,z,x,y],path=f'tiles/{layer}/{z}/{x}/{y}.png',
            bytes=100,sha256='c'*64,checkpointOffset=0,checkpointObject=obj,jobReceipt=jr,
            pixelReadbackVerified=True,independentRecovery=s['recovery'],sourceRecipeSHA256=s['recipeSHA256']))
    proof['parents'].append(dict(job=job['id'],fourChildrenHashAndPixelVerified=True,
        independentParentRecomputationMatches=True,sourceQualityUnchanged=True,officialSourceRequests=0,
        childProof=dict(format='rrgh-crosswave-interior-dependencies-v1',job=job['id'],children=children,
            officialSourceRequests=0,priorChildrenUnmodified=True)))
sys.path.insert(0,str(source/'backend/scripts'))
from gorge_checkpoint import encode_record,COMPACT_RECEIPT
assert len(encode_record({'result':{'overviewPilotVerification':proof}},COMPACT_RECEIPT,True))<COMPACT_RECEIPT//2
audit=copy.deepcopy(audit)
audit.update(wave=1357,planSHA256=sha,jobsNew=4,tilesNew=4,
    acceptedJobs=audit['acceptedJobs']+4,acceptedRasterTiles=267476,overviewPilotVerification=proof)
audit['receiptRef']=dict(bytes=1600,generation='125',sha256='d'*64,
    key='engineering/map-production/plans/'+sha+'/slots/00002/receipt.json')
audit['receiptSHA256']=audit['receiptRef']['sha256']
audit['nextCarry']['priorCompletedJobs']+=4;audit['nextCarry']['priorRasterTiles']+=4
prepare(audit)
summary=json.loads((source/'RRGH-COMPLETION-WAIT.json').read_bytes())
assert summary['acceptedRasterTiles']==267476 and summary['remainingRasterTiles']==10802
assert summary['fullRasterCoverageComplete'] is False
assert subprocess.check_output(['git','-C',str(source),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()==['RRGH-COMPLETION-WAIT.json']
print(json.dumps(dict(verified='pilot once-only settlement with no empty successor',syntheticAccepted=267476,liveProduction=False)))
