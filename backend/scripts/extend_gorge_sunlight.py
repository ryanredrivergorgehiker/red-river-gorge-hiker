#!/usr/bin/env python3
"""Extend accepted Sunlight privately; retain all 30 accepted sectors verbatim.

Exact accepted algorithms are imported from the existing source scripts. This
worker uses the explicitly ZMeters government service, never the foot-valued COG.
No Actions dispatch, cloud upload, catalog activation or public output path.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sqlite3
import time

import numpy as np
from PIL import Image
import rasterio
import requests
from shapely.geometry import box
from shapely.ops import unary_union
from cached_cog_source import atomic, digest
from benchmark_gorge_pipeline import AOI,json_bytes

ROOT=Path(__file__).resolve().parents[2]
SERVICE='https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase2_ZMeters_WGS84WM/ImageServer'
BYTE_CAP=1_000_000_000
REQUEST_CAP=101


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def accepted_modules():
    return (module('accepted_sun','generate-rrg-lidar-sun.py'),
            module('accepted_continuous','generate-rrg-lidar-sun-continuous.py'),
            module('accepted_mobile','generate-rrg-lidar-sun-mobile.py'))


def extension_grid(existing):
    old={tuple(round(v,8) for v in s['boundsWgs84']):s for s in existing}
    result=[]
    for row in range(-1,7):
        for col in range(-2,8):
            b=[max(AOI[0],-.0-83.745+col*.045),max(AOI[1],37.93-(row+1)*.04),
               min(AOI[2],-83.745+(col+1)*.045),min(AOI[3],37.93-row*.04)]
            b=[round(v,8) for v in b]
            if b[0]>=b[2] or b[1]>=b[3]:continue
            if tuple(b) in old:continue
            result.append({'id':f'extension-r{row+2}c{col+3}','boundsWgs84':b})
    if box(*AOI).difference(unary_union([box(*s['boundsWgs84']) for s in [*existing,*result]])).area>1e-10:
        raise ValueError('Sunlight plan leaves a coverage gap')
    return result


class Cache:
    def __init__(self,root):
        import fcntl
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=(self.root/'producer.lock').open('a+');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.db=sqlite3.connect(self.root/'requests.sqlite')
        self.db.executescript('CREATE TABLE IF NOT EXISTS limits(bytes INTEGER,requests INTEGER);CREATE TABLE IF NOT EXISTS calls(key TEXT,reserved INTEGER,received INTEGER,seconds REAL,status TEXT);')
        old=self.db.execute('SELECT * FROM limits').fetchone()
        if old and old!=(BYTE_CAP,REQUEST_CAP):raise ValueError('Immutable Sunlight transfer ceiling mismatch')
        if not old:self.db.execute('INSERT INTO limits VALUES (?,?)',(BYTE_CAP,REQUEST_CAP));self.db.commit()
    def close(self):self.db.close();self.lock.close()
    def metrics(self):
        r=self.db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0),COALESCE(SUM(seconds),0) FROM calls').fetchone()
        return dict(requests=r[0],reservedBytes=r[1],receivedBytes=r[2],networkSeconds=r[3],byteCeiling=BYTE_CAP,requestCeiling=REQUEST_CAP)
    def fetch(self,params):
        key=digest(json_bytes(params));meta=self.root/(key+'.json');path=self.root/(key+'.tif')
        if meta.exists():
            m=json.loads(meta.read_text())
            if path.stat().st_size!=m['bytes'] or digest(path.read_bytes())!=m['sha256']:raise ValueError('Pinned DEM cache corrupted')
            return path,m
        maximum=40_000_000;usage=self.metrics()
        if usage['requests']>=REQUEST_CAP or usage['reservedBytes']+maximum>BYTE_CAP:raise ValueError('Sunlight cumulative transfer ceiling reached')
        cur=self.db.execute('INSERT INTO calls VALUES (?,?,0,0,?)',(key,maximum,'reserved'));self.db.commit()
        start=time.perf_counter();raw=bytearray()
        try:
            with requests.get(SERVICE+'/exportImage',params=params,timeout=(15,90),stream=True,allow_redirects=False) as response:
                response.raise_for_status()
                if response.status_code!=200:raise ValueError('Unexpected source status')
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw)>maximum:raise ValueError('DEM exceeds bounded export reservation')
            m={'sourceURL':SERVICE,'parameters':params,'bytes':len(raw),'sha256':digest(raw),'elevationUnits':'meters',
               'retrievedUTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            atomic(path,raw);atomic(meta,json_bytes(m))
            self.db.execute("UPDATE calls SET received=?,reserved=?,seconds=?,status='complete' WHERE rowid=?",(len(raw),len(raw),time.perf_counter()-start,cur.lastrowid));self.db.commit()
            return path,m
        except Exception:
            self.db.execute("UPDATE calls SET received=?,seconds=?,status='failed' WHERE rowid=?",(len(raw),time.perf_counter()-start,cur.lastrowid));self.db.commit();raise


def dem_params(bounds,accepted):
    west,south,east,north=bounds;x1,y1=accepted.TO_WEB.transform(west,south);x2,y2=accepted.TO_WEB.transform(east,north)
    x1-=180;y1-=180;x2+=180;y2+=180
    cols=math.ceil((x2-x1)/2.5);rows=math.ceil((y2-y1)/2.5)
    if cols>15000 or rows>4100:raise ValueError('Service export dimension ceiling')
    return {'f':'image','bbox':f'{x1:.6f},{y1:.6f},{x2:.6f},{y2:.6f}','bboxSR':'3857','imageSR':'3857',
            'size':f'{cols},{rows}','format':'tiff','pixelType':'F32','compression':'LZ77',
            'interpolation':'RSP_BilinearInterpolation','adjustAspectRatio':'false','returnSquarePixels':'false'}


def process(sector,cache,out,modules,recipe):
    accepted,continuous,mobile=modules;bounds=sector['boundsWgs84'];sid=sector['id'];start=time.perf_counter()
    source,meta=cache.fetch(dem_params(bounds,accepted))
    with rasterio.open(source) as ds:
        dem=ds.read(1);transform=ds.transform
        if ds.crs.to_epsg()!=3857 or not np.all(ds.dataset_mask()==255) or not np.isfinite(dem).all():raise ValueError('Incomplete meter DEM')
    if not math.isclose(accepted.MIN_ELEVATION_M,335.28,rel_tol=0,abs_tol=1e-9):raise ValueError('Accepted elevation threshold changed')
    fields=accepted.terrain_fields(dem,transform);features=[];rasters={};outputs=[]
    for kind,direction,rgb in [('sunrise','east',continuous.SUNRISE_RGB),('sunset','west',continuous.SUNSET_RGB)]:
        alpha=accepted.trace_alpha(dem,transform,fields[direction+'_lip'],fields['allowed'],fields[direction+'_distance'],fields[direction+'_indices'],fields['smooth'])
        # Use the exact accepted hard-vector implementation. A zero fade array
        # avoids unnecessary six-band polygon generation; hard_mask is unchanged.
        features+=accepted.vectorize(np.zeros_like(alpha),fields[direction+'_lip'],transform,kind,accepted.core_polygon_web(bounds),sid)
        core=continuous.crop_to_core(accepted,alpha,transform,bounds)
        rasters[kind]=Image.fromarray(continuous.rgba_for_kind(core,rgb))
    hard={'type':'FeatureCollection','features':features};hard_path=out/'hard'/(sid+'.geojson');atomic(hard_path,json_bytes(hard))
    variants={}
    for name,width in [('overview',256),('detail',768)]:
        variants[name]={}
        for kind in ('sunrise','sunset'):
            src=rasters[kind];height=max(1,round(src.height*width/src.width));target=src.resize((width,height),Image.Resampling.LANCZOS)
            target=Image.alpha_composite(target,mobile.hard_overlay(hard,kind,bounds,target.size))
            rel=f'data/map/rrg-lidar-sun-mobile/{sid}-{kind}-{name}.webp';p=out/rel;p.parent.mkdir(parents=True,exist_ok=True)
            target.save(p,format='WEBP',lossless=True,quality=100,method=4)
            with Image.open(p) as check:check.load();assert check.size==target.size
            entry={'file':rel,'bytes':p.stat().st_size,'sha256':digest(p.read_bytes()),'shape':[height,width]}
            variants[name][kind]=entry;outputs.append(entry)
    return {**sector,'sourceRasterShape':[rasters['sunrise'].height,rasters['sunrise'].width],'sourceDEM':meta,
            'sourceHardSha256':digest(hard_path.read_bytes()),'hardFeatures':len(features),'variants':variants,
            'recipeSHA256':recipe,'elapsedSeconds':time.perf_counter()-start,'elevationMetersRange':[float(dem.min()),float(dem.max())],
            'outputs':outputs,'hardFile':str(hard_path.relative_to(out))}


def run(accepted_root,out,cache_root,max_new_sectors,max_seconds,live):
    accepted_root=Path(accepted_root);out=Path(out)
    if 'public' in out.resolve().parts or ROOT.resolve() in out.resolve().parents:raise ValueError('Generated protected content must be outside repository/public paths')
    manifest=json.loads((accepted_root/'data/map/rrg-lidar-sun-mobile-manifest.json').read_text())
    if manifest['minimumElevationFeet']!=1100 or not manifest.get('acceptedHardLipReusedVerbatim') or len(manifest['sectors'])!=30:raise ValueError('Accepted lineage mismatch')
    mods=accepted_modules();sources={p.name:digest(p.read_bytes()) for p in (ROOT/'scripts').glob('generate-rrg-lidar-sun*.py')}
    recipe=digest(json_bytes({'code':digest(Path(__file__).read_bytes()),'acceptedCode':sources,'acceptedManifest':digest(json_bytes(manifest))}))
    grid=extension_grid(manifest['sectors']);out.mkdir(parents=True,exist_ok=True)
    plan={'boundsWgs84':AOI,'acceptedSectors':30,'newSectors':grid,'recipeSHA256':recipe,'sourceCode':sources,'minimumElevationMeters':335.28,'serviceElevationUnits':'meters','byteCap':BYTE_CAP,'requestCap':REQUEST_CAP}
    planpath=out/'PLAN.json'
    if planpath.exists() and json.loads(planpath.read_text())!=plan:raise ValueError('Immutable recipe changed; new output directory required')
    atomic(planpath,json_bytes(plan));sectors=list(manifest['sectors'])
    for sector in sectors:
        for variant in sector['variants'].values():
            for e in variant.values():
                source=accepted_root/e['file'];dest=out/e['file']
                if digest(source.read_bytes())!=e['sha256']:raise ValueError('Accepted Sunlight content changed')
                if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
                if digest(dest.read_bytes())!=e['sha256']:raise ValueError('Retained accepted Sunlight corrupted')
    cache=Cache(cache_root);start=time.perf_counter();processed=0
    try:
        for sector in grid:
            path=out/'receipts'/(sector['id']+'.json')
            if path.exists():
                r=json.loads(path.read_text())
                if digest((out/r['hardFile']).read_bytes())!=r['sourceHardSha256']:raise ValueError('Hard-rim receipt mismatch')
                if r['recipeSHA256']!=recipe or any(digest((out/e['file']).read_bytes())!=e['sha256'] for e in r['outputs']):raise ValueError('Sunlight receipt mismatch')
                sectors.append(r);continue
            if not live or processed>=max_new_sectors or time.perf_counter()-start>=max_seconds:continue
            r=process(sector,cache,out,mods,recipe);atomic(path,json_bytes(r));sectors.append(r);processed+=1
            print(json.dumps({'id':r['id'],'seconds':r['elapsedSeconds'],'sourceBytes':r['sourceDEM']['bytes'],'outputBytes':sum(e['bytes'] for e in r['outputs'])}),flush=True)
        complete=len(sectors)==30+len(grid)
        result={**manifest,'sectors':sectors,'boundsWgs84':AOI,'fullGorgeCoverageVerified':complete,
                'coverageMissingSquareDegrees':box(*AOI).difference(unary_union([box(*s['boundsWgs84']) for s in sectors])).area,
                'extendedUsingAcceptedAlgorithm':True,'acceptedSectorsPreserved':30,'recipeSHA256':recipe,
                'sourceLedger':cache.metrics(),'newSectorsProcessed':processed,'elapsedSeconds':time.perf_counter()-start,
                'counts':{'sectors':len(sectors),'files':len(sectors)*4,'bytes':sum(e['bytes'] for s in sectors for v in s['variants'].values() for e in v.values()),'hardFeatures':sum(s['hardFeatures'] for s in sectors)}}
        atomic(out/'data/map/rrg-lidar-sun-mobile-manifest.json',json_bytes(result));atomic(out/'SUNLIGHT-RESULT.json',json_bytes(result));return result
    finally:cache.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--accepted-root',required=True);p.add_argument('--output',required=True);p.add_argument('--cache',required=True)
    p.add_argument('--max-new-sectors',type=int,default=0);p.add_argument('--max-seconds',type=int,default=600);p.add_argument('--live-source',action='store_true');a=p.parse_args()
    if not 0<=a.max_new_sectors<=50 or not 1<=a.max_seconds<=3600:p.error('Bounded job/time ceilings required')
    r=run(a.accepted_root,a.output,a.cache,a.max_new_sectors,a.max_seconds,a.live_source);print(json.dumps({k:r[k] for k in ['counts','sourceLedger','fullGorgeCoverageVerified','coverageMissingSquareDegrees']},indent=2))
