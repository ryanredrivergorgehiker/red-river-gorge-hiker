"""Offline failure/race tests. Fixtures are synthetic, never production evidence."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import rrgh_dispatcher as d
ROOT=Path(__file__).resolve().parents[2]
SOURCE_ROOT=Path(os.environ.get('RRGH_TEST_SOURCE','rrgh-source')).resolve()
sys.path.insert(0,str(SOURCE_ROOT/'backend/scripts'))
import gorge_producer_identity as identity


def state():
    return dict(format='rrgh-controller-state-v1',owner='autonomous-v1',epoch=1,
        enabled=True,status='awaiting-auth',sequence=58,sourceSHA='a'*40,planSHA256='b'*64,
        controlDigest=d.local_digest(ROOT),legacyFenceSHA256=d.digest((ROOT/d.ORIGINAL).read_bytes()),
        githubReservedUSD='286.53')


class FakeGitHub:
    def __init__(self):
        self.value=state();self.version='1';self.calls=[];self.ambiguous=False;self.active=[]
        self.head=self.value['sourceSHA'];self.legacy=(ROOT/d.ORIGINAL).read_bytes()
    def state(self):return self.version,copy.deepcopy(self.value)
    def cas(self,old,value,message):
        if old!=self.version:raise d.Halt('CAS conflict')
        self.value=copy.deepcopy(value);self.version=str(int(self.version)+1);return self.version
    def file(self,path):return {},self.legacy
    def call(self,method,path,payload=None):
        self.calls.append((method,path,payload))
        if path.startswith('actions/runs?'):return dict(total_count=len(self.active),workflow_runs=self.active)
        if path.startswith('git/ref/'):return dict(object=dict(sha=self.head))
        if method=='POST' and path.endswith('/dispatches'):
            if self.ambiguous:raise TimeoutError('lost response after acceptance')
            return {}
        raise AssertionError((method,path))


class DispatcherTests(unittest.TestCase):
    def launch(self,api=None):
        api=api or FakeGitHub();sha,s=api.state();d.dispatch(api,ROOT,sha,s,'probe');return api
    def inputs(self,api):
        s=api.value
        return dict(source_sha=s['sourceSHA'],plan_sha256=s['planSHA256'],dispatch_id=s['dispatchID'],
                    mode=s['mode'],sequence=str(s['sequence']))
    def test_claim_is_durable_before_post_and_duplicate_cannot_launch(self):
        api=self.launch();self.assertEqual(api.value['status'],'dispatching')
        sha,s=api.state()
        with self.assertRaises(d.Halt):d.dispatch(api,ROOT,sha,s,'probe')
        self.assertEqual(sum(c[0]=='POST' for c in api.calls),1)
    def test_ambiguous_post_retains_allocation_and_reservation(self):
        api=FakeGitHub();api.ambiguous=True
        with self.assertRaises(TimeoutError):self.launch(api)
        self.assertEqual(api.value['status'],'dispatching');self.assertEqual(api.value['githubReservedUSD'],'286.63')
        with self.assertRaises(d.Halt):self.launch(api)
        self.assertEqual(sum(c[0]=='POST' for c in api.calls),1)
    def test_concurrent_stale_writer_cannot_dispatch(self):
        api=FakeGitHub();old,s=api.state();self.launch(api)
        with self.assertRaises(d.Halt):d.dispatch(api,ROOT,old,s,'probe')
        self.assertEqual(sum(c[0]=='POST' for c in api.calls),1)
    def test_only_one_worker_can_claim(self):
        api=self.launch();inputs=self.inputs(api);d.claim(api,ROOT,inputs,123)
        self.assertEqual(api.value['runID'],123);self.assertEqual(api.value['status'],'probing')
        with self.assertRaises(d.Halt):d.claim(api,ROOT,inputs,124)
    def test_wrong_worker_inputs_never_claim(self):
        for key in ('source_sha','plan_sha256','dispatch_id','sequence','mode'):
            with self.subTest(key=key):
                api=self.launch();inputs=self.inputs(api);inputs[key]='forged'
                with self.assertRaises(d.Halt):d.claim(api,ROOT,inputs,123)
                self.assertEqual(api.value['status'],'dispatching')
    def test_source_lease_change_blocks_launch_and_claim(self):
        api=FakeGitHub();api.head='c'*40
        with self.assertRaises(d.Halt):self.launch(api)
        self.assertEqual(api.version,'1')
        api=self.launch();api.head='c'*40
        with self.assertRaises(d.Halt):d.claim(api,ROOT,self.inputs(api),123)
    def test_active_old_or_new_producer_blocks_launch(self):
        for path in (d.ORIGINAL,'.github/workflows/'+d.WORKFLOW):
            api=FakeGitHub();api.active=[dict(id=999,path=path)]
            with self.assertRaises(d.Halt):self.launch(api)
            self.assertEqual(api.version,'1')
    def test_completed_parent_is_only_allowed_active_producer(self):
        api=FakeGitHub();api.active=[dict(id=123,path='.github/workflows/'+d.WORKFLOW)]
        api.value['status']='ready';old,s=api.state();d.dispatch(api,ROOT,old,s,'produce',allowed_run=123)
        self.assertEqual(api.value['parentRunID'],123);self.assertEqual(api.value['githubReservedUSD'],'291.53')
    def test_budget_stop_happens_before_mutation(self):
        for value in ('349.95','350','-1','NaN'):
            api=FakeGitHub();api.value['githubReservedUSD']=value
            with self.assertRaises(d.Halt):self.launch(api)
            self.assertEqual(api.version,'1')
    def test_legacy_fence_cannot_be_partially_removed(self):
        api=FakeGitHub();api.legacy=api.legacy.replace(b'if: false',b'if: true',1)
        with self.assertRaises(d.Halt):self.launch(api)
        self.assertEqual(api.version,'1')
    def test_paused_or_unreviewed_controller_cannot_launch(self):
        for key,value in [('enabled',False),('controlDigest','c'*64),('epoch',2),('owner','legacy')]:
            api=FakeGitHub();api.value[key]=value
            with self.assertRaises(d.Halt):self.launch(api)
    def test_launch_caller_requires_owner_and_exact_workflow(self):
        env=dict(GITHUB_REPOSITORY=d.REPO,GITHUB_REF='refs/heads/'+d.WORKER,GITHUB_RUN_ATTEMPT='1',
            GITHUB_ACTOR='ryanredrivergorgehiker',GITHUB_EVENT_NAME='push',
            GITHUB_WORKFLOW_REF=d.REPO+'/.github/workflows/rrgh-controller-launch.yml@refs/heads/'+d.WORKER)
        with patch.dict(os.environ,env,clear=True):d.caller('launch')
        for key in env:
            bad={**env,key:'untrusted'}
            with patch.dict(os.environ,bad,clear=True),self.assertRaises(d.Halt):d.caller('launch')


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((SOURCE_ROOT/'backend/config/gorge-campaign-wave-058-20261102/PLAN.json').read_bytes())
        self.env={**identity.COMMON,'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_ACTOR':'github-actions[bot]',
            'GITHUB_WORKFLOW_REF':d.REPO+'/.github/workflows/'+d.WORKFLOW+'@refs/heads/'+d.WORKER,
            'RRGH_SOURCE_SHA':'a'*40,'RRGH_PLAN_SHA256':d.digest(d.canonical(self.plan)),
            'RRGH_DISPATCH_ID':'c'*64,'GITHUB_RUN_ID':'123'}
        self.s={**state(),'status':'running','runID':123,'dispatchID':'c'*64,'planSHA256':self.env['RRGH_PLAN_SHA256']}
    def test_exact_automatic_identity_and_owner_pass(self):identity.validate_owner(self.s,self.plan,'produce',self.env)
    def test_every_identity_dimension_is_required(self):
        for key in self.env:
            with self.subTest(key=key),self.assertRaises(ValueError):
                identity.validate_owner(self.s,self.plan,'produce',{**self.env,key:'untrusted'})
    def test_every_ownership_dimension_is_required(self):
        for key,value in [('owner','legacy'),('epoch',2),('status','ready'),('runID',124),('sequence',59),
                          ('sourceSHA','b'*40),('dispatchID','d'*64),('planSHA256','d'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                identity.validate_owner({**self.s,key:value},self.plan,'produce',self.env)
    def test_paused_owner_can_finish_recovery_but_not_start_jobs(self):
        s={**self.s,'enabled':False};identity.validate_owner(s,self.plan,'recovery',self.env)
        with self.assertRaises(ValueError):identity.validate_owner(s,self.plan,'produce',self.env)
    def test_original_push_identity_preserved_but_fenced_from_new_controller(self):
        env={**self.env,'GITHUB_EVENT_NAME':'push','GITHUB_ACTOR':'ryanredrivergorgehiker',
             'GITHUB_WORKFLOW_REF':d.REPO+'/'+d.ORIGINAL+'@refs/heads/'+d.WORKER}
        self.assertEqual(identity.validate_context(env),'push')
        with self.assertRaises(ValueError):identity.validate_owner(self.s,self.plan,'produce',env)
        legacy=copy.deepcopy(self.plan);legacy['campaign'].pop('controllerEpoch')
        identity.validate_owner(dict(owner='legacy',enabled=True),legacy,'produce',env)
    def test_changed_plan_content_rejected_even_with_matching_sequence(self):
        changed=copy.deepcopy(self.plan);changed['maxConcurrency']=2
        with self.assertRaises(ValueError):identity.validate_owner(self.s,changed,'produce',self.env)


if __name__=='__main__':unittest.main()
