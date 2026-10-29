#!/usr/bin/env python3
"""Offline Gate C assessor. Never transfers data, starts jobs, or grants access.

Uses preserved measurements, explicit rate/budget evidence, and implementation
receipts. A passing result is a review prerequisite, not a production executor.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path

GIB = 2**30
REQUIRED_CONTROLS = (
    'generationPinnedRecovery', 'createOnlyCheckpointWrites',
    'durableCumulativeReservations', 'packedCacheDeltas',
    'sourceTransferCeiling', 'gcsEgressCeiling', 'storageCeiling',
    'revision4ReceiptsAndLedgersPreserved',
)


def number(value, label):
    if isinstance(value, bool):
        raise ValueError(label + ' must be a finite nonnegative number')
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(label + ' must be numeric') from exc
    if not result.is_finite() or result < 0:
        raise ValueError(label + ' must be finite and nonnegative')
    return result


def recent(timestamp, now):
    try:
        when = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return when.tzinfo is not None and 0 <= (now - when).total_seconds() <= 86400
    except (AttributeError, TypeError, ValueError):
        return False


def assess(forecast, controls, now=None):
    now = now or datetime.now(timezone.utc)
    # These are archived measured-sample projections, not new benchmarks.
    source = number(forecast['sourceAndCompute']['totalSourceCacheBytes'], 'source bytes')
    output = number(forecast['combined']['archiveBytes'], 'package bytes')
    if source != int(source) or output != int(output):
        raise ValueError('Byte counts must be integers')
    rates = controls['rates']
    storage = number(rates['storageUSDPerGiBMonth'], 'storage rate')
    egress = number(rates['egressUSDPerGiB'], 'egress rate')
    a = number(rates['classAUSDPer1000'], 'Class A rate')
    b = number(rates['classBUSDPer1000'], 'Class B rate')
    if min(storage, egress, a, b) <= 0:
        raise ValueError('No assumed free-tier or zero-rate credits')
    raw_count = math.ceil(source / 65536)
    packed_count = math.ceil(source / (64 * 2**20))
    # Scenario comparisons expose costs omitted by a byte-storage-only model.
    scenarios = {
        'raw64KiBObjectCountEstimate': raw_count,
        'raw64KiBUploadOperationsUSD': float(raw_count * a / 1000),
        'packed64MiBMinimumObjectCountEstimate': packed_count,
        'packed64MiBMinimumUploadOperationsUSD': float(packed_count * a / 1000),
        'sourceCacheGiB': float(source / GIB),
        'retainedSourceCacheUSDPerMonth': float(source / GIB * storage),
        'oneCompleteExternalCacheRecoveryUSD': float(source / GIB * egress),
        'packageGiB': float(output / GIB),
        'packagesUSDPerMonth': float(output / GIB * storage),
        'oneCompletePackageDownloadUSD': float(output / GIB * egress),
    }
    limits = controls['proposedLimits']
    stored = number(limits['storedBytes'], 'stored byte ceiling')
    read = number(limits['egressBytes'], 'egress byte ceiling')
    class_a = number(limits['classARequests'], 'Class A ceiling')
    class_b = number(limits['classBRequests'], 'Class B ceiling')
    months = number(limits['chargedRetentionMonths'], 'retention months')
    if months < 1:
        raise ValueError('At least one month of retention must be budgeted')
    # No deletion privilege or lifecycle rule is inferred from stopping work.
    cap_cost = (stored / GIB * storage * months + read / GIB * egress
                + class_a / 1000 * a + class_b / 1000 * b)
    margin = number(limits['costContingencyFraction'], 'contingency')
    if margin < Decimal('0.2'):
        raise ValueError('At least 20 percent contingency required')
    reserved_cost = cap_cost * (1 + margin)
    blockers = []
    for section in ['githubBilling', 'gcsBilling', 'bucket']:
        evidence = controls.get(section, {})
        if not evidence.get('evidenceReference') or not recent(evidence.get('observedAt'), now):
            blockers.append(section + ': current evidence missing or older than 24 hours')
    github = controls.get('githubBilling', {})
    if github.get('hardCeilingUSD') != 350 or github.get('stopAtLimitVerified') is not True:
        blockers.append('GitHub $350 hard stop not verified')
    if github.get('currentUsedUSD') is None:
        blockers.append('Current GitHub spend unavailable')
    elif number(github['currentUsedUSD'], 'GitHub spend') >= 350:
        blockers.append('GitHub ceiling already reached')
    if controls.get('runner') != {'repositoryVisibility': 'public', 'label': 'ubuntu-latest',
                                  'artifactUploads': False, 'actionsCache': False}:
        blockers.append('Only verified standard public Ubuntu with no Actions artifacts/cache is budgeted')
    gcs = controls.get('gcsBilling', {})
    if any(gcs.get(k) is None for k in ['approvedRemainingUSD', 'alreadyReservedUSD']):
        blockers.append('Current approved GCS headroom/reservations unavailable')
    elif reserved_cost + number(gcs['alreadyReservedUSD'], 'GCS reservations') > number(gcs['approvedRemainingUSD'], 'GCS headroom'):
        blockers.append('Proposed GCS cost reservation exceeds approved remaining funds')
    bucket = controls.get('bucket', {})
    if bucket.get('name') != 'rrgh-nonproduction-protected-packages' or bucket.get('storageClass') != 'STANDARD':
        blockers.append('Existing bucket and Standard storage class not verified')
    if not bucket.get('location') or bucket.get('rateProfileVerified') is not True:
        blockers.append('Bucket location/rate profile not verified')
    if bucket.get('uniformAccessVerified') is not True or bucket.get('publicAccessPrevention') != 'enforced':
        blockers.append('Existing bucket protections not verified')
    if controls.get('retentionLiabilityAcknowledged') is not True:
        blockers.append('Persistent storage obligation unresolved: producer cannot delete objects')
    for name in REQUIRED_CONTROLS:
        receipt = controls.get('implementationEvidence', {}).get(name)
        if not isinstance(receipt, str) or not receipt.strip():
            blockers.append('Production-scale control unverified: ' + name)
    if controls.get('acceptedPrivateInputsVerified') is not True:
        blockers.append('Accepted private vector/weather input recovery incomplete')
    if stored < source + 2 * output:
        blockers.append('Declared storage cannot retain the forecast cache plus outputs and verification copy')
    if read < output:
        blockers.append('Egress allowance cannot cover one complete package verification read')
    if class_a < packed_count + 34750 + 244:
        blockers.append('Class A ceiling omits packed cache, job receipts, or package/checkpoint objects')
    return {
        'format': 'rrgh-production-cost-gate-v1',
        'observedAt': now.isoformat(),
        'fullProductionPreflightPassed': not blockers,
        'productionDispatched': False,
        'scenarios': scenarios,
        'proposedWorstCaseGCSUSD': float(cap_cost),
        'proposedGCSReservationWithContingencyUSD': float(reserved_cost),
        'blockers': blockers,
        'notes': ['No account balance, rate location, deletion, lifecycle, free tier or credit is assumed.',
                  'Packed-object count is a lower bound; shard boundaries and partial packs increase it.',
                  'This assessor is not yet wired into a durable production executor.',
                  'Passing does not validate imagery, authorize deployment or establish a regional release.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forecast', required=True, type=Path)
    parser.add_argument('--controls', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = assess(json.loads(args.forecast.read_text()), json.loads(args.controls.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'fullProductionPreflightPassed': result['fullProductionPreflightPassed'],
                      'blockerCount': len(result['blockers']),
                      'proposedGCSReservationWithContingencyUSD': result['proposedGCSReservationWithContingencyUSD']}))
    raise SystemExit(0 if result['fullProductionPreflightPassed'] else 2)
