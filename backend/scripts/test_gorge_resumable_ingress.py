import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from gorge_checkpoint import BUCKET, DIMENSIONS, Meter, PREFIX, Ref, canonical, digest
from gorge_resumable_ingress import IngressError, put_file, reservation


class Response(io.BytesIO):
    def __init__(self, url, status, body=b'', headers=None):
        super().__init__(body); self.url=url; self.status=status; self.headers=headers or {}
    def geturl(self): return self.url


class Server:
    def __init__(self, raw):
        self.raw=raw; self.received=b''; self.calls=[]; self.mode='ok'; self.failed=False
    def metadata(self):
        return canonical({'bucket':BUCKET,'name':self.key,'generation':'12345',
            'size':str(len(self.raw)), 'md5Hash':base64.b64encode(
                hashlib.md5(self.raw,usedforsecurity=False).digest()).decode()})
    def __call__(self, req, timeout):
        self.calls.append(req)
        if req.method=='POST':
            q=parse_qs(urlsplit(req.full_url).query); self.key=q['name'][0]
            assert q['ifGenerationMatch']==['0']
            assert req.get_header('Authorization')=='Bearer TEST_ONLY'
            if self.mode=='conflict':return Response(req.full_url,412)
            uri=req.full_url+'&upload_id=TEST_PRIVATE_SESSION'
            if self.mode=='foreign':uri=uri.replace('storage.googleapis.com','example.invalid')
            return Response(req.full_url,200,headers={'Location':uri})
        if req.method=='GET':
            q=parse_qs(urlsplit(req.full_url).query)
            assert q['generation']==q['ifGenerationMatch']==['12345']
            raw=self.received
            if self.mode=='corrupt':raw=b'!'+raw[1:]
            if self.mode=='short':raw=raw[:-1]
            if self.mode=='long':raw+=b'!'
            generation='9' if self.mode=='generation' else '12345'
            return Response(req.full_url,200,raw,{'x-goog-generation':generation})
        assert req.get_header('Authorization') is None
        cr=req.get_header('Content-range')
        if not cr.startswith('bytes */'):
            start=int(cr.split()[1].split('-')[0])
            assert start==len(self.received)
            if self.mode=='lostpartial' and not self.failed:
                self.received+=req.data[:131072]; self.failed=True
                raise URLError('secret URL must not escape')
            self.received+=req.data
            if self.mode=='lostfinal' and len(self.received)==len(self.raw) and not self.failed:
                self.failed=True;raise URLError('secret URL must not escape')
        if len(self.received)==len(self.raw):return Response(req.full_url,200,self.metadata())
        headers={'Range':'bytes=0-'+str(len(self.received)-1)} if self.received else {}
        if self.mode=='bad_range':headers={'Range':'bytes=0-99999999'}
        if self.mode=='http308':
            raise HTTPError(req.full_url,308,'Resume Incomplete',headers,io.BytesIO(b''))
        return Response(req.full_url,308,headers=headers)


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name);os.chmod(self.root,0o700)
        self.raw=b'abc12345'*(65536+10);self.path=self.root/'source';self.path.write_bytes(self.raw)
        self.server=Server(self.raw); self.plan={'test':'non-live fixture'}
        self.prefix=PREFIX+'plans/'+digest(canonical(self.plan))+'/'
        caps={x:0 for x in DIMENSIONS};caps.update(storedBytes=2**30,egressBytes=2**30,
            classARequests=200,classBRequests=500,seconds=60)
        self.slot=SimpleNamespace(closed=False,plan=self.plan,index=0,prefix=self.prefix,
            claim=Ref(self.prefix+'slots/00000/claim.json','2',1,'0'*64),meter=Meter(caps))
        self.slot.store=SimpleNamespace(plan_prefix=self.prefix,opener=self.server,
            expiry=datetime.now(timezone.utc)+timedelta(hours=1),token_provider=lambda:'TEST_ONLY')
    def tearDown(self):self.temp.cleanup()
    def run_upload(self):
        return put_file(self.slot,self.path,len(self.raw),digest(self.raw),self.root/'session.json',chunk=262144)
    def test_success_and_separate_reservations(self):
        r=self.run_upload();self.assertTrue(r['sha256ReadbackVerified'])
        self.assertEqual(self.server.received,self.raw)
        self.assertEqual(self.slot.meter.used['classARequests'],8)
        self.assertEqual(r['usage']['writeRequests'],4)
        self.assertEqual(r['usage']['readbackBytes'],len(self.raw))
        self.assertIsNone(json.loads((self.root/'session.json').read_text())['sessionURI'])
        self.assertNotIn('TEST_PRIVATE_SESSION',json.dumps(r))
        self.assertEqual((self.root/'session.json').stat().st_mode&0o777,0o600)
    def test_lost_partial_response_resumes_exact_offset(self):
        self.server.mode='lostpartial';r=self.run_upload()
        self.assertEqual(self.server.received,self.raw);self.assertEqual(r['usage']['statusQueries'],1)
        self.assertEqual(r['usage']['uploadBodyBytesAttempted'],len(self.raw)+131072)
    def test_lost_completion_response_queries_without_recreating(self):
        self.server.mode='lostfinal';r=self.run_upload()
        self.assertEqual(r['usage']['statusQueries'],1)
        self.assertEqual(sum(r.method=='POST' for r in self.server.calls),1)
    def test_urllib_http308_is_protocol_response(self):
        self.server.mode='http308';self.run_upload()
    def test_no_ops_when_preoperation_budget_insufficient(self):
        self.slot.meter.caps['classARequests']=7
        with self.assertRaisesRegex(ValueError,'limit'):self.run_upload()
        self.assertEqual(self.server.calls,[])
    def test_corrupt_local_seed_stops_before_credentials_or_io(self):
        self.path.write_bytes(b'!'+self.raw[1:])
        with self.assertRaisesRegex(ValueError,'SHA256'):self.run_upload()
        self.assertEqual(self.server.calls,[])
    def test_remote_integrity_generation_and_length_fail_closed(self):
        for mode in ('corrupt','short','long','generation'):
            with self.subTest(mode=mode):
                self.server=Server(self.raw);self.server.mode=mode;self.slot.store.opener=self.server
                journal=self.root/'session.json'
                if journal.exists():journal.unlink() # Synthetic fixture only.
                with self.assertRaises(IngressError):self.run_upload()
                self.assertFalse(json.loads(journal.read_text())['accepted'])
    def test_foreign_session_never_receives_bytes(self):
        self.server.mode='foreign'
        with self.assertRaisesRegex(IngressError,'endpoint'):self.run_upload()
        self.assertEqual(len(self.server.calls),1)
    def test_conflict_never_overwrites_or_restarts(self):
        self.server.mode='conflict'
        with self.assertRaisesRegex(IngressError,'412'):self.run_upload()
        self.assertEqual(len(self.server.calls),1)
    def test_bad_acknowledgement_stops(self):
        self.server.mode='bad_range'
        with self.assertRaisesRegex(IngressError,'extent'):self.run_upload()
        self.assertEqual(len(self.server.calls),2)
    def test_existing_journal_cannot_reset_allocation(self):
        (self.root/'session.json').write_text('{}')
        with self.assertRaises(FileExistsError):self.run_upload()
        self.assertEqual(self.server.calls,[])
    def test_session_expiry_stops_before_network(self):
        self.slot.store.expiry=datetime.now(timezone.utc)-timedelta(seconds=1)
        with self.assertRaisesRegex(IngressError,'deadline'):self.run_upload()
        self.assertEqual(self.server.calls,[])
    def test_journal_privacy_required(self):
        os.chmod(self.root,0o755)
        with self.assertRaisesRegex(ValueError,'private'):self.run_upload()
        self.assertEqual(self.server.calls,[])
    def test_seed_and_pack_envelopes(self):
        zip_budget=reservation(309600543)
        self.assertEqual(zip_budget['classARequests'],24)
        sizes=[67108864]*4+[23658496,16355492]
        self.assertEqual(sum(reservation(n)['classARequests'] for n in sizes),49)
        self.assertEqual(sum(reservation(n)['storedBytes'] for n in sizes),308449444)


if __name__=='__main__':unittest.main()
