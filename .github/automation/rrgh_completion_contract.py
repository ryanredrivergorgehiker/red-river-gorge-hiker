"""One separately funded completion of the consumed wave289 recovery slot.

The old plan, all its claims and the failed receipt are immutable. The new
namespace has one source-free slot; both full reservations remain charged.
"""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

MANIFEST = Path(__file__).with_name('wave289-completion.json')
PREFIX = 'engineering/map-production/plans/'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def manifest():
    return json.loads(MANIFEST.read_bytes())


def manifest_sha():
    return hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def cost(v):
    return (Decimal(v['storedBytes'])/2**30*Decimal('.03') +
            Decimal(v['egressBytes'])/2**30*Decimal('.23') +
            Decimal(v['classARequests'])/1000*Decimal('.01') +
            Decimal(v['classBRequests'])/1000*Decimal('.001'))*Decimal('1.2')


def monthly(stored):
    return Decimal(stored)/2**30*Decimal('.036')


def retained_allocation(m):
    previous = m.get('retainedCompletions', [])
    require(len(previous) <= 1 and all(p['allocation'] == m['completionAllocation'] for p in previous),
            'Only the exact bounded failed completion reservation may be retained')
    allocations = [m['originalAllocation'], m['completionAllocation']]+[p['allocation'] for p in previous]
    return {k:sum(v[k] for v in allocations) for k in m['completionAllocation']}


def funding(m=None):
    m = manifest() if m is None else m
    cap = m['completionAllocation']
    require(cap['sourceBytes'] == cap['sourceRequests'] == cap['attempts'] == 0,
            'Completion cannot fund source production')
    plan = dict(format='rrgh-checkpoint-plan-v1', bucket='rrgh-nonproduction-protected-packages',
                purpose='wave289-consumed-recovery-completion-v1', expiresAt=m['expiresAt'],
                deleteAllowed=False, bulkProductionEnabled=False, automaticRetryPermitted=False,
                maxConcurrency=1, bookkeepingProfile='compact-v2',
                sourceSnapshotSHA256=m['sourceSnapshotSHA256'],
                originalPlanSHA256=m['planSHA256'], originalRunID=m['originalRunID'],
                failedRecoveryReceipt=m['failedRecoveryReceipt'], authorizationSHA256=manifest_sha(),
                retainedCompletions=m.get('retainedCompletions', []),
                slots=[copy.deepcopy(cap)], limits=copy.deepcopy(cap), slotJobs={})
    reserve = cost(cap)
    retained = retained_allocation(m)
    carry = m['priorCarry']
    require(Decimal(carry['chargedUSD'])+cost(retained) <= Decimal('123') and
            monthly(carry['storedBytes']+retained['storedBytes']) <= Decimal('2'),
            'Original plus completion reservations exceed existing campaign authority')
    evidence = dict(planningRates=dict(storageUSDPerGiBMonth='.03', egressUSDPerGiB='.23',
                                     classAUSDPer1000='.01', classBUSDPer1000='.001'),
                    github=dict(hardCeilingUSD=350, stopAtLimitVerified=True),
                    cloudStorageAllowance=dict(approvalReference=m['authorization'],
                        approvedUSD=str(reserve), reservedWorstCaseUSD=str(reserve),
                        approvedRecurringStorageUSDPerMonth='2.00', ongoingStorageAcknowledged=True,
                        chargedRetentionMonths=1, planSHA256=sha(plan)))
    return plan, evidence


def settlement(used, m=None):
    m = manifest() if m is None else m
    funded, _ = funding(m)
    cap = m['completionAllocation']
    require(set(used) == set(cap) and all(type(v) is int and 0 <= v <= cap[k] for k,v in used.items()),
            'Completion usage exceeds its separate allocation')
    retained = retained_allocation(m)
    charged = str(Decimal(m['priorCarry']['chargedUSD'])+cost(retained))
    stored = m['priorCarry']['storedBytes']+retained['storedBytes']
    return dict(format='rrgh-campaign-settlement-v1', campaignID='gorge-full-quality-125usd-20261031',
                sequence=m['sequence'], planSHA256=sha(funded), originalPlanSHA256=m['planSHA256'],
                originalAllocation=m['originalAllocation'], completionAllocation=cap,
                retainedCompletions=m.get('retainedCompletions', []),
                retainedUsage=retained, observedCompletionUsage=used,
                demonstrablyUnused={k:0 for k in cap},
                independentRecoveryComplete=True, ambiguousAllocationRetained=True,
                chargedUSD=charged, storedBytes=stored, ceilingUSD='125.00',
                remainingAuthorityUSD=str(Decimal('125')-Decimal(charged)),
                storageEstimateUSDPerMonth=str(monthly(stored)),
                historicalReleasedUSDRetained='0.70', invoiceReading=False)


def next_carry(ledger, m=None):
    m = manifest() if m is None else m
    return dict(m['priorCarry'], chargedUSD=ledger['chargedUSD'], storedBytes=ledger['storedBytes'],
                priorCompletedJobs=m['priorCarry']['priorCompletedJobs']+m['jobs'],
                priorRasterTiles=m['priorCarry']['priorRasterTiles']+m['tiles'])


def check_reference(ref):
    funded, _ = funding()
    require(ref.get('key') == PREFIX+sha(funded)+'/slots/00000/receipt.json' and
            type(ref.get('bytes')) is int and 0 < ref['bytes'] <= 16384 and
            re.fullmatch(r'[1-9][0-9]*', str(ref.get('generation',''))) is not None and
            re.fullmatch(r'[0-9a-f]{64}', str(ref.get('sha256',''))) is not None,
            'Completion must use its fresh immutable receipt namespace')


def check_report(report):
    """Shared planner/publisher guard for the single reviewed receipt exception."""
    m = manifest()
    require(report.get('completedConsumedRecovery') is True and
            report.get('completionManifestSHA256') == manifest_sha() and
            report.get('wave') == m['sequence'] and report.get('run') == m['originalRunID'] and
            report.get('planSHA256') == m['planSHA256'] and
            report.get('batchClosure') == m['batchClosure'] and report.get('jobsNew') == m['jobs'] and
            report.get('tilesNew') == m['tiles'] and report.get('partialRecovered') is False and
            report.get('sourcePixelGapJobs') == [] and report.get('batchPilotEnabled') is False,
            'Unreviewed consumed recovery exception')
    ledger = report.get('completionSettlement', {})
    require(ledger == settlement(ledger.get('observedCompletionUsage', {})) and
            report.get('nextCarry') == next_carry(ledger) and
            report.get('acceptedJobs') == next_carry(ledger)['priorCompletedJobs'] and
            report.get('acceptedRasterTiles') == next_carry(ledger)['priorRasterTiles'],
            'Consumed and completion reservations or accepted inventory changed')
    check_reference(report['receiptRef'])
