#!/usr/bin/env python3
"""Atomic plan publication and one-time worker dispatch; DRY RUN BY DEFAULT.

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
WORKER_FILE = "offline-map-restricted-dispatch.yml"
CAP_SEQUENCE = 22  # one-wave limited safety pilot; never self-escalate
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
    guard(type(prior_seq) is int and prior_seq+1 == CAP_SEQUENCE,
          "One-wave pilot cap reached or missing predecessor")
    parent = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                     text=True).strip()
    guard(SHA40.fullmatch(parent) is not None, "Invalid prior Git commit")
    old_dir = root / f"backend/config/gorge-campaign-wave-{prior_seq:03d}-20261031"
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
    guard(len(excluded) == 45 and
          not excluded & set(plan["approvedJobIDs"]), "Quarantine overlap")
    guard(plan["maxConcurrency"] == 1 and
          plan["automaticRetryPermitted"] is False, "Concurrency/retry guard changed")
    guard(plan["bucket"] == "rrgh-nonproduction-protected-packages", "Wrong cloud bucket")
    guard(plan["campaign"]["ceilingUSD"] == "25.00" and
          plan["campaign"]["storageTargetUSDPerMonth"] == "1.00",
          "New authority needs separate forward-only budget migration")
    guard(Decimal(audit["nextCarry"]["chargedUSD"]) >= 0, "Bad prior costs")
    guard(Decimal(audit["nextCarry"]["chargedUSD"]) +
          Decimal(allowance["cloudStorageAllowance"]["reservedWorstCaseUSD"])
          < Decimal("23"), "Protected completion reserve cannot be spent")
    plan_hash = digest(canonical(plan))
    guard(SHA64.fullmatch(plan_hash) is not None, "Malformed plan SHA")
    guard(allowance["cloudStorageAllowance"]["planSHA256"] == plan_hash,
          "Cloud allowance not exact-plan-bound")
    guard(re.search(r"CONFIG=SOURCE.parent/'config/gorge-campaign-wave-022-20261031'",
                    code.read_text()) is not None, "Source not pinned to new scope")
    identity = root / "backend/scripts/fetch_gorge_private_seed.py"
    ctx = identity.read_text()
    guard("'GITHUB_EVENT_NAME':'workflow_dispatch'" in ctx and
          ".github/workflows/offline-map-restricted-dispatch.yml@refs/heads/" +
          WORKER_BRANCH in ctx, "New producer workflow identity is not source-pinned")
    paths = [code, identity, new_dir/"PLAN.json", new_dir/"ALLOWANCE.json", region_file]
    entries = []
    for file in paths:
        payload = file.read_text(encoding="utf-8")
        guard(0 < len(payload) <= 500000, "Unexpected immutable file size")
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
    guard(os.environ.get("RRGH_ENABLE_ONE_WAVE_PILOT") == "EXPLICITLY_ENABLED_20261031",
          "Explicit one-wave pilot authorization flag absent")
    guard(os.environ.get("GITHUB_REPOSITORY") == REPO, "Repository changed")
    # Do not dispatch if required workflow files are not on BOTH branches.
    api("GET", "contents/.github/workflows/"+WORKER_FILE+"?ref=main", token)
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
        "message": f"Lane20: immutable auto-reviewed wave{plan['sequence']:03d} one-time pilot [skip ci]",
        "tree": tree["sha"], "parents": [branch]})
    api("PATCH", "git/refs/heads/"+SRC_BRANCH, token, {
        "sha": commit["sha"], "force": False})
    check = api("GET", "git/ref/heads/"+SRC_BRANCH, token)["object"]["sha"]
    guard(check == commit["sha"], "Published source ref mismatch")
    # Only workflow_dispatch is guaranteed to trigger on a GITHUB_TOKEN action.
    api("POST", "actions/workflows/"+WORKER_FILE+"/dispatches", token, {
        "ref": WORKER_BRANCH,
        "inputs": {"source_sha": commit["sha"],
                   "plan_sha256": plan["planSHA256"],
                   "sequence": str(plan["sequence"])}})
    print(json.dumps({"status": "ONE_WAVE_PILOT_DISPATCHED",
                      "commitSHA": commit["sha"],
                      "planSHA256": plan["planSHA256"],
                      "sequence": plan["sequence"]}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_checkout")
    parser.add_argument("audit_json")
    parser.add_argument("--dispatch", action="store_true",
                        help="Only allowed with explicit trusted environment flag")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    guard(bool(token), "Missing GitHub API token")
    audit = json.loads(Path(args.audit_json).read_text())
    publish(args.source_checkout, audit, token, dry_run=not args.dispatch)


if __name__ == "__main__":
    try:
        main()
    except Halt as exc:
        print("PUBLISHER_STOP: "+str(exc), file=sys.stderr)
        sys.exit(1)
