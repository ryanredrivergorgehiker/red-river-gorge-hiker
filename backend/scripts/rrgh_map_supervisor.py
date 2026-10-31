#!/usr/bin/env python3
"""Read-only, fail-closed supervision of the restricted map production campaign.

No cloud credentials, no Git writes and no retries. The future dispatcher must
not consume this report unless its ready flag is true AND its separate GitHub
account billing hard-stop has been verified. Test with unittest in this module.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

REPO = "ryanredrivergorgehiker/red-river-gorge-hiker"
BRANCH = "lane20/offline-production-preflight-20261029"
WORKFLOW = "offline-map-producer-access.yml"
PREFIX = "engineering/map-production/plans/"
RUN_RE = re.compile(r"^Lane20: execute verified new-territory wave(\\d{3}) 20261031$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXCLUDED = 45
SUNLIGHT = 320
MAX_JOBS = 512
EXPECTED_CAMPAIGN = "gorge-full-quality-25usd-20261030"


class Halt(Exception):
    """A guarded stop. Always blocks dispatch."""


def require(test, message):
    if not test:
        raise Halt(message)


def decimal(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise Halt("Invalid monetary value") from exc
    require(n.is_finite() and n >= 0, "Nonfinite/negative monetary value")
    return n


def audit_run(run, jobs, receipt_lines):
    """Pure verification: unit tests require no GitHub or Google Cloud access."""
    require(run.get("status") == "completed" and run.get("conclusion") == "success",
            "Latest producer is not successfully completed")
    require(run.get("run_attempt") == 1, "Rerun prohibited")
    require(run.get("head_branch") == BRANCH, "Producer branch mismatch")
    require(run.get("event") == "push", "Unreviewed production trigger")
    headline = run.get("head_commit") or {}
    message = headline.get("message", "")
    match = RUN_RE.fullmatch(message)
    require(match is not None, "Unknown production commit message")
    sequence = int(match.group(1))
    require(sequence >= 20, "Pre-campaign run")
    require(run.get("repository", {}).get("full_name") == REPO, "Wrong repository")
    active = [j for j in jobs if j.get("status") in ("queued", "in_progress", "waiting")]
    require(not active, "Unfinished worker jobs")
    producer = [j for j in jobs if j.get("name") == "bounded-stage"]
    recovery = [j for j in jobs if j.get("name") == "independent-recovery"]
    require(len(producer) == len(recovery) == 1, "Producer/recovery job multiplicity")
    require(producer[0].get("conclusion") == recovery[0].get("conclusion") == "success",
            "Producer or independent recovery failed")
    reports = []
    for line in receipt_lines:
        if '"phase": "independent-recovery"' not in line:
            continue
        marker = line.find("{")
        if marker < 0:
            continue
        try:
            obj = json.loads(line[marker:])
        except (ValueError, TypeError):
            continue
        if obj.get("phase") == "independent-recovery":
            reports.append(obj)
    require(len(reports) == 1, "Exactly one independent recovery report required")
    receipt = reports[0]
    result = receipt.get("result") or {}
    reference = receipt.get("receiptRef") or {}
    require(result.get("status") == "verified", "Independent verification not complete")
    require(result.get("allOutputHashesAndPixelsVerified") is True, "Unverified pixels/hash")
    require(result.get("allNewPackageChunksReadBack") is True, "Unread package chunks")
    require(result.get("allExistingCachesPreserved") is True, "Cache preservation failed")
    require(result.get("sourcePixelGapJobs") == [], "Source pixel gap")
    require(isinstance(result.get("adjacentEdgesMeasured"), int) and
            result["adjacentEdgesMeasured"] > 0, "Missing edge QA")
    jobs_count = result.get("jobs")
    require(type(jobs_count) is int and 1 <= jobs_count <= MAX_JOBS, "Invalid job count")
    carry = result.get("nextCarry") or {}
    settlement = result.get("settlement") or {}
    require(settlement.get("independentRecoveryComplete") is True, "Unsettled recovery")
    require(settlement.get("ambiguousAllocationRetained") is False, "Ambiguous allocation")
    require(settlement.get("campaignID") == EXPECTED_CAMPAIGN, "Campaign identity changed")
    require(settlement.get("sequence") == sequence, "Sequence mismatch")
    require(carry.get("priorSunlightAssets") == SUNLIGHT, "Sunlight loss")
    require(type(carry.get("priorCompletedJobs")) is int, "Invalid accepted inventory")
    require(type(carry.get("priorRasterTiles")) is int, "Invalid raster inventory")
    require(type(carry.get("storedBytes")) is int, "Invalid storage")
    require(carry["priorCompletedJobs"] >= jobs_count, "Inventory regression")
    require(carry["priorRasterTiles"] >= jobs_count, "Raster regression")
    require(carry.get("chargedUSD") == settlement.get("chargedUSD"), "Cost disagreement")
    require(carry.get("storedBytes") == settlement.get("storedBytes"), "Storage disagreement")
    require(decimal(settlement.get("chargedUSD")) <= decimal(settlement.get("ceilingUSD")),
            "Production campaign ceiling breached")
    require(decimal(settlement.get("storageEstimateUSDPerMonth")) <= Decimal("2"),
            "Owner monthly storage ceiling breached")
    require(decimal(settlement.get("remainingAuthorityUSD")) >= 0, "Negative remaining authority")
    require(type(reference.get("bytes")) is int and 0 < reference["bytes"] < 100000,
            "Invalid recovery receipt size")
    require(re.fullmatch(r"\\d+", str(reference.get("generation", ""))) is not None,
            "Invalid immutable generation")
    require(SHA256.fullmatch(str(reference.get("sha256", ""))) is not None,
            "Invalid receipt SHA")
    key = reference.get("key", "")
    require(isinstance(key, str) and key.startswith(PREFIX) and
            key.endswith("/slots/00002/receipt.json"), "Unexpected recovery receipt key")
    plan_sha = key[len(PREFIX):].split("/", 1)[0]
    require(SHA256.fullmatch(plan_sha) is not None, "Bad plan SHA")
    require(settlement.get("planSHA256") == plan_sha, "Settlement plan mismatch")
    require(decimal(settlement.get("ceilingUSD")) in (Decimal("25"), Decimal("125")),
            "Unexpected production ceiling")
    return {
        "verified": True,
        "wave": sequence,
        "run": run.get("id"),
        "jobsNew": jobs_count,
        "acceptedJobs": carry["priorCompletedJobs"],
        "acceptedRasterTiles": carry["priorRasterTiles"],
        "sunlightAssets": carry["priorSunlightAssets"],
        "historicalExclusions": EXCLUDED,
        "receiptSHA256": reference["sha256"],
        "receiptGeneration": str(reference["generation"]),
        "planSHA256": plan_sha,
        "modeledCumulativeUSD": settlement["chargedUSD"],
        "modeledMonthlyStorageUSD": settlement["storageEstimateUSDPerMonth"],
        "nextStep": "BILLING_GATE_REQUIRED",
        "dispatchAuthorized": False
    }


def gh(path, token, *, raw=False):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "RRGH-read-only-supervisor"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read(12_000_000)
    except urllib.error.HTTPError as e:
        raise Halt("GitHub read HTTP " + str(e.code)) from None
    return data.decode("utf-8") if raw else json.loads(data)


def review(token):
    runs = gh("actions/workflows/" + WORKFLOW +
              "/runs?branch=" + BRANCH + "&per_page=12", token)
    candidates = runs.get("workflow_runs") or []
    require(candidates, "No production history")
    require(not any(r.get("status") in ("queued", "in_progress", "waiting", "requested")
                    for r in candidates), "Production still running")
    run = candidates[0]
    require(run.get("run_attempt") == 1, "Latest run was retried")
    jobs = gh("actions/runs/" + str(run["id"]) + "/jobs?per_page=100", token)
    require(not jobs.get("total_count", 0) > 100, "Job pagination required")
    recovered = [j for j in jobs.get("jobs", []) if j.get("name") == "independent-recovery"]
    require(len(recovered) == 1, "Missing recovery job")
    log = gh("actions/jobs/" + str(recovered[0]["id"]) + "/logs", token, raw=True)
    return audit_run(run, jobs.get("jobs", []), log.splitlines())


def main():
    require(os.environ.get("GITHUB_REPOSITORY") == REPO, "Wrong GitHub repository")
    token = os.environ.get("GH_TOKEN", "")
    require(bool(token), "No GitHub read token")
    report = review(token)
    print(json.dumps(report, sort_keys=True))
    # Deliberate pilot stop. Never launch, modify source, or silently recurse.
    print("SUPERVISOR_READ_ONLY: Production dispatch requires separate approved billing gate.")


if __name__ == "__main__":
    try:
        main()
    except Halt as err:
        print("SUPERVISOR_STOP: " + str(err), file=sys.stderr)
        sys.exit(1)
