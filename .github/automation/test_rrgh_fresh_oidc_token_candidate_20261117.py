#!/usr/bin/env python3
"""Strictly offline contract for proposed fresh-OIDC WIF token supplier.

All network calls are intercepted; no GitHub id-token permission, Google STS,
gcloud command, production secrets, or package-worker dispatch is available.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
import rrgh_fresh_oidc_token_candidate_20261117 as v2
from rrgh_dispatcher import local_digest, CODE_FILES

JWT='A'*50+'.'+'B'*50+'.'+'C'*50
ACCESS='ya29.'+'X'*90
CTX={
    'GITHUB_REPOSITORY':'ryanredrivergorgehiker/red-river-gorge-hiker',
    'GITHUB_REF':'refs/heads/lane20/offline-production-preflight-20261029',
    'GITHUB_WORKFLOW_REF':v2._WORKFLOW,
    'GITHUB_EVENT_NAME':'workflow_dispatch',
    'GITHUB_RUN_ATTEMPT':'1',
    'GITHUB_ACTOR':'github-actions[bot]',
    'ACTIONS_ID_TOKEN_REQUEST_URL':'https://pipelines.actions.githubusercontent.com/opaque/idtoken?api-version=2.0',
    'ACTIONS_ID_TOKEN_REQUEST_TOKEN':'runner-scoped-token-that-is-not-a-cloud-key',
}


class Response:
    def __init__(self,request,value,status=200,target=None):
        self.value=value if isinstance(value,bytes) else json.dumps(value).encode()
        self.status=status
        self.target=target or request.full_url
    def geturl(self):
        return self.target
    def read(self,count):
        return self.value[:count]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


def success_open(request,timeout):
    assert timeout == 25
    if request.get_method()=='GET':
        assert request.full_url.startswith('https://pipelines.actions.githubusercontent.com/')
        query=parse_qs(urlsplit(request.full_url).query)
        assert query['audience']==[v2.AUDIENCE]
        assert query['api-version']==['2.0']
        assert request.get_header('Authorization')=='Bearer '+CTX['ACTIONS_ID_TOKEN_REQUEST_TOKEN']
        return Response(request,{'value':JWT})
    assert request.get_method()=='POST'
    assert request.full_url==v2.STS_URL
    assert not request.has_header('Authorization')
    body=parse_qs(request.data.decode())
    assert body=={
        'grant_type':['urn:ietf:params:oauth:grant-type:token-exchange'],
        'requested_token_type':['urn:ietf:params:oauth:token-type:access_token'],
        'subject_token_type':['urn:ietf:params:oauth:token-type:jwt'],
        'subject_token':[JWT],
        'audience':[v2.STS_AUDIENCE],
        'scope':[v2.SCOPE],
    }
    return Response(request,dict(access_token=ACCESS,expires_in=300,token_type='Bearer',
        issued_token_type='urn:ietf:params:oauth:token-type:access_token'))


class RenewalTests(unittest.TestCase):
    def setUp(self):
        v2._VALUE=None;v2._UNTIL=0.0
    def tearDown(self):
        v2._VALUE=None;v2._UNTIL=0.0

    def run_success(self, clock=100):
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=success_open) as opener,patch.object(v2.time,'monotonic',return_value=clock):
            self.assertEqual(v2.token(),ACCESS)
            self.assertEqual(v2._UNTIL,clock+120)
            self.assertEqual(opener.call_count,2)

    def test_fresh_oidc_and_exact_sts_exchange_not_static_gcloud(self):
        self.run_success()

    def test_repeated_renewal_mints_new_github_jwt_and_never_uses_stale_bearer(self):
        with patch.dict(v2.os.environ,CTX,clear=True):
            with patch.object(v2.time,'monotonic',return_value=100.0) as timer:
                with patch.object(v2,'_OPEN',side_effect=success_open) as opener:
                    self.assertEqual(v2.token(),ACCESS)
                    timer.return_value=219.0
                    self.assertEqual(v2.token(),ACCESS)
                    self.assertEqual(opener.call_count,2)
                    timer.return_value=220.0
                    self.assertEqual(v2.token(),ACCESS)
                    self.assertEqual(opener.call_count,4)
                    timer.return_value=340.0
                    self.assertEqual(v2.token(),ACCESS)
                    self.assertEqual(opener.call_count,6)
        self.assertTrue(all(c.kwargs.get('timeout')==25 for c in opener.call_args_list))

    def test_simulated_55_minute_job_renews_fresh_oidc_without_reusing_old_bearer(self):
        with patch.dict(v2.os.environ,CTX,clear=True):
            with patch.object(v2.time,'monotonic',return_value=0.0) as clock:
                with patch.object(v2,'_OPEN',side_effect=success_open) as opener:
                    for minute in range(56):
                        clock.return_value=minute*60.0
                        self.assertEqual(v2.token(),ACCESS)
                    # Initial request plus 27 renewals, each with separate GitHub
                    # OIDC assertion AND STS exchange. No real time/network used.
                    self.assertEqual(opener.call_count,56)
                    self.assertEqual(v2._UNTIL,3360.0)

    def test_rejections_without_oidc_env_do_not_contact_any_endpoint(self):
        for missing in CTX:
            with self.subTest(missing=missing):
                v2._VALUE=None;v2._UNTIL=0.0
                env=dict(CTX);env.pop(missing)
                with patch.dict(v2.os.environ,env,clear=True),patch.object(v2,'_OPEN') as opener:
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        v2.token()
                    opener.assert_not_called()

    def test_wrong_github_identity_ref_attempt_or_actor_denied_before_network(self):
        for k,value in [
            ('GITHUB_REPOSITORY','another/repo'),
            ('GITHUB_REF','refs/heads/main'),
            ('GITHUB_WORKFLOW_REF','other.yml@refs/heads/main'),
            ('GITHUB_EVENT_NAME','pull_request'),
            ('GITHUB_RUN_ATTEMPT','2'),
            ('GITHUB_ACTOR','untrusted-author')]:
            with self.subTest(k=k):
                env=dict(CTX,kval='noop');env.pop('kval');env[k]=value
                with patch.dict(v2.os.environ,env,clear=True),patch.object(v2,'_OPEN') as opener:
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        v2.token()
                    opener.assert_not_called()

    def test_invalid_oidc_host_or_embedded_audience_never_leaks_runner_secret(self):
        for url in (
            'http://pipelines.actions.githubusercontent.com/idtoken?api-version=2.0',
            'https://attacker.invalid/idtoken',
            'https://pipelines.actions.githubusercontent.com.attacker.invalid/idtoken',
            'https://pipelines.actions.githubusercontent.com/idtoken?audience=override',
            'https://user@pipelines.actions.githubusercontent.com/idtoken',
            'https://pipelines.actions.githubusercontent.com:1234/idtoken',
            'https://pipelines.actions.githubusercontent.com:bogus/idtoken',
            'https://pipelines.actions.githubusercontent.com/idtoken\\nHost: evil.invalid',
            'https://pipelines.actions.githubusercontent.com/idtoken#fragment',
            'https://pipelines.actions.githubusercontent.com/idtoken?api-version=2.0&api-version=2.1',
        ):
            with self.subTest(url=url):
                env=dict(CTX);env['ACTIONS_ID_TOKEN_REQUEST_URL']=url
                with patch.dict(v2.os.environ,env,clear=True),patch.object(v2,'_OPEN') as opener:
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid') as fail:
                        v2.token()
                    self.assertNotIn(CTX['ACTIONS_ID_TOKEN_REQUEST_TOKEN'],str(fail.exception))
                    opener.assert_not_called()

    def test_google_403_rejection_is_hard_stop_no_retry_or_stale_token(self):
        def deny(request,timeout):
            if request.get_method()=='GET':
                return Response(request,{'value':JWT})
            raise HTTPError(request.full_url,403,'private-token-rejected',{},None)
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=deny) as opener,patch.object(v2.time,'sleep') as sleeper:
            with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid') as error:
                v2.token()
        self.assertEqual(opener.call_count,2)
        self.assertIsNone(v2._VALUE)
        sleeper.assert_not_called()
        self.assertNotIn('private-token',str(error.exception))

    def test_google_transient_503_can_retry_exactly_once_then_succeed(self):
        called=[0]
        def once(request,timeout):
            if request.get_method()=='POST' and called[0]==0:
                called[0]+=1
                raise HTTPError(request.full_url,503,'do-not-log-anything',{},None)
            return success_open(request,timeout)
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=once) as opener,patch.object(v2.time,'sleep') as sleeper:
            self.assertEqual(v2.token(),ACCESS)
        self.assertEqual(opener.call_count,4)
        sleeper.assert_called_once_with(1)

    def test_retry_exhaustion_stops_after_three_fresh_oidc_assertions(self):
        def unavailable(request,timeout):
            if request.get_method()=='POST':
                raise HTTPError(request.full_url,503,'unsafe-private-payload',{},None)
            return Response(request,{'value':JWT})
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=unavailable) as opener,patch.object(v2.time,'sleep') as sleeper:
            with self.assertRaisesRegex(RuntimeError,'transport') as error:
                v2.token()
        self.assertEqual(opener.call_count,6)
        self.assertEqual(sleeper.call_count,2)
        self.assertNotIn('unsafe-private',str(error.exception))
        self.assertIsNone(v2._VALUE)

    def test_sts_token_expiry_bounds_shorter_than_120_only(self):
        def expires_soon(req,timeout):
            if req.get_method()=='GET':return Response(req,{'value':JWT})
            return Response(req,dict(access_token=ACCESS,expires_in=100,token_type='Bearer',
                issued_token_type='urn:ietf:params:oauth:token-type:access_token'))
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=expires_soon),patch.object(v2.time,'monotonic',return_value=200):
            self.assertEqual(v2.token(),ACCESS)
            self.assertEqual(v2._UNTIL,240)

    def test_reject_wrong_google_audience_issuer_token_type_and_lease(self):
        variants=[
            dict(access_token='x',expires_in=300,token_type='Bearer'),
            dict(access_token=ACCESS,expires_in=300,token_type='not-bearer'),
            dict(access_token=ACCESS,expires_in=300,token_type='Bearer',
                issued_token_type='urn:ietf:params:oauth:token-type:id_token'),
            dict(access_token=ACCESS,expires_in=20,token_type='Bearer'),
            dict(access_token=ACCESS,expires_in=100000,token_type='Bearer'),
        ]
        for result in variants:
            with self.subTest(result=result):
                v2._VALUE=None;v2._UNTIL=0
                def wrong(req,timeout):
                    return Response(req,{'value':JWT} if req.get_method()=='GET' else result)
                with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=wrong):
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        v2.token()
                self.assertIsNone(v2._VALUE)

    def test_jwt_shape_redirect_and_oversized_response_denied(self):
        for kind in ('jwt','redirect','oversized'):
            def bad(req,timeout):
                if kind=='jwt':return Response(req,{'value':'invalid.jwt'})
                if kind=='redirect':return Response(req,{'value':JWT},target='https://attacker.invalid/')
                return Response(req,b'{'+b'A'*(16*1024+100))
            with self.subTest(kind=kind):
                with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=bad):
                    with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                        v2.token()
                self.assertIsNone(v2._VALUE)

    def test_denied_refresh_does_not_return_prior_cached_bearer(self):
        allow=[True]
        def later(req,timeout):
            if allow[0]:return success_open(req,timeout)
            if req.get_method()=='GET':return Response(req,{'value':JWT})
            raise HTTPError(req.full_url,403,'stale-token',{},None)
        with patch.dict(v2.os.environ,CTX,clear=True),patch.object(v2,'_OPEN',side_effect=later),patch.object(v2.time,'monotonic',return_value=100) as clock:
            self.assertEqual(v2.token(),ACCESS)
            clock.return_value=221;allow[0]=False
            with self.assertRaisesRegex(RuntimeError,'rejected-or-invalid'):
                v2.token()
            self.assertIsNone(v2._VALUE);self.assertEqual(v2._UNTIL,0.0)


class SourceIsolationTests(unittest.TestCase):
    def test_candidate_not_in_controller_digest_or_called_by_live_runtime(self):
        path='.github/automation/rrgh_fresh_oidc_token_candidate_20261117.py'
        self.assertNotIn(path,CODE_FILES)
        current=json.loads((ROOT/'.github/automation/rrgh-controller-state.json').read_text())
        self.assertEqual(current['controlDigest'],local_digest(ROOT))
        self.assertEqual(current['status'],'halted')
        self.assertEqual(current['runID'],43290954679)
        self.assertEqual(current['package']['lastVerified']['verifiedParts'],32)
        self.assertEqual(current['package']['lastVerified']['verifiedIndexes'],0)
        live=(ROOT/'.github/automation/rrgh_package_runtime.py').read_text()
        self.assertIn('from rrgh_wif_credentials import token',live)
        self.assertNotIn('rrgh_fresh_oidc_token_candidate',live)

    def test_existing_workflow_preserves_authorized_identity_scope(self):
        workflow=(ROOT/'.github/workflows/offline-map-restricted-dispatch.yml').read_text()
        stage=workflow.split('  package-stage:',1)[1].split('  package-verify:',1)[0]
        self.assertIn('id-token: write',stage)
        self.assertIn('google-github-actions/auth@v3',stage)
        self.assertNotIn('service_account:',stage)
        self.assertNotIn('rrgh_fresh_oidc_token_candidate',stage)


if __name__=='__main__':unittest.main()
