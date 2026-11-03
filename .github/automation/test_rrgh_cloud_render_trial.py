import hashlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(os.environ.get('RRGH_TEST_SOURCE','source260')).resolve()/'backend/scripts'))
from gorge_checkpoint import Ref
import rrgh_cloud_render_trial as t

class Response(io.BytesIO):
    def __init__(self,raw,url,headers,status=200):
        super().__init__(raw);self.url=url;self.headers=headers;self.status=status
    def geturl(self):return self.url

class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.raw=b'verified child';self.calls=[]
        self.ref=Ref('engineering/map-production/plans/'+t.CHILD_PLAN+'/slots/00001/outputs/pin','123',len(self.raw),hashlib.sha256(self.raw).hexdigest())
        def open_(request,timeout):
            self.calls.append(request)
            return Response(self.raw,request.full_url,{'x-goog-generation':'123'})
        self.reader=t.ReadOnlyChildren(open_)
    def test_get_only_and_exact_generation_and_cache(self):
        with patch('rrgh_wif_credentials.token',return_value='test-only'):
            self.assertEqual(self.reader.get(self.ref),self.raw)
            self.assertEqual(self.reader.get(self.ref),self.raw)
        self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0].get_method(),'GET')
        self.assertIn('ifGenerationMatch=123',self.calls[0].full_url)
        self.assertEqual(self.reader.meter.used['classARequests'],0)
        self.assertEqual(self.reader.meter.used['storedBytes'],0)
    def test_other_plan_refused_before_credentials(self):
        wrong=Ref(self.ref.key.replace(t.CHILD_PLAN,'0'*64),'123',self.ref.bytes,self.ref.sha256)
        with patch('rrgh_wif_credentials.token',side_effect=AssertionError('credential called')):
            with self.assertRaises(ValueError):self.reader.get(wrong)
        self.assertEqual(self.calls,[])
    def test_caps_reserved_before_request(self):
        self.reader.meter.used['classBRequests']=256
        with patch('rrgh_wif_credentials.token',side_effect=AssertionError('credential called')):
            with self.assertRaises(ValueError):self.reader.get(self.ref)
    def test_changed_bytes_refused(self):
        self.raw=b'incorrect data'
        with patch('rrgh_wif_credentials.token',return_value='test-only'):
            with self.assertRaises(ValueError):self.reader.get(self.ref)
    def test_no_write_or_listing_methods(self):
        for name in ('put','create','commit_job','close','receipt','list','delete'):
            self.assertFalse(hasattr(self.reader,name))
    def test_wrong_identity_refused(self):
        with self.assertRaises(ValueError):t.identity({})
    def test_workflow_trial_is_not_a_production_dependency(self):
        path=Path(__file__).parents[1]/'workflows/offline-map-restricted-dispatch.yml'
        text=path.read_text()
        self.assertEqual(text.count('parallel-render-trial'),1)
        block=text.split('  parallel-render-trial:',1)[1].split('  bounded-stage:',1)[0]
        self.assertIn('continue-on-error: true',block)
        self.assertIn("inputs.sequence == '261'",block)
        self.assertNotIn('contents: write',block);self.assertNotIn('actions: write',block)
        self.assertNotIn('GH_TOKEN',block)

if __name__=='__main__':unittest.main()
