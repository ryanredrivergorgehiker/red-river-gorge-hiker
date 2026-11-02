"""Offline regression tests; synthetic receipts never count as production."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

import rrgh_dispatcher as d
import rrgh_expanded_production as e
import rrgh_dispatch_audit as a
from test_rrgh_dispatcher import FakeGitHub, DispatcherTests

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(os.environ.get('RRGH_TEST_SOURCE','rrgh-expansion-source')).resolve()
sys.path.insert(0,str(SOURCE/'backend/scripts'))


def region():
    return e.read_region(SOURCE/'backend/config/gorge-campaign-wave-058-20261102')


class ExpansionTests(unittest.TestCase):
    def test_all_pinned_original_objects_and_other_families_preserved(self):
        old=region();new=e.migration(copy.deepcopy(old))
        for family,rows in old['inventory']['sources'].items():
            index={s['id']:s for s in new['inventory']['sources'][family]}
            for row in rows:self.assertEqual(row,index[row['id']])
        self.assertEqual(new['boundsWGS84'],old['boundsWGS84'])
        self.assertEqual(new['profiles'],old['profiles'])
        self.assertFalse(new['regionalPixelCoverageVerified'])
        index,missing=e.build_index(new)
        self.assertEqual(len(index),25900)
        self.assertEqual(sum(missing.values()),0)
    def test_rollback_restores_original_selection_without_changing_history(self):
        old=region();new=e.migration(copy.deepcopy(old))
        frozen=copy.deepcopy(new['jobs'])
        e.migration(new,'legacy')
        self.assertEqual(new['inventory'],old['inventory'])
        self.assertEqual(new['jobs'],frozen)
        index,_=e.build_index(new)
        self.assertEqual(len(index),11940)
        e.migration(new,'expanded')
        self.assertEqual(len(e.build_index(new)[0]),25900)
    def test_tampered_original_source_or_rollback_rejected(self):
        for field in ('url','id'):
            old=region();old['inventory']['sources']['dem'][0][field]='forged'
            with self.assertRaises(ValueError):e.migration(old)
        new=e.migration(region());new['legacyInventory']['sources']['hiking'][0]['url']='forged'
        with self.assertRaises(ValueError):e.migration(new)
    def test_new_sources_require_native_metadata_and_attribution(self):
        old=region();new=e.migration(copy.deepcopy(old))
        for family in ('hiking','dem','leaf-off'):
            ids={s['id'] for s in old['inventory']['sources'][family]}
            for row in new['inventory']['sources'][family]:
                if row['id'] not in ids:
                    self.assertEqual(row['expandedNativePolicy'],family)
                    self.assertEqual(row['catalogSHA256'],e.CATALOG_SHA)
                    self.assertIn('attribution',row)
    def test_worst_case_pilot_fits_actual_producer_seconds(self):
        self.assertEqual(sum(e.LIMITS.values()),9)
        self.assertLessEqual(sum(e.LIMITS.values())*600,9000)


class UpgradeTests(unittest.TestCase):
    def prepared(self):
        api=FakeGitHub();old,state=api.state();d.dispatch(api,ROOT,old,state,'probe')
        inputs=DispatcherTests().inputs(api)
        old_digest='2'*64
        api.value['controlDigest']=old_digest
        api.value['pendingControllerUpgrade']=dict(fromDigest=old_digest,toDigest=d.local_digest(ROOT),
            authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-02',preserveAcceptedHistory=True)
        return api,inputs
    def test_upgrade_only_at_new_exact_claim_preserves_plan_and_receipt(self):
        api,inputs=self.prepared();before=copy.deepcopy(api.value)
        d.claim(api,ROOT,inputs,123)
        for k in ('sequence','sourceSHA','planSHA256','dispatchID','githubReservationHistory'):
            self.assertEqual(api.value[k],before[k])
        self.assertEqual(api.value['controlDigest'],d.local_digest(ROOT))
        self.assertEqual(api.value['controllerUpgradeHistory'][0]['claimedRunID'],123)
        self.assertNotIn('pendingControllerUpgrade',api.value)
    def test_missing_changed_or_unauthorized_upgrade_fails_closed(self):
        for k in ('fromDigest','toDigest','authorizedBy','authorizedOn','preserveAcceptedHistory'):
            api,inputs=self.prepared();api.value['pendingControllerUpgrade'].pop(k)
            before=copy.deepcopy(api.value)
            with self.assertRaises(d.Halt):d.claim(api,ROOT,inputs,123)
            self.assertEqual(api.value,before)
    def test_no_mid_run_upgrade_and_no_wrong_worker_claim(self):
        api,inputs=self.prepared();api.value['status']='running'
        with self.assertRaises(d.Halt):d.validate_state(api.value,ROOT,allow_upgrade=True)
        api,inputs=self.prepared();inputs['source_sha']='f'*40
        with self.assertRaises(d.Halt):d.claim(api,ROOT,inputs,123)
        self.assertEqual(api.value['controlDigest'],'2'*64)


class NativeMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('expanded_native_renderer',ROOT/e.TEMPLATE)
        cls.renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.renderer)
    def dataset(self,unit='US survey foot',pixel=2.0):
        return SimpleNamespace(crs='EPSG:3089',units=(unit,),
            transform=SimpleNamespace(a=pixel,e=-pixel,b=0,d=0))
    def test_dem_exact_native_units_are_used(self):
        for unit in ('US survey foot','metre'):
            self.assertEqual(self.renderer.expanded_native_unit({'expandedNativePolicy':'dem'},self.dataset(unit),True),unit)
    def test_missing_unit_coarse_source_or_wrong_crs_rejected(self):
        cases=[self.dataset(None),self.dataset('feet'),self.dataset(pixel=5)]
        bad=self.dataset();bad.crs='EPSG:3857';cases.append(bad)
        for ds in cases:
            with self.assertRaises(ValueError):self.renderer.expanded_native_unit({'expandedNativePolicy':'dem'},ds,True)
    def test_family_mismatch_rejected_and_original_path_preserved(self):
        with self.assertRaises(ValueError):self.renderer.expanded_native_unit({'expandedNativePolicy':'leaf-off'},self.dataset(),True)
        self.assertEqual(self.renderer.expanded_native_unit({'verticalUnit':'US survey foot'},self.dataset(),True),'US survey foot')


class ZeroOutputRecoveryTests(unittest.TestCase):
    def fixture(self):
        seq=100;plan='a'*64;dispatch='b'*64;gap='hiking-16-17512-25290'
        state=dict(sequence=seq,runID=123,dispatchID=dispatch,planSHA256=plan)
        run=dict(id=123,run_attempt=1,head_branch=d.WORKER,event='workflow_dispatch',status='in_progress',
            conclusion=None,path='.github/workflows/'+d.WORKFLOW,actor=dict(login='github-actions[bot]'),
            repository=dict(full_name=d.REPO),display_title=f'RRGH production {seq} '+dispatch)
        jobs=[dict(name=n,status='completed',conclusion='success') for n in ('bounded-stage','independent-recovery')]
        result=dict(status='verified',jobs=0,tiles=0,outputBytes=0,packageParts=0,packageBytes=0,adjacentEdgesMeasured=0,
            allOutputHashesAndPixelsVerified=True,allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,
            sourcePixelGapJobs=[gap],pixelGapAttemptsConsumed=1,
            nextCarry=dict(priorCompletedJobs=100,priorRasterTiles=500,priorSunlightAssets=320,chargedUSD='20',storedBytes=1000),
            settlement=dict(independentRecoveryComplete=True,ambiguousAllocationRetained=False,
                campaignID='gorge-full-quality-125usd-20261031',sequence=seq,ceilingUSD='125',
                planSHA256=plan,chargedUSD='20',storedBytes=1000,storageEstimateUSDPerMonth='1',remainingAuthorityUSD='105'))
        receipt=dict(phase='independent-recovery',receiptRef=dict(bytes=1000,generation='123',sha256='c'*64,
            key=a.PREFIX+plan+'/slots/00002/receipt.json'),result=result)
        producer=[dict(job=gap,status='source-pixel-gap-quarantined',attemptConsumed=True,sourceQualityUnchanged=True),
            dict(phase='production',jobs=0,sourcePixelGapJobs=[gap],status='bounded-stop',diagnostic=None)]
        return run,jobs,receipt,producer,state
    def audit(self,f):
        run,jobs,receipt,producer,state=f
        return a.audit_run(run,jobs,[json.dumps(receipt)],[json.dumps(x) for x in producer],expected_dispatch=state)
    def test_verified_all_gap_batch_advances_without_inventing_output(self):
        result=self.audit(self.fixture())
        self.assertEqual(result['jobsNew'],0)
        self.assertEqual(result['acceptedRasterTiles'],500)
        self.assertEqual(result['sourceCompletedJobIDs'],[])
    def test_zero_output_without_consumed_gap_or_with_claimed_output_rejected(self):
        for key,value in [('sourcePixelGapJobs',[]),('pixelGapAttemptsConsumed',0),('tiles',1),('packageParts',1)]:
            f=self.fixture();f[2]['result'][key]=value
            with self.assertRaises(a.Halt):self.audit(f)
        f=self.fixture();f[3][0]['attemptConsumed']=False
        with self.assertRaises(a.Halt):self.audit(f)


if __name__=='__main__':unittest.main()
