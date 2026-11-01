#!/usr/bin/env python3
"""Atomic source publication of one verified successor; never automatically dispatch.

This is a trusted controller-side script. No source-tree Python is imported
while GH_TOKEN is present. A branch compare-and-swap prevents duplicate waves.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "ryanredrivergorgehiker/red-river-gorge-hiker"
SRC_BRANCH = "lane20/map-producer-iam-design-20261029"
WORKER_BRANCH = "lane20/offline-production-preflight-20261029"
WORKER_FILE = "offline-map-producer-access.yml"
MAX_SEQUENCE = 100  # finite bound; source, monthly and monetary guards remain authoritative
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


class Halt(Exception):
    pass


def guard(ok, message):
    if not ok:
        raise Halt(message)


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       allow_nan=False)+"\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def api(method, path, token, payload=None):
    url = "https://api.github.com/repos/" + REPO + "/" + path
    raw = None if payload is None else canonical(payload)
    req = Request(url, data=raw, method=method, headers={
        "Authorization": "Bearer "+token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RRGH-guarded-atomic-publisher",
        **({"Content-Type": "application/json"} if raw is not None else {})})
    try:
        with urlopen(req, timeout=35) as response:
            content=response.read(7_000_000)
    except HTTPError as exc:
        raise Halt("GitHub API rejected " + method + " " +
                   path.split("?")[0] + " (HTTP " + str(exc.code) + ")") from None
    return json.loads(content) if content else {}


def check_local(root, audit):
    root = Path(root).resolve()
    guard(audit.get("verified") is True and
          audit.get("dispatchAuthorized") is False,
          "Independent pre-publish audit must be read-only and verified")
    prior_seq = audit.get("wave")
    guard(type(prior_seq) is int and 21 <= prior_seq < MAX_SEQUENCE,
          "Campaign sequence missing or beyond finite safety bound")
    parent = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                     text=True).strip()
    guard(SHA40.fullmatch(parent) is not None, "Invalid prior Git commit")
    previous_code = subprocess.check_output(["git", "-C", str(root), "show",
                            "HEAD:backend/scripts/gorge_campaign.py"], text=True)
    match = re.search(r"CONFIG=SOURCE.parent/'config/(gorge-campaign-wave-\d{3}(?:-push)?-\d{8})'",
                      previous_code)
    guard(match is not None and f"wave-{prior_seq:03d}" in match.group(1),
          "Prior source configuration pointer changed")
    old_dir = root / "backend/config" / match.group(1)
    new_dir = root / f"backend/config/gorge-campaign-wave-{prior_seq+1:03d}-20261031"
    code = root / "backend/scripts/gorge_campaign.py"
    guard(old_dir.is_dir() and new_dir.is_dir() and code.is_file(),
          "Missing old/new immutable artifacts")
    prior = json.loads((old_dir/"PLAN.json").read_bytes())
    plan = json.loads((new_dir/"PLAN.json").read_bytes())
    allowance = json.loads((new_dir/"ALLOWANCE.json").read_bytes())
    region_file = new_dir/"REGION-PLAN.json.z.b64"
    guard(region_file.is_file(), "Missing immutable region plan")
    old_sha = digest(canonical(prior))
    guard(audit.get("planSHA256") == old_sha, "Prior plan does not match independent receipt")
    guard(prior["campaign"]["sequence"] == prior_seq and
          plan["campaign"]["sequence"] == prior_seq+1, "Invalid wave advance")
    guard(plan["campaign"]["previousRecovery"] == audit["receiptRef"],
          "Unknown predecessor recovery reference")
    guard(plan["campaign"]["carry"] == audit["nextCarry"],
          "Incorrect conservative settlement carry")
    guard(len(plan["approvedJobIDs"]) == 512 and
          len(set(plan["approvedJobIDs"])) == 512, "Invalid pilot batch")
    guard(len(plan["completedJobIDs"]) == audit["acceptedJobs"] and
          not set(plan["completedJobIDs"]) & set(plan["approvedJobIDs"]),
          "Previously accepted work overlap")
    excluded = {jid for jid, v in plan["priorAttemptCounts"].items()
                if v > 0 and jid not in plan["completedJobIDs"]}
    guard(len(excluded) == (45 if prior_seq <= 22 else 46) and
          not excluded & set(plan["approvedJobIDs"]), "Quarantine overlap")
    if prior_seq == 23:
        recovered = audit.get("partialCompletedJobIDs")
        guard(audit.get("partialRecovered") is True and
              audit.get("run") == 41225003991 and
              isinstance(recovered, list) and len(recovered) == 207 and
              recovered == prior["approvedJobIDs"][:207] and
              audit.get("failedJobID") == prior["approvedJobIDs"][207] and
              plan["completedJobIDs"] == prior["completedJobIDs"] + recovered and
              audit["failedJobID"] in excluded and
              plan["priorAttemptCounts"].get(audit["failedJobID"]) == 1,
              "Exact partial-recovery quarantine or accepted-prefix mismatch")
    else:
        guard(audit.get("partialRecovered") is False,
              "Unexpected partial recovery outside pinned incident")
    guard(plan["maxConcurrency"] == 1 and
          plan["automaticRetryPermitted"] is False, "Concurrency/retry guard changed")
    guard(plan["bucket"] == "rrgh-nonproduction-protected-packages", "Wrong cloud bucket")
    guard(plan["campaign"]["id"] == "gorge-full-quality-125usd-20261031" and
          plan["campaign"]["ceilingUSD"] == "125.00" and
          plan["campaign"]["storageTargetUSDPerMonth"] == "2.00",
          "Expected forward-only USD125/USD2 authority missing")
    if prior_seq == 22:
        guard(prior["campaign"]["id"] == "gorge-full-quality-25usd-20261030" and
              prior["campaign"]["ceilingUSD"] == "25.00",
              "Legacy Wave022 lineage changed before migration")
    else:
        guard(prior["campaign"]["id"] == plan["campaign"]["id"],
              "Unexpected subsequent authority lineage")
    guard(Decimal(audit["nextCarry"]["chargedUSD"]) >= 0, "Bad prior costs")
    guard(Decimal(audit["nextCarry"]["chargedUSD"]) +
          Decimal(allowance["cloudStorageAllowance"]["reservedWorstCaseUSD"])
          < Decimal("123"), "USD2 protected completion reserve cannot be spent")
    plan_hash = digest(canonical(plan))
    guard(SHA64.fullmatch(plan_hash) is not None, "Malformed plan SHA")
    guard(allowance["cloudStorageAllowance"]["planSHA256"] == plan_hash,
          "Cloud allowance not exact-plan-bound")
    expected_code_pin = f"CONFIG=SOURCE.parent/'config/gorge-campaign-wave-{prior_seq+1:03d}-20261031'"
    guard(expected_code_pin in code.read_text(), "Source not pinned to exact successor scope")
    guard("'ceilingUSD':c['ceilingUSD']" in code.read_text(),
          "Forward-only campaign fence ceiling not migrated")
    identity = (root / "backend/scripts/fetch_gorge_private_seed.py").read_text()
    guard("'GITHUB_EVENT_NAME':'push'" in identity and
          ".github/workflows/offline-map-producer-access.yml@refs/heads/" + WORKER_BRANCH in identity,
          "Original authorized push WIF source claim changed")
    budget_path = root / "backend/scripts/gorge_campaign_budget.py"
    budget_text = budget_path.read_text()
    guard("CAMPAIGN='gorge-full-quality-125usd-20261031'" in budget_text and
          "Decimal('123.00')" in budget_text,
          "Reviewed conservative budget source changed")
    guard(allowance["cloudStorageAllowance"]["approvedRecurringStorageUSDPerMonth"] == "2.00" and
          allowance["cloudStorageAllowance"]["approvalReference"] == plan["campaign"]["ownerApproval"],
          "Recurring storage authority not plan-bound")
    paths = [code, budget_path, new_dir/"PLAN.json", new_dir/"ALLOWANCE.json", region_file]
    entries = []
    for file in paths:
        payload = file.read_text(encoding="utf-8")
        # PLAN.json grows by up to 512 accepted IDs per wave; retain a finite,
        # separately bounded 2 MB plan cap without relaxing all other file caps.
        # Canonical SHA, exact receipt, budget, lease, quarantine and job guards
        # above still apply before any source publication or Cloud dispatch.
        max_bytes = 2_000_000 if file.name == "PLAN.json" else 500_000
        guard(0 < len(payload) <= max_bytes,
              f"Unexpected immutable file size: {file.relative_to(root)} "
              f"bytes={len(payload)} limit={max_bytes}")
        entries.append({"path": str(file.relative_to(root)),
                        "mode": "100644", "type": "blob", "content": payload})
    return {"parent": parent, "sequence": prior_seq+1,
            "planSHA256": plan_hash, "entries": entries}


def publish(root, audit, token, *, dry_run):
    plan = check_local(root, audit)
    branch = api("GET", "git/ref/heads/"+SRC_BRANCH, token)["object"]["sha"]
    guard(branch == plan["parent"], "Source branch changed; compare-and-swap stop")
    if dry_run:
        print(json.dumps({"status": "DRY_RUN_VERIFIED_ONLY",
                          "oldSHA": plan["parent"], "newWave": plan["sequence"],
                          "newPlanSHA256": plan["planSHA256"],
                          "fileCount": len(plan["entries"]),
                          "dispatched": False}, sort_keys=True))
        return
    guard(os.environ.get("RRGH_ENABLE_VERIFIED_NEXT_WAVE_SOURCE") == "BOUNDED_SOURCE_ONLY",
          "Source publication flag missing")
    guard(os.environ.get("GITHUB_REPOSITORY") == REPO, "Repository changed")
    # Original WIF producer remains on its exact restricted branch.
    # A GITHUB_TOKEN push cannot trigger another workflow: dispatch must be
    # a separately authorized original-identity push from the GitHub connector.
    api("GET", "contents/.github/workflows/"+WORKER_FILE+"?ref="+WORKER_BRANCH, token)
    active = api("GET", "actions/workflows/"+WORKER_FILE+
                 "/runs?branch="+WORKER_BRANCH+"&per_page=30", token)
    guard(not any(r.get("status") in ("queued","in_progress","waiting","requested")
                  for r in active.get("workflow_runs", [])),
          "Another restricted producer remains active; never overlap")
    old = api("GET", "git/commits/"+branch, token)
    tree = api("POST", "git/trees", token, {
        "base_tree": old["tree"]["sha"], "tree": plan["entries"]})
    commit = api("POST", "git/commits", token, {
        "message": f"Lane20: immutable successor wave{plan['sequence']:03d} with forward-only reviewed budget [skip ci]",
        "tree": tree["sha"], "parents": [branch]})
    api("PATCH", "git/refs/heads/"+SRC_BRANCH, token, {
        "sha": commit["sha"], "force": False})
    check = api("GET", "git/ref/heads/"+SRC_BRANCH, token)["object"]["sha"]
    guard(check == commit["sha"], "Published source ref mismatch")
    print(json.dumps({"status": "NEXT_SOURCE_PUBLISHED_AWAITING_ORIGINAL_PUSH",
                      "commitSHA": commit["sha"],
                      "planSHA256": plan["planSHA256"],
                      "sequence": plan["sequence"],
                      "workerTriggered": False}, sort_keys=True))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_checkout")
    parser.add_argument("audit_json")
    parser.add_argument("--publish", action="store_true",
                        help="Only allow source publication; never dispatch worker")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    guard(bool(token), "Missing GitHub API token")
    audit = json.loads(Path(args.audit_json).read_text())
    publish(args.source_checkout, audit, token, dry_run=not args.publish)


if __name__ == "__main__":
    try:
        main()
    except Halt as exc:
        print("PUBLISHER_STOP: "+str(exc), file=sys.stderr)
        sys.exit(1)
