#!/usr/bin/env python3
"""Private resumable region jobs. Default is plan/validate only; no cloud writes.

Immutable plans pin code, source inventory and budget limits. A durable SQLite
reservation survives crashes; one process/one job isolates native raster errors.
Existing cache ledgers are reused without raising their transfer ceilings.
"""
import argparse
import io
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import platform
import rasterio
from PIL import Image
import numpy as np
from rasterio.warp import transform_bounds
from shapely.geometry import box
from shapely.ops import unary_union
from cached_cog_source import Cache,atomic,digest
from benchmark_gorge_pipeline import AOI,json_bytes,mosaic,receipt_valid,file_entry
from benchmark_ky_naip_usgs import ServiceCache,NAIP,USGS,render_naip
from build_gorge_map_bundles import PROFILE
from build_gorge_base_native_v4 import xy
from pilot_official_cog_xyz import mercator_bounds

ROOT=Path(__file__).resolve().parents[2]
LAYERS={k:v for group in PROFILE.values() for k,v in group.items()}


def tile_coords(z):
    l,b=xy(AOI[0],AOI[1],z);r,t=xy(AOI[2],AOI[3],z)
    return [(x,y) for x in range(l,r+1) for y in range(t,b+1)]


def make_plan(inventory,limits,source_limits=None):
    if set(limits)!={'attempts','seconds','outputBytes','childSeconds'} or not (0<limits['attempts']<=70000 and 1<=limits['childSeconds']<=600 and limits['childSeconds']<=limits['seconds']<=30_000_000 and 0<limits['outputBytes']<=100_000_000_000):raise ValueError('Explicit bounded production limits required')
    source_limits=source_limits or {'cogBytes':250_000_000,'serviceBytes':80_000_000,'serviceRequests':120}
    if set(source_limits)!={'cogBytes','serviceBytes','serviceRequests'} or not (0<source_limits['cogBytes']<=1_000_000_000_000 and 0<source_limits['serviceBytes']<=1_000_000_000_000 and 0<source_limits['serviceRequests']<=2_000_000):raise ValueError('Bounded source ledger limits required')
    sources=inventory['sources'];jobs=[];coverage={}
    for layer in LAYERS:
        family='dem' if layer=='terrain' else layer
        if layer!='usgs-topo':
            shapes=[box(*s['bbox']) for s in sources.get(family,[])]
            coverage[layer]=box(*AOI).difference(unary_union(shapes)).area if shapes else .12
        # COG/NAIP high detail grouped into one source window, reused at 16..max.
        levels=range(10,17) if layer=='usgs-topo' else [16,*range(15,9,-1)]
        for z in levels:
            for x,y in tile_coords(z):
                n=2**z
                b=[x/n*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+1)/n)))),(x+1)/n*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*y/n))))]
                selected=[s['id'] for s in sources.get(family,[]) if s['bbox'][0]<b[2] and s['bbox'][2]>b[0] and s['bbox'][1]<b[3] and s['bbox'][3]>b[1]] if z==16 else []
                jobs.append({'id':f'{layer}-{z}-{x}-{y}','layer':layer,'z':z,'x':x,'y':y,'sourceIDs':selected,
                             'operation':'usgs-tile' if layer=='usgs-topo' else 'source-window' if z==16 else 'overview'})
    # Hash every local Python processing dependency, not just the controller.
    code={p.name:digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py')) if not p.name.startswith('test_')}
    return {'format':'rrgh-region-plan-v1','sourceLimits':source_limits,'boundsWGS84':AOI,'profiles':PROFILE,'limits':limits,'inventory':inventory,
            'runtime':{'python':platform.python_version(),'rasterio':rasterio.__version__,'GDAL':rasterio.__gdal_version__,'numpy':np.__version__},'inventorySHA256':digest(json_bytes(inventory)),'engineHashes':code,'jobs':jobs,'sourceBboxMissingSquareDegrees':coverage,
            'regionalPixelCoverageVerified':False,'cloudWrites':False,'actionsDispatch':False}


def private_root(root):
    root=Path(root).resolve()
    if 'public' in root.parts or root==ROOT.resolve() or ROOT.resolve() in root.parents:raise ValueError('Protected output must be outside source checkout/public paths')
    return root


def write_image(image,root,layer,z,x,y):
    if image.mode=='RGBA' and image.getextrema()[3]==(255,255):image=image.convert('RGB')
    ext='png' if image.mode=='RGBA' else 'jpg'
    path=root/f'tiles/{layer}/{z}/{x}/{y}.{ext}';path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path,format='PNG' if ext=='png' else 'JPEG',**({'compress_level':6} if ext=='png' else {'quality':90,'subsampling':0}))
    with Image.open(path) as check:check.load();assert check.size==(256,256)
    return file_entry(path,root)


def worker(plan,job,root,cog_cache,service_cache):
    root=private_root(root);caps=plan.get('sourceLimits',{'cogBytes':250_000_000,'serviceBytes':80_000_000,'serviceRequests':120});layer=job['layer'];z,x,y=(job[k] for k in ('z','x','y'));outputs=[];evidence=[]
    if job['operation']=='overview':
        image=Image.new('RGBA',(512,512));allowed=set(tile_coords(z+1))
        for dx in range(2):
            for dy in range(2):
                cx,cy=x*2+dx,y*2+dy
                if (cx,cy) not in allowed:continue  # Outside approved region only.
                children=list((root/f'tiles/{layer}/{z+1}/{cx}').glob(str(cy)+'.*'))
                if len(children)!=1:raise ValueError('Missing verified overview dependency')
                with Image.open(children[0]) as im:image.paste(im.convert('RGBA'),(dx*256,dy*256))
        outputs=[write_image(image.resize((256,256),Image.Resampling.LANCZOS),root,layer,z,x,y)]
    elif layer=='usgs-topo':
        cache=ServiceCache(service_cache,byte_limit=caps['serviceBytes'],request_limit=caps['serviceRequests'])
        try:
            raw,source=cache.fetch(f'{USGS}/tile/{z}/{y}/{x}',maximum=500_000)
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                if im.size!=(256,256):raise ValueError('USGS tile grid mismatch')
                extension='png' if im.format=='PNG' else 'jpg' if im.format=='JPEG' else None
                if not extension:raise ValueError('USGS encoding mismatch')
            path=root/f'tiles/{layer}/{z}/{x}/{y}.{extension}';atomic(path,raw);outputs=[file_entry(path,root)];evidence=[source]
        finally:cache.close()
    elif layer=='leaf-on':
        cache=ServiceCache(service_cache,byte_limit=caps['serviceBytes'],request_limit=caps['serviceRequests'])
        try:
            metadata,_=cache.fetch(NAIP,{'f':'pjson'});b=transform_bounds('EPSG:3857','EPSG:4326',*mercator_bounds(x,y,16))
            r=render_naip(cache,json.loads(metadata),{'id':job['id'],'lon':(b[0]+b[2])/2,'lat':(b[1]+b[3])/2},root)
            outputs=r['outputs'];evidence=[r['sourceExport']]
        finally:cache.close()
    else:
        family='dem' if layer=='terrain' else layer;sources=[s for s in plan['inventory']['sources'][family] if s['id'] in job['sourceIDs']]
        cache=Cache(cog_cache,limit=caps['cogBytes'],maximum_limit=1_000_000_000_000)
        try:
            bounds=mercator_bounds(x,y,16);size=256*2**(LAYERS[layer]-16)
            if layer=='terrain':
                halo=(bounds[2]-bounds[0])/size;b=[bounds[0]-halo,bounds[1]-halo,bounds[2]+halo,bounds[3]+halo]
                high,tr,evidence=mosaic(cache,sources,b,size+2,size+2,dem=True)
                ll=transform_bounds('EPSG:3857','EPSG:4326',*bounds);ground=abs(tr.a)*math.cos(math.radians((ll[1]+ll[3])/2))
                gy,gx=np.gradient(high[0],ground,ground);az,alt=math.radians(315),math.radians(45)
                shade=(-gx*math.sin(az)*math.cos(alt)+gy*math.cos(az)*math.cos(alt)+math.sin(alt))/np.sqrt(1+gx*gx+gy*gy)
                image=Image.fromarray(np.uint8(np.clip(255*(.25+.75*np.maximum(shade,0)),0,255))[1:-1,1:-1]).convert('RGB')
            else:
                array,tr,evidence=mosaic(cache,sources,bounds,size,size);image=Image.fromarray(array.transpose(1,2,0))
            for level in range(16,LAYERS[layer]+1):
                n=2**(level-16);scaled=image.resize((n*256,n*256),Image.Resampling.LANCZOS);allowed=set(tile_coords(level))
                for dx in range(n):
                    for dy in range(n):
                        xx,yy=x*n+dx,y*n+dy
                        if (xx,yy) in allowed:outputs.append(write_image(scaled.crop((dx*256,dy*256,(dx+1)*256,(dy+1)*256)),root,layer,level,xx,yy))
        finally:cache.close()
    # NAIP metatiles include edge children outside the exact regional XYZ set.
    outputs=[e for e in outputs if tuple(map(int,[e['path'].split('/')[3],Path(e['path']).stem])) in set(tile_coords(int(e['path'].split('/')[2])))]
    return {'job':job['id'],'validated':True,'outputs':outputs,'sourceEvidence':evidence,'recipeSHA256':digest(json_bytes(plan))}


def run(plan_path,root,cog_cache,service_cache,max_jobs=0):
    import fcntl
    root=private_root(root);root.mkdir(parents=True,exist_ok=True);plan=json.loads(Path(plan_path).read_text());recipe=digest(json_bytes(plan))
    if plan.get('format')!='rrgh-region-plan-v1' or plan['boundsWGS84']!=AOI or plan['profiles']!=PROFILE:raise ValueError('Invalid immutable region plan')
    for name,sha in plan['engineHashes'].items():
        if Path(name).name!=name or digest((Path(__file__).parent/name).read_bytes())!=sha:raise ValueError('Engine changed; new plan required')
    pinned=root/'PLAN.json'
    if pinned.exists() and pinned.read_bytes()!=json_bytes(plan):raise ValueError('Cannot reset source/budget plan on resume')
    atomic(pinned,json_bytes(plan))
    with (root/'producer.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=sqlite3.connect(root/'jobs.sqlite');db.execute('CREATE TABLE IF NOT EXISTS attempts(job TEXT,seconds INTEGER,status TEXT)')
        completed=[];attempted=0
        try:
            for job in plan['jobs']:
                receipt=root/'receipts'/(job['id']+'.json')
                if receipt.exists():
                    r=json.loads(receipt.read_text());receipt_valid(root,r,recipe);completed.append(r);continue
                if attempted>=max_jobs:continue
                count,seconds=db.execute('SELECT COUNT(*),COALESCE(SUM(seconds),0) FROM attempts').fetchone();limits=plan['limits']
                disk=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
                if count>=limits['attempts'] or seconds+limits['childSeconds']>limits['seconds'] or disk+32_000_000>limits['outputBytes'] or shutil.disk_usage(root).free<64_000_000:raise ValueError('Cumulative job/time/output/free-space ceiling reached')
                if db.execute('SELECT COUNT(*) FROM attempts WHERE job=?',(job['id'],)).fetchone()[0]>=2:raise ValueError('Two-attempt recovery ceiling reached')
                reservation=db.execute('INSERT INTO attempts VALUES (?,?,?)',(job['id'],limits['childSeconds'],'reserved')).lastrowid;db.commit();attempted+=1
                command=[sys.executable,str(Path(__file__).resolve()),'--plan',str(Path(plan_path).resolve()),'--output',str(root),'--cog-cache',str(Path(cog_cache).resolve()),'--service-cache',str(Path(service_cache).resolve()),'--worker',job['id'],'--reservation',str(reservation)]
                log=root/'logs'/(job['id']+f'-{reservation}.log');log.parent.mkdir(exist_ok=True)
                try:
                    with log.open('wb') as stream:r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=limits['childSeconds'],env={**os.environ,'GDAL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'},check=False)
                    status=str(r.returncode)
                except subprocess.TimeoutExpired:status='timeout'
                db.execute('UPDATE attempts SET status=? WHERE rowid=?',(status,reservation));db.commit()
                if not receipt.exists():raise RuntimeError('Job failed; committed work/cache retained: '+job['id'])
                r=json.loads(receipt.read_text());receipt_valid(root,r,recipe);completed.append(r)
            result={'recipeSHA256':recipe,'receipts':completed,'jobsCompleted':len(completed),'jobsPlanned':len(plan['jobs']),'allJobsComplete':len(completed)==len(plan['jobs']),'attempts':db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],'cloudWrites':False}
            atomic(root/'BENCHMARK.json',json_bytes(result));return result
        finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--cog-cache',required=True);p.add_argument('--service-cache',required=True);p.add_argument('--max-jobs',type=int,default=0);p.add_argument('--live-source',action='store_true');p.add_argument('--worker');p.add_argument('--reservation',type=int);p.add_argument('--drain-bounded-plan',action='store_true');a=p.parse_args()
    if not 0<=a.max_jobs<=12 or ((a.max_jobs or a.drain_bounded_plan) and not a.live_source):p.error('Explicit bounded invocation required (0..12 jobs)')
    if a.worker:
        root=private_root(a.output)
        if not a.reservation or not (root/'jobs.sqlite').exists() or (root/'PLAN.json').read_bytes()!=a.plan.read_bytes():raise ValueError('Worker requires parent reservation')
        db=sqlite3.connect(root/'jobs.sqlite')
        changed=db.execute("UPDATE attempts SET status='running' WHERE rowid=? AND job=? AND status='reserved'",(a.reservation,a.worker)).rowcount;db.commit();db.close()
        if changed!=1:raise ValueError('Worker reservation already consumed or invalid')
        plan=json.loads(a.plan.read_text());job=next(j for j in plan['jobs'] if j['id']==a.worker);r=worker(plan,job,a.output,a.cog_cache,a.service_cache);atomic(a.output/'receipts'/(job['id']+'.json'),json_bytes(r))
    else:
        maximum=json.loads(a.plan.read_text())['limits']['attempts'] if a.drain_bounded_plan else a.max_jobs
        r=run(a.plan,a.output,a.cog_cache,a.service_cache,maximum);print(json.dumps({k:v for k,v in r.items() if k!='receipts'},indent=2))
