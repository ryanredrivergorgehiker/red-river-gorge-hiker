import importlib.util,io,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE',str(ROOT.parent/'native-batch-source'))).resolve()
sys.path.insert(0,str(SOURCE/'backend/scripts'))
from gorge_checkpoint import Meter,DIMENSIONS
spec=importlib.util.spec_from_file_location('rrgh_reviewed_transport',ROOT/'.github/automation/source-templates/gorge_guarded_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
URL='https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/Phase2/N100E365_2024_DEM_Phase2_cog.tif'

class Response(io.BytesIO):
    status=206

class TransportTests(unittest.TestCase):
    def meter(self,requests=2):
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(sourceBytes=8,sourceRequests=requests,seconds=60)
        return Meter(caps)

    def request(self):return Request(URL,headers={'Range':'bytes=0-3','If-Match':'"original-etag"'})

    def test_one_transient_read_reserves_both_requests_and_preserves_identity(self):
        seen=[]
        def open_(request,timeout):
            seen.append(request)
            if len(seen)==1:raise HTTPError(URL,503,'Temporary',{},None)
            return Response(b'abcd')
        meter=self.meter();opener=worker.SourceOpener(meter,open_);request=self.request()
        with patch.object(worker.time,'sleep'):
            with opener(request) as response:self.assertEqual(response.read(4),b'abcd')
        self.assertEqual(seen,[request,request]);self.assertEqual(request.get_header('If-match'),'"original-etag"')
        self.assertEqual(meter.used['sourceRequests'],2);self.assertEqual(meter.used['sourceBytes'],8)
        self.assertEqual(opener.summary()['statuses'],[503,206]);self.assertEqual(opener.summary()['receivedBodyBytes'],4)

    def test_original_one_request_cap_blocks_retry_before_network(self):
        calls=[]
        def open_(*args,**kwargs):calls.append(1);raise HTTPError(URL,500,'Temporary',{},None)
        meter=self.meter(1);opener=worker.SourceOpener(meter,open_)
        with patch.object(worker.time,'sleep'),self.assertRaises(ValueError):opener(self.request())
        self.assertEqual(len(calls),1);self.assertEqual(meter.used['sourceRequests'],1)

    def test_second_failure_stops_without_third_request(self):
        calls=[]
        def open_(*args,**kwargs):calls.append(1);raise HTTPError(URL,502,'Temporary',{},None)
        opener=worker.SourceOpener(self.meter(),open_)
        with patch.object(worker.time,'sleep'),self.assertRaises(HTTPError):opener(self.request())
        self.assertEqual(len(calls),2);self.assertEqual(opener.summary()['reservedResponseBytes'],8)

    def test_identity_authorization_and_missing_source_errors_never_retry(self):
        for code in (401,403,404,412,429):
            with self.subTest(code=code):
                calls=[]
                def open_(*args,**kwargs):calls.append(1);raise HTTPError(URL,code,'Refused',{},None)
                with self.assertRaises(HTTPError):worker.SourceOpener(self.meter(),open_)(self.request())
                self.assertEqual(len(calls),1)

    def test_received_body_failure_never_replays_a_partial_transfer(self):
        class Broken(Response):
            def read(self,size=-1):raise OSError('partial body interrupted')
        calls=[]
        def open_(*args,**kwargs):calls.append(1);return Broken(b'')
        opener=worker.SourceOpener(self.meter(),open_)
        with self.assertRaises(OSError):opener(self.request()).read(4)
        self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
