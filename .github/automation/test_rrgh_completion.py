import copy
from dataclasses import asdict
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import rrgh_completion_contract as c
import rrgh_completion_audit as a
import rrgh_dispatcher as d


def synthetic_report():
    """Explicit synthetic audit input; never a live recovery acceptance."""
    m = c.manifest();plan,_ = c.funding()
    ledger = c.settlement(dict.fromkeys(m['completionAllocation'],0))
    ref = dict(key=c.PREFIX+c.sha(plan)+'/slots/00000/receipt.json', generation='999', bytes=2000, sha256='a'*64)
    result = dict(status='verified', completionManifestSHA256=c.manifest_sha(),
        originalProducerRunID=m['originalRunID'], originalPlanSHA256=m['planSHA256'],
        failedRecoveryReceipt=m['failedRecoveryReceipt'], workerReceipt=m['producerReceipt'],
        bootstrapReceipt=m['bootstrapReceipt'], batchClosure=m['batchClosure'], jobs=24, tiles=246,
        verifiedTileCatalogTiles=246, sourceJobsExecuted=0, sourceRequests=0, sourceBytesReceived=0,
        adjacentEdgesMeasured=10, packageParts=3, packageBytes=10000, sourcePixelGapJobs=[], pixelGapAttemptsConsumed=0,
        allOutputHashesAndPixelsVerified=True, allNewPackageChunksReadBack=True, allExistingCachesPreserved=True,
        originalClaimsAndReceiptsUnchanged=True, settlement=ledger, nextCarry=c.next_carry(ledger),
        overviewPilotVerification=None)
    state = dict(runID=999,dispatchID='b'*64,sourcePolicyMode='expanded',overviewPilotEnabled=False)
    parent = dict(created_at='2026-11-03T22:38:21Z')
    job = dict(completed_at='2026-11-04T02:00:00Z')
    row = dict(receiptRef=ref,result=result)
    return row,state,parent,job


class CompletionTests(unittest.TestCase):
    def test_new_allocation_cannot_render_or_download_source(self):
        p,e = c.funding()
        self.assertEqual(p['limits']['attempts'],0)
        self.assertEqual(p['limits']['sourceBytes'],0)
        self.assertEqual(p['limits']['sourceRequests'],0)
        self.assertEqual(len(p['slots']),1)
        self.assertNotEqual(c.sha(p),c.manifest()['planSHA256'])
        bad=c.manifest();bad['completionAllocation']['attempts']=1
        with self.assertRaises(ValueError):c.funding(bad)

    def test_full_failed_and_completion_allocations_retained_even_with_zero_usage(self):
        m=c.manifest();ledger=c.settlement(dict.fromkeys(m['completionAllocation'],0))
        self.assertEqual(ledger['retainedUsage'],{k:m['originalAllocation'][k]+2*m['completionAllocation'][k]
                                               for k in m['completionAllocation']})
        self.assertEqual(ledger['retainedCompletions'],m['retainedCompletions'])
        self.assertTrue(ledger['ambiguousAllocationRetained'])
        self.assertTrue(ledger['independentRecoveryComplete'])
        self.assertEqual(c.next_carry(ledger)['priorCompletedJobs'],14021)
        self.assertEqual(c.next_carry(ledger)['priorRasterTiles'],144334)
        self.assertLess(Decimal(ledger['chargedUSD']),Decimal('123'))

    def test_completion_overrun_is_rejected(self):
        used=c.manifest()['completionAllocation'];used['classBRequests']+=1
        with self.assertRaises(ValueError):c.settlement(used)

    def test_original_consumed_receipt_cannot_be_used_as_completion(self):
        with self.assertRaises(ValueError):c.check_reference(c.manifest()['failedRecoveryReceipt'])

    def test_verified_result_preserves_inventory_and_forces_prospective_fallback(self):
        report=a.verify_result(*synthetic_report());c.check_report(report)
        self.assertFalse(report['batchPilotEnabled'])
        self.assertEqual(report['batchClosure'],c.manifest()['batchClosure'])
        self.assertEqual(report['acceptedRasterTiles'],144334)

    def test_false_qa_or_source_replay_is_rejected(self):
        for key,value in [('sourceRequests',1),('sourceJobsExecuted',24),('allOutputHashesAndPixelsVerified',False),
                          ('allNewPackageChunksReadBack',False),('originalClaimsAndReceiptsUnchanged',False),
                          ('tiles',245),('workerReceipt',c.manifest()['failedRecoveryReceipt'])]:
            with self.subTest(key=key):
                args=synthetic_report();args[0]['result'][key]=value
                with self.assertRaises(ValueError):a.verify_result(*args)

    def test_old_allocation_cannot_be_refunded(self):
        args=synthetic_report();args[0]['result']['settlement']['retainedUsage']['classARequests']-=1
        with self.assertRaises(ValueError):a.verify_result(*args)

    def test_receipt_exception_is_exact(self):
        for key,value in [('wave',290),('planSHA256','f'*64),('batchPilotEnabled',True),
                          ('completionManifestSHA256','0'*64),('acceptedJobs',14022)]:
            with self.subTest(key=key):
                report=a.verify_result(*synthetic_report());report[key]=value
                with self.assertRaises(ValueError):c.check_report(report)

    def test_original_run_identity_is_exact(self):
        m=c.manifest()
        run=dict(id=m['originalRunID'],run_attempt=1,head_branch=a.BRANCH,path=a.WORKFLOW,
                 event='workflow_dispatch',actor=dict(login='github-actions[bot]'),
                 repository=dict(full_name=a.REPO),display_title='RRGH production 289 '+m['originalDispatchID'])
        a.identity(run,'production',m['originalRunID'],m['originalDispatchID'])
        run['run_attempt']=2
        with self.assertRaises(ValueError):a.identity(run,'production',m['originalRunID'],m['originalDispatchID'])

    def test_repeated_completion_is_rejected_before_cloud_or_dispatch(self):
        m=c.manifest()
        state=dict(enabled=True,status='halted',mode='complete',runID=999,dispatchID='f'*64,
                   sourceSHA=m['sourceSHA'],planSHA256=m['planSHA256'],sequence=289,
                   completionOf=dict(manifestSHA256=c.manifest_sha()))
        class API:
            def state(self):return 'old',state
            def call(self,*args):raise AssertionError('No API dispatch permitted')
        with patch.object(d,'caller'),patch.object(d,'validate_state'):
            with self.assertRaises(d.Halt):d.complete_halted(API(),Path('.'))


@unittest.skipUnless(os.environ.get('RRGH_TEST_SOURCE'),'Actual checkpoint engine path required')
class CheckpointEngineTests(unittest.TestCase):
    def test_exact_retained_completion_is_durably_claimed_once(self):
        sys.path.insert(0,str(Path(os.environ['RRGH_TEST_SOURCE']).resolve()/'backend/scripts'))
        from test_rrgh_dispatcher import FakeGitHub, ROOT
        m=c.manifest();prior=m['retainedCompletions'][0]
        api=FakeGitHub();api.head=m['sourceSHA']
        api.value.update(status='halted',mode='complete',sequence=289,sourceSHA=m['sourceSHA'],
                         planSHA256=m['planSHA256'],runID=prior['runID'],dispatchID=prior['dispatchID'],
                         completionOf=dict(manifestSHA256=prior['manifestSHA256']),
                         completionAuthorization=dict(authorizedBy='ryanredrivergorgehiker',
                             authorizedOn='2026-11-04',manifestSHA256=c.manifest_sha()))
        with patch.object(d,'caller'),patch.object(a,'original'):
            d.complete_halted(api,ROOT)
            self.assertEqual(api.value['status'],'dispatching')
            self.assertEqual(api.value['mode'],'complete')
            self.assertEqual(api.value['sourceSHA'],m['sourceSHA'])
            self.assertEqual(api.value['completionOf']['runID'],m['originalRunID'])
            self.assertEqual(api.value['retainedCompletionHistory'],m['retainedCompletions'])
            with self.assertRaises(d.Halt):d.complete_halted(api,ROOT)
            self.assertEqual(sum(call[0]=='POST' for call in api.calls),1)

    def test_funded_immutable_slot_and_duplicate_claim(self):
        sys.path.insert(0,str(Path(os.environ['RRGH_TEST_SOURCE']).resolve()/'backend/scripts'))
        from gorge_checkpoint import Slot,Ref,require_live_allowance,digest
        plan,evidence=c.funding();require_live_allowance(plan,evidence)
        class MemoryStore:
            def __init__(self):self.objects={}
            def create(self,key,raw):
                if key in self.objects:raise ValueError('create-only collision')
                self.objects[key]=raw
                return Ref(key,str(len(self.objects)),len(raw),digest(raw))
        store=MemoryStore();slot=Slot(store,plan,0,'synthetic-owner')
        before=copy.deepcopy(store.objects)
        with self.assertRaises(ValueError):Slot(store,plan,0,'synthetic-owner-2')
        self.assertEqual(before,store.objects)
        self.assertNotIn(c.manifest()['failedRecoveryReceipt']['key'],store.objects)
        with self.assertRaises(ValueError):slot.meter.reserve(sourceRequests=1)


if __name__ == '__main__':
    unittest.main()
