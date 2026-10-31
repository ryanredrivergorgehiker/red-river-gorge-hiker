"""Fast, offline policy tests for read-only map-supervisor gate."""
import unittest
from rrgh_map_supervisor import audit_run, Halt, REPO, BRANCH

PLAN = "a" * 64
RECEIPT = "b" * 64
RUN = {
    "status": "completed", "conclusion": "success", "run_attempt": 1,
    "head_branch": BRANCH, "event": "push", "id": 123,
    "head_commit": {"message": "Lane20: execute verified new-territory wave021 20261031"},
    "repository": {"full_name": REPO},
}
JOBS = [
    {"name": "bounded-stage", "status": "completed", "conclusion": "success"},
    {"name": "independent-recovery", "status": "completed", "conclusion": "success"}
]
REPORT = {
    "phase": "independent-recovery",
    "receiptRef": {
        "bytes": 1546, "generation": "1793461561304485",
        "key": "engineering/map-production/plans/" + PLAN + "/slots/00002/receipt.json",
        "sha256": RECEIPT
    },
    "result": {
        "status": "verified", "jobs": 512, "allOutputHashesAndPixelsVerified": True,
        "allNewPackageChunksReadBack": True, "allExistingCachesPreserved": True,
        "sourcePixelGapJobs": [], "adjacentEdgesMeasured": 9610,
        "nextCarry": {
            "chargedUSD": "7.3665", "storedBytes": 15970352688,
            "priorCompletedJobs": 3937, "priorRasterTiles": 41173, "priorSunlightAssets": 320
        },
        "settlement": {
            "independentRecoveryComplete": True, "ambiguousAllocationRetained": False,
            "campaignID": "gorge-full-quality-25usd-20261030", "sequence": 21,
            "chargedUSD": "7.3665", "storedBytes": 15970352688,
            "storageEstimateUSDPerMonth": "0.54", "remainingAuthorityUSD": "17.63",
            "ceilingUSD": "25.00", "planSHA256": PLAN
        }
    }
}
import copy, json

def lines(report):
    return ["2026-10-31T15:46:00Z " + json.dumps(report, sort_keys=True)]

class SupervisorTests(unittest.TestCase):
    def test_success_never_authorizes_dispatch_without_live_billing(self):
        out = audit_run(copy.deepcopy(RUN), copy.deepcopy(JOBS), lines(REPORT))
        self.assertTrue(out["verified"])
        self.assertFalse(out["dispatchAuthorized"])
        self.assertEqual(out["acceptedRasterTiles"], 41173)

    def check_reject(self, adjust_run=None, adjust_jobs=None, adjust_report=None):
        run, jobs, report = copy.deepcopy(RUN), copy.deepcopy(JOBS), copy.deepcopy(REPORT)
        if adjust_run: adjust_run(run)
        if adjust_jobs: adjust_jobs(jobs)
        if adjust_report: adjust_report(report)
        with self.assertRaises(Halt):
            audit_run(run, jobs, lines(report))

    def test_reject_failed_producer(self):
        self.check_reject(adjust_jobs=lambda jobs: jobs[0].update(conclusion="failure"))

    def test_reject_rerun(self):
        self.check_reject(adjust_run=lambda run: run.update(run_attempt=2))

    def test_reject_wrong_branch(self):
        self.check_reject(adjust_run=lambda run: run.update(head_branch="main"))

    def test_reject_ambiguous_settlement(self):
        self.check_reject(adjust_report=lambda r: r["result"]["settlement"].update(ambiguousAllocationRetained=True))

    def test_reject_pixels(self):
        self.check_reject(adjust_report=lambda r: r["result"].update(allOutputHashesAndPixelsVerified=False))

    def test_reject_gaps(self):
        self.check_reject(adjust_report=lambda r: r["result"].update(sourcePixelGapJobs=["leaf-on-16-1-1"]))

    def test_reject_unverified_receipt(self):
        self.check_reject(adjust_report=lambda r: r["receiptRef"].update(sha256="invalid"))

    def test_reject_invoice_overrun(self):
        self.check_reject(adjust_report=lambda r: r["result"]["settlement"].update(storageEstimateUSDPerMonth="2.01"))

    def test_reject_ceiling_overrun(self):
        self.check_reject(adjust_report=lambda r: r["result"]["settlement"].update(chargedUSD="126.00"))

    def test_reject_forged_plan(self):
        self.check_reject(adjust_report=lambda r: r["result"]["settlement"].update(planSHA256="c"*64))

    def test_reject_duplicate_recovery(self):
        with self.assertRaises(Halt):
            audit_run(copy.deepcopy(RUN), copy.deepcopy(JOBS), lines(REPORT)+lines(REPORT))

    def test_reject_missing_recovery(self):
        with self.assertRaises(Halt):
            audit_run(copy.deepcopy(RUN), copy.deepcopy(JOBS), [])

if __name__ == "__main__":
    unittest.main()
