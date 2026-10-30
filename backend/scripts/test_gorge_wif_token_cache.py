#!/usr/bin/env python3
"""Offline, deterministic regression tests for bounded process-local WIF token reuse."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_gorge_checkpoint_slot as subject

class TokenCacheTest(unittest.TestCase):
    def setUp(self):
        subject._TOKEN_VALUE=None
        subject._TOKEN_UNTIL=0.0

    def tearDown(self):
        subject._TOKEN_VALUE=None
        subject._TOKEN_UNTIL=0.0

    def test_cache_prevents_repeated_external_auth_exchanges(self):
        ok=SimpleNamespace(returncode=0,stdout='opaque-bearer-token\n')
        with patch.object(subject.time,'monotonic',return_value=100.0) as tick:
            with patch.object(subject.subprocess,'run',return_value=ok) as cmd:
                self.assertEqual(subject.token(),'opaque-bearer-token')
                self.assertEqual(subject.token(),'opaque-bearer-token')
                self.assertEqual(cmd.call_count,1)
                tick.return_value=701.0
                self.assertEqual(subject.token(),'opaque-bearer-token')
                self.assertEqual(cmd.call_count,2)
                self.assertEqual(cmd.call_args.kwargs['timeout'],30)

    def test_expired_auth_failure_is_fail_closed_no_stale_bearer(self):
        ok=SimpleNamespace(returncode=0,stdout='opaque-bearer-token\n')
        bad=SimpleNamespace(returncode=1,stdout='')
        with patch.object(subject.time,'monotonic',return_value=100.0) as tick:
            with patch.object(subject.subprocess,'run',side_effect=[ok,bad]) as cmd:
                self.assertEqual(subject.token(),'opaque-bearer-token')
                tick.return_value=701.0
                with self.assertRaisesRegex(RuntimeError,'credential unavailable'):
                    subject.token()
                self.assertIsNone(subject._TOKEN_VALUE)
                self.assertEqual(subject._TOKEN_UNTIL,0.0)
                self.assertEqual(cmd.call_count,2)

    def test_invalid_or_whitespace_credentials_never_enter_cache(self):
        for result in (SimpleNamespace(returncode=0,stdout=''),
                       SimpleNamespace(returncode=0,stdout='bad token\n'),
                       SimpleNamespace(returncode=1,stdout='anything')):
            with self.subTest(result=result):
                self.setUp()
                with patch.object(subject.subprocess,'run',return_value=result):
                    with self.assertRaises(RuntimeError):
                        subject.token()
                self.assertIsNone(subject._TOKEN_VALUE)

if __name__=='__main__':
    unittest.main()
