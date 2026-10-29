import copy
from datetime import datetime,timezone,timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

from gorge_checkpoint import BUCKET, Meter, canonical, digest
from gorge_guarded_worker import SourceOpener
from gorge_stage_preflight import (BASE_KEY,BASE_SHA,BASE_BYTES,CEILINGS,
 require_stage_release, require_input_proof, install_prior_tiles)


def fixture():
    jobs=['job-'+str(i) for i in range(12)]
    caps=dict(CEILINGS)
    p={'format':'rrgh-checkpoint-plan-v1','purpose':'bounded-twelve-job-stage',
       'bucket':BUCKET,'deleteAllowed':False,'bulkProductionEnabled':False,
       'bookkeepingProfile':'compact-v2','maxConcurrency':1,
       'expiresAt':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
       'sourceSnapshotSHA256':'a'*64,'slots':[caps],'limits':caps.copy(),
       'slotJobs':{'0':jobs},'approvedJobIDs':jobs,
       'jobPolicies':{j:{'sourceBytes':1,'sourceRequests':1,'seconds':60} for j in jobs}}
    e={'cloudStorageAllowance':{'approvedUSD':'.35','reservedWorstCaseUSD':'.35',
       'approvalReference':'synthetic-test-only','planSHA256':digest(canonical(p)),
       'ongoingStorageAcknowledged':True,'approvedRecurringStorageUSDPerMonth':'1','chargedRetentionMonths':1},
       'stageRelease':{'campaignApprovedUSD':'8','releasedUSD':'.35','lockedUSD':'7.65',
       'approvedRecurringUSDPerMonth':'1','approvalReference':'synthetic-test-only','planSHA256':digest(canonical(p)),
       'approvedJobIDsSHA256':digest(canonical(jobs))},
       'planningRates':{'storageUSDPerGiBMonth':'.03','egressUSDPerGiB':'.23',
       'classAUSDPer1000':'.01','classBUSDPer1000':'.001'},
       'github':{'hardCeilingUSD':350,'stopAtLimitVerified':True}}
    return p,e


def rebind(p,e):
    for key in ['cloudStorageAllowance','stageRelease']:e[key]['planSHA256']=digest(canonical(p))


class StagePreflightTests(unittest.TestCase):
    def test_exact_release_passes_offline(self):
        p,e=fixture();require_stage_release(p,e)

    def test_campaign_approval_is_not_released_money(self):
        p,e=fixture();e['cloudStorageAllowance']['approvedUSD']='8'
        with self.assertRaisesRegex(ValueError,'Unreleased'):require_stage_release(p,e)

    def test_release_hash_and_locked_remainder_required(self):
        for field,value in [('lockedUSD','0'),('planSHA256','b'*64)]:
            p,e=fixture();e['stageRelease'][field]=value
            with self.assertRaises(ValueError):require_stage_release(p,e)

    def test_all_stage_dimensions_are_hard_capped(self):
        for dim in CEILINGS:
            p,e=fixture();p['limits'][dim]+=1;rebind(p,e)
            with self.assertRaises(ValueError):require_stage_release(p,e)

    def test_extra_worker_or_different_job_set_rejected(self):
        p,e=fixture();p['maxConcurrency']=2;rebind(p,e)
        with self.assertRaises(ValueError):require_stage_release(p,e)
        p,e=fixture();p['approvedJobIDs']=p['approvedJobIDs'][::-1];rebind(p,e)
        with self.assertRaises(ValueError):require_stage_release(p,e)

    def test_per_job_source_overallocation_rejected(self):
        p,e=fixture();p['jobPolicies']['job-0']['sourceBytes']=CEILINGS['sourceBytes'];rebind(p,e)
        with self.assertRaisesRegex(ValueError,'Per-job'):require_stage_release(p,e)

    def test_missing_input_proof_rejected(self):
        with self.assertRaisesRegex(ValueError,'proof'):require_input_proof({}, {}, {})

    def test_driver_missing_proof_never_reaches_credentials_or_cloud(self):
        from types import SimpleNamespace
        import run_gorge_checkpoint_slot as driver
        p,e=fixture()
        env={'GITHUB_REPOSITORY_ID':'1325611891','GITHUB_REPOSITORY_OWNER_ID':'313924954',
          'GITHUB_REF':'refs/heads/lane20/offline-production-preflight-20261029',
          'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1',
          'GITHUB_WORKFLOW_REF':'ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029'}
        with tempfile.TemporaryDirectory() as td, patch.dict(driver.os.environ,env),patch.object(driver,'GCS') as gcs,patch.object(driver,'token') as token:
            args=SimpleNamespace(output=Path(td)/'new',slot=0,input_proof=None,prior_root=None,shared_root=None)
            with self.assertRaisesRegex(ValueError,'input proof'):driver.execute(args,p,{},e)
            gcs.assert_not_called();token.assert_not_called()

    def proof(self):
        return {'format':'rrgh-stage-input-proof-v1','acceptedBase':{'bucket':BUCKET,
          'key':BASE_KEY,'sha256':BASE_SHA,'bytes':BASE_BYTES,'generation':'123'},
          'checkpointRefs':[{'key':'engineering/map-production/test-only','generation':'124','bytes':100,'sha256':'a'*64}],
          'files':[]}

    def test_base_pin_and_checkpoint_generation_required(self):
        for change in ['base','refs']:
            proof=self.proof()
            if change=='base':proof['acceptedBase']['generation']=None
            else:proof['checkpointRefs']=[]
            with self.assertRaises(ValueError):require_input_proof({'inputProofSHA256':digest(canonical(proof))},proof,{})

    def test_corrupted_local_private_bytes_fail_before_native_import(self):
        with tempfile.TemporaryDirectory() as td:
            roots={k:Path(td)/k for k in ['cog','service','prior','shared']}
            for p in roots.values():p.mkdir()
            (roots['cog']/'block').write_bytes(b'corrupt')
            proof=self.proof();proof['files']=[{'kind':'cog','path':'block','bytes':4,'sha256':digest(b'good'),'offset':0,'checkpointIndex':0}]
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                require_input_proof({'inputProofSHA256':digest(canonical(proof))},proof,roots)

    def test_dependency_copy_rechecks_hash_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);prior=root/'prior';prior.mkdir();(prior/'tiles').mkdir();p=prior/'tiles/test';p.write_bytes(b'good')
            v={'priorRoot':prior,'priorTiles':[{'path':'tiles/test','bytes':4,'sha256':digest(b'good')}]}
            install_prior_tiles(v,root/'out')
            with self.assertRaises(FileExistsError):install_prior_tiles(v,root/'out')
            p.write_bytes(b'evil')
            with self.assertRaisesRegex(ValueError,'changed'):install_prior_tiles(v,root/'other')

    def test_source_actual_bytes_separate_from_nonrefundable_reservation(self):
        class Response(io.BytesIO):
            status=200
        caps={k:0 for k in CEILINGS};caps.update(sourceBytes=1000001,sourceRequests=1,seconds=60)
        meter=Meter(caps);opener=SourceOpener(meter,lambda *a,**kw:Response(b'abc'))
        req=Request('https://kyraster.ky.gov/arcgis/rest/services/ImageServices/Ky_NAIP_2022_2FT/ImageServer?f=pjson')
        with opener(req) as r:self.assertEqual(r.read(1000001),b'abc')
        self.assertEqual(opener.summary()['receivedBodyBytes'],3)
        self.assertEqual(meter.used['sourceBytes'],1000001)
        with self.assertRaises(ValueError):opener(req)
        self.assertEqual(opener.summary()['operations'],1)

    def test_failed_source_operation_is_counted_without_refund(self):
        caps={k:0 for k in CEILINGS};caps.update(sourceBytes=1000001,sourceRequests=1,seconds=60)
        def fail(*a,**kw):raise OSError('synthetic unavailable')
        meter=Meter(caps);opener=SourceOpener(meter,fail)
        with self.assertRaises(OSError):opener(Request('https://kyraster.ky.gov/arcgis/rest/services/ImageServices/Ky_NAIP_2022_2FT/ImageServer'))
        self.assertEqual(opener.summary()['operations'],1)
        self.assertEqual(meter.used['sourceBytes'],1000001)


if __name__=='__main__':unittest.main()
