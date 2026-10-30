import io,json,tarfile,unittest
from gorge_base_inventory import archive_inventory
from gorge_checkpoint import canonical,digest
class InventoryTests(unittest.TestCase):
 def fixture(self):
  manifest={'vectors':[{'path':'v.geojson'}],'weatherManifest':{'path':'weather.json'},'staticAssets':[{'path':'weather.json'},{'path':'rrg-lidar-sun-old.webp'},{'path':'weather.png'}]}
  raw=canonical(manifest);buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w',format=tarfile.GNU_FORMAT) as t:
   for name,data in [('NATIVE-MAP.json',raw),('v.geojson',b'{}'*100),('weather.json',b'{}'),('weather.png',b'png'),('rrg-lidar-sun-old.webp',b'old'),('unused.bin',bytes(4096))]:
    m=tarfile.TarInfo('./'+name);m.size=len(data);t.addfile(m,io.BytesIO(data))
  buf.seek(0);return tarfile.open(fileobj=buf,mode='r:'),raw
 def test_real_layout_index_counts_exact_shared_bytes_without_raster_payloads(self):
  with self.fixture()[0] as t:
   raw=t.extractfile('./NATIVE-MAP.json').read();original=t.extractfile;reads=[]
   def tracked(m):reads.append(m.name);return original(m)
   t.extractfile=tracked
   result=archive_inventory(t,digest(raw))
   self.assertEqual(reads,['./NATIVE-MAP.json']);self.assertEqual(len(result['members']),4)
   self.assertEqual(sum(e['bytes'] for e in result['members']),len(raw)+205)
   self.assertEqual(result['archiveMembers'],6)
 def test_changed_accepted_manifest_fails_before_reading_shared_payload(self):
  with self.fixture()[0] as t:
   with self.assertRaisesRegex(ValueError,'manifest changed'):archive_inventory(t)
if __name__=='__main__':unittest.main()
