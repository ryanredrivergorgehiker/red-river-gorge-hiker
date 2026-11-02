#!/usr/bin/env python3
"""Fail-closed controller cutover and succession evidence checks, without mutations.

This prepares a reviewable transition; it is not an active dispatcher. Evidence
must be collected independently at activation. Passing fixture tests never
establishes Cloud authentication, live fencing, or production succession.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re

from rrgh_required_inventory import canonical, require, sha

REPO = "ryanredrivergorgehiker/red-river-gorge-hiker"
WORKER_BRANCH = "lane20/offline-production-preflight-20261029"
PRODUCER_CONCURRENCY = "rrgh-map-producer-auth-preflight"
CAMPAIGN = "gorge-full-quality-125usd-20261031"


def money(value):
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, "Invalid monetary value")
    return result


def validate_successor(plan, allowance, audit):
    require(audit.get("verified") is True and audit.get("dispatchAuthorized") is False,
            "Independent read-only predecessor audit required")
    require(audit.get("partialRecovered") is False, "Ambiguous partial requires explicit reconciliation")
    c = plan["campaign"]
    require(type(c["sequence"]) is int and c["sequence"] == audit["wave"]+1,
            "Sequence skipped or replayed")
    require(c["previousRecovery"] == audit["receiptRef"] and c["carry"] == audit["nextCarry"],
            "Checkpoint/carry mismatch")
    require(c["id"] == CAMPAIGN and c["ceilingUSD"] == "125.00" and
            c["storageTargetUSDPerMonth"] == "2.00", "Unapproved budget change")
    require(plan["maxConcurrency"] == 1 and plan["automaticRetryPermitted"] is False and
            plan["deleteAllowed"] is False, "Production protections changed")
    jobs = plan["approvedJobIDs"]
    require(0 < len(jobs) <= 512 and len(jobs) == len(set(jobs)), "Invalid batch")
    require(not set(jobs) & set(plan["completedJobIDs"]), "Accepted work replay")
    require(all(plan["priorAttemptCounts"].get(j, 0) == 0 for j in jobs), "Consumed allocation replay")
    require(len(plan["completedJobIDs"]) == len(set(plan["completedJobIDs"])) == audit["acceptedJobs"],
            "Accepted inventory regression")
    require(set(jobs) == set(plan["jobPolicies"]) and
            plan["slotJobs"].get("1") == jobs, "Exact per-job policies/slot allocation missing")
    require(all(type(v) is int and v >= 0 for v in plan["limits"].values()), "Invalid reservation")
    require(plan["limits"]["attempts"] >= len(jobs), "Unreserved attempts")
    policy = allowance["cloudStorageAllowance"]
    require(policy["planSHA256"] == sha(plan), "Allowance not exact-plan-bound")
    limits = plan["limits"]
    reserve = ((money(limits["storedBytes"])/2**30*Decimal(".03") +
                money(limits["egressBytes"])/2**30*Decimal(".23") +
                money(limits["classARequests"])/1000*Decimal(".01") +
                money(limits["classBRequests"])/1000*Decimal(".001"))*Decimal("1.2"))
    require(money(policy["reservedWorstCaseUSD"]) == reserve, "Reservation does not cover full resource limits")
    require(money(c["carry"]["chargedUSD"])+reserve <= Decimal("123"), "Protected USD2 reserve exhausted")
    monthly = (money(c["carry"]["storedBytes"])+money(limits["storedBytes"]))/2**30*Decimal(".036")
    require(monthly <= Decimal("2"), "Monthly storage authority exceeded")
    return {"sequence": c["sequence"], "planSHA256": sha(plan), "jobs": len(jobs),
            "reservedWorstCaseUSD": str(reserve), "monthlyAdmissionUSD": str(monthly)}


def validate_cutover(evidence, audit, now):
    require(evidence.get("format") == "rrgh-controller-cutover-v1", "Unknown transition evidence")
    require(evidence.get("repository") == REPO, "Wrong repository")
    require(evidence.get("observedAt") is not None, "No live transition observation")
    observed = datetime.fromisoformat(evidence["observedAt"].replace("Z", "+00:00"))
    require(observed.tzinfo is not None and 0 <= (now-observed).total_seconds() <= 300,
            "Transition evidence must be rechecked within five minutes")
    require(evidence.get("checkpoint") == audit["receiptRef"], "Cutover checkpoint changed")
    require(evidence.get("allProducerEntryPointsEnumerated") is True and
            evidence.get("activeRuns") == [], "Conflicting or unenumerated producers")
    require(evidence.get("legacyInitiationFenced") is True and
            bool(evidence.get("fenceReadbackRef")), "Legacy initiation still authorized")
    require(evidence.get("concurrencyGroup") == PRODUCER_CONCURRENCY, "Producer concurrency not shared")
    ownership = evidence.get("ownership", {})
    require(ownership.get("owner") == "controller" and type(ownership.get("epoch")) is int and
            ownership["epoch"] > 0 and bool(ownership.get("generation")) and
            bool(ownership.get("readbackRef")), "Durable exclusive ownership missing")
    require(evidence.get("acceptedOutputPreservationVerified") is True,
            "Accepted output preservation not verified")
    auth = evidence.get("authentication", {})
    require(auth.get("cloudProbePassed") is True and auth.get("sourceGuardPassed") is True and
            auth.get("workflow") == "offline-map-restricted-dispatch.yml" and
            auth.get("event") == "workflow_dispatch" and auth.get("branch") == WORKER_BRANCH and
            bool(auth.get("authorizationReference")) and bool(auth.get("probeRun")),
            "Exact replacement trigger has no verified authorized authentication path")
    billing = evidence.get("githubBilling", {})
    require(billing.get("hardStopVerified") is True and billing.get("hardCeilingUSD") == 350 and
            bool(billing.get("observationRef")) and
            money(billing.get("spentUSD")) + money(billing.get("reservedUSD")) <= Decimal("350"),
            "Current GitHub hard-stop/headroom evidence missing")
    require(evidence.get("rollbackPolicy") == "fence-reconcile-latest-checkpoint-fresh-allocation",
            "Rollback must not replay a historical wave")


def validate_live_succession(records):
    require(len(records) >= 2, "Two real recovered executions required")
    seen_runs, seen_plans = set(), set()
    previous = None
    for record in records:
        require(record.get("evidenceKind") == "live-github-cloud" and
                record.get("runAttempt") == 1 and record.get("producerConclusion") == "success" and
                record.get("recoveryConclusion") == "success", "Not an independently recovered live execution")
        run, plan = record["runID"], record["planSHA256"]
        require(type(run) is int and run > 0 and re.fullmatch(r"[0-9a-f]{64}", plan) is not None,
                "Invalid immutable execution identity")
        require(run not in seen_runs and plan not in seen_plans, "Duplicate execution or replayed plan")
        seen_runs.add(run); seen_plans.add(plan)
        require(record.get("verifiedNewJobs", 0) > 0 and record.get("verifiedNewTiles", 0) > 0 and
                bool(record.get("recoveryReceipt")) and bool(record.get("independentAuditRef")) and
                re.fullmatch(r"[0-9a-f]{40}", str(record.get("sourceSHA", ""))), "Missing accepted output evidence")
        if previous:
            require(record.get("sequence") == previous["sequence"]+1 and
                    record.get("predecessorReceipt") == previous["recoveryReceipt"], "Succession lineage broken")
            require(record.get("triggerActor") == "github-actions[bot]" and
                    record.get("triggerEvent") == "workflow_dispatch" and
                    record.get("controllerParentRun") == previous["runID"] and
                    bool(record.get("controllerDispatchReceipt")), "Successor was not started by the controller")
        previous = record
    return True


def assess(plan, allowance, audit, evidence, now):
    errors = []
    candidate = None
    for stage, operation in (
        ("successor", lambda: validate_successor(plan, allowance, audit)),
        ("cutover", lambda: validate_cutover(evidence, audit, now)),
    ):
        try:
            result = operation()
            if stage == "successor":
                candidate = result
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            errors.append({"stage": stage, "reason": str(exc)})
    return {"format": "rrgh-controller-preflight-v1", "candidate": candidate,
            "cutoverEvidenceComplete": not errors, "errors": errors,
            "dispatchAuthorized": False, "productionTriggered": False,
            "note": "Read-only preflight; does not apply fencing, grant IAM, or prove live succession."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "allowance", "audit", "cutover"):
        p.add_argument("--"+name, required=True, type=Path)
    args = p.parse_args()
    data = [json.loads(getattr(args, name).read_bytes()) for name in ("plan", "allowance", "audit", "cutover")]
    result = assess(*data, datetime.now(timezone.utc))
    print(canonical(result).decode(), end="")
    return 0 if result["cutoverEvidenceComplete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
