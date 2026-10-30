"""Immutable cumulative authority for finite production waves; no network API."""
from decimal import Decimal
from gorge_checkpoint import DIMENSIONS, canonical, digest, integer, validate_plan

CAMPAIGN='gorge-full-quality-25usd-20261030'
APPROVAL='Owner 2026-10-30: FULL MAP PRODUCTION; cumulative USD25; no per-batch owner approval; USD1/month storage target'
RATES={'storageUSDPerGiBMonth':'.03','egressUSDPerGiB':'.23','classAUSDPer1000':'.01','classBUSDPer1000':'.001'}
GiB=2**30

def cost(usage):
    return (Decimal(integer(usage['storedBytes']))/GiB*Decimal('.03')+
        Decimal(integer(usage['egressBytes']))/GiB*Decimal('.23')+
        Decimal(integer(usage['classARequests']))/1000*Decimal('.01')+
        Decimal(integer(usage['classBRequests']))/1000*Decimal('.001'))*Decimal('1.2')

def monthly(stored):return Decimal(integer(stored))/GiB*Decimal('.036')

def add_usage(*values):return {k:sum(integer(v.get(k,0)) for v in values) for k in DIMENSIONS}

def admit(plan,evidence):
    validate_plan(plan)
    c=plan['campaign'];carry=c['carry']
    if (c.get('id')!=CAMPAIGN or c.get('ownerApproval')!=APPROVAL or c.get('ceilingUSD')!='25.00'
        or c.get('storageTargetUSDPerMonth')!='1.00' or plan.get('maxConcurrency')!=1
        or plan.get('automaticRetryPermitted') is not False or len(plan['approvedJobIDs'])>512
        or not 1<=len(plan['approvedJobIDs']) or c.get('sequence',-1)<0):
        raise ValueError('Exact finite campaign authority required')
    prior=Decimal(carry['chargedUSD']);reserve=cost(plan['limits'])
    if not prior.is_finite() or prior<Decimal('.70') or prior+reserve>Decimal('23.00'):
        raise ValueError('Campaign admission would consume protected USD2 completion/recovery reserve')
    if monthly(carry['storedBytes']+plan['limits']['storedBytes'])>Decimal('1'):
        raise ValueError('Measured continuing storage requires owner decision')
    if c['sequence']==0:
        if carry!={'chargedUSD':'0.70','storedBytes':GiB,'priorCompletedJobs':44,'priorRasterTiles':436,'priorSunlightAssets':320}:
            raise ValueError('Historical releases and conservative storage must be retained')
        if c.get('previousRecovery') is not None:raise ValueError('First campaign wave has no predecessor')
    elif not c.get('previousRecovery'):raise ValueError('Auditable predecessor required')
    if evidence['planningRates']!=RATES or evidence['cloudStorageAllowance']['planSHA256']!=digest(canonical(plan)):
        raise ValueError('Allowance or rates changed')
    if Decimal(evidence['cloudStorageAllowance']['reservedWorstCaseUSD'])!=reserve:
        raise ValueError('Every resource ceiling must be prepaid')
    if Decimal(evidence['cloudStorageAllowance']['approvedUSD'])>Decimal('25')-prior:
        raise ValueError('Allowance exceeds cumulative remaining authority')
    b=plan['githubBilling']
    if b['hardCeilingUSD']!=350 or not b['stopAtLimitVerified'] or not b['thresholdAlertsVerified']:
        raise ValueError('GitHub hard stop required')
    if Decimal(b['spentUSD'])+Decimal(b['waveReservedUSD'])>Decimal('350'):
        raise ValueError('Insufficient Actions headroom')
    return {'reserveUSD':str(reserve),'cumulativeAdmissionUSD':str(prior+reserve),
        'monthlyAdmissionUSD':str(monthly(carry['storedBytes']+plan['limits']['storedBytes']))}

def settle(plan,used,complete):
    """New immutable result; historical claims/receipts are never rewritten."""
    for k in DIMENSIONS:
        if integer(used[k])>plan['limits'][k]:raise ValueError('Cannot conceal overrun')
    retained=used.copy() if complete else plan['limits'].copy()
    carry=plan['campaign']['carry']
    return {'format':'rrgh-campaign-settlement-v1','campaignID':CAMPAIGN,
        'sequence':plan['campaign']['sequence'],'planSHA256':digest(canonical(plan)),
        'originalAllocation':plan['limits'],'observedReservedUsage':used,'retainedUsage':retained,
        'demonstrablyUnused':{k:plan['limits'][k]-retained[k] for k in DIMENSIONS},
        'independentRecoveryComplete':complete,'ambiguousAllocationRetained':not complete,
        'chargedUSD':str(Decimal(carry['chargedUSD'])+cost(retained)),
        'storedBytes':carry['storedBytes']+retained['storedBytes'],
        'ceilingUSD':'25.00','remainingAuthorityUSD':str(Decimal('25')-Decimal(carry['chargedUSD'])-cost(retained)),
        'storageEstimateUSDPerMonth':str(monthly(carry['storedBytes']+retained['storedBytes'])),
        'historicalReleasedUSDRetained':'0.70','invoiceReading':False}
