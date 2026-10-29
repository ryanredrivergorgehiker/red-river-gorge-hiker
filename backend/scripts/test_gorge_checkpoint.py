import base64
import hashlib
import copy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs,urlparse
from urllib.request import Request

from gorge_checkpoint import (BUCKET, PREFIX, DIMENSIONS, GCS, MAX_RECEIPT, Meter,
    Ref, Slot, canonical, digest, pack_delta, recover_members, require_live_allowance, validate_plan)
from gorge_guarded_worker import SourceOpener, run_job


class DiskStore:
    """Test-only create-exclusive persistent store; independent instances share disk."""
    def __init__(self,root):self.root=Path(root);self.reads=[];self.creates=0
    def create(self,key,raw):
        self.creates+=1;p=self.root/key;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f:f.write(raw)
        return Ref(key,str(p.stat().st_ino),len(raw),digest(raw))
    def read(self,ref,start=0,length=None):
        p=self.root/ref.key
        if str(p.stat().st_ino)!=ref.generation:raise ValueError('Generation changed')
        raw=p.read_bytes()
        if digest(raw)!=ref.sha256:raise ValueError('Corruption')
        length=len(raw) if length is None else length;self.reads.append((ref.key,start,length))
        return raw[start:start+length]
    def receipt(self,key,before_media):
        p=self.root/key;raw=p.read_bytes();ref=Ref(key,str(p.stat().st_ino),len(raw),digest(raw));before_media(len(raw))
        return ref,self.read(ref)


def plan():
    caps=dict(storedBytes=10_000_000,egressBytes=10_000_000,classARequests=10,
              classBRequests=20,sourceBytes=10_000_000,sourceRequests=20,seconds=60,attempts=2)
    return {'format':'rrgh-checkpoint-plan-v1','bucket':BUCKET,
        'deleteAllowed':False,'bulkProductionEnabled':False,
        'expiresAt':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        'sourceSnapshotSHA256':'1'*64,'slots':[caps.copy(),caps.copy(),caps.copy()],
        'limits':{k:v*3 for k,v in caps.items()}}


def allowance(p):
    return {'cloudStorageAllowance':{'approvedUSD':1,'approvalReference':'TEST ONLY',
        'planSHA256':digest(canonical(p)),'reservedWorstCaseUSD':1,
        'ongoingStorageAcknowledged':True,'chargedRetentionMonths':1,
        'approvedRecurringStorageUSDPerMonth':1},
        'planningRates':{'storageUSDPerGiBMonth':.03,'egressUSDPerGiB':.23,
                         'classAUSDPer1000':.01,'classBUSDPer1000':.001},
        'github':{'hardCeilingUSD':350,'stopAtLimitVerified':True}}


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.p=plan()
        self.store=DiskStore(self.root/'objects')
    def tearDown(self):self.temp.cleanup()

    def test_crash_claim_survives_fresh_process_and_cannot_refund(self):
        first=Slot(self.store,self.p,0,'run1');first.meter.reserve(sourceBytes=700)
        with self.assertRaises(FileExistsError):Slot(DiskStore(self.store.root),self.p,0,'run2')
        second=Slot(DiskStore(self.store.root),self.p,1,'run2')
        self.assertEqual(validate_plan(self.p)['sourceBytes'],30_000_000)
        self.assertEqual(second.meter.caps['sourceBytes'],10_000_000)

    def test_concurrent_claim_has_only_one_winner(self):
        results=[]
        def claim():
            try:Slot(DiskStore(self.store.root),self.p,0,'race');results.append('won')
            except FileExistsError:results.append('lost')
        threads=[threading.Thread(target=claim) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(results,['won','lost'])

    def test_ambiguous_create_is_not_retried(self):
        original=self.store.create
        def ambiguous(k,b):original(k,b);raise TimeoutError('connection lost after commit')
        self.store.create=ambiguous
        with self.assertRaises(TimeoutError):Slot(self.store,self.p,0,'run')
        self.store.create=original
        with self.assertRaises(FileExistsError):Slot(self.store,self.p,0,'retry')

    def test_cost_ceiling_checked_before_object_write(self):
        slot=Slot(self.store,self.p,0,'run');slot.meter.caps['storedBytes']=slot.meter.used['storedBytes']
        before=self.store.creates
        with self.assertRaises(ValueError):slot.put(b'a')
        self.assertEqual(self.store.creates,before)

    def test_generation_hash_and_private_scope_enforced(self):
        slot=Slot(self.store,self.p,0,'run');ref=slot.put(b'original')
        bad=Ref(ref.key,str(int(ref.generation)+1),ref.bytes,ref.sha256)
        with self.assertRaises(ValueError):slot.get(bad)
        (self.store.root/ref.key).write_bytes(b'changed!')
        with self.assertRaises(ValueError):slot.get(ref)
        for key in ['packages/offline/accepted','engineering/map-production/../secret']:
            with self.assertRaises(ValueError):Ref(key,'1',1,'0'*64)

    def test_packed_delta_selective_fresh_runner_recovery(self):
        source=self.root/'source';source.mkdir();entries=[]
        for name,raw in [('needed',b'a'*1024),('not-needed',b'b'*4096),('already-saved',b'c'*512)]:
            (source/name).write_bytes(raw);entries.append({'path':name,'bytes':len(raw),'sha256':digest(raw)})
        writer=Slot(self.store,self.p,0,'producer');manifest=[]
        for raw,meta in pack_delta(source,entries,{entries[2]['sha256']}):
            manifest.append({'ref':asdict(writer.put(raw)), 'members':meta['members']})
        final=writer.finish({'packs':manifest})
        reader=Slot(DiskStore(self.store.root),self.p,1,'fresh-runner')
        found,result=reader.recover_receipt(0)
        self.assertEqual(found,final)
        result=recover_members(reader,result['result']['packs'],{'needed'},self.root/'recovered')
        self.assertEqual(result,{'files':1,'recoveredBytes':1024})
        self.assertEqual((self.root/'recovered/needed').read_bytes(),b'a'*1024)
        self.assertFalse((self.root/'recovered/not-needed').exists())
        self.assertEqual(reader.store.reads[-1][2],1024)

    def test_cache_corruption_fails_without_network(self):
        source=self.root/'src';source.mkdir();(source/'a').write_bytes(b'wrong')
        with self.assertRaises(ValueError):list(pack_delta(source,[{'path':'a','bytes':5,'sha256':digest(b'right')}]))
        self.assertEqual(self.store.creates,0)

    def test_pack_boundary_is_bounded_and_members_do_not_split(self):
        source=self.root/'src';source.mkdir();entries=[]
        for i in range(3):
            raw=bytes([i])*7;(source/str(i)).write_bytes(raw)
            entries.append({'path':str(i),'bytes':7,'sha256':digest(raw)})
        packs=list(pack_delta(source,entries,maximum=14))
        self.assertEqual([len(raw) for raw,_ in packs],[14,7])

    def test_missing_member_does_not_read_or_publish(self):
        slot=Slot(self.store,self.p,0,'run')
        with self.assertRaises(ValueError):recover_members(slot,[],{'missing'},self.root/'out')
        self.assertEqual(self.store.reads,[]);self.assertFalse((self.root/'out').exists())

    def test_expired_changed_or_overallocated_plan_fails(self):
        for kind in ('expired','over','bulk'):
            p=copy.deepcopy(self.p)
            if kind=='expired':p['expiresAt']='2020-01-01T00:00:00+00:00'
            elif kind=='over':p['limits']['sourceBytes']=1
            else:p['bulkProductionEnabled']=True
            with self.assertRaises(ValueError):Slot(self.store,p,0,'run')
        self.assertEqual(self.store.creates,0)

    def test_trial_credit_is_not_allowance_and_no_credential_lookup(self):
        tokens=[]
        with self.assertRaises(ValueError):GCS(self.p,{'trialCreditUSD':300.00},lambda:tokens.append('looked'))
        self.assertEqual(tokens,[])
        e=allowance(self.p);e['cloudStorageAllowance']['planSHA256']='0'*64
        with self.assertRaises(ValueError):require_live_allowance(self.p,e)

    def test_underfunded_or_missing_recurring_storage_rejected(self):
        for key,value in [('reservedWorstCaseUSD',.000001),('approvedRecurringStorageUSDPerMonth',0)]:
            e=allowance(self.p);e['cloudStorageAllowance'][key]=value
            with self.assertRaises(ValueError):require_live_allowance(self.p,e)

    def test_completed_jobs_and_third_attempt_are_rejected(self):
        p=copy.deepcopy(self.p);p['slotJobs']={'0':['done']};p['completedJobIDs']=['done']
        with self.assertRaises(ValueError):validate_plan(p)
        p=copy.deepcopy(self.p);p['slotJobs']={str(i):['same'] for i in range(3)}
        with self.assertRaises(ValueError):validate_plan(p)

    def test_source_budget_rejects_before_network(self):
        caps=self.p['slots'][0].copy();caps['sourceBytes']=100;meter=Meter(caps);calls=[]
        opener=SourceOpener(meter,lambda *args,**kw:calls.append('called'))
        req=Request('https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/16/1/1')
        with self.assertRaises(ValueError):opener(req)
        self.assertEqual(calls,[])

    def test_source_host_rejected_before_network(self):
        meter=Meter(self.p['slots'][0]);calls=[]
        opener=SourceOpener(meter,lambda *a,**k:calls.append(1))
        with self.assertRaises(ValueError):opener(Request('https://example.com/data'))
        self.assertEqual(calls,[])

    def test_job_receipt_survives_crash_before_final_slot_receipt(self):
        p=copy.deepcopy(self.p);p['slotJobs']={'0':['hiking-16-1-1']}
        first=Slot(self.store,p,0,'producer')
        saved=first.commit_job('hiking-16-1-1',{'output':'verified fixture'})
        # Deliberately no finish(): simulate interruption after a completed job.
        fresh=Slot(DiskStore(self.store.root),p,1,'fresh')
        ref,record=fresh.recover_job(0,'hiking-16-1-1')
        self.assertEqual(ref,saved);self.assertEqual(record['result']['output'],'verified fixture')
        self.assertFalse((self.store.root/(first.prefix+'slots/00000/receipt.json')).exists())

    def test_job_output_tamper_is_rejected_before_checkpoint(self):
        from gorge_guarded_worker import validate_receipt
        root=self.root/'job';(root/'receipts').mkdir(parents=True);(root/'tile').write_bytes(b'wrong')
        region={'jobs':[]};r={'validated':True,'job':'x',
            'recipeSHA256':digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode()),
            'outputs':[{'path':'tile','bytes':5,'sha256':digest(b'right')}]}
        (root/'receipts/x.json').write_bytes(canonical(r))
        with self.assertRaises(ValueError):validate_receipt(region,'x',root)
        self.assertEqual(self.store.creates,0)

    def test_driver_default_preflight_checks_code_and_plan_pins(self):
        from run_gorge_checkpoint_slot import code_snapshot,preflight
        source=self.root/'scripts';source.mkdir();(source/'engine.py').write_text('#fixture')
        region={'format':'rrgh-region-plan-v1','jobs':[{'id':'x'}],
                'engineHashes':{'engine.py':digest((source/'engine.py').read_bytes())}}
        p=copy.deepcopy(self.p);p['regionPlanSHA256']=digest(canonical(region))
        p['sourceSnapshotSHA256']=code_snapshot(source);p['slotJobs']={'0':['x']}
        self.assertEqual(preflight(p,region,source)['attempts'],6)
        (source/'engine.py').write_text('#changed')
        with self.assertRaises(ValueError):preflight(p,region,source)
        self.assertEqual(self.store.creates,0)

    def test_selected_cache_ledger_survives_fresh_runner_without_reset(self):
        from cached_cog_source import Cache, atomic
        from gorge_cache_selection import select_cog_cache, seed_selected_cog
        root=self.root/'cache';c=Cache(root,limit=1000000)
        url='https://prd-tnm.s3.amazonaws.com/data/test.tif';etag='"fixture"';length=200000
        identity=digest(json.dumps([url,etag,length]).encode())
        meta={'url':url,'etag':etag,'length':length,'identity':identity}
        c.db.execute('INSERT INTO sources VALUES (?,?,?)',(url,identity,json.dumps(meta)))
        for n,raw in [(0,b'a'*65536),(1,b'b'*65536)]:
            atomic(root/f'blocks/{identity}/{n}',raw)
            c.db.execute('INSERT INTO blocks VALUES (?,?,?,?)',(identity,n,digest(raw),len(raw)))
        c.db.execute("INSERT INTO transfers(url,start,end,reserved,received,status) VALUES (?,0,131071,131072,131072,'complete')",(url,))
        c.db.commit();c.close();before=(root/'cache.sqlite').read_bytes()
        selection=select_cog_cache(root,[(identity,1)])
        self.assertEqual((root/'cache.sqlite').read_bytes(),before)
        self.assertEqual(selection['originRequestsReservedReceived'],(1,131072,131072))
        slot=Slot(self.store,self.p,0,'producer');manifest=[]
        for raw,info in pack_delta(root,selection['entries']):
            manifest.append({'ref':asdict(slot.put(raw)),'members':info['members']})
        receipt=slot.finish({'manifest':manifest,'selection':selection})
        fresh=Slot(DiskStore(self.store.root),self.p,1,'recovery')
        _,r=fresh.recover_receipt(0);result=r['result']
        paths={e['path'] for e in result['selection']['entries']}
        recover_members(fresh,result['manifest'],paths,self.root/'recovered-cache')
        seed_selected_cog(result['selection'],self.root/'recovered-cache',self.root/'new-cache',500000)
        c=Cache(self.root/'new-cache',limit=500000)
        self.assertEqual(c.read(meta,65536,131071),b'b'*65536)
        self.assertEqual(c.metrics()['requests'],0);c.close()
        self.assertFalse((self.root/'new-cache'/f'blocks/{identity}/0').exists())
        self.assertEqual((root/'cache.sqlite').read_bytes(),before)

    def test_gcs_wire_uses_create_precondition_and_pinned_ranges(self):
        calls=[];payload=b'abcdefghij';ref=None
        class Response(io.BytesIO):
            status=200
            def geturl(self):return self.url
        def opening(req,timeout):
            nonlocal ref
            q=parse_qs(urlparse(req.full_url).query);calls.append((req,q))
            if req.method=='POST':
                self.assertEqual(q['ifGenerationMatch'],['0'])
                obj={'bucket':BUCKET,'name':q['name'][0],'generation':'1234567890','size':str(len(req.data)),
                     'md5Hash':base64.b64encode(hashlib.md5(req.data).digest()).decode()}
                r=Response(json.dumps(obj).encode());r.headers={}
            else:
                self.assertEqual(q['generation'],['1234567890']);self.assertEqual(q['ifGenerationMatch'],['1234567890'])
                self.assertEqual(req.get_header('Range'),'bytes=2-4')
                r=Response(b'cde');r.status=206;r.headers={'x-goog-generation':'1234567890','Content-Range':'bytes 2-4/10'}
            r.url=req.full_url;return r
        gcs=GCS(self.p,allowance(self.p),lambda:'TEST-TOKEN',opener=opening)
        ref=gcs.create(PREFIX+'plans/'+digest(canonical(self.p))+'/fixture',payload)
        self.assertEqual(gcs.read(ref,2,3),b'cde');self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
