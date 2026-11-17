"""Owner-gated, ONE-TIME halted package CAS and dispatch implementation.

STAGED SOURCE ONLY. No executable entrypoint or Actions trigger. A separate,
reviewed owner-authenticated workflow must explicitly call execute() after
PR140's exact protected source has been approved and installed. The module
does not mint an authorization, fetch credentials, or silently retry a job.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import rrgh_dispatcher as dispatcher
import rrgh_package_contract as contract
from rrgh_package_authority import require
from rrgh_package_controller import source_context
from rrgh_halted_package_transition_review_20261117 import (
    LIVE_BLOB_SHA, OLD_DIGEST, CANDIDATE_DIGEST, CANDIDATE_HEAD_SHA,
    ACCEPTED_RECEIPT, ACCEPTED_SOURCE, SOURCED_PLAN,
)
from test_rrgh_full_package_historical_budget_20261117 import recompute, evidence
from gorge_campaign_budget import cost, monthly

OWNER = 'ryanredrivergorgehiker'
REQUIRED_PARTS = ['core-032', 'core-033'] + [f'leaf-on-{i:03d}' for i in range(6)]
AUTH_FORMAT = 'rrgh-owner-one-time-halted-package-authorization-v1'


def git_blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\\0' + raw).hexdigest()


def utc(value):
    require(type(value) is str and value.endswith('Z'), 'UTC timestamp required')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except (ValueError, OverflowError):
        raise ValueError('Invalid authorization time') from None
    return parsed


def require_owner_context(context):
    """GitHub runner MUST supply these trusted fields, never request JSON."""
    require(context == {
        'repository': dispatcher.REPO,
        'ref': 'refs/heads/' + dispatcher.WORKER,
        'event': 'workflow_dispatch',
        'actor': OWNER,
        'triggeringActor': OWNER,
        'runAttempt': 1,
    }, 'Authenticated one-time owner execution context missing')


def exact_halt(old, old_sha, root):
    raw = (Path(root) / dispatcher.STATE).read_bytes()
    require(old_sha == LIVE_BLOB_SHA and git_blob(raw) == LIVE_BLOB_SHA
            and json.loads(raw) == old,
            'Exact historical halted controller Git blob changed')
    p = old.get('package', {})
    prior = p.get('lastVerified', {})
    require(old.get('format') == 'rrgh-controller-state-v1'
            and old.get('owner') == 'autonomous-v1'
            and old.get('enabled') is True and old.get('epoch') == 1
            and old.get('status') == 'halted' and old.get('mode') == 'package'
            and old.get('sequence') == 1462 and old.get('runID') == 43290954679
            and old.get('controlDigest') == OLD_DIGEST
            and old.get('sourceSHA') == ACCEPTED_SOURCE
            and old.get('planSHA256') == SOURCED_PLAN
            and old.get('dispatchID') is not None
            and p.get('ordinal') == 26 and p.get('retryCount') == 2
            and p.get('expiresAt') == '2026-11-14T19:30:55Z'
            and len(p.get('retainedFailures', [])) == 5
            and p.get('operation', {}).get('kind') == 'parts'
            and [part['partID'] for part in p['operation']['parts']] == REQUIRED_PARTS
            and prior.get('ordinal') == 23 and prior.get('verifiedParts') == 32
            and prior.get('verifiedIndexes') == 0
            and prior.get('receiptRef', {}).get('sha256') == ACCEPTED_RECEIPT
            and p.get('previousCheckpoint') == prior.get('checkpoint')
            and old.get('completionProgress', {}).get('acceptedRasterTiles') == 278278
            and old['completionProgress'].get('finalPackageDeliveryComplete') is False
            and not old.get('pendingControllerUpgrade'),
            'Unreviewed halt, failed allocation, receipt or accepted history')
    return p, prior


def verify_authorization(request, old, prior, new_plan_hash, reserve, report, now):
    require(type(request) is dict, 'Owner approval object missing')
    expected = {
        'format': AUTH_FORMAT,
        'action': 'resume-source-free-package-once',
        'authorizedBy': OWNER,
        'candidatePR': 140,
        'candidateHeadSHA': CANDIDATE_HEAD_SHA,
        'fromControllerBlobSHA': LIVE_BLOB_SHA,
        'fromDigest': OLD_DIGEST,
        'toDigest': CANDIDATE_DIGEST,
        'sourceSHA': ACCEPTED_SOURCE,
        'sourcePlanSHA256': SOURCED_PLAN,
        'failedRunID': 43290954679,
        'acceptedReceiptSHA256': ACCEPTED_RECEIPT,
        'acceptedCheckpoint': prior['checkpoint'],
        'failedOrdinal': 26,
        'nextOrdinal': 27,
        'nextParts': REQUIRED_PARTS,
        'retainedFailures': 5,
        'retryCountRetained': 2,
        'newPackagePlanSHA256': new_plan_hash,
        'nextAllocationModeledUSD': str(reserve),
        'wholeDeliveryModeledUSD': report['totalModeledUSD'],
        'monthlyStorageModeledUSD': report['modeledMonthlyStorageUSD'],
        'originalCampaignCeilingUSD': '125.00',
        'packageStopUSD': '122.25',
        'storageCeilingUSDPerMonth': '2.00',
        'finalDeliveryReserveUSD': '0.75',
        'sourceRequests': 0,
        'preserveHistory': True,
        'oneNewCloudDispatch': True,
        'catalogActivation': False,
        'appRelease': False,
    }
    require(set(request) == set(expected) | {'authorizedAt', 'expiresAt'},
            'Owner approval fields incomplete or unreviewed')
    require(all(request.get(key) == value for key, value in expected.items()),
            'Owner approval differs from exact state, source, receipt, budget or scope')
    issued, expiry = utc(request['authorizedAt']), utc(request['expiresAt'])
    require(issued <= now < expiry and expiry - issued <= timedelta(hours=24)
            and now - issued <= timedelta(hours=24)
            and expiry > utc(old['package']['expiresAt']),
            'Approval expired, future-dated or valid for too long')


def verify_fences(api, state):
    """Before publishing READY, enforce the same legacy/source hard stops
    enforced a second time by dispatcher.dispatch() before its durable claim.
    """
    policy = state.get('githubBudgetPolicy', {})
    require(policy.get('enforcement') == 'github-platform'
            and policy.get('authorizedBy') == OWNER
            and policy.get('stopProtectionConfirmedByOwner') is True,
            'Existing GitHub platform stop protection changed')
    dispatcher.assert_no_other_producers(api)
    _, legacy = api.file(dispatcher.ORIGINAL)
    require(dispatcher.digest(legacy) == state['legacyFenceSHA256']
            and b'# RRGH_LEGACY_INITIATION_FENCED_EPOCH_1' in legacy
            and b'if: false' in legacy,
            'Legacy producer fence changed')
    _, planner = api.file(dispatcher.LEGACY_PLANNER, ref=dispatcher.LEGACY_SUPERVISOR)
    require(dispatcher.digest(planner) == state['legacyPlannerFenceSHA256']
            and b'if: false' in planner, 'Legacy planner fence changed')
    head = api.call('GET', 'git/ref/heads/' + dispatcher.SOURCE)['object']['sha']
    require(head == ACCEPTED_SOURCE, 'Original accepted raster source moved')


def preflight(api, root, source, request, context, now=None):
    """No writes. Return exact expected GitHub blob and one funded ready state."""
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, 'Timezone-aware approval clock required')
    require_owner_context(context)
    old_sha, old = api.state()
    p, prior = exact_halt(old, old_sha, root)
    require(dispatcher.local_digest(root) == CANDIDATE_DIGEST,
            'Reviewed PR140 protected code fingerprint is not installed')
    require(utc(p['expiresAt']) < now, 'Failed claim not expired')
    report = recompute()
    require(evidence()['current']['controllerBlobSHA'] == LIVE_BLOB_SHA
            and report['fullLayoutParts'] == 122 and report['remainingParts'] == 90
            and report['finalIndexes'] == 3
            and report['doubleCountsAccepted32'] is True
            and report['additionalTransportFailuresAssumed'] == 0
            and Decimal(report['totalModeledUSD']) <= Decimal('122.25')
            and Decimal(report['modeledMonthlyStorageUSD']) <= Decimal('2'),
            'Original whole-delivery proof or storage cap does not hold')
    source_plan, authority = source_context(source, old)
    ready = deepcopy(old)
    ready['controlDigest'] = CANDIDATE_DIGEST
    cursor, plan, _ = contract.allocate(
        source_plan, ready, authority, p['operation'], p['carry'],
        p['ordinal'] + 1, p['previousCheckpoint'], request.get('expiresAt'))
    cursor['lastVerified'] = deepcopy(prior)
    cursor['retainedFailures'] = deepcopy(p['retainedFailures'])
    cursor['retryCount'] = 2  # exhausted historical window NEVER resets
    require(cursor['ordinal'] == 27 and cursor['operation'] == p['operation']
            and cursor['carry'] == p['carry']
            and cursor['previousCheckpoint'] == p['previousCheckpoint']
            and cursor['retryCount'] == p['retryCount']
            and cursor['retainedFailures'] == p['retainedFailures']
            and cursor['lastVerified'] == prior
            and plan['finalPackagePhase']['controllerDigest'] == CANDIDATE_DIGEST
            and plan['limits']['sourceRequests'] == plan['limits']['sourceBytes'] == 0,
            'Reallocated package changes accepted history, scope or source-free budget')
    reserve = cost(plan['limits'])
    require(Decimal(p['carry']['chargedUSD']) + reserve <= Decimal('122.25')
            and monthly(p['carry']['storedBytes'] + plan['limits']['storedBytes']) <= Decimal('2'),
            'Next bounded source-free allocation exceeds original limits')
    verify_authorization(request, old, prior, contract.digest(plan), reserve, report, now)
    ready.setdefault('controllerUpgradeHistory', []).append({
        'kind': 'owner-once-halted-package-ordinal27',
        'authorizedBy': OWNER, 'authorizedAt': request['authorizedAt'],
        'fromBlobSHA': LIVE_BLOB_SHA, 'fromDigest': OLD_DIGEST,
        'toDigest': CANDIDATE_DIGEST,
        'acceptedReceiptSHA256': ACCEPTED_RECEIPT,
        'acceptedCheckpoint': deepcopy(prior['checkpoint']),
        'newPlanSHA256': contract.digest(plan), 'retainedFailures': 5,
        'sourceRequests': 0, 'oneDispatchOnly': True,
    })
    ready.update(package=cursor, status='package-ready', mode='package',
                 runID=None, dispatchID=None)
    dispatcher.validate_state(ready, root)  # cannot use legacy pending-upgrade path
    verify_fences(api, old)
    return old_sha, ready


def execute(api, root, source, request, context, now=None):
    """Owner-authenticated trusted runner ONLY; no automatic replay/recovery.

    Durable exact-SHA CAS first, then existing claim-CAS and one dispatch POST.
    A failure after transition leaves state unresolved: require fresh human
    audit; NEVER repeat this function or rerun an old workflow automatically.
    """
    old_sha, ready = preflight(api, root, source, request, context, now=now)
    updated_sha = api.cas(old_sha, ready,
                          'exact owner-authorized one-time halted package ordinal27 transition')
    # Existing dispatcher separately re-verifies fences/owner before claiming.
    # A failed or ambiguous dispatch is NOT retried here.
    return dispatcher.dispatch(api, Path(root), updated_sha, ready, 'package',
                               allowed_run=43290954679)
