"""Failure/race injection for receipt-only handoffs; no network or Cloud access."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import rrgh_dispatcher as d
import rrgh_handoff as h

ROOT=Path(__file__).resolve().parents[2]
ENV=dict(GITHUB_REPOSITORY=d.REPO,GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',
    GITHUB_WORKFLOW_REF=d.REPO+'/.github/workflows/'+h.WORKFLOW+'@refs/heads/main',
    GITHUB_EVENT_NAME='schedule',GITHUB_ACTOR='ryanredrivergorgehiker',GITHUB_RUN_ID='900')
RECEIPT=dict(bytes=1497,generation='123',sha256='d'*64,key='exact-immutable-recovery')
AUDIT=dict(receiptRef=RECEIPT,acceptedJobs=15185,acceptedRasterTiles=156172,jobsNew=12,tilesNew=122)


class API:
    def __init__(self):
        self.value=dict(format='rrgh-controller-state-v1',owner='autonomous-v1',epoch=1,enabled=True,
            status='halted',mode='produce',sequence=387,runID=387,dispatchID='c'*64,
            sourceSHA='a'*40,planSHA256='b'*64,controlDigest=d.local_digest(ROOT),
            automaticHandoffRecovery=copy.deepcopy(h.POLICY),checkpoint={'sha256':'old'},
            lastRecovered={'sequence':386},batchPilotEnabled=False)
        self.version=0;self.writes=[];self.calls=[];self.older_status='completed';self.head='a'*40
        self.fail_write=None
    def state(self):return self.version,copy.deepcopy(self.value)
    def cas(self,old,state,message):
        if old!=self.version:raise d.Halt('competing owner')
        self.version+=1;self.value=copy.deepcopy(state);self.writes.append(copy.deepcopy(state))
        return self.version
    def call(self,method,path,payload=None):
        self.calls.append((method,path,payload))
        if method==self.fail_write:raise TimeoutError('ambiguous write')
        if path.startswith('actions/runs?'):return dict(total_count=0,workflow_runs=[])
        if path.startswith('actions/runs/'):return dict(status=self.older_status,conclusion='failure')
        if path=='git/ref/heads/'+d.SOURCE:return {'object':{'sha':self.head}}
        if path.startswith('git/commits/') and method=='GET':return {'tree':{'sha':'tree'}}
        if path=='git/trees':return {'sha':'new-tree'}
        if path=='git/commits':return {'sha':'e'*40}
        if method=='PATCH':self.head=payload['sha'];return {}
        raise AssertionError((method,path))


class HandoffTests(unittest.TestCase):
    def setUp(self):
        patch.dict(os.environ,ENV,clear=True).start()
        self.audit=patch.object(d,'audit_state',return_value=copy.deepcopy(AUDIT)).start()
        self.api=API();self.addCleanup(patch.stopall)
    def prepare(self):return h.prepare(self.api,ROOT)
    def test_verified_receipt_claim_preserves_consumed_allocation_and_counts(self):
        before=copy.deepcopy(self.api.value);result=self.prepare()
        self.assertTrue(result['active']);self.assertEqual(result['audit'],AUDIT)
        self.assertEqual(self.api.value['status'],'handoff-pending')
        for key in (*h.PINS,'checkpoint','lastRecovered','batchPilotEnabled'):
            self.assertEqual(self.api.value[key],before[key])
        self.assertEqual(self.api.value['handoffPending']['recoveryReceipt'],RECEIPT)
        self.assertTrue(all(c[0]=='GET' for c in self.api.calls))
    def test_healthy_paused_unclaimed_and_nonproduction_states_never_recover(self):
        initial=copy.deepcopy(self.api.value)
        for key,value in [('status','running'),('status','dispatching'),('status','publishing'),
                          ('mode','recover'),('mode','complete'),('enabled',False),('automaticHandoffRecovery',{})]:
            self.api.value={**initial,key:value}
            self.assertFalse(self.prepare()['active']);self.assertEqual(self.api.version,0)
        self.audit.assert_not_called()
    def test_failed_independent_verification_never_claims_or_publishes(self):
        self.audit.side_effect=ValueError('recovery failed')
        with self.assertRaisesRegex(ValueError,'recovery failed'):self.prepare()
        self.assertEqual(self.api.version,0)
    def test_run_must_be_terminal_before_recovery(self):
        self.api.older_status='in_progress'
        with self.assertRaisesRegex(d.Halt,'completed failed'):self.prepare()
        self.audit.assert_not_called();self.assertEqual(self.api.version,0)
    def test_ambiguous_publication_is_never_replayed(self):
        self.api.value['publicationOf']=h.pins(self.api.value)
        with self.assertRaisesRegex(d.Halt,'unresolved'):self.prepare()
        self.audit.assert_not_called();self.assertEqual(self.api.version,0)
    def test_changed_source_never_claims(self):
        self.api.head='f'*40
        with self.assertRaisesRegex(d.Halt,'Source lease changed'):self.prepare()
        self.assertEqual(self.api.version,0)
    def test_live_reconciler_cannot_be_replaced(self):
        self.prepare();self.api.older_status='in_progress'
        with self.assertRaisesRegex(d.Halt,'still owns'):self.prepare()
        self.assertEqual(self.api.version,1)
    def test_interrupted_preparation_can_resume_only_after_owner_finished(self):
        self.prepare()
        with patch.dict(os.environ,GITHUB_RUN_ID='901'):self.prepare()
        pending=self.api.value['handoffPending']
        self.assertEqual(pending['reconcilerRunID'],901);self.assertEqual(pending['preparationAttempts'],2)
        self.assertEqual(pending['recoveryReceipt'],RECEIPT)
    def test_release_preserves_receipt_and_bounded_future_attempts(self):
        self.prepare();h.release(self.api,ROOT)
        self.assertIsNone(self.api.value['handoffPending']['reconcilerRunID'])
        self.prepare();h.release(self.api,ROOT);self.prepare();h.release(self.api,ROOT)
        with self.assertRaisesRegex(d.Halt,'attempts exhausted'):self.prepare()
        self.assertEqual(self.api.value['handoffPending']['recoveryReceipt'],RECEIPT)
    def test_each_original_pin_and_receipt_must_survive_pending(self):
        self.prepare();initial=copy.deepcopy(self.api.value)
        for key in (*h.PINS,'recoveryReceipt'):
            self.api.value=copy.deepcopy(initial);self.api.value['handoffPending'][key]='changed'
            with self.assertRaises(d.Halt):h.audit_pending(self.api,ROOT)
    def test_failed_recheck_cannot_publish(self):
        self.prepare();self.audit.return_value={'receiptRef':{'sha256':'changed'}}
        with patch.object(d,'candidate_entries') as candidate,self.assertRaisesRegex(d.Halt,'receipt changed'):
            d.publish_and_advance(self.api,ROOT,None,AUDIT,automatic=True)
        candidate.assert_not_called();self.assertEqual(self.api.version,1)
    def test_competing_cas_blocks_publication(self):
        self.prepare();original_cas=self.api.cas
        def competing(*args):self.api.version+=1;return original_cas(*args)
        with patch.object(self.api,'cas',side_effect=competing),patch.object(d,'candidate_entries',return_value=self.candidate()),self.assertRaisesRegex(d.Halt,'competing'):
            d.publish_and_advance(self.api,ROOT,None,AUDIT,automatic=True)
        self.assertTrue(all(c[0]=='GET' for c in self.api.calls))
    def candidate(self):
        return 'a'*40,'f'*64,{'campaign':{'sequence':388}},[{'path':'backend/config/gorge-campaign-wave-388-20261102/PLAN.json'}]
    def test_success_settles_once_and_dispatches_fresh_sequence(self):
        self.prepare()
        with patch.object(d,'candidate_entries',return_value=self.candidate()),patch.object(d,'dispatch') as dispatch:
            d.publish_and_advance(self.api,ROOT,None,AUDIT,automatic=True)
        final=self.api.value
        self.assertEqual(final['sequence'],388);self.assertEqual(final['lastRecovered']['acceptedRasterTiles'],156172)
        self.assertEqual(final['lastRecovered']['tilesNew'],122);self.assertEqual(final['checkpoint'],RECEIPT)
        self.assertNotIn('publicationOf',final);self.assertNotIn('handoffPending',final)
        self.assertEqual(len(final['handoffRecoveryHistory']),1)
        self.assertEqual(dispatch.call_args.args[4],'produce')
        self.assertEqual(dispatch.call_args.kwargs,{'allowed_run':387})
        self.assertEqual(h.release(self.api,ROOT)['status'],'OTHER_OR_ADVANCED_OWNER_PRESERVED')
    def test_source_write_timeout_retains_publication_marker_and_never_retries(self):
        self.prepare();self.api.fail_write='PATCH'
        with patch.object(d,'candidate_entries',return_value=self.candidate()),patch.object(d,'dispatch') as dispatch,self.assertRaises(TimeoutError):
            d.publish_and_advance(self.api,ROOT,None,AUDIT,automatic=True)
        dispatch.assert_not_called();self.assertEqual(self.api.value['status'],'publishing')
        self.assertEqual(h.release(self.api,ROOT)['status'],'UNRESOLVED_WRITE_PRESERVED')
        self.assertEqual(len([c for c in self.api.calls if c[0]=='PATCH']),1)
    def test_ready_successor_can_finish_dispatch_but_claim_is_not_replayed(self):
        self.api.value.update(status='ready',sequence=388,runID=None,dispatchID=None,checkpoint=RECEIPT,
            lastRecovered=dict(sequence=387,runID=387,recoveryReceipt=RECEIPT))
        with patch.object(d,'dispatch') as dispatch:self.assertFalse(self.prepare()['active'])
        dispatch.assert_called_once();self.audit.assert_not_called()
        self.api.value['status']='dispatching'
        with patch.object(d,'dispatch') as dispatch:self.assertFalse(self.prepare()['active'])
        dispatch.assert_not_called()
    def test_ready_requires_settled_predecessor(self):
        self.api.value.update(status='ready',runID=None,dispatchID=None)
        with self.assertRaisesRegex(d.Halt,'settled recovery'):self.prepare()


class InRunHandoffTests(unittest.TestCase):
    def setUp(self):
        self.env={**ENV,'GITHUB_REF':'refs/heads/'+d.WORKER,'GITHUB_JOB':'resume-handoff',
            'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTOR':'github-actions[bot]',
            'GITHUB_WORKFLOW_REF':d.REPO+'/.github/workflows/'+d.WORKFLOW+'@refs/heads/'+d.WORKER,
            'GITHUB_RUN_ID':'387','RRGH_DISPATCH_ID':'c'*64}
        patch.dict(os.environ,self.env,clear=True).start()
        self.audit=patch.object(d,'audit_state',return_value=copy.deepcopy(AUDIT)).start()
        self.api=API();self.jobs=[dict(name=n,conclusion=c,status='completed') for n,c in
            [('bounded-stage','success'),('independent-recovery','success'),('advance','failure'),('retain-failure','success')]]
        original=self.api.call
        def call(method,path,payload=None):
            if path=='actions/runs/387':return dict(status='in_progress',conclusion=None)
            if path=='actions/runs/387/jobs?per_page=100':return dict(total_count=len(self.jobs),jobs=self.jobs)
            return original(method,path,payload)
        self.api.call=call;self.addCleanup(patch.stopall)
    def test_exact_failed_handoff_recovers_inside_original_workflow(self):
        result=h.prepare(self.api,ROOT)
        self.assertTrue(result['active']);self.assertEqual(self.api.value['handoffPending']['reconcilerRunID'],387)
        with patch.object(d,'candidate_entries',return_value=('a'*40,'f'*64,{'campaign':{'sequence':388}},[{'path':'backend/config/gorge-campaign-wave-388-20261102/PLAN.json'}])),patch.object(d,'dispatch') as dispatch:
            d.publish_and_advance(self.api,ROOT,None,AUDIT,automatic=True)
        self.assertEqual(self.api.value['sequence'],388)
        self.assertEqual(self.api.value['lastRecovered']['acceptedRasterTiles'],156172)
        dispatch.assert_called_once()
    def test_original_active_run_is_permitted_but_another_producer_is_not(self):
        original=self.api.call
        for rid in (387,999):
            def call(method,path,payload=None):
                if path.startswith('actions/runs?'):return dict(total_count=1,workflow_runs=[dict(id=rid,path='.github/workflows/'+d.WORKFLOW)])
                return original(method,path,payload)
            self.api.call=call
            if rid==387:self.assertEqual(h.evidence(self.api,ROOT,self.api.value),AUDIT)
            else:
                with self.assertRaisesRegex(d.Halt,'Another producer'):h.evidence(self.api,ROOT,self.api.value)
    def test_failed_worker_or_missing_failed_advance_never_qualifies(self):
        initial=copy.deepcopy(self.jobs)
        for index,conclusion in ((0,'failure'),(1,'failure'),(2,'success')):
            self.jobs=copy.deepcopy(initial);self.jobs[index]['conclusion']=conclusion
            with self.assertRaisesRegex(d.Halt,'controller-only'):h.prepare(self.api,ROOT)
        self.assertEqual(self.api.version,0);self.audit.assert_not_called()
    def test_other_run_or_dispatch_claim_never_qualifies(self):
        for key,value in [('GITHUB_RUN_ID','999'),('RRGH_DISPATCH_ID','e'*64)]:
            with patch.dict(os.environ,{key:value}),self.assertRaisesRegex(d.Halt,'exact allocation'):h.prepare(self.api,ROOT)
        self.assertEqual(self.api.version,0)
    def test_every_inrun_identity_dimension_is_required(self):
        h.caller()
        for key in self.env:
            if key in ('GITHUB_RUN_ID','RRGH_DISPATCH_ID'):continue
            with patch.dict(os.environ,{key:'untrusted'}),self.assertRaises(d.Halt):h.caller()
    def test_sibling_job_cannot_use_active_run_exception(self):
        with patch.dict(os.environ,GITHUB_JOB='bounded-stage'),self.assertRaises(d.Halt):h.prepare(self.api,ROOT)
    def test_workflow_requires_successful_verification_and_has_no_cloud_credentials(self):
        job=(ROOT/'.github/workflows'/d.WORKFLOW).read_text().split('\n  resume-handoff:\n',1)[1]
        for gate in ("needs.bounded-stage.result == 'success'","needs.independent-recovery.result == 'success'",
                     "needs.advance.result == 'failure'","needs.retain-failure.result == 'success'"):
            self.assertIn(gate,job)
        self.assertNotIn('id-token:',job)
        self.assertNotIn('google-github-actions',job)


class CallerAndReadTests(unittest.TestCase):
    def test_exact_workflow_identity_and_first_attempt_required(self):
        with patch.dict(os.environ,ENV,clear=True):h.caller()
        for key in ENV:
            if key=='GITHUB_RUN_ID':continue
            with patch.dict(os.environ,{**ENV,key:'untrusted'},clear=True),self.assertRaises(d.Halt):h.caller()
    def test_bot_allowed_only_for_completed_workflow_event(self):
        for event in ('push','schedule','workflow_dispatch'):
            with patch.dict(os.environ,{**ENV,'GITHUB_ACTOR':'github-actions[bot]','GITHUB_EVENT_NAME':event},clear=True),self.assertRaises(d.Halt):h.caller()
        with patch.dict(os.environ,{**ENV,'GITHUB_ACTOR':'github-actions[bot]','GITHUB_EVENT_NAME':'workflow_run'},clear=True):h.caller()
    def test_status_can_settle_after_original_short_window(self):
        api=API()
        with patch.object(api,'call',side_effect=[{'status':'queued'}]*4+[{'status':'in_progress'}]) as call,patch.object(d.time,'sleep') as sleep:
            self.assertEqual(d.read_audit_run(api,387)['status'],'in_progress')
            self.assertEqual(call.call_count,5);self.assertEqual(sum(c.args[0] for c in sleep.call_args_list),110)
    def test_persistent_status_reports_exact_value_and_stops(self):
        api=API()
        with patch.object(api,'call',return_value={'status':'waiting'}) as call,patch.object(d.time,'sleep'),self.assertRaisesRegex(d.Halt,"status='waiting'"):
            d.read_audit_run(api,387)
        self.assertEqual(call.call_count,5)


if __name__=='__main__':unittest.main()
