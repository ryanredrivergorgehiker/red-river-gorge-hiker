import hashlib,struct,tempfile,unittest
from decimal import Decimal
from pathlib import Path
from assess_gorge_regional_scaling import cost,maximum_reads,all_caps_fit,locality
from cached_tiff_analysis import CachedMetadata,MissingMetadata,tiff_pages,blocks_for_window

class ScalingTests(unittest.TestCase):
    def test_cost_reconciliation_exposes_missing_cache_recovery(self):
        self.assertEqual(cost(24*2**30,21*2**30,90000,150000),Decimal('7.92'))
        self.assertEqual(cost(24*2**30,25*2**30,90000,150000),Decimal('9.024'))
    def test_budget_inverse_never_admits_one_byte_over(self):
        n=maximum_reads('8',24*2**30,90000,150000)
        self.assertLessEqual(cost(24*2**30,n,90000,150000),8)
        self.assertGreater(cost(24*2**30,n+1,90000,150000),8)
    def test_historical_release_is_not_refunded_in_target(self):
        self.assertEqual(Decimal('.70')+cost(22*2**30,int(19.5*2**30),75000,120000),Decimal('7.918'))
    def test_all_dimensions_must_fit(self):
        self.assertFalse(all_caps_fit({'bytes':9,'ops':11},{'bytes':10,'ops':10}))
        self.assertFalse(all_caps_fit({'bytes':-1,'ops':0},{'bytes':10,'ops':10}))
        self.assertTrue(all_caps_fit({'bytes':10,'ops':10},{'bytes':10,'ops':10}))
    def test_source_incidence_is_deduplicated_per_batch(self):
        jobs=[{'sourceIDs':['a','b']},{'sourceIDs':['a','b']},{'sourceIDs':['b','c']}]
        self.assertEqual(locality(jobs,2)['sourceBatchIncidences'],4)
        self.assertEqual(locality(jobs,3)['sourceBatchIncidences'],3)
    def test_missing_cache_never_falls_back_to_network(self):
        with tempfile.TemporaryDirectory()as t:
            r=CachedMetadata(t,{'length':100,'identity':'id'}, {})
            with self.assertRaises(MissingMetadata):r.read(0,16)
    def test_cache_corruption_rejected(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t)/'blocks/id';p.mkdir(parents=True);(p/'0').write_bytes(b'x'*16)
            r=CachedMetadata(t,{'length':16,'identity':'id'},{0:('0'*64,16)})
            with self.assertRaisesRegex(ValueError,'hash'):r.read(0,16)
    def test_metadata_range_cannot_escape_source(self):
        r=CachedMetadata('/unused',{'length':100,'identity':'id'}, {})
        with self.assertRaises(ValueError):r.read(90,20)
        with self.assertRaises(ValueError):r.read(-1,1)
    def test_tiff_invalid_ifd_rejected_before_array_read(self):
        raw=b'II'+struct.pack('<HI',42,16)+b'\0'*8+struct.pack('<H',257)
        class R:
            def read(self,s,n):return raw[s:s+n]
        with self.assertRaisesRegex(ValueError,'IFD entries'):tiff_pages(R())
    def test_block_union_accounts_partial_last_block(self):
        p={256:[2],257:[2],322:[2],323:[2],324:[65530],325:[10],33550:[1,1,0],33922:[0,0,0,0,2,0],34735:[1,1,0,1,3072,0,1,26916]}
        identity=lambda a,b,*bounds,**kw:bounds
        self.assertEqual(blocks_for_window([p],65540,(0,0,2,2),identity),{0,1})
        with self.assertRaisesRegex(ValueError,'extent'):blocks_for_window([p],65539,(0,0,2,2),identity)

if __name__=='__main__':unittest.main()
