import copy
from datetime import datetime, timezone
import unittest
from assess_map_production_costs import assess, REQUIRED_CONTROLS

NOW = datetime(2026, 10, 29, 19, tzinfo=timezone.utc)


def fixture():
    evidence = {'observedAt': NOW.isoformat(), 'evidenceReference': 'fixture-only'}
    return {'sourceAndCompute': {'totalSourceCacheBytes': 564951223050},
            'combined': {'archiveBytes': 7685212160}}, {
        'rates': {'storageUSDPerGiBMonth': .02, 'egressUSDPerGiB': .12,
                  'classAUSDPer1000': .005, 'classBUSDPer1000': .0004},
        'proposedLimits': {'storedBytes': 600*2**30, 'egressBytes': 10*2**30,
                           'classARequests': 50000, 'classBRequests': 100000,
                           'chargedRetentionMonths': 1, 'costContingencyFraction': .2},
        'githubBilling': {**evidence, 'hardCeilingUSD': 350,
                          'currentUsedUSD': 300, 'stopAtLimitVerified': True},
        'gcsBilling': {**evidence, 'approvedRemainingUSD': 20, 'alreadyReservedUSD': 0},
        'bucket': {**evidence, 'name': 'rrgh-nonproduction-protected-packages',
                   'location': 'us-east1', 'storageClass': 'STANDARD',
                   'rateProfileVerified': True, 'uniformAccessVerified': True,
                   'publicAccessPrevention': 'enforced'},
        'runner': {'repositoryVisibility': 'public', 'label': 'ubuntu-latest',
                   'artifactUploads': False, 'actionsCache': False},
        'retentionLiabilityAcknowledged': True,
        'acceptedPrivateInputsVerified': True,
        'implementationEvidence': {k: 'fixture-only' for k in REQUIRED_CONTROLS},
    }


class CostGateTests(unittest.TestCase):
    def test_complete_fixture_passes_without_dispatch(self):
        f,c=fixture();r=assess(f,c,NOW)
        self.assertTrue(r['fullProductionPreflightPassed'])
        self.assertFalse(r['productionDispatched'])
        self.assertAlmostEqual(r['proposedGCSReservationWithContingencyUSD'],16.188)

    def test_missing_account_state_fails(self):
        f,c=fixture();c['githubBilling']={};c['gcsBilling']={}
        self.assertFalse(assess(f,c,NOW)['fullProductionPreflightPassed'])

    def test_stale_or_future_evidence_fails(self):
        for t in ['2026-10-27T19:00:00+00:00','2026-10-30T19:00:00+00:00']:
            f,c=fixture();c['bucket']['observedAt']=t
            self.assertFalse(assess(f,c,NOW)['fullProductionPreflightPassed'])

    def test_five_and_fifteen_dollar_headroom_fail_full_cache_scenario(self):
        for limit in [5,15]:
            f,c=fixture();c['gcsBilling']['approvedRemainingUSD']=limit
            self.assertIn('Proposed GCS cost reservation exceeds approved remaining funds',assess(f,c,NOW)['blockers'])

    def test_packing_operations_and_egress_math(self):
        f,c=fixture();r=assess(f,c,NOW)['scenarios']
        self.assertEqual(r['raw64KiBObjectCountEstimate'],8620472)
        self.assertAlmostEqual(r['raw64KiBUploadOperationsUSD'],43.10236)
        self.assertEqual(r['packed64MiBMinimumObjectCountEstimate'],8419)
        self.assertAlmostEqual(r['oneCompleteExternalCacheRecoveryUSD'],63.13821931)

    def test_private_or_larger_runner_not_free(self):
        for key,value in [('repositoryVisibility','private'),('label','ubuntu-16-core'),('artifactUploads',True)]:
            f,c=fixture();c['runner'][key]=value
            self.assertFalse(assess(f,c,NOW)['fullProductionPreflightPassed'])

    def test_tiny_checkpoint_does_not_prove_production_controls(self):
        f,c=fixture();c['implementationEvidence']={'createOnlyCheckpointWrites':'successful tiny-object test'}
        r=assess(f,c,NOW)
        self.assertFalse(r['fullProductionPreflightPassed'])
        self.assertTrue(any('durableCumulativeReservations' in b for b in r['blockers']))

    def test_nonfinite_negative_and_zero_rates_rejected(self):
        for value in ['NaN','Infinity',-1,0,True]:
            f,c=fixture();c['rates']['egressUSDPerGiB']=value
            with self.assertRaises(ValueError):assess(f,c,NOW)

    def test_no_assumed_cleanup_or_small_storage(self):
        f,c=fixture();c['retentionLiabilityAcknowledged']=False
        c['proposedLimits']['storedBytes']=28*2**30
        r=assess(f,c,NOW)
        self.assertFalse(r['fullProductionPreflightPassed'])
        self.assertTrue(any('storage cannot' in b for b in r['blockers']))

    def test_existing_reservations_count_against_headroom(self):
        f,c=fixture();c['gcsBilling']['alreadyReservedUSD']=5
        self.assertFalse(assess(f,c,NOW)['fullProductionPreflightPassed'])


if __name__ == '__main__': unittest.main()
