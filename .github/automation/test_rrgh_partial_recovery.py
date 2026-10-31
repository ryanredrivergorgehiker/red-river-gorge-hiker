"""Offline, fail-closed regression tests for the single Wave023 partial recovery."""
import copy
import json
import unittest

from rrgh_map_supervisor_v2 import audit_run, Halt, REPO, BRANCH

PLAN = "b661abadce4c7977e2e3d7770e76d8912d8f9bd4d79bfac8a0531f097588dffb"
RECEIPT = "3b11557e069de5362569e6567afe6351b06cc7bb47d507de2707783f2db229ed"
FAILED = "usgs-topo-16-17570-25321"
RUN = {
    "id": 41225003991, "status": "completed", "conclusion": "failure",
    "run_attempt": 1, "head_branch": BRANCH,
    "head_sha": "a0d966e92654c412e1ae6259e77feb4a005321d9",
    "event": "push", "repository": {"full_name": REPO},
    "head_commit": {"message": "Lane20: execute verified new-territory wave023 20261031"},
}
JOBS = [
    {"name": "bounded-stage", "status": "completed", "conclusion": "failure"},
    {"name": "independent-recovery", "status": "completed", "conclusion": "success"},
]
ALLOCATION = {"attempts": 512, "sourceBytes": 1000, "sourceRequests": 512,
              "seconds": 12300, "storedBytes": 1000, "egressBytes": 1000,
              "classARequests": 3000, "classBRequests": 3000}
RECOVERY = {
    "phase": "independent-recovery",
    "receiptRef": {"bytes": 1487, "generation": "1793468516112546",
                   "key": "engineering/map-production/plans/" + PLAN +
                          "/slots/00002/receipt.json", "sha256": RECEIPT},
    "result": {
        "status": "partial-verified", "jobs": 207, "tiles": 207, "packageParts": 2,
        "allOutputHashesAndPixelsVerified": True, "allNewPackageChunksReadBack": True,
        "allExistingCachesPreserved": True, "sourcePixelGapJobs": [],
        "adjacentEdgesMeasured": 226,
        "nextCarry": {"chargedUSD": "8.18", "storedBytes": 17887533731,
                      "priorCompletedJobs": 4656, "priorRasterTiles": 47002,
                      "priorSunlightAssets": 320},
        "settlement": {
            "independentRecoveryComplete": False, "ambiguousAllocationRetained": True,
            "campaignID": "gorge-full-quality-125usd-20261031",
            "ceilingUSD": "125.00", "sequence": 23, "planSHA256": PLAN,
            "chargedUSD": "8.18", "storedBytes": 17887533731,
            "storageEstimateUSDPerMonth": "0.60", "remainingAuthorityUSD": "116.82",
            "originalAllocation": ALLOCATION, "retainedUsage": ALLOCATION,
            "demonstrablyUnused": {k: 0 for k in ALLOCATION},
        },
    },
}
def line(obj):
    return "2026-10-31T17:41:56Z " + json.dumps(obj, sort_keys=True)

def producer_lines():
    out = []
    for i in range(207):
        jid = f"usgs-topo-16-{17000+i}-{25000+i}"
        out.append(line({
            "job": jid, "completedJobs": i + 1,
            "durableJobReceipt": {
                "key": f"engineering/map-production/plans/{PLAN}/slots/00001/jobs/{jid}.json",
                "sha256": "a" * 64, "generation": str(1793468000000000+i),
            },
        }))
    out.append(line({"phase": "production", "status": "failed",
                     "diagnostic": {"lastJobConsidered": FAILED,
                                    "child": {"errorClass": "HTTPError"}}}))
    return out

class IncidentTests(unittest.TestCase):
    def verify(self, run=None, jobs=None, receipt=None, producer=None):
        return audit_run(copy.deepcopy(RUN if run is None else run),
                         copy.deepcopy(JOBS if jobs is None else jobs),
                         [line(copy.deepcopy(RECOVERY if receipt is None else receipt))],
                         producer_lines() if producer is None else producer)

    def test_verified_subset_is_not_dispatch_authority(self):
        report = self.verify()
        self.assertTrue(report["verified"])
        self.assertTrue(report["partialRecovered"])
        self.assertFalse(report["dispatchAuthorized"])
        self.assertEqual(report["acceptedJobs"], 4656)
        self.assertEqual(len(report["partialCompletedJobIDs"]), 207)
        self.assertEqual(report["failedJobID"], FAILED)

    def test_no_producer_log(self):
        with self.assertRaises(Halt):
            self.verify(producer=[])

    def test_wrong_source_head(self):
        run = copy.deepcopy(RUN)
        run["head_sha"] = "f" * 40
        with self.assertRaises(Halt):
            self.verify(run=run)

    def test_missing_receipt(self):
        receipt = copy.deepcopy(RECOVERY)
        receipt["receiptRef"]["sha256"] = "c" * 64
        with self.assertRaises(Halt):
            self.verify(receipt=receipt)

    def test_not_conservatively_retained(self):
        receipt = copy.deepcopy(RECOVERY)
        receipt["result"]["settlement"]["retainedUsage"]["attempts"] = 208
        with self.assertRaises(Halt):
            self.verify(receipt=receipt)

    def test_unverified_pixels(self):
        receipt = copy.deepcopy(RECOVERY)
        receipt["result"]["allOutputHashesAndPixelsVerified"] = False
        with self.assertRaises(Halt):
            self.verify(receipt=receipt)

    def test_wrong_failure(self):
        producer = producer_lines()
        producer[-1] = line({"phase": "production", "status": "failed",
                             "diagnostic": {"lastJobConsidered": FAILED,
                                            "child": {"errorClass": "PermissionError"}}})
        with self.assertRaises(Halt):
            self.verify(producer=producer)

    def test_noncontiguous_producer_sequence(self):
        producer = producer_lines()
        bad = json.loads(producer[1].split(" ", 1)[1])
        bad["completedJobs"] = 9
        producer[1] = line(bad)
        with self.assertRaises(Halt):
            self.verify(producer=producer)

if __name__ == "__main__":
    unittest.main()
