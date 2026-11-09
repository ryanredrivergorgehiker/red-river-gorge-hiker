#!/usr/bin/env python3
"""Read-only, fail-closed supervision of the restricted map production campaign.

No cloud credentials or Git writes. Only transient GET failures retry. The dispatcher must
not consume this report unless its ready flag is true AND its separate GitHub
account billing hard-stop has been verified. Test with unittest in this module.
"""
import json
import os
import re
import sys
import time
from http.client import IncompleteRead
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

REPO = "ryanredrivergorgehiker/red-river-gorge-hiker"
BRANCH = "lane20/offline-production-preflight-20261029"
WORKFLOW = "offline-map-producer-access.yml"
PREFIX = "engineering/map-production/plans/"
RUN_RE = re.compile(r"^Lane20: execute verified new-territory wave(\d{3}) 20261031$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXCLUDED = 45
SUNLIGHT = 320
MAX_JOBS = 512
# Exact immutable exceptions, never a blanket authorization for failed producers.
PARTIAL_INCIDENTS = {
    260: dict(run=41687927485, head="b4f80f989341c7d651894679d670f9e9564fab3a",
              plan="65e5d8891320ca386dbdaced9acfc3956a3153fc64c8556e132cbc1b6a1b4b88",
              receipt="df0b69c14fa1091ee2beb3f3046bb4bdbeca456fba0591b7d361bf2d461d75d0",
              jobs=9, tiles=59, parts=7, failed="leaf-off-16-17512-25319",
              error="RuntimeError", dispatcher=True,
              source="e6a2e6ccf0a8a8de8efcd958f83587291b14ee83",
              dispatch="40cfb7d5c70605c4f6b84bc14d358bccee81385d0f320bcced60930858fb3e16"),
    23: dict(run=41225003991, head="a0d966e92654c412e1ae6259e77feb4a005321d9",
             plan="b661abadce4c7977e2e3d7770e76d8912d8f9bd4d79bfac8a0531f097588dffb",
             receipt="3b11557e069de5362569e6567afe6351b06cc7bb47d507de2707783f2db229ed",
             jobs=207, tiles=207, parts=2, failed="usgs-topo-16-17570-25321",
             error="HTTPError"),
    34: dict(run=41324364372, head="ae3203b49ac33347a22998aafef5b78ccb3d4448",
             plan="d8fc62a5caf21e86283821666157591d3b23d4a257725306de5cb14a60c026fd",
             receipt="2d72a0556885ef89a54817c68b985161b01a4622c06b066bfe0e05a5375e7802",
             jobs=488, tiles=4938, parts=20, failed="leaf-on-16-17575-25345",
             error="URLError"),
}
AUTHORIZED_CAMPAIGNS = {
    "gorge-full-quality-25usd-20261030": "25.00",
    "gorge-full-quality-125usd-20261031": "125.00",
}


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


def audit_run(run, jobs, receipt_lines, producer_lines=None, expected_dispatch=None, allow_failed_controller=False, recovery_execution=None):
    """Pure verification: unit tests require no GitHub or Google Cloud access."""
    require(run.get("run_attempt") == 1, "Rerun prohibited")
    require(run.get("head_branch") == BRANCH, "Producer branch mismatch")
    if expected_dispatch is None:
        require(run.get("status") == "completed", "Latest producer has not completed")
        require(run.get("event") == "push", "Unreviewed production trigger")
        match = RUN_RE.fullmatch((run.get("head_commit") or {}).get("message", ""))
        require(match is not None, "Unknown production commit message")
        sequence = int(match.group(1))
    else:
        expected = expected_dispatch
        require(run.get("status") in ("in_progress", "completed"),
                "Dispatcher run not active/completed: status=" + repr(run.get("status")))
        require(run.get("event") == "workflow_dispatch" and
                run.get("path") == ".github/workflows/offline-map-restricted-dispatch.yml" and
                (run.get("actor") or {}).get("login") == "github-actions[bot]", "Unapproved dispatcher identity")
        require(run.get("id") == expected.get("runID") and
                run.get("display_title") == "RRGH production " + str(expected["sequence"]) + " " + expected["dispatchID"],
                "Execution is not bound to the durable dispatch claim")
        sequence = expected["sequence"]
        require(type(sequence) is int and sequence >= 58, "Unapproved dispatcher sequence")
    require(sequence >= 20, "Pre-campaign run")
    # Only explicitly pinned, independently recovered partial incidents qualify.
    incident = PARTIAL_INCIDENTS.get(sequence)
    pinned_dispatch_partial = (allow_failed_controller and expected_dispatch is not None and
        incident is not None and incident.get('dispatcher') is True and
        expected_dispatch.get('sourceSHA') == incident['source'] and
        expected_dispatch.get('dispatchID') == incident['dispatch'])
    partial = ((expected_dispatch is None or pinned_dispatch_partial) and incident is not None and
               run.get("id") == incident["run"] and run.get("head_sha") == incident["head"])
    if recovery_execution is not None:
        from rrgh_recovery_only import validate_split_recovery
        validate_split_recovery(run,jobs,expected_dispatch,recovery_execution)
    recovered_controller_failure = (allow_failed_controller and expected_dispatch is not None and
        run.get('status') == 'completed' and run.get('conclusion') == 'failure' and
        any(j.get('name') == 'advance' and j.get('conclusion') == 'failure' for j in jobs) and
        all(j.get('name') in ('advance','retain-failure','resume-handoff') for j in jobs if j.get('conclusion') == 'failure'))
    require(recovery_execution is not None or recovered_controller_failure or
            (expected_dispatch is not None and run.get("status") == "in_progress" and run.get("conclusion") is None)
            or run.get("conclusion") == ("failure" if partial else "success"),
            "Unrecognized producer run conclusion")
    require(run.get("repository", {}).get("full_name") == REPO, "Wrong repository")
    recovery_jobs=recovery_execution['jobs'] if recovery_execution is not None else jobs
    active = [j for j in jobs if j.get("name") == 'bounded-stage' and j.get("status") != "completed"]
    active += [j for j in recovery_jobs if j.get('name')=='independent-recovery' and j.get('status')!='completed']
    require(not active, "Unfinished worker jobs")
    producer = [j for j in jobs if j.get("name") == "bounded-stage"]
    recovery = [j for j in recovery_jobs if j.get("name") == "independent-recovery"]
    require(len(producer) == len(recovery) == 1, "Producer/recovery job multiplicity")
    require(producer[0].get("conclusion") == ("failure" if partial else "success") and
            recovery[0].get("conclusion") == "success",
            "Producer or independent recovery conclusion mismatch")
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
    if recovery_execution is not None:
        require(result.get('workerReceipt')==recovery_execution['state']['recoveryOnlyOf']['producerReceipt'],
                'Recovery read a different original producer receipt')
    reference = receipt.get("receiptRef") or {}
    require(result.get("status") == ("partial-verified" if partial else "verified"),
            "Independent verification status mismatch")
    require(result.get("allOutputHashesAndPixelsVerified") is True, "Unverified pixels/hash")
    require(result.get("allNewPackageChunksReadBack") is True, "Unread package chunks")
    require(result.get("allExistingCachesPreserved") is True, "Cache preservation failed")
    batch=result.get('batchClosure')
    if batch is not None:
        from rrgh_batch_contract import partition
        try:
            partition(batch.get('attemptedJobIDs',[])+batch.get('unattemptedJobIDs',[]),batch,
                      expected_dispatch['planSHA256'] if expected_dispatch else None)
        except (ValueError,TypeError,KeyError) as error:raise Halt('Invalid independent batch closure') from error
        require(expected_dispatch is not None and not partial and producer_lines is not None,
                'Batch closure requires the restricted dispatcher and original producer')
    pixel_gaps = result.get("sourcePixelGapJobs")
    require(isinstance(pixel_gaps, list) and len(pixel_gaps) <= MAX_JOBS and
            len(set(pixel_gaps)) == len(pixel_gaps) and
            all(isinstance(j, str) and re.fullmatch(r"(hiking|terrain|leaf-off|leaf-on|usgs-topo)-16-\d+-\d+", j)
                for j in pixel_gaps), "Malformed source-pixel-gap quarantine")
    require(result.get("pixelGapAttemptsConsumed", 0) == len(pixel_gaps),
            "Pixel-gap attempted slot accounting mismatch")
    jobs_count = result.get("jobs")
    require(type(jobs_count) is int and 0 <= jobs_count <= MAX_JOBS, "Invalid job count")
    if jobs_count == 0:
        require(expected_dispatch is not None and not partial and (bool(pixel_gaps) or batch is not None) and
                all(type(result.get(k)) is int and result[k] == 0 for k in
                    ("tiles","outputBytes","packageParts","packageBytes","adjacentEdgesMeasured")),
                "Zero-output recovery must contain only independently verified consumed pixel gaps")
    else:
        # This exact pilot has one output per layer, so there are no adjacent
        # output pairs. All sixteen child tiles and all four recomputed parents
        # must still pass their pinned independent verification.
        from rrgh_overview_integration import validate_verification
        checked_overview=validate_verification(result.get('overviewPilotVerification'))
        isolated_pilot=(isinstance(checked_overview,dict) and
            checked_overview.get('format')=='rrgh-crosswave-verification-v1' and
            jobs_count==result.get('tiles')==4 and not partial and not pixel_gaps and
            result.get('sourceRequests')==0 and result.get('sourceBytesReceived')==0)
        require(type(result.get("adjacentEdgesMeasured")) is int and
                (result["adjacentEdgesMeasured"] > 0 or
                 (isolated_pilot and result["adjacentEdgesMeasured"] == 0)), "Missing edge QA")
    carry = result.get("nextCarry") or {}
    settlement = result.get("settlement") or {}
    require(settlement.get("independentRecoveryComplete") is (not partial),
            "Unexpected recovery completion")
    require(settlement.get("ambiguousAllocationRetained") is partial,
            "Ambiguous allocation retention mismatch")
    campaign_id = settlement.get("campaignID")
    require(campaign_id in AUTHORIZED_CAMPAIGNS, "Unknown campaign identity")
    require(campaign_id == ("gorge-full-quality-25usd-20261030" if sequence <= 22
                            else "gorge-full-quality-125usd-20261031"),
            "Unreviewed or retroactive budget migration")
    require(decimal(settlement.get("ceilingUSD")) == decimal(AUTHORIZED_CAMPAIGNS[campaign_id]),
            "Campaign ceiling and lineage disagreed")
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
    require(re.fullmatch(r"\d+", str(reference.get("generation", ""))) is not None,
            "Invalid immutable generation")
    require(SHA256.fullmatch(str(reference.get("sha256", ""))) is not None,
            "Invalid receipt SHA")
    key = reference.get("key", "")
    require(isinstance(key, str) and key.startswith(PREFIX) and
            key.endswith("/slots/00002/receipt.json"), "Unexpected recovery receipt key")
    plan_sha = key[len(PREFIX):].split("/", 1)[0]
    require(SHA256.fullmatch(plan_sha) is not None, "Bad plan SHA")
    require(settlement.get("planSHA256") == plan_sha, "Settlement plan mismatch")
    if expected_dispatch is not None:
        require(plan_sha == expected_dispatch["planSHA256"], "Recovery belongs to another dispatch plan")
    recovered_ids = []
    failed_job = None
    if partial:
        require(plan_sha == incident["plan"] and
                reference["sha256"] == incident["receipt"],
                "Pinned partial incident receipt identity mismatch")
        require(jobs_count == incident["jobs"] and
                result.get("tiles") == incident["tiles"] and
                result.get("packageParts") == incident["parts"],
                "Pinned partial incident recovered subset mismatch")
        require(settlement.get("retainedUsage") == settlement.get("originalAllocation") and
                settlement.get("demonstrablyUnused") ==
                {k: 0 for k in settlement.get("originalAllocation", {})},
                "Partial allocation was not conservatively retained")
        require(producer_lines is not None, "Original producer log required for partial recovery")
        failure_reports = []
        for line in producer_lines:
            marker = line.find("{")
            if marker < 0:
                continue
            try:
                item = json.loads(line[marker:])
            except (ValueError, TypeError):
                continue
            if "completedJobs" in item and "durableJobReceipt" in item:
                number = item["completedJobs"]
                jid = item.get("job")
                ref_job = item["durableJobReceipt"]
                require(type(number) is int and number == len(recovered_ids) + 1 and
                        isinstance(jid, str) and
                        jid.startswith(("usgs-topo-16-", "leaf-on-16-", "hiking-16-", "terrain-16-", "leaf-off-16-")) and
                        jid not in recovered_ids and
                        ref_job.get("key") == PREFIX + plan_sha +
                        "/slots/00001/jobs/" + jid + ".json" and
                        SHA256.fullmatch(str(ref_job.get("sha256", ""))) is not None and
                        re.fullmatch(r"\d+", str(ref_job.get("generation", ""))) is not None,
                        "Producer job receipt sequence or identity mismatch")
                recovered_ids.append(jid)
            if item.get("phase") == "production" and item.get("status") == "failed":
                failure_reports.append(item)
        require(len(recovered_ids) == jobs_count and len(failure_reports) == 1,
                "Incomplete or ambiguous producer receipt log")
        diagnostic = failure_reports[0].get("diagnostic") or {}
        failed_job = diagnostic.get("lastJobConsidered")
        failure_class = diagnostic.get('errorClass') if pinned_dispatch_partial else (diagnostic.get('child') or {}).get('errorClass')
        require(failed_job == incident["failed"] and failure_class == incident["error"] and
                failed_job not in recovered_ids, "Unexpected incident failure or job overlap")
        if pinned_dispatch_partial:
            final = failure_reports[0]
            require(final.get('receiptRef') == result.get('workerReceipt') and
                    final.get('jobs') == jobs_count and final.get('sourcePixelGapJobs') == [] and
                    final.get('stopped') is None and
                    any(f.get('file') == 'rrgh_wif_credentials.py' and f.get('function') == 'token'
                        for f in diagnostic.get('frames', [])), 'Pinned partial closure changed')
    source_completed = []
    if pixel_gaps and batch is None:
        require(not partial and producer_lines is not None, "Cannot combine uncertain partial with pixel gaps")
        source_gap_logs = []
        final_production = []
        for line in producer_lines:
            marker = line.find("{")
            if marker < 0:
                continue
            try:
                row = json.loads(line[marker:])
            except (ValueError, TypeError):
                continue
            if "completedJobs" in row and "durableJobReceipt" in row:
                n = row.get("completedJobs")
                jid = row.get("job")
                item = row["durableJobReceipt"]
                require(type(n) is int and n == len(source_completed)+1 and
                        isinstance(jid, str) and jid not in source_completed and
                        item.get("key") == PREFIX+plan_sha+"/slots/00001/jobs/"+jid+".json" and
                        SHA256.fullmatch(str(item.get("sha256", ""))) is not None and
                        re.fullmatch(r"\d+", str(item.get("generation", ""))) is not None,
                        "Missing original durable output job receipt in pixel gap wave")
                source_completed.append(jid)
            if row.get("status") == "source-pixel-gap-quarantined":
                require(row.get("attemptConsumed") is True and
                        row.get("sourceQualityUnchanged") is True and
                        isinstance(row.get("job"), str),
                        "Unverified original-source gap attempt")
                source_gap_logs.append(row["job"])
            if row.get("phase") == "production" and "sourcePixelGapJobs" in row:
                final_production.append(row)
        require(len(source_completed) == jobs_count and
                source_gap_logs == pixel_gaps and
                len(set(source_completed) | set(pixel_gaps)) == jobs_count+len(pixel_gaps) and
                len(final_production) == 1 and
                final_production[0].get("sourcePixelGapJobs") == pixel_gaps and
                final_production[0].get("jobs") == jobs_count and
                final_production[0].get("status") == "bounded-stop",
                "Nonmatching producer pixel-gap exclusion and independent recovery")
    elif batch is None:
        require(result.get("pixelGapAttemptsConsumed", 0) == 0,
                "Unexplained consumed source attempt")
    require(decimal(settlement.get("ceilingUSD")) in (Decimal("25"), Decimal("125")),
            "Unexpected production ceiling")
    if batch is not None:
        parsed=[]
        for line in producer_lines:
            try:parsed.append(json.loads(line[line.index('{'):]))
            except (ValueError,TypeError):continue
        finals=[r for r in parsed if r.get('phase')=='production']
        rows=[r for r in parsed if 'completedJobs' in r and 'durableJobReceipt' in r]
        require(len(finals)==1 and finals[0].get('batchClosure')==batch and
                finals[0].get('receiptRef')==result.get('workerReceipt') and
                finals[0].get('jobs')==jobs_count and
                finals[0].get('status') in ('complete','bounded-stop'),
                'Producer and independent batch closure disagree')
        require([r.get('job') for r in rows]==batch['acceptedJobIDs'] and len(rows)==jobs_count,
                'Batch accepted output receipt log differs')
        for n,row in enumerate(rows,1):
            ref_job=row['durableJobReceipt']
            require(row['completedJobs']==n and
                    ref_job.get('key')==PREFIX+plan_sha+'/slots/00001/jobs/'+row['job']+'.json' and
                    SHA256.fullmatch(str(ref_job.get('sha256',''))) is not None and
                    re.fullmatch(r'[1-9][0-9]*',str(ref_job.get('generation',''))) is not None,
                    'Batch output receipt lineage differs')
        require([r.get('job') for r in parsed if r.get('status')=='source-pixel-gap-quarantined']==pixel_gaps and
                set(pixel_gaps)<=set(batch['quarantinedJobIDs']) and
                (not (set(batch['quarantinedJobIDs'])-set(pixel_gaps)) or batch['fallbackRequired']),
                'Unexplained consumed batch attempts')
    cycle_rate=None;seconds=None
    if run.get('created_at') and recovery[0].get('completed_at'):
        from datetime import datetime
        seconds=(datetime.fromisoformat(recovery[0]['completed_at'].replace('Z','+00:00'))-
                 datetime.fromisoformat(run['created_at'].replace('Z','+00:00'))).total_seconds()
        require(seconds>0,'Invalid dispatch-to-recovery timing')
        cycle_rate=result['tiles']/seconds
    from rrgh_overview_integration import validate_verification
    overview_proof=validate_verification(result.get('overviewPilotVerification'))
    return {
        "verified": True,
        "batchClosure": batch,
        "cycleTilesPerSecond": cycle_rate,
        "recoveryCycleSeconds": seconds,
        "tilesNew": result.get("tiles"),
        "overviewPilotVerification": overview_proof,
        "partialRecovered": partial,
        "partialCompletedJobIDs": recovered_ids,
        "failedJobID": failed_job,
        "sourcePixelGapJobs": pixel_gaps,
        "sourceCompletedJobIDs": source_completed,
        "wave": sequence,
        "run": run.get("id"),
        "jobsNew": jobs_count,
        "acceptedJobs": carry["priorCompletedJobs"],
        "acceptedRasterTiles": carry["priorRasterTiles"],
        "sunlightAssets": carry["priorSunlightAssets"],
        "historicalExclusions": EXCLUDED,
        "receiptRef": reference,
        "nextCarry": carry,
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
    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, old_req, fp, code, msg, headers, newurl):
            from urllib.parse import urlsplit
            host = urlsplit(newurl).hostname
            require(host is not None and newurl.startswith("https://"), "Unsafe GitHub log redirect")
            redirected = super().redirect_request(old_req, fp, code, msg, headers, newurl)
            if redirected is None:
                return None
            # GitHub's signed log URL is another host: never forward API bearer.
            if host != "api.github.com":
                redirected.remove_header("Authorization")
                redirected.unredirected_hdrs.pop("Authorization", None)
            return redirected
    delays=(5,15,30,60)
    log_read=raw and re.fullmatch(r'actions/jobs/[1-9][0-9]*/logs',path) is not None
    for attempt in range(len(delays)+1):
        try:
            # Always reacquire the API redirect; never cache an expired signed
            # URL, forward its bearer token, or retain a partial log response.
            client = urllib.request.build_opener(SafeRedirect)
            with client.open(req, timeout=30) as response:
                data = response.read(12_000_001)
            require(len(data)<=12_000_000,'GitHub read response limit exceeded')
            break
        except urllib.error.HTTPError as e:
            reason='HTTP '+str(e.code)
            if e.code not in (408,429,500,502,503,504) and not (log_read and e.code==404):
                raise Halt('GitHub read '+reason+' at '+path.split('?')[0]) from None
        except (urllib.error.URLError,TimeoutError,ConnectionError,IncompleteRead) as e:
            reason=type(e).__name__
        if attempt==len(delays):
            raise Halt('GitHub read '+reason+' at '+path.split('?')[0]+'; bounded GET retries exhausted') from None
        print('CONTROLLER_READ_RETRY: '+reason+' at '+path.split('?')[0]+'; reacquiring read',file=sys.stderr)
        time.sleep(delays[attempt])
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
    producer = [j for j in jobs.get("jobs", []) if j.get("name") == "bounded-stage"]
    require(len(producer) == 1, "Missing producer job")
    producer_log = gh("actions/jobs/" + str(producer[0]["id"]) + "/logs", token, raw=True)
    return audit_run(run, jobs.get("jobs", []), log.splitlines(), producer_log.splitlines())


def main():
    require(os.environ.get("GITHUB_REPOSITORY") == REPO, "Wrong GitHub repository")
    token = os.environ.get("GH_TOKEN", "")
    require(bool(token), "No GitHub read token")
    report = review(token)
    artifact = os.environ.get("SUPERVISOR_OUTPUT_FILE")
    if artifact:
        with open(artifact, "w", encoding="utf-8") as fh:
            json.dump(report, fh, sort_keys=True)
    print(json.dumps(report, sort_keys=True))
    # Deliberate pilot stop. Never launch, modify source, or silently recurse.
    print("SUPERVISOR_READ_ONLY: Production dispatch requires separate approved billing gate.")


if __name__ == "__main__":
    try:
        main()
    except Halt as err:
        print("SUPERVISOR_STOP: " + str(err), file=sys.stderr)
        sys.exit(1)
