"""Closed, finite two-child allocations. Pure checks shared by both trust domains."""
import hashlib
import json
import math

FORMAT = 'rrgh-resumable-pairs-v1'
CLOSURE = 'rrgh-closed-batch-v1'
FIELDS = ('sourceBytes', 'sourceRequests', 'seconds', 'attempts')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False)+'\n').encode()).hexdigest()


def policy_check(policy):
    require(isinstance(policy, dict) and set(policy) ==
            {'format','workers','targetJobs','stage','successfulWaves','baselineTilesPerSecond',
             'recentTilesPerSecond'}, 'Batch policy fields changed')
    require(policy['format'] == FORMAT and policy['workers'] == 2 and
            policy['targetJobs'] in (12,24) and policy['stage'] in ('pilot12','pilot24','active24'),
            'Unreviewed batch policy')
    require(policy['targetJobs'] == (12 if policy['stage']=='pilot12' else 24), 'Batch stage mismatch')
    require(type(policy['successfulWaves']) is int and 0<=policy['successfulWaves']<=2,
            'Invalid pilot count')
    numbers=[policy['baselineTilesPerSecond'], *policy['recentTilesPerSecond']]
    require(isinstance(policy['recentTilesPerSecond'],list) and len(numbers)<=4 and
            all(type(n) in (int,float) and math.isfinite(n) and n>0 for n in numbers),
            'Invalid throughput history')
    return policy


def partition(approved, closure, plan_sha=None):
    require(isinstance(closure,dict) and closure.get('format')==CLOSURE and
            closure.get('allChildrenJoined') is True and closure.get('sourceLedgersMerged') is True,
            'Batch is not demonstrably closed')
    if plan_sha is not None:
        require(closure.get('planSHA256')==plan_sha,'Closure plan mismatch')
    require(closure.get('allocationSHA256')==sha(approved),'Closure allocation mismatch')
    attempted=closure.get('attemptedJobIDs');accepted=closure.get('acceptedJobIDs')
    quarantined=closure.get('quarantinedJobIDs');tail=closure.get('unattemptedJobIDs')
    require(all(isinstance(a,list) and all(isinstance(j,str) for j in a) and len(a)==len(set(a))
                for a in (approved,attempted,accepted,quarantined,tail)), 'Duplicate or malformed batch inventory')
    require(attempted==approved[:len(attempted)] and tail==approved[len(attempted):],
            'Only an exact untouched tail can remain eligible')
    require(accepted==[j for j in attempted if j in accepted] and
            quarantined==[j for j in attempted if j not in accepted] and
            set(accepted).isdisjoint(quarantined) and set(accepted)|set(quarantined)==set(attempted),
            'Accepted, consumed and untouched work must partition the allocation')
    require(type(closure.get('fallbackRequired')) is bool and
            (not tail or bool(closure.get('stopReason'))),'Unexplained partial closure')
    return attempted,accepted,quarantined,tail


def next_policy(old, audit):
    """Finite rollout and automatic *prospective* fallback; never alter a ledger."""
    policy=old.get('resumableBatch')
    if audit.get('batchPilotEnabled') is not True:
        return None
    rate=audit.get('cycleTilesPerSecond')
    if not policy:
        require(type(rate) in (float,int) and math.isfinite(rate) and rate>0,'Missing dispatch-to-recovery baseline')
        return dict(format=FORMAT,workers=2,targetJobs=12,stage='pilot12',successfulWaves=0,
                    baselineTilesPerSecond=rate,recentTilesPerSecond=[])
    policy_check(policy)
    proof=audit.get('batchClosure')
    partition(old['approvedJobIDs'],proof,audit['planSHA256'])
    if proof['fallbackRequired'] or not proof['acceptedJobIDs'] or proof['unattemptedJobIDs']:
        return None
    require(type(rate) in (float,int) and math.isfinite(rate) and rate>0,'Missing dispatch-to-recovery measurement')
    recent=(policy['recentTilesPerSecond']+[rate])[-3:]
    # One modest fluctuation is tolerated; a substantial regression or two
    # consecutive sub-baseline waves disable the trial automatically.
    baseline=policy['baselineTilesPerSecond']
    if rate<baseline*.8 or (len(recent)>=2 and all(r<baseline for r in recent[-2:])):
        return None
    stage=policy['stage'];count=min(2,policy['successfulWaves']+1)
    if stage=='pilot12' and count==2:
        if sum(recent[-2:])/2<baseline:
            return None
        stage='pilot24';count=0;recent=[]
    elif stage=='pilot24' and count==2:
        if sum(recent[-2:])/2<baseline*1.05:
            return None
        stage='active24'
    return {**policy,'stage':stage,'targetJobs':12 if stage=='pilot12' else 24,
            'successfulWaves':count,'recentTilesPerSecond':recent}


def admission(used,caps,policies,seconds_left,output_bytes,output_tiles,cache_bytes,cache_cap):
    """Check the entire pair, including outstanding reservations, before either starts."""
    amounts={k:sum(p[k] for p in policies) for k in FIELDS if k!='attempts'}
    amounts['attempts']=len(policies)
    for k,v in amounts.items():
        if used[k]+v>caps[k]:return 'pair '+k+' allowance exhausted'
    if max(p['seconds'] for p in policies)+240>seconds_left:return 'closure deadline reserve'
    if output_bytes+output_tiles*512*1024>512*2**20:return 'output envelope'
    # Each outstanding response can add metadata too. Physical immutable blocks
    # are hard-linked; only new blocks consume this shared working-cache reserve.
    growth=sum(p['sourceBytes']+p['sourceRequests']*8192 for p in policies)
    if cache_bytes+growth>cache_cap:return 'working cache envelope'
    return None
