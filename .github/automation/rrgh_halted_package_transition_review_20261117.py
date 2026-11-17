"""SOURCE-ONLY review of a future owner-approved HALTED package transition.

This proposal has no API client, no state-file writer, no credential access, no
Cloud interaction and no executable dispatch path. A candidate state is held in
memory ONLY, so it cannot be mistaken for owner authorization or a live claim.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.github/automation'))
import rrgh_dispatcher as dispatcher
import rrgh_package_contract as contract
from rrgh_package_authority import require
from rrgh_package_controller import source_context
from test_rrgh_full_package_historical_budget_20261117 import evidence, recompute

LIVE_BLOB_SHA='24e3468dd67d96d541a383a2db93f585c9464b02'
OLD_DIGEST='ab8c5bc19ef079cdd36df45c13240aad17fa526ba5214e55e32a4bbdb63a32a8'
# Exact candidate fingerprint, as demonstrated by draft PR #140, NOT merged.
CANDIDATE_DIGEST='9876ab579696c5ba0d3ea4246f326ba744ee090c12fc4afb3993c6c6d39a8875'
CANDIDATE_PR=140
CANDIDATE_HEAD_SHA='f6ccbc111751d17099232732e6e6e5fc04d10c00'
ACCEPTED_RECEIPT='1c54e40b0b8e50b5e030ebebf10b2384872664699ade365ecadeb2495e60e4f8'
SOURCED_PLAN='a161d6d494b0c737734de937a90c11fc1bb9aac6a0d93ab57bac7304ba75c891'
ACCEPTED_SOURCE='d17d0e335ac47e1f6d116e149992cc02d6e4a827'


def _blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+bytes([0])+raw).hexdigest()


def proposal(root=ROOT,source=None,expiry='2026-11-19T00:00:00Z'):
    """Create ONLY a dry-run review summary; never return/write a live state."""
    root=Path(root).resolve()
    source=Path(source or root/'source').resolve()
    path=root/dispatcher.STATE
    raw=path.read_bytes()
    require(_blob(raw)==LIVE_BLOB_SHA, 'Live halted controller blob moved')
    import json
    old=json.loads(raw)
    require(dispatcher.local_digest(root)==OLD_DIGEST==old['controlDigest'],
            'Exact reviewed current worker source changed')
    p=old.get('package',{})
    prior=p.get('lastVerified',{})
    require(old.get('status')=='halted' and old.get('mode')=='package'
            and old.get('enabled') is True and old.get('epoch')==1
            and old.get('sequence')==1462 and old.get('runID')==43290954679
            and old.get('dispatchID') is not None
            and old.get('sourceSHA')==ACCEPTED_SOURCE
            and old.get('planSHA256')==SOURCED_PLAN
            and p.get('ordinal')==26 and p.get('retryCount')==2
            and p.get('expiresAt')=='2026-11-14T19:30:55Z'
            and len(p.get('retainedFailures',[]))==5
            and prior.get('ordinal')==23 and prior.get('verifiedParts')==32
            and prior.get('verifiedIndexes')==0 and
            prior.get('receiptRef',{}).get('sha256')==ACCEPTED_RECEIPT
            and p.get('previousCheckpoint')==prior.get('checkpoint')
            and old['completionProgress']['acceptedRasterTiles']==278278
            and old['completionProgress']['finalPackageDeliveryComplete'] is False,
            'Unreviewed halted package, source, or independent receipt')
    require([x['partID'] for x in p['operation']['parts']]==
            ['core-032','core-033']+[f'leaf-on-{n:03d}' for n in range(6)]
            and p['operation']['kind']=='parts',
            'Accepted successor group differs')
    require(datetime.fromisoformat(p['expiresAt'].replace('Z','+00:00')) <
            datetime.fromisoformat(expiry.replace('Z','+00:00')),
            'Old allocation was not expired before proposed expiry')
    report=recompute()
    require(report['fullLayoutParts']==122 and report['remainingParts']==90
            and report['finalIndexes']==3
            and Decimal(report['totalModeledUSD'])<=Decimal('122.25')
            and Decimal(report['modeledMonthlyStorageUSD'])<=Decimal('2')
            and report['doubleCountsAccepted32'] is True
            and report['additionalTransportFailuresAssumed']==0,
            'Conservative whole-delivery funding proof missing')
    require(evidence()['current']['controllerBlobSHA']==LIVE_BLOB_SHA,
            'Historical budget evidence references a different controller')

    # Compute the actual contract's funded successor and plan hash with the
    # candidate digest in memory, using only the pinned source SHA.
    source_plan,auth=source_context(source,old)
    temporary=deepcopy(old)
    temporary['controlDigest']=CANDIDATE_DIGEST
    cursor,plan,_=contract.allocate(source_plan,temporary,auth,p['operation'],
                 p['carry'],p['ordinal']+1,p['previousCheckpoint'],expiry)
    cursor['lastVerified']=deepcopy(prior)
    cursor['retainedFailures']=deepcopy(p['retainedFailures'])
    # SAME operation after exhausted prior retries: do not reset its finite
    # automatic retry allowance. One-time owner approval would allow exactly
    # one new claim, not a restored multi-attempt transport window.
    cursor['retryCount']=2
    require(cursor['ordinal']==27 and cursor['retryCount']==2
            and cursor['carry']==p['carry']
            and cursor['previousCheckpoint']==p['previousCheckpoint']
            and cursor['retainedFailures']==p['retainedFailures']
            and cursor['lastVerified']==prior
            and cursor['operation']==p['operation']
            and plan['finalPackagePhase']['controllerDigest']==CANDIDATE_DIGEST
            and plan['limits']['sourceRequests']==plan['limits']['sourceBytes']==0,
            'New in-memory source-free allocation altered immutable evidence')
    from gorge_campaign_budget import cost,monthly
    require(Decimal(p['carry']['chargedUSD'])+cost(plan['limits'])<=Decimal('122.25')
            and monthly(p['carry']['storedBytes']+plan['limits']['storedBytes'])<=Decimal('2'),
            'Single new allocation cannot be funded under existing stops')
    # Deliberately no merged controller state, CAS, credentials or dispatch.
    return {
      'kind':'rrgh-proposed-halted-package-transition-review-v1',
      'liveControllerBlobSHA':LIVE_BLOB_SHA,
      'candidateProtectedCodeDigest':CANDIDATE_DIGEST,
      'candidatePR':CANDIDATE_PR,
      'candidateHeadSHA':CANDIDATE_HEAD_SHA,
      'historicallyVerifiedLayoutParts':122,
      'historicallyVerifiedAndAcceptedParts':32,
      'remainingParts':90,'remainingIndexes':3,
      'newOrdinalProposal':27,'retryCountPreservedAt':2,
      'historicalRetainedFailures':5,
      'independentAcceptedReceiptSHA256':ACCEPTED_RECEIPT,
      'hypotheticalNewPlanSHA256':contract.digest(plan),
      'hypotheticalExpiration':expiry,
      'singleAllocationModeledReserveUSD':str(cost(plan['limits'])),
      'wholeProductUpperBoundUSD':report['totalModeledUSD'],
      'wholeProductModeledStorageUSDPerMonth':report['modeledMonthlyStorageUSD'],
      'codeMerged':False,'ownerAuthorizationPresent':False,
      'cloudDispatchAuthorized':False,'cloudCalls':0,'controllerWrites':0,
      'actualCloudInvoice':False,'realWIFAcceptanceTested':False
    }
