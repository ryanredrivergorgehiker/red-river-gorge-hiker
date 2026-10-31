#!/usr/bin/env python3
"""Plan the next full-quality wave under the original push identity, offline only.

Run from a temporary checkout of the exact engineering source ref, with the
latest independent recovery receipt supplied from a separate trusted audit.
This module is outside backend/scripts so it does not change engine snapshots.
"""
import base64
import copy
import json
import os
import re
import sys
import zlib
from collections import Counter
from pathlib import Path


class Stop(Exception):
    pass


def check(pred, message):
    if not pred:
        raise Stop(message)


def prepare(root, verified):
    root = Path(root).resolve()
    os.chdir(root)
    sys.path.insert(0, str(root / "backend/scripts"))
    from gorge_checkpoint import canonical, digest
    from run_gorge_checkpoint_slot import code_snapshot
    from forecast_gorge_checkpoint_campaign import bbox, coords, intersects, morton, PROFILES

    code_path = root / "backend/scripts/gorge_campaign.py"
    original_code = code_path.read_text()
    match = re.search(r"CONFIG=SOURCE.parent/'config/gorge-campaign-wave-(\d{3})(-push)?-(\d{8})'", original_code)
    check(match is not None, "Missing canonical source configuration pointer")
    wave = int(match.group(1))
    suffix = match.group(2) or ""
    date = match.group(3)
    check(wave >= 21, "Unrecognized old wave")
    check(verified.get("wave") == wave, "Recovery sequence mismatch")
    prefix = "gorge-campaign-wave-"
    old_path = root / "backend/config" / f"{prefix}{wave:03d}{suffix}-{date}"
    next_path = root / "backend/config" / f"{prefix}{wave+1:03d}-{date}"
    check(old_path.is_dir() and not next_path.exists(), "Old/new configuration missing or reused")
    old = json.loads((old_path / "PLAN.json").read_bytes())
    env = json.loads((old_path / "ALLOWANCE.json").read_bytes())
    region = json.loads(zlib.decompress(base64.b64decode(
        (old_path / "REGION-PLAN.json.z.b64").read_bytes())))
    check(old["campaign"]["sequence"] == wave, "Prior campaign sequence mismatch")
    check(old["approvedJobIDs"] == [x["id"] for x in region["jobs"]], "Prior region mismatch")
    legacy = wave == 22
    if legacy:
        check(old["campaign"]["id"] == "gorge-full-quality-25usd-20261030" and
              old["campaign"]["ceilingUSD"] == "25.00" and
              old["campaign"]["storageTargetUSDPerMonth"] == "1.00",
              "Wave022 legacy authority lineage changed")
    else:
        check(old["campaign"]["id"] == "gorge-full-quality-125usd-20261031" and
              old["campaign"]["ceilingUSD"] == "125.00" and
              old["campaign"]["storageTargetUSDPerMonth"] == "2.00",
              "Forward-only budget lineage unexpectedly changed")
    budget_path = root / "backend/scripts/gorge_campaign_budget.py"
    template = Path(__file__).with_name("rrgh_campaign_budget_v2.py").read_bytes()
    check(b"CAMPAIGN='gorge-full-quality-125usd-20261031'" in template,
          "Missing exact authorized successor budget policy")
    if legacy:
        check(b"CAMPAIGN='gorge-full-quality-25usd-20261030'" in budget_path.read_bytes(),
              "Original Wave022 budget source changed")
        budget_path.write_bytes(template)
        # The first v2 engine must carry the new ceiling in its immutable
        # server-side campaign fence too, not only in the plan and settlement.
        rebind_code = code_path.read_text()
        old_fence = "'ceilingUSD':'25.00'"
        check(rebind_code.count(old_fence) == 1,
              "Legacy engine fence unexpectedly changed")
        code_path.write_text(rebind_code.replace(old_fence,
                                               "'ceilingUSD':c['ceilingUSD']"))
    else:
        check(budget_path.read_bytes() == template, "Existing budget successor template mismatch")
    import importlib
    budget = importlib.import_module("gorge_campaign_budget")
    budget = importlib.reload(budget)
    admit, cost = budget.admit, budget.cost
    prior_plan_sha = digest(canonical(old))
    check(verified["planSHA256"] == prior_plan_sha, "Previous plan digest mismatch")
    ref = verified["receiptRef"]
    check(ref["key"] == "engineering/map-production/plans/" + prior_plan_sha +
          "/slots/00002/receipt.json", "Previous receipt key mismatch")
    check(verified["receiptSHA256"] == ref["sha256"], "Previous receipt hash mismatch")

    accepted = old["completedJobIDs"] + old["approvedJobIDs"]
    check(len(accepted) == len(set(accepted)) == verified["acceptedJobs"],
          "Prior accepted jobs disagree with independent settlement")
    check(verified["acceptedRasterTiles"] >= len(accepted), "Raster count regression")
    check(verified["sunlightAssets"] == 320, "Sunlight regression")
    before_attempts = old["priorAttemptCounts"].copy()
    excluded = {jid for jid, n in before_attempts.items() if n > 0 and jid not in accepted}
    check(len(excluded) == 45 and verified["historicalExclusions"] == 45,
          "Historical exclusion inventory changed")
    check(not set(accepted) & excluded, "Accepted and excluded overlap")
    check(old["campaign"]["ambiguousExcludedJobs"] ==
          ["leaf-on-16-17535-25316", "leaf-on-16-17556-25323"],
          "Historic two transport ambiguities changed")
    for jid in old["approvedJobIDs"]:
        check(before_attempts.get(jid, 0) == 0, "Previously attempted new job")
        before_attempts[jid] = 1
    check(all(n <= 2 for n in before_attempts.values()), "Attempt overflow")

    grids = {z: coords(z) for z in (16, 17, 18)}
    index, missing = {}, {}
    for group, layers in PROFILES.items():
        for layer, maxz in layers.items():
            family = "dem" if layer == "terrain" else layer
            sources = region["inventory"]["sources"].get(family, [])
            gaps = 0
            for x, y in sorted(grids[16], key=lambda xy: morton(*xy)):
                if layer == "usgs-topo":
                    source_ids = []
                else:
                    rect = bbox(16, x, y, 1/512 if layer == "terrain" else 0)
                    source_ids = [f["id"] for f in sources if intersects(f["bbox"], rect)]
                    if not source_ids:
                        gaps += 1
                        continue
                tiles = []
                for z in range(16, maxz+1):
                    n = 2**(z-16)
                    for dx in range(n):
                        for dy in range(n):
                            xx, yy = x*n+dx, y*n+dy
                            if (xx, yy) in grids[z]:
                                tiles.append([z, xx, yy])
                jid = f"{layer}-16-{x}-{y}"
                check(jid not in index and bool(tiles), "Source-window index collision")
                index[jid] = {"id": jid, "layer": layer, "group": group,
                    "z": 16, "x": x, "y": y,
                    "operation": "usgs-tile" if layer == "usgs-topo" else "source-window",
                    "sourceIDs": source_ids, "dependencies": [],
                    "outputTiles": tiles, "preservedComplete": False}
            missing[layer] = gaps
    check(len(index) == 11940 and sum(missing.values()) == 13960,
          "Pinned source inventory changed")
    for prior in region["jobs"]:
        reference = index[prior["id"]]
        check(prior["sourceIDs"] == reference["sourceIDs"] and
              prior["outputTiles"] == reference["outputTiles"],
              "Source-pinned prior job changed")

    limits = {"usgs-topo": 256, "leaf-on": 256}
    picked = []
    for layer, limit in limits.items():
        landmarks = [index[jid] for jid in accepted if jid in index and
                     index[jid]["layer"] == layer]
        check(bool(landmarks), "No verified family anchors")
        coords_done = [(j["x"], j["y"]) for j in landmarks]
        eligible = [job for job in index.values()
            if job["layer"] == layer and job["id"] not in accepted and
            job["id"] not in excluded and before_attempts.get(job["id"], 0) == 0 and
            (job["sourceIDs"] or layer == "usgs-topo")]
        eligible.sort(key=lambda job: (
            min(abs(job["x"] - x) + abs(job["y"] - y) for x,y in coords_done),
            morton(job["x"], job["y"]), job["id"]))
        sample = eligible[:limit]
        check(len(sample) == limit, "Supported source territory exhausted; stop")
        sample.sort(key=lambda job: (
            tuple(job["sourceIDs"]), morton(job["x"], job["y"]), job["id"]))
        picked.extend(sample)
    jobs = [j["id"] for j in picked]
    check(len(jobs) == len(set(jobs)) == 512 and
          not set(jobs) & (set(accepted)|excluded), "Job scope overlap")
    check(Counter(j["layer"] for j in picked) == limits, "Layer mix changed")
    expected_tiles = sum(len(j["outputTiles"]) for j in picked)
    # Every source window retains all children inside the pinned regional grid.
    # Border windows may have fewer children, without resampling/downscaling.
    check(5500 <= expected_tiles <= 5632,
          "Unexpected geometry-derived tile count: "+str(expected_tiles))

    policy = {}
    for jid, perjob in old["jobPolicies"].items():
        layer = jid.rsplit("-", 3)[0]
        if layer in policy:
            check(policy[layer] == perjob, "Old job policy inconsistent")
        else:
            policy[layer] = perjob
    check(all(x in policy for x in limits), "Missing policy")

    # Update only the one canonical source CONFIG pin. Old source files remain
    # byte-identical, and the new scope is generated from the same provenance.
    before = f"CONFIG=SOURCE.parent/'config/{prefix}{wave:03d}{suffix}-{date}'"
    after = f"CONFIG=SOURCE.parent/'config/{prefix}{wave+1:03d}-{date}'"
    check(original_code.count(before) == 1, "Canonical source pin not unique")
    code_path.write_text(original_code.replace(before, after))

    plan = copy.deepcopy(old)
    plan["campaign"]["sequence"] = wave + 1
    if legacy:
        plan["campaign"]["id"] = "gorge-full-quality-125usd-20261031"
        plan["campaign"]["ownerApproval"] = budget.APPROVAL
        plan["campaign"]["ceilingUSD"] = "125.00"
        plan["campaign"]["storageTargetUSDPerMonth"] = "2.00"
    plan["campaign"]["previousRecovery"] = ref
    carry = verified["nextCarry"]
    check(carry["priorCompletedJobs"] == len(accepted) and
          carry["priorRasterTiles"] == verified["acceptedRasterTiles"] and
          carry["priorSunlightAssets"] == 320, "Carry inventory mismatch")
    plan["campaign"]["carry"] = carry
    plan["completedJobIDs"] = accepted
    plan["approvedJobIDs"] = jobs
    plan["slotJobs"] = {"1": jobs}
    plan["priorAttemptCounts"] = before_attempts
    from datetime import datetime, timezone, timedelta
    plan["expiresAt"] = (datetime.now(timezone.utc) +
                         timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    plan["jobPolicies"] = {j["id"]: policy[j["layer"]] for j in picked}
    plan["slots"][1]["attempts"] = len(jobs)
    plan["limits"]["attempts"] = len(jobs)
    check(plan["slots"][1]["classARequests"] == 2000 and
          3*len(jobs)+32 < 2000, "No producer Class-A headroom")
    region["jobs"] = picked
    check("gorge_campaign.py" in region["engineHashes"], "Missing engine hash")
    region["engineHashes"]["gorge_campaign.py"] = digest(code_path.read_bytes())
    if "gorge_campaign_budget.py" in region["engineHashes"]:
        region["engineHashes"]["gorge_campaign_budget.py"] = digest(budget_path.read_bytes())
    # Retain the established, restricted WIF push-event identity.
    context = (root / "backend/scripts/fetch_gorge_private_seed.py").read_text()
    check("'GITHUB_EVENT_NAME':'push'" in context and
          "offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029" in context,
          "Original restricted push identity changed")
    plan["regionPlanSHA256"] = digest(canonical(region))
    plan["sourceSnapshotSHA256"] = code_snapshot(root / "backend/scripts")
    env["cloudStorageAllowance"]["approvalReference"] = budget.APPROVAL
    env["cloudStorageAllowance"]["approvedRecurringStorageUSDPerMonth"] = "2.00"
    env["cloudStorageAllowance"]["approvedUSD"] = "0.6456"
    env["cloudStorageAllowance"]["reservedWorstCaseUSD"] = str(cost(plan["limits"]))
    env["cloudStorageAllowance"]["planSHA256"] = digest(canonical(plan))
    ad = admit(plan, env)
    check(str(ad["reserveUSD"]) == env["cloudStorageAllowance"]["reservedWorstCaseUSD"],
          "Budget admission/reservation mismatch")
    from decimal import Decimal
    check(Decimal(ad["cumulativeAdmissionUSD"]) < Decimal("123") and
          Decimal(ad["monthlyAdmissionUSD"]) < Decimal("2"),
          "Authorized successor budget admission failed")

    # Source-only CAS publication must include the new v2 budget module.
    # The historical Wave022 plan and receipt are never overwritten.
    next_path.mkdir(parents=True, exist_ok=False)
    (next_path/"PLAN.json").write_bytes(canonical(plan))
    (next_path/"ALLOWANCE.json").write_bytes(canonical(env))
    (next_path/"REGION-PLAN.json.z.b64").write_bytes(
        base64.b64encode(zlib.compress(canonical(region), 9)))

    # Dynamic local readback uses the new modified source pin, never cloud data.
    from gorge_campaign import configuration
    p,e,r = configuration(next_path)
    check(p["approvedJobIDs"] == jobs and p["completedJobIDs"] == accepted,
          "Local canonical scope mismatch")
    check(p["campaign"]["previousRecovery"] == ref and
          p["campaign"]["carry"] == carry, "Immutable predecessor/carry mismatch")
    return {
        "nextSequence": wave+1,
        "budgetMigrated": legacy,
        "successorBudgetSource": "backend/scripts/gorge_campaign_budget.py",
        "jobs": len(jobs), "tiles": expected_tiles,
        "sourcePlanParent": prior_plan_sha,
        "nextPlanSHA256": digest(canonical(plan)),
        "sourcePinBefore": before, "sourcePinAfter": after,
        "newScope": str(next_path.relative_to(root)),
        "newSource": str(code_path.relative_to(root)),
        "expectedPreviousReceipt": ref,
        "cumulativeAdmissionUSD": str(ad["cumulativeAdmissionUSD"]),
        "monthlyAdmissionUSD": str(ad["monthlyAdmissionUSD"])
    }


def main():
    check(len(sys.argv) == 3, "Use <source-checkout> <verified-recovery.json>")
    root = Path(sys.argv[1])
    report = json.loads(Path(sys.argv[2]).read_text())
    check(report.get("verified") is True and report.get("dispatchAuthorized") is False,
          "Missing gated independent supervisor readback")
    summary = prepare(root, report)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Stop as exc:
        print("AUTO_PLANNER_STOP: " + str(exc), file=sys.stderr)
        sys.exit(1)
