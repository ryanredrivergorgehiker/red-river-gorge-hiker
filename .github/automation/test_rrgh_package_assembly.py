import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image
from gorge_checkpoint import Meter, DIMENSIONS, digest as raw_digest
from build_gorge_map_bundles import part_size
from rrgh_package_assembly import recover_part, native_entry
from rrgh_package_authority import geometry


class ReadSlot:
    def __init__(self, objects):
        self.objects=objects;self.calls=[]
        caps=dict.fromkeys(DIMENSIONS,0)
        caps.update(egressBytes=16*2**20,classBRequests=100,seconds=60)
        self.meter=Meter(caps)
    def get(self, ref, start=0, length=None, expected_sha256=None):
        length=ref.bytes if length is None else length
        self.meter.reserve(classBRequests=1,egressBytes=length+1)
        self.calls.append((ref,start,length))
        raw=self.objects[(ref.key,ref.generation)][start:start+length]
        if expected_sha256 and raw_digest(raw)!=expected_sha256:raise ValueError('Hash mismatch')
        return raw


def fixture():
    jid='hiking-16-17544-25322';data=bytearray();files=[]
    for i,(layer,z,x,y) in enumerate(sorted(geometry(jid))):
        im=Image.new('RGB',(256,256))
        im.putdata([((xx+i)%256,yy,(xx+yy)%256) for yy in range(256) for xx in range(256)])
        buffer=io.BytesIO();im.save(buffer,format='PNG');raw=buffer.getvalue()
        files.append(dict(path=f'tiles/{layer}/{z}/{x}/{y}.png',bytes=len(raw),sha256=raw_digest(raw),
                          object=0,offset=len(data),job=jid));data.extend(raw)
    raw=bytes(data)
    obj=dict(key='engineering/map-production/plans/'+'a'*64+'/slots/00001/outputs/'+raw_digest(raw),
             bytes=len(raw),generation='123',sha256=raw_digest(raw))
    inventory=dict(files=files,objects=[obj])
    entries=[native_entry(f)[0] for f in files]
    part=dict(id='core-000',group='core',entries=entries,files=len(entries)+1,
              expectedArchiveBytes=part_size('core',entries))
    slot=ReadSlot({(obj['key'],obj['generation']):raw})
    return inventory,part,slot


class AssemblyTests(unittest.TestCase):
    def test_unchanged_bytes_and_native_archive_roundtrip(self):
        inventory,part,slot=fixture()
        with tempfile.TemporaryDirectory() as temp:
            result=recover_part(slot,inventory,part,Path(temp)/'part')
            self.assertEqual(result['rasterTiles'],5)
            self.assertTrue(result['allMemberHashesVerified'])
            self.assertFalse(result['finalPackageDeliveryComplete'])
            self.assertEqual(len(slot.calls),1)
            with tarfile.open(result['path'],'r:') as archive:
                self.assertEqual(archive.getnames()[0],'PART-MANIFEST.json')
                manifest=json.load(archive.extractfile('PART-MANIFEST.json'))
                self.assertEqual(manifest['files'],part['entries'])
                for e in inventory['files']:
                    self.assertEqual(raw_digest(archive.extractfile(e['path']).read()),e['sha256'])

    def test_corrupt_accepted_pack_fails_before_archive_creation(self):
        inventory,part,slot=fixture();key=next(iter(slot.objects))
        slot.objects[key]=b'!'+slot.objects[key][1:]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'part'
            with self.assertRaises(ValueError):recover_part(slot,inventory,part,root)
            self.assertFalse((root/'output').exists())

    def test_changed_layout_member_is_rejected_before_cloud_reads(self):
        inventory,part,slot=fixture();part['entries'][0]['sha256']='b'*64
        part['expectedArchiveBytes']=part_size('core',part['entries'])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):recover_part(slot,inventory,part,Path(temp)/'part')
        self.assertEqual(slot.calls,[])

    def test_existing_workspace_cannot_be_reused(self):
        inventory,part,slot=fixture()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):recover_part(slot,inventory,part,Path(temp))
        self.assertEqual(slot.calls,[])

    def test_rehashed_blank_pixels_are_not_accepted(self):
        inventory,part,slot=fixture()
        im=Image.new('RGB',(256,256),'white');buf=io.BytesIO();im.save(buf,format='PNG');raw=buf.getvalue()
        obj=inventory['objects'][0];obj.update(bytes=len(raw),sha256=raw_digest(raw))
        e=inventory['files'][0];e.update(bytes=len(raw),sha256=raw_digest(raw),offset=0)
        inventory['files']=[e]
        part['entries']=[native_entry(e)[0]];part['files']=2
        part['expectedArchiveBytes']=part_size('core',part['entries'])
        slot.objects[(obj['key'],obj['generation'])]=raw
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'Blank'):recover_part(slot,inventory,part,Path(temp)/'part')


if __name__=='__main__':unittest.main()
