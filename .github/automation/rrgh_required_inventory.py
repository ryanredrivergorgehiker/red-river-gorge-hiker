#!/usr/bin/env python3
"""Reproducible required XYZ manifest and evidence-separated offline inventory.

Pure local processing. Imports no producer code and never changes source plans,
Cloud objects, workflows, or authorization. Historical acceptance is explicitly
receipt-backed reconstruction, not a new per-tile byte or pixel readback.
"""
import argparse
import base64
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import zlib


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def xy(lon, lat, z):
    n = 2 ** z
    return (math.floor((lon + 180) / 360 * n),
            math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def extent(z, x, y):
    n = 2 ** z
    lat = lambda a: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * a / n))))
    return [x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)]


class Manifest:
    def __init__(self, spec):
        require(spec.get("format") == "rrgh-required-xyz-v1", "Unknown manifest format")
        b = spec["boundsWGS84"]
        require(len(b) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in b),
                "Invalid bounds")
        require(-180 <= b[0] < b[2] < 180 and -85.05112878 < b[1] < b[3] < 85.05112878,
                "Unsupported or wrapped Web Mercator bounds")
        require(spec["boundaryRule"] == "inclusive-floor-corner-xyz-v1", "Unknown edge rule")
        require(spec["scopeStatus"] in ("provisional", "approved"), "Missing scope decision")
        require(spec["scopeStatus"] != "approved" or bool(spec.get("approvalReference")),
                "Approved scope needs governing approval reference")
        require(bool(spec.get("geographicRequirementVersion")), "Missing geography version")
        require(set(spec["profiles"]) == {"hiking", "terrain", "usgs-topo", "leaf-on", "leaf-off"},
                "All five raster layers required")
        self.spec = spec
        self.grids = {}
        self.groups = {}
        for layer, profile in sorted(spec["profiles"].items()):
            lo, hi = profile["minZoom"], profile["maxZoom"]
            require(type(lo) is int and type(hi) is int and 0 <= lo <= 16 <= hi <= 18,
                    "Invalid zoom profile")
            expected = layer if layer in ("leaf-on", "leaf-off") else "core"
            require(profile["group"] == expected, "Core/optional membership changed")
            self.groups[layer] = expected
            for z in range(lo, hi + 1):
                left, bottom = xy(b[0], b[1], z)
                right, top = xy(b[2], b[3], z)
                self.grids[layer, z] = (left, right, top, bottom)
        require(self.count() <= 2_000_000, "Manifest exceeds local safety bound")
        self.revision = sha(spec)

    def count(self):
        return sum((r-l+1)*(b-t+1) for l, r, t, b in self.grids.values())

    def contains(self, tile):
        layer, z, x, y = tile
        if (layer, z) not in self.grids:
            return False
        l, r, t, b = self.grids[layer, z]
        return l <= x <= r and t <= y <= b

    def tiles(self):
        for (layer, z), (l, r, t, b) in sorted(self.grids.items()):
            for x in range(l, r+1):
                for y in range(t, b+1):
                    yield (layer, z, x, y)

    def record(self, tile):
        layer, z, x, y = tile
        return {"layer": layer, "z": z, "x": x, "y": y,
                "boundsWGS84": extent(z, x, y), "group": self.groups[layer],
                "geographicRequirementVersion": self.spec["geographicRequirementVersion"],
                "manifestRevision": self.revision, "sourceProvenance": None}

    def digest(self):
        h = hashlib.sha256()
        for tile in self.tiles():
            h.update(canonical(self.record(tile)))
        return h.hexdigest()

    def expand_job(self, job):
        match = re.fullmatch(r"(hiking|terrain|usgs-topo|leaf-on|leaf-off)-(\d+)-(\d+)-(\d+)", job)
        require(match is not None, "Malformed job identity")
        layer, z, x, y = match.groups()
        z, x, y = int(z), int(x), int(y)
        require(0 <= z <= 18 and 0 <= x < 2**z and 0 <= y < 2**z, "Invalid XYZ job")
        require(self.spec["profiles"][layer]["minZoom"] <= z <= self.spec["profiles"][layer]["maxZoom"],
                "Historical job needs a separately supported zoom profile")
        # z16 native windows include only children inside the documented grid.
        # Older single-tile overview jobs are never extrapolated to descendants.
        if z == 16 and layer != "usgs-topo":
            result = set()
            for zz in range(16, self.spec["profiles"][layer]["maxZoom"]+1):
                n = 2**(zz-16)
                for dx in range(n):
                    for dy in range(n):
                        tile = (layer, zz, x*n+dx, y*n+dy)
                        if self.contains(tile):
                            result.add(tile)
            require(bool(result), "Outside-scope source window requires explicit historical output records")
            return result
        return {(layer, z, x, y)}


def validate_baseline(manifest, plan, region, recovery, expected_plan_sha):
    require(sha(plan) == expected_plan_sha, "Immutable plan hash mismatch")
    require(sha(region) == plan["regionPlanSHA256"], "Region plan hash mismatch")
    require(region["boundsWGS84"] == manifest.spec["boundsWGS84"], "Plan geography differs")
    profiles = {l: p["maxZoom"] for l, p in manifest.spec["profiles"].items()}
    require({l: z for g in region["profiles"].values() for l, z in g.items()} == profiles,
            "Source-specific zoom ceilings differ")
    c, result = plan["campaign"], recovery["result"]
    require(recovery.get("phase") == "independent-recovery" and
            c["previousRecovery"] == recovery["receiptRef"] and
            c["carry"] == result["nextCarry"], "Independent recovery lineage mismatch")
    require(result.get("status") == "verified" and
            all(result.get(k) is True for k in ("allOutputHashesAndPixelsVerified",
                "allNewPackageChunksReadBack", "allExistingCachesPreserved")),
            "Baseline lacks complete independent verification")
    settlement = result["settlement"]
    require(settlement.get("sequence") == c["sequence"]-1 and
            settlement.get("independentRecoveryComplete") is True and
            settlement.get("ambiguousAllocationRetained") is False,
            "Predecessor is not completely settled")
    ref = recovery["receiptRef"]
    require(ref["key"] == "engineering/map-production/plans/" + settlement["planSHA256"] +
            "/slots/00002/receipt.json", "Receipt key does not bind predecessor plan")
    require(re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) and
            re.fullmatch(r"[1-9][0-9]*", str(ref["generation"])), "Invalid receipt identity")
    require(len(plan["completedJobIDs"]) == len(set(plan["completedJobIDs"])) ==
            c["carry"]["priorCompletedJobs"], "Duplicate/missing accepted jobs")
    accepted = {}
    for job in plan["completedJobIDs"]:
        for tile in manifest.expand_job(job):
            require(tile not in accepted, "Overlapping accepted output identities")
            accepted[tile] = job
    require(len(accepted) == c["carry"]["priorRasterTiles"], "Accepted tile count differs from recovery")
    gaps = c.get("sourcePixelGapQuarantines", [])
    require(len(gaps) == len(set(gaps)), "Duplicate quarantined attempts")
    require(not set(plan["approvedJobIDs"]) & set(plan["completedJobIDs"]), "Successor replays accepted jobs")
    for job in gaps:
        require(plan["priorAttemptCounts"].get(job, 0) > 0 and
                job not in plan["completedJobIDs"], "Quarantine/accepted history conflicts")
    require(plan["approvedJobIDs"] == [j["id"] for j in region["jobs"]], "Allocation differs from region")
    for job in region["jobs"]:
        require(manifest.expand_job(job["id"]) == {(job["layer"], *v) for v in job["outputTiles"]},
                "Producer output expansion differs from required manifest")
    return accepted


SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE required(layer TEXT,z INTEGER,x INTEGER,y INTEGER,download_group TEXT,
 west REAL,south REAL,east REAL,north REAL,PRIMARY KEY(layer,z,x,y));
CREATE TABLE accepted(layer TEXT,z INTEGER,x INTEGER,y INTEGER,job_id TEXT,
 verification_basis TEXT,receipt_ref TEXT,object_key TEXT,generation TEXT,
 sha256 TEXT,bytes INTEGER,source_identity TEXT,PRIMARY KEY(layer,z,x,y));
CREATE TABLE attempts(job_id TEXT PRIMARY KEY,attempt_count INTEGER,outcome TEXT);
CREATE TABLE attempt_tiles(job_id TEXT,layer TEXT,z INTEGER,x INTEGER,y INTEGER,
 PRIMARY KEY(job_id,layer,z,x,y));
CREATE TABLE packages(package_id TEXT,version TEXT,manifest_sha256 TEXT,validation TEXT,
 delivery TEXT,PRIMARY KEY(package_id,version));
CREATE TABLE package_tiles(package_id TEXT,version TEXT,layer TEXT,z INTEGER,x INTEGER,y INTEGER,
 sha256 TEXT,PRIMARY KEY(package_id,version,layer,z,x,y));
CREATE TABLE device_acceptance(package_id TEXT,version TEXT,app_version TEXT,result TEXT,evidence_ref TEXT,
 PRIMARY KEY(package_id,version,app_version));
CREATE VIEW inventory AS SELECT r.*, CASE WHEN a.job_id IS NOT NULL THEN 'produced'
 WHEN EXISTS(SELECT 1 FROM attempt_tiles t WHERE (t.layer,t.z,t.x,t.y)=(r.layer,r.z,r.x,r.y))
 THEN 'failed_attempt' ELSE 'unprocessed' END production,
 CASE WHEN a.job_id IS NOT NULL THEN 'verified'
 WHEN EXISTS(SELECT 1 FROM attempt_tiles t WHERE (t.layer,t.z,t.x,t.y)=(r.layer,r.z,r.x,r.y))
 THEN 'quarantined' ELSE 'awaiting_verification' END independent_verification,
 CASE WHEN a.job_id IS NULL THEN 'awaiting_source_validation' ELSE 'validated_at_historical_output' END source_coverage,
 a.verification_basis,a.receipt_ref,a.object_key,a.generation,a.sha256,a.bytes,a.source_identity,
 CASE WHEN EXISTS(SELECT 1 FROM package_tiles p WHERE (p.layer,p.z,p.x,p.y)=(r.layer,r.z,r.x,r.y))
 THEN 'included' ELSE 'unpackaged' END package_membership
 FROM required r LEFT JOIN accepted a USING(layer,z,x,y);
CREATE INDEX attempts_by_tile ON attempt_tiles(layer,z,x,y);
"""


def build_database(path, manifest, plan, region, recovery, plan_sha, source_sha):
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None, "Exact source SHA required")
    accepted = validate_baseline(manifest, plan, region, recovery, plan_sha)
    path = Path(path)
    # Exclusive creation protects existing evidence; failures remove only this new file.
    with path.open("xb"):
        pass
    db = None
    try:
        db = sqlite3.connect(path)
        db.executescript(SCHEMA)
        metadata = {"spec": manifest.spec, "manifestRevision": manifest.revision,
                    "requiredManifestSHA256": manifest.digest(), "sourceSHA": source_sha,
                    "planSHA256": plan_sha, "predecessorReceipt": recovery["receiptRef"],
                    "scopeStatus": manifest.spec["scopeStatus"],
                    "historicalBytesReread": False, "geographicAreaPercent": None,
                    "deliveryStatus": "not_verified", "deviceAcceptance": "not_tested",
                    "supportingAssets": "Sunlight 320 historical assets; vectors/weather/shared dependency membership unverified"}
        db.executemany("INSERT INTO metadata VALUES (?,?)", ((k, canonical(v).decode()) for k, v in metadata.items()))
        db.executemany("INSERT INTO required VALUES (?,?,?,?,?,?,?,?,?)",
                       ((*t, manifest.groups[t[0]], *extent(t[1], t[2], t[3])) for t in manifest.tiles()))
        ref = canonical(recovery["receiptRef"]).decode().strip()
        db.executemany("INSERT INTO accepted VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       ((*t, job, "historical_receipt_reconstruction", ref, None, None, None, None, None)
                        for t, job in sorted(accepted.items())))
        gaps = set(plan["campaign"].get("sourcePixelGapQuarantines", []))
        for job, count in sorted(plan["priorAttemptCounts"].items()):
            require(type(count) is int and count >= 0, "Invalid attempt counter")
            if count == 0:
                continue
            outcome = ("accepted" if job in plan["completedJobIDs"] else
                       "source_pixel_gap_attempt" if job in gaps else "excluded_or_ambiguous")
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (job, count, outcome))
            if outcome != "accepted":
                db.executemany("INSERT INTO attempt_tiles VALUES (?,?,?,?,?)",
                               ((job, *t) for t in sorted(manifest.expand_job(job))))
        db.commit()
        return summarize(db)
    except BaseException:
        if db:
            db.close()
            db = None
        path.unlink()
        raise
    finally:
        if db:
            db.close()


def summarize(db):
    meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM metadata")}
    counts = []
    for layer, z, group, n, v in db.execute("""SELECT layer,z,download_group,count(*),
            sum(independent_verification='verified') FROM inventory GROUP BY layer,z ORDER BY layer,z"""):
        counts.append(dict(layer=layer, zoom=z, group=group, required=n, verified=v, missing=n-v))
    outside = db.execute("SELECT count(*) FROM accepted a LEFT JOIN required r USING(layer,z,x,y) WHERE r.layer IS NULL").fetchone()[0]
    return {"format": "rrgh-offline-inventory-summary-v1", **meta,
            "required": sum(c["required"] for c in counts), "verified": sum(c["verified"] for c in counts),
            "outsideScopeAcceptedPreserved": outside, "byLayerZoom": counts,
            "overviewMissing": sum(c["missing"] for c in counts if c["zoom"] <= 15),
            "completionBasis": "tile positions, not geographic area or package/device completion",
            "productionTriggered": False}


def overview_queue(db):
    """Prepare dependency-exact overview work; never pretend clipped edges are full tiles."""
    required = {tuple(r) for r in db.execute("SELECT layer,z,x,y FROM required")}
    accepted = {tuple(r) for r in db.execute("SELECT layer,z,x,y FROM accepted")}
    for tile in sorted(required - accepted, key=lambda t: (t[0], -t[1], t[2], t[3])):
        layer, z, x, y = tile
        if z > 15:
            continue
        children = [(layer, z+1, x*2+dx, y*2+dy) for dx in range(2) for dy in range(2)]
        missing = [c for c in children if c in required and c not in accepted]
        outside = [c for c in children if c not in required]
        direct = layer == "usgs-topo"
        yield {"tile": tile, "operation": "official_tile_read" if direct else "overview",
               "requiredChildren": [] if direct else [c for c in children if c in required],
               "missingChildren": [] if direct else missing,
               "outsideFootprintChildren": [] if direct else outside,
               "dependencyStatus": "source_read_validation_required" if direct else
               "missing_children" if missing else "edge_policy_required" if outside else "children_receipt_backed",
               "productionReady": False,
               "remainingGates": ["fresh_allocation", "resource_reservation", "renderer_QA", "source_rights",
                                  "byte_pixel_readback", "approved_controller"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("spec", "plan", "region", "recovery", "database", "summary", "overview"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--plan-sha256", required=True)
    p.add_argument("--source-sha", required=True)
    args = p.parse_args()
    for out in (args.database, args.summary, args.overview):
        require(not out.exists(), "Output already exists: " + str(out))
    spec, plan, recovery = [json.loads(path.read_bytes()) for path in (args.spec, args.plan, args.recovery)]
    region = json.loads(zlib.decompress(base64.b64decode(args.region.read_bytes().strip(), validate=True)))
    report = build_database(args.database, Manifest(spec), plan, region, recovery, args.plan_sha256, args.source_sha)
    with args.summary.open("xb") as out:
        out.write(canonical(report))
    with sqlite3.connect(args.database) as db, args.overview.open("xb") as out:
        for item in overview_queue(db):
            out.write(canonical(item))
    print(json.dumps({k: report[k] for k in ("required", "verified", "overviewMissing", "requiredManifestSHA256")}))


if __name__ == "__main__":
    main()
