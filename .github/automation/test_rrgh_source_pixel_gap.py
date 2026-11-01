#!/usr/bin/env python3
"""Offline regression evidence for the verified Wave037 source gap, never a Cloud receipt."""
import copy,json,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from rrgh_map_supervisor_v2 import audit_run,Halt,PREFIX
PLAN="f6678688ba3bd7c15c8515e522cc079e2289893002c19aa63b4ee25d9d7f46b3"
GAPS=["terrain-16-17539-25316","terrain-16-17538-25317","leaf-off-16-17538-25318"]
SUCCESS=["hiking-16-17535-25325","hiking-16-17535-25326","hiking-16-17535-25327",
         "terrain-16-17539-25318","leaf-off-16-17539-25317","leaf-off-16-17539-25319"]
RUN={"status":"completed","conclusion":"success","run_attempt":1,
     "head_branch":"lane20/offline-production-preflight-20261029","event":"push","id":41343009849,
     "head_sha":"5d82a616819410f200d6d49ab8300a2b558160a3",
     "head_commit":{"message":"Lane20: execute verified new-territory wave037 20261031"},
     "repository":{"full_name":"ryanredrivergorgehiker/red-river-gorge-hiker"}}
JOBS=[{"name":"bounded-stage","status":"completed","conclusion":"success"},
      {"name":"independent-recovery","status":"completed","conclusion":"success"}]
REPORT={"phase":"independent-recovery",
 "receiptRef":{"bytes":1518,"generation":"1793562351250637",
  "key":PREFIX+PLAN+"/slots/00002/receipt.json",
  "sha256":"75a28886f5a3c97e58fcd7664b0573a731185bbfd83604eadd1314b63d6b4794"},
 "result":{"status":"verified","jobs":6,"tiles":62,"packageParts":7,
  "allOutputHashesAndPixelsVerified":True,"allNewPackageChunksReadBack":True,
  "allExistingCachesPreserved":True,"adjacentEdgesMeasured":78,
  "sourcePixelGapJobs":GAPS,"pixelGapAttemptsConsumed":3,
  "nextCarry":{"chargedUSD":"10.82569141765992045402526856","storedBytes":23020384953,
     "priorCompletedJobs":10879,"priorRasterTiles":116021,"priorSunlightAssets":320},
  "settlement":{"independentRecoveryComplete":True,"ambiguousAllocationRetained":False,
     "campaignID":"gorge-full-quality-125usd-20261031","sequence":37,
     "chargedUSD":"10.82569141765992045402526856",
     "storedBytes":23020384953,"storageEstimateUSDPerMonth":"0.7718185505904257297515869140",
     "remainingAuthorityUSD":"114.1743085823400795459747315",
     "ceilingUSD":"125.00","planSHA256":PLAN}}}
def producer_lines():
    lines=[]
    for n,j in enumerate(SUCCESS,1):
        lines.append(json.dumps({"completedJobs":n,"job":j,
          "durableJobReceipt":{"key":PREFIX+PLAN+"/slots/00001/jobs/"+j+".json",
          "sha256":"c"*64,"generation":"1"}}))
    for j in GAPS:
        lines.append(json.dumps({"attemptConsumed":True,"job":j,
             "sourceQualityUnchanged":True,"status":"source-pixel-gap-quarantined"}))
    lines.append(json.dumps({"phase":"production","status":"bounded-stop",
                             "jobs":6,"sourcePixelGapJobs":GAPS}))
    return lines
def report_lines(r=REPORT):
    return [json.dumps(r)]
class SourcePixelGapEvidenceTests(unittest.TestCase):
    def test_accept_exact_source_pinned_readback_but_never_dispatch(self):
        result=audit_run(copy.deepcopy(RUN),copy.deepcopy(JOBS),
                 report_lines(copy.deepcopy(REPORT)),producer_lines())
        self.assertTrue(result["verified"])
        self.assertFalse(result["dispatchAuthorized"])
        self.assertEqual(result["sourceCompletedJobIDs"],SUCCESS)
        self.assertEqual(result["sourcePixelGapJobs"],GAPS)
        self.assertEqual(result["acceptedJobs"],10879)
        self.assertEqual(result["acceptedRasterTiles"],116021)
    def test_reject_unconfirmed_gap(self):
        r=copy.deepcopy(REPORT);r["result"]["sourcePixelGapJobs"][0]="terrain-16-0-0"
        with self.assertRaises(Halt):
            audit_run(RUN,JOBS,report_lines(r),producer_lines())
    def test_reject_missing_gap_consumption(self):
        r=copy.deepcopy(REPORT);r["result"]["pixelGapAttemptsConsumed"]=2
        with self.assertRaises(Halt):
            audit_run(RUN,JOBS,report_lines(r),producer_lines())
    def test_reject_missing_successful_durable_job(self):
        with self.assertRaises(Halt):
            audit_run(RUN,JOBS,report_lines(),producer_lines()[1:])
    def test_reject_gap_not_source_quality_protected(self):
        broken=producer_lines();i=6;j=json.loads(broken[i]);j["sourceQualityUnchanged"]=False;broken[i]=json.dumps(j)
        with self.assertRaises(Halt):
            audit_run(RUN,JOBS,report_lines(),broken)
    def test_reject_invalid_receipt(self):
        r=copy.deepcopy(REPORT);r["receiptRef"]["sha256"]="invalid"
        with self.assertRaises(Halt):
            audit_run(RUN,JOBS,report_lines(r),producer_lines())
if __name__=="__main__":unittest.main()
