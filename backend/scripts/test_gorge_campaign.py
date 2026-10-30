"""New campaign safeguards plus local genuine-output recovery replay (no render)."""
import copy,io,json,os,sqlite3,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from dataclasses import asdict
from gorge_checkpoint import Slot,Ref,Meter,canonical,digest,decode_record,DIMENSIONS,PREFIX
import gorge_campaign as controller
from gorge_campaign_budget import admit,cost,settle,monthly

class MemoryStore:
    def __init__(self):self.data={};self.refs={};self.plan_prefix='';self.requests=[]
    def create(self,key,raw):
        if key in self.data:raise RuntimeError('GCS HTTP 412')
        r=Ref(key,str(len(self.data)+1),len(raw),digest(raw));self.data[key]=raw;self.refs[key]=r;self.requests.append(('write',len(raw)));return r
    def read(self,ref,start=0,length=None):
        if self.refs[ref.key]!=ref:raise ValueError('Generation changed')
        b=self.data[ref.key];self.requests.append(('read',len(b) if length is None else length));return b[start:] if length is None else b[start:start+length]
    def receipt(self,key,before_media):
        r=self.refs[key];before_media(r.bytes);return r,self.read(r)
    def _request(self,method,key,query,maximum,data=None):
        import base64,hashlib
        assert query['ifGenerationMatch']=='0'
        r=self.create(key,data)
        return canonical({'bucket':'rrgh-nonproduction-protected-packages','name':key,'generation':r.generation,'size':len(data),'md5Hash':base64.b64encode(hashlib.md5(data,usedforsecurity=False).digest()).decode()}),{},200

class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan,cls.evidence,cls.region=controller.configuration()
    def test_campaign_retains_history_and_recovery_reserve(self):
        p=copy.deepcopy(self.plan);e=copy.deepcopy(self.evidence)
        p['campaign']['carry']['chargedUSD']='22.99';p['campaign']['sequence']=1;p['campaign']['previousRecovery']={'proof':'placeholder'}
        e['cloudStorageAllowance']['planSHA256']=digest(canonical(p))
        with self.assertRaises(ValueError):admit(p,e)
    def test_monthly_growth_stops_before_network(self):
        p=copy.deepcopy(self.plan);e=copy.deepcopy(self.evidence);p['campaign']['sequence']=1;p['campaign']['previousRecovery']={'proof':'placeholder'}
        p['campaign']['carry']['storedBytes']=28*2**30;e['cloudStorageAllowance']['planSHA256']=digest(canonical(p))
        with self.assertRaises(ValueError):admit(p,e)
    def test_ambiguous_wave_retains_whole_allocation(self):
        small=dict.fromkeys(DIMENSIONS,0);r=settle(self.plan,small,False)
        self.assertEqual(r['retainedUsage'],self.plan['limits']);self.assertFalse(any(r['demonstrablyUnused'].values()))
    def test_confirmed_settlement_is_new_record_without_mutation(self):
        before=canonical(self.plan);used={k:min(v,100) for k,v in self.plan['limits'].items()};r=settle(self.plan,used,True)
        self.assertEqual(canonical(self.plan),before);self.assertEqual(r['retainedUsage'],used);self.assertEqual(r['historicalReleasedUSDRetained'],'0.70')
    def test_wave_fence_rejects_parallel_or_revised_duplicate(self):
        store=MemoryStore();slot=Slot(store,self.plan,0,'test')
        key=PREFIX+'campaigns/test/wave-00000.json'
        controller.create_fence(slot,key,{'plan':'a'})
        with self.assertRaises(RuntimeError):controller.create_fence(slot,key,{'plan':'b'})
    def test_two_generation_pinned_cache_deltas_merge_without_overwrite(self):
        store=MemoryStore();slot=Slot(store,self.plan,0,'test')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'first';second=root/'second'
            for dest,entries in [(first,{'cog/old':b'old-cache','service/meta':b'same'}),(second,{'cog/new':b'new-cache','service/meta':b'same'})]:
                catalogs=[]
                for path,raw in entries.items():
                    ref=slot.put(raw)
                    catalogs.append({'ref':asdict(ref),'members':[{'path':path,'offset':0,'bytes':len(raw),'sha256':digest(raw)}]})
                controller.recover_catalogs(slot,catalogs,list(entries),dest)
            controller.merge_recovered(second,first)
            self.assertEqual((first/'cog/old').read_bytes(),b'old-cache');self.assertEqual((first/'cog/new').read_bytes(),b'new-cache')
            third=root/'third';third.mkdir();(third/'cog').mkdir();(third/'cog/old').write_bytes(b'conflict')
            with self.assertRaises(ValueError):controller.merge_recovered(third,first)
            self.assertEqual((first/'cog/old').read_bytes(),b'old-cache')
    def test_large_metadata_survives_full_slot_handoff(self):
        store=MemoryStore();slot=Slot(store,self.plan,1,'test')
        obj={'refs':[{'key':str(n),'sha':digest(str(n).encode())} for n in range(512)]}
        ref=controller.save_large(slot,obj);slot.finish({'detailRef':ref})
        fresh=Slot(store,self.plan,2,'independent');_,receipt=fresh.recover_receipt(1)
        self.assertEqual(controller.load_large(fresh,receipt['result']['detailRef']),obj)
    def test_successful_child_records_actual_and_unused_without_debit_reset(self):
        store=MemoryStore();slot=Slot(store,self.plan,1,'test');job=self.plan['approvedJobIDs'][0]
        fake={'execution':{'sourceUsage':{'reserved':{'sourceBytes':65536,'sourceRequests':1}}},'outputs':[]}
        with patch.object(controller,'run_job',return_value=fake):
            result=controller.bounded_child(slot,self.plan,Path('unused'),job,Path('unused'))
        self.assertEqual(slot.meter.used['attempts'],1);self.assertEqual(slot.meter.used['sourceBytes'],65536)
        self.assertGreater(result['campaignReservation']['confirmedUnused']['sourceBytes'],0)
        self.assertTrue(result['campaignReservation']['ref']['generation'])
    def test_failed_child_charges_full_reservation(self):
        store=MemoryStore();slot=Slot(store,self.plan,1,'test');job=self.plan['approvedJobIDs'][0]
        with patch.object(controller,'run_job',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):controller.bounded_child(slot,self.plan,Path('unused'),job,Path('unused'))
        self.assertEqual(slot.meter.used['sourceBytes'],self.plan['jobPolicies'][job]['sourceBytes'])
        self.assertEqual(slot.meter.used['seconds'],600)
    def test_actual_worker_handoff_uses_parent_admission_deadline(self):
        store=MemoryStore();slot=Slot(store,self.plan,1,'test');job=self.plan['approvedJobIDs'][0]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=root/'region.json';path.write_bytes(canonical(self.region))
            def completed_child(args,**kwargs):
                ticket=Path(args[-1]);ticket.with_suffix('.usage.json').write_text(json.dumps({'completed':True,'reserved':{'sourceBytes':0,'sourceRequests':0}}))
                return SimpleNamespace(returncode=0)
            with patch('gorge_guarded_worker.subprocess.run',side_effect=completed_child),patch('gorge_guarded_worker.validate_receipt',return_value={'outputs':[]}):
                receipt=controller.bounded_child(slot,self.plan,path,job,root)
            self.assertEqual(slot.meter.used['attempts'],1);self.assertEqual(slot.meter.used['sourceBytes'],0)
            self.assertEqual(receipt['execution']['sourceUsage']['reserved']['sourceRequests'],0)
    def test_512_job_scope_preserves_every_old_job(self):
        self.assertEqual(len(self.plan['approvedJobIDs']),512)
        self.assertFalse(set(self.plan['approvedJobIDs'])&set(self.plan['completedJobIDs']))
        self.assertEqual(sum(len(j['outputTiles']) for j in self.region['jobs']),5448)
    def test_local_genuine_output_checkpoint_recovery_and_assembly(self):
        workspace=os.environ.get('RRGH_PRESERVED_WORKSPACE')
        if not workspace:self.skipTest('Requires explicitly supplied local genuine preserved output')
        files=[]
        for base in ['benchmark/v2','benchmark2/final-services']:
            for layer in ['hiking','terrain','leaf-off','leaf-on','usgs-topo']:
                matches=list((Path(workspace)/base/'tiles'/layer/'16').glob('*/*'))
                if matches and not any(x[0]==layer for x in files):files.append((layer,matches[0]))
        self.assertGreaterEqual(len(files),4)
        plan=copy.deepcopy(self.plan);region=copy.deepcopy(self.region);region['jobs']=[];records=[]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);worker=root/'worker';recovery=root/'recovered';worker.mkdir();recovery.mkdir()
            for layer,p in files:
                x=int(p.parent.name);y=int(p.stem);job=f'{layer}-16-{x}-{y}'
                region['jobs'].append({'id':job,'layer':layer,'outputTiles':[[16,x,y]],'operation':'source-window'})
            plan['approvedJobIDs']=[j['id'] for j in region['jobs']];plan['completedJobIDs']=[];plan['slotJobs']={'1':plan['approvedJobIDs']};plan['regionPlanSHA256']=digest(canonical(region))
            recipe=digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode());store=MemoryStore();producer=Slot(store,plan,1,'producer')
            refs=[]
            for (layer,p),j in zip(files,region['jobs']):
                raw=p.read_bytes();name=f'tiles/{layer}/16/{p.parent.name}/{p.name}';target=worker/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                receipt={'job':j['id'],'validated':True,'recipeSHA256':recipe,'outputs':[{'path':name,'bytes':len(raw),'sha256':digest(raw)}]}
                refs.append(controller.checkpoint_job(producer,receipt,worker))
            details=controller.save_large(producer,{'completedJobReceipts':[asdict(r) for r in refs]});producer.finish({'detailRef':details})
            independent=Slot(store,plan,2,'independent');_,r=independent.recover_receipt(1)
            for ref in controller.load_large(independent,r['result']['detailRef'])['completedJobReceipts']:records.append(controller.record(independent,ref,'rrgh-checkpoint-job-v1'))
            cats=[c for r in records for c in r['result']['outputPacks']];paths=[e['path'] for c in cats for e in c['members']]
            controller.recover_catalogs(independent,cats,paths,recovery/'outputs')
            qa=controller.verify_outputs(plan,region,records,recovery/'outputs');parts=controller.assemble(independent,records,recovery)
            self.assertEqual(qa['files'],len(files));self.assertTrue(qa['pixelsDecoded']);self.assertEqual({p['group'] for p in parts},{'core','leaf-on','leaf-off'})
            self.assertTrue(all(p['nativePartBoundsPass'] for p in parts))

if __name__=='__main__':unittest.main()
