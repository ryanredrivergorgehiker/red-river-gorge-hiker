"""Local regression fixtures only. No Cloud, spending, or live autonomy evidence."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rrgh_required_inventory import Manifest, canonical, sha, extent, validate_baseline, build_database, overview_queue
from rrgh_controller_preflight import validate_successor, validate_cutover, validate_live_succession, assess, REPO, WORKER_BRANCH, PRODUCER_CONCURRENCY
from rrgh_package_readiness import assess as assess_package, check_file
from rrgh_source_window_intake import union_fraction, windows


def fixture():
    tile = extent(16, 17535, 25325)
    # Strict interior of one z16 cell; boundary overviews still require an edge policy.
    b = [tile[0]+.00001, tile[1]+.00001, tile[2]-.00001, tile[3]-.00001]
    profiles = {l: {"minZoom": 15, "maxZoom": z, "group": l if l in ("leaf-on", "leaf-off") else "core"}
                for l,z in (("hiking",17),("terrain",17),("usgs-topo",16),("leaf-on",18),("leaf-off",18))}
    spec = {"format":"rrgh-required-xyz-v1", "geographicRequirementVersion":"fixture-v1",
            "boundsWGS84":b,"boundaryRule":"inclusive-floor-corner-xyz-v1","scopeStatus":"provisional",
            "approvalReference":None,"profiles":profiles,
            "coreSupportingGroups":["sunlight","vectors","weather","shared-offline-dependencies"]}
    manifest = Manifest(spec)
    accepted, pending = "hiking-16-17535-25325", "terrain-16-17535-25325"
    carry = {"priorCompletedJobs":1,"priorRasterTiles":len(manifest.expand_job(accepted)),
             "priorSunlightAssets":320,"chargedUSD":"12.00","storedBytes":1000}
    ref = {"key":"engineering/map-production/plans/"+"a"*64+"/slots/00002/receipt.json",
           "generation":"1234","sha256":"b"*64,"bytes":1500}
    region = {"boundsWGS84":b,"profiles":{"core":{"hiking":17,"terrain":17,"usgs-topo":16},
              "leaf-on":{"leaf-on":18},"leaf-off":{"leaf-off":18}},
              "jobs":[{"id":pending,"layer":"terrain","outputTiles":[list(t[1:]) for t in sorted(manifest.expand_job(pending))]}]}
    plan = {"completedJobIDs":[accepted], "approvedJobIDs":[pending], "priorAttemptCounts":{accepted:1},
        "regionPlanSHA256":sha(region),"campaign":{"sequence":58,"previousRecovery":ref,"carry":carry,
        "sourcePixelGapQuarantines":[],"id":"gorge-full-quality-125usd-20261031","ceilingUSD":"125.00",
        "storageTargetUSDPerMonth":"2.00"},"maxConcurrency":1,"automaticRetryPermitted":False,"deleteAllowed":False,
        "slotJobs":{"1":[pending]},"jobPolicies":{pending:{"seconds":600}},
        "limits":{"attempts":1,"storedBytes":0,"egressBytes":0,"classARequests":1000,"classBRequests":0}}
    recovery = {"phase":"independent-recovery","receiptRef":ref,"result":{"status":"verified",
        "nextCarry":carry,"allOutputHashesAndPixelsVerified":True,"allNewPackageChunksReadBack":True,
        "allExistingCachesPreserved":True,"settlement":{"sequence":57,"planSHA256":"a"*64,
        "independentRecoveryComplete":True,"ambiguousAllocationRetained":False}}}
    audit = {"verified":True,"dispatchAuthorized":False,"partialRecovered":False,"wave":57,
             "receiptRef":ref,"nextCarry":carry,"acceptedJobs":1}
    allowance = {"cloudStorageAllowance":{"planSHA256":sha(plan),"reservedWorstCaseUSD":".012"}}
    return manifest,plan,region,recovery,audit,allowance


class InventoryTests(unittest.TestCase):
    def test_hash_is_reproducible_and_scope_bound(self):
        m,*_ = fixture()
        self.assertEqual(m.digest(), Manifest(copy.deepcopy(m.spec)).digest())
        changed = copy.deepcopy(m.spec); changed["geographicRequirementVersion"] = "v2"
        self.assertNotEqual(m.digest(), Manifest(changed).digest())

    def test_boundary_rule_is_existing_inclusive_grid(self):
        m,*_ = fixture()
        spec = copy.deepcopy(m.spec)
        spec["boundsWGS84"] = extent(16,17535,25325)
        full = Manifest(spec)
        self.assertEqual(full.grids["hiking",16][1],17536)

    def test_unknown_approval_rejected(self):
        m,*_ = fixture(); spec=copy.deepcopy(m.spec); spec["scopeStatus"]="approved"
        with self.assertRaisesRegex(ValueError,"approval reference"):
            Manifest(spec)

    def test_exact_baseline(self):
        m,p,r,v,*_ = fixture()
        self.assertEqual(len(validate_baseline(m,p,r,v,sha(p))),5)

    def test_wrong_immutable_plan_rejected(self):
        m,p,r,v,*_ = fixture()
        with self.assertRaisesRegex(ValueError,"plan hash"):
            validate_baseline(m,p,r,v,"f"*64)

    def test_wrong_recovery_ref_rejected(self):
        m,p,r,v,*_ = fixture(); v=copy.deepcopy(v);v["receiptRef"]["generation"]="999"
        with self.assertRaisesRegex(ValueError,"lineage"):
            validate_baseline(m,p,r,v,sha(p))

    def test_duplicate_accepted_jobs_rejected(self):
        m,p,r,v,*_ = fixture();p["completedJobIDs"]*=2
        with self.assertRaisesRegex(ValueError,"Duplicate/missing"):
            validate_baseline(m,p,r,v,sha(p))

    def test_no_future_source_counted_as_accepted(self):
        m,p,r,v,*_ = fixture()
        accepted = validate_baseline(m,p,r,v,sha(p))
        self.assertFalse(any(t[0]=="terrain" for t in accepted))

    def test_producer_geometry_cannot_drift(self):
        m,p,r,v,*_ = fixture();r["jobs"][0]["outputTiles"].pop();p["regionPlanSHA256"]=sha(r)
        with self.assertRaisesRegex(ValueError,"expansion"):
            validate_baseline(m,p,r,v,sha(p))

    def test_inventory_keeps_dimensions_and_historical_limit(self):
        m,p,r,v,*_ = fixture()
        j="leaf-off-16-17535-25325";p["campaign"]["sourcePixelGapQuarantines"]=[j];p["priorAttemptCounts"][j]=1
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"inventory.sqlite"
            summary=build_database(path,m,p,r,v,sha(p),"c"*40)
            self.assertFalse(summary["historicalBytesReread"])
            with sqlite3.connect(path) as db:
                row=db.execute("SELECT independent_verification,source_coverage,package_membership,sha256 FROM inventory WHERE layer='leaf-off' AND z=16").fetchone()
                self.assertEqual(row,("quarantined","awaiting_source_validation","unpackaged",None))
                accepted=db.execute("SELECT independent_verification,sha256 FROM inventory WHERE layer='hiking' AND z=16").fetchone()
                self.assertEqual(accepted,("verified",None))
            with self.assertRaises(FileExistsError):
                build_database(path,m,p,r,v,sha(p),"c"*40)

    def test_overview_queue_exposes_missing_and_outside_children(self):
        m,p,r,v,*_ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"i.sqlite";build_database(path,m,p,r,v,sha(p),"c"*40)
            with sqlite3.connect(path) as db:
                queue=list(overview_queue(db))
            h=next(q for q in queue if q["tile"][0]=="hiking")
            self.assertEqual(h["dependencyStatus"],"edge_policy_required")
            self.assertEqual(len(h["outsideFootprintChildren"]),3)
            self.assertFalse(h["productionReady"])
            self.assertEqual(next(q for q in queue if q["tile"][0]=="terrain")["dependencyStatus"],"missing_children")

    def test_existing_outside_scope_single_tile_is_preserved(self):
        m,p,r,v,*_ = fixture();p["completedJobIDs"].append("hiking-15-100-100")
        p["campaign"]["carry"]["priorCompletedJobs"]+=1;p["campaign"]["carry"]["priorRasterTiles"]+=1
        with tempfile.TemporaryDirectory() as tmp:
            summary=build_database(Path(tmp)/"i.sqlite",m,p,r,v,sha(p),"c"*40)
            self.assertEqual(summary["outsideScopeAcceptedPreserved"],1)
            self.assertEqual(summary["verified"],5)


class SourceTests(unittest.TestCase):
    def test_overlap_does_not_double_count(self):
        self.assertEqual(union_fraction([0,0,2,2],[[0,0,2,2],[0,0,2,2]]),1)

    def test_bbox_intersection_is_not_full_coverage(self):
        self.assertEqual(union_fraction([0,0,2,2],[[0,0,1,2]]),.5)

    def test_mosaic_can_cover_window_with_two_sources(self):
        self.assertEqual(union_fraction([0,0,2,2],[[0,0,1,2],[1,0,2,2]]),1)

    def test_hole_and_outside_sources_remain_missing(self):
        self.assertEqual(union_fraction([0,0,2,2],[[0,0,2,1],[2,0,3,2]]),.5)
        self.assertEqual(union_fraction([0,0,2,2],[]),0)

    def test_full_metadata_never_promotes_pixels(self):
        m,*_=fixture();catalog={g:[{"id":"fixture", "bbox":[-84,37,-83,39]}] for g in ("hiking","dem","leaf-off")}
        for w in windows(m,catalog):
            self.assertTrue(w["metadataFullWindowCovered"])
            self.assertFalse(w["productionReady"])
            self.assertEqual(w["sourceCoverage"],"awaiting_source_validation")


class ControllerTests(unittest.TestCase):
    def test_candidate_admission_does_not_authorize_dispatch(self):
        _,p,_,_,a,e=fixture()
        result=assess(p,e,a,{},datetime.now(timezone.utc))
        self.assertEqual(result["candidate"]["sequence"],58)
        self.assertFalse(result["cutoverEvidenceComplete"])
        self.assertFalse(result["dispatchAuthorized"])

    def test_consumed_attempt_cannot_be_reused(self):
        _,p,_,_,a,e=fixture();p["priorAttemptCounts"][p["approvedJobIDs"][0]]=1;e["cloudStorageAllowance"]["planSHA256"]=sha(p)
        with self.assertRaisesRegex(ValueError,"Consumed"):
            validate_successor(p,e,a)

    def test_forward_plan_not_receipt_bound_rejected(self):
        _,p,_,_,a,e=fixture();a=copy.deepcopy(a);a["receiptRef"]["sha256"]="d"*64
        with self.assertRaisesRegex(ValueError,"Checkpoint"):
            validate_successor(p,e,a)

    def test_budget_reserve_and_nonfinite_rejected(self):
        for money in ("123.00","NaN","Infinity"):
            _,p,_,_,a,e=fixture();p["campaign"]["carry"]["chargedUSD"]=money;e["cloudStorageAllowance"]["planSHA256"]=sha(p)
            with self.assertRaises((ValueError,ArithmeticError)):
                validate_successor(p,e,a)

    def cutover(self):
        *_,audit,_=fixture();now=datetime(2026,11,2,tzinfo=timezone.utc)
        e={"format":"rrgh-controller-cutover-v1","repository":REPO,"observedAt":now.isoformat(),
           "checkpoint":audit["receiptRef"],"allProducerEntryPointsEnumerated":True,"activeRuns":[],
           "legacyInitiationFenced":True,"fenceReadbackRef":"fixture-only","concurrencyGroup":PRODUCER_CONCURRENCY,
           "ownership":{"owner":"controller","epoch":1,"generation":"123","readbackRef":"fixture-only"},
           "acceptedOutputPreservationVerified":True,"authentication":{"cloudProbePassed":True,
            "sourceGuardPassed":True,"workflow":"offline-map-restricted-dispatch.yml","event":"workflow_dispatch",
            "branch":WORKER_BRANCH,"authorizationReference":"fixture-only","probeRun":123},
           "githubBilling":{"hardStopVerified":True,"hardCeilingUSD":350,"observationRef":"fixture-only",
            "spentUSD":"300","reservedUSD":"5"},
           "rollbackPolicy":"fence-reconcile-latest-checkpoint-fresh-allocation"}
        return e,audit,now

    def test_unfenced_or_running_producer_blocks_cutover(self):
        for change in ({"legacyInitiationFenced":False},{"activeRuns":[123]},{"allProducerEntryPointsEnumerated":False}):
            e,a,n=self.cutover();e.update(change)
            with self.assertRaises(ValueError):validate_cutover(e,a,n)

    def test_stale_or_future_observation_rejected(self):
        e,a,n=self.cutover()
        for delta in (301,-1):
            with self.assertRaises(ValueError):validate_cutover(e,a,n+timedelta(seconds=delta))

    def test_authentication_requires_cloud_and_source_guards(self):
        for field in ("cloudProbePassed","sourceGuardPassed"):
            e,a,n=self.cutover();e["authentication"][field]=False
            with self.assertRaisesRegex(ValueError,"authentication"):validate_cutover(e,a,n)

    def records(self):
        # Structural validation fixtures; these numbers are not real production runs.
        a={"evidenceKind":"live-github-cloud","runAttempt":1,"producerConclusion":"success",
           "recoveryConclusion":"success","runID":100,"planSHA256":"a"*64,"sourceSHA":"c"*40,
           "verifiedNewJobs":1,"verifiedNewTiles":1,"recoveryReceipt":{"fixture":1},
           "independentAuditRef":"fixture-only","sequence":58}
        b={**a,"runID":101,"planSHA256":"b"*64,"sequence":59,"recoveryReceipt":{"fixture":2},
           "predecessorReceipt":a["recoveryReceipt"],"triggerActor":"github-actions[bot]",
           "triggerEvent":"workflow_dispatch","controllerParentRun":100,"controllerDispatchReceipt":"fixture-only"}
        return [a,b]

    def test_structural_successor_contract(self):
        self.assertTrue(validate_live_succession(self.records()))

    def test_manual_successor_is_not_autonomy(self):
        r=self.records();r[1]["triggerActor"]="owner"
        with self.assertRaisesRegex(ValueError,"controller"):validate_live_succession(r)

    def test_source_only_or_single_or_replayed_run_rejected(self):
        with self.assertRaises(ValueError):validate_live_succession(self.records()[:1])
        r=self.records();r[1]["verifiedNewTiles"]=0
        with self.assertRaises(ValueError):validate_live_succession(r)
        r=self.records();r[1]["planSHA256"]=r[0]["planSHA256"]
        with self.assertRaises(ValueError):validate_live_succession(r)


class PackageTests(unittest.TestCase):
    def test_missing_tiles_and_support_block_core(self):
        m,p,r,v,*_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"i.sqlite";summary=build_database(path,m,p,r,v,sha(p),"c"*40)
            package={"format":"rrgh-package-evidence-v1","packageID":"core","version":"test",
                     "group":"core","requiredManifestSHA256":summary["requiredManifestSHA256"],"tiles":[]}
            with sqlite3.connect(path) as db:result=assess_package(db,package,Path(tmp))
            self.assertFalse(result["complete"])
            self.assertFalse(result["supportingAssetsComplete"])
            self.assertGreater(result["missingRasterTiles"],0)

    def test_reconstructed_acceptance_does_not_prove_package_bytes(self):
        m,p,r,v,*_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"i.sqlite";summary=build_database(path,m,p,r,v,sha(p),"c"*40)
            package={"format":"rrgh-package-evidence-v1","packageID":"core","version":"test","group":"core",
                "requiredManifestSHA256":summary["requiredManifestSHA256"],
                "tiles":[{"tile":["hiking",16,17535,25325],"path":"fake.png","sha256":"a"*64,"bytes":100}]}
            with sqlite3.connect(path) as db:result=assess_package(db,package,Path(tmp))
            self.assertEqual(result["tileEvidenceErrors"],1)
            self.assertFalse(result["complete"])

    def test_file_integrity_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"member").write_bytes(b"verified-fixture")
            entry={"path":"member","bytes":16,"sha256":hashlib.sha256(b"verified-fixture").hexdigest()}
            check_file(root,entry)
            for changed in ({**entry,"path":"../member"},{**entry,"bytes":17},{**entry,"sha256":"a"*64}):
                with self.assertRaises(ValueError):check_file(root,changed)
            (root/"link").symlink_to(root/"member")
            with self.assertRaises(ValueError):check_file(root,{**entry,"path":"link"})


if __name__=="__main__":
    unittest.main()
