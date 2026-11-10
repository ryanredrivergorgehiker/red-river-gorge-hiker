import copy
from dataclasses import asdict
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from gorge_checkpoint import Ref,digest as raw_digest
from rrgh_package_authority import digest
from rrgh_package_records import put,get,descriptors,describe,part_input
from rrgh_package_provenance import build,VECTORS
from rrgh_package_assembly import GROUP
from test_rrgh_package_assembly import fixture


class MetadataSlot:
    def __init__(self):self.objects={}
    def put(self,raw,kind):
        ref=Ref(key='engineering/map-production/plans/'+'a'*64+'/slots/00000/indexes/'+raw_digest(raw),
            generation='123',bytes=len(raw),sha256=raw_digest(raw))
        self.objects[ref.key]=raw;return ref
    def get(self,ref):
        raw=self.objects[ref.key]
        if raw_digest(raw)!=ref.sha256:raise ValueError('Hash changed')
        return raw


class MetadataTests(unittest.TestCase):
    def test_descriptor_preserves_original_member_ranges_and_native_layout(self):
        inventory,part,_=fixture()
        layout=dict(authoritySHA256='b'*64,inventorySHA256=digest(inventory),parts=[part],groups={})
        value=list(descriptors(inventory,layout))[0];slot=MetadataSlot()
        reference=put(slot,value)
        delivery=describe(layout,[reference],{'core':[]})
        op=dict(kind='part',partID=part['id'],archiveBytes=part['expectedArchiveBytes'],
            contentBytes=sum(e['bytes'] for e in part['entries']),files=part['files'],descriptorBytes=reference['bytes'])
        self.assertEqual(part_input(slot,delivery,op)['inventory'],inventory)
        self.assertEqual(get(slot,reference),value)
        wrong=dict(op,archiveBytes=op['archiveBytes']+10240)
        with self.assertRaises(ValueError):part_input(slot,delivery,wrong)
    def test_record_sizes_and_content_hash_are_enforced(self):
        slot=MetadataSlot();reference=put(slot,{'key':'x'*500})
        with self.assertRaises(ValueError):get(slot,reference,maximum=10)
        with self.assertRaises(ValueError):put(slot,{'key':'x'*500},decoded=20)
        slot.objects[reference['key']]=b'corrupt'
        with self.assertRaises(ValueError):get(slot,reference)
    def test_provenance_retains_separate_osm_and_truthful_derivative_hashes(self):
        files=[dict(path='tiles/'+layer+'/16/17544/25322.png',bytes=100,sha256='a'*64) for layer in GROUP]
        vectors=[dict(id=i,path='shared/'+i+'.geojson',sha256='b'*64) for i in VECTORS]
        sun=dict(path='shared/sun.json',sha256='c'*64,sourceCommit='d'*40)
        weather=dict(path='shared/weather.json',sha256='e'*64,sourceCommit='d'*40)
        files.extend(dict(path=e['path'],bytes=100,sha256=e['sha256']) for e in vectors+[sun,weather])
        shared=dict(vectors=vectors,sunPotentialManifest=sun,weatherManifest=weather)
        result=build({'files':files},shared,'test-release')
        self.assertEqual([len(result[g]) for g in ('core','leaf-on','leaf-off')],[18,1,1])
        osm=next(s for s in result['core'] if s['sourceID']=='rrgh-community-informal')
        self.assertIn('ODbL',osm['rightsBasis']);self.assertIn('Separate',osm['attributionOrDisclaimer'])
        raster=result['core'][0]
        self.assertIn('not upstream source archive',raster['integrityScope'])
        self.assertFalse(any('live' in s['vintageOrRetrievedAt'] for s in result['core']))
        files[-1]['sha256']='f'*64
        with self.assertRaises(ValueError):build({'files':files},shared,'test-release')


if __name__=='__main__':unittest.main()
