"""One exact forward transition after wave1453 failed before any raster job."""
import copy,hashlib,json
from decimal import Decimal
from pathlib import Path

FAILED_SOURCE='c0685c5eb6a2be25ef7f294426a3d6346825551f'
FAILED_PLAN='fb654b24e8c7a8e4dbcfd7cccfe082603acb9b59284770c34564df2a8994e537'
FAILED_RUN=42899104427
FAILED_REF={'bytes':539,'generation':'1794343916377562','key':'engineering/map-production/plans/'+FAILED_PLAN+'/slots/00000/receipt.json','sha256':'75fb66f8e985316649bb7a9b54a4384255b82b9240c61176e9dc0a0836859df0'}
MARKER=dict(format='rrgh-seed-bootstrap-forward-recovery-v1',failedSequence=1453,failedRunID=FAILED_RUN,
    failedSourceSHA=FAILED_SOURCE,failedPlanSHA256=FAILED_PLAN,failedBootstrapReceipt=FAILED_REF,
    retainEntireFailedAllocation=True,restorationReservedUSD='0.05',inspectionReservedUSD='0.03',
    restoredStoredBytes=4918025,acceptedRasterTiles=277587,unstartedRasterJobs=4)

def require(ok,message):
    if not ok:raise ValueError(message)
def canonical(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def original():
    path=Path(__file__).resolve().parents[1]/'config/gorge-campaign-wave-1453-20261102/PLAN.json'
    return json.loads(path.read_bytes())
def carry(old):
    from gorge_campaign_budget import cost
    require(digest(old)==FAILED_PLAN,'Original failed allocation changed')
    c=copy.deepcopy(old['campaign']['carry'])
    c['chargedUSD']=str(Decimal(c['chargedUSD'])+cost(old['limits'])+Decimal('0.08'))
    c['storedBytes']+=old['limits']['storedBytes']+MARKER['restoredStoredBytes']
    return c

def validate(plan,old):
    require(plan.get('seedBootstrapRecovery')==MARKER and digest(old)==FAILED_PLAN,
        'Exact seed bootstrap failure history required')
    require(plan['campaign']['sequence']==1454 and plan['campaign']['previousRecovery']==old['campaign']['previousRecovery'] and
        plan['campaign']['carry']==carry(old),'Failed allocation or restoration reservation lost')
    for k in ('approvedJobIDs','completedJobIDs','priorAttemptCounts','limits','slots','nativeRepairHistory','crosswaveHistory','finalOverviewHistory'):
        require(plan.get(k)==old.get(k),'Seed recovery changed original inventory or resource ceilings: '+k)
    require(all(old['priorAttemptCounts'].get(j,0)==0 for j in old['approvedJobIDs']) and len(old['approvedJobIDs'])==4,
        'A consumed raster job cannot be retried')

def verify_predecessor(slot,plan,previous):
    from gorge_second_stage import record
    old=original();validate(plan,old)
    require(previous['status']=='verified' and previous['settlement']['sequence']==1452 and
        previous['nextCarry']==old['campaign']['carry'],'Last independently verified boundary changed')
    closed=record(slot,FAILED_REF)
    require(closed['planSHA256']==FAILED_PLAN and closed['slot']==0 and closed['result']['status']=='failed' and
        closed['result']['errorClass']=='ValueError' and closed['nonrefundableAllocation']==old['slots'][0] and
        closed['used']['attempts']==0 and closed['used']['sourceBytes']==0 and closed['used']['sourceRequests']==0,
        'Failure was not confined to seed bootstrap')

PREDECESSOR_BLOCK="""                if previous.get('status') not in ('verified','partial-verified') or previous['settlement']['sequence']!=c['sequence']-1:
                    raise ValueError('Previous recovery must close successfully')
                if previous['status']=='partial-verified' and not previous['settlement']['ambiguousAllocationRetained']:
                    raise ValueError('Partial recovery must retain full ambiguous allocation')
                if previous['nextCarry']!=c['carry']:raise ValueError('Cumulative ledger cannot reset or silently fork')"""
PREDECESSOR_PATCH="""                if plan.get('seedBootstrapRecovery') and c['sequence']==1454:
                    from rrgh_seed_bootstrap_recovery import verify_predecessor
                    verify_predecessor(slot,plan,previous)
                else:
"""+'\n'.join('    '+line for line in PREDECESSOR_BLOCK.splitlines())


def strip_predecessor_patch(code):
    if PREDECESSOR_PATCH in code:
        require(code.count(PREDECESSOR_PATCH)==1, "Duplicate bootstrap recovery hook")
        return code.replace(PREDECESSOR_PATCH,PREDECESSOR_BLOCK)
    return code
