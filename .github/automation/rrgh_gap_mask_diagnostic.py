"""Three bounded read-only original-source mask probes; no production retry.

Outputs only coverage measurements and exact source identities. No Cloud
credential, upload, map tile, allocation reset or accepted-state mutation.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zlib

CASES=('hiking-16-17534-25326','terrain-16-17537-25329','leaf-off-16-17537-25329')
SOURCE_SHA='2c121dfba317d918749acaadd6842be81c88fee1'
PLAN_SHA='e2631ee1ca7b5a8b0dd787afcabcf8abfbf9d76e3420f2dbdd28a2f33eaa4902'


def run(source):
    source=Path(source).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_bounds
    from cached_cog_source import Cache
    from gorge_checkpoint import Meter,DIMENSIONS,canonical,digest
    from gorge_guarded_worker import SourceOpener
    from orchestrate_gorge_region import LAYERS
    from pilot_official_cog_xyz import mercator_bounds
    from rrgh_expanded_production import build_index
    folder=source/'backend/config/gorge-campaign-wave-1322-20261102'
    plan=json.loads((folder/'PLAN.json').read_bytes())
    if digest(canonical(plan))!=PLAN_SHA:raise ValueError('Diagnostic baseline changed')
    region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    if digest(canonical(region))!=plan['regionPlanSHA256']:raise ValueError('Diagnostic source inventory changed')
    jobs,_=build_index(region);results=[]
    for jid in CASES:
        if jid not in plan['campaign']['sourcePixelGapQuarantines'] or jid in plan['completedJobIDs'] or plan['priorAttemptCounts'].get(jid)!=1:
            raise ValueError('Diagnostic must retain the original consumed, unaccepted position')
        job=jobs[jid];layer=job['layer'];dem=layer=='terrain';family='dem' if dem else layer
        candidates=[s for s in region['inventory']['sources'][family] if s['id'] in job['sourceIDs']]
        if not 1<=len(candidates)<=4:raise ValueError('Bounded exact source candidate set required')
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(sourceBytes=64*2**20,sourceRequests=128,seconds=600)
        meter=Meter(caps);opener=SourceOpener(meter)
        print(json.dumps(dict(phase='diagnostic-reservation',job=jid,maximumSourceBytes=64*2**20,
            maximumSourceRequests=128,maximumSeconds=600,sourceSHA=SOURCE_SHA,
            cloudRequests=0,productionAttemptReplayed=False,acceptanceChanged=False)),flush=True)
        bounds=list(mercator_bounds(job['x'],job['y'],16));size=256*2**(LAYERS[layer]-16)
        if dem:
            halo=(bounds[2]-bounds[0])/size
            bounds=[bounds[0]-halo,bounds[1]-halo,bounds[2]+halo,bounds[3]+halo];size+=2
        transform=from_bounds(*bounds,size,size);filled=np.zeros((size,size),dtype=bool)
        aoi=transform_bounds('EPSG:4326','EPSG:3857',*region['boundsWGS84'])
        xs=transform.c+(np.arange(size)+.5)*transform.a
        ys=transform.f+(np.arange(size)+.5)*transform.e
        inside=(xs[None,:]>=aoi[0])&(xs[None,:]<=aoi[2])&(ys[:,None]>=aoi[1])&(ys[:,None]<=aoi[3])
        observations=[];started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='rrgh-mask-diagnostic-') as temp:
            cache=Cache(Path(temp)/'cache',limit=64*2**20,opener=opener)
            try:
                with cache.serve(candidates) as urls,rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
                    GDAL_HTTP_MAX_RETRY='0',GDAL_HTTP_TIMEOUT='30',GDAL_CACHEMAX=64_000_000,
                    CPL_VSIL_CURL_CHUNK_SIZE='65536',CPL_VSIL_CURL_CACHE_SIZE='4194304'):
                    for candidate,url in zip(candidates,urls,strict=True):
                        with rasterio.open(url) as ds:
                            if not ds.crs or ds.count<(1 if dem else 3):raise ValueError('Source georeference/bands missing')
                            with WarpedVRT(ds,crs='EPSG:3857',transform=transform,width=size,height=size,
                                resampling=Resampling.bilinear,add_alpha=True,warp_mem_limit=64) as vrt:
                                values=vrt.read([1] if dem else [1,2,3]);alpha=vrt.read(vrt.count)
                                valid=(alpha>0)&np.isfinite(values).all(axis=0)
                                new=valid&~filled;filled|=valid
                            observations.append(dict(id=candidate['id'],sourceIdentity=cache.source(candidate['url']),
                                catalogBoundsWGS84=candidate['bbox'],actualBoundsWGS84=list(transform_bounds(ds.crs,'EPSG:4326',*ds.bounds,densify_pts=21)),
                                sourceCRS=ds.crs.to_string(),sourceCount=ds.count,nodata=repr(ds.nodata),
                                sourceMaskFlags=[str(v) for v in ds.mask_flag_enums],
                                validPixels=int(valid.sum()),newlyCoveredPixels=int(new.sum())))
                row=dict(phase='source-mask-diagnostic',job=jid,width=size,height=size,totalPixels=int(filled.size),
                    validPixels=int(filled.sum()),missingPixels=int((~filled).sum()),
                    requiredInsideAOIPixels=int(inside.sum()),missingInsideAOIPixels=int((~filled&inside).sum()),
                    missingOutsideAOIPixels=int((~filled&~inside).sum()),allPixelsPresent=bool(filled.all()),
                    sources=observations,actual=opener.summary(),reserved=meter.used,seconds=round(time.monotonic()-started,3),
                    cloudRequests=0,mapTilesWritten=0,productionAttemptReplayed=False,acceptedTilesAdded=0)
                results.append(row);print(json.dumps(row,sort_keys=True,allow_nan=False),flush=True)
            except Exception as exc:
                # Do not turn a bounded diagnostic failure into an invented source diagnosis.
                row=dict(phase='source-mask-diagnostic-failed',job=jid,errorClass=type(exc).__name__,
                    reason=str(exc)[:500],actual=opener.summary(),reserved=meter.used,
                    cloudRequests=0,acceptedTilesAdded=0,remainingReservationRetained=True)
                results.append(row);print(json.dumps(row,sort_keys=True),flush=True)
            finally:cache.close()
    print(json.dumps(dict(phase='diagnostic-complete',cases=len(results),
        completed=sum(r['phase']=='source-mask-diagnostic' for r in results),acceptedTilesAdded=0,
        officialRequests=sum(r['actual']['operations'] for r in results),
        receivedSourceBytes=sum(r['actual']['receivedBodyBytes'] for r in results),
        noProductionMutation=True)),flush=True)


if __name__=='__main__':run(sys.argv[1])
