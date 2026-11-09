"""Actual GitHub scheduler incident; no Cloud execution or synthetic acceptance."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import rrgh_recovery_only as r
import rrgh_dispatcher as d
import rrgh_handoff as h
from test_rrgh_handoff import API, ENV
from test_rrgh_recovery_only import RecoveryOnlyTests

ROOT=Path(__file__).resolve().parents[2]

def fixture():
    return json.loads((Path(__file__).parent/'fixtures/wave1358-unscheduled-recovery.json').read_bytes())

class UnscheduledTests(unittest.TestCase):
    def test_actual1358_saved108_outputs_only_unused_verification_is_eligible(self):
        f=fixture();r.eligible_parent(f['run'],f['jobs']['jobs'],f['state'])
        receipt=r.producer_receipt([json.dumps(p) for p in f['producer']],f['state']['planSHA256'])
        self.assertEqual(receipt['sha256'],'94f2ad8d683f93b7fa77ed097dd59992184c38ec81a00f12618a931949a04ea7')
        self.assertEqual(f['producer'][0]['jobs'],108)
        self.assertEqual(f['producer'][0]['sourceRequests'],0)

    def test_active_ambiguous_started_and_changed_identity_never_qualify(self):
        for fault in ('active','rerun','producer','admission','other-started','recovery-present','foreign-job','duplicate','missing-advance'):
            f=fixture();jobs=f['jobs']['jobs']
            if fault=='active':f['run'].update(status='in_progress',conclusion=None)
            elif fault=='rerun':f['run']['run_attempt']=2
            elif fault=='producer':r.one(jobs,'bounded-stage')['conclusion']='failure'
            elif fault=='admission':r.one(jobs,'admit')['conclusion']='failure'
            elif fault=='other-started':r.one(jobs,'independent-completion')['conclusion']='success'
            elif fault=='recovery-present':jobs.append(dict(name='independent-recovery',run_id=f['run']['id'],status='completed',conclusion='skipped'))
            elif fault=='foreign-job':jobs[0]['run_id']=123
            elif fault=='duplicate':jobs.append(copy.deepcopy(jobs[0]))
            else:jobs[:]=[j for j in jobs if j['name']!='advance']
            with self.subTest(fault=fault),self.assertRaises(ValueError):r.eligible_parent(f['run'],jobs,f['state'])

    def test_split_recovery_still_requires_independent_success_and_same_producer(self):
        test=RecoveryOnlyTests();x=test.fixture()
        x[1][:]=[j for j in x[1] if j['name']!='independent-recovery']
        x[1].append(dict(name='admit',status='completed',conclusion='success',run_id=x[0]['id']))
        self.assertTrue(test.audit(x)['verified'])
        x[5]['jobs'][1]['conclusion']='failure'
        with self.assertRaises(Exception):test.audit(x)

    def test_detached_handoff_arms_once_and_rejects_incomplete_inventory(self):
        f=fixture();api=API();api.token='test';api.value.update(f['state'],status='running')
        api.head=f['state']['sourceSHA'];original=api.call
        def call(method,path,payload=None):
            if path=='actions/runs/'+str(f['run']['id']):return f['run']
            if path=='actions/runs/'+str(f['run']['id'])+'/jobs?per_page=100':return f['jobs']
            return original(method,path,payload)
        api.call=call
        logs='\n'.join(json.dumps(p) for p in f['producer'])
        with patch.dict(os.environ,ENV,clear=True),patch('rrgh_dispatch_audit.gh',return_value=logs),patch.object(d,'dispatch',return_value={'mode':'recover'}) as dispatch:
            f['jobs']['total_count']+=1
            with self.assertRaises(d.Halt):h.prepare(api,ROOT)
            self.assertEqual(api.version,0);dispatch.assert_not_called()
            f['jobs']['total_count']-=1
            result=h.prepare(api,ROOT)
            self.assertEqual(result['unusedRecovery']['mode'],'recover')
            self.assertEqual(api.value['status'],'recovery-ready')
            self.assertEqual(api.value['recoveryOnlyOf']['runID'],f['run']['id'])
            self.assertEqual(api.value['recoveryOnlyOf']['producerReceipt'],f['producer'][0]['receiptRef'])
            self.assertFalse(h.prepare(api,ROOT)['active'])
            dispatch.assert_called_once()
            self.assertEqual(dispatch.call_args.args[4],'recover')
        self.assertEqual(api.value['lastRecovered'],{'sequence':386})

if __name__=='__main__':unittest.main()
