"""Synthetic setup incidents; never production acceptance evidence."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import rrgh_recovery_only as r
import rrgh_dispatcher as d
import rrgh_dispatch_audit as a
import test_rrgh_expanded_production as f

ROOT=Path(__file__).resolve().parents[2]

class RecoveryOnlyTests(unittest.TestCase):
    def fixture(self):
        run,jobs,receipt,producer,state=f.ZeroOutputRecoveryTests().fixture()
        state.update(sourceSHA='a'*40,mode='produce')
        run.update(status='completed',conclusion='failure')
        for j in jobs:j['run_id']=run['id']
        jobs[1].update(conclusion='failure',steps=[
            dict(name=r.SETUP_STEP,status='completed',conclusion='failure',number=7),
            dict(name=r.RECOVERY_STEP,status='completed',conclusion='skipped',number=8)])
        jobs.append(dict(name='advance',status='completed',conclusion='skipped',run_id=123))
        pref=dict(key=a.PREFIX+state['planSHA256']+'/slots/00001/receipt.json',generation='456',sha256='d'*64,bytes=1000)
        producer[-1]['receiptRef']=pref;receipt['result']['workerReceipt']=pref
        parent={**state,'producerReceipt':pref}
        newstate={**state,'runID':124,'dispatchID':'e'*64,'mode':'recover','recoveryOnlyOf':parent}
        newrun={**run,'id':124,'status':'in_progress','conclusion':None,
            'display_title':f"RRGH recovery {state['sequence']} "+newstate['dispatchID']}
        newjobs=[dict(name='bounded-stage',status='completed',conclusion='skipped',run_id=124),
            dict(name='independent-recovery',status='completed',conclusion='success',run_id=124)]
        execution=dict(run=newrun,jobs=newjobs,state=newstate)
        return run,jobs,receipt,producer,state,execution
    def audit(self,x):
        run,jobs,receipt,producer,state,execution=x
        return a.audit_run(run,jobs,[json.dumps(receipt)],[json.dumps(p) for p in producer],
            expected_dispatch=state,recovery_execution=execution)
    def test_actual_distinct_producer_and_recovery_run_bindings_are_required(self):
        x=self.fixture();self.assertTrue(self.audit(x)['verified'])
        self.assertEqual(r.producer_receipt([json.dumps(p) for p in x[3]],x[4]['planSHA256']),x[2]['result']['workerReceipt'])
        x[5]['jobs'][1]['run_id']=999
        with self.assertRaises(ValueError):self.audit(x)
    def test_no_recovery_that_may_have_started_can_retry(self):
        for conclusion in ('success','failure','cancelled',None):
            x=self.fixture();x[1][1]['steps'][1]['conclusion']=conclusion
            with self.assertRaises(ValueError):self.audit(x)
        x=self.fixture();x[1][0]['conclusion']='failure'
        with self.assertRaises(ValueError):self.audit(x)
    def test_mismatched_plan_source_dispatch_actor_and_replayed_production_rejected(self):
        for key in ('sequence','sourceSHA','planSHA256'):
            x=self.fixture();x[5]['state'][key]='forged'
            with self.assertRaises(ValueError):self.audit(x)
        for mode in ('dispatch','actor','rerun','produce','receipt'):
            x=self.fixture()
            if mode=='dispatch':x[5]['state']['recoveryOnlyOf']['dispatchID']='f'*64
            if mode=='actor':x[5]['run']['actor']=dict(login='intruder')
            if mode=='rerun':x[5]['run']['run_attempt']=2
            if mode=='produce':x[5]['jobs'][0]['conclusion']='success'
            if mode=='receipt':x[2]['result']['workerReceipt']={}
            with self.assertRaises((ValueError,a.Halt)):self.audit(x)
    def test_exact_original_failed_setup_is_required(self):
        x=self.fixture();x[1][1]['steps'][0]['name']='Some other failure'
        with self.assertRaises(ValueError):self.audit(x)
        x=self.fixture();x[1][1]['steps'][0]['number']=9
        with self.assertRaises(ValueError):self.audit(x)
    def test_arming_is_durable_and_only_one_recovery_dispatch_can_exist(self):
        x=self.fixture();run,jobs,receipt,producer,state,execution=x
        api=f.FakeGitHub();api.token='test';api.value.update(state,status='halted')
        api.head=state['sourceSHA'];api.value['recoveryStartAuthorization']={k:state[k] for k in ('runID','planSHA256','sourceSHA','dispatchID')}
        api.value['recoveryStartAuthorization'].update(authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-02',
            producerReceipt=receipt['result']['workerReceipt'])
        jobs[0]['id']=1000
        original=api.call
        def call(method,path,payload=None):
            if path=='actions/runs/123':return run
            if path=='actions/runs/123/jobs?per_page=100':return dict(total_count=len(jobs),jobs=jobs)
            return original(method,path,payload)
        api.call=call
        owner=f.RecoveredContinuationTests().owner()
        with patch.dict(os.environ,owner,clear=True),patch.object(a,'gh',return_value='\n'.join(json.dumps(p) for p in producer)):
            result=d.arm_unstarted_recovery(api,ROOT)
            self.assertEqual(result['mode'],'recover');self.assertEqual(api.value['status'],'dispatching')
            self.assertEqual(api.value['recoveryOnlyOf']['producerReceipt'],receipt['result']['workerReceipt'])
            with self.assertRaises(d.Halt):d.arm_unstarted_recovery(api,ROOT)
        self.assertEqual(sum(c[0]=='POST' for c in api.calls),1)

if __name__=='__main__':unittest.main()
