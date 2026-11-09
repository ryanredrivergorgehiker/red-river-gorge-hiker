#!/usr/bin/env python3
"""Plan the next full-quality wave under the exact dispatcher identity, offline only.

Run from a temporary checkout of the exact engineering source ref, with the
latest independent recovery receipt supplied from a separate trusted audit.
This module is outside backend/scripts so it does not change engine snapshots.
"""
import base64
import rrgh_crosswave_batch  # Bind trusted inventory before the source import path is added.
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
    match = re.search(r"CONFIG=SOURCE.parent/'config/gorge-campaign-wave-(\d{3,9})(-push)?-(\d{8})'", original_code)
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
    # Read the migrated engine again before rewriting its CONFIG pointer.
    # Otherwise the legacy source variable would silently undo the v2 fence.
    original_code = code_path.read_text()
    prior_plan_sha = digest(canonical(old))
    check(verified["planSHA256"] == prior_plan_sha, "Previous plan digest mismatch")
    ref = verified["receiptRef"]
    if verified.get('completedConsumedRecovery') is True:
        from rrgh_completion_contract import check_report
        check_report(verified)
    else:
        check(ref["key"] == "engineering/map-production/plans/" + prior_plan_sha +
              "/slots/00002/receipt.json", "Previous receipt key mismatch")
    check(verified["receiptSHA256"] == ref["sha256"], "Previous receipt hash mismatch")

    checkpoint=verified.get('checkpointRecovery') is not None
    prior_checkpoint=old['campaign'].get('checkpointRecoveryQuarantines',[])
    check(isinstance(prior_checkpoint,list) and len(prior_checkpoint)==len(set(prior_checkpoint)), 'Checkpoint quarantine duplicated')
    recovered_checkpoint=None
    if checkpoint:
        from rrgh_checkpoint_recovery import validate_planning
        recovered_checkpoint=validate_planning(old,verified)
    partial = verified.get("partialRecovered") is True
    pixel_gaps = verified.get("sourcePixelGapJobs", [])
    check(isinstance(pixel_gaps, list) and len(set(pixel_gaps)) == len(pixel_gaps),
          "Malformed verified pixel-gap exclusions")
    prior_pixel_gaps = old["campaign"].get("sourcePixelGapQuarantines", [])
    check(isinstance(prior_pixel_gaps, list) and
          len(set(prior_pixel_gaps)) == len(prior_pixel_gaps) and
          not set(prior_pixel_gaps) & set(old["completedJobIDs"]),
          "Inherited original-source pixel-gap quarantine corrupted")
    from rrgh_salvage_audit import manifest as salvage_manifest,manifest_sha
    salvage=verified.get('salvagedCheckpointRecovery') is True
    prior_salvage=old['campaign'].get('checkpointSalvageQuarantines',[])
    m=salvage_manifest()
    check(prior_salvage==([] if wave<=105 else m['uncertainJobIDs']), 'Salvage quarantine lineage changed')
    from rrgh_batch_contract import partition as batch_partition, next_policy
    batch=old.get('resumableBatch') is not None
    prior_batch=old['campaign'].get('batchQuarantines',[])
    batch_quarantines=[]
    if checkpoint:
        check(not batch and not partial and not salvage and not pixel_gaps,'Checkpoint recovery mixed with another exception')
        accepted=old['completedJobIDs']+recovered_checkpoint['completedJobIDs']
        attempted=old['approvedJobIDs']
    elif batch:
        check(not partial and not salvage, 'Batch closure cannot use historical incident exceptions')
        attempted,recovered,quarantined,untouched=batch_partition(old['approvedJobIDs'],verified.get('batchClosure'),prior_plan_sha)
        check(len(recovered)==verified['jobsNew'] and set(pixel_gaps)<=set(quarantined), 'Batch recovery inventory mismatch')
        accepted=old['completedJobIDs']+recovered
        batch_quarantines=[j for j in quarantined if j not in pixel_gaps]
    elif salvage:
        check(wave==105 and verified.get('run')==m['originalRunID'] and prior_plan_sha==m['planSHA256'] and
              verified.get('salvageManifestSHA256')==manifest_sha() and
              verified.get('partialCompletedJobIDs')==m['completedJobIDs'] and
              verified.get('uncertainJobIDs')==m['uncertainJobIDs'] and
              old['approvedJobIDs']==m['completedJobIDs']+m['uncertainJobIDs'] and
              verified.get('failedJobID') is None and not pixel_gaps,'Exact salvage evidence mismatch')
        accepted=old['completedJobIDs']+m['completedJobIDs']
        attempted=old['approvedJobIDs']
    elif partial:
        # Exact, independently verified partial incidents only. Every consumed
        # prefix and the failing attempt are retained; never replay a checkpoint.
        incidents = {
            260: (41687927485,
                  "65e5d8891320ca386dbdaced9acfc3956a3153fc64c8556e132cbc1b6a1b4b88",
                  9, "leaf-off-16-17512-25319"),
            23: (41225003991,
                 "b661abadce4c7977e2e3d7770e76d8912d8f9bd4d79bfac8a0531f097588dffb",
                 207, "usgs-topo-16-17570-25321"),
            34: (41324364372,
                 "d8fc62a5caf21e86283821666157591d3b23d4a257725306de5cb14a60c026fd",
                 488, "leaf-on-16-17575-25345"),
        }
        check(wave in incidents, "Unreviewed partial incident")
        run_id, pinned_plan, count, failed = incidents[wave]
        check(verified.get("run") == run_id and
              verified.get("planSHA256") == pinned_plan and
              verified.get("failedJobID") == failed,
              "Pinned partial incident identity mismatch")
        recovered = verified.get("partialCompletedJobIDs")
        check(isinstance(recovered, list) and len(recovered) == count and
              recovered == old["approvedJobIDs"][:count] and
              failed == old["approvedJobIDs"][count] and
              failed not in recovered,
              "Exact recovered prefix and failed attempt mismatch")
        accepted = old["completedJobIDs"] + recovered
        attempted = old["approvedJobIDs"][:count + 1]
    elif pixel_gaps:
        check(verified.get("partialCompletedJobIDs") == [] and
              verified.get("failedJobID") is None,
              "Source pixel gaps cannot be conflated with ambiguous failed allocations")
        source_success = verified.get("sourceCompletedJobIDs")
        check(isinstance(source_success, list) and
              len(source_success) == verified.get("jobsNew") and
              len(source_success) + len(pixel_gaps) == len(old["approvedJobIDs"]) and
              set(source_success).isdisjoint(pixel_gaps) and
              set(source_success) | set(pixel_gaps) == set(old["approvedJobIDs"]) and
              len(set(source_success)) == len(source_success),
              "Independent source gap evidence disagrees with exact prior allocation")
        accepted = old["completedJobIDs"] + source_success
        attempted = old["approvedJobIDs"]
    else:
        check(verified.get("partialCompletedJobIDs") == [] and
              verified.get("failedJobID") is None and
              verified.get("sourceCompletedJobIDs", []) == [],
              "Unexpected incident metadata on complete ordinary wave")
        accepted = old["completedJobIDs"] + old["approvedJobIDs"]
        attempted = old["approvedJobIDs"]
    check(len(accepted) == len(set(accepted)) == verified["acceptedJobs"],
          "Prior accepted jobs disagree with independent settlement")
    check(verified["acceptedRasterTiles"] >= len(accepted), "Raster count regression")
    check(verified["sunlightAssets"] == 320, "Sunlight regression")
    before_attempts = old["priorAttemptCounts"].copy()
    historical_excluded = {jid for jid, n in before_attempts.items()
                           if n > 0 and jid not in accepted}
    inherited_exclusion_count = 45 + (1 if wave > 23 else 0) + (1 if wave > 34 else 0) + (1 if wave > 260 else 0) + len(prior_pixel_gaps) + len(prior_salvage) + len(prior_batch) + len(prior_checkpoint)
    check(len(historical_excluded) == inherited_exclusion_count and
          set(prior_pixel_gaps) <= historical_excluded and set(prior_batch) <= historical_excluded and
          set(prior_checkpoint) <= historical_excluded and
          verified["historicalExclusions"] == 45,
          "Historical exclusions or incident quarantine changed")
    check(not set(accepted) & historical_excluded, "Accepted and excluded overlap")
    check(old["campaign"]["ambiguousExcludedJobs"] ==
          ["leaf-on-16-17535-25316", "leaf-on-16-17556-25323"],
          "Historic two transport ambiguities changed")
    for jid in attempted:
        check(before_attempts.get(jid, 0) == 0, "Previously attempted new job")
        before_attempts[jid] = 1
    excluded = {jid for jid, n in before_attempts.items() if n > 0 and jid not in accepted}
    check(len(excluded) == inherited_exclusion_count + (len(m["uncertainJobIDs"]) if salvage else 1 if partial else 0) + len(pixel_gaps) + len(batch_quarantines) + (len(recovered_checkpoint['uncertainJobIDs']) if checkpoint else 0) and
          set(pixel_gaps) <= excluded and
          (not partial or salvage or verified["failedJobID"] in excluded),
          "Failed job must remain excluded from fresh territory")
    check(all(n <= 2 for n in before_attempts.values()), "Attempt overflow")

    from rrgh_expanded_production import build_index, migration, install_engine, LIMITS
    # Validate prior scope against the prior inventory before any expansion.
    index, missing = build_index(region)
    expected_index = 25900 if region.get('expandedSourceProduction', {}).get('mode') == 'expanded' else 11940
    check(len(index) == expected_index, "Pinned source inventory changed")
    from rrgh_overview_integration import validate_previous,install as install_overview,select as select_overview,MODULES as OVERVIEW_MODULES
    validate_previous(old,region)
    from rrgh_completion_phase import lower_usgs_index, validate_plan as validate_completion, select as select_completion, PHASE, PHASE_V1, phase_for, job_policy
    if old.get('completionPhase'):
        validate_completion(old,region,verified.get('completionPolicy'))
    from rrgh_overview_integration import validate_recovery
    validate_recovery(old,verified)
    for prior in region["jobs"]:
        if prior['operation']=='overview':continue
        prior_index=lower_usgs_index(region) if old.get('completionPhase') else index
        check(prior == prior_index[prior["id"]], "Source-pinned prior job changed")
    prior_region=copy.deepcopy(region)
    migration(region, verified.get('sourcePolicyMode', 'expanded'))
    install_engine(root)
    from rrgh_recovery_catalog_integration import install as install_catalog, MODULE as CATALOG_MODULE
    from rrgh_batch_integration import strip as strip_batch, install as install_batch, installed as batch_installed, MODULES as BATCH_MODULES
    code_path.write_text(strip_batch(code_path.read_text()))
    install_catalog(root)
    from rrgh_credential_integration import install as install_credentials, MODULE as CRED_MODULE
    install_credentials(root)
    install_overview(root)
    batch_policy=next_policy(old,verified)
    if batch_policy or batch_installed(root):install_batch(root)
    original_code=code_path.read_text()
    index, missing = build_index(region)
    if region['expandedSourceProduction']['mode'] == 'expanded':
        check(len(index) == 25900 and sum(missing.values()) == 0,
              "Expanded catalog metadata does not cover unchanged region")
    limits = {k:(batch_policy['targetJobs']//3 if batch_policy else v) for k,v in LIMITS.items()}
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
        # The finite regional grid is being exhausted: do not invent windows
        # or require artificial 256-job family quotas. Keep every selected
        # window source-backed, full-resolution, fresh and non-overlapping.
        sample = eligible[:limit]
        if not sample:
            continue
        sample.sort(key=lambda job: (
            tuple(job["sourceIDs"]), morton(job["x"], job["y"]), job["id"]))
        picked.extend(sample)
    picked,overview_pilot=select_overview(picked,accepted,before_attempts,verified.get('overviewPilotEnabled') is True and batch_policy is None)
    completion_phase=None
    crosswave_phase=None
    crosswave_history=None
    if not picked and verified.get('crosswavePolicy') is not None:
        from rrgh_crosswave_phase import POLICY as CW_POLICY,select as select_crosswave,waiting_summary as crosswave_wait
        from rrgh_crosswave_batch import POLICY as CW_BATCH,TYPED_POLICY,advance_history,select as select_batch
        if verified['crosswavePolicy'] in (CW_BATCH,TYPED_POLICY):
            check(old.get('crosswavePhase') is not None,'Batch requires independently verified overview predecessor')
            if verified['crosswavePolicy']==TYPED_POLICY:
                check(wave>=1358 and old['crosswavePhase']['format']=='rrgh-crosswave-batch-phase-v2' and
                    verified.get('overviewPilotVerification',{}).get('allParentsIndependentlyRecomputed') is True,
                    'Typed readers require an independently verified ordinary batch')
            if old['crosswavePhase']['format']=='rrgh-crosswave-pilot-phase-v1':
                check(wave==CW_BATCH['baselineSequence'] and prior_plan_sha==CW_BATCH['baselinePlanSHA256'] and
                    verified['receiptRef']==CW_BATCH['verifiedPilotRecovery'] and verified['acceptedRasterTiles']==267476,
                    'Measured batch must start at the exact verified pilot')
            crosswave_history=advance_history(old,prior_region,verified)
            picked,crosswave_phase=select_batch(accepted,before_attempts,verified['crosswavePolicy'],crosswave_history)
        else:
            if not old.get('crosswavePhase'):
                check(wave==CW_POLICY['baselineSequence'] and prior_plan_sha==CW_POLICY['baselinePlanSHA256'] and
                    verified['acceptedRasterTiles']==CW_POLICY['baselineAcceptedTiles'] and
                    not select_completion(region,accepted,before_attempts,verified['completionPolicy']),
                    'Cross-wave pilot must start at the independently settled USGS boundary')
            picked,crosswave_phase=select_crosswave(accepted,before_attempts,verified['crosswavePolicy'])
        limits={}
        if not picked:
            summary=crosswave_wait(old,region,verified)
            (root/'RRGH-COMPLETION-WAIT.json').write_bytes(canonical(summary))
            return summary
    if not picked and verified.get('completionPolicy') is not None:
        from rrgh_completion_phase import BASELINE_PLAN
        check(old.get('completionPhase') in (PHASE,PHASE_V1) or
              (wave==1322 and prior_plan_sha==BASELINE_PLAN and verified['acceptedRasterTiles']==265702),
              'Completion queue requires exact approved baseline or enrolled predecessor')
        picked=select_completion(region,accepted,before_attempts,verified['completionPolicy'])
        completion_phase=copy.deepcopy(phase_for(verified['completionPolicy']))
        limits={'usgs-topo':verified['completionPolicy']['maxJobs']}
        if not picked and old.get('completionPhase'):
            from rrgh_completion_phase import waiting_summary
            summary=waiting_summary(old,region,verified)
            (root/'RRGH-COMPLETION-WAIT.json').write_bytes(canonical(summary))
            return summary
    jobs = [j["id"] for j in picked]
    check(bool(jobs),
          "SOURCE_TERRITORY_EXHAUSTED: no fresh source-backed hiking, terrain or leaf-off "
          "jobs remain; do not replay attempted jobs or pad the wave. "
          "Next work requires reviewed source/layer coverage before a new wave.")
    check(len(jobs) <= 512 and len(jobs) == len(set(jobs)) and
          not set(jobs) & (set(accepted)|excluded), "Job scope overlap")
    selected_counts = Counter(j["layer"] for j in picked if j["operation"]!="overview")
    check(set(selected_counts) <= set(limits) and
          all(0 < count <= limits[layer] for layer, count in selected_counts.items()),
          "Unexpected layer mix or finite family cap")
    expected_tiles = sum(len(j["outputTiles"]) for j in picked)
    # The count is determined by exact regional geometry, not a historical
    # constant: border windows naturally contain fewer children over time.
    # Check every chosen window against its full-resolution source profile,
    # reject duplicate outputs, and never pad or downsample to meet a quota.
    check(all(len(j["outputTiles"]) >= 1 and
              len(j["outputTiles"]) <= (1 if j["layer"] == "usgs-topo" else 21)
              for j in picked), "Selected window has invalid tile geometry")
    unique_outputs = {(j["layer"], *tile) for j in picked
                      for tile in j["outputTiles"]}
    check(len(unique_outputs) == expected_tiles,
          "Duplicate output tile in fresh allocation")
    check(len(jobs) <= expected_tiles <= 256 + 256*21,
          "Unexpected geometry-derived tile count: "+str(expected_tiles))

    # Preserve original Wave000 per-layer source/time caps, rather than inferring
    # authorization only from the most recent topo/leaf-on batch.
    historic = json.loads((root / "backend/config/gorge-campaign-wave-000-20261030/PLAN.json").read_bytes())
    policy = {}
    for jid, perjob in historic["jobPolicies"].items():
        layer = jid.rsplit("-", 3)[0]
        if layer in policy:
            check(policy[layer] == perjob, "Historic policy inconsistent")
        else:
            policy[layer] = perjob
    check(policy.get("hiking") == {"seconds":600,"sourceBytes":67108864,"sourceRequests":150}
          and policy.get("terrain") == {"seconds":600,"sourceBytes":134217728,"sourceRequests":200}
          and policy.get("leaf-off") == {"seconds":600,"sourceBytes":536870912,"sourceRequests":750},
          "Original source and time bounds changed")
    for jid, perjob in old["jobPolicies"].items():
        if old.get('crosswavePhase') or (old.get('overviewPilot') or {}).get('job')==jid:
            prior_seconds=60 if old.get('crosswavePhase',{}).get('format')=='rrgh-crosswave-batch-phase-v2' else 600
            check(perjob==dict(seconds=prior_seconds,sourceBytes=0,sourceRequests=0),'Overview source caps changed')
        elif old.get('completionPhase'):
            check(perjob==job_policy(old['completionPhase']['authority']),'Prior completion policy changed')
        else:check(policy[jid.rsplit("-", 3)[0]] == perjob, "Prior layer policy changed")
    if completion_phase:policy['usgs-topo']=job_policy(verified['completionPolicy'])
    overview_seconds=60 if crosswave_phase and crosswave_phase['format']=='rrgh-crosswave-batch-phase-v2' else 600
    picked_policies={j['id']:(dict(seconds=overview_seconds,sourceBytes=0,sourceRequests=0) if j['operation']=='overview' else policy[j['layer']]) for j in picked}
    check(all(x in policy for x in limits), "Missing original approved layer policy")
    check(sum(picked_policies[j['id']]['sourceRequests'] for j in picked)
          <= old["slots"][1]["sourceRequests"], "Source requests cannot exceed prior envelope")
    check(sum(picked_policies[j['id']]['sourceBytes'] for j in picked)
          <= old["slots"][1]["sourceBytes"], "Source bytes cannot exceed prior envelope")
    if not batch_policy:
        check(sum(picked_policies[j['id']]['seconds'] for j in picked)<=old['slots'][1]['seconds'],
              'Production seconds cannot exceed prior envelope')
    # A larger finite allocation is an eligibility list, not permission to start
    # every job. The coordinator reserves whole pairs against the unchanged slot.

    # Update only the one canonical source CONFIG pin. Old source files remain
    # byte-identical, and the new scope is generated from the same provenance.
    before = f"CONFIG=SOURCE.parent/'config/{prefix}{wave:03d}{suffix}-{date}'"
    after = f"CONFIG=SOURCE.parent/'config/{prefix}{wave+1:03d}-{date}'"
    check(original_code.count(before) == 1, "Canonical source pin not unique")
    code_path.write_text(original_code.replace(before, after))

    plan = copy.deepcopy(old)
    plan['resumableBatch']=batch_policy
    plan['campaign']['batchQuarantines']=prior_batch+batch_quarantines
    if checkpoint or prior_checkpoint:
        plan['campaign']['checkpointRecoveryQuarantines']=prior_checkpoint+(recovered_checkpoint['uncertainJobIDs'] if checkpoint else [])
    plan["campaign"]["sequence"] = wave + 1
    plan["campaign"]["sourcePixelGapQuarantines"] = prior_pixel_gaps + pixel_gaps
    plan["campaign"]["checkpointSalvageQuarantines"] = prior_salvage + (m["uncertainJobIDs"] if salvage else [])
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
    plan['overviewPilot']=overview_pilot
    if crosswave_phase:plan['crosswavePhase']=crosswave_phase
    else:plan.pop('crosswavePhase',None)
    if completion_phase:plan['completionPhase']=completion_phase
    else:plan.pop('completionPhase',None)
    plan['jobPolicies']=picked_policies
    if crosswave_history is not None:
        plan['crosswaveHistory']=crosswave_history
        from rrgh_crosswave_batch import fund
        fund(plan)
    plan["slots"][1]["attempts"] = len(jobs)
    plan["limits"]["attempts"] = len(jobs)
    check(plan["slots"][1]["classARequests"] == 2000 and
          3*len(jobs)+32 < 2000, "No producer Class-A headroom")
    region["jobs"] = picked
    check("gorge_campaign.py" in region["engineHashes"], "Missing engine hash")
    region["engineHashes"]["gorge_campaign.py"] = digest(code_path.read_bytes())
    region["engineHashes"]["benchmark_gorge_pipeline.py"] = digest(
        (root / "backend/scripts/benchmark_gorge_pipeline.py").read_bytes())
    if batch_installed(root):
        for name in BATCH_MODULES:
            region['engineHashes'][name]=digest((root/'backend/scripts'/name).read_bytes())
    for overview_module in OVERVIEW_MODULES:
        region['engineHashes'][overview_module]=digest((root/'backend/scripts'/overview_module).read_bytes())
    for credential_file in ('run_gorge_checkpoint_slot.py',CRED_MODULE):
        region['engineHashes'][credential_file]=digest((root/'backend/scripts'/credential_file).read_bytes())
    region['engineHashes'][CATALOG_MODULE]=digest((root/'backend/scripts'/CATALOG_MODULE).read_bytes())
    if "gorge_campaign_budget.py" in region["engineHashes"]:
        region["engineHashes"]["gorge_campaign_budget.py"] = digest(budget_path.read_bytes())
    identity = root / "backend/scripts/gorge_producer_identity.py"
    check(identity.is_file() and 'offline-map-restricted-dispatch.yml' in identity.read_text(),
          "Reviewed exact dispatcher identity guard missing")
    check(plan["campaign"].get("controllerEpoch") == 1, "Exclusive controller epoch changed")
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
