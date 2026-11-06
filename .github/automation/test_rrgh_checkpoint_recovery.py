"""Original wave613 log evidence plus synthetic failure/ownership cases.

Cloud inspection and receipt result fixtures are synthetic, not accepted output.
"""
import copy
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import rrgh_checkpoint_recovery as c
import rrgh_dispatcher as d
import rrgh_handoff as h
import rrgh_wif_credentials as w
import rrgh_credential_integration as ci
from test_rrgh_dispatcher import FakeGitHub

ROOT=Path(__file__).resolve().parents[2]


def fixture():
    f=json.loads((Path(__file__).parent/'fixtures/wave613-checkpoints.json').read_bytes())
    f['plan']['completedJobIDs']=['previous-'+str(i) for i in range(f['plan']['campaign']['carry']['priorCompletedJobs'])]
    return f


class OriginalAPI:
    token='test-only'
    def __init__(self,f):self.f=f
    def file(self,path,ref=None):
        assert path==d.STATE and ref==self.f['run']['head_sha']
        return {},d.canonical({**self.f['state'],'status':'dispatching','runID':None})
    def call(self,method,path):
        assert method=='GET'
        return self.f['jobs'] if '/jobs?' in path else self.f['run']


def original_fixture(f=None):
    f=fixture() if f is None else f
    with patch.object(c,'plan_at',return_value=f['plan']),patch('rrgh_dispatch_audit.gh',return_value='\n'.join(map(json.dumps,f['producerRows']))):
        return c.original(OriginalAPI(f),f['state']),f


def inspection(m,p):
    prefix='engineering/map-production/plans/'+m['planSHA256']+'/slots/'
    rows=[dict(key=prefix+f'{s:05d}/{n}.json',exists=False) for s in range(3) for n in ('claim','receipt')]
    rows.extend(dict(key=prefix+'00001/jobs/'+j+'.json',exists=False) for j in p['approvedJobIDs'])
    indexed={r['key']:r for r in rows}
    claim=dict(key=prefix+'00001/claim.json',generation='1234',bytes=400,sha256='c'*64)
    indexed[claim['key']].update(exists=True,ref=claim,record=dict(owner=str(m['originalRunID']),
        planSHA256=m['planSHA256'],slot=1,allocation=p['slots'][1]))
    indexed[prefix+'00000/receipt.json'].update(exists=True,ref=m['bootstrapReceipt'],record=dict(result=dict(status='ready')))
    for j,r in zip(m['completedJobIDs'],m['completedJobRefs'],strict=True):
        indexed[r['key']].update(exists=True,ref=r,record=dict(job=j,planSHA256=m['planSHA256'],slot=1))
    return dict(planSHA256=m['planSHA256'],sequence=m['sequence'],cloudWrites=0,sourceRequests=0,
        readRequests=32,readResponseBytes=30000,objects=rows)


def result_fixture(m):
    from rrgh_campaign_budget_v2 import cost
    v=m['originalAllocation'];prior=m['priorCarry']
    carry=dict(prior,chargedUSD=str(Decimal(prior['chargedUSD'])+cost(v)),storedBytes=prior['storedBytes']+v['storedBytes'],
        priorCompletedJobs=prior['priorCompletedJobs']+m['jobs'],priorRasterTiles=prior['priorRasterTiles']+m['tiles'])
    r=dict(status='partial-verified',salvage=c.KIND,originalProducerRunID=m['originalRunID'],workerReceipt=None,
        producerClaim=dict(key='engineering/map-production/plans/'+m['planSHA256']+'/slots/00001/claim.json',bytes=400,generation='1234',sha256='c'*64),
        bootstrapReceipt=m['bootstrapReceipt'],completedJobRefs=m['completedJobRefs'],completedJobIDs=m['completedJobIDs'],
        uncertainJobIDs=m['uncertainJobIDs'],jobs=m['jobs'],tiles=m['tiles'],verifiedTileCatalogTiles=m['tiles'],
        sourceJobsExecuted=0,adjacentEdgesMeasured=80,packageParts=7,packageBytes=1000000,
        allOutputHashesAndPixelsVerified=True,allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,
        unacceptedAttemptsQuarantined=True,sourcePinsReconstructed=dict(allPriorPinsPreserved=True),nextCarry=carry,
        settlement=dict(sequence=m['sequence'],planSHA256=m['planSHA256'],originalAllocation=v,retainedUsage=v,
            demonstrablyUnused={k:0 for k in v},ambiguousAllocationRetained=True,independentRecoveryComplete=False,
            chargedUSD=carry['chargedUSD'],storedBytes=carry['storedBytes']))
    return dict(phase='independent-checkpoint-salvage',result=r,receiptRef=dict(bytes=2200,generation='9999',sha256='d'*64,
        key='engineering/map-production/plans/'+m['planSHA256']+'/slots/00002/receipt.json'))


class CheckpointTests(unittest.TestCase):
    def test_actual_613_log_establishes_ten_checkpoints_not_accepted_output(self):
        (m,p),f=original_fixture()
        self.assertEqual((m['jobs'],m['tiles'],len(m['uncertainJobIDs'])),(10,76,2))
        self.assertEqual(m['priorCarry']['priorRasterTiles'],183459)
        self.assertEqual(m['completedJobIDs'],p['approvedJobIDs'][:10])
    def test_original_identity_and_job_evidence_fail_closed(self):
        for fault in ('rerun','actor','title','incomplete','recovery','admit','retention','producer'):
            f=fixture()
            if fault=='rerun':f['run']['run_attempt']=2
            elif fault=='actor':f['run']['actor']['login']='other'
            elif fault=='title':f['run']['display_title']='forged'
            elif fault=='incomplete':f['jobs']['total_count']+=1
            else:
                name={'recovery':'independent-recovery','admit':'admit','retention':'retain-failure','producer':'bounded-stage'}[fault]
                next(j for j in f['jobs']['jobs'] if j['name']==name)['conclusion']='success' if fault in ('recovery','producer') else 'failure'
            with self.subTest(fault=fault),self.assertRaises(d.Halt):original_fixture(f)
    def test_noncredential_failure_closure_or_pixel_gaps_cannot_use_recovery(self):
        for fault in ('reason','closure','gap','prefix','count','reference','no-checkpoints'):
            f=fixture();rows=f['producerRows'];jobs=[r for r in rows if 'durableJobReceipt' in r]
            if fault=='reason':rows[-1]['frames']=[]
            elif fault=='closure':rows.append(dict(phase='production'))
            elif fault=='gap':rows.append(dict(status='source-pixel-gap-quarantined'))
            elif fault=='prefix':jobs[0]['job']=f['plan']['approvedJobIDs'][-1]
            elif fault=='count':jobs[0]['completedJobs']=5
            elif fault=='reference':jobs[0]['durableJobReceipt']['sha256']='broken'
            else:f['producerRows']=[r for r in rows if 'durableJobReceipt' not in r]
            with self.subTest(fault=fault),self.assertRaises(d.Halt):original_fixture(f)
    def test_paired_overview_and_previous_attempts_are_not_eligible(self):
        for fault in ('batch','overview','worker','attempt','budget'):
            f=fixture();p=f['plan']
            if fault=='batch':p['resumableBatch']={}
            elif fault=='overview':p['overviewPilot']={}
            elif fault=='worker':p['maxConcurrency']=2
            elif fault=='attempt':p['priorAttemptCounts'][p['approvedJobIDs'][0]]=1
            else:p['campaign']['ceilingUSD']='999'
            with self.subTest(fault=fault),self.assertRaises(d.Halt):original_fixture(f)
    def test_inspection_requires_exact_saved_refs_and_unused_recovery(self):
        (m,p),_=original_fixture();e=inspection(m,p)
        actual=c.inspect_manifest(m,p,e)
        self.assertEqual(actual['jobs'],10);self.assertEqual(actual['inspectionUsage']['classBRequests'],32)
        for fault in ('claim2','receipt2','closure','unknown','missing','ref','owner','allocation','duplicate','overflow'):
            changed=copy.deepcopy(e);rows=changed['objects']
            if fault in ('claim2','receipt2','closure'):
                key={'claim2':'00002/claim.json','receipt2':'00002/receipt.json','closure':'00001/receipt.json'}[fault]
                next(r for r in rows if r['key'].endswith(key))['exists']=True
            elif fault=='unknown':next(r for r in rows if m['uncertainJobIDs'][0]+'.json' in r['key'])['exists']=True
            elif fault=='missing':rows.pop()
            elif fault=='ref':next(r for r in rows if r['key']==m['completedJobRefs'][0]['key'])['ref']['sha256']='e'*64
            elif fault=='owner':next(r for r in rows if r['key'].endswith('00001/claim.json'))['record']['owner']='other'
            elif fault=='allocation':next(r for r in rows if r['key'].endswith('00001/claim.json'))['record']['allocation']={}
            elif fault=='duplicate':rows.append(copy.deepcopy(rows[0]))
            else:changed['readRequests']=65
            with self.subTest(fault=fault),self.assertRaises(d.Halt):c.inspect_manifest(m,p,changed)
    def test_verified_partial_carry_is_inclusive_and_fully_charged(self):
        (m,p),f=original_fixture();r=result_fixture(m)
        report=c.validate_report(m,r,{**f['state'],'runID':999})
        self.assertEqual(report['acceptedRasterTiles'],183535)
        self.assertEqual(report['acceptedJobs'],17895)
        self.assertEqual(report['tilesNew'],76)
        self.assertGreater(Decimal(report['nextCarry']['chargedUSD']),Decimal(m['priorCarry']['chargedUSD']))
    def test_corrupt_or_unverified_partial_results_are_rejected(self):
        for fault in ('tiles','pixel','package','pins','source','refund','carry','receipt','identity','unknown'):
            (m,p),f=original_fixture();r=result_fixture(m);v=r['result']
            if fault=='tiles':v['tiles']+=1
            elif fault=='pixel':v['allOutputHashesAndPixelsVerified']=False
            elif fault=='package':v['allNewPackageChunksReadBack']=False
            elif fault=='pins':v['sourcePinsReconstructed']['allPriorPinsPreserved']=False
            elif fault=='source':v['sourceJobsExecuted']=1
            elif fault=='refund':v['settlement']['demonstrablyUnused']['storedBytes']=1
            elif fault=='carry':v['nextCarry']['priorRasterTiles']+=76
            elif fault=='receipt':r['receiptRef']['key']='other'
            elif fault=='identity':v['originalProducerRunID']=1
            else:v['uncertainJobIDs']=[]
            with self.subTest(fault=fault),self.assertRaises(d.Halt):c.validate_report(m,r,f['state'])


class OwnershipTests(unittest.TestCase):
    def prepared(self):
        (m,p),f=original_fixture();api=FakeGitHub();api.value.update(f['state']);api.head=f['state']['sourceSHA']
        api.value['checkpointRecoveryPolicy']=copy.deepcopy(c.POLICY)
        return api,m,p
    def test_owner_recovery_claims_once_and_never_dispatches_produce(self):
        api,m,p=self.prepared()
        with patch.object(d,'caller'),patch.object(c,'original',return_value=(m,p)):
            r=c.arm(api,ROOT)
            self.assertEqual(r['mode'],'checkpoints');self.assertEqual(api.value['mode'],'checkpoints')
            self.assertEqual(api.value['checkpointRecoveryOf']['runID'],m['originalRunID'])
            with self.assertRaises(d.Halt):c.arm(api,ROOT)
        posts=[x for x in api.calls if x[0]=='POST']
        self.assertEqual(len(posts),1);self.assertEqual(posts[0][2]['inputs']['mode'],'checkpoints')
    def test_uncertain_dispatch_is_retained_without_retry(self):
        api,m,p=self.prepared();api.ambiguous=True
        with patch.object(d,'caller'),patch.object(c,'original',return_value=(m,p)):
            with self.assertRaises(TimeoutError):c.arm(api,ROOT)
            with self.assertRaises(d.Halt):c.arm(api,ROOT)
        self.assertEqual(api.value['status'],'dispatching');self.assertEqual(sum(x[0]=='POST' for x in api.calls),1)
    def test_paused_wrong_policy_active_or_consumed_state_never_claims(self):
        for fault in ('disabled','policy','active','consumed','published','source'):
            api,m,p=self.prepared()
            if fault=='disabled':api.value['enabled']=False
            elif fault=='policy':api.value['checkpointRecoveryPolicy']['maxRecoveryAttempts']=2
            elif fault=='active':api.active=[dict(id=22,path='.github/workflows/'+d.WORKFLOW)]
            elif fault=='consumed':api.value['mode']='checkpoints'
            elif fault=='published':api.value['publicationOf']={'runID':3}
            else:api.head='f'*40
            with patch.object(d,'caller'),patch.object(c,'original',return_value=(m,p)):
                with self.subTest(fault=fault),self.assertRaises(d.Halt):c.arm(api,ROOT)
            self.assertEqual(api.version,'1')
    def test_original_inrun_fallback_owns_exact_failed_producer(self):
        api,m,p=self.prepared()
        with patch.dict(os.environ,dict(GITHUB_JOB='resume-handoff',GITHUB_RUN_ID=str(m['originalRunID']),RRGH_DISPATCH_ID=m['originalDispatchID']),clear=True),patch.object(c,'original',return_value=(m,p)) as original:
            c.arm(api,ROOT,automatic=True);self.assertTrue(original.call_args.kwargs['active'])
    def test_hourly_handoff_selects_credential_checkpoint_route(self):
        api,m,p=self.prepared();api.value['automaticHandoffRecovery']=h.POLICY
        old_call=api.call
        def call(method,path,payload=None):
            if '/jobs?' in path:return fixture()['jobs']
            return old_call(method,path,payload)
        api.call=call
        with patch.object(h,'caller'),patch.object(c,'original',return_value=(m,p)):
            r=h.prepare(api,ROOT)
        self.assertFalse(r['active']);self.assertEqual(r['checkpointRecovery']['mode'],'checkpoints')
    def test_inrun_handoff_routes_failed_producer_after_retention(self):
        # Exercise the same handoff entry the real restricted workflow invokes.
        api,m,p=self.prepared();api.value['automaticHandoffRecovery']=h.POLICY
        old_call=api.call
        api.call=lambda method,path,payload=None: fixture()['jobs'] if '/jobs?' in path else old_call(method,path,payload)
        with patch.object(h,'caller'),patch.object(c,'original',return_value=(m,p)) as original,patch.dict(os.environ,
            dict(GITHUB_JOB='resume-handoff',GITHUB_RUN_ID=str(m['originalRunID']),RRGH_DISPATCH_ID=m['originalDispatchID']),clear=True):
            h.prepare(api,ROOT)
            self.assertTrue(original.call_args.kwargs['active'])
        self.assertEqual(api.value['mode'],'checkpoints')


class CredentialDiagnosticsTests(unittest.TestCase):
    def test_safe_categories_never_emit_token_or_raw_error(self):
        from types import SimpleNamespace
        w._VALUE=None;w._UNTIL=0
        with patch.object(w.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='SECRET-TOKEN',stderr='permission_denied SECRET-CREDENTIAL')),patch.object(w.sys,'stderr',new_callable=io.StringIO) as output:
            with self.assertRaises(RuntimeError):w.token()
        self.assertNotIn('SECRET',output.getvalue());self.assertIn('rejected-or-invalid',output.getvalue())
        self.assertIn('storageRequestStarted',output.getvalue())
    def test_known_http_refresh_errors_retry_but_denials_win(self):
        for code in (408,429,500,502,503,504):self.assertTrue(w.transient('HTTP '+str(code)))
        self.assertFalse(w.transient('HTTP 503 permission_denied'))
        self.assertFalse(w.transient('HTTP 403'))
    def test_forward_credential_migration_accepts_only_reviewed_previous_module(self):
        current=(ROOT/'.github/automation/rrgh_wif_credentials.py').read_bytes()
        ci.validate_module(current,current)
        with self.assertRaises(ValueError):ci.validate_module(b'unreviewed',current)
        with self.assertRaises(ValueError):ci.validate_module(current,current+b'\n')


if __name__=='__main__':unittest.main()
