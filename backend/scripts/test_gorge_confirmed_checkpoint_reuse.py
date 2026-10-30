"""No cloud I/O: repeated immutable state bytes must not create a second object."""
import json,tempfile,unittest
from pathlib import Path
from gorge_checkpoint import Slot,Ref,digest,canonical,decode_record
from gorge_stage_coordinator import save_delta

class Store:
    def __init__(self):self.objects={};self.calls=[];self.fail=False
    def create(self,key,raw):
        self.calls.append(key)
        if self.fail or key in self.objects:raise RuntimeError('Simulated failed create; retain reservation')
        self.objects[key]=raw
        return Ref(key,str(1000+len(self.calls)),len(raw),digest(raw))

class ConfirmedReuseTests(unittest.TestCase):
    def slot(self):
        plan=json.loads((Path(__file__).resolve().parent.parent/'config/gorge-indexed-stage-20261029/PLAN.json').read_bytes())
        from datetime import datetime,timedelta,timezone
        plan['expiresAt']=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
        store=Store();return Slot(store,plan,1,'offline-test'),store
    def test_same_confirmed_bytes_reuse_generation_without_second_reservation(self):
        slot,store=self.slot();first=slot.put(b'unchanged-state');used=slot.meter.used.copy();calls=len(store.calls)
        self.assertEqual(slot.put(b'unchanged-state'),first)
        self.assertEqual(slot.meter.used,used);self.assertEqual(len(store.calls),calls)
    def test_different_bytes_and_object_kinds_still_create(self):
        slot,store=self.slot();a=slot.put(b'one');b=slot.put(b'two');c=slot.put(b'one','outputs')
        self.assertEqual(len({a.key,b.key,c.key}),3)
    def test_failed_create_is_not_confirmed_or_refunded(self):
        slot,store=self.slot();before=slot.meter.used.copy();store.fail=True
        with self.assertRaises(RuntimeError):slot.put(b'failed-state')
        self.assertEqual(slot.confirmed_creates,{})
        self.assertEqual(slot.meter.used['classARequests'],before['classARequests']+1)
        self.assertEqual(slot.meter.used['storedBytes'],before['storedBytes']+12)
    def test_two_overview_catalogs_reuse_one_state_pack_and_keep_both_paths(self):
        slot,store=self.slot()
        with tempfile.TemporaryDirectory() as td:
            catalogs=[]
            for job in ('hiking-15-8772-12661','terrain-15-8772-12661'):
                root=Path(td)/job;name='state/'+job+'/cog.sqlite.z1';p=root/name;p.parent.mkdir(parents=True);p.write_bytes(b'identical-confirmed-ledger')
                entries=[{'path':name,'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())}]
                refs=save_delta(slot,root,entries);catalogs.append(decode_record(store.objects[refs[0]['key']],4*2**20))
            self.assertEqual(catalogs[0]['ref'],catalogs[1]['ref'])
            self.assertNotEqual(catalogs[0]['members'][0]['path'],catalogs[1]['members'][0]['path'])
            self.assertEqual(len([k for k in store.calls if '/packs/' in k]),1)
            self.assertEqual(len([k for k in store.calls if '/indexes/' in k]),2)
if __name__=='__main__':unittest.main()
