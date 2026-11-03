"""Two finite subprocess children; one owner, reservation writer and checkpoint writer."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import math
from pathlib import Path
import shutil
import time
from types import SimpleNamespace

from rrgh_batch_contract import CLOSURE, admission, partition, policy_check, require, sha
from rrgh_pair_cache import seed, merge, usage


def execute(a,slot,plan,job,root,region_path):
    policy=plan['jobPolicies'][job]
    caps=dict.fromkeys(a.DIMENSIONS,0);caps.update(policy,attempts=1)
    proxy=SimpleNamespace(plan=plan,index=1,meter=a.Meter(caps))
    proxy.meter.deadline=slot.meter.deadline
    started=time.monotonic()
    try:
        receipt=a.run_job(proxy,region_path,job,root/'worker',root/'working-cog',
                          root/'working-service',policy,policy['seconds'],
                          growth_cap=policy['sourceBytes']+policy['sourceRequests']*8192)
        elapsed=time.monotonic()-started
        reserved=receipt['execution']['sourceUsage']['reserved']
        charge={k:reserved[k] for k in ('sourceBytes','sourceRequests')}
        charge.update(attempts=1,seconds=math.ceil(elapsed))
        require(all(charge[k]<=policy[k] for k in policy),'Child exceeded reserved allowance')
        return dict(receipt=receipt,charge=charge,elapsed=elapsed,error=None,pixelGap=False)
    except Exception as error:
        path=root/'worker'/('gate-c-'+job+'.usage.json')
        child=json.loads(path.read_bytes()) if path.is_file() else None
        return dict(receipt=None,charge={**policy,'attempts':1},elapsed=time.monotonic()-started,
                    error={'errorClass':type(error).__name__},pixelGap=a.is_verified_original_pixel_gap(child),
                    usage=child)


def produce(plan,evidence,region,root,store,opener,owner,api):
    a=SimpleNamespace(**api);policy_check(plan['resumableBatch'])
    require(all(j['operation']=='source-window' and j['layer'] in ('hiking','terrain','leaf-off')
                for j in region['jobs']),'Pair scope must contain only original-COG windows')
    require(len(plan['approvedJobIDs'])<=plan['resumableBatch']['targetJobs'],'Finite pair scope exceeded')
    boot=a.Slot(store,plan,0,owner);opener.deadline=boot.meter.deadline
    try:
        initial=a.bootstrap(boot,plan,region,root);initialref=a.save_large(boot,initial)
        ref=boot.finish({'status':'ready','inputProofValidated':True,'bootstrapDataRef':initialref,'gcs':opener.summary()})
        a.signal('bootstrap_ready');a.emit(phase='bootstrap',receiptRef=asdict(ref),sharedBytesDownloaded=0,
            selectedCacheBytes=initial['selectedCOGBytes'],gcsIncludingReceipt=opener.summary())
    except Exception as error:
        if not boot.closed:boot.finish({'status':'failed','errorClass':type(error).__name__,'gcs':opener.summary()})
        raise
    slot=a.Slot(store,plan,1,owner);opener.deadline=slot.meter.deadline
    approved=plan['approvedJobIDs'];by_id={j['id']:j for j in region['jobs']}
    completed=[];attempts=[];gaps=[];outputs=0;sourcebytes=0;sourcerequests=0
    start=time.monotonic();childwall=0;stop=None;fallback=False;reuse=0;gap_streak=0
    # Pair barriers keep all GCS and SQLite merging on this one thread. Child
    # threads merely supervise separate processes and never touch the parent meter.
    for offset in range(0,len(approved),2):
        jobs=approved[offset:offset+2];policies=[plan['jobPolicies'][j] for j in jobs]
        from gorge_producer_identity import require_owner
        require_owner(plan,'produce')
        stop=admission(slot.meter.used,slot.meter.caps,policies,slot.meter.deadline-time.monotonic(),
                       outputs,sum(len(by_id[j]['outputTiles']) for j in jobs),usage(root),a.WORKING_CACHE_CAP)
        if shutil.disk_usage(root).free<2*2**30:stop='runner free-space reserve'
        if stop:break
        children=[]
        # Seed every isolated cache BEFORE writing an attempt reservation. Errors
        # here cannot be mistaken for official source attempts.
        try:
            for i,j in enumerate(jobs):
                child=root/f'pair-{offset:04d}-{i}'
                marks=seed(root,child)
                children.append((j,child,marks))
        except Exception:
            stop='isolated cache preparation failed';fallback=True;break
        reservations=[]
        try:
            for i,(j,child,marks) in enumerate(children):
                reservation={'format':'rrgh-pair-reservation-v1','planSHA256':sha(plan),
                    'job':j,'ordinal':len(attempts),'worker':i,'policy':plan['jobPolicies'][j],
                    'priorUsed':slot.meter.used.copy(),'pairJobIDs':jobs}
                ref=asdict(slot.put(a.canonical(reservation),'indexes'))
                entry={'job':j,'reservationRef':ref,'reservation':reservation,'outcome':'quarantined'}
                attempts.append(entry);reservations.append(entry)
        except Exception:
            # No child was submitted. A successfully created reservation remains
            # consumed conservatively; an unknown Cloud write is never repeated.
            for entry in reservations:slot.meter.reserve(**plan['jobPolicies'][entry['job']],attempts=1)
            stop='reservation creation failed before pair launch';fallback=True;break
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(execute,a,slot,plan,j,child,root/'REGION-PLAN.json') for j,child,_ in children]
            results=[future.result() for future in futures]
        # All submitted subprocesses exited (or were killed and joined by their
        # bounded subprocess.run timeout) before checkpointing or another launch.
        for (j,child,marks),entry,result in zip(children,reservations,results,strict=True):
            slot.meter.reserve(**result['charge']);childwall+=result['elapsed']
            entry['retained']=result['charge'];entry['pixelGap']=result['pixelGap']
            if result['receipt'] is not None:
                receipt=result['receipt'];receipt['campaignReservation']={
                    'ref':entry['reservationRef'],'allocation':entry['reservation'],
                    'retained':result['charge'],
                    'confirmedUnused':{k:plan['jobPolicies'][j][k]-result['charge'][k] for k in plan['jobPolicies'][j]}}
                try:
                    require(all(e['bytes']<=a.TILE_CAP for e in receipt['outputs']),'Full-quality tile bound')
                    ref=a.checkpoint_job(slot,receipt,child/'worker');completed.append(asdict(ref))
                    entry['outcome']='accepted';entry['jobReceipt']=asdict(ref)
                    outputs+=sum(e['bytes'] for e in receipt['outputs'])
                    sourcebytes+=receipt['execution']['sourceUsage']['actual']['receivedBodyBytes']
                    sourcerequests+=receipt['execution']['sourceUsage']['actual']['operations']
                    gap_streak=0
                    a.emit(job=j,completedJobs=len(completed),jobTiles=len(receipt['outputs']),outputBytes=outputs,
                           sourceBytes=sourcebytes,sourceRequests=sourcerequests,durableJobReceipt=asdict(ref))
                except Exception:
                    # Unknown output publication stays quarantined. Retain the
                    # entire child reservation, including unused source capacity.
                    extra={k:plan['jobPolicies'][j][k]-result['charge'][k] for k in plan['jobPolicies'][j]}
                    slot.meter.reserve(**extra);entry['retained']={**plan['jobPolicies'][j],'attempts':1}
                    stop='output checkpoint failed';fallback=True
            else:
                if result['usage'] is not None:entry['usageRef']=a.save_large(slot,result['usage'])
                if result['pixelGap']:
                    gaps.append(j);gap_streak+=1
                    a.emit(job=j,status='source-pixel-gap-quarantined',attemptConsumed=True,sourceQualityUnchanged=True)
                    if gap_streak>=2:stop='consecutive source pixel gaps';fallback=True
                else:stop='bounded child failed';fallback=True
            # Both children are idle. Merge every source pin and transfer entry,
            # including failed reservations; do not discard failed source ledgers.
            reuse+=merge(root,child,marks)
        # Removing these *temporary* hardlinks does not delete canonical inputs,
        # Cloud objects, outputs in immutable checkpoints or any ledger rows.
        for _,child,_ in children:shutil.rmtree(child)
        if stop:break
    attempted=[e['job'] for e in attempts];accepted=[e['job'] for e in attempts if e['outcome']=='accepted']
    closure=dict(format=CLOSURE,planSHA256=sha(plan),allocationSHA256=sha(approved),
        attemptedJobIDs=attempted,acceptedJobIDs=accepted,
        quarantinedJobIDs=[j for j in attempted if j not in accepted],unattemptedJobIDs=approved[len(attempted):],
        allChildrenJoined=True,sourceLedgersMerged=True,stopReason=stop,fallbackRequired=fallback,
        workers=2,producerSeconds=round(time.monotonic()-start,6),childWallSeconds=round(childwall,6),
        immutableCacheBytesAvailableForReuse=reuse)
    partition(approved,closure,sha(plan))
    state_ref=a.save_large(slot,a.state_snapshot(root))
    details={'completedJobReceipts':completed,'stateRef':state_ref,'sourceBytesReceived':sourcebytes,
        'sourceRequests':sourcerequests,'outputBytes':outputs,'seconds':closure['producerSeconds'],
        'failure':None,'stoppedBeforeNextAttempt':stop,'sourcePixelGapJobs':gaps,'pixelGapAttemptsConsumed':len(gaps),
        'rawCachePolicy':plan['cachePolicy'],'batchClosure':closure,'batchAttempts':attempts,'gcs':opener.summary()}
    detail_ref=a.save_large(slot,details);status='bounded-stop' if stop or gaps else 'complete'
    ref=slot.finish({'status':status,'detailRef':detail_ref,'jobs':len(completed),'outputBytes':outputs,
                     'stateRef':state_ref,'gcs':opener.summary()})
    a.signal('worker_receipt');a.emit(phase='production',status=status,receiptRef=asdict(ref),jobs=len(completed),
        outputBytes=outputs,sourceBytes=sourcebytes,sourceRequests=sourcerequests,diagnostic=None,stopped=stop,
        sourcePixelGapJobs=gaps,batchClosure=closure,gcsIncludingReceipt=opener.summary())


def verify_closure(slot,plan,detail,records,worker,api):
    """Runs only on the independent runner, after normal output/pixel/package QA."""
    if not plan.get('resumableBatch'):
        require('batchClosure' not in detail,'Unallocated batch closure')
        return None
    a=SimpleNamespace(**api);policy_check(plan['resumableBatch'])
    closure=detail.get('batchClosure');attempted,accepted,quarantined,tail=partition(plan['approvedJobIDs'],closure,sha(plan))
    require(worker['result']['status'] in ('complete','bounded-stop'),'Unclosed producer')
    require([r['job'] for r in records]==accepted,'Recovered receipts differ from closed accepted set')
    require([e['job'] for e in detail['batchAttempts']]==attempted and worker['used']['attempts']==len(attempted),
            'Missing or additional source attempt')
    sums=dict.fromkeys(('sourceBytes','sourceRequests','seconds','attempts'),0)
    by_id={r['job']:r for r in records};gaps=[]
    for ordinal,entry in enumerate(detail['batchAttempts']):
        j=entry['job'];ref=a.Ref(**entry['reservationRef']);reservation=json.loads(slot.get(ref))
        require(ref.key.startswith(a.PREFIX+'plans/'+sha(plan)+'/slots/00001/indexes/') and
                reservation==entry['reservation'] and reservation['format']=='rrgh-pair-reservation-v1' and
                reservation['planSHA256']==sha(plan) and reservation['ordinal']==ordinal and
                reservation['worker']==ordinal%2 and reservation['job']==j and
                reservation['policy']==plan['jobPolicies'][j], 'Reservation lineage mismatch')
        retained=entry.get('retained',{**plan['jobPolicies'][j],'attempts':1})
        require(set(retained)==set(sums) and all(type(v) is int and v>=0 for v in retained.values()) and
                retained['attempts']==1,'Invalid retained child allowance')
        if j in accepted:
            receipt=by_id[j]['result']['originalReceipt'];bound=receipt['campaignReservation']
            require(entry['outcome']=='accepted' and bound['ref']==entry['reservationRef'] and
                    bound['allocation']==reservation and bound['retained']==retained,
                    'Output receipt lost its source reservation')
            expected=receipt['execution']['sourceUsage']['reserved']
            require(all(retained[k]==expected[k] for k in ('sourceBytes','sourceRequests')) and
                    all(retained[k]<=plan['jobPolicies'][j][k] for k in plan['jobPolicies'][j]),'Output source charges differ')
        else:
            require(entry['outcome']=='quarantined' and retained=={**plan['jobPolicies'][j],'attempts':1},
                    'Unaccepted attempt received a refund')
        if entry.get('pixelGap'):
            child=a.load_large(slot,entry['usageRef'])
            require(j in quarantined and a.is_verified_original_pixel_gap(child),'Unverified source gap')
            gaps.append(j)
        for k in sums:sums[k]+=retained[k]
    require(all(worker['used'][k]==v for k,v in sums.items()),'Parent usage does not conserve child reservations')
    require(gaps==detail['sourcePixelGapJobs'] and len(gaps)==detail['pixelGapAttemptsConsumed'],
            'Source gap partition differs')
    require(len(accepted)==worker['result']['jobs'] and closure['workers']==2 and
            closure['producerSeconds']==detail['seconds'],'Closed batch summary mismatch')
    return closure
