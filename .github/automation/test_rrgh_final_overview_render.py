"""Actual pinned overview renderer, synthetic children, no network or acceptance."""
import copy,io,json,os,re,tempfile,unittest,zlib,base64
from pathlib import Path
from PIL import Image
from rrgh_final_overview_render import render
from rrgh_overview_coverage import alpha,child_positions,verify
from rrgh_verified_tile_catalog import digest
from rrgh_seed_children import AUTHORITY,AUTHORITY_SHA

class FinalRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=Path(os.environ['RRGH_TEST_SOURCE']).resolve()
        code=(self.source/'backend/scripts/gorge_campaign.py').read_text()
        folder=re.search(r"CONFIG=SOURCE.parent/'config/([^']+)'",code).group(1)
        self.region=json.loads(zlib.decompress(base64.b64decode((self.source/'backend/config'/folder/'REGION-PLAN.json.z.b64').read_bytes())))
    def tearDown(self):self.temp.cleanup()
    def case(self,z,x,y,layer='hiking',seed=False):
        job=dict(id=f'{layer}-{z}-{x}-{y}',layer=layer,z=z,x=x,y=y,
            operation='overview',sourceIDs=[],outputTiles=[[z,x,y]])
        region=copy.deepcopy(self.region);region['jobs']=[job];children=[]
        for zz,xx,yy in child_positions(z,x,y):
            jid=f'{layer}-{zz}-{xx}-{yy}';path=f'tiles/{layer}/{zz}/{xx}/{yy}.png'
            image=Image.new('RGBA',(256,256));image.putdata([(a,b,(a+b)//2,255) for b in range(256) for a in range(256)])
            image.putalpha(Image.frombytes('L',(256,256),alpha(zz,xx,yy)))
            out=io.BytesIO();image.save(out,format='PNG');raw=out.getvalue()
            target=self.root/'children'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            ref=dict(key='engineering/map-production/fixture/'+jid,generation='1234',bytes=len(raw),sha256=digest(raw))
            child=dict(tile=[layer,zz,xx,yy],job=jid,path=path,bytes=len(raw),sha256=digest(raw),
                checkpointObject=ref,checkpointOffset=0,pixelReadbackVerified=True,coverage=verify(image,zz,xx,yy))
            if seed:
                self.assertIn(jid,AUTHORITY['jobs'])
                child['seedAcceptanceProof']=dict(format='rrgh-accepted-seed-child-v1',authoritySHA256=AUTHORITY_SHA,
                    kind='original-accepted-seed',acceptanceReceipt=AUTHORITY['history']['acceptedBootstrap'],
                    originalProof=AUTHORITY['history']['proof'])
            else:child['jobReceipt']=ref
            children.append(child)
        return region,job,children
    def run_case(self,case):
        region,job,children=case
        return render(region,job,children,self.root/'children',self.root/'output',self.source)
    def test_northern_edge_uses_two_required_children_and_exact_alpha(self):
        case=self.case(14,4378,6322);self.assertEqual(len(case[2]),2)
        before={c['path']:digest((self.root/'children'/c['path']).read_bytes()) for c in case[2]}
        result=self.run_case(case);self.assertEqual(result['sourceRequests'],0)
        with Image.open(self.root/'output'/result['receipt']['outputs'][0]['path']) as image:
            self.assertGreater(verify(image,14,4378,6322)['transparentPixels'],0)
        self.assertFalse(result['productionAccepted'])
        self.assertEqual(before,{c['path']:digest((self.root/'children'/c['path']).read_bytes()) for c in case[2]})
    def test_lowest_zoom_uses_partially_covered_verified_children(self):
        case=self.case(10,273,395);result=self.run_case(case)
        self.assertGreater(result['coverage']['transparentPixels'],0)
    def test_seed_proofs_are_explicit_and_never_fabricate_campaign_receipts(self):
        case=self.case(15,8772,12661,'leaf-on',seed=True)
        self.assertTrue(all('jobReceipt' not in c for c in case[2]))
        self.assertEqual(len(self.run_case(case)['dependencies']),4)
    def test_missing_required_child_and_extra_exterior_child_rejected(self):
        region,job,children=self.case(14,4378,6322)
        with self.assertRaises(ValueError):self.run_case((region,job,children[:-1]))
        outside=copy.deepcopy(children[0]);outside['tile'][3]-=1
        with self.assertRaises(ValueError):self.run_case((region,job,children+[outside]))
    def test_rehashed_interior_hole_is_still_rejected(self):
        region,job,children=self.case(14,4378,6322);child=children[0]
        target=self.root/'children'/child['path']
        with Image.open(target) as image:
            image.load();image.putpixel((100,100),(1,2,3,0));out=io.BytesIO();image.save(out,format='PNG')
        raw=out.getvalue();target.write_bytes(raw);child.update(bytes=len(raw),sha256=digest(raw))
        child['checkpointObject'].update(bytes=len(raw),sha256=digest(raw))
        with self.assertRaisesRegex(ValueError,'missing regional pixels'):self.run_case((region,job,children))

if __name__=='__main__':unittest.main()
