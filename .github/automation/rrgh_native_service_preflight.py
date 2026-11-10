"""Read native government responses and masks without creating map outputs."""
import base64,hashlib,io,json,sys,tempfile,time,zlib
from pathlib import Path

SOURCE='895c01953481b2b5825abee9a4c0681f37211eb4'
PLAN='a9924758e5178a70dc62d9abcc3d00e0f7921906e963bf3f62a1bb1e9bdc899b'
CASE_SHA='7593b906e4bee2a2d4224ef154e4c05a761e861a0ab0060476236f0d4526679d'

def run(root):
    root=Path(root).resolve();sys.path.insert(0,str(root/'backend/scripts'))
    import numpy as np
    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT
    import benchmark_ky_naip_usgs as services
    from gorge_checkpoint import Meter,DIMENSIONS,canonical,digest
    from gorge_guarded_worker import SourceOpener
    from pilot_official_cog_xyz import mercator_bounds
    raw=(Path(__file__).with_name('fixtures')/'native-service-candidates-20261110.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==CASE_SHA
    cases=json.loads(raw);assert len(cases)==29 and len(set(cases))==29
    folder=root/'backend/config/gorge-campaign-wave-1418-20261102'
    plan=json.loads((folder/'PLAN.json').read_bytes());assert digest(canonical(plan))==PLAN
    region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
    assert digest(canonical(region))==plan['regionPlanSHA256']
    totals=dict.fromkeys(DIMENSIONS,0);totals.update(sourceBytes=280_000_000,sourceRequests=60,seconds=1500)
    total=Meter(totals);total_opener=SourceOpener(total);results=[]
    for jid in cases:
        assert jid not in plan['completedJobIDs'] and plan['priorAttemptCounts'].get(jid)==1
        layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y));assert z==16 and layer in ('leaf-on','usgs-topo')
        if time.monotonic()+300>total.deadline:raise ValueError('Finite service diagnostic time bound')
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(seconds=300,
            sourceBytes=9_000_002 if layer=='leaf-on' else 500_001,sourceRequests=2 if layer=='leaf-on' else 1)
        meter=Meter(caps);opener=SourceOpener(meter,opener=total_opener);services.urlopen=opener
        start=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='rrgh-service-mask-') as temp:
            cache=services.ServiceCache(temp,byte_limit=9_000_000,request_limit=2)
            try:
                if layer=='leaf-on':
                    metadata,metadata_ref=cache.fetch(services.NAIP,{'f':'pjson'})
                    bounds=mercator_bounds(x,y,16);params=services.naip_parameters(bounds,json.loads(metadata))
                    body,evidence=cache.fetch(services.NAIP+'/exportImage',params,8_000_000)
                    with MemoryFile(body) as mem,mem.open() as ds:
                        assert ds.crs.to_epsg()==3089 and ds.count==4 and ds.transform.a==2 and ds.transform.e==-2
                        native_complete=bool(np.all(ds.dataset_mask()==255))
                        with WarpedVRT(ds,crs='EPSG:3857',transform=from_bounds(*bounds,1024,1024),
                            width=1024,height=1024,resampling=Resampling.bilinear) as vrt:
                            rgb=vrt.read([1,2,3]);mask=vrt.dataset_mask();valid=(mask==255)&np.isfinite(rgb).all(axis=0)
                        contrast=max(float(b.std()) for b in rgb)
                    side=1024
                else:
                    body,evidence=cache.fetch(f'{services.USGS}/tile/{z}/{y}/{x}',maximum=500_000)
                    with Image.open(io.BytesIO(body)) as image:
                        image.load();assert image.size==(256,256) and image.format in ('PNG','JPEG')
                        rgb=np.asarray(image.convert('RGB'));valid=np.ones((256,256),dtype=bool)
                        if image.mode=='RGBA':valid=np.asarray(image.getchannel('A'))==255
                        contrast=max(float(rgb[:,:,b].std()) for b in range(3))
                    native_complete=True;side=256;metadata_ref=None
                complete=native_complete and bool(valid.all()) and contrast>=1
                row=dict(phase='service-mask-diagnostic',job=jid,allPixelsPresent=complete,
                    width=side,height=side,totalPixels=side*side,validPixels=int(valid.sum()),missingPixels=int((~valid).sum()),
                    nativeSourceMaskComplete=native_complete,contrast=contrast,sourceEvidence=evidence,metadataEvidence=metadata_ref,
                    actual=opener.summary(),reserved=meter.used,seconds=round(time.monotonic()-start,3),
                    cloudRequests=0,mapTilesWritten=0,productionAttemptReplayed=False,acceptedTilesAdded=0)
            except Exception as error:
                row=dict(phase='service-mask-diagnostic-failed',job=jid,errorClass=type(error).__name__,reason=str(error)[:400],
                    actual=opener.summary(),reserved=meter.used,cloudRequests=0,acceptedTilesAdded=0)
            finally:cache.close()
        results.append(row);print(json.dumps(row,sort_keys=True),flush=True)
    print(json.dumps(dict(phase='diagnostic-complete',cases=len(results),complete=sum(r.get('allPixelsPresent') is True for r in results),
        sourceSHA=SOURCE,planSHA256=PLAN,readRequests=total.used['sourceRequests'],readBytes=total.used['sourceBytes'],
        productionAttemptsReplayed=0,acceptedTilesAdded=0)),flush=True)

if __name__=='__main__':run(sys.argv[1])
