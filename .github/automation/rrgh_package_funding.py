"""Finite source-free package allocations under the unchanged campaign budget."""
import copy
from decimal import Decimal

from rrgh_package_authority import digest, require

POLICY=dict(format='rrgh-final-package-authority-v1',enabled=True,
    authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-10',
    requiredRasterTiles=278278,requiredAcceptedJobs=34750,sharedFiles=340,
    maxPartBytes=256000000,maxPartEntries=60000,maxPartsPerGroup=64,
    sourceRequests=0,sourceBytes=0,preserveAcceptedOutputs=True,
    preserveConsumedAttempts=True,activateCatalogs=False)
MIB=2**20


def allocation(stored,egress,writes,reads,seconds):
    from gorge_checkpoint import DIMENSIONS
    v=dict.fromkeys(DIMENSIONS,0)
    v.update(storedBytes=stored,egressBytes=egress,classARequests=writes,
             classBRequests=reads,seconds=seconds)
    return v


def caps(operation):
    """Each cap includes claims, receipts, metadata response bounds and headroom."""
    kind=operation['kind']
    overhead=2*MIB
    if kind=='inventory':
        jobs=operation['jobs'];waves=operation['stop']-operation['start']
        require(type(jobs) is int and 0<jobs<=34750 and 0<waves<=96,'Invalid metadata allocation')
        requests=3*waves+jobs+24
        reads=waves*288*1024+jobs*64*1024+8*MIB
        # One metadata slice is bounded to64MiB encoded/128MiB decoded.
        return [allocation(66*MIB,reads+66*MIB+overhead,8,requests+6,2400),
                allocation(2*MIB,reads+66*MIB+overhead,8,requests+6,2400)]
    if kind=='layout':
        require(1<=operation['slices']<=32 and 0<operation['encodedBytes']<=512*MIB,
                'Final metadata layout input exceeds fixed bound')
        reads=operation['encodedBytes']+overhead
        return [allocation(128*MIB,reads+132*MIB,256,260,1800),
                allocation(2*MIB,reads+132*MIB,8,260,1800)]
    if kind=='part':
        size=operation['archiveBytes'];content=operation['contentBytes'];files=operation['files']
        descriptor=operation['descriptorBytes']
        require(type(size) is int and 0<size<=256000000 and 0<content<size and
                type(files) is int and 2<=files<=60000 and 0<descriptor<=32*MIB,
                'Final native part bounds changed')
        from rrgh_package_ingress import reservation
        upload=reservation(size)
        # Worst case one immutable source range per member; no speculative
        # cache reads, public source access or refund of failed requests.
        return [allocation(size+2*MIB,content+upload['egressBytes']+descriptor+overhead,
                           upload['classARequests']+8,files+12,2400),
                allocation(2*MIB,size+descriptor+overhead,8,16,1200)]
    if kind=='indexes':
        require(operation['groups']==3 and 3<=operation['parts']<=192,'Complete three-group release required')
        return [allocation(8*MIB,16*MIB,32,24,600),allocation(4*MIB,16*MIB,16,24,600)]
    raise ValueError('Unknown final package operation')


def make(source_plan, anchor, operation, carry, ordinal, previous, controller_digest,
         authority_sha, expires_at):
    from gorge_campaign_budget import CAMPAIGN, APPROVAL, RATES, cost, monthly, add_usage
    from gorge_checkpoint import validate_plan
    require(anchor['planSHA256']==digest(source_plan) and
            anchor['sequence']==source_plan['campaign']['sequence'] and
            carry['priorCompletedJobs']==34750 and carry['priorRasterTiles']==278278 and
            carry['priorSunlightAssets']==320 and
            type(ordinal) is int and ordinal>=0,'Verified raster completion anchor required')
    slots=caps(operation);limits=add_usage(*slots)
    charge=cost(limits)
    require(Decimal(carry['chargedUSD'])+charge<=Decimal('123.00') and
            monthly(carry['storedBytes']+limits['storedBytes'])<=Decimal('2.00'),
            'Package reservation exceeds original campaign or storage ceiling')
    phase=dict(format='rrgh-final-package-phase-v1',authority=copy.deepcopy(POLICY),
        authoritySHA256=authority_sha,anchor=copy.deepcopy(anchor),operation=copy.deepcopy(operation),
        ordinal=ordinal,previousCheckpoint=copy.deepcopy(previous),controllerDigest=controller_digest)
    if operation['kind']=='inventory':phase['inventorySlice']=[operation['start'],operation['stop']]
    plan=dict(format='rrgh-checkpoint-plan-v1',bucket='rrgh-nonproduction-protected-packages',
        purpose='rrgh-final-offline-packages-v1',expiresAt=expires_at,
        sourceSnapshotSHA256=source_plan['sourceSnapshotSHA256'],
        deleteAllowed=False,bulkProductionEnabled=False,automaticRetryPermitted=False,maxConcurrency=1,
        bookkeepingProfile='compact-v2',slots=slots,limits=limits,slotJobs={},
        completedJobIDs=source_plan['completedJobIDs']+source_plan['approvedJobIDs'],
        priorAttemptCounts=dict(source_plan['priorAttemptCounts'],**{
            j:source_plan['priorAttemptCounts'].get(j,0)+1 for j in source_plan['approvedJobIDs']}),
        campaign=dict(id=CAMPAIGN,ownerApproval=APPROVAL,ceilingUSD='125.00',
            storageTargetUSDPerMonth='2.00',sequence=anchor['sequence'],controllerEpoch=1,
            carry=copy.deepcopy(carry)),finalPackagePhase=phase)
    validate_plan(plan)
    evidence=dict(planningRates=RATES,github=dict(hardCeilingUSD=350,stopAtLimitVerified=True),
        cloudStorageAllowance=dict(approvalReference=APPROVAL+'; owner instructed completion to iPhone testing',
            approvedUSD=str(charge),reservedWorstCaseUSD=str(charge),
            approvedRecurringStorageUSDPerMonth='2.00',ongoingStorageAcknowledged=True,
            chargedRetentionMonths=1,planSHA256=digest(plan)))
    return plan,evidence


def settle(plan, usage, complete):
    from gorge_campaign_budget import cost, monthly
    caps=plan['limits'];carry=plan['campaign']['carry']
    require(set(usage)==set(caps) and all(type(v) is int and 0<=v<=caps[k] for k,v in usage.items()),
            'Package usage exceeds funded allocation')
    require(usage['sourceBytes']==usage['sourceRequests']==usage['attempts']==0,
            'Package assembly cannot produce new source tiles')
    retained=usage if complete else caps
    charged=str(Decimal(carry['chargedUSD'])+cost(retained));stored=carry['storedBytes']+retained['storedBytes']
    require(Decimal(charged)<=Decimal('123') and monthly(stored)<=Decimal('2'),
            'Package settlement exceeds original budget')
    return dict(format='rrgh-final-package-settlement-v1',planSHA256=digest(plan),
        ordinal=plan['finalPackagePhase']['ordinal'],originalAllocation=copy.deepcopy(caps),
        observedUsage=copy.deepcopy(usage),retainedUsage=copy.deepcopy(retained),
        independentReadbackComplete=complete,ambiguousAllocationRetained=not complete,
        nextCarry=dict(carry,chargedUSD=charged,storedBytes=stored),
        modeledStorageUSDPerMonth=str(monthly(stored)),invoiceReading=False)
