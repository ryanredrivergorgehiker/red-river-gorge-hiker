"""Exact, source-mask-verified second-attempt pilot; no historical claim replay."""
import copy
import hashlib
import json

JOBS=['hiking-16-17534-25326','terrain-16-17537-25329','leaf-off-16-17537-25329']
JOB_SHA='54aedeefc5a2f89dcbc0d7ddd5765f7f6b7cbd867768ae72aeb87496c5f00b94'
BASELINE='a9924758e5178a70dc62d9abcc3d00e0f7921906e963bf3f62a1bb1e9bdc899b'
RECEIPT=dict(key='engineering/map-production/plans/'+BASELINE+'/slots/00002/receipt.json',
    bytes=3241,generation='1794312166017060',sha256='a5875a47b685e8c2d3eaec5ebf82b055cf6117336565bb88e442e5b5371f3a1f')
POLICY=dict(format='rrgh-native-repair-pilot-authority-v1',enabled=True,
    authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-10',
    baselineSequence=1418,baselinePlanSHA256=BASELINE,baselineAcceptedTiles=273837,
    baselineAcceptedJobs=33683,baselineRecovery=RECEIPT,requiredRasterTiles=278278,
    jobs=JOBS,jobManifestSHA256=JOB_SHA,maxJobs=3,maxGlobalAttempts=2,
    sourceMaskDiagnosticRuns=[42634892249,42682993035],
    preserveAcceptedOutputs=True,preserveConsumedAttempts=True,holdAfterPilot=True)
PHASE=dict(format='rrgh-native-repair-pilot-phase-v1',authority=POLICY,
    expectedRasterTiles=31,attemptNumber=2)


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):
    return hashlib.sha256((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()


def authorized(authority):
    require(authority==POLICY,'Exact reviewed native repair authority required')


def baseline(old,audit):
    authorized(audit.get('nativeRepairPolicy'))
    require(digest(old)==BASELINE and old['campaign']['sequence']==1418 and
        audit['wave']==1418 and audit['planSHA256']==BASELINE and audit['receiptRef']==RECEIPT and
        audit['acceptedRasterTiles']==273837 and audit['acceptedJobs']==33683 and
        audit['jobsNew']==audit['tilesNew']==len(old['approvedJobIDs'])==29 and
        not audit.get('sourcePixelGapJobs') and not audit.get('partialRecovered') and
        not audit.get('checkpointRecovery') and not old.get('nativeRepairPhase'),
        'Native repairs must begin at the exact independently settled wave1418')


def select(index,accepted,attempts,authority):
    authorized(authority)
    require(all(j not in accepted and attempts.get(j)==1 for j in JOBS),
        'Native repair requires exactly one failed prior attempt and no accepted output')
    jobs=[index[j] for j in JOBS]
    require(digest(jobs)==JOB_SHA,'Reviewed native source windows, pixel geometry or source order changed')
    return copy.deepcopy(jobs),copy.deepcopy(PHASE)


def validate_plan(plan,region,authority):
    from rrgh_expanded_production import build_index
    jobs,phase=select(build_index(region)[0],plan['completedJobIDs'],plan['priorAttemptCounts'],authority)
    require(plan.get('nativeRepairPhase')==phase and region['jobs']==jobs and
        plan['approvedJobIDs']==JOBS and plan['slotJobs']=={'1':JOBS} and
        plan['campaign']['sequence']==1419 and plan['campaign']['previousRecovery']==RECEIPT and
        plan['campaign']['carry']['priorCompletedJobs']==33683 and
        plan['campaign']['carry']['priorRasterTiles']==273837 and
        not any(plan.get(k) for k in ('crosswavePhase','completionPhase','overviewPilot','resumableBatch')) and
        set(JOBS)<=set(plan['campaign']['sourcePixelGapQuarantines']),
        'Native repair pilot scope or prior failure history changed')
    policies={JOBS[0]:dict(seconds=600,sourceBytes=67108864,sourceRequests=150),
        JOBS[1]:dict(seconds=600,sourceBytes=134217728,sourceRequests=200),
        JOBS[2]:dict(seconds=600,sourceBytes=536870912,sourceRequests=750)}
    require(plan['jobPolicies']==policies,'Original per-job native repair resource limits changed')


def validate_publication(old,old_region,plan,region,audit):
    baseline(old,audit);validate_plan(plan,region,audit['nativeRepairPolicy'])
    require(plan['completedJobIDs']==old['completedJobIDs']+old['approvedJobIDs'],
        'Native repair publication lost or invented accepted history')
    attempts=copy.deepcopy(old['priorAttemptCounts'])
    for j in old['approvedJobIDs']:
        require(attempts.get(j,0)==0,'Prior overview was already attempted')
        attempts[j]=1
    require(plan['priorAttemptCounts']==attempts,'Native repair erased or invented consumed attempts')
    campaign=copy.deepcopy(old['campaign'])
    campaign.update(sequence=1419,previousRecovery=audit['receiptRef'],carry=audit['nextCarry'])
    require(plan['campaign']==campaign,'Native repair changed campaign history or authority')
    slots=copy.deepcopy(old['slots']);slots[1]['attempts']=3
    require(plan['slots']==slots and plan['limits']==dict(old['limits'],attempts=3),
        'Native repair resource envelope changed')
    from rrgh_crosswave_batch import advance_history
    require(plan['crosswaveHistory']==advance_history(old,old_region,audit),
        'Final accepted overview provenance lost at native transition')


def waiting_summary(plan,region,audit):
    validate_plan(plan,region,audit.get('nativeRepairPolicy'))
    require(audit['planSHA256']==digest(plan) and audit['wave']==1419 and
        audit['receiptRef']['key']=='engineering/map-production/plans/'+digest(plan)+'/slots/00002/receipt.json' and
        not audit.get('partialRecovered') and not audit.get('checkpointRecovery') and
        not audit.get('batchClosure') and not audit.get('overviewPilotVerification'),
        'Native pilot requires its own independent recovery')
    failed=audit.get('sourcePixelGapJobs',[])
    accepted=audit.get('sourceCompletedJobIDs',[]) if failed else JOBS
    require(len(failed)==len(set(failed)) and len(accepted)==len(set(accepted)) and
        set(failed).isdisjoint(accepted) and set(failed)|set(accepted)==set(JOBS),
        'Native pilot settlement does not partition the exact allocation')
    count=sum(len(j['outputTiles']) for j in region['jobs'] if j['id'] in accepted)
    require(audit['jobsNew']==len(accepted) and audit['tilesNew']==count and
        audit['acceptedJobs']==33683+len(accepted) and audit['acceptedRasterTiles']==273837+count,
        'Native pilot independent accepted inventory disagrees')
    return dict(format='rrgh-native-repair-pilot-wait-v1',phase='verified-native-repair-pilot',
        sequence=1419,planSHA256=audit['planSHA256'],recoveryReceipt=audit['receiptRef'],
        acceptedRasterTiles=audit['acceptedRasterTiles'],requiredRasterTiles=278278,
        remainingRasterTiles=278278-audit['acceptedRasterTiles'],fullRasterCoverageComplete=False,
        resolvedNativeJobs=accepted,unresolvedNativeJobs=failed,
        totalConsumedAttempts={j:2 for j in JOBS},originalQuarantineHistoryPreserved=True,
        nextPhase='source-mask-verified-repair-batches-and-boundary-coverage')
