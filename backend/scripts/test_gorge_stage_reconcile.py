import copy,unittest
from types import SimpleNamespace
from gorge_stage_coordinator import configuration
from gorge_stage_reconcile import validate,settled_reservation,create_fence,CARRY
from gorge_checkpoint import DIMENSIONS,Meter,canonical,digest
class StageSettlementTests(unittest.TestCase):
 def setUp(self):self.p,self.e,self.r=configuration()
 def test_full_caps_preserve_measured_and_padding(self):
  validate(self.p,self.e)
  for k in DIMENSIONS:self.assertLessEqual(CARRY[k]+sum(s[k] for s in self.p['slots']),self.p['limits'][k])
 def test_unambiguous_only_returns_proven_unused(self):
  a=dict.fromkeys(DIMENSIONS,100);used=dict.fromkeys(DIMENSIONS,30);pad=dict.fromkeys(DIMENSIONS,7)
  result=settled_reservation(a,used,pad)
  self.assertTrue(all(v==37 for v in result['retained'].values()));self.assertTrue(all(v==63 for v in result['demonstrablyUnused'].values()))
  self.assertEqual(a,dict.fromkeys(DIMENSIONS,100))
 def test_ambiguous_keeps_entire_allocation(self):
  result=settled_reservation(dict.fromkeys(DIMENSIONS,100),{}, {},True)
  self.assertTrue(all(v==100 for v in result['retained'].values()));self.assertFalse(any(result['demonstrablyUnused'].values()))
 def test_negative_and_overrun_rejected(self):
  for x in (-1,101):
   with self.assertRaises(ValueError):settled_reservation(dict.fromkeys(DIMENSIONS,100),{'storedBytes':x},{})
 def test_history_cannot_be_edited(self):
  for key in ('storedBytes','egressBytes','classARequests','classBRequests','seconds'):
   p=copy.deepcopy(self.p);p['reconciliation']['carriedUsage'][key]-=1
   with self.assertRaises(ValueError):validate(p,self.e)
 def test_prior_refs_or_seed_cannot_change(self):
  for key in ('priorReceiptRefs','seedRefs','seedCatalogRefs'):
   p=copy.deepcopy(self.p);p['reconciliation'][key][0]['generation']='999'
   with self.assertRaises(ValueError):validate(p,self.e)
 def test_cannot_spend_aggregate_twice(self):
  p=copy.deepcopy(self.p);p['slots'][2]['egressBytes']+=2**20
  with self.assertRaises(ValueError):validate(p,self.e)
 def test_jobs_limits_and_owner_scope_fixed(self):
  for key in ('approvedJobIDs','completedDependencies','limits'):
   p=copy.deepcopy(self.p);p[key]=[]
   with self.assertRaises(ValueError):validate(p,self.e)
 def test_atomic_fence_collision_retains_prepaid_reservation(self):
  meter=Meter(self.p['slots'][0]);seen=[]
  def create(*a,**kw):seen.append(a);raise RuntimeError('412')
  slot=SimpleNamespace(meter=meter,store=SimpleNamespace(_request=create))
  with self.assertRaisesRegex(RuntimeError,'412'):create_fence(slot,'engineering/map-production/test',{'continuation':'one'})
  self.assertEqual(seen[0][2]['ifGenerationMatch'],'0');self.assertEqual(meter.used['classARequests'],1)
  self.assertGreater(meter.used['storedBytes'],0)
if __name__=='__main__':unittest.main()
