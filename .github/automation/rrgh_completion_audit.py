"""Trusted audit for the exact, separately reserved wave289 completion."""
from datetime import datetime
from rrgh_completion_contract import (manifest, manifest_sha, require, check_reference,
                                      settlement, next_carry, check_report)
from rrgh_salvage_audit import one, reports

REPO = 'ryanredrivergorgehiker/red-river-gorge-hiker'
BRANCH = 'lane20/offline-production-preflight-20261029'
WORKFLOW = '.github/workflows/offline-map-restricted-dispatch.yml'


def identity(run, mode, rid, dispatch):
    require(run.get('id') == rid and run.get('run_attempt') == 1 and
            run.get('head_branch') == BRANCH and run.get('path') == WORKFLOW and
            run.get('event') == 'workflow_dispatch' and run.get('actor', {}).get('login') == 'github-actions[bot]' and
            run.get('repository', {}).get('full_name') == REPO and
            run.get('display_title') == f'RRGH {mode} 289 {dispatch}', 'Completion workflow identity changed')


def jobs_for(api, rid):
    data = api.call('GET', 'actions/runs/'+str(rid)+'/jobs?per_page=100')
    require(data['total_count'] == len(data['jobs']) <= 100, 'Incomplete job inventory')
    return data['jobs']


def log_reports(api, job):
    from rrgh_dispatch_audit import gh
    return reports(gh('actions/jobs/'+str(job['id'])+'/logs', api.token, raw=True).splitlines())


def original(api):
    m = manifest()
    run = api.call('GET', 'actions/runs/'+str(m['originalRunID']))
    identity(run, 'production', m['originalRunID'], m['originalDispatchID'])
    require(run.get('head_sha') == m['originalHeadSHA'] and run.get('status') == 'completed' and
            run.get('conclusion') == 'failure', 'Original failed execution changed')
    jobs = jobs_for(api, m['originalRunID'])
    require(all(one(jobs,n)['conclusion'] == c for n,c in
                [('admit','success'), ('bounded-stage','success'), ('independent-recovery','failure'),
                 ('advance','skipped'), ('retain-failure','success')]), 'Original job outcomes changed')
    rows = log_reports(api, one(jobs, 'bounded-stage'))
    completed = [r for r in rows if 'durableJobReceipt' in r]
    finals = [r for r in rows if r.get('phase') == 'production']
    boots = [r for r in rows if r.get('phase') == 'bootstrap']
    require([r['job'] for r in completed] == m['completedJobIDs'] and
            [r['durableJobReceipt'] for r in completed] == m['completedJobRefs'] and
            sum(r['jobTiles'] for r in completed) == m['tiles'] and
            len(finals) == len(boots) == 1 and finals[0]['receiptRef'] == m['producerReceipt'] and
            finals[0]['status'] == 'complete' and finals[0]['batchClosure'] == m['batchClosure'] and
            boots[0]['receiptRef'] == m['bootstrapReceipt'], 'Original completed output evidence changed')
    failed = [r for r in log_reports(api, one(jobs, 'independent-recovery')) if r.get('phase') == 'independent-recovery']
    require(len(failed) == 1 and failed[0]['receiptRef'] == m['failedRecoveryReceipt'] and
            failed[0]['result'].get('status') == 'failed' and
            failed[0]['result'].get('allWaveAllocationsRetained') is True and
            failed[0]['result'].get('diagnostic') == m['originalFailure'], 'Consumed recovery failure changed')
    return run


def verify_result(row, state, original_run, job):
    m = manifest()
    r = row['result']; ref = row['receiptRef']
    require(r.get('status') == 'verified' and r.get('completionManifestSHA256') == manifest_sha() and
            r.get('originalProducerRunID') == m['originalRunID'] and r.get('originalPlanSHA256') == m['planSHA256'] and
            r.get('failedRecoveryReceipt') == m['failedRecoveryReceipt'] and
            r.get('workerReceipt') == m['producerReceipt'] and r.get('bootstrapReceipt') == m['bootstrapReceipt'] and
            r.get('batchClosure') == m['batchClosure'], 'Completion immutable lineage changed')
    require(r.get('jobs') == m['jobs'] and r.get('tiles') == r.get('verifiedTileCatalogTiles') == m['tiles'] and
            r.get('sourceJobsExecuted') == r.get('sourceRequests') == r.get('sourceBytesReceived') == 0 and
            r.get('adjacentEdgesMeasured', 0) > 0 and r.get('packageParts', 0) > 0 and
            r.get('packageBytes', 0) > 0 and r.get('sourcePixelGapJobs') == [] and
            r.get('pixelGapAttemptsConsumed') == 0, 'Completion QA or source-free bound failed')
    require(all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified', 'allNewPackageChunksReadBack',
                                        'allExistingCachesPreserved', 'originalClaimsAndReceiptsUnchanged')),
            'Completion acceptance evidence incomplete')
    ledger = r['settlement']
    require(ledger == settlement(ledger.get('observedCompletionUsage', {})) and r['nextCarry'] == next_carry(ledger),
            'Completion accounting did not retain both reservations')
    check_reference(ref)
    seconds = (datetime.fromisoformat(job['completed_at'].replace('Z','+00:00')) -
               datetime.fromisoformat(original_run['created_at'].replace('Z','+00:00'))).total_seconds()
    require(seconds > 0, 'Invalid dispatch-to-completion elapsed time')
    carry = r['nextCarry']
    report = dict(verified=True, partialRecovered=False, completedConsumedRecovery=True,
        completionManifestSHA256=manifest_sha(), completionSettlement=ledger,
        partialCompletedJobIDs=[], failedJobID=None, sourcePixelGapJobs=[], sourceCompletedJobIDs=[],
        wave=289, run=m['originalRunID'], recoveryRunID=state['runID'], jobsNew=m['jobs'], tilesNew=m['tiles'],
        acceptedJobs=carry['priorCompletedJobs'], acceptedRasterTiles=carry['priorRasterTiles'], sunlightAssets=320,
        historicalExclusions=45, receiptRef=ref, nextCarry=carry, receiptSHA256=ref['sha256'],
        receiptGeneration=ref['generation'], planSHA256=m['planSHA256'],
        modeledCumulativeUSD=carry['chargedUSD'], modeledMonthlyStorageUSD=ledger['storageEstimateUSDPerMonth'],
        recoveryCycleSeconds=seconds, cycleTilesPerSecond=m['tiles']/seconds,
        batchClosure=r['batchClosure'], batchPilotEnabled=False,
        fallbackReason='Owner-authorized prospective serial fallback after consumed recovery failure',
        overviewPilotEnabled=state.get('overviewPilotEnabled') is True,
        overviewPilotVerification=r.get('overviewPilotVerification'),
        sourcePolicyMode=state.get('sourcePolicyMode', 'expanded'), dispatchAuthorized=False,
        controllerDispatchID=state['dispatchID'], controllerParentRun=state.get('parentRunID'))
    check_report(report)
    return report


def audit(api, state):
    m = manifest()
    require(state.get('mode') == 'complete' and state.get('completionOf', {}).get('manifestSHA256') == manifest_sha() and
            state.get('sourceSHA') == m['sourceSHA'] and state.get('planSHA256') == m['planSHA256'] and
            state.get('sequence') == 289, 'Completion ownership changed')
    parent = original(api)
    run = api.call('GET', 'actions/runs/'+str(state['runID']))
    identity(run, 'completion', state['runID'], state['dispatchID'])
    require(run.get('status') in ('in_progress','completed') and run.get('conclusion') in (None,'success'),
            'Completion execution failed or is ambiguous')
    jobs = jobs_for(api, state['runID'])
    job = one(jobs, 'independent-completion')
    require(job['status'] == 'completed' and job['conclusion'] == 'success' and
            all(one(jobs,n)['conclusion'] == 'skipped' for n in
                ('bounded-stage','independent-recovery','independent-salvage')),
            'Completion must run on a separate runner without source production or old-slot recovery')
    rows = [r for r in log_reports(api, job) if r.get('phase') == 'independent-checkpoint-completion']
    require(len(rows) == 1, 'One independent completion report required')
    return verify_result(rows[0], state, parent, job)
