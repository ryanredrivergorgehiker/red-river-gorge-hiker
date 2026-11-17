#!/usr/bin/env python3
"""No-Cloud, no-live-CAS fault injection for the one-time owner boundary."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/automation'))
sys.path.insert(0, str(ROOT / 'source/backend/scripts'))
import rrgh_dispatcher as d
import rrgh_package_contract as contract
import rrgh_halted_package_cas_dispatch_20261117 as once


CONTEXT = {
    'repository': d.REPO, 'ref': 'refs/heads/' + d.WORKER,
    'event': 'push', 'actor': once.OWNER,
    'triggeringActor': once.OWNER, 'runAttempt': 1,
    'workflowRef': d.REPO + '/.github/workflows/' +
        'rrgh-owner-package-recovery-activation.yml@refs/heads/' + d.WORKER,
}
NOW = datetime(2026, 11, 17, 17, tzinfo=timezone.utc)
REPORT = {
    'fullLayoutParts': 122, 'remainingParts': 90, 'finalIndexes': 3,
    'doubleCountsAccepted32': True, 'additionalTransportFailuresAssumed': 0,
    'totalModeledUSD': '105.0788062088',
    'modeledMonthlyStorageUSD': '1.8600851496',
}


class InMemoryGitHub:
    def __init__(self):
        raw = (ROOT / d.STATE).read_bytes()
        self.sha = once.git_blob(raw)
        self.state_body = json.loads(raw)
        self.cas_count = 0
    def state(self):
        return self.sha, deepcopy(self.state_body)
    def cas(self, old_sha, state, message):
        if old_sha != self.sha:
            raise d.Halt('CAS conflict')
        self.cas_count += 1
        self.state_body = deepcopy(state)
        self.sha = 'f' * 40
        return self.sha


class OneTimeCASReview(unittest.TestCase):
    def setUp(self):
        self.api = InMemoryGitHub()
        self.assertEqual(self.api.sha, once.LIVE_BLOB_SHA)
        self.p = self.api.state_body['package']
        self.plan = {'finalPackagePhase': {'controllerDigest': once.CANDIDATE_DIGEST},
                     'limits': {'sourceRequests': 0, 'sourceBytes': 0,
                                'storedBytes': 1}}
        self.cursor = deepcopy(self.p)
        self.cursor.update(ordinal=27, retryCount=0,
                           expiresAt='2026-11-18T10:00:00Z')
        self.request = {
            'format': once.AUTH_FORMAT,
            'action': 'resume-source-free-package-once',
            'authorizedBy': once.OWNER, 'candidatePR': 140,
            'candidateHeadSHA': once.CANDIDATE_HEAD_SHA,
            'fromControllerBlobSHA': once.LIVE_BLOB_SHA,
            'fromDigest': once.OLD_DIGEST, 'toDigest': once.CANDIDATE_DIGEST,
            'sourceSHA': once.ACCEPTED_SOURCE,
            'sourcePlanSHA256': once.SOURCED_PLAN,
            'failedRunID': 43290954679,
            'acceptedReceiptSHA256': once.ACCEPTED_RECEIPT,
            'acceptedCheckpoint': deepcopy(self.p['lastVerified']['checkpoint']),
            'failedOrdinal': 26, 'nextOrdinal': 27,
            'nextParts': deepcopy(once.REQUIRED_PARTS),
            'retainedFailures': 5, 'retryCountRetained': 2,
            'newPackagePlanSHA256': contract.digest(self.plan),
            'nextAllocationModeledUSD': '0.050',
            'wholeDeliveryModeledUSD': REPORT['totalModeledUSD'],
            'monthlyStorageModeledUSD': REPORT['modeledMonthlyStorageUSD'],
            'originalCampaignCeilingUSD': '125.00',
            'packageStopUSD': '122.25',
            'storageCeilingUSDPerMonth': '2.00',
            'finalDeliveryReserveUSD': '0.75', 'sourceRequests': 0,
            'preserveHistory': True, 'oneNewCloudDispatch': True,
            'catalogActivation': False, 'appRelease': False,
            'activationHelperGitBlobSHA': once.git_blob((ROOT /
                '.github/automation/rrgh_halted_package_cas_dispatch_20261117.py').read_bytes()),
            'activationWorkflowGitBlobSHA': once.git_blob((ROOT /
                '.github/workflows/rrgh-owner-package-recovery-activation.yml').read_bytes()),
            'activationRunnerGitBlobSHA': once.git_blob((ROOT /
                '.github/automation/rrgh_owner_package_activation_runner_20261117.py').read_bytes()),
            'authorizedAt': '2026-11-17T16:00:00Z',
            'expiresAt': '2026-11-18T10:00:00Z',
        }
        self.patches = [
            patch.object(d, 'local_digest', return_value=once.CANDIDATE_DIGEST),
            patch.object(once, 'recompute', return_value=deepcopy(REPORT)),
            patch.object(once, 'evidence',
                         return_value={'current': {'controllerBlobSHA': once.LIVE_BLOB_SHA}}),
            patch.object(once, 'source_context', return_value=({}, {})),
            patch.object(contract, 'allocate', side_effect=self.allocate),
            patch.object(once, 'cost', return_value=Decimal('0.050')),
            patch.object(once, 'monthly', return_value=Decimal('1.86')),
            patch.object(once, 'verify_fences'),
        ]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def allocate(self, *args):
        return deepcopy(self.cursor), deepcopy(self.plan), {}

    def preflight(self, **kwargs):
        return once.preflight(self.api, ROOT, ROOT / 'source',
                              self.request, CONTEXT, now=NOW, **kwargs)

    def test_positive_proposes_one_exact_CAS_and_preserves_every_old_receipt(self):
        old_sha, ready = self.preflight()
        self.assertEqual(old_sha, once.LIVE_BLOB_SHA)
        self.assertEqual(ready['status'], 'package-ready')
        self.assertEqual(ready['package']['ordinal'], 27)
        self.assertEqual(ready['package']['retryCount'], 2)
        self.assertEqual(ready['package']['retainedFailures'], self.p['retainedFailures'])
        self.assertEqual(ready['package']['carry'], self.p['carry'])
        self.assertEqual(ready['package']['lastVerified'], self.p['lastVerified'])
        self.assertEqual(ready['completionProgress'],
                         self.api.state_body['completionProgress'])
        self.assertIsNone(ready['runID'])
        self.assertIsNone(ready['dispatchID'])
        self.assertEqual(self.api.cas_count, 0)

    def test_authenticated_owner_and_first_attempt_required(self):
        for change in ({'actor':'github-actions[bot]'}, {'runAttempt':2},
                       {'ref':'refs/heads/main'}, {'event':'workflow_dispatch'},
                       {'triggeringActor':'someone-else'}, {'workflowRef':'wrong'}):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, 'owner execution'):
                    once.preflight(self.api, ROOT, ROOT/'source', self.request,
                                   dict(CONTEXT, **change), NOW)
        self.assertEqual(self.api.cas_count, 0)

    def test_auth_has_no_general_or_implicit_approval(self):
        for key, value in [('toDigest', once.OLD_DIGEST),
                           ('preserveHistory', False),
                           ('oneNewCloudDispatch', False),
                           ('sourceRequests', 1),
                           ('retryCountRetained', 0),
                           ('nextAllocationModeledUSD', '0.04'),
                           ('acceptedCheckpoint', {}),
                           ('newPackagePlanSHA256', '0'*64),
                           ('candidateHeadSHA', '0'*40)]:
            with self.subTest(key=key):
                broken = deepcopy(self.request)
                broken[key] = value
                with self.assertRaises(ValueError):
                    once.preflight(self.api, ROOT, ROOT/'source', broken, CONTEXT, NOW)
        with self.assertRaises(ValueError):
            once.preflight(self.api, ROOT, ROOT/'source', {}, CONTEXT, NOW)

    def test_expired_or_future_owner_approval_rejected(self):
        for authorized, expires in [('2026-11-17T18:00:00Z','2026-11-18T10:00:00Z'),
                                    ('2026-11-16T10:00:00Z','2026-11-17T12:00:00Z'),
                                    ('2026-11-17T16:00:00Z','2026-11-20T10:00:00Z')]:
            bad = deepcopy(self.request)
            bad.update(authorizedAt=authorized, expiresAt=expires)
            with self.assertRaises(ValueError):
                once.preflight(self.api, ROOT, ROOT/'source', bad, CONTEXT, NOW)

    def test_unreviewed_historical_state_or_digest_rejected(self):
        old = deepcopy(self.api.state_body)
        for mutate in (lambda x: x['package']['lastVerified'].update(verifiedParts=31),
                       lambda x: x['package'].update(retryCount=0),
                       lambda x: x.update(controlDigest='0'*64)):
            broken = deepcopy(old)
            mutate(broken)
            self.api.state_body = broken
            with self.assertRaises(ValueError):
                self.preflight()
        self.api.state_body = old
        with patch.object(d, 'local_digest', return_value='0'*64):
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                self.preflight()

    def test_no_dispatch_when_CAS_fails(self):
        with patch.object(self.api, 'cas', side_effect=d.Halt('CAS conflict')):
            with patch.object(d, 'dispatch') as dispatch:
                with self.assertRaisesRegex(d.Halt, 'CAS conflict'):
                    once.execute(self.api, ROOT, ROOT/'source',
                                 self.request, CONTEXT, NOW)
                dispatch.assert_not_called()

    def test_one_CAS_before_exactly_one_existing_dispatch(self):
        seen = []
        def fake_dispatch(api, root, sha, state, mode, allowed_run):
            seen.append((api.cas_count, sha, state['package']['retryCount'],
                         state['package']['ordinal'], mode, allowed_run))
            return {'status': 'MOCK_ONLY'}
        with patch.object(d, 'dispatch', side_effect=fake_dispatch):
            result = once.execute(self.api, ROOT, ROOT/'source',
                                  self.request, CONTEXT, NOW)
        self.assertEqual(result, {'status':'MOCK_ONLY'})
        self.assertEqual(seen, [(1, 'f'*40, 2, 27, 'package', 43290954679)])
        with self.assertRaisesRegex(ValueError, 'historical halted controller'):
            self.preflight()  # once consumed; no replay

    def test_ambiguous_post_CAS_dispatch_failure_does_not_retry(self):
        with patch.object(d, 'dispatch', side_effect=d.TransientGitHubError('unknown')) as dispatch:
            with self.assertRaises(d.TransientGitHubError):
                once.execute(self.api, ROOT, ROOT/'source',
                             self.request, CONTEXT, NOW)
            self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(self.api.cas_count, 1)
        self.assertEqual(self.api.state_body['status'], 'package-ready')

    def test_storage_or_full_remaining_budget_breach_fails_closed(self):
        report = dict(REPORT, modeledMonthlyStorageUSD='2.001')
        with patch.object(once, 'recompute', return_value=report):
            with self.assertRaisesRegex(ValueError, 'whole-delivery'):
                self.preflight()
        with patch.object(once, 'monthly', return_value=Decimal('2.001')):
            with self.assertRaisesRegex(ValueError, 'original limits'):
                self.preflight()

    def test_module_is_not_a_deployable_workflow_or_protected_source_change(self):
        src = (ROOT/'.github/automation/rrgh_halted_package_cas_dispatch_20261117.py').read_text()
        self.assertNotIn("if __name__ == '__main__'", src)
        self.assertNotIn('os.environ', src)
        self.assertNotIn('google-github-actions/auth', src)
        self.assertNotIn('rrgh_halted_package_cas_dispatch_20261117.py', d.CODE_FILES)
        self.assertEqual(self.api.cas_count, 0)


if __name__ == '__main__':
    unittest.main()
