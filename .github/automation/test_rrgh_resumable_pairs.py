"""Offline adversarial tests. Fake source outputs never establish live coverage."""
import copy
from dataclasses import asdict
import importlib.util
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rrgh_batch_contract as contract
import rrgh_pair_cache as cache
import rrgh_pair_worker as worker
import rrgh_batch_integration as integration

SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','source-checkout')).resolve()
sys.path.insert(0,str(SOURCE/'backend/scripts'))
import gorge_checkpoint as checkpoint


def policy():
    return dict(format=contract.FORMAT,workers=2,targetJobs=12,stage='pilot12',successfulWaves=0,
                baselineTilesPerSecond=1.,recentTilesPerSecond=[])


def closure(jobs,attempted=None,accepted=None,**extra):
    attempted=jobs if attempted is None else attempted
    accepted=attempted if accepted is None else accepted
    return dict(format=contract.CLOSURE,planSHA256='a'*64,allocationSHA256=contract.sha(jobs),
                attemptedJobIDs=attempted,acceptedJobIDs=accepted,
                quarantinedJobIDs=[j for j in attempted if j not in accepted],
                unattemptedJobIDs=jobs[len(attempted):],allChildrenJoined=True,sourceLedgersMerged=True,
                fallbackRequired=False,stopReason='resource' if len(attempted)<len(jobs) else None,
                producerSeconds=5,childWallSeconds=8,workers=2,**extra)


class ContractTests(unittest.TestCase):
    def test_exact_partition_and_untouched_tail(self):
        c=closure(['a','b','c','d'],['a','b'],['a'])
        self.assertEqual(contract.partition(['a','b','c','d'],c,'a'*64),(['a','b'],['a'],['b'],['c','d']))
    def test_interrupted_reordered_duplicate_and_forged_closures_rejected(self):
        jobs=['a','b','c'];c=closure(jobs,['a','b'],['a'])
        for key,value in [('allChildrenJoined',False),('sourceLedgersMerged',False),
                          ('attemptedJobIDs',['b','a']),('acceptedJobIDs',['a','a']),
                          ('quarantinedJobIDs',[]),('unattemptedJobIDs',['b','c']),
                          ('allocationSHA256','f'*64),('planSHA256','b'*64),('stopReason',None)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                contract.partition(jobs,{**c,key:value},'a'*64)
    def test_outstanding_pair_reservations_precede_either_child(self):
        used=dict(sourceBytes=0,sourceRequests=0,seconds=0,attempts=0)
        p=dict(sourceBytes=50,sourceRequests=2,seconds=600)
        caps=dict(sourceBytes=100,sourceRequests=4,seconds=1200,attempts=2)
        self.assertIsNone(contract.admission(used,caps,[p,p],2000,0,2,0,2**30))
        for key in caps:
            c={**caps,key:caps[key]-1}
            self.assertIn(key,contract.admission(used,c,[p,p],2000,0,2,0,2**30))
        self.assertIn('deadline',contract.admission(used,caps,[p,p],839,0,2,0,2**30))
        self.assertIn('cache',contract.admission(used,caps,[p,p],2000,0,2,2**30,2**30))
        self.assertIn('output',contract.admission(used,caps,[p,p],2000,512*2**20,2,0,2**30))
    def test_two_successful_small_then_two_large_waves(self):
        old={'approvedJobIDs':['a','b']};audit=dict(batchPilotEnabled=True,cycleTilesPerSecond=1.,planSHA256='a'*64)
        p=contract.next_policy(old,audit);self.assertEqual(p['targetJobs'],12)
        audit.update(batchClosure=closure(old['approvedJobIDs']),cycleTilesPerSecond=1.2)
        for stage in ('pilot12','pilot24','pilot24','active24'):
            p=contract.next_policy({**old,'resumableBatch':p},audit)
            self.assertEqual(p['stage'],stage)
        self.assertEqual(p['targetJobs'],24)
    def test_failure_tail_no_gain_and_regression_trigger_fallback(self):
        old={'approvedJobIDs':['a','b'],'resumableBatch':policy()}
        audit=dict(batchPilotEnabled=True,cycleTilesPerSecond=1.2,planSHA256='a'*64,batchClosure=closure(['a','b']))
        for change in ({'fallbackRequired':True}, {'unattemptedJobIDs':['b'],'attemptedJobIDs':['a'],
                         'acceptedJobIDs':['a'],'stopReason':'resource'}):
            self.assertIsNone(contract.next_policy(old,{**audit,'batchClosure':{**audit['batchClosure'],**change}}))
        self.assertIsNone(contract.next_policy(old,{**audit,'cycleTilesPerSecond':.79}))
        p=contract.next_policy(old,{**audit,'cycleTilesPerSecond':.95})
        self.assertIsNone(contract.next_policy({**old,'resumableBatch':p},{**audit,'cycleTilesPerSecond':.99}))
        self.assertIsNone(contract.next_policy(old,{**audit,'batchPilotEnabled':False}))


def init_cache(root):
    (root/'working-cog').mkdir();(root/'working-service').mkdir()
    with sqlite3.connect(root/'working-cog/cache.sqlite') as db:
        db.executescript('CREATE TABLE config(id INTEGER PRIMARY KEY,ceiling INTEGER); INSERT INTO config VALUES(1,1000000000);'
            'CREATE TABLE sources(url TEXT PRIMARY KEY,identity TEXT,metadata TEXT);'
            'CREATE TABLE blocks(identity TEXT,number INTEGER,sha TEXT,bytes INTEGER,PRIMARY KEY(identity,number));'
            'CREATE TABLE transfers(id INTEGER PRIMARY KEY,url TEXT,start INTEGER,end INTEGER,reserved INTEGER,received INTEGER,status TEXT,seconds REAL,error TEXT);')
    with sqlite3.connect(root/'working-service/requests.sqlite') as db:
        db.executescript('CREATE TABLE budget(bytes INTEGER,requests INTEGER);INSERT INTO budget VALUES(1000000,100);'
                        'CREATE TABLE calls(id INTEGER PRIMARY KEY,key TEXT,reserved INTEGER,received INTEGER,status TEXT,seconds REAL);')


def add_range(root,number,identity='a'*64,raw=b'original-pixels'):
    p=root/'working-cog/blocks'/identity/str(number);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    meta=json.dumps(dict(identity=identity,url='pinned-source',etag='etag',length=100000,pinnedAtUTC='fixed'))
    with sqlite3.connect(root/'working-cog/cache.sqlite') as db:
        db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?)',('pinned-source',identity,meta))
        db.execute('INSERT INTO blocks VALUES(?,?,?,?)',(identity,number,checkpoint.digest(raw),len(raw)))
        db.execute('INSERT INTO transfers(url,start,end,reserved,received,status,seconds) VALUES(?,?,?,?,?,?,?)',
                   ('pinned-source',number,number+1,len(raw),len(raw),'complete',.1))


class CacheTests(unittest.TestCase):
    def test_isolated_writers_union_transfers_and_reuse_both_inputs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);init_cache(root);add_range(root,0)
            a=root/'a';b=root/'b';ma=cache.seed(root,a);mb=cache.seed(root,b)
            self.assertFalse(os.path.samefile(root/'working-cog/cache.sqlite',a/'working-cog/cache.sqlite'))
            self.assertTrue(os.path.samefile(root/'working-cog/blocks'/('a'*64)/'0',a/'working-cog/blocks'/('a'*64)/'0'))
            add_range(a,1);add_range(b,2)
            cache.merge(root,a,ma);cache.merge(root,b,mb)
            c=root/'c';cache.seed(root,c)
            with sqlite3.connect(c/'working-cog/cache.sqlite') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transfers').fetchone()[0],3)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM blocks').fetchone()[0],3)
    def test_changed_source_missing_history_or_corrupted_range_fails_closed(self):
        for kind in ('identity','history','range','service'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as t:
                root=Path(t);init_cache(root);add_range(root,0);child=root/'child';marks=cache.seed(root,child)
                if kind=='range':
                    add_range(child,1);(child/'working-cog/blocks'/('a'*64)/'1').write_bytes(b'corrupt')
                else:
                    path=child/('working-service/requests.sqlite' if kind=='service' else 'working-cog/cache.sqlite')
                    with sqlite3.connect(path) as db:
                        db.execute({'identity':"UPDATE sources SET identity='changed'",'history':'DELETE FROM transfers',
                                    'service':'UPDATE budget SET requests=999'}[kind])
                with self.assertRaises(ValueError):cache.merge(root,child,marks)


class MemoryStore:
    def __init__(self):self.objects={};self.serial=0
    def create(self,key,raw):
        if key in self.objects:raise ValueError('Create-only collision')
        self.serial+=1;ref=checkpoint.Ref(key,str(self.serial),len(raw),checkpoint.digest(raw))
        self.objects[key]=(ref,raw);return ref
    def read(self,ref,start,length):
        stored,raw=self.objects[ref.key]
        if stored!=ref:raise ValueError('Generation or hash drift')
        return raw[start:start+length]


class WorkerTests(unittest.TestCase):
    def exercise(self,mode='success',count=4):
        current=re.search(r"CONFIG=SOURCE.parent/'config/([^']+)'",(SOURCE/'backend/scripts/gorge_campaign.py').read_text()).group(1)
        folder=SOURCE/'backend/config'/current/'PLAN.json'
        plan=json.loads(folder.read_bytes());jobs=[f'hiking-16-19000-{100+i}' for i in range(count)]
        plan.update(approvedJobIDs=jobs,slotJobs={'1':jobs},resumableBatch=policy(),completedJobIDs=[])
        plan['campaign']['carry']['priorCompletedJobs']=0
        plan['jobPolicies']={j:dict(sourceBytes=65536,sourceRequests=2,seconds=10) for j in jobs}
        plan['slots'][1]['attempts']=count;plan['limits']['attempts']=count
        if mode=='source-cap':plan['slots'][1]['sourceBytes']=131072
        if mode=='request-cap':plan['slots'][1]['sourceRequests']=4
        if mode=='time-cap':plan['slots'][1]['seconds']=20
        region={'jobs':[dict(id=j,operation='source-window',layer='hiking',outputTiles=[[16,19000,100+i]]) for i,j in enumerate(jobs)]}
        plan['regionPlanSHA256']=checkpoint.digest(checkpoint.canonical(region))
        store=MemoryStore();events=[];active=0;peak=0;lock=threading.Lock();used_inputs=[]
        def bootstrap(slot,p,r,root):
            init_cache(root);(root/'REGION-PLAN.json').write_bytes(checkpoint.canonical(region))
            return {'selectedCOGBytes':0}
        def run_job(proxy,region_path,job,root,cog,service,caps,seconds,growth_cap=None):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            try:
                # Exercise two actual subprocesses without network or credentials.
                subprocess.run([sys.executable,'-c','import time;time.sleep(.03)'],check=True)
                with sqlite3.connect(cog/'cache.sqlite') as db:used_inputs.append((job,db.execute('SELECT COUNT(*) FROM blocks').fetchone()[0]))
                number=jobs.index(job);add_range(root.parent,number)
                if mode in ('failure','consecutive-gaps') and (number==0 or mode=='consecutive-gaps'):
                    usage={'completed':False,'diagnostic':{'failureCode':'SOURCE_PIXEL_GAP' if mode=='consecutive-gaps' else 'UNCLASSIFIED'}}
                    (root/('gate-c-'+job+'.usage.json')).write_text(json.dumps(usage));raise RuntimeError('synthetic child failure')
                return {'job':job,'outputs':[dict(path='synthetic/'+job,bytes=10,sha256='f'*64)],
                    'execution':{'sourceUsage':{'completed':True,'reserved':{'sourceBytes':65536 if mode=='source-cap' else 1,'sourceRequests':2 if mode=='request-cap' else 1},
                                                'actual':{'receivedBodyBytes':1,'operations':1}}}}
            finally:
                with lock:active-=1
        def save(slot,obj):return asdict(slot.put(checkpoint.encode_record(obj,16*2**20,True,128*2**20),'indexes'))
        def load(slot,ref):return checkpoint.decode_record(slot.get(checkpoint.Ref(**ref)),128*2**20)
        def commit(slot,receipt,root):
            if mode=='checkpoint-failure' and receipt['job']==jobs[0]:raise RuntimeError('synthetic unknown write response')
            return slot.commit_job(receipt['job'],{'originalReceipt':receipt,'outputPacks':[]})
        api=dict(Slot=checkpoint.Slot,Meter=checkpoint.Meter,DIMENSIONS=checkpoint.DIMENSIONS,Ref=checkpoint.Ref,
                 PREFIX=checkpoint.PREFIX,canonical=checkpoint.canonical,bootstrap=bootstrap,run_job=run_job,
                 save_large=save,load_large=load,signal=lambda *a:None,emit=lambda **kw:events.append(kw),
                 state_snapshot=lambda root:{'testOnly':True},checkpoint_job=commit,
                 is_verified_original_pixel_gap=lambda child:bool(child and child['diagnostic']['failureCode']=='SOURCE_PIXEL_GAP'),
                 WORKING_CACHE_CAP=6*2**30,TILE_CAP=512*1024)
        opener=SimpleNamespace(deadline=None,summary=lambda:{})
        identity=SimpleNamespace(require_owner=lambda *a:None)
        with tempfile.TemporaryDirectory() as t,patch.dict(sys.modules,{'gorge_producer_identity':identity}):
            worker.produce(plan,{},region,Path(t),store,opener,'offline-test',api)
        final=events[-1];closed=checkpoint.decode_record(store.objects[final['receiptRef']['key']][1])
        recovery=checkpoint.Slot(store,plan,2,'independent-offline-test')
        detail=load(recovery,closed['result']['detailRef'])
        records=[checkpoint.decode_record(store.objects[r['key']][1]) for r in detail['completedJobReceipts']]
        proof=worker.verify_closure(recovery,plan,detail,records,closed,api)
        return plan,proof,peak,used_inputs,detail,closed,records,recovery,api
    def test_two_processes_and_next_pair_reuses_both_prior_inputs(self):
        plan,p,peak,inputs,*_=self.exercise()
        self.assertEqual(peak,2);self.assertEqual(p['acceptedJobIDs'],plan['approvedJobIDs'])
        self.assertEqual([n for j,n in inputs[:2]],[0,0]);self.assertEqual([n for j,n in inputs[2:]],[2,2])
    def test_child_failure_and_checkpoint_failure_preserve_peer_then_fallback(self):
        for mode in ('failure','checkpoint-failure'):
            plan,p,*_=self.exercise(mode)
            self.assertEqual(p['acceptedJobIDs'],plan['approvedJobIDs'][1:2])
            self.assertEqual(p['quarantinedJobIDs'],plan['approvedJobIDs'][:1])
            self.assertEqual(p['unattemptedJobIDs'],plan['approvedJobIDs'][2:]);self.assertTrue(p['fallbackRequired'])
    def test_consecutive_source_failures_consume_pair_and_leave_tail(self):
        plan,p,*_=self.exercise('consecutive-gaps')
        self.assertEqual(p['quarantinedJobIDs'],plan['approvedJobIDs'][:2]);self.assertTrue(p['fallbackRequired'])
    def test_source_request_and_time_resource_exits_close_safely(self):
        for mode in ('source-cap','request-cap','time-cap'):
            plan,p,*_=self.exercise(mode)
            self.assertTrue(p['stopReason']);self.assertTrue(p['unattemptedJobIDs'])
            self.assertFalse(set(p['attemptedJobIDs'])&set(p['unattemptedJobIDs']))
    def test_independent_recovery_rejects_changed_attempt_charge_or_output_set(self):
        plan,p,peak,inputs,detail,closed,records,recovery,api=self.exercise('failure')
        for field in ('attempt','charge','output','completion','checkpoint'):
            d=copy.deepcopy(detail);w=copy.deepcopy(closed);r=copy.deepcopy(records)
            if field=='attempt':d['batchAttempts'].pop()
            elif field=='charge':w['used']['sourceBytes']-=1
            elif field=='output':r=[]
            elif field=='completion':r[0]['result']['originalReceipt']['execution']['sourceUsage']['completed']=False
            else:d['batchAttempts'][1]['jobReceipt']['sha256']='a'*64
            with self.assertRaises(ValueError):worker.verify_closure(recovery,plan,d,r,w,api)
    def test_duplicate_cloud_claim_never_replays_source(self):
        plan,*_=self.exercise()
        store=MemoryStore();checkpoint.Slot(store,plan,1,'one')
        with self.assertRaises(ValueError):checkpoint.Slot(store,plan,1,'two')


class IntegrationTests(unittest.TestCase):
    def test_exact_hooks_idempotent_and_partial_hooks_rejected(self):
        code=(SOURCE/'backend/scripts/gorge_campaign.py').read_text()
        changed=integration.augment(code)
        self.assertEqual(integration.augment(changed),changed)
        self.assertEqual(integration.strip(changed),code)
        with self.assertRaises(ValueError):integration.strip(changed.replace('batch_proof=verify_closure','tampered=verify_closure'))


if __name__=='__main__':unittest.main()
