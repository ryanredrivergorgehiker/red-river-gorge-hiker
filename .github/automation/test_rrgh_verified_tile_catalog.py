"""Real encoded fixture tiles/native archives; no Cloud or production claims."""
import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from PIL import Image
import rrgh_verified_tile_catalog as c


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.job='hiking-16-17560-25330';self.path='tiles/hiking/16/17560/25330.png'
        im=Image.new('RGB',(256,256));im.putdata([(x%256,y%256,(x+y)%256) for y in range(256) for x in range(256)])
        stream=io.BytesIO();im.save(stream,format='PNG');raw=stream.getvalue()
        target=self.root/'outputs'/self.path;target.parent.mkdir(parents=True);target.write_bytes(raw)
        self.region=dict(jobs=[dict(id=self.job,layer='hiking',outputTiles=[[16,17560,25330]])])
        self.plan=dict(approvedJobIDs=[self.job],regionPlanSHA256=c.digest(c.canonical(self.region)),
                       campaign=dict(sequence=58,previousRecovery=dict(key='accepted-predecessor')))
        self.sha=c.digest(c.canonical(self.plan));self.base=c.PREFIX+'plans/'+self.sha+'/'
        self.output=dict(path=self.path,bytes=len(raw),sha256=c.digest(raw))
        object_ref=self.ref('outputs/preserved-pack',raw)
        self.records=[dict(format='rrgh-checkpoint-job-v1',job=self.job,planSHA256=self.sha,slot=1,
            result=dict(originalReceipt=dict(job=self.job,validated=True,
                recipeSHA256=c.digest((json.dumps(self.region,sort_keys=True,indent=2)+'\n').encode()),outputs=[self.output]),
                outputPacks=[dict(ref=object_ref,members=[dict(self.output,offset=0)])]))]
        self.refs=[self.ref('slots/00001/jobs/'+self.job+'.json',c.canonical(self.records[0]))]
        self.qa=dict(allExpectedTilesPresent=True,pixelsDecoded=True,gridAndAlphaVerified=True,jobs=1,files=1,bytes=len(raw))
        manifest=c.canonical(dict(format='rrgh-map-part-v1',group='core',files=[dict(self.output,layer='hiking',z=16,x=17560,y=25330)]))
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w',format=tarfile.USTAR_FORMAT) as tar:
            for name,data in [('PART-MANIFEST.json',manifest),(self.path,raw)]:
                member=tarfile.TarInfo(name);member.size=len(data);member.mtime=0;tar.addfile(member,io.BytesIO(data))
        archive=buf.getvalue();name=c.digest(archive)+'.rrghpkg'
        folder=self.root/'parts/core';folder.mkdir(parents=True);(folder/name).write_bytes(archive)
        self.parts=[dict(group='core',file=name,byteCount=len(archive),sha256=c.digest(archive),fileCount=2,
            manifestSHA256=c.digest(manifest),chunks=[dict(offset=0,ref=self.ref('outputs/native-package',archive))])]
    def tearDown(self):self.tmp.cleanup()
    def ref(self,key,raw):return dict(key=self.base+key,generation='123456',bytes=len(raw),sha256=c.digest(raw))
    def run_catalog(self):return c.catalog(self.plan,self.region,self.records,self.refs,self.qa,self.parts,self.root)
    def test_exact_tile_checkpoint_generation_and_native_membership_export(self):
        result=self.run_catalog();tile=result['tiles'][0]
        self.assertEqual(tile['tile'],['hiking',16,17560,25330]);self.assertEqual(tile['sha256'],self.output['sha256'])
        self.assertEqual(tile['jobReceipt'],self.refs[0]);self.assertEqual(tile['checkpointObject']['generation'],'123456')
        self.assertEqual(tile['package']['chunks'],self.parts[0]['chunks'])
        self.assertTrue(result['independentPixelsAndHashesVerified']);self.assertFalse(result['fullRegionalCoverageClaimed'])
        self.assertFalse(result['deliveryVerified']);self.assertFalse(result['physicalDeviceVerified'])
    def test_pixel_verification_cannot_be_skipped(self):
        self.qa['pixelsDecoded']=False
        with self.assertRaisesRegex(ValueError,'pixel'):self.run_catalog()
    def test_output_tamper_rejected(self):
        (self.root/'outputs'/self.path).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.run_catalog()
    def test_foreign_plan_receipt_rejected(self):
        self.refs[0]['key']=self.refs[0]['key'].replace(self.sha,'f'*64)
        with self.assertRaisesRegex(ValueError,'lineage'):self.run_catalog()
    def test_foreign_object_rejected(self):
        self.records[0]['result']['outputPacks'][0]['ref']['key']=c.PREFIX+'other/output'
        with self.assertRaisesRegex(ValueError,'another plan'):self.run_catalog()
    def test_overlapping_range_rejected(self):
        pack=self.records[0]['result']['outputPacks'][0];pack['members'].append(dict(pack['members'][0],path='other'))
        with self.assertRaisesRegex(ValueError,'Overlapping'):self.run_catalog()
    def test_native_package_tamper_rejected(self):
        (self.root/'parts/core'/self.parts[0]['file']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'package bytes'):self.run_catalog()
    def test_missing_native_package_rejected(self):
        self.parts=[]
        with self.assertRaisesRegex(ValueError,'not durably packaged'):self.run_catalog()
    def test_package_chunk_generation_is_required(self):
        self.parts[0]['chunks'][0]['ref']['generation']=''
        with self.assertRaisesRegex(ValueError,'generation'):self.run_catalog()
    def test_incomplete_package_chunks_rejected(self):
        self.parts[0]['chunks']=[]
        with self.assertRaisesRegex(ValueError,'Incomplete durable'):self.run_catalog()
    def test_duplicate_record_rejected(self):
        self.records*=2;self.refs*=2
        with self.assertRaisesRegex(ValueError,'duplicate recovered'):self.run_catalog()
    def test_missing_job_reference_rejected(self):
        self.refs=[]
        with self.assertRaisesRegex(ValueError,'paired'):self.run_catalog()
    def test_unpinned_region_rejected(self):
        self.region['jobs'][0]['outputTiles']=[[16,17561,25330]]
        with self.assertRaisesRegex(ValueError,'region pin'):self.run_catalog()
    def test_symlink_rejected(self):
        target=self.root/'outputs'/self.path;target.rename(target.with_suffix('.original'));target.symlink_to(target.with_suffix('.original'))
        with self.assertRaisesRegex(ValueError,'Symlink'):self.run_catalog()
    def test_recovery_totals_must_match(self):
        self.qa['files']=2
        with self.assertRaisesRegex(ValueError,'totals disagree'):self.run_catalog()


if __name__=='__main__':unittest.main()
