#!/usr/bin/env python3
"""One-time GitHub-only acceptance of eight independently verified map archives.

No Cloud credentials, storage calls, source regeneration, archive staging,
verifier slot replay or successor dispatch. Checks exact historical stage and
verifier jobs, source plan, immutable receipt IDs, and CAS-protected controller.
"""
import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

from rrgh_orphan_package_verify_20261111 import (
    preflight,source_plan_and_funding,ORIGINAL_RUN,STAGE_JOB,
    STAGE_RECEIPT,PACKAGE_PLAN,SOURCE,NEW_CONTROL)
from rrgh_package_controller import audit_run,reports
from rrgh_package_authority import digest
from rrgh_package_contract import allocate

VERIFIER_RUN=43138598788
VERIFIER_JOB=130919828018
FAILED_RECONCILE_JOB=130920484364
VERIFIER_HEAD='5c970e01405a5c421f1018a3dc580523d41ad4bd'
STATE_BLOB='90e5cad8cdb8048a24d30f847af5c848dab7cdbb'
VERIFY_RECEIPT=dict(
    bytes=1503,generation='1794449049070634',
    key='engineering/map-production/plans/'+PACKAGE_PLAN+'/slots/00001/receipt.json',
    sha256='a1558fab5d7383487d7734f51dc406172e3261cd540bd8a00c7933dc19c4459c')
VERIFY_CHECKPOINT=dict(
    bytes=3850,generation='1794449048219048',
    key='engineering/map-production/plans/'+PACKAGE_PLAN+'/slots/00001/indexes/3e29db75b2131a8ce05fe240cec5af1a437f0890af62c0fc4f17ab8cd09fd139',
    sha256='3e29db75b2131a8ce05fe240cec5af1a437f0890af62c0fc4f17ab8cd09fd139')
REQUEST_PATH='.github/automation/rrgh-archive-reconcile-request.json'
WORKFLOW='.github/workflows/rrgh-archive-reconcile-only.yml'


def require(value,message):
    if not value:raise ValueError(message)


def expected_request():
    return dict(
        format='rrgh-verified-eight-part-reconcile-v1',
        action='accept-existing-verified-parts-no-dispatch',
        authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-11',
        originalStageRunID=ORIGINAL_RUN,stageJobID=STAGE_JOB,
        verifiedRunID=VERIFIER_RUN,verifiedJobID=VERIFIER_JOB,
        failedReconcileJobID=FAILED_RECONCILE_JOB,
        verifiedRunHeadSHA=VERIFIER_HEAD,
        previousStateBlobSHA=STATE_BLOB,
        sourceSHA=SOURCE,packagePlanSHA256=PACKAGE_PLAN,
        controllerDigest=NEW_CONTROL,
        stageReceipt=STAGE_RECEIPT,verifiedReceipt=VERIFY_RECEIPT,
        verifiedCheckpoint=VERIFY_CHECKPOINT,acceptedParts=8,
        noCloudCredentials=True,noCloudRequests=True,noRasterGeneration=True,
        noArchiveRestaging=True,noVerifierSlotReplay=True,
        noNextPackageDispatch=True,noCatalogActivation=True)


def owner_identity(env):
    from rrgh_dispatcher import REPO,WORKER
    exact=dict(
        GITHUB_REPOSITORY=REPO,
        GITHUB_REF='refs/heads/'+WORKER,
        GITHUB_RUN_ATTEMPT='1',
        GITHUB_EVENT_NAME='push',
        GITHUB_ACTOR='ryanredrivergorgehiker',
        GITHUB_WORKFLOW_REF=REPO+'/'+WORKFLOW+'@refs/heads/'+WORKER,
        GITHUB_REPOSITORY_ID='1325611891',
        GITHUB_REPOSITORY_OWNER_ID='313924954')
    require(all(env.get(k)==v for k,v in exact.items()),'Incorrect owner, run, or GitHub-only workflow')
    require(str(env.get('GITHUB_RUN_ID','')).isdigit(),'Owner reconcile run ID missing')


def verify_job_identity(run,jobs):
    from rrgh_dispatcher import REPO,WORKER,WORKFLOW as RESTRICTED_WORKFLOW
    require(run.get('id')==VERIFIER_RUN and run.get('status')=='completed' and
        run.get('conclusion')=='failure' and run.get('run_attempt')==1 and
        run.get('event')=='workflow_dispatch' and
        run.get('path')=='.github/workflows/'+RESTRICTED_WORKFLOW and
        run.get('head_sha')==VERIFIER_HEAD and run.get('head_branch')==WORKER and
        run.get('repository',{}).get('full_name')==REPO and
        run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('display_title')=='RRGH queued-package-verification 1462 '+
            'f66aaf8623842a4cda678ecd2568db540fd915c0736d3770e9e14d454852b56f',
        'Not the exact original bot-verified archive run')
    def one(name):
        selected=[j for j in jobs if j.get('name')==name]
        require(len(selected)==1,'Ambiguous independent worker '+name)
        return selected[0]
    v=one('orphan-verify')
    failed=one('orphan-reconcile')
    require(v.get('id')==VERIFIER_JOB and v.get('status')=='completed' and
        v.get('conclusion')=='success' and
        failed.get('id')==FAILED_RECONCILE_JOB and failed.get('status')=='completed' and
        failed.get('conclusion')=='failure',
        'Independent verifier did not succeed or unexpected controller reconciler')
    return v,failed


def verified_report(lines):
    row=reports(lines,'final-package-verify')
    require(row.get('receiptRef')==VERIFY_RECEIPT and row.get('phase')=='final-package-verify' and
        row.get('rescue')==dict(format='rrgh-cross-run-verify-only-v1',
            originalRunID=ORIGINAL_RUN,verifierRunID=VERIFIER_RUN,
            noRestaging=True,sourceRequests=0),
        'Immutable independent readback receipt identity differs')
    result=row['result']
    require(result.get('status')=='verified' and result.get('ordinal')==18 and
        result.get('workerReceipt')==STAGE_RECEIPT and
        result.get('checkpoint')==VERIFY_CHECKPOINT and
        result.get('packagePlanSHA256')==PACKAGE_PLAN and
        result.get('verifiedParts')==8 and result.get('verifiedIndexes')==0 and
        result.get('rasterTiles')==278278 and result.get('sourceRequests')==0 and
        result.get('sourceBytes')==0 and result.get('packageBytesIndependentlyVerified') is False and
        result.get('finalPackageDeliveryComplete') is False and
        result.get('physicalIPhoneTestComplete') is False,
        'Eight-part verified receipt is not exact, source-free and unfinished')
    return row


def run(api,source,root=Path('.')):
    from rrgh_dispatch_audit import gh
    from rrgh_dispatcher import GitHub,validate_state
    from rrgh_package_controller import source_context

    owner_identity(os.environ)
    request=json.loads((Path(root)/REQUEST_PATH).read_text())
    require(request==expected_request(),'Owner did not approve this exact no-Cloud reconcile')
    old_sha,state,(original,admit,stage,_)=preflight(api,root)
    require(old_sha==STATE_BLOB and state.get('runID')==ORIGINAL_RUN and
        state.get('package',{}).get('ordinal')==18 and
        state.get('controlDigest')==NEW_CONTROL and
        state.get('packageOrphanWorkflowUpgrade') is not None and
        not state.get('packageCrossRunRecoveryHistory'),
        'Original stranded controller changed or already accepted')

    verify_run=api.call('GET','actions/runs/'+str(VERIFIER_RUN))
    resp=api.call('GET',f'actions/runs/{VERIFIER_RUN}/jobs?per_page=100')
    jobs=resp.get('jobs',[])
    require(resp.get('total_count')==len(jobs)<=100,'Incomplete independent job inventory')
    verifier,failed=verify_job_identity(verify_run,jobs)
    verify_lines=gh(f'actions/jobs/{VERIFIER_JOB}/logs',api.token,raw=True).splitlines()
    failed_lines=gh(f'actions/jobs/{FAILED_RECONCILE_JOB}/logs',api.token,raw=True).splitlines()
    require(any('ValueError: Independent readback workflow ownership changed' in x
                for x in failed_lines),
            'Controller stopped for an unexpected reason')
    verified_report(verify_lines)
    stage_lines=gh(f'actions/jobs/{STAGE_JOB}/logs',api.token,raw=True).splitlines()

    source_plan,authority=source_context(source,state)
    plan,_,_=source_plan_and_funding(source,state)
    require(digest(plan)==PACKAGE_PLAN,'Rebuilt original funded plan has changed')
    synthetic=[copy.deepcopy(admit),copy.deepcopy(stage),
               dict(name='package-verify',status='completed',conclusion='success')]
    result=audit_run(state,plan,original,synthetic,stage_lines,verify_lines)
    require(result.get('receiptRef')==VERIFY_RECEIPT and
        result.get('checkpoint')==VERIFY_CHECKPOINT and
        result.get('verifiedParts')==8 and result.get('verifiedIndexes')==0 and
        result.get('nextOperation',{}).get('kind')=='parts' and
        [p['partID'] for p in result['nextOperation']['parts']]==
            ['core-%03d'%i for i in range(8,16)] and
        result['settlement']['nextCarry']['priorRasterTiles']==278278 and
        Decimal('0')<Decimal(result['settlement']['nextCarry']['chargedUSD'])<=Decimal('124.25'),
        'Independent receipt, next operation, cost or raster carry incorrect')

    # Purely construct the exact successor; there is NO Cloud slot and NO
    # dispatch here. The existing controller must approve all contract bounds.
    next_state=copy.deepcopy(state)
    cursor,_,_=allocate(source_plan,next_state,authority,
        result['nextOperation'],result['settlement']['nextCarry'],19,result['checkpoint'])
    cursor['lastVerified']={
        **{k:result[k] for k in ('ordinal','operation','receiptRef','checkpoint',
              'inventorySlices','verifiedParts','verifiedIndexes',
              'packageBytesIndependentlyVerified','catalogCandidates')},
        'runID':ORIGINAL_RUN,'verifyRunID':VERIFIER_RUN,
        'planSHA256':PACKAGE_PLAN,'crossRunVerified':True}
    cursor['retainedFailures']=copy.deepcopy(state['package']['retainedFailures'])
    next_state.setdefault('packageCrossRunRecoveryHistory',[]).append(dict(
        format='rrgh-verified-eight-part-reconcile-v1',
        originalRunID=ORIGINAL_RUN,verifyRunID=VERIFIER_RUN,
        verifyJobID=VERIFIER_JOB,failedReconcileJobID=FAILED_RECONCILE_JOB,
        stageReceipt=STAGE_RECEIPT,verifyReceipt=VERIFY_RECEIPT,
        previousOrdinal=18,nextOrdinal=19,
        independentlyAcceptedParts=8,sourceRequests=0,
        sourceWrites=0,producerReplays=0,
        nextPackageDispatch=False,catalogActivation=False))
    next_state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    validate_state(next_state,root)
    # Recheck the exact live old blob before a single SHA-conditional controller CAS.
    require(api.state()[0]==old_sha,'Controller changed while auditing verified receipts')
    new_sha=api.cas(old_sha,next_state,
        'accept exact 8 independently verified archive parts, paused before next package dispatch')
    print(json.dumps(dict(
        status='VERIFIED_EIGHT_PARTS_ACCEPTED_WITHOUT_DISPATCH',
        verifiedParts=8,verifiedIndexes=0,
        previousOrdinal=18,nextOrdinal=19,
        oldControllerBlob=old_sha,newControllerBlob=new_sha,
        sourceRequests=0,cloudRequests=0,archiveRestaging=False,
        nextPackageDispatch=False,catalogActivation=False),sort_keys=True))


def main():
    from rrgh_dispatcher import GitHub
    require(len(sys.argv)==2,'Exactly one accepted source checkout required')
    run(GitHub(os.environ['GH_TOKEN']),Path(sys.argv[1]))


if __name__=='__main__':main()
