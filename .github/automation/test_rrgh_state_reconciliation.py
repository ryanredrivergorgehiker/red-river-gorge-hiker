"""Failure injection for bounded SHA-conditional controller state writes."""
import copy
import hashlib
import unittest
from unittest.mock import patch
from urllib.error import URLError

import rrgh_dispatcher as d


class StateWriteTests(unittest.TestCase):
    def setUp(self):
        self.api=d.GitHub('synthetic')
        self.value={'status':'publishing','runID':356,'receipt':{'sha256':'a'*64}}
        raw=d.canonical(self.value)
        self.wanted=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.pause=patch.object(d.time,'sleep').start()
        self.addCleanup(patch.stopall)

    def test_success_uses_one_conditional_write(self):
        with patch.object(self.api,'call',return_value={'content':{'sha':self.wanted}}) as call, patch.object(self.api,'state') as read:
            self.assertEqual(self.api.cas('old',self.value,'test'),self.wanted)
            self.assertEqual(call.call_count,1)
            self.assertEqual(call.call_args.args[:2],('PUT','contents/'+d.STATE))
            self.assertEqual(call.call_args.args[2]['sha'],'old')
            read.assert_not_called()

    def test_applied_write_with_lost_response_is_not_repeated(self):
        for error in (d.TransientGitHubError('HTTP 500'),URLError('response lost'),TimeoutError(),ConnectionResetError()):
            with self.subTest(error=type(error).__name__),patch.object(self.api,'call',side_effect=error) as call,patch.object(self.api,'state',return_value=(self.wanted,copy.deepcopy(self.value))):
                self.assertEqual(self.api.cas('old',self.value,'test'),self.wanted)
                self.assertEqual(call.call_count,1)

    def test_unchanged_old_blob_allows_only_same_conditional_write(self):
        with patch.object(self.api,'call',side_effect=[d.TransientGitHubError('500'),{'content':{'sha':self.wanted}}]) as call,patch.object(self.api,'state',return_value=('old',{'status':'running'})) as read:
            self.assertEqual(self.api.cas('old',self.value,'test'),self.wanted)
            self.assertEqual(call.call_count,2)
            self.assertEqual(call.call_args_list[0],call.call_args_list[1])
            read.assert_called_once()

    def test_competing_writer_prevents_retry(self):
        with patch.object(self.api,'call',side_effect=d.TransientGitHubError('500')) as call,patch.object(self.api,'state',return_value=('other',{'status':'running','runID':357})):
            with self.assertRaisesRegex(d.Halt,'different owner'):self.api.cas('old',self.value,'test')
            self.assertEqual(call.call_count,1)

    def test_matching_body_without_matching_blob_is_not_accepted(self):
        with patch.object(self.api,'call',side_effect=d.TransientGitHubError('500')) as call,patch.object(self.api,'state',return_value=('other',self.value)):
            with self.assertRaises(d.Halt):self.api.cas('old',self.value,'test')
            self.assertEqual(call.call_count,1)

    def test_matching_blob_without_matching_body_is_not_accepted(self):
        with patch.object(self.api,'call',side_effect=d.TransientGitHubError('500')) as call,patch.object(self.api,'state',return_value=(self.wanted,{'changed':True})):
            with self.assertRaises(d.Halt):self.api.cas('old',self.value,'test')
            self.assertEqual(call.call_count,1)

    def test_persistent_unchanged_failure_stops_after_three_writes(self):
        with patch.object(self.api,'call',side_effect=d.TransientGitHubError('500')) as call,patch.object(self.api,'state',return_value=('old',{})) as read:
            with self.assertRaisesRegex(d.Halt,'three conditional attempts'):self.api.cas('old',self.value,'test')
            self.assertEqual(call.call_count,3);self.assertEqual(read.call_count,3)
            self.assertEqual(self.pause.call_count,2)

    def test_failed_readback_cannot_repeat_write(self):
        with patch.object(self.api,'call',side_effect=d.TransientGitHubError('500')) as call,patch.object(self.api,'state',side_effect=d.Halt('read failed')):
            with self.assertRaisesRegex(d.Halt,'read failed'):self.api.cas('old',self.value,'test')
            self.assertEqual(call.call_count,1)

    def test_permissions_and_conflicts_are_not_retried(self):
        for status in ('403','409','422'):
            with self.subTest(status=status),patch.object(self.api,'call',side_effect=d.Halt(status)) as call,patch.object(self.api,'state') as read:
                with self.assertRaises(d.Halt):self.api.cas('old',self.value,'test')
                self.assertEqual(call.call_count,1);read.assert_not_called()


if __name__=='__main__':unittest.main()
