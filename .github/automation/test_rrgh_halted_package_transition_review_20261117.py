#!/usr/bin/env python3
"""Test-only approval-boundary review. No Cloud credentials or state mutation."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
import rrgh_dispatcher as d
import rrgh_halted_package_transition_review_20261117 as review


class HaltedControllerProposal(unittest.TestCase):
    def test_exact_historical_source_and_funded_proposed_ordinal27(self):
        p=review.proposal()
        self.assertEqual((p['historicallyVerifiedLayoutParts'],p['remainingParts'],p['remainingIndexes']),
                         (122,90,3))
        self.assertEqual(p['newOrdinalProposal'],27)
        self.assertEqual(p['retryCountPreservedAt'],2)
        self.assertEqual(p['historicalRetainedFailures'],5)
        self.assertEqual(p['candidateProtectedCodeDigest'],review.CANDIDATE_DIGEST)
        self.assertEqual(p['liveControllerBlobSHA'],review.LIVE_BLOB_SHA)
        self.assertEqual(p['independentAcceptedReceiptSHA256'],review.ACCEPTED_RECEIPT)
        self.assertEqual(p['candidatePR'],140)
        self.assertTrue(len(p['hypotheticalNewPlanSHA256'])==64)
        self.assertFalse(p['codeMerged'])
        self.assertFalse(p['ownerAuthorizationPresent'])
        self.assertFalse(p['cloudDispatchAuthorized'])
        self.assertFalse(p['realWIFAcceptanceTested'])
        self.assertEqual(p['controllerWrites'],0)
        self.assertEqual(p['cloudCalls'],0)
        print('HALTED_OWNER_PROPOSAL_SOURCE_ONLY '+json.dumps(p,sort_keys=True))

    def test_stale_controller_and_unreviewed_new_digest_are_rejected(self):
        old=json.loads((ROOT/d.STATE).read_text())
        self.assertEqual(d.local_digest(ROOT),review.OLD_DIGEST)
        # A new digest without an exact owner CAS transition must fail even
        # if a caller allows legacy upgrades.
        future=copy.deepcopy(old)
        future['controlDigest']=review.CANDIDATE_DIGEST
        for allow in (False,True):
            with self.subTest(allow_upgrade=allow):
                with self.assertRaisesRegex(d.Halt,'Reviewed controller code changed'):
                    d.validate_state(future,ROOT,allow_upgrade=allow)
        self.assertEqual(old['status'],'halted')

    def test_source_state_tampering_is_refused_before_any_planning(self):
        state_path=str((ROOT/d.STATE).resolve())
        original=Path.read_bytes
        old=(ROOT/d.STATE).read_bytes()
        mutated=json.loads(old)
        mutated['package']['lastVerified']['verifiedParts']=31
        tampered=json.dumps(mutated).encode()
        def substitute(self):
            if str(self.resolve())==state_path:return tampered
            return original(self)
        with patch.object(Path,'read_bytes',new=substitute):
            with self.assertRaisesRegex(ValueError,'Live halted controller blob moved'):
                review.proposal()
        self.assertEqual((ROOT/d.STATE).read_bytes(),old)

    def test_review_code_has_no_credential_or_cloud_or_dispatch_surface(self):
        text=(ROOT/'.github/automation/rrgh_halted_package_transition_review_20261117.py').read_text()
        forbidden=['api.cas(','.dispatch(', 'google-github-actions/auth','gcloud','GH_TOKEN',
                   'os.environ[','write_text(','.write_bytes(']
        for word in forbidden:
            self.assertNotIn(word,text,word)
        self.assertNotIn('rrgh_halted_package_transition_review_20261117.py',d.CODE_FILES)

    def test_cost_headroom_is_not_approval_for_unbounded_retries(self):
        from test_rrgh_full_package_historical_budget_20261117 import recompute
        from decimal import Decimal
        from gorge_campaign_budget import monthly
        e=recompute()
        self.assertGreater(Decimal(e['remainingCloudHeadroomUSD']),0)
        self.assertGreater(Decimal(e['monthlyStorageHeadroomUSD']),0)
        current=47342383951
        self.assertGreater(monthly(current+3*e['originalAllProspectiveStoredBytes']),Decimal('2'))
        self.assertEqual(e['additionalTransportFailuresAssumed'],0)


if __name__=='__main__':unittest.main()
