"""Synthetic recovery evidence through actual wave105->106 source publication.

Also validates real inspected source-evidence metadata against original scope.
No Cloud credential, source request, or production acceptance occurs here.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import rrgh_dispatcher as d
import rrgh_checkpoint_salvage as s
import rrgh_salvage_audit as a
from rrgh_prepare_dispatch_successor import prepare

root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'backend/scripts'))
from test_rrgh_checkpoint_salvage import AuditTests
from gorge_campaign import configuration
plan,_,region=configuration()
assert d.digest(d.canonical(plan))==a.manifest()['planSHA256']
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'pins.sqlite'
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE sources(url TEXT PRIMARY KEY,identity TEXT,metadata TEXT)')
    rows=json.loads((Path(__file__).parent/'fixtures/wave105-source-pins.json').read_bytes())
    assert [r['job'] for r in rows]==a.manifest()['completedJobIDs']
    assert s.merge_pins(path,rows,region)['completedSourcePins']>0

audit=AuditTests().evaluate(AuditTests().fixture())
def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
state=dict(sourceSHA=git('rev-parse','HEAD'),planSHA256=a.manifest()['planSHA256'],epoch=1)
assert state['sourceSHA']==a.manifest()['sourceSHA']
old_dir,old,_=d.config(root);frozen=(old_dir/'PLAN.json').read_bytes()
prepare(root,audit)
with tempfile.TemporaryDirectory() as temp:
    file=Path(temp)/'audit.json';file.write_text(json.dumps(dict(audit=audit,state=state)))
    code='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import rrgh_dispatcher as d
x=json.loads(Path(sys.argv[3]).read_bytes())
print(json.dumps(d.candidate_entries(sys.argv[2],x['audit'],x['state'])))
'''
    parent,new_hash,new_plan,entries=json.loads(subprocess.check_output(
        [sys.executable,'-I','-c',code,str(Path(__file__).parent.resolve()),str(root),str(file)],text=True))
assert (old_dir/'PLAN.json').read_bytes()==frozen
assert new_plan['campaign']['sequence']==106
assert new_plan['completedJobIDs']==old['completedJobIDs']+a.manifest()['completedJobIDs']
assert new_plan['campaign']['checkpointSalvageQuarantines']==a.manifest()['uncertainJobIDs']
assert not set(new_plan['approvedJobIDs'])&set(old['approvedJobIDs'])
assert all(new_plan['priorAttemptCounts'][j]==1 for j in old['approvedJobIDs'])
assert len(new_plan['approvedJobIDs'])==12
git('add',*[entry['path'] for entry in entries])
git('-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC salvage successor')
print(json.dumps(dict(test='SYNTHETIC_CHECKPOINT_SALVAGE',fromSequence=105,toSequence=106,
    uncertainJobsQuarantined=2,acceptedJobsPreserved=True,sourcePinsPreserved=True,liveProduction=False)))
subprocess.run([sys.executable,str(Path(__file__).with_name('verify_rrgh_dispatch_roundtrip.py')),str(root)],check=True)
