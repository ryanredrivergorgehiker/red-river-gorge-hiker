from datetime import datetime,timedelta,timezone
import hashlib,io,os,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import fetch_gorge_private_seed as seed


class Reply(io.BytesIO):
    def __init__(self,req,body):super().__init__(body);self.url=req.full_url;self.status=200;self.headers={}
    def geturl(self):return self.url


class PrivateSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.raw=[b'first',b'second',b'third',b'fourth'];self.joined=b''.join(self.raw)
        self.parts=tuple((len(b),hashlib.sha256(b).hexdigest()) for b in self.raw)
        self.patches=[patch.object(seed,'PARTS',self.parts),patch.object(seed,'SEED_BYTES',len(self.joined)),
            patch.object(seed,'SEED_SHA256',hashlib.sha256(self.joined).hexdigest())]
        for p in self.patches:p.start()
        query=urlencode({'se':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),
                         'sp':'r','sr':'b','sig':'TEST_ONLY_NOT_A_CREDENTIAL'})
        self.descriptor={'format':'rrgh-stage-seed-transfer-v1','seedBytes':seed.SEED_BYTES,
            'seedSHA256':seed.SEED_SHA256,'parts':[{'part':i+1,'bytes':n,'sha256':s,
            'download_url':f'https://sdmntprcentralus.oaiusercontent.com/test-{i}?{query}'} for i,(n,s) in enumerate(self.parts)]}
        self.calls=[]
    def tearDown(self):
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def opener(self,req,timeout):
        i=len(self.calls);self.calls.append(req);return Reply(req,self.raw[i])
    def run_receive(self):return seed.receive(self.descriptor,self.root/'seed.zip',self.opener)
    def test_exact_assembly_is_private_and_receipt_contains_no_url(self):
        r=self.run_receive();self.assertEqual((self.root/'seed.zip').read_bytes(),self.joined)
        self.assertEqual((self.root/'seed.zip').stat().st_mode&0o777,0o600)
        self.assertEqual(r['privateReadRequests'],4);self.assertFalse(r['gcsAccepted'])
        self.assertNotIn('https',str(r));self.assertNotIn('sig',str(r))
    def test_expired_or_write_reference_rejected_before_io(self):
        for key,value in [('sp','rw'),('se','2020-01-01T00:00:00Z')]:
            with self.subTest(key=key):
                original=self.descriptor['parts'][0]['download_url']
                self.descriptor['parts'][0]['download_url']=original+'&'+key+'='+value
                with self.assertRaises(seed.SeedTransferError):self.run_receive()
                self.assertEqual(self.calls,[]);self.descriptor['parts'][0]['download_url']=original
    def test_unapproved_host_or_part_reorder_rejected(self):
        self.descriptor['parts'][0]['download_url']=self.descriptor['parts'][0]['download_url'].replace('sdmntprcentralus.oaiusercontent.com','example.invalid')
        with self.assertRaises(seed.SeedTransferError):self.run_receive()
        self.assertEqual(self.calls,[])
        self.descriptor['parts'].reverse()
        with self.assertRaises(seed.SeedTransferError):self.run_receive()
    def test_corrupt_part_never_publishes_or_retries(self):
        self.raw[0]=b'wrong'
        with self.assertRaises(seed.SeedTransferError):self.run_receive()
        self.assertEqual(len(self.calls),1);self.assertFalse((self.root/'seed.zip').exists())
    def test_transport_error_cannot_disclose_secret(self):
        def fail(req,timeout):raise RuntimeError(req.full_url)
        with self.assertRaises(seed.SeedTransferError) as e:
            seed.receive(self.descriptor,self.root/'seed.zip',fail)
        self.assertNotIn('https',str(e.exception));self.assertTrue(e.exception.__suppress_context__)
    def test_existing_partial_or_target_blocks_reuse(self):
        (self.root/'seed.zip.partial').touch()
        with self.assertRaises(seed.SeedTransferError):self.run_receive()
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
