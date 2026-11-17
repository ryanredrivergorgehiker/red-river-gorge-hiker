#!/usr/bin/env python3
"""Read-only review of a PROPOSED protected package-credential cutover.

NO GitHub API mutations, OIDC permission, Cloud creds, storage, dispatch or state
writes. The old halted controller MUST reject the proposed new CODE_FILES digest.
"""
import copy
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
import rrgh_dispatcher as dispatcher
import rrgh_package_runtime as runtime
import rrgh_package_funding as funding
import rrgh_package_contract as contract
import rrgh_fresh_oidc_token_candidate_20261117 as supplier

STATE_SHA='24e3468dd67d96d541a383a2db93f585c9464b02'
PRIOR_DIGEST='ab8c5bc19ef079cdd36df45c13240aad17fa526ba5214e55e32a4bbdb63a32a8'
PRIOR_RECEIPT='1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8'
PROPOSED_MODULE='.github/automation/rrgh_fresh_oidc_token_candidate_20261117.py'

def blob_sha(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\\0'+raw).hexdigest()

def live_state():
    data=(ROOT/dispatcher.STATE).read_bytes()
    assert blob_sha(data)==STATE_SHA, 'Halted controller changed or formatting drifted'
    return json.loads(data)


class ImmutableHaltTests(unittest.TestCase):
    def test_exact_controller_blob_and_independent_32_part_receipt(self):
        state=live_state()
        self.assertEqual(state['controlDigest'],PRIOR_DIGEST)
        self.assertEqual(state['mode'],'package')
        self.assertEqual(state['status'],'halted')
        self.assertEqual(state['runID'],43290954679)
        self.assertEqual(state['package']['ordinal'],26)
        self.assertEqual(state['package']['retryCount'],2)
        self.assertEqual(len(state['package']['retainedFailures']),5)
        last=state['package']['lastVerified']
        self.assertEqual(last['ordinal'],23)
        self.assertEqual(last['verifiedParts'],32)
        self.assertEqual(last['verifiedIndexes'],0)
        self.assertEqual(last['receiptRef']['sha256'],PRIOR_RECEIPT)
        self.assertEqual(state['completionProgress']['acceptedRasterTiles'],278278)
        self.assertEqual(state['completionProgress']['remainingRasterTiles'],0)
        self.assertFalse(state['completionProgress']['finalPackageDeliveryComplete'])
        self.assertEqual([p['partID'] for p in state['package']['operation']['parts']],
            ['core-032','core-033']+[f'leaf-on-{i:03d}' for i in range(6)])
        self.assertEqual(state['package']['carry']['chargedUSD'],
            '98.07584213409313559532165537')
        self.assertEqual(state['package']['expiresAt'],'2026-11-14T19:30:55Z')

    def test_exact_original_production_credential_helpers_are_unmodified(self):
        for p, sha in [
            ('.github/automation/rrgh_wif_credentials.py','3627cfd47a886ba887a3c5700a8836fe2496955c'),
            ('.github/automation/rrgh_credential_integration.py','f729e5b9dc26e2e01e76606db5810a08589f0055')]:
            self.assertEqual(blob_sha((ROOT/p).read_bytes()),sha)
        self.assertIn('from rrgh_wif_credentials import token',
            (ROOT/'.github/automation/rrgh_credential_integration.py').read_text())

    def test_supplier_and_package_runtime_are_both_in_reviewed_digest(self):
        self.assertIn(PROPOSED_MODULE,dispatcher.CODE_FILES)
        self.assertIn('.github/automation/rrgh_package_runtime.py',dispatcher.CODE_FILES)
        self.assertIn('.github/automation/rrgh_dispatcher.py',dispatcher.CODE_FILES)
        self.assertEqual(len(dispatcher.CODE_FILES),len(set(dispatcher.CODE_FILES)))
        source=(ROOT/'.github/automation/rrgh_package_runtime.py').read_text()
        self.assertIn('from rrgh_fresh_oidc_token_candidate_20261117 import token',source)
        self.assertNotIn('from rrgh_wif_credentials import token',source)
        self.assertIn('store=GCS(plan,evidence,token,opener)',source)
        self.assertIn('worker_ref,worker=slot.recover_receipt(0)',source)
        self.assertIn('complete=verify(slot,auth,checkpoint,operation,worker',source)
        self.assertIn('packageBytesIndependentlyVerified=next_op is None',source)
        self.assertEqual(runtime.transient(RuntimeError('Short-lived WIF refresh failed: rejected-or-invalid')),False)
        self.assertEqual(runtime.transient(RuntimeError('Short-lived WIF refresh failed: transport')),False)
        self.assertIsNotNone(supplier.token)

    def test_candidate_mutation_changes_controller_fingerprint(self):
        files={p:dispatcher.digest((ROOT/p).read_bytes()) for p in dispatcher.CODE_FILES}
        digest=dispatcher.digest(dispatcher.canonical(files))
        self.assertEqual(digest,dispatcher.local_digest(ROOT))
        self.assertNotEqual(digest,PRIOR_DIGEST)
        changed=dict(files);changed[PROPOSED_MODULE]=dispatcher.digest(b'unauthorized edit')
        self.assertNotEqual(dispatcher.digest(dispatcher.canonical(changed)),digest)

    def test_current_halt_rejects_all_unreviewed_new_code_even_upgrade_true(self):
        s=live_state()
        self.assertNotIn('pendingControllerUpgrade',s)
        for allow in (False,True):
            with self.subTest(allow_upgrade=allow):
                with self.assertRaisesRegex(dispatcher.Halt,'Reviewed controller code changed'):
                    dispatcher.validate_state(copy.deepcopy(s),ROOT,allow_upgrade=allow)
        forged=copy.deepcopy(s)
        forged['pendingControllerUpgrade']={
            'fromDigest':PRIOR_DIGEST,
            'toDigest':dispatcher.local_digest(ROOT),
            'authorizedBy':'ryanredrivergorgehiker',
            'authorizedOn':'2026-11-09',
            'preserveAcceptedHistory':True,
        }
        with self.assertRaisesRegex(dispatcher.Halt,'Reviewed controller code changed'):
            dispatcher.validate_state(forged,ROOT,allow_upgrade=True)
        self.assertEqual(blob_sha((ROOT/dispatcher.STATE).read_bytes()),STATE_SHA)

    def test_original_budget_and_receipts_protect_exact_next_operation(self):
        state=live_state()
        op=state['package']['operation']
        self.assertEqual(op['kind'],'parts')
        self.assertEqual(sum(p['archiveBytes'] for p in op['parts']),398243840)
        self.assertEqual(sum(p['files'] for p in op['parts']),12479)
        slots=funding.caps(op)
        self.assertEqual(len(slots),2)
        for slot in slots:
            self.assertEqual(slot['sourceRequests'],0)
            self.assertEqual(slot['sourceBytes'],0)
            self.assertEqual(slot['attempts'],0)
        from gorge_campaign_budget import cost,monthly,add_usage
        limits=add_usage(*slots)
        charge=cost(limits)
        carry=state['package']['carry']
        self.assertLessEqual(Decimal(carry['chargedUSD'])+charge,funding.PACKAGE_STOP)
        self.assertLessEqual(monthly(carry['storedBytes']+limits['storedBytes']),Decimal('2'))
        self.assertEqual(funding.DELIVERY_RESERVE,Decimal('.75'))
        self.assertEqual(funding.PACKAGE_STOP,Decimal('122.25'))
        print('SOURCE_ONLY_NEXT_BATCH_MODEL',json.dumps({
            'archiveParts':len(op['parts']),'hypotheticalNewChargeUSD':str(charge),
            'hypotheticalTotalUSD':str(Decimal(carry['chargedUSD'])+charge),
            'protectedDeliveryReserveUSD':'0.75',
            'modeledMonthlyStorageUSD':str(monthly(carry['storedBytes']+limits['storedBytes'])),
            'fullRemainingLayoutVerified':False,'invoice':False,'cloudDispatched':False},
            sort_keys=True))

    def test_failed_allocation_cannot_be_recycled_as_transport_retry(self):
        state=live_state();error={
            'phase':'final-package-error','packagePlanSHA256':state['package']['planSHA256'],
            'workerPhase':'stage','transientTransport':False,
            'entireAllocationRetained':True,'sourceRequests':0,
            'errorClass':'RuntimeError',
        }
        # Even with the original source plan and authority, the immutable
        # recovery policy requires transientTransport true and retryCount<2.
        source=importlib.import_module('inspect').getsource(
            importlib.import_module('rrgh_package_controller').recovery_allocation)
        self.assertIn("error['transientTransport'] is True",source)
        self.assertIn("p.get('retryCount',0)<2",source)
        self.assertFalse(error['transientTransport'])
        self.assertEqual(state['package']['retryCount'],2)
        self.assertEqual(state['status'],'halted')


if __name__=='__main__':unittest.main()
