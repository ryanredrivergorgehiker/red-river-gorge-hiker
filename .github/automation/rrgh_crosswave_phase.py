"""First funded four-layer cross-wave allocation and exact acceptance gates."""
import copy
import hashlib
import json
from pathlib import Path

POLICY = dict(format='rrgh-crosswave-pilot-authority-v1', enabled=True,
    authorizedBy='ryanredrivergorgehiker', authorizedOn='2026-11-09',
    baselineSequence=1356,
    baselinePlanSHA256='d6d055dba16d3576d9f1fa7dba449d70d633f31d763bf973b36bab8f654c24f4',
    baselineAcceptedTiles=267472, requiredRasterTiles=278278, maxJobs=4,
    preserveAcceptedOutputs=True, preserveConsumedAttempts=True)
JOB_POLICY = dict(seconds=600, sourceBytes=0, sourceRequests=0)
BINDING_SHA='0a99f404f20cda595e80f2da390e1dde877cd234ca33886dfe8615ca45aa1990'


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def authorized(value):
    require(value==POLICY,'Exact reviewed cross-wave pilot authority required')


def phase():
    raw=Path(__file__).with_name('crosswave-pilot-bindings.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==BINDING_SHA,'Reviewed immutable child binding changed')
    binding=json.loads(raw)
    return dict(format='rrgh-crosswave-pilot-phase-v1',authority=copy.deepcopy(POLICY),
        bindings=binding['bindings'])


def select(accepted,attempts,authority):
    authorized(authority);p=phase();jobs=[b['job'] for b in p['bindings']]
    done=[j['id'] in accepted for j in jobs]
    if all(done):return [],None
    require(not any(done) and all(attempts.get(j['id'],0)==0 for j in jobs),
        'Partial or consumed pilot requires explicit checkpoint repair; never replay')
    from rrgh_crosswave_dependencies import child_ids
    require(all(set(child_ids(j))<=set(accepted) for j in jobs),'Accepted pilot children missing')
    return copy.deepcopy(jobs),p


def validate_plan(plan,region,authority):
    authorized(authority)
    jobs,p=select(plan['completedJobIDs'],plan['priorAttemptCounts'],authority)
    require(p is not None and plan.get('crosswavePhase')==p and region['jobs']==jobs and
        plan['approvedJobIDs']==[j['id'] for j in jobs] and
        plan.get('overviewPilot') is None and plan.get('completionPhase') is None and
        plan.get('resumableBatch') is None and region['boundsWGS84']==[-83.8,37.65,-83.4,37.95] and
        plan['jobPolicies']=={j['id']:JOB_POLICY for j in jobs},'Cross-wave allocation changed')


def waiting_summary(plan,region,audit):
    validate_plan(plan,region,audit.get('crosswavePolicy'))
    require(audit['jobsNew']==4 and audit['tilesNew']==4 and not audit.get('partialRecovered') and
        not audit.get('checkpointRecovery') and not audit.get('sourcePixelGapJobs'),
        'Incomplete cross-wave pilot cannot settle')
    from rrgh_crosswave_runtime import validate_verification
    validate_verification(audit.get('overviewPilotVerification'))
    require(audit['acceptedRasterTiles']==267476,'Cross-wave pilot carry changed')
    return dict(format='rrgh-crosswave-pilot-wait-v1',phase='verified-interior-overview-pilot',
        sequence=plan['campaign']['sequence'],planSHA256=audit['planSHA256'],
        recoveryReceipt=audit['receiptRef'],acceptedRasterTiles=audit['acceptedRasterTiles'],
        requiredRasterTiles=278278,remainingRasterTiles=278278-audit['acceptedRasterTiles'],
        fullRasterCoverageComplete=False,nextPhase='measured-overview-batches-and-native-repairs')
