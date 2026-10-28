import io
import tempfile
import unittest
from pathlib import Path

from cached_cog_source import Cache, BLOCK, official_url

URL = 'https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/test.tif'
DATA = bytes(range(256)) * 2048

class Response(io.BytesIO):
    def __init__(self, data=b'', status=200, headers=None, url=URL):
        super().__init__(data)
        self.status, self.headers, self.url = status, headers or {}, url
    def geturl(self):
        return self.url

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        self.fail = None
    def open(self, request, timeout=0):
        if request.get_method() == 'HEAD':
            return Response(headers={'Content-Length':str(len(DATA)), 'ETag':'"fixed"'})
        start,end = map(int, request.get_header('Range').split('=')[1].split('-'))
        self.calls.append((start,end))
        self.assertEqual(request.get_header('If-match'), '"fixed"')
        headers={'Content-Length':str(end-start+1),'ETag':'"fixed"',
                 'Content-Range':f'bytes {start}-{end}/{len(DATA)}'}
        if self.fail=='etag':headers['ETag']='"changed"'
        if self.fail=='truncated':return Response(b'x',206,headers)
        if self.fail=='200':return Response(DATA,200,headers)
        return Response(DATA[start:end+1],206,headers)
    def cache(self,limit=1_000_000):
        return Cache(self.tmp.name,limit=limit,opener=self.open)
    def test_coalesced_correct_partial_reads_and_restart_zero_network(self):
        c=self.cache();s=c.source(URL)
        self.assertEqual(c.read(s,10,BLOCK*3-10),DATA[10:BLOCK*3-9])
        self.assertEqual(len(self.calls),1)
        self.assertEqual(c.metrics()['receivedBytes'],BLOCK*3)
        c.close()
        c=self.cache();s=c.source(URL)
        self.assertEqual(c.read(s,17,BLOCK*2+7),DATA[17:BLOCK*2+8])
        self.assertEqual(len(self.calls),1)
        c.close()
    def test_changed_origin_truncated_and_full_response_fail_closed(self):
        for mode in ('etag','truncated','200'):
            self.fail=mode
            c=self.cache();s=c.source(URL)
            with self.assertRaises(ValueError):c.read(s,0,100)
            self.assertEqual(c.metrics()['reservedBytes'],BLOCK*(('etag','truncated','200').index(mode)+1))
            c.close()
    def test_failure_reservations_survive_restart(self):
        c=self.cache(BLOCK);s=c.source(URL);self.fail='200'
        with self.assertRaises(ValueError):c.read(s,0,100)
        c.close();self.fail=None
        c=self.cache(BLOCK);s=c.source(URL)
        with self.assertRaises(ValueError):c.read(s,0,100)
        self.assertEqual(len(self.calls),1);c.close()
    def test_corruption_is_not_reused_or_redownloaded(self):
        c=self.cache();s=c.source(URL);c.read(s,0,100)
        (Path(self.tmp.name)/'blocks'/s['identity']/'0').write_bytes(b'bad')
        with self.assertRaises(ValueError):c.read(s,0,100)
        self.assertEqual(len(self.calls),1);c.close()
    def test_cumulative_cap_cannot_silently_change(self):
        c=self.cache();c.close()
        with self.assertRaises(ValueError):self.cache(2_000_000)
    def test_second_producer_rejected(self):
        c=self.cache()
        with self.assertRaises(RuntimeError):self.cache()
        c.close()
    def test_reject_urls_and_unbounded_reads(self):
        for u in ('http://example.com/a.tif', URL+'?key=secret', 'https://kyfromabove.s3.us-west-2.amazonaws.com/tiles/a.tif'):
            with self.assertRaises(ValueError):official_url(u)
        c=self.cache();s=c.source(URL)
        for start,end in ((-1,2),(0,len(DATA)),(5,4)):
            with self.assertRaises(ValueError):c.read(s,start,end)
        self.assertFalse(self.calls);c.close()

if __name__=='__main__':unittest.main()
