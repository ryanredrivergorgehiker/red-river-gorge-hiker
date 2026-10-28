#!/usr/bin/env python3
"""Bounded public-government leaf-on and USGS benchmark, with durable reuse.

NAIP is a lossless four-band, native-grid ImageServer export, not an original
source GeoTIFF download. USGS tiles are retained byte-for-byte at each zoom;
lower cartographic zooms must not be synthesized from the high-zoom image.
"""
import argparse
import io
import json
import math
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from cached_cog_source import atomic, digest
from benchmark_gorge_pipeline import pyramid, detail_metrics, file_entry, json_bytes, receipt_valid, AOI
from build_gorge_base_native_v4 import xy
from pilot_official_cog_xyz import mercator_bounds

NAIP = 'https://kyraster.ky.gov/arcgis/rest/services/ImageServices/Ky_NAIP_2022_2FT/ImageServer'
USGS = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer'


class ServiceCache:
    def __init__(self, root, byte_limit=80_000_000, request_limit=120):
        import fcntl
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / 'producer.lock').open('a+')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.db = sqlite3.connect(self.root / 'requests.sqlite')
        self.db.executescript('CREATE TABLE IF NOT EXISTS budget(bytes INTEGER,requests INTEGER); CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,key TEXT,reserved INTEGER,received INTEGER,status TEXT,seconds REAL);')
        old = self.db.execute('SELECT * FROM budget').fetchone()
        if old and old != (byte_limit, request_limit):
            self.close()
            raise ValueError('Cannot reset reservation limits on resume')
        if not old: self.db.execute('INSERT INTO budget VALUES (?,?)',(byte_limit,request_limit));self.db.commit()
        self.byte_limit,self.request_limit=byte_limit,request_limit

    def close(self):
        self.db.close();self.lock.close()

    def metrics(self):
        r=self.db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0),COALESCE(SUM(seconds),0) FROM calls').fetchone()
        return dict(requests=r[0],reservedBytes=r[1],receivedBytes=r[2],networkSeconds=r[3])

    def fetch(self,url,params=None,maximum=1_000_000):
        if not (url in (NAIP,NAIP+'/query',NAIP+'/exportImage',USGS) or url.startswith(USGS+'/tile/')):
            raise ValueError('Unapproved government endpoint')
        if not 0 < maximum <= 8_000_000: raise ValueError('Unbounded request')
        full=url+('?' + urlencode(sorted((params or {}).items())) if params else '')
        key=digest(full.encode());meta=self.root/(key+'.json');data=self.root/(key+'.bin')
        if meta.exists():
            m=json.loads(meta.read_text());raw=data.read_bytes()
            if digest(raw)!=m['sha256'] or len(raw)!=m['bytes']:raise ValueError('Cached service response corrupted')
            if m.get('status') == 404:raise ValueError('Pinned source 404: no tile at this coordinate/zoom')
            return raw,m
        usage=self.metrics()
        if usage['reservedBytes']+maximum>self.byte_limit or usage['requests']>=self.request_limit:
            raise ValueError('Persistent service benchmark budget reached')
        cur=self.db.execute('INSERT INTO calls(key,reserved,received,status,seconds) VALUES (?,?,0,?,0)',(key,maximum,'reserved'));self.db.commit()
        start=time.perf_counter();received=0
        try:
            with urlopen(Request(full,headers={'Accept-Encoding':'identity'}),timeout=45) as r:
                if r.status!=200 or r.geturl()!=full:raise ValueError('Government export status/redirect rejected')
                raw=r.read(maximum+1);received=len(raw)
                if received>maximum:raise ValueError('Response exceeds bounded reservation')
                m={'url':url,'parameters':params or {},'sha256':digest(raw),'bytes':len(raw),'contentType':r.headers.get('Content-Type'),
                   'etag':r.headers.get('ETag'),'lastModified':r.headers.get('Last-Modified'),'retrievedUTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            atomic(data,raw);atomic(meta,json_bytes(m))
            self.db.execute("UPDATE calls SET received=?,reserved=?,status='complete',seconds=? WHERE id=?",(received,received,time.perf_counter()-start,cur.lastrowid));self.db.commit()
            return raw,m
        except Exception as error:
            if isinstance(error,HTTPError) and error.code==404:
                atomic(data,b'');atomic(meta,json_bytes({'url':url,'parameters':params or {},'status':404,'sha256':digest(b''),'bytes':0}))
            self.db.execute("UPDATE calls SET received=?,status='failed',seconds=? WHERE id=?",(received,time.perf_counter()-start,cur.lastrowid));self.db.commit();raise


def naip_parameters(bounds,service):
    b=transform_bounds('EPSG:3857','EPSG:3089',*bounds,densify_pts=21)
    e=service['fullExtent'];pixel=2.0
    left=e['xmin']+math.floor((b[0]-e['xmin'])/pixel)*pixel
    top=e['ymax']-math.floor((e['ymax']-b[3])/pixel)*pixel
    width=math.ceil((b[2]-left)/pixel);height=math.ceil((top-b[1])/pixel)
    if max(width,height)>15000:raise ValueError('Exceeds source image export dimensions')
    return {'f':'image','bbox':','.join(map(str,[left,top-height*pixel,left+width*pixel,top])),
            'bboxSR':3089,'imageSR':3089,'size':f'{width},{height}','format':'tiff','pixelType':'U8',
            'bandIds':'0,1,2,3','compression':'LZ77','interpolation':'RSP_NearestNeighbor','adjustAspectRatio':'false'}


def render_naip(cache,service,sample,root):
    x,y=xy(sample['lon'],sample['lat'],16);bounds=mercator_bounds(x,y,16)
    params=naip_parameters(bounds,service);raw,source=cache.fetch(NAIP+'/exportImage',params,8_000_000)
    original=root/'source-exports'/(sample['id']+'.tif');atomic(original,raw)
    with rasterio.open(original) as ds:
        if ds.crs.to_epsg()!=3089 or ds.count!=4 or ds.transform.a!=2 or ds.transform.e!=-2:
            raise ValueError('Source export native grid/four-band contract mismatch')
        if not np.all(ds.dataset_mask()==255):raise ValueError('NAIP source has no-data pixels')
        with WarpedVRT(ds,crs='EPSG:3857',transform=from_bounds(*bounds,1024,1024),width=1024,height=1024,resampling=Resampling.bilinear) as v:
            rgb=v.read([1,2,3]);mask=v.dataset_mask()
        if not np.all(mask==255) or max(float(b.std()) for b in rgb)<1:raise ValueError('NAIP coverage/imagery failure')
        image=Image.fromarray(rgb.transpose(1,2,0))
        outputs,zooms=pyramid(image,root,'leaf-on',x,y)
        return {'outputs':outputs,'zooms':zooms,'sourceExport':source,'sourcePixelMeters':2*1200/3937,
                'sourcePixelCoverage':1.0,'bandsRetainedInSourceCache':4,'sourceType':'government lossless native-grid export; not original TIFF',
                'detailMetrics':detail_metrics(image)}


def render_usgs(cache,sample,root):
    x,y=xy(sample['lon'],sample['lat'],16);outputs=[];zooms=[];sources=[]
    for z in (16,17,18):
        total=0;valid=0;errors=[]
        for dx in range(2**(z-16)):
            for dy in range(2**(z-16)):
                xx,yy=x*2**(z-16)+dx,y*2**(z-16)+dy
                try:
                    raw,source=cache.fetch(f'{USGS}/tile/{z}/{yy}/{xx}',maximum=500_000)
                    with Image.open(io.BytesIO(raw)) as tile:
                        tile.load();a=np.asarray(tile.convert('RGB'))
                        if tile.size!=(256,256) or max(float(b.std()) for b in a.transpose(2,0,1))<1:raise ValueError('Blank/non-256px USGS tile')
                        ext='png' if tile.format=='PNG' else 'jpg' if tile.format=='JPEG' else None
                        if not ext:raise ValueError('Unsupported official tile format')
                    path=root/'tiles/usgs-topo'/str(z)/str(xx)/(str(yy)+'.'+ext);atomic(path,raw)
                    outputs.append(file_entry(path,root));sources.append(source);total+=len(raw);valid+=1
                except Exception as error:
                    missing = (isinstance(error, HTTPError) and error.code == 404) or (
                        isinstance(error, ValueError) and str(error).startswith('Pinned source 404:'))
                    if not missing:
                        raise  # Retry transport, budget and integrity failures; never call them absent imagery.
                    errors.append({'xyz':[z,xx,yy],'reason':str(error)[:250]})
        zooms.append({'zoom':z,'tileCount':valid,'bytes':total,'expectedTiles':4**(z-16),'failures':errors})
    if not zooms[0]['tileCount']:
        raise ValueError('Required USGS z16 benchmark tile unavailable')
    return {'outputs':outputs,'zooms':zooms,'sourceResponses':sources,'sourceType':'official cached cartography bytes unchanged; independent levels'}


def render_usgs_overview(cache,samples,root):
    """Fetch each distinct low-zoom cartographic tile once, without resampling."""
    outputs=[];zooms=[];sources=[]
    for z in range(10,16):
        cells=sorted({xy(s['lon'],s['lat'],z) for s in samples});total=0
        for x,y in cells:
            raw,source=cache.fetch(f'{USGS}/tile/{z}/{y}/{x}',maximum=500_000)
            with Image.open(io.BytesIO(raw)) as tile:
                tile.load()
                if tile.size!=(256,256) or np.asarray(tile.convert('RGB')).std()<1:
                    raise ValueError('Invalid USGS overview tile')
                ext={'PNG':'png','JPEG':'jpg'}.get(tile.format)
                if not ext:raise ValueError('Unsupported USGS overview format')
            path=root/'tiles/usgs-topo'/str(z)/str(x)/(str(y)+'.'+ext)
            atomic(path,raw);outputs.append(file_entry(path,root));sources.append(source);total+=len(raw)
        zooms.append({'zoom':z,'tileCount':len(cells),'bytes':total,'expectedTiles':len(cells),'failures':[]})
    return {'outputs':outputs,'zooms':zooms,'sourceResponses':sources,'sourceType':'official independent overview cartography; no downsampling'}


def run(root,cache_root,samples):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);cache=ServiceCache(cache_root)
    start=time.perf_counter();before=cache.metrics()
    try:
        nraw,_=cache.fetch(NAIP,{'f':'pjson'});service=json.loads(nraw)
        uraw,_=cache.fetch(USGS,{'f':'pjson'});usgs=json.loads(uraw)
        query={'f':'json','where':'Category=1','geometry':','.join(map(str,AOI)),'geometryType':'esriGeometryEnvelope',
               'inSR':4326,'outSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'*','returnGeometry':'true','resultRecordCount':1000}
        qraw,_=cache.fetch(NAIP+'/query',query);footprints=json.loads(qraw)
        if footprints.get('exceededTransferLimit') or not footprints.get('features'):raise ValueError('Incomplete NAIP footprints')
        polygons=[Polygon(f['geometry']['rings'][0]).buffer(0) for f in footprints['features']]
        uncovered=box(*AOI).difference(unary_union(polygons)).area
        atomic(root/'SOURCE-SERVICE-METADATA.json',json_bytes({'naip':service,'usgs':usgs,'naipFootprints':footprints,'uncoveredFootprintSquareDegrees':uncovered}))
        recipe=digest(json_bytes({'engine':digest(Path(__file__).read_bytes()),'naip':digest(nraw),'usgs':digest(uraw),
                                 'footprints':digest(qraw),'samples':samples}))
        receipts=[]
        for sample in samples:
            for role in ('leaf-on','usgs-topo'):
                key=sample['id']+'-'+role;p=root/'receipts'/(key+'.json')
                if p.exists():
                    r=json.loads(p.read_text());receipt_valid(root,r,recipe);receipts.append({**r,'reused':True});continue
                t=time.perf_counter();m=cache.metrics()
                result=render_naip(cache,service,sample,root) if role=='leaf-on' else render_usgs(cache,sample,root)
                after=cache.metrics();r={'job':key,'validated':True,'recipeSHA256':recipe,'elapsedSeconds':time.perf_counter()-t,
                                      'sourceBytes':after['receivedBytes']-m['receivedBytes'],'sourceRequests':after['requests']-m['requests'],**result}
                atomic(p,json_bytes(r));receipts.append(r);print(json.dumps({k:r[k] for k in ('job','elapsedSeconds','sourceBytes','sourceRequests')}),flush=True)
        p=root/'receipts/usgs-topo-overview.json'
        if p.exists():
            r=json.loads(p.read_text());receipt_valid(root,r,recipe);receipts.append({**r,'reused':True})
        else:
            t=time.perf_counter();m=cache.metrics();result=render_usgs_overview(cache,samples,root);after=cache.metrics()
            r={'job':'usgs-topo-overview','validated':True,'recipeSHA256':recipe,'elapsedSeconds':time.perf_counter()-t,
               'sourceBytes':after['receivedBytes']-m['receivedBytes'],'sourceRequests':after['requests']-m['requests'],**result}
            atomic(p,json_bytes(r));receipts.append(r)
        report={'status':'SOURCE BENCHMARK; NOT REGIONAL PRODUCTION','recipeSHA256':recipe,'elapsedThisInvocationSeconds':time.perf_counter()-start,
                'before':before,'after':cache.metrics(),'receipts':receipts,'failures':[],'skipped':[],
                'coverageFootprints':{'count':len(polygons),'uncoveredSquareDegrees':uncovered,'fullRegionalPixelsVerified':False},'actualIPhoneMeasured':False}
        atomic(root/'BENCHMARK.json',json_bytes(report));return report
    finally:cache.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--live-source-benchmark',action='store_true');a=p.parse_args()
    if not a.live_source_benchmark:p.error('Explicit bounded source benchmark required')
    samples=json.loads(a.plan.read_text())['samples']
    if not 1<=len(samples)<=3 or any(not(AOI[0]<=s['lon']<=AOI[2] and AOI[1]<=s['lat']<=AOI[3]) for s in samples):p.error('At most three Gorge samples')
    run(a.output,a.cache,samples)
