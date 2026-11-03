"""Actual partial recovery -> fresh successor; offline, no Cloud or GitHub writes."""
import json
from pathlib import Path
import subprocess
import sys
import rrgh_dispatcher as d
from rrgh_dispatch_audit import audit_run
from rrgh_prepare_dispatch_successor import prepare

root=Path(sys.argv[1]).resolve()
e=json.loads(Path(__file__).with_name('fixtures').joinpath('wave260-evidence.json').read_bytes())
audit=audit_run(e['run'],e['jobs'],e['recovery'],e['producer'],expected_dispatch=e['state'],allow_failed_controller=True)
audit.update(sourcePolicyMode='expanded',overviewPilotEnabled=True)
folder,old,_=d.config(root);frozen=(folder/'PLAN.json').read_bytes()
state=dict(e['state'],sourceSHA=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip())
prepare(root,audit)
_,sha,new,entries=d.candidate_entries(root,audit,state)
assert (folder/'PLAN.json').read_bytes()==frozen
assert new['completedJobIDs']==old['completedJobIDs']+old['approvedJobIDs'][:9]
assert new['priorAttemptCounts'][old['approvedJobIDs'][9]]==1
assert old['approvedJobIDs'][9] not in new['approvedJobIDs']
assert all(new['priorAttemptCounts'].get(j,0)==0 for j in old['approvedJobIDs'][10:])
assert new['campaign']['carry']==audit['nextCarry']
assert new['campaign']['carry']['chargedUSD']=='24.19169429936535954475402836'
assert new['campaign']['previousRecovery']==audit['receiptRef']
assert new['maxConcurrency']==1 and len(new['approvedJobIDs'])<=12
print(json.dumps(dict(phase='actual-wave260-offline-continuation',acceptedNewTiles=59,
    acceptedJobs=9,quarantinedAttempt=old['approvedJobIDs'][9],unattemptedJobs=old['approvedJobIDs'][10:],
    nextSequence=new['campaign']['sequence'],sourcePublicationFiles=len(entries),nextPlanSHA256=sha)))
subprocess.run(['git','-C',str(root),'add','.'],check=True)
subprocess.run(['git','-C',str(root),'-c','user.name=Offline QA','-c','user.email=offline@example.invalid','commit','-qm','Offline wave261 for continuation regression'],check=True)
