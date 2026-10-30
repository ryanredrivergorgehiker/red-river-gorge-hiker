#!/usr/bin/env python3
"""Second owner-released stage: twelve exact new jobs, then fresh recovery.

No seed/Base transfer, old-ledger reset, rerender, campaign dispatcher or retry.
An immutable stage fence and finite claims precede every cloud/source operation.
"""
import argparse, base64, json, os, shutil, subprocess, sys, time, zlib
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from collections import defaultdict

from gorge_checkpoint import (GCS, Slot, Ref, canonical, digest, decode_record,
    recover_members, recovery_ranges, require_live_allowance, DIMENSIONS, PREFIX)
from gorge_stage_coordinator import CountedOpener, private_root, signal, snapshot_cache, save_delta, verify_outputs
from gorge_stage_inputs import private_write, PROOF_CAP
from gorge_stage_preflight import BASE_KEY, BASE_SHA, BASE_BYTES
from gorge_guarded_worker import run_job, checkpoint_job
from gorge_stage_reconcile import create_fence
from gorge_cache_selection import seed_selected_cog
from run_gorge_checkpoint_slot import preflight, token

SOURCE=Path(__file__).resolve().parent
CONFIG=SOURCE.parent/'config/gorge-second-stage-20261030'
APPROVAL='Owner 2026-10-30: SECOND BOUNDED MAP-PRODUCTION STAGE; additional USD 0.35; USD 7.30 locked'
STAGE='second-adjacent-12-job-20261030'
GROWTH_CAP=448*2**20
TILE_CAP=512*1024
TOTAL_OUTPUT_CAP=32*2**20
STATE_CAP=12*2**20
LIMITS=dict(storedBytes=2**30,egressBytes=2**30,classARequests=200,classBRequests=500,
    sourceBytes=2**31,sourceRequests=2000,seconds=10800,attempts=12)
JOBS=[f'{layer}-16-17545-{y}' for layer in ('hiking','terrain','leaf-off','leaf-on','usgs-topo') for y in (25324,25325)]+['hiking-16-17546-25324','terrain-16-17546-25324']

def configuration(directory=CONFIG):
    directory=Path(directory);plan=json.loads((directory/'PLAN.json').read_bytes())
    evidence=json.loads((directory/'ALLOWANCE.json').read_bytes())
    d=zlib.decompressobj();raw=d.decompress(base64.b64decode((directory/'REGION-PLAN.json.z.b64').read_bytes()),4*2**20)
    if not d.eof or d.unused_data or d.unconsumed_tail:raise ValueError('Region bound')
    region=json.loads(raw);preflight(plan,region,SOURCE);require_live_allowance(plan,evidence)
    if (plan.get('purpose')!=STAGE or plan.get('ownerApproval')!=APPROVAL or plan.get('maxConcurrency')!=1
        or plan['limits']!=LIMITS or plan.get('approvedJobIDs')!=JOBS or plan.get('slotJobs')!={'1':JOBS}
        or len(set(plan['completedJobIDs']))!=32 or set(JOBS)&set(plan['completedJobIDs'])
        or plan.get('priorAttemptCounts')!={} or plan.get('inputBinding')!='accepted-generation-proof-selective-v1'):
        raise ValueError('Exact second-stage authority required')
    release=evidence['stageRelease']
    if (release!={'approvalReference':APPROVAL,'planSHA256':digest(canonical(plan)),
        'campaignApprovedUSD':'8.00','releasedUSD':'0.35','priorReleasedUSD':'0.35',
        'lockedUSD':'7.30','approvedRecurringUSDPerMonth':'1.00'}
        or Decimal(evidence['cloudStorageAllowance']['approvedUSD'])!=Decimal('.35')):
        raise ValueError('Campaign release differs')
    if (len(region['jobs'])!=12 or [j['id'] for j in region['jobs']]!=JOBS
        or sum(len(j['outputTiles']) for j in region['jobs'])!=116
        or any(j.get('dependencies') or j.get('preservedComplete') for j in region['jobs'])):
        raise ValueError('Exact adjacent unfinished coverage required')
    if plan['workerEnvelope']!={'cacheGrowthBytes':GROWTH_CAP,'totalOutputBytes':TOTAL_OUTPUT_CAP,'stateBytes':STATE_CAP,'outputBytesPerTile':TILE_CAP}:
        raise ValueError('Full quality preservation capacity differs')
    if (len(plan['slots'])!=3 or plan['slots'][0]['egressBytes']<128*2**20
        or plan['slots'][1]['storedBytes']<512*2**20 or plan['slots'][2]['egressBytes']<760*2**20
        or plan['slots'][1]['classARequests']<174 or plan['slots'][2]['classBRequests']<320):
        raise ValueError('Complete production and independent recovery must be prepaid')
    continuation=plan.get('continuation',{})
    old=json.loads((SOURCE.parent/'config/gorge-second-stage-initial-20261030/PLAN.json').read_bytes())
    if (continuation.get('previousPlanSHA256')!=digest(canonical(old))
        or continuation.get('previousPlanSHA256')!='96d4dc0ed6ba530bbe84ae9d0bed57e832a56e069ee266fec8e89858504e22e7'
        or continuation.get('retainedAllocation')!=old['slots'][0]
        or continuation.get('unstartedSlots')!=[1,2] or continuation.get('refundsApplied') is not False):
        raise ValueError('Original preflight allocation must remain fully reserved')
    for k in DIMENSIONS:
        if old['slots'][0][k]+sum(x[k]for x in plan['slots'])>LIMITS[k]:raise ValueError('Cumulative second stage ceiling exceeded')
    for k in ('sourceBytes','sourceRequests','seconds'):
        if sum(plan['jobPolicies'][j][k] for j in JOBS)>plan['slots'][1][k]:raise ValueError('Child allocations exceed worker')
    if plan['githubBilling']['spentUSD']!='281.53' or plan['githubBilling']['headroomUSD']!='68.47' or not plan['githubBilling']['stopAtLimitVerified']:
        raise ValueError('Fresh headroom not bound')
    layouts=plan['cacheRanges'];ranges,total=recovery_ranges(layouts,[e['path'] for c in layouts for e in c['members']])
    if len(ranges)!=7 or total!=19202048 or sum(len(c['members']) for c in layouts)!=293:raise ValueError('Selective cache changed')
    return plan,evidence,region

def record(slot,ref,expected_format='rrgh-slot-receipt-v1'):
    obj=decode_record(slot.get(Ref(**ref)),PROOF_CAP)
    if obj.get('format')!=expected_format:raise ValueError('Historical record format')
    return obj

def neighboring_paths(region,entries):
    wanted={(j['layer'],*t) for j in region['jobs'] for t in j['outputTiles']};neighbors=set()
    for layer,z,x,y in wanted:
        neighbors.update((layer,z,xx,yy) for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)) if (layer,z,xx,yy) not in wanted)
    result=[]
    for e in entries:
        p=Path(e['path']);parts=p.parts
        if len(parts)==5 and parts[0]=='tiles' and (parts[1],int(parts[2]),int(parts[3]),int(p.stem)) in neighbors:result.append(e)
    return result

def proof_catalogs(proof,files):
    groups={}
    for e in files:
        ref=proof['checkpointRefs'][e['checkpointIndex']];key=tuple(ref.values())
        groups.setdefault(key,{'ref':ref,'members':[]})['members'].append({k:e[k] for k in ('path','bytes','sha256','offset')})
    return list(groups.values())

def recover_catalogs(slot,catalogs,paths,destination):
    """One read per immutable extent, with exact-content aliases preserved.

    The confirmed writer can reuse identical packs across different jobs.
    Only the same generation, offset, length AND SHA can share recovered bytes;
    partial overlaps or conflicting content still fail the strict range parser.
    """
    wanted=set(paths);seen_paths=set();extents={};groups={};aliases=[]
    for c in catalogs:
        ref=Ref(**c['ref'])
        for e in c['members']:
            if e['path'] not in wanted:continue
            if e['path'] in seen_paths:raise ValueError('Duplicate recovery path')
            seen_paths.add(e['path']);identity=(ref,e['offset'],e['bytes'],e['sha256'])
            if identity in extents:aliases.append((e,extents[identity]))
            else:
                extents[identity]=e['path'];groups.setdefault(ref,[]).append(e)
    if seen_paths!=wanted:raise ValueError('Missing recovery path')
    result=recover_members(slot,[{'ref':asdict(r),'members':es}for r,es in groups.items()],list(extents.values()),destination)
    from gorge_checkpoint import relative_path
    for e,original in aliases:
        target=Path(destination)/relative_path(e['path']);source=Path(destination)/original
        if source.stat().st_size!=e['bytes'] or digest(source.read_bytes())!=e['sha256']:raise ValueError('Alias hash differs')
        target.parent.mkdir(parents=True,exist_ok=True);os.link(source,target)
    return {**result,'files':len(wanted),'exactContentAliases':len(aliases)}

def bootstrap(slot,plan,region,root):
    h=plan['history'];initial=record(slot,h['bootstrap'])
    final=record(slot,h['finalRecovery'])
    qa=json.loads(slot.get(Ref(**h['finalQA'])))
    if (initial['result'].get('inputProofValidated') is not True or initial['result']['proofRef']!=h['proof']
        or final['result'].get('status')!='all-twelve-jobs-verified' or final['result']['qaRef']!=h['finalQA']
        or qa.get('jobs')!=12 or qa.get('tiles')!=108 or qa.get('bytes')!=3149357
        or initial['result']['vectorValidation']['vectorLayers']!=13
        or initial['result']['vectorValidation']['vectorFeatures']!=19789):raise ValueError('Accepted input/completion lineage changed')
    proof=record(slot,h['proof'],'rrgh-stage-input-proof-v1')
    base=proof['acceptedBase']
    if (base!=initial['result']['acceptedBase'] or base['key']!=BASE_KEY or base['sha256']!=BASE_SHA
        or base['bytes']!=BASE_BYTES or base['generation']!='1791470288796565'):
        raise ValueError('Accepted Base pin changed')
    if sorted(r['job'] for r in proof['priorReceipts'])!=sorted(plan['acceptedPriorDependencies']):raise ValueError('Accepted dependency receipt inventory changed')
    # Source cache extents must be present verbatim in the accepted private proof.
    lookup={(e['kind'],e['path']):e for e in proof['files']}
    selected=[]
    for catalog in plan['cacheRanges']:
        for e in catalog['members']:
            name=e['path'].removeprefix('cog-cache/');old=lookup.get(('cog',name))
            if old is None or any(old[k]!=e[k] for k in ('bytes','sha256','offset')) or proof['checkpointRefs'][old['checkpointIndex']]!=catalog['ref']:
                raise ValueError('Selected cache range differs from accepted proof')
            selected.append({**old,'path':'cog/'+name})
    from benchmark_ky_naip_usgs import NAIP,ServiceCache
    metadata_key=digest((NAIP+'?f=pjson').encode())
    services=[e for e in proof['files'] if e['kind']=='service' and e['path'] in (metadata_key+'.bin',metadata_key+'.json')]
    if len(services)!=2:raise ValueError('Preserved NAIP metadata pair missing')
    shared=[e for e in proof['files'] if e['kind']=='shared']
    if not shared or sum(e['bytes'] for e in shared)>80*2**20:raise ValueError('Shared input preservation bound')
    old_neighbors=neighboring_paths(region,[e for e in proof['files'] if e['kind']=='prior'])
    files=selected+[{**e,'path':e['kind']+'/'+e['path']} for e in services+shared+old_neighbors]
    catalogs=proof_catalogs(proof,files)
    recover_members(slot,catalogs,[e['path'] for e in files],root/'inputs')
    from validate_gorge_shared import validate_shared
    validate_shared([{'path':'shared/'+e['path'],'source':str(root/'inputs/shared'/e['path']),'bytes':e['bytes'],'sha256':e['sha256']} for e in shared])
    # A fresh subledger imports only verified immutable blocks. Original ledgers
    # and historical reservations remain untouched in their private checkpoints.
    selection=dict(proof['cogSelection']);paths={e['path'].removeprefix('cog/') for e in selected}
    selection['entries']=[e for e in selection['entries'] if e['path'] in paths]
    selection['blocks']=[e for e in selection['blocks'] if f"blocks/{e['identity']}/{e['number']}" in paths]
    identities={b['identity'] for b in selection['blocks']}
    selection['sources']=[s for s in selection['sources'] if s['identity'] in identities]
    selection['selectedBytes']=sum(e['bytes'] for e in selection['entries'])
    if len(selection['blocks'])!=293 or selection['selectedBytes']!=19202048:raise ValueError('Selected ledger incomplete')
    seed_selected_cog(selection,root/'inputs/cog',root/'working-cog',region['sourceLimits']['cogBytes'])
    service=root/'working-service';service.mkdir(mode=0o700)
    for e in services:os.link(root/'inputs/service'/e['path'],service/e['path'])
    svc=ServiceCache(service,byte_limit=region['sourceLimits']['serviceBytes'],request_limit=region['sourceLimits']['serviceRequests']);svc.close()
    (root/'worker').mkdir(mode=0o700)
    private_write(root/'REGION-PLAN.json',canonical(region))
    ticket=root/'HANDOFF-CHECK.json';private_write(ticket,canonical({'plan':region,'approvedJobs':JOBS,'root':str(root)}))
    check=subprocess.run([sys.executable,str(SOURCE/'gorge_worker_handoff.py'),str(ticket)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,
        env={**os.environ,'GDAL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
    if check.returncode or json.loads(check.stdout)!={'jobs':12,'networkOperations':0,'workerHandoffValidated':True}:
        raise ValueError('Complete native handoff failed')
    # Only adjacent old outputs are recovered, and only for seam QA.
    neighbors=[{'ref':c['ref'],'members':[e for e in c['members'] if e['path'].startswith('prior/')]} for c in catalogs]
    neighbors=[c for c in neighbors if c['members']]
    for jobref in h['neighborJobReceipts']:
        r=record(slot,jobref,'rrgh-checkpoint-job-v1')
        wanted={e['path'] for e in neighboring_paths(region,r['result']['originalReceipt']['outputs'])}
        for c in r['result']['outputPacks']:
            members=[{**e,'path':'prior/'+e['path']} for e in c['members'] if e['path'] in wanted]
            if members:neighbors.append({'ref':c['ref'],'members':members})
    return {'inputProofValidated':True,'historicalProofRef':h['proof'],'acceptedBase':base,
        'sharedBytes':sum(e['bytes'] for e in shared),'sharedFiles':len(shared),
        'selectedCOGBytes':selection['selectedBytes'],'selectedCOGBlocks':293,'nativeHandoff':json.loads(check.stdout),
        'neighborCatalogs':neighbors,'priorJobsPreserved':32,'priorRasterTilesPreserved':320,'sunlightAssetsPreserved':320}

def produce(plan,evidence,region,root,store,opener,owner):
    slot=Slot(store,plan,0,owner);opener.deadline=slot.meter.deadline
    try:
        c=plan['continuation'];old=record(slot,c['closedPreflightReceipt'])
        if (old.get('planSHA256')!=c['previousPlanSHA256'] or old.get('slot')!=0
            or old.get('nonrefundableAllocation')!=c['retainedAllocation']
            or old['result'].get('status')!='failed' or old['used']['attempts']!=0):raise ValueError('Closed preflight authority differs')
        # Retain the WHOLE old preflight slot, including time and failure padding.
        # Create-only fences prove the old worker/recovery claims never existed.
        old_prefix=PREFIX+'plans/'+c['previousPlanSHA256']+'/'
        fences=[]
        for index in (1,2):
            fences.append(create_fence(slot,old_prefix+f'slots/{index:05d}/claim.json',{
                'format':'rrgh-unstarted-slot-fence-v1','oldPlanSHA256':c['previousPlanSHA256'],'slot':index,
                'successorPlanSHA256':digest(canonical(plan)),'owner':owner,'rasterAttempts':0}))
        fence=create_fence(slot,old_prefix+'successor.json',{'format':'rrgh-second-stage-continuation-v1',
            'ownerApproval':APPROVAL,'planSHA256':digest(canonical(plan)),'claim':asdict(slot.claim),
            'releasedUSD':'0.35','lockedUSD':'7.30','retainedAllocation':c['retainedAllocation'],
            'closedReceipt':c['closedPreflightReceipt'],'unstartedSlotFences':fences,'refundsApplied':False})
        initial=bootstrap(slot,plan,region,root);initial['releaseFence']=fence
        ref=slot.finish({**initial,'status':'ready','gcsBeforeReceipt':opener.summary()})
        print(json.dumps({'phase':'bootstrap','receiptRef':asdict(ref),'result':initial,'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    except Exception as error:
        if not slot.closed:
            ref=slot.finish({'status':'failed','failureClass':type(error).__name__,'gcsBeforeReceipt':opener.summary()})
            print(json.dumps({'phase':'bootstrap-failed','receiptRef':asdict(ref),'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
        raise
    run_jobs(plan,region,root,store,opener,owner)

def run_jobs(plan,region,root,store,opener,owner):
    output=root/'worker';service=root/'working-service';cog=root/'working-cog'
    known={'cog/'+p.relative_to(cog).as_posix() for p in cog.glob('blocks/*/*')}
    known|={'service/'+p.name for p in service.iterdir() if p.suffix in ('.bin','.json')}
    slot=Slot(store,plan,1,owner);opener.deadline=slot.meter.deadline
    completed=[];deltas=[];growth=0;state_bytes=0;output_bytes=0;attempts=0;source_bytes=0;source_requests=0;start=time.monotonic();failure=None
    try:
        for job in JOBS:
            policy=plan['jobPolicies'][job];attempts+=1;job_error=None;receipt=None
            try:
                receipt=run_job(slot,root/'REGION-PLAN.json',job,output,cog,service,policy,policy['seconds'],growth_cap=GROWTH_CAP-growth)
                if any(e['bytes']>TILE_CAP for e in receipt['outputs']):raise ValueError('Encoded output preservation cap')
                output_bytes+=sum(e['bytes'] for e in receipt['outputs'])
                if output_bytes>TOTAL_OUTPUT_CAP:raise ValueError('Cumulative output preservation cap')
            except Exception as error:job_error=error
            usage_path=output/('gate-c-'+job+'.usage.json')
            if usage_path.exists():
                usage=json.loads(usage_path.read_bytes());growth+=usage['reserved']['storedBytes']
                source_bytes+=usage['actual']['receivedBodyBytes'];source_requests+=usage['actual']['operations']
                if usage.get('diagnostic'):print(json.dumps({'childDiagnostic':usage['diagnostic'],'job':job}),flush=True)
            else:growth=GROWTH_CAP
            destination=root/('delta-'+job)
            entries,new,state_bytes=snapshot_cache(cog,service,destination,job,known,state_bytes)
            if sum(e['bytes'] for e in entries if not e['path'].startswith('state/'))>growth:raise ValueError('Cache escaped prepaid source guard')
            delta_refs=save_delta(slot,destination,entries);deltas.extend(delta_refs);known.update(new)
            if job_error:raise RuntimeError('Bounded child failed; source cache preserved') from None
            ref=checkpoint_job(slot,receipt,output);completed.append(asdict(ref))
            print(json.dumps({'completedJobs':len(completed),'sourceReceivedBytes':source_bytes,'sourceRequests':source_requests,
                'outputBytes':output_bytes,'cacheGrowthReservedBytes':growth,'durableJobReceipt':asdict(ref),
                'job':job,'jobTiles':len(receipt['outputs']),'jobOutputBytes':sum(e['bytes']for e in receipt['outputs']),
                'execution':receipt.get('execution')},sort_keys=True),flush=True)
    except Exception as error:
        import traceback
        failure={'errorClass':type(error).__name__,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]}
    result={'status':'complete' if failure is None else 'failed','diagnostic':failure,
        'completedJobReceipts':completed,'cacheCatalogs':deltas,'historicalProofRef':plan['history']['proof'],
        'attempts':attempts,'sourceBytesReceived':source_bytes,'sourceRequests':source_requests,
        'cacheGrowthReservedBytes':growth,'stateSnapshotBytes':state_bytes,'outputBytes':output_bytes,
        'wallSeconds':round(time.monotonic()-start,6),'gcsBeforeReceipt':opener.summary()}
    ref=slot.finish(result);signal('worker_receipt')
    print(json.dumps({'phase':'stage','receiptRef':asdict(ref),'result':result,'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    if failure:raise RuntimeError('Bounded stage stopped; all reservations retained')

def recover(plan,region,root,store,opener,owner):
    slot=Slot(store,plan,2,owner);opener.deadline=slot.meter.deadline
    result={'status':'failed'};failure=None
    try:
        initial_ref,initial=slot.recover_receipt(0);worker_ref,worker=slot.recover_receipt(1)
        initial=initial['result'];worker=worker['result']
        if initial.get('status')!='ready' or not initial['inputProofValidated'] or worker['historicalProofRef']!=plan['history']['proof']:
            raise ValueError('Input binding changed')
        records=[];outputs=[]
        for r in worker['completedJobReceipts']:
            obj=record(slot,r,'rrgh-checkpoint-job-v1')
            if obj['planSHA256']!=digest(canonical(plan)) or obj['slot']!=1:raise ValueError('New job identity mismatch')
            records.append(obj);outputs.extend(obj['result']['outputPacks'])
        paths=[e['path'] for c in outputs for e in c['members']]
        if paths:recover_catalogs(slot,outputs,paths,root/'output-recovery')
        neighbors=initial['neighborCatalogs'];neighbor_paths=[e['path'] for c in neighbors for e in c['members']]
        if neighbor_paths:recover_catalogs(slot,neighbors,neighbor_paths,root/'baseline-recovery')
        catalogs=[slot.get_catalog(Ref(**r)) for r in worker['cacheCatalogs']]
        cache_paths=[e['path'] for c in catalogs for e in c['members']]
        if cache_paths:recover_catalogs(slot,catalogs,cache_paths,root/'cache-recovery')
        from gorge_state_snapshot import recover as recover_state
        states=[recover_state(root/'cache-recovery'/p) for p in cache_paths if p.startswith('state/') and p.endswith('.sqlite.z1')]
        qa=verify_outputs(plan,region,records,root/'output-recovery',root/'baseline-recovery') if paths else {'jobs':0,'files':0,'bytes':0}
        if worker['status']=='complete' and (qa['jobs']!=12 or qa['files']!=116):raise ValueError('Incomplete approved tile set')
        # Exact cache/source lineage and full-resolution payloads are retained;
        # seam deltas are measurements, not an unsupported regional acceptance.
        qa.update(regionComplete=False,priorJobsPreserved=32,priorRasterTilesPreserved=320,sunlightAssetsPreserved=320)
        qa['edgeSummary']={layer:{'edges':len(edges),'maximumMeanAbsoluteChannelDifference':max(e['meanAbsoluteChannelDifference']for e in edges),
            'maximumP95':max(e['p95']for e in edges)} for layer in sorted({e['layer']for e in qa.get('seams',[])})
            if (edges:=[e for e in qa['seams']if e['layer']==layer])}
        qa['layerOutputBytes']={layer:sum(e['bytes']for r in records for e in r['result']['originalReceipt']['outputs']if e['path'].split('/')[1]==layer)
            for layer in sorted({j['layer']for j in region['jobs']})}
        qa_ref=slot.put(canonical(qa),'indexes')
        result={'status':'verified' if worker['status']=='complete' else 'partial-preservation-verified',
            'production':{k:v for k,v in qa.items() if k!='seams'},'qaRef':asdict(qa_ref),
            'bootstrapReceipt':asdict(initial_ref),'workerReceipt':asdict(worker_ref),
            'completedJobReceipts':worker['completedJobReceipts'],'allNewCachePacksRecovered':True,
            'newCacheFilesRecovered':len(cache_paths),'sqliteSnapshotsVerified':len(states),
            'adjacentPriorTilesRecovered':len(neighbor_paths),'historicalProofReused':plan['history']['proof']}
    except Exception as error:
        import traceback
        failure=type(error).__name__;result.update(failureClass=failure,
            frames=[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)])
    result['gcsBeforeReceipt']=opener.summary();ref=slot.finish(result)
    print(json.dumps({'phase':'fresh-recovery','result':result,'receiptRef':asdict(ref),'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    if failure:raise RuntimeError('Independent recovery failed closed')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--phase',choices=['plan','produce','recovery'],default='plan');args=parser.parse_args()
    try:
        plan,evidence,region=configuration()
        if args.phase=='plan':
            print(json.dumps({'planSHA256':digest(canonical(plan)),'jobs':12,'tiles':116,'releaseUSD':'.35','lockedUSD':'7.30','allocation':{k:sum(s[k] for s in plan['slots']) for k in DIMENSIONS},'bulkProductionEnabled':False}));return
        if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('Rerun prohibited')
        root=private_root();opener=CountedOpener();store=GCS(plan,evidence,token,opener);owner=os.environ['GITHUB_RUN_ID']
        if args.phase=='produce':produce(plan,evidence,region,root,store,opener,owner)
        else:recover(plan,region,root,store,opener,owner)
    except Exception as error:
        import traceback
        print(json.dumps({'phase':args.phase,'status':'failed-closed','errorClass':type(error).__name__,'reservationRetained':True,
            'automaticRetryPermitted':False,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]}),flush=True)
        raise SystemExit(2) from None

if __name__=='__main__':main()
