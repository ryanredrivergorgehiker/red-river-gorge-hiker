"""Inject log-service failures; retries must remain bounded authenticated GETs."""
from http.client import IncompleteRead
from io import BytesIO
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError
from urllib.request import Request

import rrgh_dispatch_audit as a

PATH='actions/jobs/126833568194/logs'


class LogReadTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock()
        self.opener=patch.object(a.urllib.request,'build_opener',return_value=self.client).start()
        self.sleep=patch.object(a.time,'sleep').start()
        self.addCleanup(patch.stopall)
    def error(self,status):return HTTPError('https://api.github.com/'+PATH,status,'temporary',{},None)
    def test_wave399_503_reacquires_complete_log(self):
        self.client.open.side_effect=[self.error(503),BytesIO(b'complete verified receipt')]
        self.assertEqual(a.gh(PATH,'synthetic',raw=True),'complete verified receipt')
        self.assertEqual(self.client.open.call_count,2)
        self.assertEqual(self.client.open.call_args_list[0],self.client.open.call_args_list[1])
        self.assertEqual(self.client.open.call_args.args[0].get_method(),'GET')
        self.sleep.assert_called_once_with(5)
    def test_all_transient_server_statuses_retry(self):
        for status in (408,429,500,502,503,504):
            with self.subTest(status=status):
                self.client.open.side_effect=[self.error(status),BytesIO(b'{}')]
                self.assertEqual(a.gh(PATH,'synthetic'),{})
    def test_log_not_yet_available_can_retry_404_but_other_404_cannot(self):
        self.client.open.side_effect=[self.error(404),BytesIO(b'available')]
        self.assertEqual(a.gh(PATH,'synthetic',raw=True),'available')
        self.client.open.reset_mock();self.client.open.side_effect=self.error(404)
        with self.assertRaisesRegex(a.Halt,'HTTP 404'):a.gh('contents/missing','synthetic',raw=True)
        self.assertEqual(self.client.open.call_count,1)
    def test_network_and_truncated_reads_retry_without_using_partial_bytes(self):
        for error in (URLError('temporary'),TimeoutError(),ConnectionResetError(),IncompleteRead(b'partial',100)):
            with self.subTest(error=type(error).__name__):
                self.client.open.side_effect=[error,BytesIO(b'complete')]
                self.assertEqual(a.gh(PATH,'synthetic',raw=True),'complete')
    def test_persistent_failure_stops_after_five_gets(self):
        self.client.open.side_effect=self.error(503)
        with self.assertRaisesRegex(a.Halt,'bounded GET retries exhausted'):a.gh(PATH,'synthetic',raw=True)
        self.assertEqual(self.client.open.call_count,5)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list],[5,15,30,60])
    def test_auth_and_other_nontransient_errors_are_not_retried(self):
        for status in (400,401,403,409,422):
            self.client.open.reset_mock();self.client.open.side_effect=self.error(status)
            with self.subTest(status=status),self.assertRaises(a.Halt):a.gh(PATH,'synthetic',raw=True)
            self.assertEqual(self.client.open.call_count,1)
        self.sleep.assert_not_called()
    def test_response_bound_cannot_be_silently_truncated(self):
        self.client.open.side_effect=[BytesIO(b'x'*12_000_001)]
        with self.assertRaisesRegex(a.Halt,'response limit'):a.gh(PATH,'synthetic',raw=True)
        self.assertEqual(self.client.open.call_count,1)
    def test_malformed_json_never_becomes_success_or_retries(self):
        self.client.open.side_effect=[BytesIO(b'{broken')]
        with self.assertRaises(ValueError):a.gh('actions/runs/399','synthetic')
        self.assertEqual(self.client.open.call_count,1)
    def test_redirect_strips_api_bearer_and_requires_https(self):
        self.client.open.side_effect=[BytesIO(b'ok')];a.gh(PATH,'synthetic',raw=True)
        redirect=self.opener.call_args.args[0]()
        req=Request('https://api.github.com/repos/example/logs',headers={'Authorization':'Bearer synthetic'})
        req.add_unredirected_header('Authorization','Bearer synthetic')
        new=redirect.redirect_request(req,None,302,'found',{},'https://logs.example.invalid/signed')
        self.assertNotIn('Authorization',dict(new.header_items()))
        with self.assertRaisesRegex(a.Halt,'Unsafe'):redirect.redirect_request(req,None,302,'found',{},'http://logs.example.invalid/signed')


if __name__=='__main__':unittest.main()
