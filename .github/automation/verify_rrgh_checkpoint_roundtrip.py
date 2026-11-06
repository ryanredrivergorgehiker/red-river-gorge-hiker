"""Actual wave613 source + original log evidence; SYNTHETIC recovery result.

No Cloud requests or accepted output. Verifies prospective migration and two
ordinary successors after preserving the new quarantine in immutable plans.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import rrgh_checkpoint_recovery as c
import rrgh_dispatcher as d
from rrgh_prepare_dispatch_successor import prepare
from test_rrgh_checkpoint_recovery import fixture,OriginalAPI,result_fixture

root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'backend/scripts'))
from gorge_campaign import configuration
plan,_,region=configuration()
f=fixture();state=f['state']
assert d.digest(d.canonical(plan))==state['planSHA256']
assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==state['sourceSHA']
with patch.object(c,'plan_at',return_value=plan),patch('rrgh_dispatch_audit.gh',return_value='\n'.join(map(json.dumps,f['producerRows']))):
    m,_=c.original(OriginalAPI(f),state)
assert sum(len(j['outputTiles']) for j in region['jobs'] if j['id'] in m['completedJobIDs'])==m['tiles']==76
assert [j['id'] for j in region['jobs']]==m['completedJobIDs']+m['uncertainJobIDs']
audit=c.validate_report(m,result_fixture(m),{**state,'runID':999999,'overviewPilotEnabled':True})
folder,_,_=d.config(root);frozen=(folder/'PLAN.json').read_bytes()
prepare(root,audit)
with tempfile.TemporaryDirectory() as temp:
    payload=Path(temp)/'input.json';payload.write_text(json.dumps(dict(audit=audit,state=state)))
    script='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import rrgh_dispatcher as d
p=json.loads(Path(sys.argv[3]).read_bytes())
print(json.dumps(d.candidate_entries(Path(sys.argv[2]),p['audit'],p['state'])))
'''
    parent,sha,new,entries=json.loads(subprocess.check_output([sys.executable,'-I','-c',script,
        str(Path(__file__).parent.resolve()),str(root),str(payload)],text=True))
assert (folder/'PLAN.json').read_bytes()==frozen
assert new['campaign']['sequence']==614
assert new['campaign']['carry']['priorRasterTiles']==183535
assert new['completedJobIDs']==plan['completedJobIDs']+m['completedJobIDs']
assert new['campaign']['checkpointRecoveryQuarantines']==m['uncertainJobIDs']
assert all(new['priorAttemptCounts'][j]==1 for j in plan['approvedJobIDs'])
assert not set(new['approvedJobIDs'])&set(plan['approvedJobIDs'])
assert 'backend/scripts/rrgh_wif_credentials.py' in [e['path'] for e in entries]
subprocess.run(['git','-C',str(root),'add',*[e['path'] for e in entries]],check=True)
subprocess.run(['git','-C',str(root),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid',
    'commit','-qm','SYNTHETIC checkpoint recovery successor'],check=True)
print(json.dumps(dict(test='SYNTHETIC_CHECKPOINT_613_TO_614',originalLogsValidated=True,
    sourcePublicationValidated=True,credentialMigrationValidated=True,uncertainAttemptsRetained=2,
    syntheticInclusiveTiles=183535,liveProduction=False)))
subprocess.run([sys.executable,str(Path(__file__).with_name('verify_rrgh_dispatch_roundtrip.py')),str(root)],check=True)
