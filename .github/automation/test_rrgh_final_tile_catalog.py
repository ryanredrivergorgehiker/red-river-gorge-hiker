"""Verified package catalogs must retain valid edge alpha and reject interior holes."""
import base64,io,json,os,re,tarfile,tempfile,unittest,zlib
from pathlib import Path
from PIL import Image
import rrgh_verified_tile_catalog as c
from rrgh_overview_coverage import alpha

class FinalCatalogTests(unittest.TestCase):
    def build(self,hole=False):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        source=Path(os.environ['RRGH_TEST_SOURCE']).resolve()
        folder=re.search(r"CONFIG=SOURCE.parent/'config/([^']+)'",(source/'backend/scripts/gorge_campaign.py').read_text()).group(1)
        config=source/'backend/config'/folder
        plan=json.loads((config/'PLAN.json').read_bytes())
        region=json.loads(zlib.decompress(base64.b64decode((config/'REGION-PLAN.json.z.b64').read_bytes())))
        job=next(j for j in region['jobs'] if 0 in alpha(j['z'],j['x'],j['y']))
        layer,z,x,y=(job[k] for k in ('layer','z','x','y'));path=f'tiles/{layer}/{z}/{x}/{y}.png'
        image=Image.new('RGBA',(256,256));image.putdata([(a,b,(a+b)//2,255) for b in range(256) for a in range(256)])
        mask=bytearray(alpha(z,x,y))
        if hole:mask[mask.index(255)]=0
        image.putalpha(Image.frombytes('L',(256,256),bytes(mask)))
        data=io.BytesIO();image.save(data,format='PNG');raw=data.getvalue()
        target=root/'outputs'/path;target.parent.mkdir(parents=True);target.write_bytes(raw)
        sha=c.digest(c.canonical(plan));prefix=c.PREFIX+'plans/'+sha+'/'
        def ref(key,raw):return dict(key=prefix+key,generation='123456',bytes=len(raw),sha256=c.digest(raw))
        output=dict(path=path,bytes=len(raw),sha256=c.digest(raw));group=c.LAYERS[layer]
        record=dict(format='rrgh-checkpoint-job-v1',job=job['id'],planSHA256=sha,slot=1,result=dict(
            originalReceipt=dict(job=job['id'],validated=True,recipeSHA256=c.digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode()),outputs=[output]),
            outputPacks=[dict(ref=ref('slots/00001/outputs/fixture',raw),members=[dict(output,offset=0)])]))
        job_ref=ref('slots/00001/jobs/'+job['id']+'.json',c.canonical(record))
        manifest=c.canonical(dict(format='rrgh-map-part-v1',group=group,files=[dict(output,layer=layer,z=z,x=x,y=y)]))
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
            for name,payload in [('PART-MANIFEST.json',manifest),(path,raw)]:
                member=tarfile.TarInfo(name);member.size=len(payload);member.mtime=0;archive.addfile(member,io.BytesIO(payload))
        packed=stream.getvalue();name=c.digest(packed)+'.rrghpkg';folder=root/'parts'/group;folder.mkdir(parents=True);(folder/name).write_bytes(packed)
        part=dict(group=group,file=name,byteCount=len(packed),sha256=c.digest(packed),fileCount=2,
            manifestSHA256=c.digest(manifest),chunks=[dict(offset=0,ref=ref('slots/00002/outputs/fixture-part',packed))])
        qa=dict(allExpectedTilesPresent=True,pixelsDecoded=True,gridAndAlphaVerified=True,jobs=1,files=1,bytes=len(raw))
        return plan,region,[record],[job_ref],qa,[part],root
    def test_edge_tile_keeps_exact_coverage_and_native_package_membership(self):
        result=c.catalog(*self.build());tile=result['tiles'][0]
        self.assertGreater(tile['coverage']['transparentPixels'],0)
        self.assertTrue(result['nativePackageMembershipVerified']);self.assertIsNotNone(tile['package'])
        self.assertFalse(result['deliveryVerified'])
    def test_rehashed_packaged_interior_hole_cannot_become_verified_evidence(self):
        with self.assertRaisesRegex(ValueError,'missing regional pixels'):c.catalog(*self.build(hole=True))

if __name__=='__main__':unittest.main()
