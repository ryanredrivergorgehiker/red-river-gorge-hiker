"""Finite completion queues; old native attempts are never reopened.

USGS must be requested at each original zoom so labels retain their intended
scale. It is not eligible for the derived-child overview renderer.
"""
import math

BOUNDS = [-83.8, 37.65, -83.4, 37.95]
BASELINE_PLAN = 'e2631ee1ca7b5a8b0dd787afcabcf8abfbf9d76e3420f2dbdd28a2f33eaa4902'
POLICY = dict(format='rrgh-completion-queues-v1', enabled=True,
    authorizedBy='ryanredrivergorgehiker', authorizedOn='2026-11-09',
    baselineSequence=1322, baselinePlanSHA256=BASELINE_PLAN,
    baselineAcceptedTiles=265702, requiredRasterTiles=278278,
    phase='usgs-original-lower-zooms', maxJobs=12,
    preserveConsumedAttempts=True, preserveAcceptedOutputs=True)
PHASE = dict(format='rrgh-completion-phase-v1', phase=POLICY['phase'],
    authority=POLICY, originalZoomService=True, requiredPositions=1770)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def authorized(value):
    require(value == POLICY, 'Exact owner-authorized completion queue required')
    return True


def lower_usgs_index(region):
    require(region['boundsWGS84'] == BOUNDS and
        region['profiles']['core']['usgs-topo'] == 16,
        'USGS regional geometry or native quality changed')
    def xy(lon, lat, z):
        n = 2**z
        return (math.floor((lon + 180) / 360 * n),
            math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))
    rows = {}
    for z in range(10, 16):
        left, bottom = xy(BOUNDS[0], BOUNDS[1], z)
        right, top = xy(BOUNDS[2], BOUNDS[3], z)
        for x in range(left, right + 1):
            for y in range(top, bottom + 1):
                jid = f'usgs-topo-{z}-{x}-{y}'
                rows[jid] = dict(id=jid, layer='usgs-topo', group='core',
                    z=z, x=x, y=y, operation='usgs-tile', sourceIDs=[],
                    dependencies=[], outputTiles=[[z, x, y]], preservedComplete=False)
    require(len(rows) == 1770, 'USGS completion denominator changed')
    return rows


def select(region, accepted, attempts, authority):
    authorized(authority)
    index = lower_usgs_index(region)
    eligible = [j for j in index.values() if j['id'] not in accepted and
        attempts.get(j['id'], 0) == 0]
    # First allocation samples every original zoom. Later allocations retain
    # the proven serial twelve-job envelope and proceed from detailed to broad.
    if not set(index).intersection(accepted) and not any(attempts.get(j, 0) for j in index):
        result = []
        for z in range(10, 16):
            result += sorted((j for j in eligible if j['z'] == z),
                key=lambda j: (j['x'], j['y']))[:2]
        return result
    return sorted(eligible, key=lambda j: (-j['z'], j['x'], j['y']))[:POLICY['maxJobs']]


def validate_plan(plan, region, authority):
    authorized(authority)
    require(plan.get('completionPhase') == PHASE and plan.get('overviewPilot') is None and
        plan.get('resumableBatch') is None, 'Completion phase authority changed')
    index = lower_usgs_index(region)
    jobs = region['jobs']
    require(0 < len(jobs) <= POLICY['maxJobs'] and
        jobs == [index.get(j['id']) for j in jobs] and
        [j['id'] for j in jobs] == plan['approvedJobIDs'], 'Unreviewed lower-zoom jobs')
    require(jobs == select(region, plan['completedJobIDs'], plan['priorAttemptCounts'], authority),
        'Completion queue skipped, replayed or reordered positions')
    require(all(plan['jobPolicies'].get(j['id']) ==
        dict(seconds=600, sourceBytes=1048576, sourceRequests=1) for j in jobs),
        'Original USGS source/time policy changed')


def waiting_summary(plan, region, audit):
    """Queue exhaustion is a verified phase boundary, never full completion."""
    authorized(audit.get('completionPolicy'))
    require(plan.get('completionPhase') == PHASE, 'Only the enrolled phase can settle')
    require(not audit.get('sourcePixelGapJobs') and not audit.get('partialRecovered') and
        not audit.get('checkpointRecovery') and audit['jobsNew'] == len(plan['approvedJobIDs']),
        'Incomplete allocation cannot close the phase')
    accepted = plan['completedJobIDs'] + plan['approvedJobIDs']
    require(len(accepted) == len(set(accepted)) == audit['acceptedJobs'], 'Phase settlement count mismatch')
    attempts = {**plan['priorAttemptCounts'], **{j: 1 for j in plan['approvedJobIDs']}}
    require(not select(region, accepted, attempts, audit['completionPolicy']), 'Fresh lower-zoom work remains')
    index = lower_usgs_index(region)
    verified = len(set(index).intersection(accepted))
    return dict(format='rrgh-completion-phase-wait-v1', phase=POLICY['phase'],
        sequence=plan['campaign']['sequence'], planSHA256=audit['planSHA256'],
        recoveryReceipt=audit['receiptRef'], acceptedRasterTiles=audit['acceptedRasterTiles'],
        requiredRasterTiles=278278, verifiedLowerUSGSTiles=verified,
        consumedUnacceptedLowerUSGSTiles=len(index)-verified,
        remainingRasterTiles=278278-audit['acceptedRasterTiles'],
        fullRasterCoverageComplete=False, nextPhase='verified-overviews-and-native-repairs')
