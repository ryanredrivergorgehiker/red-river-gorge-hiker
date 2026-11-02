"""Offline synthetic fault tests. These do not count as live recovery."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rrgh_checkpoint_salvage as s
import rrgh_wif_credentials as w
import rrgh_credential_integration as ci
import rrgh_salvage_audit as a
import rrgh_dispatcher as d
from test_rrgh_dispatcher import FakeGitHub

ROOT=Path(__file__).resolve().parents[2]


class CredentialTests(unittest.TestCase):
    def setUp(self):w._VALUE=None;w._UNTIL=0
    def test_transport_refresh_retries_without_storage_operation(self):
        failures=[SimpleNamespace(returncode=1,stdout='',stderr='Connection reset by peer'),
                  SimpleNamespace(returncode=0,stdout='synthetic-token\n',stderr='')]
        with patch.object(w.subprocess,'run',side_effect=failures) as run,patch.object(w.time,'sleep'):
            self.assertEqual(w.token(),'synthetic-token');self.assertEqual(run.call_count,2)
            self.assertEqual(w.token(),'synthetic-token');self.assertEqual(run.call_count,2)
    def test_denial_unknown_or_invalid_output_never_retries(self):
        for stderr,stdout,code in [('permission_denied Connection reset','',1),('unknown','',1),('', 'two tokens',0)]:
            with patch.object(w.subprocess,'run',return_value=SimpleNamespace(returncode=code,stdout=stdout,stderr=stderr)) as run:
                with self.assertRaises(RuntimeError):w.token()
                self.assertEqual(run.call_count,1);self.assertIsNone(w._VALUE)
    def test_expired_token_is_never_fallback_after_three_timeouts(self):
        w._VALUE='expired-secret';w._UNTIL=0
        with patch.object(w.subprocess,'run',side_effect=subprocess.TimeoutExpired(['gcloud'],30)) as run,patch.object(w.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'timeout'):w.token()
            self.assertEqual(run.call_count,3);self.assertIsNone(w._VALUE)
    def test_exact_source_migration_is_idempotent_and_rejects_drift(self):
        original=(ROOT/'.github/automation/source-templates/run_gorge_checkpoint_slot.py').read_text()
        new=ci.augment(original);self.assertEqual(ci.augment(new),new)
        self.assertIn('from rrgh_wif_credentials import token',new)
        for code in (original+'\n# drift',new+'\n# drift'):
            with self.assertRaises(ValueError):ci.augment(code)


class PinTests(unittest.TestCase):
    def fixture(self,url='https://example.invalid/official.tif'):
        pin=dict(url=url,length=200000,etag='"etag"',lastModified='date',pinnedAtUTC='time')
        pin['identity']=hashlib.sha256(json.dumps([url,pin['etag'],pin['length']]).encode()).hexdigest()
        row=dict(job='terrain-16-1-2',result=dict(originalReceipt=dict(sourceEvidence=[dict(pin,id='source')])) )
        region=dict(jobs=[dict(id=row['job'],layer='terrain',sourceIDs=['source'])],
                    inventory=dict(sources=dict(dem=[dict(id='source',url=url)])))
        return pin,row,region
    def database(self,path):
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE sources(url TEXT PRIMARY KEY,identity TEXT,metadata TEXT)')
    def test_reconstruction_keeps_prior_pins_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pins.sqlite';self.database(path);pin,row,region=self.fixture()
            prior=dict(pin,url='https://example.invalid/prior.tif',identity='unchanged')
            with sqlite3.connect(path) as db:db.execute('INSERT INTO sources VALUES (?,?,?)',(prior['url'],prior['identity'],json.dumps(prior)))
            result=s.merge_pins(path,[row],region)
            self.assertEqual((result['priorPins'],result['newPins']),(1,1))
            self.assertEqual(s.merge_pins(path,[row],region)['newPins'],0)
            with sqlite3.connect(path) as db:self.assertEqual(db.execute('SELECT metadata FROM sources WHERE url=?',(prior['url'],)).fetchone()[0],json.dumps(prior))
    def test_conflicting_identity_unapproved_url_and_missing_evidence_rejected(self):
        for fault in ('identity','url','missing'):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'pins.sqlite';self.database(path);pin,row,region=self.fixture()
                if fault=='identity':row['result']['originalReceipt']['sourceEvidence'][0]['identity']='0'*64
                if fault=='url':row['result']['originalReceipt']['sourceEvidence'][0]['url']='https://attacker.invalid/'
                if fault=='missing':row['result']['originalReceipt']['sourceEvidence']=[]
                with self.assertRaises(ValueError):s.merge_pins(path,[row],region)


class AuditTests(unittest.TestCase):
    def fixture(self):
        m=a.manifest();v=m['originalAllocation'];prior=m['priorCarry'];rid=987654
        charge=(Decimal(v['storedBytes'])/2**30*Decimal('.03')+Decimal(v['egressBytes'])/2**30*Decimal('.23')+
                Decimal(v['classARequests'])/1000*Decimal('.01')+Decimal(v['classBRequests'])/1000*Decimal('.001'))*Decimal('1.2')
        carry=dict(prior,chargedUSD=str(Decimal(prior['chargedUSD'])+charge),storedBytes=prior['storedBytes']+v['storedBytes'],
                   priorCompletedJobs=prior['priorCompletedJobs']+7,priorRasterTiles=prior['priorRasterTiles']+51)
        state=dict(mode='salvage',sequence=105,runID=rid,dispatchID='a'*64,sourceSHA=m['sourceSHA'],planSHA256=m['planSHA256'],
                   salvageOf=dict(manifestSHA256=a.manifest_sha()))
        run=dict(id=rid,run_attempt=1,head_branch=a.BRANCH,path=a.WORKFLOW,event='workflow_dispatch',
                 actor=dict(login='github-actions[bot]'),repository=dict(full_name=a.REPO),
                 display_title='RRGH salvage 105 '+state['dispatchID'],status='in_progress',conclusion=None)
        jobs=[dict(id=i,name=n,status='completed',conclusion=c) for i,(n,c) in enumerate(
            [('independent-salvage','success'),('bounded-stage','skipped'),('independent-recovery','skipped')])]
        result=dict(status='partial-verified',salvage='wave105-missing-producer-closure-v1',
            originalProducerRunID=m['originalRunID'],producerClaim=m['producerClaim'],workerReceipt=None,
            bootstrapReceipt=m['bootstrapReceipt'],completedJobRefs=m['completedJobRefs'],completedJobIDs=m['completedJobIDs'],
            uncertainJobIDs=m['uncertainJobIDs'],jobs=7,tiles=51,verifiedTileCatalogTiles=51,sourceJobsExecuted=0,
            adjacentEdgesMeasured=10,packageParts=3,packageBytes=123456,allOutputHashesAndPixelsVerified=True,
            allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,unacceptedAttemptsQuarantined=True,
            sourcePinsReconstructed=dict(allPriorPinsPreserved=True),nextCarry=carry,
            settlement=dict(sequence=105,planSHA256=m['planSHA256'],originalAllocation=v,retainedUsage=v,
                demonstrablyUnused={k:0 for k in v},ambiguousAllocationRetained=True,independentRecoveryComplete=False,
                chargedUSD=carry['chargedUSD'],storedBytes=carry['storedBytes']))
        report=dict(phase='independent-checkpoint-salvage',result=result,
            receiptRef=dict(key='engineering/map-production/plans/'+m['planSHA256']+'/slots/00002/receipt.json',
                generation='1234',sha256='b'*64,bytes=2000))
        class API:
            token='test-only'
            def call(self,method,path):return dict(total_count=len(jobs),jobs=jobs) if '/jobs?' in path else run
        return API(),state,run,jobs,report
    def evaluate(self,f):
        api,state,_,_,report=f
        with patch.object(a,'original',return_value=a.manifest()),patch('rrgh_dispatch_audit.gh',return_value=json.dumps(report)):
            return a.audit(api,state)
    def test_exact_independent_salvage_retains_full_allocation(self):
        result=self.evaluate(self.fixture())
        self.assertTrue(result['salvagedCheckpointRecovery']);self.assertEqual(result['acceptedRasterTiles'],120434)
        self.assertEqual(len(result['uncertainJobIDs']),2)
    def test_mutated_receipts_refund_source_execution_or_identity_rejected(self):
        for fault in ('refund','source','receipt','identity','pin','job'):
            f=self.fixture();api,state,run,jobs,report=f;r=report['result']
            if fault=='refund':r['settlement']['retainedUsage']=dict(r['settlement']['retainedUsage'],storedBytes=0)
            if fault=='source':r['sourceJobsExecuted']=1
            if fault=='receipt':r['completedJobRefs']=[]
            if fault=='identity':run['run_attempt']=2
            if fault=='pin':r['sourcePinsReconstructed']['allPriorPinsPreserved']=False
            if fault=='job':jobs[1]['conclusion']='success'
            with self.assertRaises(ValueError):self.evaluate(f)
    def test_controller_requires_exact_owner_authorization_and_never_replays(self):
        api=FakeGitHub();m=a.manifest()
        api.value.update(status='halted',mode='produce',sequence=105,runID=m['originalRunID'],dispatchID=m['originalDispatchID'],
            sourceSHA=m['sourceSHA'],planSHA256=m['planSHA256'])
        before=copy.deepcopy(api.value)
        with patch.object(d,'caller'),patch.object(a,'original',return_value=m):
            with self.assertRaises(d.Halt):d.salvage_halted(api,ROOT)
        self.assertEqual(api.value,before)


if __name__=='__main__':unittest.main()
