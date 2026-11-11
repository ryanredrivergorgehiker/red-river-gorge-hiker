import hashlib,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit,parse_qs,unquote
import rrgh_checkpoint_diagnostics as subject

def canonical(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(v):return hashlib.sha256(v).hexdigest()

class InspectionTests(unittest.TestCase):
    def test_real_selective_recovery_uses_shared_inspection_meter(self):
        import importlib.util
        source=Path(os.environ['RRGH_TEST_SOURCE'])/'backend/scripts/gorge_checkpoint.py'
        spec=importlib.util.spec_from_file_location('inspection_real_checkpoint',source)
        checkpoint=importlib.util.module_from_spec(spec);sys.modules[spec.name]=checkpoint;spec.loader.exec_module(checkpoint)
        data=b'preserved tile bytes';calls=[]
        store=types.SimpleNamespace(read=lambda ref,start,length:(calls.append((start,length)) or data[start:start+length]))
        ref=checkpoint.Ref(key='engineering/map-production/preserved.pack',generation='1',bytes=len(data),sha256=digest(data))
        manifest=[dict(ref=vars(ref),members=[dict(path='tiles/example.png',offset=0,bytes=len(data),sha256=digest(data))])]
        slot=subject.ReadOnlySlot(store,dict(bytes=100,requests=3),2,40)
        with tempfile.TemporaryDirectory() as root:
            destination=Path(root)/'selected'
            result=checkpoint.recover_members(slot,manifest,['tiles/example.png'],destination)
            self.assertEqual((destination/'tiles/example.png').read_bytes(),data)
            self.assertEqual(result['files'],1)
            self.assertEqual(slot.meter.used,dict(egressBytes=40+len(data),classBRequests=3))
            with self.assertRaisesRegex(ValueError,'remaining egress'):
                checkpoint.recover_members(slot,manifest,['tiles/example.png'],Path(root)/'again')
            with self.assertRaisesRegex(ValueError,'inspection budget'):slot.get(ref)
        self.assertEqual(calls,[(0,len(data))])

    def run_inspection(self,corrupt=None):
        plan={'bucket':'rrgh-nonproduction-protected-packages','approvedJobIDs':[], 'campaign':{'sequence':1453},'finalOverviewPhase':{'enabled':True}}
        proof={'format':'rrgh-stage-input-proof-v1','acceptedBase':{},'priorReceipts':[{'job':'saved'}], 'checkpointRefs':[], 'files':[{'kind':'prior','path':'receipts/saved.json'},{'kind':'shared','path':'not-disclosed'}]}
        raw=canonical(proof);key='engineering/map-production/plans/'+'a'*64+'/slots/00000/indexes/proof'
        ref={'key':key,'generation':'123','bytes':len(raw),'sha256':digest(raw)};calls=[]
        def open_request(req,timeout):
            calls.append(req.get_method());self.assertEqual(req.get_method(),'GET')
            parsed=urlsplit(req.full_url);name=unquote(parsed.path.split('/o/')[1]);q=parse_qs(parsed.query)
            if name!=key:raise HTTPError(req.full_url,404,'missing',{},None)
            if q.get('alt')==['media']:
                self.assertEqual(q['generation'],['123']);self.assertEqual(q['ifGenerationMatch'],['123'])
                return io.BytesIO(raw if corrupt!='hash' else b'X'*len(raw))
            return io.BytesIO(canonical({'name':key,'generation':'124' if corrupt=='generation' else '123','size':len(raw)}))
        modules={'gorge_campaign':types.SimpleNamespace(configuration=lambda:(plan,{},{})), 'gorge_checkpoint':types.SimpleNamespace(canonical=canonical,digest=digest,decode_record=lambda b,**kw:json.loads(b)), 'gorge_producer_identity':types.SimpleNamespace(require_owner=lambda p,r:None), 'rrgh_checkpoint_recovery':types.SimpleNamespace(bounds=lambda p:dict(objects=32,requests=64,bytes=8*2**20)), 'rrgh_wif_credentials':types.SimpleNamespace(token=lambda:'test')}
        with tempfile.TemporaryDirectory() as root,patch.dict(sys.modules,modules),patch.dict(os.environ,{'RRGH_PLAN_SHA256':digest(canonical(plan))}),patch.object(subject,'credential',return_value='test'),patch.object(subject,'build_opener',return_value=types.SimpleNamespace(open=open_request)),patch.object(subject,'seed_metadata_references',return_value=[{'name':'proof','ref':ref}]):
            result=subject.inspect(root)
        return result,calls

    def test_exact_pin_read_only_and_summary(self):
        result,calls=self.run_inspection();self.assertEqual(result['cloudWrites'],0);self.assertEqual(result['sourceRequests'],0)
        record=result['objects'][-1]['record'];self.assertEqual(record['priorReceipts'],[{'job':'saved'}]);self.assertEqual(record['priorFiles'],[{'kind':'prior','path':'receipts/saved.json'}]);self.assertNotIn('files',record)
        self.assertEqual(calls,['GET']*8)
    def test_generation_change_rejected_before_media(self):
        with self.assertRaisesRegex(ValueError,'Pinned historical metadata changed'):self.run_inspection('generation')
    def test_hash_change_rejected(self):
        with self.assertRaisesRegex(ValueError,'Historical metadata hash changed'):self.run_inspection('hash')

if __name__=='__main__':unittest.main()
