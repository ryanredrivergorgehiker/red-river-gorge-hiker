"""No-Cloud positive/negative tests for accepted eight-part receipt-only CAS."""
import copy
import json
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rrgh_archive_receipt_reconcile_20261111 as fix


class OneTimeReceiptTests(unittest.TestCase):
    def good_env(self):
        from rrgh_dispatcher import REPO,WORKER
        return dict(GITHUB_REPOSITORY=REPO,GITHUB_REF='refs/heads/'+WORKER,
            GITHUB_RUN_ATTEMPT='1',GITHUB_EVENT_NAME='push',
            GITHUB_ACTOR='ryanredrivergorgehiker',
            GITHUB_WORKFLOW_REF=REPO+'/'+fix.WORKFLOW+'@refs/heads/'+WORKER,
            GITHUB_REPOSITORY_ID='1325611891',
            GITHUB_REPOSITORY_OWNER_ID='313924954',GITHUB_RUN_ID='500')

    def test_exact_owner_nonrerun_github_only(self):
        env=self.good_env()
        fix.owner_identity(env)
        for key,bad in [('GITHUB_REF','refs/heads/main'),
                        ('GITHUB_ACTOR','github-actions[bot]'),
                        ('GITHUB_EVENT_NAME','workflow_dispatch'),
                        ('GITHUB_RUN_ATTEMPT','2'),
                        ('GITHUB_WORKFLOW_REF','unreviewed'),
                        ('GITHUB_RUN_ID','not-a-run'),
                        ('GITHUB_REPOSITORY_ID','42')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                fix.owner_identity(dict(env,**{key:bad}))

    def test_every_requested_boundary_is_pinned(self):
        req=fix.expected_request()
        self.assertTrue(req['noCloudRequests'])
        self.assertTrue(req['noCloudCredentials'])
        self.assertTrue(req['noNextPackageDispatch'])
        self.assertTrue(req['noVerifierSlotReplay'])
        self.assertTrue(req['noArchiveRestaging'])
        self.assertTrue(req['noRasterGeneration'])
        self.assertFalse(req['noCatalogActivation'] is False)
        self.assertEqual(req['acceptedParts'],8)
        self.assertEqual(req['previousStateBlobSHA'],fix.STATE_BLOB)
        self.assertEqual(req['verifiedReceipt'],fix.VERIFY_RECEIPT)
        self.assertEqual(req['verifiedCheckpoint'],fix.VERIFY_CHECKPOINT)

    def good_run_and_jobs(self):
        from rrgh_dispatcher import REPO,WORKER,WORKFLOW
        run=dict(id=fix.VERIFIER_RUN,status='completed',conclusion='failure',
            run_attempt=1,event='workflow_dispatch',
            path='.github/workflows/'+WORKFLOW,
            head_sha=fix.VERIFIER_HEAD,head_branch=WORKER,
            repository=dict(full_name=REPO),actor=dict(login='github-actions[bot]'),
            display_title='RRGH queued-package-verification 1462 '+
                'f66aaf8623842a4cda678ecd2568db540fd915c0736d3770e9e14d454852b56f')
        jobs=[dict(name='orphan-verify',id=fix.VERIFIER_JOB,
                    status='completed',conclusion='success'),
              dict(name='orphan-reconcile',id=fix.FAILED_RECONCILE_JOB,
                    status='completed',conclusion='failure')]
        return run,jobs

    def test_only_successful_bot_verifier_and_known_failed_reconcile(self):
        a,b=self.good_run_and_jobs()
        fix.verify_job_identity(a,b)
        tests=[
            lambda x,y:x.update(status='in_progress'),
            lambda x,y:x.update(conclusion='success'),
            lambda x,y:x.update(event='push'),
            lambda x,y:x.update(head_sha='0'*40),
            lambda x,y:x.update(run_attempt=2),
            lambda x,y:x['actor'].update(login='ryanredrivergorgehiker'),
            lambda x,y:y[0].update(conclusion='failure'),
            lambda x,y:y[0].update(status='queued'),
            lambda x,y:y[1].update(conclusion='success'),
            lambda x,y:y[1].update(id=1),
            lambda x,y:y.append(copy.deepcopy(y[0]))]
        for change in tests:
            q,w=copy.deepcopy(a),copy.deepcopy(b)
            change(q,w)
            with self.assertRaises(ValueError):fix.verify_job_identity(q,w)

    def verified_fixture(self):
        row=dict(phase='final-package-verify',receiptRef=copy.deepcopy(fix.VERIFY_RECEIPT),
            rescue=dict(format='rrgh-cross-run-verify-only-v1',
                originalRunID=fix.ORIGINAL_RUN,verifierRunID=fix.VERIFIER_RUN,
                noRestaging=True,sourceRequests=0),
            result=dict(status='verified',ordinal=18,
                workerReceipt=copy.deepcopy(fix.STAGE_RECEIPT),
                checkpoint=copy.deepcopy(fix.VERIFY_CHECKPOINT),
                packagePlanSHA256=fix.PACKAGE_PLAN,verifiedParts=8,verifiedIndexes=0,
                rasterTiles=278278,sourceRequests=0,sourceBytes=0,
                packageBytesIndependentlyVerified=False,
                finalPackageDeliveryComplete=False,physicalIPhoneTestComplete=False))
        return row

    def test_verified_receipt_identity_and_failure_mutations(self):
        original=self.verified_fixture()
        fix.verified_report([json.dumps(original)])
        mutations=[
            lambda a:a['receiptRef'].update(generation='2'),
            lambda a:a['receiptRef'].update(sha256='0'*64),
            lambda a:a['rescue'].update(verifierRunID=1),
            lambda a:a['rescue'].update(noRestaging=False),
            lambda a:a['result'].update(sourceRequests=1),
            lambda a:a['result'].update(verifiedParts=7),
            lambda a:a['result'].update(verifiedIndexes=3),
            lambda a:a['result'].update(packageBytesIndependentlyVerified=True),
            lambda a:a['result'].update(finalPackageDeliveryComplete=True),
            lambda a:a['result'].update(physicalIPhoneTestComplete=True),
            lambda a:a['result']['checkpoint'].update(sha256='0'*64),
            lambda a:a['result'].update(workerReceipt={}),
            lambda a:a.update(phase='final-package-stage')]
        for change in mutations:
            a=copy.deepcopy(original)
            change(a)
            with self.assertRaises(ValueError):fix.verified_report([json.dumps(a)])

    def test_no_cloud_dispatch_or_archive_restaging_code(self):
        here=Path(__file__).parent
        workflow=(here.parent/'workflows/rrgh-archive-reconcile-only.yml').read_text()
        source=(here/'rrgh_archive_receipt_reconcile_20261111.py').read_text()
        assert 'google-github-actions/auth' not in workflow
        assert 'id-token: write' not in workflow
        assert 'workflow_dispatch:' not in workflow
        assert 'contents: write' in workflow
        assert 'No Cloud credentials' in workflow
        assert 'dispatch(api,' not in source
        assert 'api.cas(old_sha,next_state,' in source
        assert "status='package-ready'" in source
        assert "Decimal('124.25')" in source
        assert 'sourceRequests=0' in source
        assert 'sourceWrites=0' in source


if __name__=='__main__':unittest.main()
