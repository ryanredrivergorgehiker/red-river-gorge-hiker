#!/usr/bin/env python3
"""One-time, fail-closed independent verification of already staged package bytes.

Never calls package stage, renders source imagery, overwrites a GCS generation,
or resumes a consumed Cloud slot. The only Cloud allocation is the previously
UNCLAIMED verifier slot 1 of the exact existing ordinal-18 package plan.
Verification and reconciliation use separate GitHub jobs and a pinned request.
"""
import copy
import json
import os
from pathlib import Path
import sys

ORIGINAL_RUN=43091451308
STAGE_JOB=130769440727
UNSTARTED_VERIFY_JOB=130782410459
STATE_BLOB='6ca979be03da246609f51832e305991de08b681b'
SOURCE='d17d0e335ac47e1f6d116e149992cc02d6e4a827'
RASTER_PLAN='a161d6d494b0c737734de937a90c11fc1bb9aac6a0d93ab57bac7304ba75c891'
PACKAGE_PLAN='84105fa536ac50fdaeeef5e57d5286d4b557f77a291ff81c72c8423e16f728cb'
DISPATCH='f66aaf8623842a4cda678ecd2568db540fd915c0736d3770e9e14d454852b56f'
CONTROL='45a286bbe0f1d5681d51a651f9a832cb93889da82723efed4c261fde9a033c69'
NEW_CONTROL='ab8c5bc19ef079cdd36df45c13240aad17fa526ba5214e55e32a4bbdb63a32a8'
STAGE_RECEIPT=dict(
    bytes=2023,generation='1794428738795953',
    key='engineering/map-production/plans/'+PACKAGE_PLAN+'/slots/00000/receipt.json',
    sha256='5420c670014f8439036237dd437ba959b4afe3eb0d29759571f4877a8e981925')
WORKFLOW='.github/workflows/offline-map-restricted-dispatch.yml'
REQUEST='.github/automation/rrgh-queued-verify-request.json'


def require(ok,message):
    if not ok:raise ValueError(message)


def identity(env):
    from rrgh_dispatcher import REPO,WORKER
    expected={'GITHUB_REPOSITORY':REPO,'GITHUB_REF':'refs/heads/'+WORKER,
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_NAME':'workflow_dispatch',
        'GITHUB_ACTOR':'github-actions[bot]',
        'GITHUB_WORKFLOW_REF':REPO+'/'+WORKFLOW+'@refs/heads/'+WORKER,
        'GITHUB_REPOSITORY_ID':'1325611891',
        'GITHUB_REPOSITORY_OWNER_ID':'313924954'}
    require(all(env.get(k)==v for k,v in expected.items()),
            'Not the single owner-authenticated verification workflow')
    require(str(env.get('GITHUB_RUN_ID','')).isdigit(),'Recovery run identity absent')


def accepted_upgrade():
    return dict(format='rrgh-queued-verify-existing-wif-cutover-v1',
        authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-11',
        previousControlDigest=CONTROL,newControlDigest=NEW_CONTROL,
        priorStateBlobSHA=STATE_BLOB,originalRunID=ORIGINAL_RUN,
        sourceSHA=SOURCE,packagePlanSHA256=PACKAGE_PLAN,
        preserveAcceptedOutputs=True,sourceRequests=0,
        noArchiveRestaging=True,catalogActivation=False)


def exact_state(state, request):
    p=state.get('package') or {}
    progress=state.get('completionProgress') or {}
    require(state.get('format')=='rrgh-controller-state-v1' and
        state.get('owner')=='autonomous-v1' and state.get('epoch')==1 and
        state.get('enabled') is True and state.get('status')=='running' and
        state.get('mode')=='package' and state.get('runID')==ORIGINAL_RUN and
        state.get('sequence')==1462 and state.get('dispatchID')==DISPATCH and
        state.get('sourceSHA')==SOURCE and state.get('planSHA256')==RASTER_PLAN and
        state.get('controlDigest')==NEW_CONTROL and
        state.get('packageOrphanWorkflowUpgrade')==accepted_upgrade() and
        progress.get('acceptedRasterTiles')==278278 and
        progress.get('remainingRasterTiles')==0 and
        progress.get('finalPackageDeliveryComplete') is False and
        p.get('ordinal')==18 and p.get('planSHA256')==PACKAGE_PLAN and
        p.get('operation',{}).get('kind')=='parts' and
        [v.get('partID') for v in p.get('operation',{}).get('parts',[])]==
        ['core-%03d'%i for i in range(8)] and
        p.get('lastVerified',{}).get('ordinal')==16 and
        p.get('lastVerified',{}).get('verifiedParts')==0 and
        p.get('lastVerified',{}).get('verifiedIndexes')==0 and
        p.get('retryCount')==1 and len(p.get('retainedFailures',[]))==1 and
        p['retainedFailures'][0].get('runID')==43090539453,
        'Accepted raster/queued package cursor differs from one reviewed incident')
    expected=dict(format='rrgh-queued-verify-v1',action='verify-only-not-restage',
        authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-11',
        previousRunID=ORIGINAL_RUN,stageJobID=STAGE_JOB,
        unfinishedVerifyJobID=UNSTARTED_VERIFY_JOB,packagePlanSHA256=PACKAGE_PLAN,
        sourceSHA=SOURCE,priorStateBlobSHA=STATE_BLOB,stageReceipt=STAGE_RECEIPT,
        noSourceReadsOrWrites=True,noArchiveRestaging=True,noCatalogActivation=True,
        newVerifierSlot=1,independentReadbackRequired=True)
    require(request==expected,'Exact fresh owner-verified repair request missing')
    return p


def original_jobs(api,state):
    from rrgh_dispatcher import REPO,WORKER,WORKFLOW
    run=api.call('GET','actions/runs/'+str(ORIGINAL_RUN))
    require(run.get('id')==ORIGINAL_RUN and run.get('status')=='completed' and
        run.get('conclusion')=='failure' and run.get('run_attempt')==1 and
        run.get('path')=='.github/workflows/'+WORKFLOW and
        run.get('head_branch')==WORKER and run.get('repository',{}).get('full_name')==REPO and
        run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('display_title')==f'RRGH package 1462 {DISPATCH}',
        'Not the original terminated and authenticated package run')
    response=api.call('GET',f'actions/runs/{ORIGINAL_RUN}/jobs?per_page=100')
    jobs=response.get('jobs',[])
    require(response.get('total_count')==len(jobs)<=100,
            'Unbounded or incomplete original job inventory')
    def one(name):
        xs=[j for j in jobs if j.get('name')==name]
        require(len(xs)==1,'Missing/duplicate original '+name)
        return xs[0]
    admit,stage,unstarted=one('admit'),one('package-stage'),one('package-verify')
    require(admit.get('conclusion')=='success' and stage.get('id')==STAGE_JOB and
        stage.get('status')=='completed' and stage.get('conclusion')=='success' and
        unstarted.get('id')==UNSTARTED_VERIFY_JOB and
        unstarted.get('status')=='queued' and unstarted.get('conclusion') is None and
        unstarted.get('runner_name') is None,
        'Original verification may have executed or staging was not accepted')
    return run,admit,stage,unstarted


def preflight(api,root):
    from rrgh_dispatcher import validate_state,assert_no_other_producers
    original_sha,state=api.state()
    request=json.loads((Path(root)/REQUEST).read_text())
    exact_state(state,request)
    validate_state(state,root)
    original=original_jobs(api,state)
    assert_no_other_producers(api,int(os.environ['GITHUB_RUN_ID']))
    return original_sha,state,original


def prepare_code_upgrade(api,root):
    """Single owner-approved CAS from reviewed old digest to reviewed WIF path.

    No cloud objects or package bytes are touched here; the existing package
    allocation remains bound to its ORIGINAL fingerprint until readback.
    """
    from rrgh_dispatcher import validate_state,local_digest,assert_no_other_producers
    old,state=api.state()
    require(old==STATE_BLOB and state.get('controlDigest')==CONTROL,
            'Original completed-staging controller identity already changed')
    request=json.loads((Path(root)/REQUEST).read_text())
    upgraded=copy.deepcopy(state)
    upgraded['controlDigest']=NEW_CONTROL
    upgraded['packageOrphanWorkflowUpgrade']=accepted_upgrade()
    exact_state(upgraded,request)
    require(local_digest(root)==NEW_CONTROL,'Reviewed existing WIF workflow digest changed')
    validate_state(upgraded,root)
    original_jobs(api,state)
    assert_no_other_producers(api)
    return api.cas(old,upgraded,'one-time reviewed existing-WIF verifier path; no Cloud work')


def source_plan_and_funding(source,state):
    from rrgh_package_controller import source_context
    from rrgh_package_contract import funding
    from rrgh_package_authority import digest
    # The already-staged ordinal-18 plan was funded under the prior trusted
    # workflow digest. Reconstruct that immutable plan only; successor plans
    # use the newly reviewed digest after receipt-bound reconciliation.
    legacy_state=copy.deepcopy(state)
    legacy_state['controlDigest']=CONTROL
    sp,authority=source_context(source,legacy_state)
    plan,evidence=funding(sp,legacy_state,authority)
    from rrgh_package_funding import caps
    # One funded verifier slot covers ALL eight parts in this operation. Its
    # originally approved reservation is 8 x 2 MiB, not one part's 2 MiB.
    # Compare the full slot envelope to the existing immutable contract, not
    # an invented one-part cap that rejects the original accepted plan.
    original_slots=caps(state['package']['operation'])
    require(digest(plan)==PACKAGE_PLAN and
        plan['finalPackagePhase']['ordinal']==18 and
        plan['finalPackagePhase']['operation']==state['package']['operation'] and
        plan['finalPackagePhase']['controllerDigest']==CONTROL and
        plan['slots']==original_slots and len(original_slots)==2 and
        len(state['package']['operation']['parts'])==8 and
        plan['slots'][1]['sourceRequests']==0 and plan['slots'][1]['sourceBytes']==0 and
        plan['slots'][1]['storedBytes']==8*2*2**20,
        'Existing eight-part unconsumed verification allocation changed')
    return plan,evidence,authority


def verify_only(api,root,source):
    # Check immutable GitHub ownership first. source_context (inside funding)
    # verifies the exact source SHA and registers source/backend/scripts in
    # sys.path BEFORE importing any gorge_* native modules. An import failure
    # must never claim/consume the reserved Cloud verifier slot.
    old_sha,state,_=preflight(api,root)
    plan,evidence,authority=source_plan_and_funding(source,state)

    from rrgh_package_authority import digest
    from rrgh_package_runtime import prior,verify,read_layout,MIB
    import rrgh_package_records as records
    import rrgh_package_contract as contract
    from rrgh_package_funding import settle
    from rrgh_wif_credentials import token
    from gorge_checkpoint import GCS,Slot,Ref
    from gorge_stage_coordinator import private_root,CountedOpener
    from gorge_campaign_budget import add_usage
    from gorge_campaign import emit

    opener=CountedOpener()
    storage=GCS(plan,evidence,token,opener)
    # Slot 1 is CREATE-ONLY. Collision halts; it cannot overwrite any prior claim.
    slot=Slot(storage,plan,1,os.environ['GITHUB_RUN_ID'])
    opener.deadline=slot.meter.deadline
    try:
        stage_ref,stage=slot.recover_receipt(0)
        require(stage_ref.__dict__==STAGE_RECEIPT and
            stage['claim']['key']==('engineering/map-production/plans/'+PACKAGE_PLAN+
                                  '/slots/00000/claim.json') and
            stage.get('nonrefundableAllocation')==plan['slots'][0] and
            stage['result']['status']=='staged' and
            stage['result']['packagePlanSHA256']==PACKAGE_PLAN and
            stage['result']['operation']==state['package']['operation'] and
            stage['result'].get('sourceRequests')==stage['result'].get('sourceBytes')==0,
            'Immutable original stage receipt/claim or operation changed')
        prior_checkpoint=prior(slot,authority,plan)
        operation=plan['finalPackagePhase']['operation']
        require(operation==contract.next_operation(
            authority,prior_checkpoint,read_layout(slot,prior_checkpoint)),
            'Independently reviewed package operation shifted')
        rebuilt=verify(slot,authority,prior_checkpoint,operation,
                       stage['result']['product'],private_root())
        checkpoint=records.put(slot,rebuilt,MIB,2*MIB)
        next_op=contract.next_operation(authority,rebuilt,read_layout(slot,rebuilt))
        ledger=settle(plan,add_usage(stage['used'],dict(slot.meter.used)),True)
        result=dict(status='verified',packagePlanSHA256=PACKAGE_PLAN,
            authoritySHA256=digest(authority),ordinal=18,operation=operation,
            workerReceipt=STAGE_RECEIPT,checkpoint=checkpoint,settlement=ledger,
            nextOperation=next_op,inventorySlices=len(rebuilt['slices']),
            verifiedParts=len(rebuilt['parts']),verifiedIndexes=len(rebuilt['indexes']),
            rasterTiles=278278,sourceRequests=0,sourceBytes=0,
            packageBytesIndependentlyVerified=next_op is None,
            catalogCandidates=rebuilt.get('catalogCandidates'),
            finalPackageDeliveryComplete=False,physicalIPhoneTestComplete=False)
        # The verifier never moves the controller or starts another stage.
        # It only publishes the independently re-read checkpoint under the
        # original funded-but-unused slot, and records its own true run ID.
        require(api.state()[0]==old_sha,'Controller changed during independent verification')
        receipt=slot.finish(result)
        emit(phase='final-package-verify',receiptRef=receipt.__dict__,result=result,
             rescue=dict(format='rrgh-cross-run-verify-only-v1',
                 originalRunID=ORIGINAL_RUN,verifierRunID=int(os.environ['GITHUB_RUN_ID']),
                 noRestaging=True,sourceRequests=0),
             gcsIncludingReceipt=opener.summary())
    except Exception:
        # Do not regenerate, retry or mutate controller after an ambiguous slot
        # claim. A separately inspected receipt is required for any next action.
        raise


def reconcile(api,root,source):
    from rrgh_dispatcher import validate_state,dispatch
    from rrgh_dispatch_audit import gh
    from rrgh_package_controller import reports,audit_run
    from rrgh_package_authority import digest
    import rrgh_package_contract as contract
    from rrgh_package_controller import source_context

    state_sha,state,(original,admit,stage,never_started)=preflight(api,root)
    plan,evidence,authority=source_plan_and_funding(source,state)
    verify_run_id=int(os.environ['GITHUB_RUN_ID'])
    run=api.call('GET','actions/runs/'+str(verify_run_id))
    jobs_resp=api.call('GET',f'actions/runs/{verify_run_id}/jobs?per_page=100')
    jobs=jobs_resp.get('jobs',[])
    require(jobs_resp.get('total_count')==len(jobs)<=30 and
        run.get('event')=='push' and run.get('run_attempt')==1 and
        run.get('path')==WORKFLOW and
        run.get('actor',{}).get('login')=='ryanredrivergorgehiker' and
        run.get('status') in ('in_progress','completed'),
        'Independent readback workflow ownership changed')
    verify_jobs=[j for j in jobs if j.get('name')=='orphan-verify']
    require(len(verify_jobs)==1 and verify_jobs[0].get('conclusion')=='success' and
            verify_jobs[0].get('status')=='completed',
            'Independent verifier job did not conclude successfully')
    stage_lines=gh('actions/jobs/'+str(STAGE_JOB)+'/logs',api.token,raw=True).splitlines()
    verification_lines=gh('actions/jobs/'+str(verify_jobs[0]['id'])+'/logs',
                          api.token,raw=True).splitlines()
    # Audit includes exact cross-run ownership checks ABOVE. The original
    # functional audit independently checks the joined stage/verify receipts,
    # hashes, settlement, operation lineage and catalog flags.
    synthetic=[copy.deepcopy(admit),copy.deepcopy(stage),
        dict(name='package-verify',status='completed',conclusion='success')]
    result=audit_run(state,plan,original,synthetic,stage_lines,verification_lines)
    row=reports(verification_lines,'final-package-verify')
    require(row.get('rescue')==dict(format='rrgh-cross-run-verify-only-v1',
        originalRunID=ORIGINAL_RUN,verifierRunID=verify_run_id,
        noRestaging=True,sourceRequests=0),
        'Verifier is not one exact independent retry-free recovery')
    summary={k:result[k] for k in ('ordinal','operation','receiptRef','checkpoint',
        'inventorySlices','verifiedParts','verifiedIndexes',
        'packageBytesIndependentlyVerified','catalogCandidates')}
    summary.update(runID=ORIGINAL_RUN,verifyRunID=verify_run_id,
        planSHA256=PACKAGE_PLAN,crossRunVerified=True)
    require(result['nextOperation'] is not None and
        result['verifiedParts']==8 and result['verifiedIndexes']==0 and
        result['settlement']['nextCarry']['priorRasterTiles']==278278,
        'Expected bounded first eight parts were not independently accepted')
    cursor,_,_=contract.allocate(
        source_plan_and_funding_input(source,state),state,authority,
        result['nextOperation'],result['settlement']['nextCarry'],19,result['checkpoint'])
    cursor['lastVerified']=summary
    cursor['retainedFailures']=copy.deepcopy(state['package']['retainedFailures'])
    state.setdefault('packageCrossRunRecoveryHistory',[]).append(dict(
        format='rrgh-queued-verify-recovery-v1',originalRunID=ORIGINAL_RUN,
        verifierRunID=verify_run_id,stageJobID=STAGE_JOB,
        orphanVerifyJobID=UNSTARTED_VERIFY_JOB,
        stageReceipt=STAGE_RECEIPT,verifyReceipt=result['receiptRef'],
        previousOrdinal=18,nextOrdinal=19,sourceRequests=0,
        sourceWrites=0,producerReplays=0))
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    validate_state(state,root)
    old=api.cas(state_sha,state,'verified orphan package without restaging; advance exact successor')
    return dispatch(api,root,old,state,'package',allowed_run=int(os.environ['GITHUB_RUN_ID']))


def source_plan_and_funding_input(source,state):
    from rrgh_package_controller import source_context
    plan,_=source_context(source,state)
    return plan


def main():
    from rrgh_dispatcher import GitHub
    require(len(sys.argv)==3 and sys.argv[1] in ('verify','reconcile'),
            'Expected exact verify/reconcile command and source root')
    identity(os.environ)
    api=GitHub(os.environ.get('GH_TOKEN',''))
    root=Path('.')
    if sys.argv[1]=='verify':verify_only(api,root,Path(sys.argv[2]))
    else:print(json.dumps(reconcile(api,root,Path(sys.argv[2])),sort_keys=True))


if __name__=='__main__':
    main()
