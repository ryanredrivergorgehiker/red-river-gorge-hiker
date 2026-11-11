import copy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gorge_checkpoint import Ref,digest as raw_digest
from build_gorge_map_bundles import part_size
from rrgh_package_authority import digest
from rrgh_package_records import put,descriptors,describe
from rrgh_package_contract import empty,next_operation
from rrgh_package_runtime import stage,verify
from test_rrgh_package_assembly import fixture,ReadSlot
import test_rrgh_package_authority as authority_fixture


class MemorySlot(ReadSlot):
    def __init__(self,objects):
        super().__init__(objects);self.metadata={}
        self.plan=dict(finalPackagePhase=dict(ordinal=8,previousCheckpoint=None))
        self.store=SimpleNamespace(_request=self.metadata_request)
        self.meter.caps.update(classARequests=100,classBRequests=1000,storedBytes=100*2**20,egressBytes=100*2**20)
    def metadata_request(self,method,key,query,maximum):
        return json.dumps(self.metadata[key]).encode(),{},200
    def put(self,raw,kind):
        hash=raw_digest(raw);key='engineering/map-production/plans/'+'d'*64+'/slots/00000/'+kind+'/'+hash
        ref=Ref(key,'456',len(raw),hash);self.objects[(key,'456')]=raw;return ref
    def upload(self,slot,path,identity,root,name):
        ref=self.put(Path(path).read_bytes(),'packs')
        self.metadata[ref.key]=dict(bucket='rrgh-nonproduction-protected-packages',name=ref.key,
            generation=ref.generation,size=str(ref.bytes),metadata={'rrgh-sha256':identity['sha256'],
                'rrgh-package-id':identity['packageID'],'rrgh-version':identity['version']})
        return asdict(ref)


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authority_fixture.PackageAuthorityTests.setUpClass();cls.auth=authority_fixture.PackageAuthorityTests.authority
    def prepare(self):
        inventory,original,source=fixture();slot=MemorySlot(source.objects)
        parts=[]
        for i,entries in enumerate((original['entries'][:2],original['entries'][2:])):
            parts.append(dict(id=f'core-{i:03d}',group='core',entries=entries,files=len(entries)+1,
                              expectedArchiveBytes=part_size('core',entries)))
        layout=dict(authoritySHA256=digest(self.auth),inventorySHA256=digest(inventory),parts=parts,groups={})
        refs=[put(slot,v) for v in descriptors(inventory,layout)]
        delivery=describe(layout,refs,{'core':[]})
        checkpoint=empty(self.auth);checkpoint.update(ordinal=7,
            slices=[dict(start=0,stop=len(self.auth['waves']),object=refs[0])],layout=put(slot,delivery))
        return slot,checkpoint,next_operation(self.auth,checkpoint,delivery)
    def test_two_part_batch_local_build_and_fresh_download_before_checkpoint(self):
        slot,checkpoint,op=self.prepare()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'stage').mkdir();(root/'verify').mkdir()
            with patch('rrgh_package_runtime.upload',side_effect=slot.upload):
                produced=stage(slot,self.auth,checkpoint,op,root/'stage')
            # Separate meter and reader represent the independent job. It has
            # only immutable metadata/objects, no producer extraction directory.
            independent=MemorySlot(dict(slot.objects));independent.metadata=copy.deepcopy(slot.metadata)
            result=verify(independent,self.auth,checkpoint,op,produced,root/'verify')
            self.assertEqual(len(result['parts']),2)
            self.assertEqual(sum(p['rasterTiles'] for p in result['parts']),5)
            self.assertEqual(checkpoint['parts'],[])
            self.assertFalse(result['finalPackageDeliveryComplete'])
    def test_later_corruption_does_not_partially_accept_batch(self):
        slot,checkpoint,op=self.prepare()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'stage').mkdir();(root/'verify').mkdir()
            with patch('rrgh_package_runtime.upload',side_effect=slot.upload):
                produced=stage(slot,self.auth,checkpoint,op,root/'stage')
            ref=produced['products'][1]['object'];key=(ref['key'],ref['generation'])
            slot.objects[key]=b'!'+slot.objects[key][1:]
            with self.assertRaises(ValueError):verify(slot,self.auth,checkpoint,op,produced,root/'verify')
            self.assertEqual(checkpoint['parts'],[])
    def test_reordered_or_missing_parts_fail_closed(self):
        slot,checkpoint,op=self.prepare()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'stage').mkdir()
            with patch('rrgh_package_runtime.upload',side_effect=slot.upload):
                produced=stage(slot,self.auth,checkpoint,op,root/'stage')
            for i,products in enumerate((produced['products'][:1],list(reversed(produced['products'])))):
                path=root/str(i);path.mkdir()
                with self.assertRaises(ValueError):verify(slot,self.auth,checkpoint,op,dict(produced,products=products),path)
            self.assertEqual(checkpoint['parts'],[])


if __name__=='__main__':unittest.main()
