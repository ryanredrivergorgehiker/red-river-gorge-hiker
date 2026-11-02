"""Actual unchanged native overview renderer with synthetic fixture children."""
import base64,copy,io,json,os
from pathlib import Path
import tempfile,unittest,zlib
from PIL import Image,ImageChops,ImageStat
from rrgh_verified_tile_catalog import digest,canonical
from rrgh_verified_overview import render

class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.children=[]
        self.source=Path(os.environ['RRGH_TEST_SOURCE']).resolve()
        raw=(self.source/'backend/config/gorge-campaign-wave-058-20261102/REGION-PLAN.json.z.b64').read_bytes()
        self.region=json.loads(zlib.decompress(base64.b64decode(raw)))
        self.job=dict(id='terrain-15-8772-12661',layer='terrain',z=15,x=8772,y=12661,
            operation='overview',sourceIDs=[],outputTiles=[[15,8772,12661]])
        self.region['jobs']=[self.job];self.mosaic=Image.new('RGB',(512,512))
        for dx in range(2):
            for dy in range(2):
                x,y=17544+dx,25322+dy;path=f'tiles/terrain/16/{x}/{y}.png'
                image=Image.new('RGB',(256,256));image.putdata([((a+dx*25)%256,(b+dy*25)%256,(a+b)//2) for b in range(256) for a in range(256)])
                self.mosaic.paste(image,(dx*256,dy*256));out=io.BytesIO();image.save(out,format='PNG');raw=out.getvalue()
                target=self.root/'children'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                ref=dict(key='engineering/map-production/fixture/'+f'{x}-{y}',generation='1234',bytes=len(raw),sha256=digest(raw))
                self.children.append(dict(tile=['terrain',16,x,y],path=path,bytes=len(raw),sha256=digest(raw),
                    checkpointObject=ref,checkpointOffset=0,jobReceipt=ref,pixelReadbackVerified=True))
    def tearDown(self):self.tmp.cleanup()
    def run_render(self):return render(self.region,self.job,self.children,self.root/'children',self.root/'new',self.source)
    def test_native_overview_preserves_children_and_uses_no_source(self):
        before={c['path']:digest((self.root/'children'/c['path']).read_bytes()) for c in self.children}
        result=self.run_render();self.assertEqual(result['sourceRequests'],0);self.assertFalse(result['productionAccepted'])
        self.assertEqual(len(result['dependencies']),4)
        with Image.open(self.root/'new'/result['receipt']['outputs'][0]['path']) as actual:
            expected=self.mosaic.resize((256,256),Image.Resampling.LANCZOS)
            self.assertLess(sum(ImageStat.Stat(ImageChops.difference(expected,actual.convert('RGB'))).mean)/3,4)
        self.assertEqual(before,{c['path']:digest((self.root/'children'/c['path']).read_bytes()) for c in self.children})
    def test_missing_child_rejected(self):
        self.children.pop()
        with self.assertRaisesRegex(ValueError,'Four exact'):self.run_render()
    def test_tampered_child_rejected(self):
        (self.root/'children'/self.children[0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Child bytes'):self.run_render()
    def test_unknown_renderer_rejected(self):
        self.region['engineHashes']['orchestrate_gorge_region.py']='f'*64
        with self.assertRaisesRegex(ValueError,'renderer pin'):self.run_render()
    def test_existing_output_refused(self):
        (self.root/'new').mkdir()
        with self.assertRaisesRegex(ValueError,'Fresh private'):self.run_render()

if __name__=='__main__':unittest.main()
