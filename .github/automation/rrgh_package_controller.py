"""Receipt-bound package succession without moving the accepted source branch."""
import copy
import json
import os
from pathlib import Path
import re
import sys

from rrgh_package_authority import digest,require
import rrgh_package_contract as contract
from rrgh_package_funding import settle


def reports(lines,phase):
    result=[]
    for line in lines:
        if '"phase": "'+phase+'"' not in line:continue
        try:row=json.loads(line[line.index('{'):])
        except (ValueError,TypeError):continue
        if row.get('phase')==phase:result.append(row)
    require(len(result)==1,'Exactly one package receipt report required')
    return result[0]


def audit_run(state,plan,run,jobs,stage_lines,verify_lines):
    from rrgh_dispatcher import REPO,WORKER,WORKFLOW
    from rrgh_verified_tile_catalog import ref
    require(run.get('repository',{}).get('full_name')==REPO and
        run.get('head_branch')==WORKER and run.get('event')=='workflow_dispatch' and
        run.get('path')=='.github/workflows/'+WORKFLOW and
        run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('run_attempt')==1 and run.get('id')==state['runID'] and
        run.get('display_title')==f"RRGH package {state['sequence']} {state['dispatchID']}" and
        run.get('status') in ('in_progress','completed'), 'Package execution ownership changed')
    for name in ('admit','package-stage','package-verify'):
        selected=[j for j in jobs if j['name']==name]
        require(len(selected)==1 and selected[0]['conclusion']=='success' and
                selected[0]['status']=='completed','Incomplete package worker verification')
    stage=reports(stage_lines,'final-package-stage');verified=reports(verify_lines,'final-package-verify')
    prefix='engineering/map-production/plans/'+digest(plan)+'/slots/'
    for report,index in ((stage,0),(verified,1)):
        ref(report['receiptRef'])
        require(report['receiptRef']['key']==prefix+f'{index:05d}/receipt.json' and
                report['receiptRef']['bytes']<=16384 and
                report['result']['packagePlanSHA256']==digest(plan) and
                report['result']['operation']==plan['finalPackagePhase']['operation'] and
                report['result']['sourceRequests']==report['result']['sourceBytes']==0,
                'Package receipt allocation or source-free scope changed')
    result=verified['result']
    require(stage['result']['status']=='staged' and result['status']=='verified' and
        result['workerReceipt']==stage['receiptRef'] and result['authoritySHA256']==state['package']['authoritySHA256'] and
        result['ordinal']==state['package']['ordinal'] and result['rasterTiles']==278278 and
        result['finalPackageDeliveryComplete'] is False and result['physicalIPhoneTestComplete'] is False,
        'Package verification receipt lineage changed')
    ref(result['checkpoint'])
    require(result['checkpoint']['key'].startswith(prefix+'00001/indexes/') and
        result['checkpoint']['bytes']<=2**20 and
        result['settlement']==settle(plan,result['settlement']['observedUsage'],True),
        'Package checkpoint or budget settlement changed')
    next_op=result['nextOperation']
    require(result['packageBytesIndependentlyVerified']==(next_op is None), 'False package completion flag')
    op=result['operation']
    if op['kind']=='inventory':
        require(next_op is not None and ((next_op['kind']=='inventory' and next_op['start']==op['stop']) or
                next_op['kind']=='layout'),'Package metadata queue skipped a prerequisite')
    elif op['kind']=='layout':require(next_op is not None and next_op['kind']=='parts','Layout did not lead to parts')
    elif op['kind'] in ('part','parts'):require(next_op is not None and next_op['kind'] in ('part','parts','indexes'),'Part skipped indexes')
    elif op['kind']=='indexes':
        require(next_op is None and result['verifiedIndexes']==3 and result['catalogCandidates'],
                'Final indexes incomplete')
        ref(result['catalogCandidates'])
    else:raise ValueError('Unreviewed package operation')
    return dict(result,receiptRef=verified['receiptRef'])


def source_context(source,state):
    import subprocess
    from rrgh_dispatcher import config
    source=Path(source).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    require(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==state['sourceSHA'],
            'Package source checkout differs from accepted anchor')
    _,plan,_=config(source)
    return plan,contract.authority(source,plan,state)



# This exception is deliberately scoped to the completed 1462 raster checkpoint.
# A source-only package merge changes CODE_FILES, but must not silently update
# the durable producer fingerprint or permit a new raster production claim.
PRE_PACKAGE_DIGEST = 'eac8c2859961fe6d084d6744a4c0bedd9becb585632550fc9ea543090fd82680'
ACCEPTED_RASTER_SOURCE = 'd17d0e335ac47e1f6d116e149992cc02d6e4a827'
ACCEPTED_PLAN = 'a161d6d494b0c737734de937a90c11fc1bb9aac6a0d93ab57bac7304ba75c891'
ACCEPTED_RECEIPT = 'b8a7228562a082e8ca36cdd4d3a83d5fcb9c093a02772168a915106686fbe945'


def authorize_completed_package_cutover(state, request, current_digest):
    """Pure, one-time owner/receipt-pinned code transition: never a general digest bypass."""
    from rrgh_package_authority import require
    progress = state.get('completionProgress') or {}
    last = state.get('lastRecovered') or {}
    receipt = state.get('checkpoint') or {}
    require(state.get('format') == 'rrgh-controller-state-v1' and state.get('owner') == 'autonomous-v1'
            and state.get('epoch') == 1 and state.get('enabled') is True
            and state.get('status') == 'completion-waiting' and state.get('mode') == 'produce'
            and state.get('sequence') == 1462 and state.get('runID') == 43027688867
            and state.get('sourceSHA') == ACCEPTED_RASTER_SOURCE
            and state.get('planSHA256') == ACCEPTED_PLAN
            and state.get('controlDigest') == PRE_PACKAGE_DIGEST
            and current_digest != PRE_PACKAGE_DIGEST and len(current_digest) == 64
            and 'package' not in state and not state.get('pendingControllerUpgrade')
            and not any(x.get('kind') == 'completed-raster-package-cutover'
                        for x in state.get('controllerUpgradeHistory', [])),
            'Not the immutable, unused completed-raster package code boundary')
    require(progress.get('format') == 'rrgh-raster-complete-package-wait-v1'
            and progress.get('fullRasterCoverageComplete') is True
            and progress.get('acceptedRasterTiles') == 278278
            and progress.get('remainingRasterTiles') == 0
            and progress.get('finalPackageDeliveryComplete') is False
            and progress.get('sequence') == 1462
            and progress.get('recoveryReceipt') == receipt
            and receipt.get('sha256') == ACCEPTED_RECEIPT
            and receipt.get('generation') == '1794403195257733'
            and last.get('recoveryReceipt') == receipt
            and last.get('runID') == 43027688867
            and last.get('acceptedRasterTiles') == 278278
            and last.get('acceptedJobs') == 34750,
            'Independent raster checkpoint or accepted inventory changed')
    require(request.get('action') == 'package-start'
            and request.get('authorizedBy') == 'ryanredrivergorgehiker'
            and request.get('date') == '2026-11-11'
            and request.get('source_sha') == ACCEPTED_RASTER_SOURCE
            and request.get('sourcePlanSHA256') == ACCEPTED_PLAN
            and request.get('rasterCompletionRun') == 43027688867
            and request.get('acceptedRasterPositions') == 278278
            and request.get('acceptedJobs') == 34750
            and request.get('packageIntegrationPR') == 116
            and request.get('packageIntegrationCommit')
                == 'e93eaa8a66db7ff5a0565c72d20aa9e5065b8d89'
            and request.get('restrictions') == dict(
                sourceRegeneration=False, acceptedOutputsImmutable=True,
                consumedAttemptsImmutable=True, originalCampaignCeilingUSD='125.00',
                finalDeliveryReserveUSD='0.75', authorizedCatalogActivation=False,
                physicalIPhoneAcceptance=False),
            'Exact owner package-start approval or no-replay boundary changed')
    authorization = request.get('controllerCodeTransition')
    expected = dict(format='rrgh-reviewed-package-code-transition-v1',
                    authorizedBy='ryanredrivergorgehiker', authorizedOn='2026-11-11',
                    fromDigest=PRE_PACKAGE_DIGEST, toDigest=current_digest,
                    acceptedReceiptSHA256=ACCEPTED_RECEIPT, acceptedRunID=43027688867,
                    preserveAcceptedHistory=True, sourceRequests=0,
                    catalogActivation=False, scope='completed-raster-to-source-free-packaging')
    require(authorization == expected,
            'Reviewed exact code fingerprint authorization absent or stale')
    return dict(kind='completed-raster-package-cutover',
                authorizedBy='ryanredrivergorgehiker', authorizedOn='2026-11-11',
                fromDigest=PRE_PACKAGE_DIGEST, toDigest=current_digest,
                acceptedRunID=43027688867, acceptedRasterTiles=278278,
                acceptedReceiptSHA256=ACCEPTED_RECEIPT,
                sourceSHA=ACCEPTED_RASTER_SOURCE, planSHA256=ACCEPTED_PLAN,
                sourceWrites=0, producerReplays=0, catalogActivation=False)


def enroll(api,root,source):
    from rrgh_dispatcher import validate_state,audit_state,assert_no_other_producers,dispatch,local_digest
    old,prior=api.state()
    request=json.loads((Path(root)/'.github/automation/rrgh-controller-request.json').read_bytes())
    transition=authorize_completed_package_cutover(prior,request,local_digest(root))
    state=copy.deepcopy(prior)
    state['controlDigest']=transition['toDigest']
    validate_state(state,root)  # The general validator still rejects every other change.
    assert_no_other_producers(api)
    source_plan,auth=source_context(source,prior)
    audit=audit_state(api,root,prior)
    require(audit['acceptedRasterTiles']==278278 and audit['acceptedJobs']==34750 and
        audit['receiptRef']==prior['checkpoint'] and audit['nextCarry']['priorRasterTiles']==278278,
        'Raster completion independent audit changed')
    cursor,_,_=contract.allocate(source_plan,state,auth,contract.inventory_operation(auth,0),
                                audit['nextCarry'],0,None)
    state.setdefault('controllerUpgradeHistory',[]).append(transition)
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    validate_state(state,root)
    # ONE atomic conditional write records the reviewed digest and new package claim.
    # If this fails, no durable code upgrade or package allocation is published.
    old=api.cas(old,state,'owner-reviewed package fingerprint and source-free enrollment')
    return dispatch(api,root,old,state,'package')


def finish(api,root,source,recovering=False):
    from rrgh_dispatcher import current_run,read_audit_run,dispatch
    from rrgh_dispatch_audit import gh
    old,state=current_run(api,root,'halted' if recovering else 'running')
    require(state['mode']=='package','Wrong package controller mode')
    source_plan,auth=source_context(source,state);plan,_=contract.funding(source_plan,state,auth)
    run=read_audit_run(api,state['runID']);response=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
    jobs=response['jobs'];require(response['total_count']==len(jobs)<=100,'Incomplete package job inventory')
    lines={}
    for name in ('package-stage','package-verify'):
        selected=[j for j in jobs if j['name']==name];require(len(selected)==1,'Ambiguous package worker')
        lines[name]=gh('actions/jobs/'+str(selected[0]['id'])+'/logs',api.token,raw=True).splitlines()
    result=audit_run(state,plan,run,jobs,lines['package-stage'],lines['package-verify'])
    previous=state['runID']
    summary={k:result[k] for k in ('ordinal','operation','receiptRef','checkpoint','inventorySlices',
        'verifiedParts','verifiedIndexes','packageBytesIndependentlyVerified','catalogCandidates')}
    summary.update(runID=previous,planSHA256=digest(plan))
    if result['nextOperation'] is None:
        state['package'].update(status='verified-awaiting-catalog',carry=result['settlement']['nextCarry'],
            lastVerified=summary,verifiedCheckpoint=result['checkpoint'])
        state.update(status='package-validation-waiting')
        api.cas(old,state,'all package bytes independently verified; catalog activation and phone test pending')
        return dict(status='PACKAGE_BYTES_VERIFIED',verifiedParts=result['verifiedParts'],verifiedIndexes=3,
            acceptedRasterTiles=278278,remainingRasterTiles=0,finalPackageDeliveryComplete=False,
            physicalIPhoneTestComplete=False,catalogCandidates=result['catalogCandidates'])
    cursor,_,_=contract.allocate(source_plan,state,auth,result['nextOperation'],result['settlement']['nextCarry'],
                                state['package']['ordinal']+1,result['checkpoint'])
    cursor['lastVerified']=summary
    if state['package'].get('retainedFailures'):cursor['retainedFailures']=state['package']['retainedFailures']
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'independently verified package operation; allocate exact successor')
    return dispatch(api,root,old,state,'package',allowed_run=previous)


def recovery_allocation(source_plan,state,auth,error):
    """A failed operation may use two new allocations; no old claim is replayed."""
    plan,_=contract.funding(source_plan,state,auth);p=state['package']
    require(error['phase']=='final-package-error' and error['packagePlanSHA256']==digest(plan) and
        error['workerPhase'] in ('stage','verify') and error['transientTransport'] is True and
        error['entireAllocationRetained'] is True and error['sourceRequests']==0 and
        p.get('retryCount',0)<2,'Package failure is not eligible for bounded transport recovery')
    retained=settle(plan,dict.fromkeys(plan['limits'],0),False)
    cursor,_,_=contract.allocate(source_plan,state,auth,p['operation'],retained['nextCarry'],
                                p['ordinal']+1,p['previousCheckpoint'])
    cursor['retryCount']=p.get('retryCount',0)+1
    cursor['retainedFailures']=copy.deepcopy(p.get('retainedFailures',[]))+[dict(
        runID=state['runID'],dispatchID=state['dispatchID'],ordinal=p['ordinal'],planSHA256=digest(plan),
        operation=copy.deepcopy(p['operation']),settlement=retained,errorClass=error['errorClass'])]
    require(len(cursor['retainedFailures'])<=24,'Cumulative package recovery ceiling reached')
    if p.get('lastVerified'):cursor['lastVerified']=copy.deepcopy(p['lastVerified'])
    return cursor


def recover(api,root,source):
    from rrgh_dispatcher import validate_state,dispatch,read_audit_run
    from rrgh_dispatch_audit import gh
    old,state=api.state();validate_state(state,root)
    run_id=int(os.environ['GITHUB_RUN_ID'])
    if state.get('package',{}).get('lastVerified',{}).get('runID')==run_id and state['runID']!=run_id:
        return dict(status='PACKAGE_SUCCESSOR_PRESERVED',sourceWrites=0,producerReplays=0)
    require(state['status']=='halted' and state['mode']=='package' and state['runID']==run_id and
            state['dispatchID']==os.environ['RRGH_DISPATCH_ID'],'Wrong halted package owner')
    run=read_audit_run(api,run_id)
    response=api.call('GET','actions/runs/'+str(run_id)+'/jobs?per_page=100')
    require(response['total_count']==len(response['jobs'])<=100,'Incomplete package recovery job inventory')
    selected={name:[j for j in response['jobs'] if j['name']==name] for name in ('package-stage','package-verify')}
    require(all(len(v)==1 for v in selected.values()),'Ambiguous package recovery workers')
    if all(v[0]['conclusion']=='success' for v in selected.values()):
        return finish(api,root,source,recovering=True)
    failed=[(name,v[0]) for name,v in selected.items() if v[0]['conclusion']=='failure']
    require(len(failed)==1 and all(v[0]['status']=='completed' for v in selected.values()),
            'Only one conclusively failed package worker can recover')
    name,job=failed[0]
    lines=gh('actions/jobs/'+str(job['id'])+'/logs',api.token,raw=True).splitlines()
    error=reports(lines,'final-package-error')
    require(error['workerPhase']==('stage' if name=='package-stage' else 'verify'),
            'Transport failure phase differs from failed worker')
    source_plan,auth=source_context(source,state)
    cursor=recovery_allocation(source_plan,state,auth,error)
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'retain failed package allocation; fund bounded transport recovery')
    return dispatch(api,root,old,state,'package',allowed_run=run_id)


def main():
    from rrgh_dispatcher import GitHub,caller
    command=sys.argv[1];require(command in ('enroll','finish','recover'),'Unknown package command')
    caller('launch' if command=='enroll' else 'package')
    result={'enroll':enroll,'finish':finish,'recover':recover}[command](GitHub(os.environ['GH_TOKEN']),Path('.'),sys.argv[2])
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
