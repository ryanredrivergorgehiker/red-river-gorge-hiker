"""Real compact record decoding, selective ranges and pinned renderer offline.

Only GCS transport is in memory. Synthetic fixtures are never live acceptance.
"""
import base64
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
from PIL import Image

import rrgh_crosswave_dependencies as c

SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','source-checkout')).resolve()
sys.path.insert(0,str(SOURCE/'backend/scripts'))
from gorge_checkpoint import Meter,DIMENSIONS,digest,encode_record


class MemorySlot:
    def __init__(self,objects):
        self.objects=objects;self.reads=[];self.meter=Meter(dict.fromkeys(DIMENSIONS,100000000))
    def get(self,reference,start=0,length=None):
        actual,raw=self.objects[reference.key]
        if actual!=reference.__dict__ or len(raw)!=reference.bytes or digest(raw)!=reference.sha256:
            raise ValueError('Pinned generation/length/hash mismatch')
        length=reference.bytes if length is None else length
        self.meter.reserve(classBRequests=1,egressBytes=length+1)
        self.reads.append((reference.key,start,length))
        return raw[start:start+length]


def fixture(layer='terrain',transparent=False,wave_offset=0):
    job=dict(id=f'{layer}-15-8756-12645',layer=layer,z=15,x=8756,y=12645,
        operation='overview',sourceIDs=[],outputTiles=[[15,8756,12645]])
    ids=c.child_ids(job);objects={};waves=[]
    def put(key,raw):
        ref=dict(key=key,generation=str(len(objects)+1),bytes=len(raw),sha256=digest(raw))
        objects[key]=(ref,raw);return ref
    def record(key,obj):return put(key,encode_record(obj,2**20,True))
    for n in range(2):
        sha=str(n+1+wave_offset)*64;recipe=str(n+3)*64;prefix='engineering/map-production/plans/'+sha+'/slots/'
        refs=[]
        for k,jid in enumerate(ids[n*2:n*2+2]):
            x,y=map(int,jid.rsplit('-',2)[1:]);path=f'tiles/{layer}/16/{x}/{y}.png'
            image=Image.new('RGB',(256,256))
            image.putdata([((a+13*n)%256,(b+19*k)%256,(a+b)//2) for b in range(256) for a in range(256)])
            if transparent:
                image.putalpha(255);image.putpixel((0,0),(0,0,0,0))
            stream=io.BytesIO();image.save(stream,format='PNG');raw=stream.getvalue()
            out=dict(path=path,bytes=len(raw),sha256=digest(raw));packraw=b'untouched-prefix'+raw+b'untouched-suffix'
            pack=dict(ref=put(prefix+'00001/outputs/'+digest(packraw),packraw),members=[dict(out,offset=16)])
            # Both sentinels have sixteen bytes and must never be downloaded.
            pack['members'][0]['offset']=len(b'untouched-prefix')
            original=dict(job=jid,validated=True,recipeSHA256=recipe,outputs=[out],sourceEvidence=[])
            refs.append(record(prefix+'00001/jobs/'+jid+'.json',dict(format='rrgh-checkpoint-job-v1',
                planSHA256=sha,slot=1,job=jid,result=dict(originalReceipt=original,outputPacks=[pack]))))
        detail=record(prefix+'00001/indexes/details',dict(completedJobReceipts=refs))
        worker=record(prefix+'00001/receipt.json',dict(format='rrgh-slot-receipt-v1',planSHA256=sha,slot=1,
            result=dict(status='complete',detailRef=detail)))
        recovery=record(prefix+'00002/receipt.json',dict(format='rrgh-slot-receipt-v1',planSHA256=sha,slot=2,
            result=dict(status='verified',jobs=2,tiles=2,workerReceipt=worker,detailRef=detail,
                settlement=dict(sequence=n+10+wave_offset,planSHA256=sha,independentRecoveryComplete=True),
                allOutputHashesAndPixelsVerified=True,allNewPackageChunksReadBack=True,allExistingCachesPreserved=True)))
        waves.append(dict(sequence=n+10+wave_offset,sourcePlanSHA256=sha,recipeSHA256=recipe,recovery=recovery,
            sourceJobCount=2,expectedTiles=2,acceptedJobIDs=ids[n*2:n*2+2],acceptanceKind='ordinary'))
    index=dict(waves=waves);return job,index,ids,objects,c.manifest(index,job,ids)


class CrosswaveTests(unittest.TestCase):
    def test_four_layers_decode_real_compact_records_read_only_ranges_and_render(self):
        from rrgh_verified_overview import render
        raw=(SOURCE/'backend/config/gorge-campaign-wave-1322-20261102/REGION-PLAN.json.z.b64').read_bytes()
        region=json.loads(zlib.decompress(base64.b64decode(raw)))
        # Region engine pins are exact production hashes, not test substitutions.
        for layer in c.LAYERS:
            with self.subTest(layer=layer),tempfile.TemporaryDirectory() as tmp:
                job,index,ids,objects,binding=fixture(layer);before=copy.deepcopy(objects);slot=MemorySlot(objects)
                root=Path(tmp);proof=c.read(slot,job,binding,ids,root/'children')
                self.assertEqual(proof['sourceWaves'],2);self.assertEqual(len(slot.reads),14)
                reads=[r for r in slot.reads if '/outputs/' in r[0]]
                self.assertEqual(len(reads),4)
                self.assertTrue(all(start==len(b'untouched-prefix') and length<objects[key][0]['bytes'] for key,start,length in reads))
                a=render(region,job,proof['children'],root/'children',root/'parent',SOURCE)
                second=c.read(MemorySlot(objects),job,binding,ids,root/'fresh-children')
                b=render(region,job,second['children'],root/'fresh-children',root/'fresh-parent',SOURCE)
                self.assertEqual(a['receipt']['outputs'],b['receipt']['outputs'])
                self.assertEqual(objects,before);self.assertFalse(proof['productionAccepted'])

    def test_wrong_generation_missing_child_or_conflicting_wave_pins_rejected(self):
        for fault in ('generation','accepted','recipe','source_count','source_tiles','duplicate_child','conflicting_wave','usgs','boundary'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                job,index,ids,objects,binding=fixture()
                if fault=='generation':binding['children'][0]['source']['recovery']['generation']='99999'
                elif fault=='accepted':ids.pop()
                elif fault=='recipe':binding['children'][0]['source']['recipeSHA256']='a'*64
                elif fault=='source_count':binding['children'][0]['source']['sourceJobCount']=1
                elif fault=='source_tiles':binding['children'][0]['source']['expectedTiles']=3
                elif fault=='duplicate_child':binding['children'][1]=copy.deepcopy(binding['children'][0])
                elif fault=='conflicting_wave':binding['children'][1]['source']['recipeSHA256']='a'*64
                elif fault=='usgs':job['layer']='usgs-topo'
                else:
                    job.update(id='terrain-15-0-0',x=0,y=0,outputTiles=[[15,0,0]])
                    binding['job']=copy.deepcopy(job)
                    ids=c.child_ids(job)
                    for child,jid in zip(binding['children'],ids):child['job']=jid
                with self.assertRaises(ValueError):c.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'children')

    def test_corrupt_or_transparent_child_is_never_promoted(self):
        job,index,ids,objects,binding=fixture()
        key=next(k for k in objects if '/outputs/' in k)
        ref,raw=objects[key];objects[key]=(ref,raw[:-1]+b'X')
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
            c.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'children')
        job,index,ids,objects,binding=fixture(transparent=True)
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'pixels'):
            c.read(MemorySlot(objects),job,binding,ids,Path(tmp)/'children')

    def test_partial_salvage_and_missing_seed_do_not_invent_provenance(self):
        for fault in ('partial','missing','duplicate'):
            job,index,ids,objects,binding=fixture()
            if fault=='partial':index['waves'][0]['acceptanceKind']='partial-needs-typed-receipt'
            elif fault=='missing':index['waves'].pop()
            else:index['waves'].append(copy.deepcopy(index['waves'][0]))
            with self.subTest(fault=fault),self.assertRaises(ValueError):c.manifest(index,job,ids)


if __name__=='__main__':unittest.main()
