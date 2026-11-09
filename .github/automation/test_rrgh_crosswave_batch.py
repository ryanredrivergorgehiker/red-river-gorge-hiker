"""Real codecs/renderers with bounded in-memory transport; no live acceptance."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib
import rrgh_crosswave_batch as batch
import rrgh_crosswave_runtime as runtime
import rrgh_crosswave_dependencies as dependencies
import rrgh_dispatcher as dispatcher
from test_rrgh_crosswave_production import ProductionTests
from test_rrgh_crosswave_dependencies import MemorySlot,SOURCE,fixture


class BatchTests(unittest.TestCase):
    def test_shared_metadata_cache_is_slot_local_and_rechecks_authority(self):
        job,index,ids,objects,binding=fixture();cache={};slot=MemorySlot(objects)
        with tempfile.TemporaryDirectory() as tmp:
            a=dependencies.read(slot,job,binding,ids,Path(tmp)/'a',cache)
            b=dependencies.read(slot,job,binding,ids,Path(tmp)/'b',cache)
            self.assertEqual(a,b);self.assertEqual(len(slot.reads),14+8)
            independent=MemorySlot(objects)
            self.assertEqual(a,dependencies.read(independent,job,binding,ids,Path(tmp)/'c',{}))
            self.assertEqual(len(independent.reads),14)
            binding['children'][0]['source']['recovery']['generation']='9999'
            with self.assertRaisesRegex(ValueError,'Conflicting acceptance'):
                dependencies.read(slot,job,binding,ids,Path(tmp)/'d',cache)

    def test_batch_renders_all_layers_and_persists_full_independent_detail(self):
        helper=ProductionTests();plan,region,objects,_=helper.make()
        bindings=plan['crosswavePhase']['bindings']
        phase=dict(format=batch.FORMAT,authority=batch.POLICY,jobs=copy.deepcopy(region['jobs']),sources={},dependencies={})
        for b in bindings:
            phase['dependencies'][b['job']['id']]=[]
            for child in b['children']:
                sha=child['source']['sourcePlanSHA256'];phase['sources'][sha]=child['source']
                phase['dependencies'][b['job']['id']].append(dict(job=child['job'],source=sha))
        phase['readBounds']=batch.read_bounds(phase);plan['crosswavePhase']=phase
        plan['slots']=[{}, {}, {}];batch.fund(plan)
        plan['jobPolicies']={j:batch.JOB_POLICY for j in plan['approvedJobIDs']}
        class Writable(MemorySlot):
            def put(self,raw,kind):
                from gorge_checkpoint import Ref
                key='engineering/map-production/plans/'+batch.digest(plan)+'/slots/00002/'+kind+'/'+hashlib.sha256(raw).hexdigest()
                ref=dict(key=key,generation='123',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                self.objects[key]=(ref,raw);return Ref(**ref)
        before=copy.deepcopy(objects)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);records=helper.produce(MemorySlot(objects),plan,region,root)
            independent=Writable(objects);proof=runtime.verify(independent,plan,region,records,root/'verify',SOURCE)
            self.assertEqual(batch.validate_verification(proof),proof)
            self.assertEqual(len(proof['parents']),4);self.assertEqual(proof['planSHA256'],batch.digest(plan))
            from gorge_campaign import load_large
            detail=load_large(independent,proof['detailRef'],limit=4*2**20)
            self.assertEqual(batch.digest(detail),proof['detailSHA256'])
            self.assertEqual(detail['bindings'],bindings);self.assertEqual(len(detail['parents']),4)
            self.assertEqual({k:objects[k] for k in before},before)
            for field in ('allChildrenHashAndPixelVerified','allParentsIndependentlyRecomputed','sourceQualityUnchanged'):
                bad=copy.deepcopy(proof);bad[field]=False
                with self.assertRaises(ValueError):batch.validate_verification(bad)

    def test_full_sized_receipt_bounds_and_adjacent_pair_count(self):
        from gorge_checkpoint import encode_record,COMPACT_RECEIPT
        parents=[dict(job=f'terrain-15-{8756+i//8}-{12645+i%8}',outputBytes=12345,
            outputSHA256=hashlib.sha256(str(i).encode()).hexdigest()) for i in range(128)]
        proof=dict(format=batch.VERIFY,phaseSHA256='a'*64,planSHA256='b'*64,parents=parents,
            allChildrenHashAndPixelVerified=True,allParentsIndependentlyRecomputed=True,
            priorChildrenUnmodified=True,sourceQualityUnchanged=True,officialSourceRequests=0,
            detailSHA256='c'*64,detailRef=dict(key='engineering/map-production/plans/'+'b'*64+'/slots/00002/indexes/detail',
            generation='123',bytes=10000,sha256='d'*64))
        batch.validate_verification(proof)
        self.assertLess(len(encode_record(dict(result=dict(overviewPilotVerification=proof)),COMPACT_RECEIPT,True)),COMPACT_RECEIPT//2)
        self.assertEqual(batch.adjacent_pairs(parents),16*7+15*8)
        self.assertEqual(dispatcher.source_file_limit('backend/config/gorge-campaign-wave-1358-20261102/PLAN.json'),4_000_000)
        for p in ('other/PLAN.json','backend/scripts/PLAN.json','backend/config/gorge-campaign-wave-1358-20261102/ALLOWANCE.json'):
            self.assertEqual(dispatcher.source_file_limit(p),2_000_000)


if __name__=='__main__':unittest.main()
