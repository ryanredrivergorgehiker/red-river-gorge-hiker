"""Bounded full-window native-pixel validation of reviewed public source candidates.

Uses the unchanged production mosaic engine and existing per-job source limits.
No Cloud authentication, package publication, production source mutation or
accepted cache reuse. All pixel/cache data stays on the private ephemeral runner.
Evidence covers exactly three selected windows, never the entire catalog.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
import zlib

from rrgh_required_inventory import Manifest,canonical,require
from rrgh_source_window_intake import load_catalog,windows,clip


CAPS={'hiking':(67108864,150),'terrain':(134217728,200),'leaf-off':(536870912,750)}


def select(spec,catalog,region):
    manifest=Manifest(spec);chosen={}
    for window in windows(manifest,catalog):
        layer=window['layer'];family='dem' if layer=='terrain' else layer
        if layer in chosen or not window['metadataFullWindowCovered']:continue
        if any(clip(window['boundsWGS84'],s['bbox']) for s in region['inventory']['sources'][family]):continue
        sources=[s for s in catalog[family] if s['id'] in window['sourceCandidates']]
        if not sources or len(sources)>8:continue
        chosen[layer]={'window':window,'sources':sources}
    require(set(chosen)==set(CAPS),'Three fresh full-window candidates required')
    return [chosen[layer] for layer in CAPS]


def child(ticket):
    data=json.loads(Path(ticket).read_bytes());source=Path(data['source']).resolve()
    sys.path.insert(0,str(source/'backend/scripts'))
    from cached_cog_source import Cache
    from benchmark_gorge_pipeline import mosaic
    from pilot_official_cog_xyz import mercator_bounds
    from pyproj import CRS
    import rasterio
    import numpy as np
    window=data['candidate']['window'];sources=data['candidate']['sources'];layer=window['layer']
    byte_cap,request_cap=CAPS[layer];calls=0
    def bounded_open(req,**kwargs):
        nonlocal calls
        require(urlsplit(req.full_url).hostname=='kyfromabove.s3.us-west-2.amazonaws.com' and
                req.get_method() in ('GET','HEAD'),'Unexpected source request')
        require(calls<request_cap,'Original source request ceiling reached')
        calls+=1;return urlopen(req,**kwargs)
    cache=Cache(data['cache'],limit=byte_cap,opener=bounded_open)
    try:
        native=[]
        with cache.serve(sources) as urls:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',GDAL_HTTP_MAX_RETRY='0',
                    GDAL_HTTP_TIMEOUT='25',GDAL_CACHEMAX=64000000):
                for entry,url in zip(sources,urls,strict=True):
                    with rasterio.open(url) as ds:
                        require(ds.crs is not None,'Native source CRS missing')
                        crs=CRS(ds.crs);require(crs.is_projected,'Projected native original required')
                        unit=ds.units[0] if ds.units else None
                        if layer=='terrain':
                            require(unit in ('US survey foot','metre'),'Exact DEM vertical unit unresolved')
                            entry['verticalUnit']=unit
                        scale=crs.axis_info[0].unit_conversion_factor
                        native.append(dict(sourceID=entry['id'],sourceIdentity=cache.source(entry['url']),
                            crs=ds.crs.to_string(),nativePixelSizeMeters=[abs(ds.transform.a)*scale,abs(ds.transform.e)*scale],
                            nativeSize=[ds.width,ds.height],bands=ds.count,verticalUnit=unit))
        size=1024 if layer=='leaf-off' else 512
        bounds=list(mercator_bounds(window['x'],window['y'],16))
        if layer=='terrain':
            halo=(bounds[2]-bounds[0])/size
            bounds=[bounds[0]-halo,bounds[1]-halo,bounds[2]+halo,bounds[3]+halo];size+=2
        raster,transform,evidence=mosaic(cache,sources,bounds,size,size,dem=layer=='terrain')
        require(np.isfinite(raster).all(),'Nonfinite complete source window')
        # mosaic rejects every missing mask pixel. No output is cached as an accepted tile.
        result=dict(format='rrgh-expanded-full-window-validation-v1',layer=layer,z=16,x=window['x'],y=window['y'],
            sourceIDs=[s['id'] for s in sources],dimensions=[size,size],fullWindowMaskPassed=True,
            terrainHaloIncluded=layer=='terrain',verticalConversion='metres from exact per-source units' if layer=='terrain' else None,
            nativeSources=native,workingRasterSHA256=hashlib.sha256(raster.tobytes()).hexdigest(),
            validPixelCounts=[e['validPixelsInWindow'] for e in evidence],sourceRequests=calls,cache=cache.metrics(),
            productionPromotionApproved=False,rightsReviewComplete=False,fullRegionalCoverageProved=False,
            acceptedSourceOrCacheModified=False)
        print(json.dumps(result,sort_keys=True))
    finally:cache.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--catalog',type=Path)
    p.add_argument('--spec',type=Path);p.add_argument('--output',type=Path);p.add_argument('--child',type=Path)
    args=p.parse_args()
    if args.child:child(args.child);return
    source=args.source.resolve()
    code=(source/'backend/scripts/gorge_campaign.py').read_text()
    import re
    name=re.search(r"CONFIG=SOURCE.parent/'config/([^']+)'",code).group(1)
    region=json.loads(zlib.decompress(base64.b64decode((source/'backend/config'/name/'REGION-PLAN.json.z.b64').read_bytes())))
    candidates=select(json.loads(args.spec.read_bytes()),load_catalog(args.catalog),region)
    results=[]
    with tempfile.TemporaryDirectory(prefix='rrgh-public-window-') as temp:
        root=Path(temp)
        for i,candidate in enumerate(candidates):
            ticket=root/f'{i}.json';ticket.write_bytes(canonical(dict(source=str(source),candidate=candidate,cache=str(root/f'cache-{i}'))))
            run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',str(ticket)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=600,
                env={**os.environ,'GDAL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
            if run.returncode:
                print('FULL_WINDOW_VALIDATION_FAILED '+candidate['window']['layer'],file=sys.stderr)
                print(run.stderr[-4000:],file=sys.stderr);raise SystemExit(2)
            result=json.loads(run.stdout);results.append(result)
            print('BOUNDED_FULL_WINDOW_PASS '+json.dumps(result,sort_keys=True),flush=True)
    report=dict(format='rrgh-three-expanded-window-evidence-v1',windows=results,windowsVerified=len(results),
                liveProduction=False,fullRegionalCoverageProved=False,productionPromotionApproved=False)
    with args.output.open('xb') as out:out.write(canonical(report))


if __name__=='__main__':main()
