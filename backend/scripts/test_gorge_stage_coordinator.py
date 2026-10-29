"""New boundary tests for the authorized coordinator; no source/cloud traffic."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.request import Request

import gorge_stage_inputs as inputs
import gorge_stage_coordinator as stage
from gorge_checkpoint import Meter, canonical, DIMENSIONS, digest
from gorge_guarded_worker import SourceOpener

class Response(io.BytesIO):
    def __init__(self,raw,url,headers=None):super().__init__(raw);self.url=url;self.headers=headers or {};self.status=200
    def geturl(self):return self.url

class CoordinatorTests(unittest.TestCase):
    def test_configuration_retains_exact_limits_and_job_set(self):
        p,e,r=stage.configuration()
        self.assertEqual(len(p['approvedJobIDs']),12)
        self.assertEqual(sum(s['storedBytes'] for s in p['slots']),2**30)
        self.assertEqual(sum(s['egressBytes'] for s in p['slots']),2**30)
        self.assertEqual(sum(s['classARequests'] for s in p['slots']),200)
        self.assertEqual(sum(s['classBRequests'] for s in p['slots']),500)
        self.assertEqual(e['stageRelease']['lockedUSD'],'7.65')
        self.assertEqual(e['stageRelease']['releasedUSD'],'.35')
    def test_growth_reservation_precedes_source_open(self):
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(sourceBytes=1000000,sourceRequests=2,storedBytes=65536,seconds=60)
        m=Meter(caps);calls=[];opener=SourceOpener(m,lambda *a,**kw:calls.append(a))
        req=Request('https://prd-tnm.s3.amazonaws.com/data/test.tif',headers={'Range':'bytes=0-65535'})
        with self.assertRaisesRegex(ValueError,'storedBytes'):opener(req)
        self.assertEqual(calls,[]);self.assertEqual(m.used['sourceRequests'],0)
    def test_cumulative_growth_stops_second_request(self):
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(sourceBytes=100000,sourceRequests=2,storedBytes=10000,seconds=60)
        m=Meter(caps);calls=[]
        def open_(req,**kw):calls.append(req);return Response(b'1',req.full_url)
        opener=SourceOpener(m,open_);req=Request('https://prd-tnm.s3.amazonaws.com/data/test.tif',headers={'Range':'bytes=0-0'})
        opener(req)
        with self.assertRaises(ValueError):opener(req)
        self.assertEqual(len(calls),1);self.assertEqual(m.used['storedBytes'],8193)
    def test_base_generation_and_hash_are_verified(self):
        raw=b'accepted base fixture';sha=digest(raw);calls=[]
        caps=dict.fromkeys(DIMENSIONS,0);caps.update(classBRequests=2,egressBytes=20000,seconds=60)
        def open_(req,**kwargs):
            calls.append(req.full_url)
            if len(calls)==1:
                return Response(canonical({'bucket':inputs.BUCKET,'name':inputs.BASE_KEY,'generation':'123','size':str(len(raw)),
                    'md5Hash':base64.b64encode(hashlib.md5(raw).digest()).decode()}),req.full_url)
            self.assertIn('generation=123',req.full_url);self.assertIn('ifGenerationMatch=123',req.full_url)
            return Response(raw,req.full_url,{'x-goog-generation':'123'})
        slot=SimpleNamespace(meter=Meter(caps),store=SimpleNamespace(opener=open_,token_provider=lambda:'fixture'))
        with tempfile.TemporaryDirectory() as td,patch.object(inputs,'BASE_BYTES',len(raw)),patch.object(inputs,'BASE_SHA',sha):
            ref=inputs.base_read(slot,Path(td)/'base');self.assertEqual(ref['generation'],'123')
            self.assertEqual((Path(td)/'base').read_bytes(),raw)
        self.assertEqual(slot.meter.used['classBRequests'],2)
    def test_base_excess_read_never_starts(self):
        calls=[];caps=dict.fromkeys(DIMENSIONS,0);caps.update(seconds=60,classBRequests=1,egressBytes=2**30)
        slot=SimpleNamespace(meter=Meter(caps),store=SimpleNamespace(opener=lambda *a,**k:calls.append(a)))
        with self.assertRaises(ValueError):inputs.base_read(slot,'unused')
        self.assertEqual(calls,[])
    def test_extract_inputs_ignores_legacy_raster_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);raw=canonical({'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[0,0]},'properties':{}}]})
            weather=canonical({'files':[]});m={'packageID':'gorge-base','packageVersion':'2026.10.08.1','vectors':[{'id':'fixture','path':'v.geojson','sha256':digest(raw)}],
                'weatherManifest':{'path':'w.json','sha256':digest(weather)},'staticAssets':[]}
            payloads=[('NATIVE-MAP.json',canonical(m)),('v.geojson',raw),('w.json',weather),('legacy.png',b'not reused')]
            with tarfile.open(root/'base','w') as tar:
                for name,body in payloads:
                    info=tarfile.TarInfo(name);info.size=len(body);tar.addfile(info,io.BytesIO(body))
            result=inputs.extract_base_inputs(root/'base',root/'inputs')
            self.assertEqual(result['vectorFeatures'],1);self.assertFalse((root/'inputs/legacy.png').exists())
            with tarfile.open(root/'base','a') as tar:
                info=tarfile.TarInfo('v.geojson');info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
            with self.assertRaisesRegex(ValueError,'Duplicate'):inputs.extract_base_inputs(root/'base',root/'bad')
    def test_cache_delta_skips_preserved_blocks_and_keeps_closed_ledgers(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);cog=root/'cog';service=root/'service';(cog/'blocks/a').mkdir(parents=True);service.mkdir()
            (cog/'blocks/a/0').write_bytes(b'old');(cog/'blocks/a/1').write_bytes(b'new')
            (service/'new.bin').write_bytes(b'data')
            for path in [cog/'cache.sqlite',service/'requests.sqlite']:
                with sqlite3.connect(path) as db:db.execute('CREATE TABLE example(x)');db.execute('INSERT INTO example VALUES (1)')
            entries,names,used=stage.snapshot_cache(cog,service,root/'delta','job',{'cog/blocks/a/0'},0)
            self.assertNotIn('cog/blocks/a/0',names);self.assertIn('cog/blocks/a/1',names)
            self.assertEqual(len([e for e in entries if e['path'].startswith('state/')]),2)
            self.assertGreater(used,0)
    def test_source_pin_change_fails_before_credential(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for p in stage.CONFIG.iterdir(): (root/p.name).write_bytes(p.read_bytes())
            plan=json.loads((root/'PLAN.json').read_bytes());plan['sourceSnapshotSHA256']='0'*64
            (root/'PLAN.json').write_bytes(canonical(plan))
            with self.assertRaises(ValueError):stage.configuration(root)

class OutputRecoveryTests(unittest.TestCase):
    def fixture(self, root):
        from PIL import Image
        im=Image.new('RGB',(256,256));im.putdata([(x%256,y%256,(x+y)%256) for y in range(256) for x in range(256)])
        target=root/'new/tiles/hiking/16/2/2.jpg';target.parent.mkdir(parents=True);im.save(target,quality=90)
        prior=root/'base/prior/tiles/hiking/16/1/2.jpg';prior.parent.mkdir(parents=True);im.save(prior,quality=90)
        region={'jobs':[{'id':'fixture','outputTiles':[[16,2,2]]}]};plan={'approvedJobIDs':['fixture']}
        entry={'path':'tiles/hiking/16/2/2.jpg','bytes':target.stat().st_size,'sha256':digest(target.read_bytes())}
        record={'result':{'originalReceipt':{'job':'fixture','validated':True,'recipeSHA256':digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode()),'outputs':[entry]}}}
        return plan,region,[record],target
    def test_new_to_preserved_edge_is_measured(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,r,records,_=self.fixture(root)
            qa=stage.verify_outputs(p,r,records,root/'new',root/'base')
            self.assertEqual(qa['files'],1);self.assertEqual(qa['adjacentEdgesMeasured'],1)
            self.assertTrue(qa['allExpectedTilesPresent'])
    def test_corrupt_recovered_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p,r,records,target=self.fixture(root);target.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):stage.verify_outputs(p,r,records,root/'new')

if __name__=='__main__':unittest.main()
