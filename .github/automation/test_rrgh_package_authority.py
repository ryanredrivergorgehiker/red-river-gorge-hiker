import copy
import unittest

from rrgh_package_authority import geometry, required_jobs, validate, FORMAT, digest
from rrgh_seed_children import AUTHORITY as SEEDS, AUTHORITY_SHA as SEED_SHA
from rrgh_package_inventory import validate_job, job_outputs


def object_ref():
    return dict(key='engineering/map-production/plans/'+'1'*64+'/slots/00001/outputs/'+'2'*64,
                generation='1',bytes=1000000,sha256='2'*64)


def outputs(jid):
    return [dict(output=dict(path=f'tiles/{l}/{z}/{x}/{y}.jpg',bytes=100,sha256='3'*64),
                 member=dict(path=f'tiles/{l}/{z}/{x}/{y}.jpg',bytes=100,sha256='3'*64,offset=i*100),
                 object=object_ref()) for i,(l,z,x,y) in enumerate(sorted(geometry(jid)))]


class PackageAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        jobs=sorted(required_jobs()-set(SEEDS['jobs']))
        waves=[]
        for i in range(0,len(jobs),512):
            group=jobs[i:i+512]
            waves.append(dict(acceptanceKind='ordinary',sourcePlanSHA256=f'{i:064x}',
                acceptedJobIDs=group,sourceJobCount=len(group),expectedTiles=sum(len(geometry(j)) for j in group)))
        cls.authority=dict(format=FORMAT,seedAuthoritySHA256=SEED_SHA,rasterTiles=278278,
            protectedByteReadbackPerformed=False,finalPackageDeliveryComplete=False,
            waves=waves,acceptedJobs=sorted(required_jobs()))

    def test_exact_all_layer_denominator(self):
        result=validate(self.authority)
        self.assertEqual(result['rasterTiles'],278278)
        self.assertEqual(result['acceptedJobs'],34750)
        self.assertEqual(len(geometry('leaf-on-16-17544-25322')),21)
        self.assertEqual(len(geometry('usgs-topo-16-17544-25322')),1)

    def test_missing_usgs_is_rejected_despite_complete_four_layer_sources(self):
        candidate=copy.deepcopy(self.authority)
        for wave in candidate['waves']:
            jobs=[j for j in wave['acceptedJobIDs'] if j!='usgs-topo-10-273-395']
            if len(jobs)!=len(wave['acceptedJobIDs']):
                wave['acceptedJobIDs']=jobs;wave['sourceJobCount']-=1;wave['expectedTiles']-=1
                break
        with self.assertRaises(ValueError):validate(candidate)

    def test_same_tile_count_cannot_replace_required_position(self):
        entry=outputs('usgs-topo-16-17544-25322')
        entry[0]['output']['path']=entry[0]['member']['path']='tiles/usgs-topo/16/17544/25323.jpg'
        with self.assertRaises(ValueError):validate_job('usgs-topo-16-17544-25322',entry)

    def test_duplicate_acceptance_and_fake_delivery_flag_rejected(self):
        candidate=copy.deepcopy(self.authority)
        candidate['waves'].append(copy.deepcopy(candidate['waves'][0]))
        with self.assertRaises(ValueError):validate(candidate)
        candidate=copy.deepcopy(self.authority);candidate['finalPackageDeliveryComplete']=True
        with self.assertRaises(ValueError):validate(candidate)

    def test_original_seed_cannot_be_replaced_by_new_wave(self):
        candidate=copy.deepcopy(self.authority);j=SEEDS['jobs'][0]
        candidate['waves'][0]['acceptedJobIDs'].append(j)
        candidate['waves'][0]['sourceJobCount']+=1
        candidate['waves'][0]['expectedTiles']+=len(geometry(j))
        with self.assertRaises(ValueError):validate(candidate)

    def test_original_usgs_high_zoom_is_never_synthesized(self):
        with self.assertRaises(ValueError):geometry('usgs-topo-17-35088-50644')

    def test_pack_extent_and_hash_are_bound(self):
        jid='hiking-16-17544-25322';entries=outputs(jid)
        validate_job(jid,entries)
        for field,value in [('offset',1000000),('bytes',101),('sha256','4'*64)]:
            candidate=copy.deepcopy(entries);candidate[0]['member'][field]=value
            with self.assertRaises(ValueError):validate_job(jid,candidate)

    def test_foreign_receipt_or_recipe_rejected(self):
        jid='hiking-16-17544-25322';entries=outputs(jid)
        source=dict(sourcePlanSHA256='1'*64,acceptedJobIDs=[jid],recipeSHA256='4'*64)
        ref=dict(key='engineering/map-production/plans/'+'1'*64+'/slots/00001/jobs/'+jid+'.json')
        row=dict(job=jid,format='rrgh-checkpoint-job-v1',slot=1,planSHA256='1'*64,result=dict(
            originalReceipt=dict(job=jid,validated=True,recipeSHA256='4'*64,outputs=[e['output'] for e in entries]),
            outputPacks=[dict(ref=object_ref(),members=[e['member'] for e in entries])]))
        self.assertEqual(len(job_outputs(row,ref,source)),5)
        candidate=copy.deepcopy(row);candidate['result']['originalReceipt']['recipeSHA256']='5'*64
        with self.assertRaises(ValueError):job_outputs(candidate,ref,source)
        candidate=copy.deepcopy(row);candidate['slot']=2
        with self.assertRaises(ValueError):job_outputs(candidate,ref,source)


if __name__=='__main__':unittest.main()
