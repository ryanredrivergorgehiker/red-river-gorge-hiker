import copy
from dataclasses import asdict
import json
import random
import tempfile
import unittest
import zlib
from pathlib import Path
from gorge_checkpoint import (Slot,Ref,canonical,digest,encode_record,decode_record,bookkeeping_bounds,
    COMPACT_CLAIM,COMPACT_RECEIPT,MAX_RECEIPT,MAX_CATALOG,RECORD_MAGIC,validate_plan,recover_members)
from test_gorge_checkpoint import DiskStore,plan
from forecast_gorge_checkpoint_campaign import (build_graph,capacity,allocate_exact,selected_cache,
    PROFILES,BOUNDS,cost,GIB,validate_envelope)

class CompactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.p=plan();self.p['bookkeepingProfile']='compact-v2';self.store=DiskStore(self.root/'store')
    def tearDown(self):self.tmp.cleanup()
    def test_new_profile_exact_reserve_and_legacy_unchanged(self):
        self.assertEqual(bookkeeping_bounds(plan()),(MAX_RECEIPT,MAX_RECEIPT))
        slot=Slot(self.store,self.p,0,'owner')
        self.assertEqual(slot.meter.used['storedBytes'],COMPACT_CLAIM+COMPACT_RECEIPT)
        self.assertEqual(slot.meter.used['classARequests'],2)
    def test_small_compact_slot_and_unknown_profile_fail_before_write(self):
        for mode in ['size','profile']:
            p=copy.deepcopy(self.p)
            if mode=='size':p['slots'][0]['storedBytes']=COMPACT_CLAIM+COMPACT_RECEIPT-1
            else:p['bookkeepingProfile']='guess'
            with self.assertRaises(ValueError):Slot(self.store,p,0,'owner')
        self.assertEqual(self.store.creates,0)
    def test_whole_reservation_atomic_before_claim(self):
        seen=[];old=self.store.create
        def create(k,b):
            obj=json.loads(b);seen.append(obj['allocation']);return old(k,b)
        self.store.create=create
        slot=Slot(self.store,self.p,0,'owner')
        self.assertEqual(slot.meter.used['egressBytes'],2*16385)
        self.assertEqual(len(seen),1)
    def test_lossless_large_provenance_roundtrip(self):
        value={'sourceEvidence':[{'private':'exact provenance','sha256':str(i).zfill(64)} for i in range(1000)]}
        encoded=encode_record(value,COMPACT_RECEIPT,True)
        self.assertLess(len(encoded),COMPACT_RECEIPT);self.assertEqual(decode_record(encoded),value)
    def test_compression_bomb_trailing_truncated_and_unbounded_rejected(self):
        for raw in [RECORD_MAGIC+zlib.compress(b' '* (MAX_RECEIPT+1)),RECORD_MAGIC+zlib.compress(b'{}')+b'extra',RECORD_MAGIC+zlib.compress(b'{}')[:-1]]:
            with self.assertRaises(ValueError):decode_record(raw)
        with self.assertRaises(ValueError):encode_record({'a':'x'*(MAX_RECEIPT+1)},COMPACT_RECEIPT,True)
    def test_incompressible_receipt_stops_before_write(self):
        slot=Slot(self.store,self.p,0,'owner');before=self.store.creates
        noise=random.Random(4).randbytes(50000).hex()
        with self.assertRaises(ValueError):slot.finish({'noise':noise})
        self.assertEqual(self.store.creates,before)
    def test_compact_job_survives_missing_final_receipt_and_reads_losslessly(self):
        self.p['slotJobs']={'0':['hiking-16-1-1']}
        writer=Slot(self.store,self.p,0,'owner');value={'originalReceipt':{'preserve':'all fields'},'outputPacks':[]}
        ref=writer.commit_job('hiking-16-1-1',value)
        reader=Slot(DiskStore(self.store.root),self.p,1,'fresh')
        got,obj=reader.recover_job(0,'hiking-16-1-1')
        self.assertEqual(got,ref);self.assertEqual(obj['result'],value)
    def test_catalog_generation_hash_and_final_reference(self):
        writer=Slot(self.store,self.p,0,'owner');catalog={'members':[{'path':str(i),'sha256':digest(str(i).encode())} for i in range(1024)]}
        ref=writer.put_catalog(catalog);writer.finish({'cacheCatalogs':[asdict(ref)]})
        reader=Slot(DiskStore(self.store.root),self.p,1,'fresh');_,done=reader.recover_receipt(0)
        recovered=Ref(**done['result']['cacheCatalogs'][0]);self.assertEqual(reader.get_catalog(recovered),catalog)
        self.assertLess(ref.bytes,MAX_CATALOG)
        with self.assertRaises(ValueError):reader.get_catalog(Ref(ref.key,str(int(ref.generation)+1),ref.bytes,ref.sha256))
    def test_legacy_plain_json_receipt_still_recovers(self):
        p=plan();writer=Slot(self.store,p,0,'old');writer.finish({'legacy':'unchanged'})
        _,record=Slot(DiskStore(self.store.root),p,1,'fresh').recover_receipt(0)
        self.assertEqual(record['result'],{'legacy':'unchanged'})
    def test_inherited_attempts_count_and_cannot_reset(self):
        self.p['priorAttemptCounts']={'pending':1};self.p['slotJobs']={'0':['pending'],'1':['pending']}
        with self.assertRaises(ValueError):validate_plan(self.p)
        self.p['slotJobs']={'0':['pending']};validate_plan(self.p)
        self.p['priorAttemptCounts']['pending']=2
        with self.assertRaises(ValueError):validate_plan(self.p)

class RangeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.p=plan()
        self.store=DiskStore(self.root/'objects');self.writer=Slot(self.store,self.p,0,'writer')
        ref=self.writer.put(b'aaaaBBBBccccdddd')
        self.manifest=[{'ref':asdict(ref),'members':[{'path':str(i),'offset':i*4,'bytes':4,'sha256':digest(raw)} for i,raw in enumerate([b'aaaa',b'BBBB',b'cccc',b'dddd'])]}]
        self.reader=Slot(DiskStore(self.store.root),self.p,1,'reader')
    def tearDown(self):self.tmp.cleanup()
    def test_contiguous_members_one_read_with_every_hash_preserved(self):
        recover_members(self.reader,self.manifest,{'1','2','3'},self.root/'out')
        self.assertEqual(len(self.reader.store.reads),1);self.assertEqual(self.reader.store.reads[0][1:],(4,12))
        self.assertEqual((self.root/'out/2').read_bytes(),b'cccc')
    def test_unselected_gap_is_never_downloaded(self):
        recover_members(self.reader,self.manifest,{'0','2'},self.root/'out')
        self.assertEqual([r[1:] for r in self.reader.store.reads],[(0,4),(8,4)])
    def test_read_and_probe_limits_fail_before_io_or_partial_publication(self):
        self.reader.meter.caps['classBRequests']=1
        with self.assertRaises(ValueError):recover_members(self.reader,self.manifest,{'0','2'},self.root/'out')
        self.assertEqual(self.reader.store.reads,[]);self.assertFalse((self.root/'out.partial').exists())
        self.reader.meter.caps['classBRequests']=20
        self.reader.meter.caps['egressBytes']=self.reader.meter.used['egressBytes']+8
        with self.assertRaises(ValueError):recover_members(self.reader,self.manifest,{'0','2'},self.root/'out')
        self.assertEqual(self.reader.store.reads,[])
    def test_corrupt_selected_hash_and_overlap_do_not_publish(self):
        bad=copy.deepcopy(self.manifest);bad[0]['members'][1]['sha256']='0'*64
        with self.assertRaises(ValueError):recover_members(self.reader,bad,{'0','1'},self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
        bad=copy.deepcopy(self.manifest);bad[0]['members'][1]['offset']=2
        count=len(self.reader.store.reads)
        with self.assertRaises(ValueError):recover_members(self.reader,bad,{'0'},self.root/'overlap')
        self.assertEqual(len(self.reader.store.reads),count)
class ForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources={family:[{'id':family,'bbox':[-84,37,-83,39],'url':'fixture:'+family}] for family in ['hiking','dem','leaf-on','leaf-off']}
        cls.prior={'boundsWGS84':BOUNDS,'profiles':PROFILES,'inventory':{'sources':sources}}
        cls.g=build_graph(cls.prior,[])
    def test_entire_exact_grid_and_dependencies(self):
        s=self.g['statistics'];self.assertEqual(s['jobs'],34750);self.assertEqual(s['tileFiles'],278278);self.assertEqual(s['dependencyEdges'],27784)
        self.assertTrue(all(len(b)<=12 for b in self.g['batches']))
    def test_quality_change_and_unknown_prior_job_rejected(self):
        p=copy.deepcopy(self.prior);p['profiles']['core']['terrain']=16
        with self.assertRaises(ValueError):build_graph(p,[])
        with self.assertRaises(ValueError):build_graph(self.prior,[{'job':'missing'}])
    def test_exact_cumulative_slices_without_rounding_overdraw(self):
        for total in [0,1,1000,704*GIB]:self.assertEqual(sum(allocate_exact(total,[1,3,17,21])),total)
        for weights in [[0],[True],[]]:
            with self.assertRaises(ValueError):allocate_exact(100,weights)
    def test_unknown_cache_preserved_not_credited(self):
        recovery={'completeCacheFiles':[{'kind':'cog','path':'blocks/unknown/0','bytes':65536,'sha256':'0'*64,'includedInDelta':True}],'requiresOriginalCOGCacheLibraryFile':'fixture','archiveSHA256':'0'*64}
        c=selected_cache(self.g,self.prior,recovery,[],[])
        self.assertEqual(c['selectedBytes'],0);self.assertEqual(c['unmappedBlocksPreservedButNotSelected'],1);self.assertEqual(c['assumedFutureCacheSavingsBytes'],0)
    def test_capacity_does_not_claim_measured_completion_or_approval(self):
        old={'sourceAndCompute':{'totalSourceCacheBytes':564951223050,'totalHoursBeforeSetupAndRetries':473},'combined':{'archiveBytes':7685212160},'groups':{'x':{'sampleSpreadArchiveBytes':[0,8486559278]}}}
        f=capacity(self.g,{},old)
        self.assertEqual(sum(f['storageCategories'].values()),24*GIB);self.assertEqual(sum(f['readCategories'].values()),21*GIB)
        self.assertEqual(f['cost']['firstMonthWith20PercentUSD'],'7.9200')
        self.assertFalse(f['approved']);self.assertFalse(f['validation']['fullProductionReady']);self.assertFalse(f['sourceForecast']['quotaSlicesAreMeasuredDemand'])
        self.assertLess(f['checkpointBookkeeping']['reservedBytes'],GIB)
        self.assertTrue(validate_envelope(f))
        for change in ['storage','operations','cost','approval','source']:
            bad=copy.deepcopy(f)
            if change=='storage':bad['storageCategories']['selectedCacheCumulative']+=1
            elif change=='operations':bad['operationForecast']['classAUpperAllocated']=100000
            elif change=='cost':bad['cost']['firstMonthWith20PercentUSD']='0'
            elif change=='approval':bad['approved']=True
            else:bad['sourceForecast']['rescueSourceReservationBytes']+=1
            with self.assertRaises(ValueError):validate_envelope(bad)

if __name__=='__main__':unittest.main()
