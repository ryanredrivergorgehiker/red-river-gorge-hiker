"""Synthetic overview migration/provenance tests; no live acceptance."""
import copy
import base64
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

import rrgh_overview_integration as i
import rrgh_overview_pilot as p

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','rrgh-expansion-source')).resolve()


def synthetic_proof(job=None):
    m=i.manifest(job);prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
    rows=[]
    for jid in m['children']:
        x,y=map(int,jid.rsplit('-',2)[1:])
        rows.append(dict(job=jid,tile=['leaf-on',16,x,y],path=f'tiles/leaf-on/16/{x}/{y}.png',
            pixelReadbackVerified=True,bytes=100,sha256='c'*64,checkpointOffset=0,
            jobReceipt=dict(key=prefix+'slots/00001/jobs/'+jid+'.json',generation='1',sha256='a'*64,bytes=1000),
            checkpointObject=dict(key=prefix+'slots/00001/outputs/'+'b'*64,generation='2',sha256='b'*64,bytes=1000)))
    return dict(job=m['job'],fourChildrenHashAndPixelVerified=True,independentParentRecomputationMatches=True,
        officialSourceRequests=0,sourceQualityUnchanged=True,
        childProof=dict(format='rrgh-overview-dependency-proof-v1',job=m['job'],children=rows,
            originalIndependentRecovery=m['recovery'],sourceRecipeSHA256=m['sourceRecipeSHA256'],
            officialSourceRequests=0,priorChildrenUnmodified=True))


class OverviewProductionTests(unittest.TestCase):
    def test_all_twenty_two_parents_continue_once_then_native_production_remains(self):
        picked=[dict(id=f'{layer}-{n}',layer=layer,operation='source-window') for layer in ('hiking','terrain','leaf-off') for n in range(4)]
        manifests=i.candidates();accepted=set(c for m in manifests for c in m['children']);before=set(accepted)
        planned=[]
        for expected in manifests:
            new,authority=i.select(picked,accepted,{},True)
            self.assertEqual(authority,expected);self.assertEqual(len(new),12)
            self.assertEqual(sum(j['operation']=='overview' for j in new),1)
            i.validate_verification(synthetic_proof(expected['job']))
            accepted.add(expected['job']);planned.append(expected['job'])
        self.assertEqual(len(set(planned)),22);self.assertTrue(before<=accepted)
        self.assertEqual(i.select(picked,accepted,{},True),(picked,None))
        self.assertEqual(i.select(picked,before,{manifests[0]['job']:1},True),(picked,None))
        skipped,authority=i.select(picked,before|{manifests[0]['job']},{manifests[1]['job']:1},True)
        self.assertEqual(authority,manifests[2]);self.assertEqual(len(skipped),12)
        with self.assertRaises(ValueError):i.manifest('leaf-on-15-1-1')
    def test_installed_helper_migration_rejects_unknown_prior_code(self):
        current=(ROOT/'.github/automation/rrgh_overview_pilot.py').read_bytes()
        i.validate_prior_module('rrgh_overview_pilot.py',current,current)
        prior=(ROOT/'.github/automation/fixtures/overview-pilot-v1.py.txt').read_bytes()
        i.validate_prior_module('rrgh_overview_pilot.py',prior,current)
        with tempfile.TemporaryDirectory() as temporary:
            scripts=Path(temporary)/'backend/scripts';scripts.mkdir(parents=True)
            (scripts/'gorge_campaign.py').write_bytes((SOURCE/'backend/scripts/gorge_campaign.py').read_bytes())
            (scripts/'rrgh_overview_pilot.py').write_bytes(prior)
            i.install(temporary);i.validate_modules(temporary)
            self.assertEqual((scripts/'rrgh_overview_pilot.py').read_bytes(),current)
        for module in i.MODULES:
            with self.assertRaisesRegex(ValueError,'drift'):
                i.validate_prior_module(module,b'unreviewed prior module',current)
    def test_exact_campaign_integration_is_idempotent(self):
        code=(SOURCE/'backend/scripts/gorge_campaign.py').read_text()
        from rrgh_recovery_catalog_integration import augment_campaign
        baseline=augment_campaign(code);new=i.augment(code)
        self.assertEqual(i.augment(new),new);self.assertEqual(i.strip(new),baseline)
        for before,after in i.HOOKS:
            with self.assertRaises(ValueError):i.augment(new.replace(after,before,1))
        with self.assertRaises(ValueError):i.augment(new+'\n# unreviewed source change')
    def test_pilot_replaces_one_native_job_and_never_replays(self):
        picked=[dict(id=f'{layer}-{n}',layer=layer,operation='source-window') for layer in ('hiking','terrain','leaf-off') for n in range(4)]
        m=i.manifest();old=copy.deepcopy(picked)
        new,authority=i.select(picked,m['children'],{},True)
        self.assertEqual(picked,old);self.assertEqual(len(new),12);self.assertEqual(new[-1],i.pilot_job())
        self.assertEqual(authority,m)
        for accepted,attempts,enabled in [(m['children'],{},False),(m['children']+[m['job']],{},True),
                                         (m['children'],{m['job']:1},True),(m['children'][:-1],{},True)]:
            self.assertEqual(i.select(picked,accepted,attempts,enabled),(picked,None))
    def test_scope_requires_zero_source_caps_and_four_accepted_children(self):
        m=i.manifest();job=i.pilot_job()
        plan=dict(overviewPilot=m,approvedJobIDs=[m['job']],completedJobIDs=m['children'],priorAttemptCounts={},
                  jobPolicies={m['job']:dict(seconds=600,sourceBytes=0,sourceRequests=0)})
        region=dict(boundsWGS84=m['boundsWGS84'],jobs=[job])
        self.assertEqual(p.validate_scope(plan,region,job),m)
        for field in ('sourceBytes','sourceRequests'):
            bad=copy.deepcopy(plan);bad['jobPolicies'][m['job']][field]=1
            with self.assertRaises(ValueError):p.validate_scope(bad,region,job)
        bad=copy.deepcopy(plan);bad['completedJobIDs']=m['children'][:-1]
        with self.assertRaises(ValueError):p.validate_scope(bad,region,job)
    def test_recovery_requires_both_child_readback_and_independent_parent_match(self):
        proof=synthetic_proof();self.assertEqual(i.validate_verification(proof),proof)
        for field in ('fourChildrenHashAndPixelVerified','independentParentRecomputationMatches','sourceQualityUnchanged'):
            bad=copy.deepcopy(proof);bad[field]=False
            with self.assertRaises(ValueError):i.validate_verification(bad)
        for fault in ('missing','source','recipe','foreign_ref','bad_range'):
            bad=copy.deepcopy(proof);child=bad['childProof']
            if fault=='missing':child['children'].pop()
            if fault=='source':bad['officialSourceRequests']=1
            if fault=='recipe':child['sourceRecipeSHA256']='f'*64
            if fault=='foreign_ref':child['children'][0]['jobReceipt']['key']=child['children'][0]['jobReceipt']['key'].replace(i.manifest()['sourcePlanSHA256'],'f'*64)
            if fault=='bad_range':child['children'][0]['checkpointOffset']=1000
            with self.assertRaises(ValueError):i.validate_verification(bad)
    def test_parent_plan_cannot_omit_or_invent_recovery_proof(self):
        for plan,audit in [(dict(overviewPilot=i.manifest()),{}),({},dict(overviewPilotVerification=synthetic_proof()))]:
            with self.assertRaises(ValueError):i.validate_recovery(plan,audit)
        i.validate_recovery(dict(overviewPilot=i.manifest()),dict(overviewPilotVerification=synthetic_proof()))


class OverviewCheckpointIntegrationTests(unittest.TestCase):
    """Use actual record decoding/range recovery/rendering; only GCS is in memory."""
    def test_bootstrap_then_fresh_recovery_use_real_checkpoint_reader(self):
        sys.path.insert(0,str(SOURCE/'backend/scripts'))
        from gorge_checkpoint import Meter,DIMENSIONS,canonical,digest,encode_record
        from PIL import Image
        from rrgh_verified_overview import render
        objects={}
        def put(key,raw):
            ref=dict(key=key,generation=str(len(objects)+1),bytes=len(raw),sha256=digest(raw))
            objects[key]=raw
            return ref
        def record(key,obj):return put(key,encode_record(obj,2**20,True))
        class Slot:
            def __init__(self):self.meter=Meter(dict.fromkeys(DIMENSIONS,10_000_000))
            def get(self,ref,start=0,length=None):
                raw=objects[ref.key]
                if len(raw)!=ref.bytes or digest(raw)!=ref.sha256:raise ValueError('Immutable read mismatch')
                length=ref.bytes if length is None else length
                self.meter.reserve(classBRequests=1,egressBytes=length+1)
                return raw[start:start+length]
        m=i.manifest();m['sourceJobCount']=4
        prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
        refs=[]
        for n,jid in enumerate(m['children']):
            x,y=map(int,jid.rsplit('-',2)[1:]);path=f'tiles/leaf-on/16/{x}/{y}.png'
            image=Image.new('RGB',(256,256))
            image.putdata([((a+13*n)%256,(b+19*n)%256,(a+b)//2) for b in range(256) for a in range(256)])
            stream=io.BytesIO();image.save(stream,format='PNG');raw=stream.getvalue()
            output=dict(path=path,bytes=len(raw),sha256=digest(raw))
            pack=dict(ref=put(prefix+'slots/00001/outputs/'+digest(raw),raw),members=[dict(output,offset=0)])
            original=dict(job=jid,validated=True,recipeSHA256=m['sourceRecipeSHA256'],outputs=[output])
            refs.append(record(prefix+'slots/00001/jobs/'+jid+'.json',dict(format='rrgh-checkpoint-job-v1',
                planSHA256=m['sourcePlanSHA256'],slot=1,job=jid,result=dict(originalReceipt=original,outputPacks=[pack]))))
        detail=record(prefix+'slots/00001/indexes/details',dict(completedJobReceipts=refs))
        worker=record(prefix+'slots/00001/receipt.json',dict(format='rrgh-slot-receipt-v1',
            planSHA256=m['sourcePlanSHA256'],slot=1,result=dict(status='complete',detailRef=detail)))
        result=dict(status='verified',jobs=4,workerReceipt=worker,detailRef=detail,
            settlement=dict(sequence=m['sourceSequence'],independentRecoveryComplete=True),
            allOutputHashesAndPixelsVerified=True,allNewPackageChunksReadBack=True,allExistingCachesPreserved=True)
        m['recovery']=record(prefix+'slots/00002/receipt.json',dict(format='rrgh-slot-receipt-v1',
            planSHA256=m['sourcePlanSHA256'],slot=2,result=result))
        plan=dict(overviewPilot=m,approvedJobIDs=[m['job']],completedJobIDs=m['children'],priorAttemptCounts={},
            jobPolicies={m['job']:dict(seconds=600,sourceBytes=0,sourceRequests=0)})
        raw=(SOURCE/'backend/config/gorge-campaign-wave-058-20261102/REGION-PLAN.json.z.b64').read_bytes()
        region=json.loads(zlib.decompress(base64.b64decode(raw)));job=p.job_for(m);region['jobs']=[job]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);worker_dir=root/'worker';worker_dir.mkdir()
            before={k:digest(v) for k,v in objects.items()}
            proof=p.read_dependencies(Slot(),plan,region,worker_dir)
            self.assertEqual(len(proof['children']),4)
            rendered=render(region,job,proof['children'],worker_dir,root/'parent',SOURCE)
            original=dict(rendered['receipt'],overviewProof=proof)
            verified=p.verify(Slot(),plan,region,[dict(job=m['job'],result=dict(originalReceipt=original))],root/'recovery',SOURCE)
            self.assertTrue(verified['independentParentRecomputationMatches'])
            self.assertEqual(verified['officialSourceRequests'],0)
            self.assertEqual(before,{k:digest(v) for k,v in objects.items()})
            with self.assertRaises(ValueError):p.read_dependencies(Slot(),plan,region,worker_dir)


if __name__=='__main__':unittest.main()
