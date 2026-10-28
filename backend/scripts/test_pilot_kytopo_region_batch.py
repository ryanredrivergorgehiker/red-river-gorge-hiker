"""Offline no-network regression suite for bounded regional original COG QA batches."""
import hashlib, json, sys, tempfile, unittest, zipfile
from pathlib import Path
from types import ModuleType

# Original production module uses GDAL/HTTP206; tests inject fake renderer and
# stub only its external side-effectful GDAL helpers.
stub=ModuleType('pilot_kytopo_12_source_seams')
for name in ('HOST','RangeBudget','proxy_handler','mercator_bounds','verify_derived_grid',
             'environ','command','image_info','alpha_minmax'):
    setattr(stub,name, '127.0.0.1' if name=='HOST' else (lambda *a,**k: None))
sys.modules.setdefault('pilot_kytopo_12_source_seams',stub)
from PIL import Image
from io import BytesIO
from pilot_kytopo_region_batch import run_batch,validate_inputs

ROOT=Path(__file__).parent
PLAN=json.loads((ROOT/'official-ky-topo-full-region-footprint-plan.json').read_text())
INDEX=json.loads((ROOT/'official-ky-topo-gorge-quad-selection.json').read_text())

class BatchTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.out=Path(t.name)/'new-batch'
        b=BytesIO(); Image.new('RGB',(256,256),(30,80,20)).save(b,format='JPEG')
        self.sample=b.getvalue()
    def fake(self,index,tile,out,max_bytes):
        z,x,y=(tile[k] for k in ('z','x','y'))
        file=out/'tiles'/'kentucky-topo'/str(z)/str(x)/(str(y)+'.jpg')
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(self.sample)
        return {'xyz':{k:tile[k] for k in ('z','x','y')},'sourceIds':tile['sourceIds'],
                'sourceRerendered':True,'mosaicAlphaMin':255,'mosaicAlphaMax':255,
                'geoQA':{'pixelAndGeographicAlignmentVerified':True},
                'sourceBytesTransferred':2000,'jpegPath':file.relative_to(out).as_posix(),
                'jpegBytes':len(self.sample),'jpegSha256':hashlib.sha256(self.sample).hexdigest()}
    def test_exact_official_plan(self):
        t,_=validate_inputs(PLAN,INDEX)
        self.assertEqual(len(t),6950)
    def test_default_no_network(self):
        r=run_batch(PLAN,INDEX,0,3,self.out)
        self.assertFalse(r['allSelectedTilesPassed'])
        self.assertFalse(r['regionalPixelCoverageComplete'])
        self.assertEqual(r['sourceTransferredBytes'],0)
        self.assertEqual(len(r['passed']),0)
        self.assertEqual(len(r['batch']),3)
    def test_live_synthetic_scoped_receipt(self):
        r=run_batch(PLAN,INDEX,0,2,self.out,live=True,renderer=self.fake)
        self.assertTrue(r['allSelectedTilesPassed'])
        self.assertFalse(r['regionalPixelCoverageComplete'])
        self.assertEqual(r['sourceTransferredBytes'],4000)
        self.assertEqual(len(r['passed']),2)
    def test_fails_closed_does_not_erase_valid_receipts(self):
        counter=[0]
        def fake(*args,**kwargs):
            counter[0]+=1
            if counter[0]==2:raise ValueError('true source pixel gap')
            return self.fake(*args,**kwargs)
        r=run_batch(PLAN,INDEX,0,3,self.out,live=True,renderer=fake)
        self.assertEqual(len(r['passed']),2)
        self.assertEqual(len(r['failures']),1)
        self.assertFalse(r['allSelectedTilesPassed'])
        self.assertIn('INCOMPLETE',r['status'])
        self.assertTrue((self.out/'BATCH-SOURCE-QA.json').is_file())
    def test_no_resume_overwrite(self):
        run_batch(PLAN,INDEX,0,1,self.out)
        with self.assertRaises(FileExistsError):
            run_batch(PLAN,INDEX,0,1,self.out)
    def test_reject_unofficial_source_replacement(self):
        index=json.loads(json.dumps(INDEX))
        index['quadrangles'][0]['officialOriginalSourceBytes']=7777777
        with self.assertRaises(ValueError):
            run_batch(PLAN,index,0,1,self.out)
    def test_reject_incomplete_region(self):
        plan=json.loads(json.dumps(PLAN))
        plan['plannedTiles'][0]['sourceBboxUnionCoversClippedTile']=False
        with self.assertRaises(ValueError):
            run_batch(plan,INDEX,0,1,self.out)
    def test_bounded_batch_size_and_range(self):
        for count in (0,13,-1):
            with self.assertRaises(ValueError):run_batch(PLAN,INDEX,0,count,self.out)
        with self.assertRaises(ValueError):run_batch(PLAN,INDEX,6949,2,self.out)
        with self.assertRaises(ValueError):run_batch(PLAN,INDEX,0,1,self.out,total_limit=60_000_001)
    def test_failed_attempts_still_consume_reserved_network_budget(self):
        attempts=[]
        def fail(idx,tile,out,max_bytes):
            attempts.append(max_bytes)
            raise ValueError('truncated HTTP206 original COG data')
        r=run_batch(PLAN,INDEX,0,4,self.out,live=True,renderer=fail,total_limit=5_500_000)
        self.assertEqual(attempts,[5_000_000,500_000])
        self.assertEqual(r['sourceTransferBudgetAllocatedBytes'],5_500_000)
        self.assertFalse(r['allSelectedTilesPassed'])
        self.assertEqual(len(r['failures']),4)
        self.assertEqual(r['sourceTransferredBytes'],0)

    def test_file_integrity_is_required_even_if_fake_claims_pass(self):
        def bad(idx,tile,out,max_bytes):
            r=self.fake(idx,tile,out,max_bytes)
            r['jpegSha256']='0'*64
            return r
        r=run_batch(PLAN,INDEX,0,1,self.out,live=True,renderer=bad)
        self.assertFalse(r['allSelectedTilesPassed'])
        self.assertIn('not verified',r['failures'][0]['error'])
    def test_false_source_render_claim_fails(self):
        def bad(idx,tile,out,max_bytes):
            r=self.fake(idx,tile,out,max_bytes)
            r['sourceRerendered']=False
            return r
        r=run_batch(PLAN,INDEX,0,1,self.out,live=True,renderer=bad)
        self.assertFalse(r['allSelectedTilesPassed'])

if __name__=='__main__':unittest.main()
