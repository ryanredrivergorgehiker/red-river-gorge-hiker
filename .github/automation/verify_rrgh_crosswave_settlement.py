"""Actual1357 closed receipt to waiting state, offline; no source replay."""
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
from rrgh_dispatch_audit import audit_run

ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve()
f=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1357-audit-input.json.z.b64').read_bytes())))
s=f['state'];audit=audit_run(f['run'],f['jobs'],f['recovery'],f['producer'],expected_dispatch=s,allow_failed_controller=True)
for k in ('completionPolicy','crosswavePolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled'):
    audit[k]=s[k]
parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();s['sourceSHA']=parent
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'audit.json';p.write_text(json.dumps(audit))
    subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),str(source),str(p)],check=True,
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
class API:
    def call(self,method,path,payload=None):
        assert method=='GET'
        if path.startswith('actions/runs?'):return dict(total_count=0,workflow_runs=[])
        assert path=='git/ref/heads/'+d.SOURCE
        return {'object':{'sha':parent}}
    def cas(self,old,state,message):
        assert old=='expected-blob';self.value=copy.deepcopy(state)
api=API();result=d.settle_completion_wait(api,ROOT,source,'expected-blob',s,audit)
assert api.value['status']=='completion-waiting'
assert api.value['lastRecovered']['acceptedRasterTiles']==267476
assert api.value['lastRecovered']['recoveryReceipt']==audit['receiptRef']
assert result['producerReplays']==result['sourceWrites']==0
print(json.dumps(dict(verified='actual verified1357 receipt settled offline without replay',acceptedRasterTiles=267476,
    liveStateMutation=False,sourceWrites=0,cloudRequests=0)))
