import io
import json
from urllib.error import HTTPError

import pytest

import benchmark_ky_naip_usgs as engine
from cached_cog_source import digest


class Response(io.BytesIO):
    status=200
    headers={'Content-Type':'image/tiff'}
    def __init__(self,url,raw):super().__init__(raw);self.url=url
    def geturl(self):return self.url


def test_service_cache_resume_and_corruption(tmp_path,monkeypatch):
    calls=[]
    def open_request(req,**kw):calls.append(req.full_url);return Response(req.full_url,b'original-export')
    monkeypatch.setattr(engine,'urlopen',open_request)
    a=engine.ServiceCache(tmp_path);first,_=a.fetch(engine.NAIP);a.close()
    b=engine.ServiceCache(tmp_path);second,_=b.fetch(engine.NAIP);assert first==second and len(calls)==1
    next(tmp_path.glob('*.bin')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='corrupted'):b.fetch(engine.NAIP)
    b.close()


def test_missing_official_zoom_is_pinned_without_redownload(tmp_path,monkeypatch):
    calls=[]
    def absent(req,**kw):calls.append(1);raise HTTPError(req.full_url,404,'Not Found',{},None)
    monkeypatch.setattr(engine,'urlopen',absent)
    a=engine.ServiceCache(tmp_path);url=engine.USGS+'/tile/18/1/1'
    with pytest.raises(HTTPError):a.fetch(url)
    with pytest.raises(ValueError,match='Pinned source 404'):a.fetch(url)
    assert len(calls)==1 and a.metrics()['reservedBytes']==1_000_000;a.close()


def test_native_grid_export_preserves_four_bands_and_resolution():
    service={'fullExtent':{'xmin':3798937.7561208904,'ymax':4307216.690109557}}
    b=engine.mercator_bounds(*engine.xy(-83.57903,37.81886,16),16)
    p=engine.naip_parameters(b,service);left,bottom,right,top=map(float,p['bbox'].split(','));w,h=map(int,p['size'].split(','))
    assert (right-left)/w==2 and (top-bottom)/h==2
    assert p['bandIds']=='0,1,2,3' and p['compression']=='LZ77' and p['imageSR']==3089


def test_endpoint_and_transfer_limits_are_not_bypassable(tmp_path):
    a=engine.ServiceCache(tmp_path)
    with pytest.raises(ValueError,match='Unapproved'):a.fetch('https://example.com/tile')
    with pytest.raises(ValueError,match='Unbounded'):a.fetch(engine.NAIP,maximum=80_000_000)
    a.close()
    with pytest.raises(ValueError,match='reset'):engine.ServiceCache(tmp_path,byte_limit=90_000_000)


def test_usgs_transport_failures_are_not_reported_as_missing_zoom(tmp_path):
    class Cache:
        def fetch(self, *args, **kwargs): raise TimeoutError('source timed out')
    with pytest.raises(TimeoutError):
        engine.render_usgs(Cache(), {'lon': -83.6, 'lat': 37.8}, tmp_path)


def test_usgs_required_level_cannot_silently_validate_empty(tmp_path):
    class Cache:
        def fetch(self, *args, **kwargs): raise ValueError('Pinned source 404: no tile')
    with pytest.raises(ValueError, match='Required USGS z16'):
        engine.render_usgs(Cache(), {'lon': -83.6, 'lat': 37.8}, tmp_path)
