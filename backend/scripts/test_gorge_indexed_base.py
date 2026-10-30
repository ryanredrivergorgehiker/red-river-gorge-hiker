import io,json,tarfile,unittest
from unittest.mock import patch
from gorge_base_inventory import archive_inventory
from gorge_base_ranges import BASE_AUTHORITY
from gorge_indexed_base import IndexedArchive
from gorge_checkpoint import canonical,digest
class IndexedBaseTests(unittest.TestCase):
 def fixture(self):
  files={'v.geojson':b'{}','weather.json':b'{}'}
  manifest={'vectors':[{'path':'v.geojson'}],'weatherManifest':{'path':'weather.json'},'staticAssets':[]};raw=canonical(manifest);files['NATIVE-MAP.json']=raw
  stream=io.BytesIO()
  with tarfile.open(fileobj=stream,mode='w',format=tarfile.GNU_FORMAT) as t:
   for name,data in files.items():
    m=tarfile.TarInfo('./'+name);m.size=len(data);t.addfile(m,io.BytesIO(data))
  stream.seek(0)
  with tarfile.open(fileobj=stream,mode='r:') as t:index=archive_inventory(t,digest(raw))
  bounds={'requiredMembers':3,'requiredSharedBytes':sum(len(v) for v in files.values()),'largestMemberBytes':len(raw)}
  return stream,index,bounds,digest(raw)
 def test_indexed_exact_member_read_and_manifest_binding(self):
  stream,index,bounds,sha=self.fixture()
  with patch('gorge_indexed_base.MANIFEST_SHA',sha):
   t=IndexedArchive(index,stream,bounds)
   self.assertEqual(json.load(t.extractfile(t.members['NATIVE-MAP.json'])),index['manifest'])
 def test_changed_size_offset_or_member_set_rejected(self):
  for field,value in [('bytes',1),('offset',513),('path','../v.geojson')]:
   stream,index,bounds,sha=self.fixture();index['members'][0][field]=value
   with patch('gorge_indexed_base.MANIFEST_SHA',sha),self.assertRaises(ValueError):IndexedArchive(index,stream,bounds)
 def test_generation_change_rejected_before_payload(self):
  stream,index,bounds,sha=self.fixture();index['acceptedBase']={**BASE_AUTHORITY,'generation':'1'}
  with patch('gorge_indexed_base.MANIFEST_SHA',sha),self.assertRaises(ValueError):IndexedArchive(index,stream,bounds)
if __name__=='__main__':unittest.main()
