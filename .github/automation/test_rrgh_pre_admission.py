"""Synthetic regression evidence; does not establish live Cloud acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import rrgh_dispatcher as d

ROOT = Path(__file__).resolve().parents[2]


class API:
    token = 'synthetic'

    def __init__(self):
        self.value = dict(format='rrgh-controller-state-v1', owner='autonomous-v1', epoch=1,
            enabled=True, status='dispatching', mode='produce', runID=None, sequence=236,
            sourceSHA='a'*40, planSHA256='b'*64, dispatchID='c'*64, launchCounter=186,
            controlDigest='d'*64, checkpoint={'sha256':'e'*64},
            lastRecovered={'sequence':235,'runID':234,'recoveryReceipt':{'sha256':'e'*64}},
            overviewPilotEnabled=True, sourcePolicyMode='expanded',
            githubBudgetPolicy={'enforcement':'github-platform','authorizedBy':'ryanredrivergorgehiker',
                'authorizedOn':'2026-11-02','stopProtectionConfirmedByOwner':True},
            legacyFenceSHA256=d.digest(b'# RRGH_LEGACY_INITIATION_FENCED_EPOCH_1\nif: false'),
            legacyPlannerFenceSHA256=d.digest(b'if: false'))
        self.original = copy.deepcopy(self.value)
        self.head = self.value['sourceSHA']
        self.version = '1'
        self.writes = []
        self.posts = []
        self.active = []
        self.conflict = False
        self.ambiguous = False
        self.request = dict(action='resume-unclaimed', authorizedBy='ryanredrivergorgehiker',
            date='2026-11-03', original_run=236, failure_head_sha='f'*40,
            source_sha='a'*40, plan_sha256='b'*64, dispatch_id='c'*64)
        self.run = dict(id=236, head_sha='f'*40, head_branch=d.WORKER,
            path='.github/workflows/'+d.WORKFLOW, event='workflow_dispatch',
            actor={'login':'github-actions[bot]'}, triggering_actor={'login':'github-actions[bot]'},
            run_attempt=1, status='completed', conclusion='failure',
            display_title='RRGH production 236 '+'c'*64)
        names=['admit','bounded-stage','authentication-probe','checkpoint-inspection',
            'finish-inspection','activate','independent-recovery','independent-salvage',
            'advance','retain-failure']
        self.jobs=[dict(id=i+1000,run_id=236,name=name,status='completed',
            conclusion='failure' if name=='admit' else 'skipped') for i,name in enumerate(names)]
        self.jobs[0]['steps']=[dict(name='Atomically claim the exact controller allocation before Cloud authentication',
            conclusion='failure')]
        self.duplicates=[self.run]

    def state(self):
        return self.version,copy.deepcopy(self.value)

    def cas(self,old,value,message):
        if self.conflict or old!=self.version:raise d.Halt('CAS conflict')
        self.value=copy.deepcopy(value);self.version=str(int(self.version)+1)
        self.writes.append(message)
        return self.version

    def file(self,path,ref=None):
        if path==d.STATE:return {},d.canonical(self.original)
        if path==d.ORIGINAL:return {},b'# RRGH_LEGACY_INITIATION_FENCED_EPOCH_1\nif: false'
        if path==d.LEGACY_PLANNER:return {},b'if: false'
        raise AssertionError(path)

    def call(self,method,path,payload=None):
        if path=='actions/runs/236':return copy.deepcopy(self.run)
        if path=='actions/runs/236/jobs?per_page=100':return {'total_count':len(self.jobs),'jobs':self.jobs}
        if path.startswith('actions/runs?head_sha='):return {'total_count':len(self.duplicates),'workflow_runs':self.duplicates}
        if path.startswith('actions/runs?status='):return {'total_count':len(self.active),'workflow_runs':self.active}
        if path.startswith('git/ref/'):return {'object':{'sha':self.head}}
        if method=='POST':
            self.posts.append(payload)
            if self.ambiguous:raise TimeoutError('response lost')
            return {}
        raise AssertionError((method,path))


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.api=API()
        self.log='2026-11-03T13:10:42Z CONTROLLER_STOP: GitHub GET contents/.github/automation/rrgh-controller-state.json HTTP 500; no automatic retry\n'
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'.github/automation').mkdir(parents=True)

    def resume(self,digest='d'*64):
        (self.root/'.github/automation/rrgh-controller-request.json').write_bytes(d.canonical(self.api.request))
        with patch.object(d,'caller'),patch.object(d,'local_digest',return_value=digest),\
                patch('rrgh_dispatch_audit.gh',return_value=self.log):
            return d.resume_unclaimed(self.api,self.root)

    def rejected(self):
        with self.assertRaises(d.Halt):self.resume()
        self.assertEqual(self.api.writes,[])
        self.assertEqual(self.api.posts,[])

    def test_proven_unclaimed_dispatch_gets_unique_probe_preserving_history(self):
        before=copy.deepcopy(self.api.value)
        result=self.resume()
        self.assertEqual(result['mode'],'probe')
        self.assertEqual(self.api.posts[0]['inputs']['mode'],'probe')
        self.assertEqual(self.api.value['launchCounter'],187)
        self.assertNotEqual(self.api.value['dispatchID'],before['dispatchID'])
        for key in ('sourceSHA','planSHA256','sequence','checkpoint','lastRecovered','overviewPilotEnabled','sourcePolicyMode'):
            self.assertEqual(before[key],self.api.value[key])
        self.assertEqual(self.api.value['unclaimedAdmissionHistory'][0]['runID'],236)
        with self.assertRaises(d.Halt):self.resume()
        self.assertEqual(len(self.api.posts),1)

    def test_every_execution_identity_dimension_required(self):
        for key in self.api.run:
            with self.subTest(key=key):
                self.api=API();self.api.run[key]=None;self.rejected()

    def test_exact_owner_request_required(self):
        for key in self.api.request:
            with self.subTest(key=key):
                self.api=API();self.api.request[key]=None;self.rejected()

    def test_no_cloud_or_ambiguous_job_can_be_restarted(self):
        for i in range(1,10):
            for result in ('success','failure','cancelled',None):
                with self.subTest(job=i,result=result):
                    self.api=API();self.api.jobs[i]['conclusion']=result;self.rejected()

    def test_missing_or_duplicate_job_is_rejected(self):
        self.api.jobs.pop();self.rejected()
        self.api=API();self.api.jobs[-1]=self.api.jobs[0];self.rejected()

    def test_unknown_or_write_failure_is_not_retried(self):
        for log in ('','CONTROLLER_STOP: GitHub PUT contents/.github/automation/rrgh-controller-state.json HTTP 500; no automatic retry',
                    self.log+self.log,self.log.replace('500','403'),self.log.replace('GET contents','POST contents')):
            with self.subTest(log=log):
                self.log=log;self.rejected()

    def test_completed_duplicate_and_active_worker_are_rejected(self):
        self.api.duplicates.append({**self.api.run,'id':237});self.rejected()
        self.api=API();self.api.active=[{'id':237,'path':'.github/workflows/'+d.WORKFLOW}];self.rejected()

    def test_moved_source_or_changed_original_state_is_rejected(self):
        self.api.head='0'*40;self.rejected()
        for key in ('checkpoint','lastRecovered','controlDigest','launchCounter'):
            self.api=API();self.api.original[key]=None;self.rejected()

    def test_claimed_or_disabled_state_is_rejected(self):
        for key,value in [('runID',236),('status','running'),('enabled',False),('mode','recover')]:
            self.api=API();self.api.value[key]=value;self.rejected()

    def test_cas_conflict_never_dispatches(self):
        self.api.conflict=True;self.rejected()

    def test_lost_probe_response_retains_claim_without_second_dispatch(self):
        self.api.ambiguous=True
        with self.assertRaises(TimeoutError):self.resume()
        self.assertEqual(self.api.value['mode'],'probe')
        self.assertEqual(self.api.value['status'],'dispatching')
        with self.assertRaises(d.Halt):self.resume()
        self.assertEqual(len(self.api.posts),1)

    def test_reviewed_code_upgrade_is_consumed_with_failed_run_provenance(self):
        self.api.value['pendingControllerUpgrade']=dict(fromDigest='d'*64,toDigest='1'*64,
            authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-02',preserveAcceptedHistory=True)
        self.resume(digest='1'*64)
        self.assertEqual(self.api.value['controlDigest'],'1'*64)
        self.assertNotIn('pendingControllerUpgrade',self.api.value)
        self.assertEqual(self.api.value['controllerUpgradeHistory'][-1]['failedAdmissionRunID'],236)


class ReadRetryTests(unittest.TestCase):
    def request(self,method,codes):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{}'
        opener=MagicMock();opener.open.side_effect=[HTTPError('synthetic',code,'error',{},None) for code in codes]+[response]
        with patch.object(d,'build_opener',return_value=opener),patch.object(d.time,'sleep'):
            try:result=d.GitHub('synthetic').call(method,'synthetic')
            except d.Halt:result='halted'
        return result,opener.open.call_count

    def test_get_transient_server_errors_retry_at_most_twice(self):
        self.assertEqual(self.request('GET',[500,503]),({},3))
        self.assertEqual(self.request('GET',[500,502,504]),('halted',3))

    def test_no_write_or_authorization_error_retries(self):
        for method in ('POST','PUT','PATCH','DELETE'):
            self.assertEqual(self.request(method,[500]),('halted',1))
        for code in (401,403,404,409,429):
            self.assertEqual(self.request('GET',[code]),('halted',1))


if __name__=='__main__':unittest.main()
