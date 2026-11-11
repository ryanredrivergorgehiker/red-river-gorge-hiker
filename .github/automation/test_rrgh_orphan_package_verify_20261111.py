"""No-Cloud tests for the single stranded 2026-11-11 package verify slot."""
import copy
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import rrgh_orphan_package_verify_20261111 as fix


def fixtures():
    s=dict(format='rrgh-controller-state-v1',owner='autonomous-v1',epoch=1,
        enabled=True,status='running',mode='package',runID=fix.ORIGINAL_RUN,
        sequence=1462,dispatchID=fix.DISPATCH,sourceSHA=fix.SOURCE,
        planSHA256=fix.RASTER_PLAN,controlDigest=fix.CONTROL,
        completionProgress=dict(acceptedRasterTiles=278278,remainingRasterTiles=0,
            finalPackageDeliveryComplete=False),
        package=dict(ordinal=18,planSHA256=fix.PACKAGE_PLAN,retryCount=1,
            operation=dict(kind='parts',parts=[dict(partID='core-%03d'%i) for i in range(8)]),
            lastVerified=dict(ordinal=16,verifiedParts=0,verifiedIndexes=0),
            retainedFailures=[dict(runID=43090539453)]))
    q=dict(format='rrgh-queued-verify-v1',action='verify-only-not-restage',
        authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-11',
        previousRunID=fix.ORIGINAL_RUN,stageJobID=fix.STAGE_JOB,
        unfinishedVerifyJobID=fix.UNSTARTED_VERIFY_JOB,packagePlanSHA256=fix.PACKAGE_PLAN,
        sourceSHA=fix.SOURCE,priorStateBlobSHA=fix.STATE_BLOB,
        stageReceipt=copy.deepcopy(fix.STAGE_RECEIPT),
        noSourceReadsOrWrites=True,noArchiveRestaging=True,noCatalogActivation=True,
        newVerifierSlot=1,independentReadbackRequired=True)
    return s,q


class BoundaryTests(unittest.TestCase):
    def test_exact_owner_and_pinned_accepted_cursor(self):
        s,q=fixtures()
        self.assertIs(fix.exact_state(s,q),s['package'])
        self.assertEqual(s['status'],'running')
        self.assertEqual(s['package']['lastVerified']['verifiedParts'],0)
        self.assertNotIn('catalogCandidates',q)

    def test_mutations_fail_before_any_allocation(self):
        s,q=fixtures()
        changes=[
            ('status',lambda a,b:a.update(status='halted')),
            ('mode',lambda a,b:a.update(mode='produce')),
            ('raster',lambda a,b:a['completionProgress'].update(acceptedRasterTiles=277587)),
            ('remaining',lambda a,b:a['completionProgress'].update(remainingRasterTiles=1)),
            ('accepted',lambda a,b:a['completionProgress'].update(finalPackageDeliveryComplete=True)),
            ('run',lambda a,b:a.update(runID=1)),
            ('plan',lambda a,b:a['package'].update(planSHA256='a'*64)),
            ('source',lambda a,b:a.update(sourceSHA='a'*40)),
            ('digest',lambda a,b:a.update(controlDigest='b'*64)),
            ('currentOrdinal',lambda a,b:a['package'].update(ordinal=19)),
            ('priorOrdinal',lambda a,b:a['package']['lastVerified'].update(ordinal=17)),
            ('doubleClaim',lambda a,b:a['package'].update(retryCount=2)),
            ('retained',lambda a,b:a['package'].update(retainedFailures=[])),
            ('parts',lambda a,b:a['package']['operation']['parts'].pop()),
            ('disabled',lambda a,b:a.update(enabled=False)),
            ('owner',lambda a,b:b.update(authorizedBy='attacker')),
            ('date',lambda a,b:b.update(authorizedOn='2026-11-10')),
            ('action',lambda a,b:b.update(action='restage')),
            ('stageRef',lambda a,b:b['stageReceipt'].update(generation='42')),
            ('stageHash',lambda a,b:b['stageReceipt'].update(sha256='0'*64)),
            ('priorState',lambda a,b:b.update(priorStateBlobSHA='f'*40)),
            ('newStage',lambda a,b:b.update(noArchiveRestaging=False)),
            ('sourceWrites',lambda a,b:b.update(noSourceReadsOrWrites=False)),
            ('noVerify',lambda a,b:b.update(independentReadbackRequired=False)),
            ('catalog',lambda a,b:b.update(noCatalogActivation=False)),
            ('slot',lambda a,b:b.update(newVerifierSlot=0)),
            ('unknown',lambda a,b:b.update(moreAuthority=True)),
        ]
        for name,change in changes:
            state,request=copy.deepcopy(s),copy.deepcopy(q)
            change(state,request)
            with self.subTest(name=name),self.assertRaises(ValueError):
                fix.exact_state(state,request)

    def test_workflow_actor_and_rerun_attempt_both_fail_closed(self):
        from rrgh_dispatcher import REPO,WORKER
        e=dict(GITHUB_REPOSITORY=REPO,GITHUB_REF='refs/heads/'+WORKER,
            GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_NAME='push',GITHUB_ACTOR='ryanredrivergorgehiker',
            GITHUB_WORKFLOW_REF=REPO+'/'+fix.WORKFLOW+'@refs/heads/'+WORKER,
            GITHUB_REPOSITORY_ID='1325611891',
            GITHUB_REPOSITORY_OWNER_ID='313924954',GITHUB_RUN_ID='500')
        fix.identity(e)
        for key,bad in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_ACTOR','github-actions[bot]'),
            ('GITHUB_EVENT_NAME','workflow_dispatch'),('GITHUB_REF','refs/heads/main'),
            ('GITHUB_WORKFLOW_REF','unreviewed.yml'),('GITHUB_RUN_ID','bad')]:
            altered=dict(e,**{key:bad})
            with self.subTest(key=key),self.assertRaises(ValueError):fix.identity(altered)

    def test_only_successful_staging_and_never_run_verifier(self):
        from rrgh_dispatcher import REPO,WORKER,WORKFLOW
        s,_=fixtures()
        run=dict(id=fix.ORIGINAL_RUN,status='completed',conclusion='failure',
            run_attempt=1,path='.github/workflows/'+WORKFLOW,head_branch=WORKER,
            repository=dict(full_name=REPO),actor=dict(login='github-actions[bot]'),
            display_title='RRGH package 1462 '+fix.DISPATCH)
        jobs=[
            dict(name='admit',id=1,status='completed',conclusion='success'),
            dict(name='package-stage',id=fix.STAGE_JOB,status='completed',conclusion='success'),
            dict(name='package-verify',id=fix.UNSTARTED_VERIFY_JOB,status='queued',
                conclusion=None,runner_name=None)]
        class Fake:
            def __init__(self,r,j):self.run=r;self.jobs=j
            def call(self,method,path):
                return self.run if '/jobs' not in path else dict(total_count=len(self.jobs),jobs=self.jobs)
        fix.original_jobs(Fake(run,jobs),s)
        mutations=[
            lambda a,b:a.update(status='in_progress'),
            lambda a,b:a.update(conclusion='success'),
            lambda a,b:b[1].update(conclusion='failure'),
            lambda a,b:b[2].update(status='completed'),
            lambda a,b:b[2].update(runner_name='GitHub Actions 1'),
            lambda a,b:b[2].update(conclusion='cancelled'),
            lambda a,b:b.append(dict(name='package-stage',conclusion='success')),
        ]
        for change in mutations:
            a,b=copy.deepcopy(run),copy.deepcopy(jobs)
            change(a,b)
            with self.assertRaises(ValueError):fix.original_jobs(Fake(a,b),s)

    def test_no_cloud_work_when_state_blob_changed(self):
        state,request=fixtures()
        class API:
            def state(self):return 'f'*40,state
        with patch('builtins.open',create=True):
            with patch.object(Path,'read_text',return_value=__import__('json').dumps(request)):
                with self.assertRaises(ValueError):
                    fix.preflight(API(),Path('.'))


if __name__=='__main__':unittest.main()
