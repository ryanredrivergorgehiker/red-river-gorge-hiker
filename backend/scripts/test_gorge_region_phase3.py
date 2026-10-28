import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from shapely.geometry import box
from shapely.ops import unary_union
from benchmark_gorge_pipeline import AOI,json_bytes
from cached_cog_source import atomic
from extend_gorge_sunlight import extension_grid,dem_params,accepted_modules
from orchestrate_gorge_region import make_plan,run,tile_coords,private_root
from build_gorge_map_bundles import PROFILE,validate_regional
from validate_gorge_shared import validate_sun

class RegionSafetyTests(unittest.TestCase):
 def inventory(self):return {'sources':{k:[{'id':k,'bbox':AOI,'url':'https://example.invalid/not-fetched'}] for k in ['hiking','dem','leaf-on','leaf-off']}}
 def plan(self):return make_plan(self.inventory(),{'attempts':12,'seconds':3600,'outputBytes':100_000_000,'childSeconds':300})
 def test_all_layers_and_zooms_exact(self):
  p=self.plan();self.assertEqual(len(p['jobs']),34750)
  self.assertEqual(sum(len(tile_coords(z)) for z in range(10,19)),108420)
  self.assertEqual({j['z'] for j in p['jobs'] if j['layer']=='usgs-topo'},set(range(10,17)))
  self.assertEqual(set(p['profiles']),{'core','leaf-on','leaf-off'})
 def test_no_unbounded_limits(self):
  for limits in [{},{'attempts':0,'seconds':3600,'outputBytes':100_000_000,'childSeconds':300}]:
   with self.assertRaises(ValueError):make_plan(self.inventory(),limits)
 def test_dry_resume_pins_source_and_budget_without_cache_open(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=self.plan();atomic(root/'input.json',json_bytes(p))
   with patch('orchestrate_gorge_region.Cache',side_effect=AssertionError('network')),patch('orchestrate_gorge_region.ServiceCache',side_effect=AssertionError('network')):
    r=run(root/'input.json',root/'output',root/'cache',root/'services',0);self.assertEqual(r['attempts'],0)
    self.assertEqual(run(root/'input.json',root/'output',root/'cache',root/'services',0)['jobsCompleted'],0)
    p['limits']['attempts']=13;atomic(root/'input.json',json_bytes(p))
    with self.assertRaisesRegex(ValueError,'Cannot reset'):run(root/'input.json',root/'output',root/'cache',root/'services',0)
 def test_public_path_rejected(self):
  with self.assertRaises(ValueError):private_root('/tmp/public/generated')
 def test_accepted_sector_grid_full_and_nonoverlapping(self):
  old=[{'boundsWgs84':[round(-83.745+c*.045,8),round(37.93-(r+1)*.04,8),round(-83.745+(c+1)*.045,8),round(37.93-r*.04,8)]} for r in range(5) for c in range(6)]
  new=extension_grid(old);self.assertEqual(len(new),50)
  self.assertLess(box(*AOI).difference(unary_union([box(*s['boundsWgs84']) for s in old+new])).area,1e-10)
  self.assertAlmostEqual(sum(box(*s['boundsWgs84']).area for s in old+new),box(*AOI).area)
 def test_exact_meter_threshold_and_accepted_sampling(self):
  accepted,*_=accepted_modules();self.assertAlmostEqual(accepted.MIN_ELEVATION_M,335.28,places=8)
  p=dem_params([-83.8,37.93,-83.79,37.95],accepted);self.assertEqual(p['pixelType'],'F32');self.assertEqual(p['imageSR'],'3857')
 def test_missing_shared_cannot_activate_core(self):
  with self.assertRaises(ValueError):validate_regional([], 'core')
 def test_incomplete_sun_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);atomic(root/'data/map/rrg-lidar-sun-mobile-manifest.json',json_bytes({'fullGorgeCoverageVerified':False}))
   with self.assertRaises(ValueError):validate_sun(root)

 def test_storage_forecast_removes_archive_and_retains_rollback(self):
  from forecast_gorge_bundle_storage import forecast
  prior={'groups':{'core':{'archiveBytes':1000,'extractedBytes':800,'largestPartBytes':100}},'combined':{'archiveBytes':1000,'extractedBytes':800,'tileFiles':2},'sourceAndCompute':{}}
  sun={'counts':{'sectors':80,'files':320,'bytes':100},'sourceLedger':{},'elapsedSeconds':1}
  r=forecast(prior,sun)['combined'];self.assertEqual(r['installedContentBytes'],800)
  self.assertEqual(r['cleanInstallPeakContentBytes'],900);self.assertEqual(r['allChangedUpdateWithTwoOldGenerationsBytes'],2500)
 def test_changed_engine_refuses_resume(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=self.plan();p['engineHashes']['orchestrate_gorge_region.py']='0'*64
   atomic(root/'input.json',json_bytes(p))
   with self.assertRaisesRegex(ValueError,'Engine changed'):run(root/'input.json',root/'output',root/'cog',root/'service',0)

if __name__=='__main__':unittest.main()
