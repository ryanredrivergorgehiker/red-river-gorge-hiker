#!/usr/bin/env python3
"""GitHub-only regression for the current halted package WIF identity boundary.

No Cloud credentials, OIDC permission, network, subprocess execution or state writes.
Every gcloud subprocess call is mocked; historical receipts remain immutable.
"""
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
import rrgh_wif_credentials as wif
from rrgh_dispatcher import local_digest


class CredentialLifetimeTests(unittest.TestCase):
    def setUp(self):
        wif._VALUE=None
        wif._UNTIL=0.0
    def tearDown(self):
        wif._VALUE=None
        wif._UNTIL=0.0

    def test_120_second_cache_refreshes_not_a_long_lived_bearer(self):
        ok=SimpleNamespace(returncode=0,stdout='opaque-token\n',stderr='')
        with patch.object(wif.time,'monotonic',return_value=100.0) as clock:
            with patch.object(wif.subprocess,'run',return_value=ok) as run:
                self.assertEqual(wif.token(),'opaque-token')
                self.assertEqual(wif._UNTIL,220.0)
                clock.return_value=219.99
                self.assertEqual(wif.token(),'opaque-token')
                self.assertEqual(run.call_count,1)
                clock.return_value=220.0
                self.assertEqual(wif.token(),'opaque-token')
                self.assertEqual(run.call_count,2)
                self.assertEqual(run.call_args.kwargs['timeout'],30)
                self.assertEqual(run.call_args.args[0],
                    ['gcloud','auth','print-access-token','--quiet'])

    def test_hard_iam_rejection_overrules_transient_text_and_never_retries(self):
        bad=SimpleNamespace(returncode=1,stdout='',
            stderr='PERMISSION_DENIED invalid_grant connection reset secret-context')
        with patch.object(wif.subprocess,'run',return_value=bad) as run:
            with patch.object(wif.time,'sleep') as sleep:
                output=io.StringIO()
                with contextlib.redirect_stderr(output):
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        wif.token()
        self.assertEqual(run.call_count,1)
        sleep.assert_not_called()
        self.assertIsNone(wif._VALUE)
        self.assertEqual(wif._UNTIL,0.0)
        report=output.getvalue()
        self.assertIn('"category": "rejected-or-invalid"',report)
        self.assertIn('"retryable": false',report)
        self.assertIn('"storageRequestStarted": false',report)
        self.assertNotIn('secret-context',report)
        self.assertNotIn('PERMISSION_DENIED',report)

    def test_rejected_renewal_never_falls_back_to_cached_bearer(self):
        ok=SimpleNamespace(returncode=0,stdout='expired-bearer\n',stderr='')
        reject=SimpleNamespace(returncode=1,stdout='stolen-token',
            stderr='invalid_grant: rejected')
        with patch.object(wif.time,'monotonic',return_value=10.0) as clock:
            with patch.object(wif.subprocess,'run',side_effect=[ok,reject]) as run:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(wif.token(),'expired-bearer')
                    clock.return_value=131.0
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        wif.token()
        self.assertEqual(run.call_count,2)
        self.assertIsNone(wif._VALUE)
        self.assertEqual(wif._UNTIL,0.0)

    def test_only_known_transient_503_can_use_bounded_retry(self):
        transient=SimpleNamespace(returncode=1,stdout='',
            stderr='HTTP 503 Service Unavailable')
        ok=SimpleNamespace(returncode=0,stdout='opaque-token\n',stderr='')
        with patch.object(wif.subprocess,'run',side_effect=[transient,ok]) as run:
            with patch.object(wif.time,'sleep') as sleep:
                with contextlib.redirect_stderr(io.StringIO()) as out:
                    self.assertEqual(wif.token(),'opaque-token')
        self.assertEqual(run.call_count,2)
        sleep.assert_called_once_with(1)
        self.assertIn('"category": "transport"',out.getvalue())

    def test_exhausted_process_timeouts_never_produce_credentials(self):
        import subprocess
        failure=subprocess.TimeoutExpired(cmd=['gcloud','auth','print-access-token'],timeout=30)
        with patch.object(wif.subprocess,'run',side_effect=failure) as run:
            with patch.object(wif.time,'sleep') as sleep:
                with contextlib.redirect_stderr(io.StringIO()) as out:
                    with self.assertRaisesRegex(RuntimeError,'timeout'):
                        wif.token()
        self.assertEqual(run.call_count,3)
        self.assertEqual(sleep.call_count,2)
        self.assertEqual(sleep.call_args_list[0].args,(1,))
        self.assertEqual(sleep.call_args_list[1].args,(2,))
        self.assertNotIn('access_token',out.getvalue().lower())
        self.assertIsNone(wif._VALUE)

    def test_empty_whitespace_or_failed_token_is_never_accepted(self):
        for result in (
            SimpleNamespace(returncode=0,stdout='',stderr=''),
            SimpleNamespace(returncode=0,stdout='bad token',stderr=''),
            SimpleNamespace(returncode=1,stdout='fake-token',stderr='invalid_grant')):
            with self.subTest(result=result):
                self.setUp()
                with patch.object(wif.subprocess,'run',return_value=result):
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(RuntimeError):wif.token()
                self.assertIsNone(wif._VALUE)


class HaltedControllerReadOnlyTests(unittest.TestCase):
    def test_exact_accepted_source_state_and_no_unreviewed_digest_change(self):
        state=json.loads((ROOT/'.github/automation/rrgh-controller-state.json').read_text())
        package=state['package']
        self.assertEqual(state['format'],'rrgh-controller-state-v1')
        self.assertEqual(state['status'],'halted')
        self.assertEqual(state['mode'],'package')
        self.assertEqual(state['runID'],43290954679)
        self.assertEqual(package['ordinal'],26)
        self.assertEqual(package['retryCount'],2)
        self.assertEqual(package['lastVerified']['verifiedParts'],32)
        self.assertEqual(package['lastVerified']['verifiedIndexes'],0)
        self.assertEqual(package['lastVerified']['ordinal'],23)
        self.assertEqual(package['lastVerified']['receiptRef']['sha256'],
          '1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8')
        self.assertEqual([p['partID'] for p in package['operation']['parts']],
          ['core-032','core-033']+[f'leaf-on-{i:03d}' for i in range(6)])
        self.assertEqual(state['completionProgress']['acceptedRasterTiles'],278278)
        self.assertEqual(state['completionProgress']['remainingRasterTiles'],0)
        self.assertFalse(state['completionProgress']['finalPackageDeliveryComplete'])
        self.assertEqual(len(package['retainedFailures']),5)
        self.assertLess(datetime.fromisoformat(package['expiresAt'].replace('Z','+00:00')),
                        datetime.now(timezone.utc))
        self.assertEqual(state['controlDigest'],local_digest(ROOT))

    def test_no_cloud_qa_does_not_authorize_cloud_dispatch(self):
        import inspect
        from rrgh_package_controller import recovery_allocation
        text=inspect.getsource(recovery_allocation)
        self.assertIn("error['transientTransport'] is True",text)
        self.assertIn("p.get('retryCount',0)<2",text)
        self.assertIn("entireAllocationRetained",text)
        self.assertIn("error['sourceRequests']==0",text)
        self.assertIn("retained=settle(",text)


if __name__=='__main__':unittest.main()
