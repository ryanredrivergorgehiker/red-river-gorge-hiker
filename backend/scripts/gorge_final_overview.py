#!/usr/bin/env python3
"""Owner-approved thirteenth attempt for ONE preserved-child overview only.

No seed, Base read, official-source request, deployment, list, delete or retry.
Closed history and failed reservations remain; only 40 unused recovery B ops
are reassigned by a new create-only successor. A separate runner verifies it.
"""
import argparse
import base64
from dataclasses import asdict
from decimal import Decimal
import json
import os
from pathlib import Path
import time
import zlib

from gorge_checkpoint import (GCS, Slot, Ref, canonical, digest, decode_record,
    recover_members, DIMENSIONS, require_live_allowance, PREFIX)
from gorge_guarded_worker import run_job, checkpoint_job
from gorge_stage_coordinator import CountedOpener, private_root, signal, verify_outputs
from gorge_stage_reconcile import create_fence
from run_gorge_checkpoint_slot import preflight, token

SOURCE = Path(__file__).resolve().parent
CONFIG = SOURCE.parent/'config/gorge-final-overview-20261029'
JOB = 'terrain-15-8772-12661'
PREVIOUS = '9ba15a2a53ac9d9a49144a6865ae2f67c8cd68656cc54b2b22267e9b862c6eb7'
APPROVAL = 'Owner 2026-10-29: FINAL 13TH ATTEMPT; terrain-15-8772-12661 only'
LIMITS = dict(storedBytes=2**30, egressBytes=2**30, classARequests=200,
    classBRequests=500, sourceBytes=2**31, sourceRequests=2000, seconds=10800, attempts=13)
INCREMENT = dict(storedBytes=2**20, egressBytes=2*2**20, classARequests=8,
    classBRequests=40, sourceBytes=0, sourceRequests=0, seconds=360, attempts=1)


def configuration(directory=CONFIG):
    directory=Path(directory)
    plan=json.loads((directory/'PLAN.json').read_bytes())
    evidence=json.loads((directory/'ALLOWANCE.json').read_bytes())
    decoder=zlib.decompressobj()
    raw=decoder.decompress(base64.b64decode((directory/'REGION-PLAN.json.z.b64').read_bytes()),4*2**20)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Region configuration bound')
    region=json.loads(raw)
    preflight(plan,region,SOURCE);require_live_allowance(plan,evidence)
    old=json.loads((SOURCE.parent/'config/gorge-indexed-stage-20261029/PLAN.json').read_bytes())
    if digest(canonical(old))!=PREVIOUS:raise ValueError('Historical plan changed')
    carried={k:old['reconciliation']['carriedUsage'][k]+sum(s[k] for s in old['slots']) for k in DIMENSIONS}
    carried['classBRequests']-=40
    totals={k:sum(s[k] for s in plan['slots']) for k in DIMENSIONS}
    if (plan.get('purpose')!='owner-final-overview-exception' or plan.get('maxConcurrency')!=1
        or plan.get('limits')!=LIMITS or plan.get('ownerApproval')!=APPROVAL
        or plan.get('previousPlanSHA256')!=PREVIOUS or plan.get('carriedReservations')!=carried
        or totals!=INCREMENT or plan.get('slotJobs')!={'0':[JOB]}
        or plan.get('priorAttemptCounts')!={JOB:1} or plan.get('approvedJobIDs')!=[JOB]
        or plan.get('completedJobIDs')!=old['completedJobIDs']+old['approvedJobIDs'][:-1]
        or old['approvedJobIDs'][-1]!=JOB):
        raise ValueError('Exact final-attempt authority required')
    if any(carried[k]+totals[k]>LIMITS[k] for k in DIMENSIONS):
        raise ValueError('Cumulative original ceiling exceeded')
    if (plan['slots'][0]['classARequests']!=5 or plan['slots'][1]['classARequests']!=3
        or plan['slots'][0]['classBRequests']!=30 or plan['slots'][1]['classBRequests']!=10
        or any(s['seconds']!=180 for s in plan['slots'])):
        raise ValueError('Production and independent recovery must both be prepaid')
    target=next(j for j in region['jobs'] if j['id']==JOB)
    if target['operation']!='overview' or target['sourceIDs'] or target['outputTiles']!=[[15,8772,12661]]:
        raise ValueError('Only the unchanged overview recipe is allowed')
    if plan['children']['totalBytes']!=89547 or len(plan['children']['members'])!=4:
        raise ValueError('Four preserved children required')
    release=evidence.get('finalAttemptRelease',{})
    if (release.get('approvalReference')!=APPROVAL or release.get('planSHA256')!=digest(canonical(plan))
        or release.get('releasedUSD')!='.35' or release.get('lockedUSD')!='7.65'
        or release.get('incrementalReservationUSD')!='.002'
        or evidence['cloudStorageAllowance']['approvedUSD']!='.35'):
        raise ValueError('No plan-bound owner exception and existing release')
    # This subreservation is inside the stage release, never new campaign funds.
    rates=evidence['planningRates'];gib=Decimal(2**30)
    incremental=(Decimal(INCREMENT['storedBytes'])/gib*Decimal(rates['storageUSDPerGiBMonth'])+
        Decimal(INCREMENT['egressBytes'])/gib*Decimal(rates['egressUSDPerGiB'])+
        Decimal(8)/1000*Decimal(rates['classAUSDPer1000'])+
        Decimal(40)/1000*Decimal(rates['classBUSDPer1000']))*Decimal('1.2')
    if incremental>Decimal('.002'):raise ValueError('Incremental reservation insufficient')
    return plan,evidence,region


def prior_record(slot,ref,plan,index):
    record=decode_record(slot.get(Ref(**ref)))
    if (record.get('format')!='rrgh-slot-receipt-v1' or record.get('planSHA256')!=PREVIOUS
        or record.get('slot')!=index or record.get('nonrefundableAllocation')!=plan['slots'][index]):
        raise ValueError('Prior closed allocation changed')
    claim=Ref(**record['claim']);obj=json.loads(slot.get(claim))
    if (claim.key!=PREFIX+'plans/'+PREVIOUS+f'/slots/{index:05d}/claim.json'
        or obj.get('planSHA256')!=PREVIOUS or obj.get('slot')!=index
        or obj.get('allocation')!=plan['slots'][index] or obj.get('owner')!='40990810532'):
        raise ValueError('Prior claim changed')
    if set(record['used'])!=set(DIMENSIONS) or any(type(record['used'][k])is not int or not 0<=record['used'][k]<=plan['slots'][index][k] for k in DIMENSIONS):
        raise ValueError('Prior metered ceiling violation')
    return record


def verify_history(slot,plan,old,old_region):
    binding=plan['history']
    records=[prior_record(slot,binding[name],old,i) for i,name in enumerate(('bootstrap','worker','recovery'))]
    initial,worker,recovery=[r['result'] for r in records]
    if (initial.get('inputProofValidated') is not True or initial['proofRef']!=worker['proofRef']
        or worker.get('status')!='failed' or worker.get('attempts')!=12
        or worker.get('completedJobReceipts')!=binding['jobs']
        or worker.get('sourceBytesReceived')!=168514089 or worker.get('sourceRequests')!=115
        or worker['gcs']['statuses'].count(412)!=1):
        raise ValueError('Historical production result differs')
    if (recovery.get('status')!='partial-preservation-verified'
        or recovery.get('qaRef')!=binding['qa'] or not recovery.get('allNewCachePacksRecovered')
        or recovery.get('sqliteSnapshotsVerified')!=22 or recovery.get('newCacheFilesRecovered')!=2514):
        raise ValueError('Independent prior preservation absent')
    summary=recovery['gcs'];reserved=records[2]['used']['classBRequests']
    if (any(s not in (200,206) for s in summary['statuses'])
        or summary['classBHTTPRequests']!=62 or reserved!=62
        or old['slots'][2]['classBRequests']-reserved<40):
        raise ValueError('Unused closed read-operation capacity not proven')
    qa=json.loads(slot.get(Ref(**binding['qa'])))
    if (qa.get('jobs')!=11 or qa.get('files')!=107 or qa.get('bytes')!=3122969
        or not all(qa.get(k) for k in ('allExpectedTilesPresent','pixelsDecoded','gridAndAlphaVerified'))):
        raise ValueError('Prior full output recovery missing')
    recipe=digest((json.dumps(old_region,sort_keys=True,indent=2)+'\n').encode())
    jobs={j['id']:j for j in old_region['jobs']};count=0;bytes_=0
    for ref,job in zip(binding['jobs'],old['approvedJobIDs'][:-1],strict=True):
        rec=decode_record(slot.get(Ref(**ref)))
        r=rec['result']['originalReceipt']
        if (rec.get('format')!='rrgh-checkpoint-job-v1' or rec.get('job')!=job
            or rec.get('planSHA256')!=PREVIOUS or rec.get('slot')!=1
            or r.get('job')!=job or r.get('validated') is not True or r.get('recipeSHA256')!=recipe):
            raise ValueError('Prior job receipt authority differs')
        members=[e for p in rec['result']['outputPacks'] for e in p['members']]
        if [{k:e[k] for k in ('path','bytes','sha256')} for e in members]!=r['outputs']:
            raise ValueError('Prior output checkpoint differs')
        coordinates={(int(e['path'].split('/')[2]),int(e['path'].split('/')[3]),int(Path(e['path']).stem)) for e in members}
        if coordinates!={tuple(t) for t in jobs[job]['outputTiles']}:
            raise ValueError('Prior output tile set differs')
        count+=len(members);bytes_+=sum(e['bytes'] for e in members)
    if count!=107 or bytes_!=3122969:raise ValueError('Prior durable job totals differ')
    if plan['children']['catalogRef'] not in initial['seedCatalogs']:
        raise ValueError('Dependency catalog was not accepted in genuine preflight')
    catalog=slot.get_catalog(Ref(**plan['children']['catalogRef']))
    if catalog['ref']!=plan['children']['ref']:raise ValueError('Dependency generation changed')
    selected=[e for e in catalog['members'] if e['path'] in {x['path'] for x in plan['children']['members']}]
    if selected!=plan['children']['members']:raise ValueError('Dependency offsets/hashes changed')
    return {'format':'rrgh-final-overview-settlement-v1','ownerApproval':APPROVAL,
        'previousPlanSHA256':PREVIOUS,'history':binding,'historicalClaims':[r['claim'] for r in records],
        'historicalAllocations':[r['nonrefundableAllocation'] for r in records],
        'historicalUsedReservations':[r['used'] for r in records],
        'reassignedClosedClassBRequests':40,'closedRecoveryClassBUsed':62,
        'carriedReservations':plan['carriedReservations'],'allOtherReservationsRetained':True,
        'priorJobsIndependentlyRecovered':11,'priorTilesIndependentlyRecovered':107,
        'cacheCatalogsPreserved':worker['cacheCatalogs'],'priorOutputBytes':3122969}


def children(slot,plan,destination):
    info=plan['children'];manifest=[{'ref':info['ref'],'members':info['members']}]
    recover_members(slot,manifest,[e['path'] for e in info['members']],destination)
    from PIL import Image
    for e in info['members']:
        with Image.open(Path(destination)/e['path']) as im:
            im.load()
            if im.size!=(256,256) or im.mode!='RGB':raise ValueError('Preserved terrain child grid/mode differs')
    return manifest


def produce(plan,region,old,old_region,root,store,opener,owner):
    slot=Slot(store,plan,0,owner);opener.deadline=slot.meter.deadline
    result={'status':'failed','attempts':0};failure=None
    try:
        settlement=verify_history(slot,plan,old,old_region)
        fence=create_fence(slot,PREFIX+'plans/'+PREVIOUS+'/successor.json',{
            'format':'rrgh-final-overview-successor-v1','approval':APPROVAL,
            'predecessorPlanSHA256':PREVIOUS,'successorPlanSHA256':digest(canonical(plan)),
            'successorClaim':asdict(slot.claim),'reassignedClosedClassBRequests':40})
        children(slot,plan,root/'dependencies')
        output=root/'worker';output.mkdir()
        # Link verified preserved bytes into the fresh worker; no old job executes.
        for e in plan['children']['members']:
            target=output/e['path'].removeprefix('prior/');target.parent.mkdir(parents=True,exist_ok=True)
            os.link(root/'dependencies'/e['path'],target)
        region_file=root/'REGION-PLAN.json';region_file.write_bytes(canonical(region))
        result.update(settlement=settlement,successorRef=fence)
        receipt=run_job(slot,region_file,JOB,output,root/'unused-cog',root/'unused-service',
            {'sourceBytes':0,'sourceRequests':0},30,growth_cap=0)
        result['attempts']=1
        if (len(receipt['outputs'])!=1 or receipt['outputs'][0]['bytes']>512*1024
            or receipt['execution']['sourceUsage']['actual']['operations']!=0
            or receipt['execution']['sourceUsage']['actual']['receivedBodyBytes']!=0):
            raise ValueError('Unexpected output/source usage')
        ref=checkpoint_job(slot,receipt,output)
        result.update(status='complete',jobReceipt=asdict(ref),
            output=receipt['outputs'][0],sourceBytes=0,sourceRequests=0,
            completedJobReceipts=plan['history']['jobs']+[asdict(ref)],
            completedJobs=12,tiles=108,cachePayloadModified=False)
    except Exception as error:
        failure=type(error).__name__;result['failureClass']=failure
        result['attempts']=slot.meter.used['attempts']
        import traceback
        result['diagnosticFrames']=[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]
    result['gcsBeforeReceipt']=opener.summary()
    final=slot.finish(result)
    print(json.dumps({'phase':'final-overview','receiptRef':asdict(final),'result':result,
        'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    if failure:raise RuntimeError('Final attempt stopped; reservations retained')
    signal('final_overview_complete')
    return final,result


def recover(plan,region,root,store,opener,owner):
    slot=Slot(store,plan,1,owner);opener.deadline=slot.meter.deadline
    result={'status':'failed'};failure=None
    try:
        worker_ref,worker=slot.recover_receipt(0);w=worker['result']
        if (w.get('status')!='complete' or w.get('attempts')!=1 or w.get('completedJobs')!=12
            or w.get('completedJobReceipts')!=plan['history']['jobs']+[w['jobReceipt']]):
            raise ValueError('Complete final worker receipt required')
        record=decode_record(slot.get(Ref(**w['jobReceipt'])))
        if (record.get('format')!='rrgh-checkpoint-job-v1' or record.get('planSHA256')!=digest(canonical(plan))
            or record.get('job')!=JOB or record.get('slot')!=0):raise ValueError('Final job checkpoint identity')
        packs=record['result']['outputPacks'];paths=[e['path'] for p in packs for e in p['members']]
        recover_members(slot,packs,paths,root/'output-recovery')
        prior=decode_record(slot.get(Ref(**plan['history']['recovery'])))['result']
        qa=json.loads(slot.get(Ref(**plan['history']['qa'])))
        if (prior.get('qaRef')!=plan['history']['qa'] or qa.get('files')!=107 or qa.get('jobs')!=11
            or w['settlement'].get('history')!=plan['history']):raise ValueError('Prior recovery lineage changed')
        final_qa=verify_outputs(plan,region,[record],root/'output-recovery')
        children(slot,plan,root/'child-recovery')
        # Independent pixel alignment against the four exact preserved quadrants.
        # This is in-memory QA only; it does not write or rerender a production tile.
        from PIL import Image
        import numpy as np
        mosaic=np.zeros((512,512,3),dtype=np.uint8)
        for e in plan['children']['members']:
            parts=Path(e['path']).parts;x=int(parts[-2]);y=int(Path(e['path']).stem)
            with Image.open(root/'child-recovery'/e['path']) as im:
                mosaic[(y-25322)*256:(y-25321)*256,(x-17544)*256:(x-17543)*256]=np.asarray(im)
        expected=np.asarray(Image.fromarray(mosaic).resize((256,256),Image.Resampling.LANCZOS)).astype(float)
        with Image.open(root/'output-recovery'/paths[0]) as im:actual=np.asarray(im.convert('RGB')).astype(float)
        error=np.abs(actual-expected);mae=float(error.mean());p99=float(np.percentile(error,99))
        if mae>4 or p99>15:raise ValueError('Overview alignment/quality tolerance exceeded')
        result={'status':'all-twelve-jobs-verified','jobs':12,'tiles':108,
            'bytes':qa['bytes']+final_qa['bytes'],'priorRecoveryReused':plan['history']['recovery'],
            'workerReceipt':asdict(worker_ref),'finalJobReceipt':w['jobReceipt'],
            'completedJobReceipts':w['completedJobReceipts'],'finalTile':w['output'],
            'finalTileQA':final_qa,'childBytesVerified':89547,'childrenGenerationPinned':True,
            'meanAbsoluteChannelError':round(mae,6),'p99AbsoluteChannelError':p99,
            'sourceBytes':0,'sourceRequests':0,'allPreviousCachesAndJobsPreserved':True,
            'attemptsCumulative':13,'regionComplete':False}
        qa_ref=slot.put(canonical(result),'indexes');result['qaRef']=asdict(qa_ref)
    except Exception as error:
        failure=type(error).__name__;result['failureClass']=failure
        import traceback
        result['diagnosticFrames']=[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]
    result['gcsBeforeReceipt']=opener.summary();receipt=slot.finish(result)
    print(json.dumps({'phase':'final-independent-recovery','result':result,'receiptRef':asdict(receipt),
        'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    if failure:raise RuntimeError('Independent recovery failed closed')
    return receipt,result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['plan','produce','recovery'],default='plan');args=p.parse_args()
    try:
        plan,evidence,region=configuration()
        if args.phase=='plan':
            print(json.dumps({'planSHA256':digest(canonical(plan)),'job':JOB,'cumulativeAttemptCeiling':13,
                'newAllocation':INCREMENT,'carriedReservations':plan['carriedReservations'],
                'releasedUSD':'.35','lockedUSD':'7.65','bulkProductionEnabled':False}));return
        if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise ValueError('No automatic reruns')
        root=private_root();opener=CountedOpener();store=GCS(plan,evidence,token,opener)
        if args.phase=='produce':
            olddir=SOURCE.parent/'config/gorge-indexed-stage-20261029'
            old=json.loads((olddir/'PLAN.json').read_bytes())
            old_region=json.loads(zlib.decompress(base64.b64decode((olddir/'REGION-PLAN.json.z.b64').read_bytes())))
            produce(plan,region,old,old_region,root,store,opener,os.environ['GITHUB_RUN_ID'])
        else:recover(plan,region,root,store,opener,os.environ['GITHUB_RUN_ID'])
    except Exception as error:
        print(json.dumps({'phase':args.phase,'status':'failed-closed','errorClass':type(error).__name__,
            'reservationRetained':True,'automaticRetryPermitted':False}),flush=True)
        raise SystemExit(2) from None


if __name__=='__main__':main()
