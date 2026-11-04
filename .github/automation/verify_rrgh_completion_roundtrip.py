"""Synthetic completion -> actual immutable successor planner/publisher roundtrip.

Runs offline on exact source289. These invented receipts are not live evidence.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import rrgh_dispatcher as d
from rrgh_prepare_dispatch_successor import prepare
from rrgh_completion_contract import manifest, sha
from rrgh_completion_audit import verify_result
from test_rrgh_completion import synthetic_report

root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'backend/scripts'))
from gorge_campaign import configuration
from gorge_checkpoint import require_live_allowance
from rrgh_completion_contract import funding

old,evidence,region=configuration()
m=manifest()
assert sha(old)==m['planSHA256'] and [j['id'] for j in region['jobs']]==m['completedJobIDs']
assert sum(len(j['outputTiles']) for j in region['jobs'])==246
require_live_allowance(*funding())
report=verify_result(*synthetic_report())
before={str(p):p.read_bytes() for p in (root/'backend/config/gorge-campaign-wave-289-20261102').iterdir()}
state=dict(sourceSHA=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
           planSHA256=m['planSHA256'],epoch=1)
prepare(root,report)
with tempfile.TemporaryDirectory() as temp:
    payload=Path(temp)/'report.json';payload.write_text(json.dumps(dict(audit=report,state=state)))
    code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import rrgh_dispatcher as d
p=json.loads(Path(sys.argv[3]).read_bytes())
print(json.dumps(d.candidate_entries(Path(sys.argv[2]),p['audit'],p['state'])))
'''
    parent,new_hash,new,entries=json.loads(subprocess.check_output([sys.executable,'-I','-c',code,
        str(Path(__file__).resolve().parent),str(root),str(payload)],text=True))
assert new['campaign']['previousRecovery']==report['receiptRef']
assert new['campaign']['carry']==report['nextCarry']
assert new['completedJobIDs']==old['completedJobIDs']+old['approvedJobIDs']
assert all(new['priorAttemptCounts'][j]==1 for j in old['approvedJobIDs'])
assert all(new['priorAttemptCounts'].get(j,0)==0 for j in new['approvedJobIDs'])
assert not set(new['approvedJobIDs']) & set(old['approvedJobIDs'])
assert new['resumableBatch'] is None and len(new['approvedJobIDs'])<=12
assert new['campaign']['batchQuarantines']==old['campaign']['batchQuarantines']
assert all(Path(path).read_bytes()==raw for path,raw in before.items())
subprocess.run([sys.executable,str(root/'backend/scripts/gorge_campaign.py'),'--phase','plan'],check=True)
print(json.dumps(dict(test='SYNTHETIC_COMPLETION_ROUNDTRIP',nextSequence=290,
    jobs=len(new['approvedJobIDs']),all24AttemptsRetained=True,acceptedJobs=len(new['completedJobIDs']),
    serialFallback=True,originalPlanUnchanged=True,cloudWrites=0,liveProduction=False)))
