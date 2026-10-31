#!/usr/bin/env python3
"""Finite source-local production wave under immutable USD25 cumulative authority.

Reuses the accepted renderer, private inputs and keyless identity. Future public
source ranges are working cache, not mandatory durable output. Existing caches
are immutable; complete output checkpoints and source ledgers are preserved.
No deployment, deletion, IAM change, unbounded dispatcher or implicit retry.
"""
import argparse,base64,json,math,os,shutil,sqlite3,subprocess,sys,time,zlib
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from gorge_checkpoint import (GCS,Slot,Ref,Meter,DIMENSIONS,PREFIX,MAX_PACK,canonical,digest,
    decode_record,encode_record,require_live_allowance,recover_members,pack_delta)
from gorge_campaign_budget import CAMPAIGN,APPROVAL,admit,settle,add_usage
from gorge_stage_coordinator import CountedOpener,private_root,signal,verify_outputs
from gorge_stage_inputs import private_write,PROOF_CAP
from gorge_stage_preflight import BASE_KEY,BASE_SHA,BASE_BYTES
from gorge_stage_reconcile import create_fence
from gorge_guarded_worker import run_job,checkpoint_job
from gorge_second_stage import recover_catalogs,record,proof_catalogs,neighboring_paths
from gorge_cache_selection import select_cog_cache,seed_selected_cog
from run_gorge_checkpoint_slot import code_snapshot,token

SOURCE=Path(__file__).resolve().parent
CONFIG=SOURCE.parent/'config/gorge-campaign-wave-012-20261031'
WAVE011_SALVAGE={'key':'engineering/map-production/plans/ad02daf172b88db0e6de4c0e1099b33f238ad88b2fe5df89aa597b633ae7c335/slots/00001/receipt.json','generation':'1793405625604649','bytes':1048,'sha256':'1509488d4bc7d448fcbf5af20aa267ce61c2dfb0baf6c7c16c3d7c1e84195b1b'}
WAVE011_PRODUCER={'key':'engineering/map-production/plans/03edea40b63ad8d937064e10f7b221445a55da1fa87f7689657a70efab3d96eb/slots/00001/receipt.json','generation':'1793401709392186','bytes':728,'sha256':'eaf01977e64789af249b51e12046a6007613ace8523271716fc8921455d0920c'}
WAVE011_AMBIGUOUS='leaf-on-16-17535-25316'
OUTPUT_CAP=512*2**20
TILE_CAP=512*1024
WORKING_CACHE_CAP=6*2**30
STATE_RAW_CAP=64*2**20
STATE_ENCODED_CAP=16*2**20

def configuration(directory=CONFIG):
    directory=Path(directory)
    plan=json.loads((directory/'PLAN.json').read_bytes());evidence=json.loads((directory/'ALLOWANCE.json').read_bytes())
    decoder=zlib.decompressobj();raw=decoder.decompress(base64.b64decode((directory/'REGION-PLAN.json.z.b64').read_bytes()),8*2**20)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('Bounded region required')
    region=json.loads(raw);admit(plan,evidence);require_live_allowance(plan,evidence)
    if plan['sourceSnapshotSHA256']!=code_snapshot(SOURCE) or digest(canonical(region))!=plan['regionPlanSHA256']:
        raise ValueError('Exact source/region pin changed')
    from build_gorge_map_bundles import PROFILE
    if region['profiles']!=PROFILE or region['format']!='rrgh-region-plan-v1':raise ValueError('Full quality profile changed')
    for name,sha in region['engineHashes'].items():
        if Path(name).name!=name or digest((SOURCE/name).read_bytes())!=sha:raise ValueError('Engine pin changed')
    jobs=plan['approvedJobIDs']
    if [j['id'] for j in region['jobs']]!=jobs or plan['slotJobs']!={'1':jobs} or len(set(jobs))!=len(jobs):
        raise ValueError('Exact finite job assignment required')
    if any(j in plan['completedJobIDs'] for j in jobs):raise ValueError('Completed job cannot run again')
    if len(plan['completedJobIDs'])!=plan['campaign']['carry']['priorCompletedJobs']:
        raise ValueError('Accepted inventory mismatch')
    if plan['cachePolicy']!='preserve-existing-working-public-ranges-source-pinned-v1':raise ValueError('Cache policy changed')
    if len(plan['slots'])!=3 or plan['slots'][1]['storedBytes']<OUTPUT_CAP+64*2**20 or plan['slots'][2]['egressBytes']<2*OUTPUT_CAP+128*2**20:
        raise ValueError('Full output/recovery/assembly must be prepaid')
    if set(plan['jobPolicies'])!=set(jobs):raise ValueError('Missing bounded job policy')
    return plan,evidence,region

def emit(**value):print(json.dumps(value,sort_keys=True),flush=True)

def state_snapshot(root):
    """Bounded, lossless snapshots of NEW working ledgers; no original mutation."""
    records={}
    for kind,file in [('cog','cache.sqlite'),('service','requests.sqlite')]:
        p=root/('working-'+kind)/file;out=root/(kind+'-state.sqlite')
        with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as src:
            if src.execute('PRAGMA integrity_check(10)').fetchall()!=[('ok',)]:raise ValueError('Source ledger corruption')
            with sqlite3.connect(out) as dst:src.backup(dst)
        raw=out.read_bytes()
        if len(raw)>STATE_RAW_CAP:raise ValueError('Ledger expansion bound')
        records[kind]={'bytes':len(raw),'sha256':digest(raw),'zlib':base64.b64encode(zlib.compress(raw,9)).decode()}
    return records

def check_states(records,root):
    for kind,r in records.items():
        if kind not in ('cog','service') or not 0<r['bytes']<=STATE_RAW_CAP:raise ValueError('State bound')
        dec=zlib.decompressobj();raw=dec.decompress(base64.b64decode(r['zlib']),r['bytes']+1)
        if not dec.eof or dec.unused_data or dec.unconsumed_tail or len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:
            raise ValueError('State hash/length mismatch')
        p=root/(kind+'.sqlite');private_write(p,raw)
        with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
            if db.execute('PRAGMA integrity_check(10)').fetchall()!=[('ok',)]:raise ValueError('Recovered ledger integrity')
    return {'ledgers':len(records),'hashesAndSQLiteVerified':True,'rawRangesAreTransientForNewWorkingCache':True}

def load_large(slot,ref,limit=STATE_ENCODED_CAP):
    ref=Ref(**ref)
    if ref.bytes>limit:raise ValueError('Bounded metadata object required')
    return decode_record(slot.get(ref),128*2**20)

def save_large(slot,obj,limit=STATE_ENCODED_CAP):
    return asdict(slot.put(encode_record(obj,limit,True,128*2**20),'indexes'))

def merge_recovered(source,destination):
    """Merge independently verified deltas without replacing any prior bytes."""
    for p in Path(source).rglob('*'):
        if not p.is_file():continue
        target=Path(destination)/p.relative_to(source)
        if target.exists():
            if target.is_symlink() or target.read_bytes()!=p.read_bytes():raise ValueError('Recovered delta collision')
        else:
            target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)

def bootstrap(slot,plan,region,root):
    c=plan['campaign'];h=plan['history']
    # Same sequence can be claimed only once across all source/config revisions.
    if c['sequence']:
        if c.get('failedBootstrap'):
            from decimal import Decimal
            from gorge_campaign_budget import cost
            prior=c['failedBootstrap']
            priorplan=json.loads((CONFIG.parent/'gorge-campaign-wave-000-20261030/PLAN.json').read_bytes())
            if (digest(canonical(priorplan))!=prior['planSHA256'] or priorplan['limits']!=prior['fullWaveAllocation']
                or priorplan['campaign']['carry']!=prior['carry'] or priorplan['campaign']['sequence']+1!=c['sequence']
                or prior['receiptKey']!=PREFIX+'plans/'+prior['planSHA256']+'/slots/00000/receipt.json'):
                raise ValueError('Failed allocation lineage mismatch')
            slot.meter.reserve(classBRequests=1,egressBytes=65537)
            oldref,raw=slot.store.receipt(prior['receiptKey'],lambda size:slot.meter.reserve(classBRequests=1,egressBytes=size+1))
            closed=decode_record(raw)
            if (closed['planSHA256']!=prior['planSHA256'] or closed['slot']!=0 or closed['result'].get('status')!='failed'
                or closed['nonrefundableAllocation']!=priorplan['slots'][0]
                or closed['used']['attempts'] or closed['used']['sourceBytes']):raise ValueError('Unconfirmed failed bootstrap')
            expected={**prior['carry'],'chargedUSD':str(Decimal(prior['carry']['chargedUSD'])+cost(prior['fullWaveAllocation'])),
                'storedBytes':prior['carry']['storedBytes']+prior['fullWaveAllocation']['storedBytes']}
            if c['carry']!=expected or c['previousRecovery']!={'failedBootstrapReceiptKey':prior['receiptKey']}:
                raise ValueError('Failed wave entire allocation must remain charged')
            previous=None
            emit(phase='previous-failure-retained',receiptRef=asdict(oldref),retainedFullAllocation=prior['fullWaveAllocation'],
                actualRecordedUsage=closed['used'],gcsBeforePriorReceipt=closed['result'].get('gcs'))
        else:
            previous=record(slot,c['previousRecovery'])['result']
            if c['sequence']==12:
                if c['previousRecovery']!=WAVE011_SALVAGE or c.get('ambiguousExcludedJobs')!=[WAVE011_AMBIGUOUS]:
                    raise ValueError('Exact Wave011 salvage source and unresolved attempt required')
                if (previous.get('status')!='verified' or previous.get('recoveryOnly') is not True
                    or previous.get('sourceWave')!=11 or previous.get('sourceProducer')!=WAVE011_PRODUCER
                    or previous.get('newlyAcceptedJobs')!=64 or previous.get('newlyAcceptedTiles')!=64
                    or previous.get('cumulativeAcceptedJobs')!=1210 or previous.get('cumulativeAcceptedTiles')!=11426
                    or previous.get('oldWaveProductionNotRepeated') is not True
                    or previous.get('ambiguousFirstLeafOnNotAccepted') is not True
                    or previous.get('packageChunksIndependentReadback') is not True
                    or previous.get('hashesPixelsEdgesSourceLedgersVerified') is not True):
                    raise ValueError('Wave011 salvage completion not fully verified')
                expected={'chargedUSD':'5.666507366374617815017700196','storedBytes':12804302742,
                          'priorCompletedJobs':1210,'priorRasterTiles':11426,'priorSunlightAssets':320}
                if c['carry']!=expected:raise ValueError('Failed-wave and salvage allocation must stay charged')
                historical_worker=record(slot,WAVE011_PRODUCER)['result']
                if historical_worker.get('status')!='failed' or historical_worker.get('jobs')!=64:
                    raise ValueError('Original failed checkpoint identity changed')
            else:
                if previous.get('status') not in ('verified','partial-verified') or previous['settlement']['sequence']!=c['sequence']-1:
                    raise ValueError('Previous recovery must close successfully')
                if previous['status']=='partial-verified' and not previous['settlement']['ambiguousAllocationRetained']:
                    raise ValueError('Partial recovery must retain full ambiguous allocation')
                if previous['nextCarry']!=c['carry']:raise ValueError('Cumulative ledger cannot reset or silently fork')
    fence=create_fence(slot,PREFIX+'campaigns/'+CAMPAIGN+f"/wave-{c['sequence']:05d}.json",{
        'format':'rrgh-campaign-wave-claim-v1','campaign':CAMPAIGN,'ownerApproval':APPROVAL,
        'planSHA256':digest(canonical(plan)),'slotClaim':asdict(slot.claim),'previousRecovery':c.get('previousRecovery'),
        'carry':c['carry'],'allocation':plan['limits'],'ceilingUSD':'25.00'})
    initial=record(slot,h['acceptedBootstrap']);accepted=record(slot,h['secondRecovery'])
    oldworker=record(slot,h['secondWorker'])
    if (initial['result'].get('inputProofValidated') is not True or
        initial['result']['vectorValidation']['vectorLayers']!=13 or initial['result']['vectorValidation']['vectorFeatures']!=19789 or
        accepted['result'].get('status')!='verified' or accepted['result']['production']['jobs']!=12 or accepted['result']['production']['files']!=116 or
        accepted['result']['workerReceipt']!=h['secondWorker'] or oldworker['result']['status']!='complete'):
        raise ValueError('Accepted private input/second-stage lineage changed')
    proof=record(slot,h['proof'],'rrgh-stage-input-proof-v1')
    b=proof['acceptedBase']
    if (initial['result']['proofRef']!=h['proof'] or b!=initial['result']['acceptedBase'] or b['key']!=BASE_KEY or b['sha256']!=BASE_SHA
        or b['bytes']!=BASE_BYTES or b['generation']!='1791470288796565'):
        raise ValueError('Accepted Base identity mismatch')
    shared=[e for e in proof['files'] if e['kind']=='shared']
    if len(shared)!=340 or sum(e['bytes'] for e in shared)!=73865407:raise ValueError('Shared inventory differs')
    # Accepted shared bytes stay in prior immutable checkpoints; raster workers
    # need their proof, not another full 73.9MB shared-input download.
    selected_paths={e['path'].removeprefix('cog-cache/') for cat in h['originalCacheRanges'] for e in cat['members']}
    selected=[e for e in proof['files'] if e['kind']=='cog' and e['path'] in selected_paths]
    if len(selected)!=293:raise ValueError('Original selected cache inventory differs')
    original_files=[{**e,'path':'cog/'+e['path']} for e in selected]
    service_files=[{**e,'path':'service/'+e['path']} for e in proof['files'] if e['kind']=='service' and e['path'] in h['serviceMetadataPaths']]
    if len(service_files)!=2:raise ValueError('NAIP service metadata missing')
    original_files+=service_files
    recover_catalogs(slot,proof_catalogs(proof,original_files),[e['path'] for e in original_files],root/'seed')
    cats=[slot.get_catalog(Ref(**ref)) for ref in oldworker['result']['cacheCatalogs']]
    paths=[e['path'] for cat in cats for e in cat['members'] if e['path'].startswith(('cog/','service/'))]
    last_job=plan['history']['secondStageLastJob']
    last_state=f'state/{last_job}/cog.sqlite.z1'
    if sum(e['path']==last_state for cat in cats for e in cat['members'])!=1:raise ValueError('Latest source ledger snapshot missing')
    recover_catalogs(slot,cats,paths+[last_state],root/'second-seed')
    merge_recovered(root/'second-seed',root/'seed')
    from gorge_state_snapshot import decode
    private_write(root/'seed/cog/cache.sqlite',decode((root/'seed'/last_state).read_bytes()))
    with sqlite3.connect('file:'+str(root/'seed/cog/cache.sqlite')+'?mode=ro',uri=True) as db:
        keys=db.execute('SELECT identity,number FROM blocks').fetchall()
    selection=select_cog_cache(root/'seed/cog',keys)
    seed_selected_cog(selection,root/'seed/cog',root/'working-cog',region['sourceLimits']['cogBytes'])
    if c['sequence'] and previous is not None:
        # Carry exact pins forward even when newly obtained public raw ranges
        # were intentionally transient. Refetch can never silently adopt a
        # newer source version after a completed wave.
        prior_detail=load_large(slot,previous['detailRef'])
        prior_states=load_large(slot,prior_detail['stateRef'])
        pins=root/'prior-state';pins.mkdir();check_states(prior_states,pins)
        with sqlite3.connect('file:'+str(pins/'cog.sqlite')+'?mode=ro',uri=True) as src, sqlite3.connect(root/'working-cog/cache.sqlite') as dst:
            for url,identity,metadata in src.execute('SELECT url,identity,metadata FROM sources'):
                old=dst.execute('SELECT identity FROM sources WHERE url=?',(url,)).fetchone()
                if old and old[0]!=identity:raise ValueError('Prior source identity conflict')
                dst.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?)',(url,identity,metadata))
            dst.commit()
    service=root/'working-service';service.mkdir(mode=0o700)
    for p in (root/'seed/service').iterdir():
        if p.suffix in ('.json','.bin'):os.link(p,service/p.name)
    from benchmark_ky_naip_usgs import ServiceCache
    svc=ServiceCache(service,byte_limit=region['sourceLimits']['serviceBytes'],request_limit=region['sourceLimits']['serviceRequests']);svc.close()
    (root/'worker').mkdir(mode=0o700)
    private_write(root/'REGION-PLAN.json',canonical(region))
    # New sources are pinned by the established source HEAD/If-Match path before
    # their first pixel read. Accepted cached identities never silently refresh.
    ticket=root/'HANDOFF.json';private_write(ticket,canonical({'root':str(root),'region':region,'plan':plan}))
    r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--handoff',str(ticket)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    if r.returncode or json.loads(r.stdout).get('networkOperations')!=0:raise ValueError('Integrated worker handoff failed')
    # Only real old neighboring tiles are read for independent edge comparison.
    neighbors=[]
    for ref in oldworker['result']['completedJobReceipts']:
        old=record(slot,ref,'rrgh-checkpoint-job-v1')
        wanted={e['path'] for e in neighboring_paths(region,old['result']['originalReceipt']['outputs'])}
        for cat in old['result']['outputPacks']:
            es=[{**e,'path':'prior/'+e['path']} for e in cat['members'] if e['path'] in wanted]
            if es:neighbors.append({'ref':cat['ref'],'members':es})
    old_files=[e for e in proof['files'] if e['kind']=='prior']
    es=[{**e,'path':'prior/'+e['path']} for e in neighboring_paths(region,old_files)]
    neighbors+=proof_catalogs(proof,es)
    return {'inputProofValidated':True,'proofRef':h['proof'],'acceptedBase':b,'sharedBytesReusedWithoutTransfer':73865407,
        'selectedCOGBytes':selection['selectedBytes'],'selectedCOGBlocks':len(keys),'neighbors':neighbors,
        'campaignFence':fence,'workingCachePolicy':plan['cachePolicy'],'workerHandoff':json.loads(r.stdout)}

def handoff(ticket):
    import socket
    def block(*args,**kwargs):raise RuntimeError('No network during integrated handoff')
    socket.socket.connect=block;socket.create_connection=block
    p=json.loads(Path(ticket).read_bytes());root=Path(p['root']);region=p['region'];plan=p['plan']
    import orchestrate_gorge_region as engine
    from cached_cog_source import Cache,official_url
    from benchmark_ky_naip_usgs import ServiceCache,NAIP
    from build_gorge_map_bundles import PROFILE
    if region['profiles']!=PROFILE:raise ValueError('Recipe profile mismatch')
    sources={s['id']:s for values in region['inventory']['sources'].values() for s in values}
    for j in region['jobs']:
        if j['id'] in plan['completedJobIDs'] or not j['outputTiles']:raise ValueError('Invalid job')
        for sid in j['sourceIDs']:
            if j['layer']!='leaf-on':official_url(sources[sid]['url'])
        if j['operation']=='overview':raise ValueError('First sustained wave must use explicit source windows')
    cache=Cache(root/'working-cog',limit=region['sourceLimits']['cogBytes'],maximum_limit=1_000_000_000_000);cache.close()
    service=ServiceCache(root/'working-service',byte_limit=region['sourceLimits']['serviceBytes'],request_limit=region['sourceLimits']['serviceRequests'])
    meta,_=service.fetch(NAIP,{'f':'pjson'});service.close()
    if not json.loads(meta):raise ValueError('NAIP metadata absent')
    emit(workerHandoffValidated=True,jobs=len(region['jobs']),networkOperations=0)


def producer_reservation_stop(used,caps,policy):
    """Return a safe bounded-stop reason before a child reservation is written.

    Failed source-pixel attempts retain their *full* seconds allocation. The
    source-byte and attempt guards alone must not allow a later Meter.reserve
    failure to convert resource exhaustion into an unrelated fatal error.
    """
    if any(used[k]+policy[k]>caps[k] for k in ('sourceBytes','sourceRequests')):
        return 'source allowance exhausted before next attempt'
    if used['attempts']+1>caps['attempts']:
        return 'attempt allowance exhausted before next job'
    if used['seconds']+policy['seconds']>caps['seconds']:
        return 'worker seconds allowance exhausted before next attempt'
    return None


def bounded_child(slot,plan,region_path,job,root):
    policy=plan['jobPolicies'][job]
    timeout=policy['seconds']
    reason=producer_reservation_stop(slot.meter.used,slot.meter.caps,policy)
    if reason:raise ValueError('Stop before new child reservation: '+reason)
    if timeout+180>slot.meter.deadline-time.monotonic():raise ValueError('Time reserved for checkpoint closure')
    allocation={'job':job,'policy':policy,'workingCacheCeiling':WORKING_CACHE_CAP,'priorUsed':slot.meter.used.copy()}
    reservation=slot.put(canonical({'format':'rrgh-campaign-child-reservation-v1',**allocation}),'indexes')
    childcaps=dict.fromkeys(DIMENSIONS,0);childcaps.update(policy,attempts=1)
    proxy=SimpleNamespace(plan=slot.plan,index=slot.index,meter=Meter(childcaps))
    # The 600-second child reservation sits inside the longer parent deadline.
    # run_job independently enforces its subprocess timeout and source caps.
    proxy.meter.deadline=slot.meter.deadline
    started=time.monotonic();success=False
    try:
        receipt=run_job(proxy,region_path,job,root/'worker',root/'working-cog',root/'working-service',policy,timeout)
        use=receipt['execution']['sourceUsage']['reserved']
        charged={'sourceBytes':use['sourceBytes'],'sourceRequests':use['sourceRequests'],'attempts':1,'seconds':math.ceil(time.monotonic()-started)}
        slot.meter.reserve(**charged);success=True
        receipt['campaignReservation']={'ref':asdict(reservation),'allocation':allocation,'retained':charged,
            'confirmedUnused':{k:policy[k]-charged[k] for k in ('sourceBytes','sourceRequests','seconds')}}
        return receipt
    finally:
        if not success:
            # Ambiguous child consumes its whole allowance. No refund, rerun or
            # later job is allowed after this path.
            slot.meter.reserve(sourceBytes=policy['sourceBytes'],sourceRequests=policy['sourceRequests'],attempts=1,seconds=timeout)

def is_verified_original_pixel_gap(child):
    """Only a fully typed native pixel-gap failure may be skipped.

    The attempt and entire reserved resource allowance were already consumed.
    This predicate must never accept arbitrary RuntimeError, a missing usage
    receipt, a child timeout, or a failed output integrity check.
    """
    if not isinstance(child,dict) or child.get('completed') is not False:
        return False
    reason=child.get('diagnostic')
    return (isinstance(reason,dict) and reason.get('errorClass')=='ValueError'
        and reason.get('failureCode')=='SOURCE_PIXEL_GAP'
        and isinstance(reason.get('frames'),list)
        and any(isinstance(f,dict)
                and f.get('file')=='benchmark_gorge_pipeline.py'
                and f.get('function')=='mosaic'
                for f in reason['frames']))


def produce(plan,evidence,region,root,store,opener,owner):
    boot=Slot(store,plan,0,owner);opener.deadline=boot.meter.deadline
    try:
        initial=bootstrap(boot,plan,region,root);initialref=save_large(boot,initial)
        ref=boot.finish({'status':'ready','inputProofValidated':True,'bootstrapDataRef':initialref,'gcs':opener.summary()})
        signal('bootstrap_ready');emit(phase='bootstrap',receiptRef=asdict(ref),sharedBytesDownloaded=0,selectedCacheBytes=initial['selectedCOGBytes'],gcsIncludingReceipt=opener.summary())
    except Exception as error:
        if not boot.closed:boot.finish({'status':'failed','errorClass':type(error).__name__,'gcs':opener.summary()})
        raise
    slot=Slot(store,plan,1,owner);opener.deadline=slot.meter.deadline
    completed=[];outputs=0;failure=None;stopped=None;start=time.monotonic();sourcebytes=0;sourcerequests=0
    sourcegaps=[]
    try:
        for job in plan['approvedJobIDs']:
            expected=next(j for j in region['jobs'] if j['id']==job)
            if outputs+len(expected['outputTiles'])*TILE_CAP>OUTPUT_CAP:
                stopped='output envelope reached before next attempt';break
            if shutil.disk_usage(root).free<2*2**30:
                stopped='runner capacity reserve reached';break
            with sqlite3.connect('file:'+str(root/'working-cog/cache.sqlite')+'?mode=ro',uri=True) as db:
                working=db.execute('SELECT COALESCE(SUM(bytes),0) FROM blocks').fetchone()[0]
            working+=sum(p.stat().st_size for p in (root/'working-service').glob('*.bin'))
            if working+plan['jobPolicies'][job]['sourceBytes']>WORKING_CACHE_CAP:
                stopped='working cache bound reached before next attempt';break
            policy=plan['jobPolicies'][job]
            stopped=producer_reservation_stop(slot.meter.used,slot.meter.caps,policy)
            if stopped:break
            if policy['seconds']+180>slot.meter.deadline-time.monotonic():
                stopped='worker deadline reserve reached before next attempt';break
            try:
                receipt=bounded_child(slot,plan,root/'REGION-PLAN.json',job,root)
            except RuntimeError:
                # Only a verified original-source pixel-gap ValueError may be
                # skipped. The child consumes its FULL reservation on failure;
                # every other failure is fatal. Do not rerender skipped jobs.
                usage=root/'worker'/('gate-c-'+job+'.usage.json')
                if usage.is_file():
                    child=json.loads(usage.read_bytes())
                    if is_verified_original_pixel_gap(child):
                        sourcegaps.append(job)
                        emit(job=job,status='source-pixel-gap-quarantined',
                             attemptConsumed=True,sourceQualityUnchanged=True)
                        continue
                raise
            if any(e['bytes']>TILE_CAP for e in receipt['outputs']):raise ValueError('Full quality output bound; never recompress')
            ref=checkpoint_job(slot,receipt,root/'worker');completed.append(asdict(ref))
            outputs+=sum(e['bytes'] for e in receipt['outputs'])
            sourcebytes+=receipt['execution']['sourceUsage']['actual']['receivedBodyBytes']
            sourcerequests+=receipt['execution']['sourceUsage']['actual']['operations']
            emit(job=job,completedJobs=len(completed),jobTiles=len(receipt['outputs']),outputBytes=outputs,sourceBytes=sourcebytes,sourceRequests=sourcerequests,durableJobReceipt=asdict(ref))
    except Exception as error:
        import traceback
        failure={'errorClass':type(error).__name__,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]}
        # The child already writes an immutable local usage/exception record on
        # a normal Python failure. Preserve its *structured non-secret* reason
        # for review before spending a second and final job attempt. Never
        # print raw child stdout, source URLs, exception messages or tokens.
        if 'job' in locals() and job in plan['approvedJobIDs']:
            failure['lastJobConsidered']=job
            child_usage=root/'worker'/('gate-c-'+job+'.usage.json')
            if child_usage.is_file():
                child=json.loads(child_usage.read_bytes())
                reason=child.get('diagnostic')
                if isinstance(reason,dict):
                    frames=reason.get('frames',[])
                    failure['child']={'errorClass':str(reason.get('errorClass',''))[:80],
                        'frames':[{'file':Path(t.get('file','')).name[:100],
                                   'line':int(t.get('line',0)),
                                   'function':str(t.get('function',''))[:100]}
                                  for t in frames[-8:] if isinstance(t,dict)]}
    # Future raw public ranges remain a bounded working cache. Save the complete
    # ledger, exact source pins and successful outputs, without multiplying raw
    # cache storage/recovery costs. Existing accepted raw packs remain untouched.
    states=state_snapshot(root);state_ref=save_large(slot,states)
    details={'completedJobReceipts':completed,'stateRef':state_ref,'sourceBytesReceived':sourcebytes,'sourceRequests':sourcerequests,
        'outputBytes':outputs,'seconds':round(time.monotonic()-start,3),'failure':failure,'stoppedBeforeNextAttempt':stopped,
        'sourcePixelGapJobs':sourcegaps,'pixelGapAttemptsConsumed':len(sourcegaps),
        'rawCachePolicy':plan['cachePolicy'],'gcs':opener.summary()}
    detail_ref=save_large(slot,details)
    status='failed' if failure else 'bounded-stop' if stopped or sourcegaps else 'complete'
    ref=slot.finish({'status':status,'detailRef':detail_ref,'jobs':len(completed),'outputBytes':outputs,'stateRef':state_ref,'gcs':opener.summary()})
    signal('worker_receipt');emit(phase='production',status=status,receiptRef=asdict(ref),jobs=len(completed),outputBytes=outputs,sourceBytes=sourcebytes,sourceRequests=sourcerequests,diagnostic=failure,stopped=stopped,sourcePixelGapJobs=sourcegaps,gcsIncludingReceipt=opener.summary())
    if failure:raise RuntimeError('Production stopped with preserved completed jobs')

def assemble(slot,records,root):
    from build_gorge_map_bundles import PROFILE,partition,write_part
    grouped={g:[] for g in PROFILE}
    for record in records:
        for e in record['result']['originalReceipt']['outputs']:
            fields=e['path'].split('/');layer=fields[1]
            group=next(g for g,ls in PROFILE.items() if layer in ls)
            grouped[group].append({**e,'source':str(root/'outputs'/e['path']),'layer':layer,'z':int(fields[2]),'x':int(fields[3]),'y':int(Path(fields[4]).stem)})
    result=[]
    for group,entries in grouped.items():
        if not entries:continue
        folder=root/'parts'/group;folder.mkdir(parents=True)
        for items in partition(group,entries):
            part=write_part(group,items,folder);p=folder/part['file'];chunks=[]
            with p.open('rb') as stream:
                offset=0
                while raw:=stream.read(MAX_PACK):
                    ref=slot.put(raw,'outputs');chunks.append({'offset':offset,'ref':asdict(ref)})
                    # Read back each generation-pinned stored chunk. Original
                    # raster recovery on this separate runner supplies assembly.
                    if slot.get(ref)!=raw:raise ValueError('Stored package chunk mismatch')
                    offset+=len(raw)
            result.append({'group':group,**part,'chunks':chunks,'regionalReady':False,'nativePartBoundsPass':part['byteCount']<=256000000 and part['fileCount']<=60000})
    return result

def recover(plan,region,root,store,opener,owner):
    slot=Slot(store,plan,2,owner);opener.deadline=slot.meter.deadline
    status='failed';error=None;result={};boot=None;worker=None
    try:
        bootref,boot=slot.recover_receipt(0)
        if boot['result'].get('status')!='ready':raise ValueError('Bootstrap not accepted')
        initial=load_large(slot,boot['result']['bootstrapDataRef'])
        workerref,worker=slot.recover_receipt(1)
        detail=load_large(slot,worker['result']['detailRef'])
        records=[record(slot,r,'rrgh-checkpoint-job-v1') for r in detail['completedJobReceipts']]
        if any(r['planSHA256']!=digest(canonical(plan)) or r['slot']!=1 for r in records):raise ValueError('Output lineage changed')
        catalogs=[c for r in records for c in r['result']['outputPacks']]
        paths=[e['path'] for c in catalogs for e in c['members']]
        if paths:recover_catalogs(slot,catalogs,paths,root/'outputs')
        neighbors=initial['neighbors'];oldpaths=[e['path'] for c in neighbors for e in c['members']]
        if oldpaths:recover_catalogs(slot,neighbors,oldpaths,root/'old')
        qa=verify_outputs(plan,region,records,root/'outputs',root/'old') if records else {'jobs':0,'files':0,'bytes':0,'seams':[]}
        (root/'state').mkdir();states=check_states(load_large(slot,detail['stateRef']),root/'state')
        parts=assemble(slot,records,root) if records else []
        qa['sourceLedgerVerification']=states;qa['parts']=parts;qa['regionComplete']=False
        qaref=save_large(slot,qa)
        completed=worker['result']['status'] in ('complete','bounded-stop')
        used=add_usage(boot['used'],worker['used'],slot.meter.used)
        ledger=settle(plan,used,completed)
        nextcarry={'chargedUSD':ledger['chargedUSD'],'storedBytes':ledger['storedBytes'],
            'priorCompletedJobs':plan['campaign']['carry']['priorCompletedJobs']+qa['jobs'],
            'priorRasterTiles':plan['campaign']['carry']['priorRasterTiles']+qa['files'],'priorSunlightAssets':320}
        status='verified' if completed else 'partial-verified'
        result={'status':status,'jobs':qa['jobs'],'tiles':qa['files'],'outputBytes':qa['bytes'],'qaRef':qaref,
            'packageParts':len(parts),'packageBytes':sum(p['byteCount'] for p in parts),'adjacentEdgesMeasured':len(qa['seams']),
            'workerReceipt':asdict(workerref),'bootstrapReceipt':asdict(bootref),'detailRef':worker['result']['detailRef'],
            'sourceBytesReceived':detail['sourceBytesReceived'],'sourceRequests':detail['sourceRequests'],
            'producerSeconds':detail['seconds'],'settlement':ledger,'nextCarry':nextcarry,
            'sourcePixelGapJobs':detail.get('sourcePixelGapJobs',[]),
            'pixelGapAttemptsConsumed':detail.get('pixelGapAttemptsConsumed',0),
            'allOutputHashesAndPixelsVerified':True,'allNewPackageChunksReadBack':True,'allExistingCachesPreserved':True}
    except Exception as exc:
        import traceback
        error={'errorClass':type(exc).__name__,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(exc.__traceback__)]}
        result.update(status='failed',diagnostic=error,allWaveAllocationsRetained=True)
    result['gcsBeforeReceipt']=opener.summary();ref=slot.finish(result)
    emit(phase='independent-recovery',receiptRef=asdict(ref),result=result,gcsIncludingReceipt=opener.summary())
    if error:raise RuntimeError('Independent recovery failed closed')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['plan','produce','recovery'],default='plan');ap.add_argument('--handoff');a=ap.parse_args()
    if a.handoff:handoff(a.handoff);return
    try:
        plan,evidence,region=configuration()
        if a.phase=='plan':emit(planSHA256=digest(canonical(plan)),jobs=len(region['jobs']),tiles=sum(len(j['outputTiles']) for j in region['jobs']),**admit(plan,evidence));return
        if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('Rerun prohibited')
        root=private_root();opener=CountedOpener();store=GCS(plan,evidence,token,opener);owner=os.environ['GITHUB_RUN_ID']
        if a.phase=='produce':produce(plan,evidence,region,root,store,opener,owner)
        else:recover(plan,region,root,store,opener,owner)
    except Exception as error:
        import traceback
        emit(phase=a.phase,status='failed-closed',errorClass=type(error).__name__,frames=[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)],automaticRetryPermitted=False)
        raise SystemExit(2) from None

if __name__=='__main__':main()
