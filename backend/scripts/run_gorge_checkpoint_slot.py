#!/usr/bin/env python3
"""Plan-only by default. Execute ONE funded, immutable engineering slot.

Bulk production remains disabled. No workflow dispatch, IAM, catalog, deployment,
artifact/cache upload, source-cache deletion or budget mutation exists here.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from gorge_checkpoint import (GCS, Slot, canonical, digest, validate_plan,
                              require_live_allowance, pack_delta)
from gorge_guarded_worker import run_job, checkpoint_job


def code_snapshot(directory):
    return digest(canonical({p.name:digest(p.read_bytes()) for p in sorted(Path(directory).glob('*.py'))
                             if not p.name.startswith('test_')}))


def preflight(plan, region, source_dir):
    totals=validate_plan(plan)
    if plan.get('regionPlanSHA256')!=digest(canonical(region)):
        raise ValueError('Region plan changed')
    if plan['sourceSnapshotSHA256']!=code_snapshot(source_dir):
        raise ValueError('Executable source snapshot changed')
    if region.get('format')!='rrgh-region-plan-v1':raise ValueError('Region plan required')
    all_jobs={j['id']:j for j in region['jobs']}
    assigned=[j for jobs in plan.get('slotJobs',{}).values() for j in jobs]
    if not set(assigned)<=all_jobs.keys():raise ValueError('Assigned job absent from region plan')
    if any(len(jobs)>12 for jobs in plan.get('slotJobs',{}).values()):
        raise ValueError('This engineering driver allows at most 12 jobs per slot')
    for key,sha in region['engineHashes'].items():
        if Path(key).name!=key or digest((Path(source_dir)/key).read_bytes())!=sha:
            raise ValueError('Region engine pin changed')
    return totals


# Process-local only: never persist or log the bearer credential. The existing
# WIF login emits a one-hour access token; use a much shorter 10-minute cache.
# This avoids requesting a new external credential for every immutable GCS GET.
_TOKEN_LOCK=threading.Lock()
_TOKEN_VALUE=None
_TOKEN_UNTIL=0.0
_TOKEN_CACHE_SECONDS=600

def token():
    global _TOKEN_VALUE,_TOKEN_UNTIL
    with _TOKEN_LOCK:
        now=time.monotonic()
        if _TOKEN_VALUE is not None and now<_TOKEN_UNTIL:
            return _TOKEN_VALUE
        # No retry, fallback or extension of stale credentials. Unexpected
        # auth failure still stops all cloud work and preserves prior receipts.
        result=subprocess.run(['gcloud','auth','print-access-token','--quiet'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=30,text=True)
        value=result.stdout.strip()
        if result.returncode or not value or any(c.isspace() for c in value):
            _TOKEN_VALUE=None
            _TOKEN_UNTIL=0.0
            raise RuntimeError('Short-lived WIF credential unavailable')
        _TOKEN_VALUE=value
        _TOKEN_UNTIL=time.monotonic()+_TOKEN_CACHE_SECONDS
        return value


def execute(args,plan,region,evidence):
    from gorge_stage_preflight import require_stage_release, require_input_proof, install_prior_tiles
    require_stage_release(plan,evidence)
    expected={'GITHUB_REPOSITORY_ID':'1325611891','GITHUB_REPOSITORY_OWNER_ID':'313924954',
      'GITHUB_REF':'refs/heads/lane20/offline-production-preflight-20261029',
      'GITHUB_EVENT_NAME':'push',
      'GITHUB_WORKFLOW_REF':'ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029'}
    if any(os.environ.get(k)!=v for k,v in expected.items()):
        raise ValueError('Requires the existing exact dedicated engineering workflow context')
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('Automatic reruns cannot reuse a spending slot')
    root=Path(args.output).resolve();source=Path(__file__).resolve().parents[2]
    if source==root or source in root.parents or 'public' in root.parts:
        raise ValueError('Private output outside checkout required')
    if root.exists():raise ValueError('New per-slot private workspace required')
    # All local configuration checks precede the first credential lookup or write.
    jobs=plan.get('slotJobs',{}).get(str(args.slot),[])
    policies=plan.get('jobPolicies',{})
    if any(j not in policies for j in jobs):raise ValueError('Every job needs explicit source/time bounds')
    if not args.input_proof or not args.prior_root or not args.shared_root:
        raise ValueError('Generation-pinned private input proof required before cloud operations')
    verified=require_input_proof(plan,json.loads(args.input_proof.read_bytes()),
        {'cog':args.cog_cache,'service':args.service_cache,'prior':args.prior_root,'shared':args.shared_root})
    store=GCS(plan,evidence,token);slot=Slot(store,plan,args.slot,os.environ.get('GITHUB_RUN_ID',''))
    root.mkdir(parents=True,exist_ok=False);completed=[]
    install_prior_tiles(verified,root)
    # Source caches are intentionally supplied as prevalidated local selections.
    # The driver never searches GCS, imports every cache, or recreates old ledgers.
    for job in jobs:
        prior=[int(i) for i,ids in plan.get('slotJobs',{}).items() if int(i)<args.slot and job in ids]
        if prior:
            # A missing/ambiguous earlier receipt stops. Never infer permission to
            # rerender from an absent final slot receipt after a runner crash.
            ref,previous=slot.recover_job(max(prior),job)
            completed.append(asdict(ref))
            continue
        policy=policies[job]
        receipt=run_job(slot,args.region_plan,job,root,args.cog_cache,args.service_cache,
                        policy,policy['seconds'])
        ref=checkpoint_job(slot,receipt,root);completed.append(asdict(ref))
        # Private local pointer; each deterministic per-job receipt is durable too.
        (root/'RECOVERY-POINTERS.json').write_bytes(canonical(completed))
    cache_refs=[]
    for selection in plan.get('cacheDeltas',{}).get(str(args.slot),[]):
        # Entries/root are explicit private planning inputs, never CLI discovery.
        for raw,info in pack_delta(selection['root'],selection['entries'],selection.get('knownHashes',[])):
            # Large member catalogs have their own metered, hash-pinned object.
            # No provenance is omitted to fit a compact final receipt.
            catalog={'format':'rrgh-cache-pack-catalog-v1',
                     'ref':asdict(slot.put(raw)), 'members':info['members']}
            cache_refs.append(asdict(slot.put_catalog(catalog)))
    final=slot.finish({'completedJobReceipts':completed,'cacheCatalogs':cache_refs})
    (root/'FINAL-RECOVERY-POINTER.json').write_bytes(canonical(asdict(final)))
    return {'jobsCompleted':len(completed),'slot':args.slot,'bulkProductionEnabled':False,
            'cloudCheckpointSaved':True,'budgetAllocationNotRefunded':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','region-plan','evidence'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--slot',type=int,default=0);p.add_argument('--execute',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--cog-cache',type=Path);p.add_argument('--service-cache',type=Path)
    p.add_argument('--input-proof',type=Path);p.add_argument('--prior-root',type=Path);p.add_argument('--shared-root',type=Path)
    args=p.parse_args();plan=json.loads(args.plan.read_bytes());region=json.loads(args.region_plan.read_bytes())
    evidence=json.loads(args.evidence.read_bytes());totals=preflight(plan,region,Path(__file__).parent)
    if args.execute:
        if not all((args.output,args.cog_cache,args.service_cache)):p.error('Explicit private paths required')
        result=execute(args,plan,region,evidence)
    else:
        result={'planValid':True,'cumulativeAllocations':totals,'productionDispatched':False,
                'executeRequested':False,'spendingAuthorized':False}
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
