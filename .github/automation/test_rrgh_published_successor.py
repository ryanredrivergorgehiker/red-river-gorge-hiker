"""Inject split source/state publication failures; never access Cloud/network."""
import copy
import json
import os
import unittest
from unittest.mock import patch
import rrgh_dispatcher as d
import rrgh_handoff as h
from test_rrgh_handoff import API, ROOT, ENV, AUDIT, RECEIPT


class PublishedTests(unittest.TestCase):
    def setUp(self):
        patch.dict(os.environ,ENV,clear=True).start();self.addCleanup(patch.stopall)
        self.api=API()
        self.audit={**copy.deepcopy(AUDIT),'acceptedJobs':2,'acceptedRasterTiles':20,
            'nextCarry':{'priorCompletedJobs':2,'priorRasterTiles':20,'chargedUSD':'40.00','storedBytes':300}}
        self.plan={'campaign':{'sequence':388,'controllerEpoch':1,'previousRecovery':RECEIPT,
            'carry':self.audit['nextCarry'],'ceilingUSD':'125.00','storageTargetUSDPerMonth':'2.00'},
            'approvedJobIDs':['fresh'],'completedJobIDs':['old1','old2'],'priorAttemptCounts':{},
            'maxConcurrency':1,'automaticRetryPermitted':False,'deleteAllowed':False}
        self.plan_path='backend/config/gorge-campaign-wave-388-20261102/PLAN.json'
        self.proof={'sourceSHA':'e'*40,'planSHA256':d.digest(d.canonical(self.plan)),
            'sequence':388,'planPath':self.plan_path}
        self.api.value.update(recoveredReceipt=RECEIPT,
            publicationOf={**h.pins(self.api.value),'successor':copy.deepcopy(self.proof)})
        self.api.head='e'*40
        self.commit={'sha':'e'*40,'parents':[{'sha':'a'*40}]}
        original=self.api.call
        def call(method,path,payload=None):
            if method=='GET' and path=='git/commits/'+'e'*40:
                self.api.calls.append((method,path,payload));return self.commit
            return original(method,path,payload)
        self.api.call=call
        self.api.file=lambda path,ref: ({},d.canonical(self.plan)) if (path,ref)==(self.plan_path,'e'*40) else self.fail('wrong immutable read')
        self.audit_mock=patch.object(d,'audit_state',return_value=self.audit).start()
        self.dispatch=patch.object(d,'dispatch').start()
    def prepare(self):return h.prepare(self.api,ROOT)
    def rehash(self):self.api.value['publicationOf']['successor']['planSHA256']=d.digest(d.canonical(self.plan))
    def test_published_source_final_state_failure_settles_receipt_once_without_source_writes(self):
        before=copy.deepcopy(self.api.value)
        self.assertFalse(self.prepare()['active'])
        final=self.api.value
        self.assertEqual(final['sequence'],388);self.assertEqual(final['sourceSHA'],'e'*40)
        self.assertEqual(final['lastRecovered']['acceptedRasterTiles'],20)
        self.assertEqual(final['lastRecovered']['runID'],387);self.assertEqual(final['checkpoint'],RECEIPT)
        self.assertEqual(final['publicationRecoveryHistory'][0]['successor'],self.proof)
        self.assertEqual(final['batchPilotEnabled'],before['batchPilotEnabled'])
        self.assertTrue(all(c[0]=='GET' for c in self.api.calls));self.dispatch.assert_called_once()
    def test_old_or_unrelated_source_never_replayed(self):
        for head in ('a'*40,'f'*40):
            self.api.head=head
            with self.assertRaisesRegex(d.Halt,'Source lease'):self.prepare()
        self.assertEqual(self.api.version,0);self.dispatch.assert_not_called()
        self.assertTrue(all(c[0]=='GET' for c in self.api.calls))
    def test_each_pin_or_missing_proof_blocks_before_audit(self):
        original=copy.deepcopy(self.api.value)
        for key in h.PINS:
            self.api.value=copy.deepcopy(original);self.api.value['publicationOf'][key]='changed'
            with self.assertRaisesRegex(d.Halt,'unresolved'):self.prepare()
        self.api.value=copy.deepcopy(original);del self.api.value['publicationOf']['successor']
        with self.assertRaisesRegex(d.Halt,'unresolved'):self.prepare()
        self.audit_mock.assert_not_called();self.dispatch.assert_not_called()
    def test_successor_identity_must_be_bounded_exact_child(self):
        original=copy.deepcopy(self.api.value)
        for key,value in [('sourceSHA','a'*40),('sourceSHA','invalid'),('planSHA256','invalid'),
                          ('sequence',389),('planPath','backend/config/../PLAN.json')]:
            self.api.value=copy.deepcopy(original);self.api.value['publicationOf']['successor'][key]=value
            with self.assertRaisesRegex(d.Halt,'unresolved'):self.prepare()
        self.audit_mock.assert_not_called()
    def test_failed_original_verification_never_settles(self):
        self.audit_mock.side_effect=ValueError('independent recovery failed')
        with self.assertRaisesRegex(ValueError,'independent recovery'):self.prepare()
        self.assertEqual(self.api.version,0);self.dispatch.assert_not_called()
    def test_wrong_receipt_plan_hash_or_commit_parent_blocks(self):
        for mutate in ('receipt','hash','parent'):
            with self.subTest(mutate=mutate):
                before=copy.deepcopy(self.api.value);commit=copy.deepcopy(self.commit)
                if mutate=='receipt':self.api.value['recoveredReceipt']={}
                elif mutate=='hash':self.api.value['publicationOf']['successor']['planSHA256']='0'*64
                else:self.commit['parents']=[{'sha':'f'*40}]
                with self.assertRaises(d.Halt):self.prepare()
                self.api.value=before;self.commit=commit
        self.assertEqual(self.api.version,0);self.dispatch.assert_not_called()
    def test_fresh_allocation_and_inclusive_counts_required_even_with_matching_hash(self):
        original=copy.deepcopy(self.plan)
        for mutate in ('attempt','completed','carry','budget','concurrency'):
            self.plan=copy.deepcopy(original)
            if mutate=='attempt':self.plan['priorAttemptCounts']['fresh']=1
            if mutate=='completed':self.plan['approvedJobIDs']=['old1']
            if mutate=='carry':self.plan['campaign']['carry']['priorRasterTiles']+=1
            if mutate=='budget':self.plan['campaign']['ceilingUSD']='126.00'
            if mutate=='concurrency':self.plan['maxConcurrency']=2
            self.rehash()
            with self.assertRaisesRegex(d.Halt,'allocation mismatch'):self.prepare()
        self.assertEqual(self.api.version,0);self.dispatch.assert_not_called()
    def test_active_other_reconciler_blocks(self):
        self.api.value['handoffPending']={**h.pins(self.api.value),'recoveryReceipt':RECEIPT,'reconcilerRunID':777}
        self.api.older_status='in_progress'
        with self.assertRaisesRegex(d.Halt,'still owns'):self.prepare()
        self.assertEqual(self.api.version,0);self.audit_mock.assert_not_called()
    def test_competing_state_or_source_writer_cannot_be_overwritten(self):
        with patch.object(self.api,'cas',side_effect=d.Halt('competing owner')):
            with self.assertRaisesRegex(d.Halt,'competing owner'):self.prepare()
        self.dispatch.assert_not_called()
        original=self.api.file
        def moved(*args,**kwargs):self.api.head='f'*40;return original(*args,**kwargs)
        self.api.file=moved
        with self.assertRaisesRegex(d.Halt,'moved before settlement'):self.prepare()
        self.assertEqual(self.api.version,0)
    def test_lost_final_state_write_can_be_reconciled_later(self):
        with patch.object(self.api,'cas',side_effect=d.Halt('state write unavailable')):
            with self.assertRaisesRegex(d.Halt,'state write unavailable'):self.prepare()
        self.dispatch.assert_not_called();self.assertIn('publicationOf',self.api.value)
        self.prepare();self.assertEqual(len(self.api.value['publicationRecoveryHistory']),1)
        self.assertEqual(self.api.value['lastRecovered']['acceptedRasterTiles'],20)
    def test_ambiguous_dispatch_claim_is_never_replayed(self):
        def dispatch(api,root,old,state,mode,allowed_run):
            state=copy.deepcopy(state);state.update(status='dispatching',dispatchID='f'*64)
            api.cas(old,state,'claim');raise TimeoutError('dispatch response lost')
        self.dispatch.side_effect=dispatch
        with self.assertRaises(TimeoutError):self.prepare()
        self.assertFalse(self.prepare()['active']);self.dispatch.assert_called_once()
        self.assertEqual(len(self.api.value['publicationRecoveryHistory']),1)
    def test_successor_intent_is_durable_before_source_patch(self):
        self.api.value.pop('publicationOf');self.api.head='a'*40
        h.prepare(self.api,ROOT)
        original=self.api.call
        def call(method,path,payload=None):
            if method=='PATCH':
                self.assertEqual(self.api.value['publicationOf']['successor'],self.proof)
                self.api.head=payload['sha'];raise TimeoutError('applied ref, lost response')
            return original(method,path,payload)
        self.api.call=call
        candidate=('a'*40,self.proof['planSHA256'],self.plan,[{'path':self.plan_path}])
        with patch.object(d,'candidate_entries',return_value=candidate):
            with self.assertRaises(TimeoutError):d.publish_and_advance(self.api,ROOT,None,self.audit,automatic=True)
        self.api.value['status']='halted';self.api.call=original
        self.prepare();self.assertEqual(self.api.value['sequence'],388)
        self.assertTrue(all(c[0]!='PATCH' for c in self.api.calls))


if __name__=='__main__':unittest.main()
