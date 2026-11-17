#!/usr/bin/env python3
"""Audit exact historical 122-part independent layout + current retained carry.

Zero Cloud/API calls. All amounts are prospective, never invoices or authority
to dispatch. The full verified 122-part projection is added again to CURRENT
carry; this intentionally double-counts the 32 accepted parts for a strict,
source-only, no-future-failure conservative bound.
"""
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
sys.path.insert(0,str(ROOT/'source/backend/scripts'))
import rrgh_dispatcher as dispatcher
from gorge_campaign_budget import monthly

EVIDENCE=ROOT/'.github/automation/fixtures/rrgh-verified-full-layout-budget-evidence-20261117.json'
HIST_LAYOUT_SHA='4ab453e99f36c823fda0c1bc7dfc6de752ec8fbeb269a9eec8382f4e41f6e8a8'
HIST_LAYOUT_OBJECT_SHA='e9ba4e8b61bc5b2523e964711e8b2d9337ba7e810b47c363baa9fd2d741a5304'
HIST_VERIFY_RECEIPT='653ecbf5e5c8ee4c53dbacc4e511d37bb8b5b7e025e7230fabf5f13721856ba2'
HIST_VERIFY_CHECKPOINT='a19e36cf638c1cd1d9901fabd3cdf15c5a69f4217c3cc25124d0eaf8278bbbbd'
LATEST_ACCEPTANCE='1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8'
PRIOR_SOURCE='d17d0e335ac47e1f6d116e149992cc02d6e4a827'
CLOUD_STOP=Decimal('122.25')
STORAGE_STOP=Decimal('2.00')


def evidence():
    return json.loads(EVIDENCE.read_text())


def state():
    raw=(ROOT/dispatcher.STATE).read_bytes()
    sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    assert sha==evidence()['current']['controllerBlobSHA'], 'Live controller moved'
    return json.loads(raw)


def recompute():
    e=evidence();old=e['independentVerifier']['settlement'];now=e['current']
    prospective=e['stage']['product']['budgetOutlook']
    # Recover historical pre-layout carry by subtracting only the exact
    # independent layout settlement's observed stored bytes, not billed usage.
    prior_stored=old['nextCarry']['storedBytes']-old['observedUsageStoredBytes']
    # Historical original budget outlook's monthly storage is an exact
    # rounded Decimal result of this integer byte count. Invert that read-only
    # rate to nearest integer and confirm by running the real original formula.
    future_total=(Decimal(prospective['modeledStorageUSDPerMonth'])/Decimal('.036')*
                  Decimal(2**30)).to_integral_value(rounding=ROUND_HALF_EVEN)
    assert monthly(int(future_total))==Decimal(prospective['modeledStorageUSDPerMonth'])
    all_prospective_bytes=int(future_total)-prior_stored
    assert all_prospective_bytes>0
    model_future=Decimal(prospective['remainingWorstCaseUSD'])
    current=Decimal(now['carry']['chargedUSD'])
    cumulative=current+model_future
    conservative_storage=now['carry']['storedBytes']+all_prospective_bytes
    return dict(
        acceptedParts=now['verifiedParts'],fullLayoutParts=e['stage']['product']['parts'],
        remainingParts=e['stage']['product']['parts']-now['verifiedParts'],
        finalIndexes=3,historicalBeforeLayoutStoredBytes=prior_stored,
        originalAllProspectiveStoredBytes=all_prospective_bytes,
        currentRetainedModeledUSD=str(current),
        conservativelyRebudgetAll122PartsAndIndexesUSD=str(model_future),
        totalModeledUSD=str(cumulative),
        totalIncludingProtectedFinalDeliveryUSD=str(cumulative+Decimal('.75')),
        packageStopUSD=str(CLOUD_STOP),
        remainingCloudHeadroomUSD=str(CLOUD_STOP-cumulative),
        modeledMonthlyStorageUSD=str(monthly(conservative_storage)),
        monthlyStorageHeadroomUSD=str(STORAGE_STOP-monthly(conservative_storage)),
        doubleCountsAccepted32=True,additionalTransportFailuresAssumed=0,
        realLayoutObjectReadNow=False,newCloudRead=False,invoice=False,dispatchAuthorized=False)


class HistoricalFullFundingProof(unittest.TestCase):
    def test_layout_and_independent_receipt_are_exact_and_source_pinned(self):
        e=evidence();s=e['stage'];v=e['independentVerifier']
        self.assertEqual(e['format'],'rrgh-historical-verified-layout-budget-anchor-v1')
        self.assertEqual(e['sourceSha'],PRIOR_SOURCE)
        self.assertEqual(s['runID'],v['runID'])
        self.assertEqual((s['jobID'],v['jobID']),(130763515272,130764452361))
        self.assertEqual((s['kind'],v['kind']),('layout','layout'))
        self.assertEqual(s['product']['parts'],122)
        self.assertEqual(s['product']['metadataSHA256'],HIST_LAYOUT_SHA)
        self.assertEqual(s['product']['object']['sha256'],HIST_LAYOUT_OBJECT_SHA)
        self.assertEqual(v['packagePlanSHA256'],'4fb2365c1775855f0b056b5ab98083887ff424fff87bd9c94e727b93fdbf9d67')
        self.assertIn(v['packagePlanSHA256'],s['product']['object']['key'])
        self.assertEqual(v['receiptRef']['sha256'],HIST_VERIFY_RECEIPT)
        self.assertEqual(v['checkpoint']['sha256'],HIST_VERIFY_CHECKPOINT)
        self.assertTrue(v['settlement']['independentReadbackComplete'])
        self.assertEqual(v['status'],'verified')
        self.assertEqual((v['sourceRequests'],v['sourceBytes']),(0,0))
        self.assertFalse(s['product']['budgetOutlook']['invoiceReading'])
        # The protected real implementation independently fetched the
        # publication and recomputed the complete-budget outlook.
        source=(ROOT/'.github/automation/rrgh_package_runtime.py').read_text()
        self.assertIn("actual=records.get(slot,produced['object'],MIB,4*MIB)",source)
        self.assertIn("require(actual==records.describe(value,refs,sources)",source)
        self.assertIn("contract.budget_outlook(actual,slot.plan['campaign']['carry'])",source)
        self.assertIn("outlook=contract.budget_outlook(published,slot.plan['campaign']['carry'])",source)

    def test_current_accepted_halt_and_original_ledger_unchanged(self):
        e=evidence();s=state();now=e['current']
        self.assertEqual(s['status'],now['status'])
        self.assertEqual(s['status'],'halted')
        self.assertEqual((s['package']['ordinal'],s['runID']),(26,43290954679))
        self.assertEqual(s['controlDigest'],now['controllerDigest'])
        self.assertEqual(dispatcher.local_digest(ROOT),s['controlDigest'])
        self.assertEqual(s['package']['carry'],dict(
            chargedUSD=now['carry']['chargedUSD'],
            priorCompletedJobs=34750,priorRasterTiles=278278,
            priorSunlightAssets=320,storedBytes=now['carry']['storedBytes']))
        self.assertEqual((s['package']['lastVerified']['verifiedParts'],
                          s['package']['lastVerified']['verifiedIndexes']),(32,0))
        self.assertEqual(s['package']['lastVerified']['receiptRef']['sha256'],LATEST_ACCEPTANCE)
        self.assertEqual(s['package']['lastVerified']['ordinal'],23)
        self.assertEqual(s['package']['lastVerified']['runID'],now['lastIndependentRun'])
        self.assertEqual(len(s['package']['retainedFailures']),now['retainedFailures'])
        self.assertEqual(s['package']['expiresAt'],now['expiredAt'])
        self.assertEqual(s['completionProgress']['acceptedRasterTiles'],278278)
        self.assertFalse(s['completionProgress']['finalPackageDeliveryComplete'])
        self.assertNotIn('pendingControllerUpgrade',s)

    def test_conservative_whole_layout_122_parts_including_three_indexes_under_original_caps(self):
        e=evidence()
        outlook=e['stage']['product']['budgetOutlook']
        self.assertEqual(outlook['remainingWorstCaseUSD'],
                         '7.002964074742573499679565428')
        self.assertEqual(outlook['modeledStorageUSDPerMonth'],
                         '1.741435576893389225006103516')
        self.assertEqual(e['independentVerifier']['settlement']['nextCarry']['storedBytes'],43836942245)
        self.assertEqual(e['independentVerifier']['settlement']['observedUsageStoredBytes'],33419643)
        m=recompute()
        self.assertEqual(m['remainingParts'],90)
        self.assertEqual(m['originalAllProspectiveStoredBytes'],8136816640)
        self.assertLessEqual(Decimal(m['totalModeledUSD']),CLOUD_STOP)
        self.assertLessEqual(Decimal(m['modeledMonthlyStorageUSD']),STORAGE_STOP)
        self.assertEqual(e['constraints']['cloudCeilingUSD'],'125.00')
        self.assertEqual(e['constraints']['packageStopUSD'],'122.25')
        self.assertEqual(e['constraints']['protectedFinalDeliveryReserveUSD'],'0.75')
        self.assertEqual(e['constraints']['monthlyStorageCeilingUSD'],'2.00')
        # This bound fully re-adds the original *entire* 122-part + index
        # forecast after the current actual accumulated model (32 accepted,
        # five failed allocations). Therefore it cannot silently refund any.
        self.assertTrue(m['doubleCountsAccepted32'])
        self.assertEqual(m['additionalTransportFailuresAssumed'],0)
        self.assertFalse(m['dispatchAuthorized'])
        print('FULL_LAYOUT_HISTORICAL_CONSERVATIVE_MODEL '+json.dumps(m,sort_keys=True))

    def test_failures_storage_guard_must_remain_enabled(self):
        m=recompute()
        current=evidence()['current']['carry']['storedBytes']
        one_full=m['originalAllProspectiveStoredBytes']
        self.assertGreater(monthly(current+3*one_full),STORAGE_STOP)
        self.assertFalse(evidence()['constraints']['packageReplaysForbidden'] is False)
        self.assertFalse(evidence()['constraints']['cloudDispatchAuthorized'])
        # We do NOT approve three more historical-layout-sized repeats.
        self.assertFalse(m['newCloudRead'])


if __name__=='__main__':unittest.main()
