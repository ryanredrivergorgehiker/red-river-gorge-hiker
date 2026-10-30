"""New one-time transition failure tests; no network or old benchmarks."""
import copy,json,unittest,tempfile,base64,hashlib
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch
import gorge_reconciliation as r
from gorge_checkpoint import Ref,Meter,canonical,digest,BUCKET,PREFIX
from gorge_stage_coordinator import configuration

class ReconciliationTests(unittest.TestCase):
    def setUp(self):self.p,self.e,self.region=configuration()
    def test_exact_plan_carries_old_usage_inside_original_caps(self):
        r.validate_reconciliation(self.p,self.e)
        for k,v in r.MIN_CARRY.items():self.assertLessEqual(v+sum(s[k] for s in self.p['slots']),self.p['limits'][k])
        self.assertEqual(len(self.p['approvedJobIDs']),12)
    def test_missing_specific_approval_rejected(self):
        p=copy.deepcopy(self.p);p['reconciliation']['ownerApproval']='generic approval'
        with self.assertRaisesRegex(ValueError,'approval'):r.validate_reconciliation(p,self.e)
    def test_prior_spending_cannot_be_zeroed(self):
        p=copy.deepcopy(self.p);p['reconciliation']['carriedUsage']['egressBytes']=0
        with self.assertRaisesRegex(ValueError,'Prior charges'):r.validate_reconciliation(p,self.e)
    def test_new_slot_total_cannot_ignore_history(self):
        p=copy.deepcopy(self.p);p['slots'][2]['egressBytes']+=6*2**20
        with self.assertRaisesRegex(ValueError,'Cumulative'):r.validate_reconciliation(p,self.e)
    def test_completed_or_substituted_job_rejected(self):
        p=copy.deepcopy(self.p);p['approvedJobIDs'][0]=p['completedJobIDs'][0]
        with self.assertRaisesRegex(ValueError,'history'):r.validate_reconciliation(p,self.e)
    def test_historical_generation_change_rejected(self):
        p=copy.deepcopy(self.p);p['reconciliation']['priorReceiptRefs'][0]['generation']='999'
        with self.assertRaisesRegex(ValueError,'Unpinned'):r.validate_reconciliation(p,self.e)
    def test_changed_runtime_bound_rejected(self):
        p=copy.deepcopy(self.p);p['reconciliation']['maxWorkflowSeconds']=10800
        with self.assertRaisesRegex(ValueError,'runtime'):r.validate_reconciliation(p,self.e)
    def test_old_worker_claim_collision_stops_before_history_or_source_read(self):
        meter=Meter(self.p['slots'][0]);calls=[]
        def create(*args,**kw):calls.append((args,kw));raise RuntimeError('GCS HTTP 412')
        slot=SimpleNamespace(meter=meter,store=SimpleNamespace(_request=create),claim=Ref(PREFIX+'plans/new/slots/00000/claim.json','123',1,'0'*64),get=lambda *a:self.fail('No reads after collision'))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,'412'):r.transition(slot,self.p,self.e,Path(td))
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0][2]['ifGenerationMatch'],'0')
        self.assertEqual(meter.used['classARequests'],1);self.assertGreater(meter.used['storedBytes'],0)
    def test_missing_historical_receipt_cannot_start_inputs(self):
        meter=Meter(self.p['slots'][0])
        def create(method,key,query,maximum,data=None):
            return canonical({'bucket':BUCKET,'name':key,'size':str(len(data)),'generation':'123',
                'md5Hash':base64.b64encode(hashlib.md5(data).digest()).decode()}),{},200
        def get(ref):raise RuntimeError('missing receipt')
        slot=SimpleNamespace(meter=meter,store=SimpleNamespace(_request=create),claim=Ref(PREFIX+'plans/new/slots/00000/claim.json','123',1,'0'*64),get=get)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,'missing receipt'):r.transition(slot,self.p,self.e,Path(td))
        self.assertEqual(meter.used['classARequests'],1)

if __name__=='__main__':unittest.main()
