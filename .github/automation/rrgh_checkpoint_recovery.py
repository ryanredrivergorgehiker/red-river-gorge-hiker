"""Bounded recovery of native checkpoints after credential refresh interruption.

Only the unused independent recovery slot is consumed. The original producer,
its entire resource allocation and every uncertain attempt remain retained.
"""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys

import rrgh_dispatcher as d
from rrgh_salvage_audit import one, reports

POLICY={'enabled':True,'authorizedBy':'ryanredrivergorgehiker','authorizedOn':'2026-11-05',
        'maxNativeJobs':12,'maxRecoveryAttempts':1}
KIND='bounded-native-checkpoint-recovery-v1'
PINS=('runID','dispatchID','sourceSHA','planSHA256','sequence')


def policy(state):
    d.guard(state.get('checkpointRecoveryPolicy')==POLICY,'Reviewed checkpoint recovery policy missing')


def reference(value,key):
    d.guard(isinstance(value,dict) and set(value)=={'key','generation','bytes','sha256'} and
        value.get('key')==key and str(value.get('generation','')).isdigit() and
        type(value.get('bytes')) is int and 0<value['bytes']<100000 and
        re.fullmatch('[0-9a-f]{64}',value.get('sha256','')) is not None,'Invalid checkpoint reference')
    return value


def plan_at(api,state):
    _,code=api.file('backend/scripts/gorge_campaign.py',ref=state['sourceSHA'])
    match=re.search(r"CONFIG=SOURCE.parent/'config/(gorge-campaign-wave-\d{3,9}-\d{8})'",code.decode())
    d.guard(match is not None,'Unknown immutable source configuration')
    _,raw=api.file('backend/config/'+match.group(1)+'/PLAN.json',ref=state['sourceSHA'])
    plan=json.loads(raw)
    d.guard(d.digest(d.canonical(plan))==state['planSHA256'] and
        plan['campaign']['sequence']==state['sequence'] and plan['campaign']['controllerEpoch']==state['epoch'],
        'Checkpoint source plan changed')
    return plan


def original(api,state,active=False):
    """Authenticate original run and complete immutable-log evidence, no writes."""
    original_state=state.get('checkpointRecoveryOf',state)
    rid=original_state['runID'];run=d.read_audit_run(api,rid)
    d.guard(run.get('id')==rid and run.get('run_attempt')==1 and run.get('head_branch')==d.WORKER and
        run.get('path')=='.github/workflows/'+d.WORKFLOW and run.get('event')=='workflow_dispatch' and
        run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('repository',{}).get('full_name')==d.REPO and
        run.get('display_title')==f"RRGH production {original_state['sequence']} {original_state['dispatchID']}" and
        ((active and run.get('status')=='in_progress' and run.get('conclusion') is None) or
         (not active and run.get('status')=='completed' and run.get('conclusion')=='failure')),
        'Original failed producer identity changed')
    _,original_raw=api.file(d.STATE,ref=run['head_sha']);allocation=json.loads(original_raw)
    d.guard(all(allocation.get(k)==original_state.get(k) for k in ('dispatchID','sourceSHA','planSHA256','sequence')) and
        allocation.get('status')=='dispatching' and allocation.get('mode')=='produce' and allocation.get('runID') is None,
        'Original execution did not bind this exact producer allocation')
    data=api.call('GET',f'actions/runs/{rid}/jobs?per_page=100');jobs=data.get('jobs',[])
    d.guard(data.get('total_count')==len(jobs)<=100,'Incomplete original job inventory')
    d.guard(one(jobs,'admit').get('conclusion')=='success' and
        one(jobs,'bounded-stage').get('conclusion')=='failure' and
        one(jobs,'independent-recovery').get('conclusion')=='skipped' and
        one(jobs,'advance').get('conclusion')=='skipped' and
        one(jobs,'retain-failure').get('conclusion')=='success',
        'Producer did not fail before independent recovery or original ownership is unresolved')
    from rrgh_dispatch_audit import gh
    log=gh('actions/jobs/'+str(one(jobs,'bounded-stage')['id'])+'/logs',api.token,raw=True)
    rows=reports(log.splitlines());checkpoints=[r for r in rows if 'durableJobReceipt' in r]
    stops=[r for r in rows if r.get('phase')=='produce' and r.get('status')=='failed-closed']
    d.guard(len(stops)==1 and stops[0].get('errorClass')=='RuntimeError' and
        any(f.get('file')=='rrgh_wif_credentials.py' and f.get('function')=='token' for f in stops[0].get('frames',[])) and
        not any(r.get('phase')=='production' or r.get('status')=='source-pixel-gap-quarantined' for r in rows),
        'Only a proven credential interruption with no producer closure is eligible')
    plan=plan_at(api,state);jobs=plan['approvedJobIDs'];ids=[r['job'] for r in checkpoints]
    native_scope=all(j.rsplit('-',3)[0] in ('hiking','terrain','leaf-off') for j in jobs)
    if plan.get('completionPhase') is not None:
        from rrgh_completion_phase import POLICY as COMPLETION_POLICY,PHASE,lower_usgs_index,BOUNDS
        index=lower_usgs_index(dict(boundsWGS84=BOUNDS,profiles={'core':{'usgs-topo':16}}))
        native_scope=(state.get('completionPolicy')==COMPLETION_POLICY and
            plan['completionPhase']==PHASE and set(jobs)<=set(index) and
            all(plan['jobPolicies'].get(j)==dict(seconds=600,sourceBytes=1048576,sourceRequests=1) for j in jobs))
    d.guard(plan.get('resumableBatch') is None and plan.get('overviewPilot') is None and
        plan['maxConcurrency']==1 and plan['automaticRetryPermitted'] is False and plan['deleteAllowed'] is False and
        plan['campaign']['ceilingUSD']=='125.00' and plan['campaign']['storageTargetUSDPerMonth']=='2.00' and
        0<len(ids)<=len(jobs)<=12 and len(set(jobs))==len(jobs) and ids==jobs[:len(ids)] and
        native_scope and
        all(plan['priorAttemptCounts'].get(j,0)==0 and j not in plan['completedJobIDs'] for j in jobs),
        'Only a fresh serial native checkpoint prefix is eligible')
    prefix='engineering/map-production/plans/'+state['planSHA256']+'/slots/'
    refs=[reference(r['durableJobReceipt'],prefix+'00001/jobs/'+r['job']+'.json') for r in checkpoints]
    d.guard([r.get('completedJobs') for r in checkpoints]==list(range(1,len(ids)+1)) and
        all(type(r.get('jobTiles')) is int and 0<r['jobTiles']<=21 for r in checkpoints),'Malformed durable job counts')
    boots=[r for r in rows if r.get('phase')=='bootstrap']
    d.guard(len(boots)==1,'One completed bootstrap required')
    boot=reference(boots[0]['receiptRef'],prefix+'00000/receipt.json')
    return dict(format=KIND,originalRunID=rid,originalDispatchID=original_state['dispatchID'],
        originalHeadSHA=run['head_sha'],sourceSHA=state['sourceSHA'],planSHA256=state['planSHA256'],
        sequence=state['sequence'],producerLogSHA256=d.digest(log.encode()),bootstrapReceipt=boot,
        completedJobIDs=ids,completedJobRefs=refs,uncertainJobIDs=jobs[len(ids):],
        jobs=len(ids),tiles=sum(r['jobTiles'] for r in checkpoints),
        priorCarry=plan['campaign']['carry'],originalAllocation=plan['limits']),plan


def arm(api,root,automatic=False):
    if not automatic:d.caller('launch')
    old,state=api.state();d.validate_state(state,root);policy(state)
    d.guard(state.get('enabled') is True and state.get('status')=='halted' and state.get('mode')=='produce' and
        not state.get('publicationOf') and not state.get('checkpointRecoveryOf'),
        'Checkpoint recovery cannot replace an active or consumed allocation')
    active=automatic and os.environ.get('GITHUB_JOB')=='resume-handoff'
    if active:d.guard(str(state['runID'])==os.environ.get('GITHUB_RUN_ID') and
        state['dispatchID']==os.environ.get('RRGH_DISPATCH_ID'),'In-run recovery belongs to another allocation')
    manifest,_=original(api,state,active=active)
    d.assert_no_other_producers(api,state['runID'] if active else None)
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    parent={k:state[k] for k in PINS};parent['mode']='produce'
    parent.update(epoch=state['epoch'],manifestSHA256=d.digest(d.canonical(manifest)))
    state.update(checkpointRecoveryOf=parent,status='checkpoint-recovery-ready')
    old=api.cas(old,state,'retain failed producer; reserve one source-free checkpoint recovery')
    return d.dispatch(api,root,old,state,'checkpoints',allowed_run=parent['runID'])


def inspect_manifest(manifest,plan,inspection):
    """Match every known receipt and prove slot2 unused before its first write."""
    d.guard(inspection.get('planSHA256')==manifest['planSHA256'] and
        inspection.get('sequence')==manifest['sequence'] and inspection.get('cloudWrites')==0 and
        inspection.get('sourceRequests')==0,'Checkpoint inspection identity changed')
    prefix='engineering/map-production/plans/'+manifest['planSHA256']+'/slots/'
    rows=inspection['objects'];objects={r['key']:r for r in rows}
    expected={prefix+f'{s:05d}/{n}.json' for s in range(3) for n in ('claim','receipt')}
    expected|={prefix+'00001/jobs/'+j+'.json' for j in plan['approvedJobIDs']}
    d.guard(len(objects)==len(rows) and set(objects)==expected,'Incomplete or duplicate checkpoint inspection')
    for key in [prefix+'00001/receipt.json',prefix+'00002/claim.json',prefix+'00002/receipt.json']:
        d.guard(objects[key].get('exists') is False,'Recovery slot consumed or producer closure appeared; no replay')
    claim=objects[prefix+'00001/claim.json'];record=claim.get('record',{})
    d.guard(claim.get('exists') is True and record.get('owner')==str(manifest['originalRunID']) and
        record.get('planSHA256')==manifest['planSHA256'] and record.get('slot')==1 and
        record.get('allocation')==plan['slots'][1],'Original producer claim changed')
    reference(claim['ref'],prefix+'00001/claim.json')
    boot=objects[prefix+'00000/receipt.json']
    d.guard(boot.get('exists') is True and boot.get('ref')==manifest['bootstrapReceipt'] and
        boot['record']['result'].get('status')=='ready','Original bootstrap changed')
    for jid,ref in zip(manifest['completedJobIDs'],manifest['completedJobRefs'],strict=True):
        row=objects[prefix+'00001/jobs/'+jid+'.json'];r=row.get('record',{})
        d.guard(row.get('exists') is True and row.get('ref')==ref and r.get('job')==jid and
            r.get('planSHA256')==manifest['planSHA256'] and r.get('slot')==1,'Saved checkpoint differs from original log')
    for jid in manifest['uncertainJobIDs']:
        d.guard(objects[prefix+'00001/jobs/'+jid+'.json'].get('exists') is False,
            'Unlogged receipt appeared; exact reconciliation required')
    result=copy.deepcopy(manifest);result['producerClaim']=claim['ref']
    result['inspectionUsage']={'classBRequests':inspection['readRequests'],
                               'egressBytes':inspection['readResponseBytes']+inspection['readRequests']}
    d.guard(0<result['inspectionUsage']['classBRequests']<=64 and
        result['inspectionUsage']['egressBytes']<=8*2**20+64,'Inspection exceeds reserved read envelope')
    return result


def run(source_root):
    api=d.GitHub(os.environ.get('GH_TOKEN',''));d.caller('worker')
    _,state=d.current_run(api,Path('.'),'running');policy(state)
    d.guard(state['mode']=='checkpoints' and state.get('checkpointRecoveryOf'),'Recovery claim missing')
    manifest,plan=original(api,state)
    d.guard(d.digest(d.canonical(manifest))==state['checkpointRecoveryOf']['manifestSHA256'],
        'Original recovery evidence changed after dispatch')
    # Trusted credential helper is loaded before source imports. Source files
    # remain pinned and unmodified; only this reviewed recovery runs Cloud work.
    import rrgh_wif_credentials
    from rrgh_checkpoint_diagnostics import inspect
    inspection=inspect(source_root)
    m=inspect_manifest(manifest,plan,inspection)
    print(json.dumps({'phase':'checkpoint-recovery-preflight','manifestSHA256':d.digest(d.canonical(manifest)),
        'originalProducerRunID':manifest['originalRunID'],'savedJobs':m['jobs'],'savedTiles':m['tiles'],
        'unusedRecoverySlotVerified':True,'cloudWrites':0},sort_keys=True),flush=True)
    from rrgh_checkpoint_salvage import run as recover
    recover(source_root,reviewed=m)


def audit(api,state,allow_failed_controller=False):
    policy(state);m,plan=original(api,state)
    d.guard(state.get('mode')=='checkpoints' and
        state.get('checkpointRecoveryOf',{}).get('manifestSHA256')==d.digest(d.canonical(m)),
        'Checkpoint recovery evidence differs from its durable claim')
    rid=state['runID'];run=d.read_audit_run(api,rid)
    d.guard(run.get('id')==rid and run.get('run_attempt')==1 and run.get('head_branch')==d.WORKER and
        run.get('path')=='.github/workflows/'+d.WORKFLOW and run.get('event')=='workflow_dispatch' and
        run.get('actor',{}).get('login')=='github-actions[bot]' and run.get('repository',{}).get('full_name')==d.REPO and
        run.get('display_title')==f"RRGH checkpoints {state['sequence']} {state['dispatchID']}" and
        run.get('status') in ('in_progress','completed') and
        (run.get('conclusion') in (None,'success') or (allow_failed_controller and run.get('conclusion')=='failure')),
        'Checkpoint recovery execution identity changed')
    data=api.call('GET',f'actions/runs/{rid}/jobs?per_page=100');jobs=data.get('jobs',[])
    d.guard(data.get('total_count')==len(jobs)<=100,'Incomplete recovery jobs')
    job=one(jobs,'independent-checkpoints')
    d.guard(job.get('status')=='completed' and job.get('conclusion')=='success' and
        one(jobs,'admit').get('conclusion')=='success' and
        all(one(jobs,n).get('conclusion')=='skipped' for n in
            ('bounded-stage','independent-recovery','independent-salvage','independent-completion')),
        'Recovery must not execute production or other consumed paths')
    from rrgh_dispatch_audit import gh
    rows=reports(gh('actions/jobs/'+str(job['id'])+'/logs',api.token,raw=True).splitlines())
    results=[r for r in rows if r.get('phase')=='independent-checkpoint-salvage']
    d.guard(len(results)==1,'Exactly one independent checkpoint report required')
    return validate_report(m,results[0],state)


def validate_report(m,report,state):
    r=report['result'];ledger=r['settlement'];carry=r['nextCarry'];ref=report['receiptRef']
    d.guard(r.get('status')=='partial-verified' and r.get('salvage')==KIND and
        r.get('originalProducerRunID')==m['originalRunID'] and r.get('workerReceipt') is None and
        all(r.get(k)==m[k] for k in ('bootstrapReceipt','completedJobRefs','completedJobIDs','uncertainJobIDs')) and
        r.get('jobs')==m['jobs'] and r.get('tiles')==r.get('verifiedTileCatalogTiles')==m['tiles'] and
        r.get('sourceJobsExecuted')==0 and r.get('adjacentEdgesMeasured',0)>0 and
        r.get('packageParts',0)>0 and r.get('packageBytes',0)>0,'Checkpoint result identity or verification changed')
    reference(r['producerClaim'],'engineering/map-production/plans/'+m['planSHA256']+'/slots/00001/claim.json')
    d.guard(all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified','allNewPackageChunksReadBack',
        'allExistingCachesPreserved','unacceptedAttemptsQuarantined')) and
        r.get('sourcePinsReconstructed',{}).get('allPriorPinsPreserved') is True,'Preservation or pixel/package QA missing')
    allocation=m['originalAllocation']
    d.guard(ledger['sequence']==m['sequence'] and ledger['planSHA256']==m['planSHA256'] and
        ledger['originalAllocation']==ledger['retainedUsage']==allocation and
        ledger['demonstrablyUnused']=={k:0 for k in allocation} and
        ledger['ambiguousAllocationRetained'] is True and ledger['independentRecoveryComplete'] is False,
        'Entire failed-wave reservation must stay charged')
    # Audit runs without the source checkout on sys.path. Keep the approved
    # four-rate reservation arithmetic independent of source/Cloud imports.
    d.guard(all(type(v) is int and v>=0 for v in allocation.values()),'Invalid reservation units')
    reserved=(Decimal(allocation['storedBytes'])/2**30*Decimal('.03')+
        Decimal(allocation['egressBytes'])/2**30*Decimal('.23')+
        Decimal(allocation['classARequests'])/1000*Decimal('.01')+
        Decimal(allocation['classBRequests'])/1000*Decimal('.001'))*Decimal('1.2')
    expected=dict(m['priorCarry'],chargedUSD=str(Decimal(m['priorCarry']['chargedUSD'])+reserved),
        storedBytes=m['priorCarry']['storedBytes']+allocation['storedBytes'],
        priorCompletedJobs=m['priorCarry']['priorCompletedJobs']+m['jobs'],
        priorRasterTiles=m['priorCarry']['priorRasterTiles']+m['tiles'])
    d.guard(carry==expected and ledger['chargedUSD']==carry['chargedUSD'] and ledger['storedBytes']==carry['storedBytes'] and
        Decimal(carry['chargedUSD'])<123 and Decimal(carry['storedBytes'])/2**30*Decimal('.036')<2,
        'Conservative recovery carry or budget changed')
    reference(ref,'engineering/map-production/plans/'+m['planSHA256']+'/slots/00002/receipt.json')
    proof={'manifest':m,'manifestSHA256':d.digest(d.canonical(m))}
    report=dict(verified=True,checkpointRecovery=proof,partialRecovered=False,
        partialCompletedJobIDs=[],sourceCompletedJobIDs=[],sourcePixelGapJobs=[],failedJobID=None,
        uncertainJobIDs=m['uncertainJobIDs'],wave=m['sequence'],run=m['originalRunID'],recoveryRunID=state['runID'],
        jobsNew=m['jobs'],tilesNew=m['tiles'],acceptedJobs=carry['priorCompletedJobs'],
        acceptedRasterTiles=carry['priorRasterTiles'],sunlightAssets=320,historicalExclusions=45,
        receiptRef=ref,receiptSHA256=ref['sha256'],receiptGeneration=ref['generation'],nextCarry=carry,
        planSHA256=m['planSHA256'],modeledCumulativeUSD=carry['chargedUSD'],
        modeledMonthlyStorageUSD=str(Decimal(carry['storedBytes'])/2**30*Decimal('.036')),
        dispatchAuthorized=False,sourcePolicyMode=state.get('sourcePolicyMode','expanded'),
        controllerDispatchID=state['dispatchID'],controllerParentRun=state.get('parentRunID'),
        overviewPilotEnabled=state.get('overviewPilotEnabled') is True,batchPilotEnabled=False)
    if state.get('completionPolicy') is not None:
        from rrgh_completion_phase import authorized
        authorized(state['completionPolicy']);report['completionPolicy']=state['completionPolicy']
    return report


def validate_planning(plan,audit):
    proof=audit['checkpointRecovery'];m=proof['manifest']
    d.guard(proof.get('manifestSHA256')==d.digest(d.canonical(m)) and m['format']==KIND and
        m['planSHA256']==d.digest(d.canonical(plan))==audit['planSHA256'] and
        m['sequence']==audit['wave']==plan['campaign']['sequence'] and m['originalRunID']==audit['run'] and
        m['priorCarry']==plan['campaign']['carry'] and m['originalAllocation']==plan['limits'] and
        m['completedJobIDs']+m['uncertainJobIDs']==plan['approvedJobIDs'] and
        m['jobs']==len(m['completedJobIDs'])==audit['jobsNew'] and
        0<m['jobs']<=len(plan['approvedJobIDs'])<=12 and plan.get('resumableBatch') is None and
        plan.get('overviewPilot') is None and audit['acceptedJobs']==len(plan['completedJobIDs'])+m['jobs'] and
        audit['acceptedRasterTiles']==plan['campaign']['carry']['priorRasterTiles']+m['tiles'],
        'Verified checkpoint planning evidence changed')
    return m


if __name__=='__main__':run(Path(sys.argv[1]))
