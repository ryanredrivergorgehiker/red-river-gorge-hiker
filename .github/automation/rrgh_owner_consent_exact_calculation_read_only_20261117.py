#!/usr/bin/env python3
"""READ-ONLY exact source-free ordinal27 owner consent calculation.

No GitHub API, owner approval file, controller mutation, IAM, GCS, OIDC,
dispatch or Cloud calls. Logs ONLY the plan hash, funding and stop evidence.
This review branch is NEVER merged into the live Lane20 worker.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,'accepted-source/backend/scripts')
sys.path.insert(0,'.github/automation')  # production runner import precedence

import rrgh_dispatcher as dispatcher
import rrgh_package_contract as contract
from rrgh_package_controller import source_context
from rrgh_halted_package_cas_dispatch_20261117 import (
    LIVE_BLOB_SHA, OLD_DIGEST, CANDIDATE_DIGEST,
    ACCEPTED_RECEIPT, ACCEPTED_SOURCE, SOURCED_PLAN,
    REQUIRED_PARTS, git_blob)
from test_rrgh_full_package_historical_budget_20261117 import recompute

EXPIRY='2026-11-18T18:45:00Z'
root=Path('.').resolve()
raw=(root/dispatcher.STATE).read_bytes()
assert git_blob(raw)==LIVE_BLOB_SHA
old=json.loads(raw)
assert old['status']=='halted' and old['mode']=='package'
assert old['runID']==43290954679 and old['package']['ordinal']==26
assert old['controlDigest']==OLD_DIGEST
assert old['sourceSHA']==ACCEPTED_SOURCE and old['planSHA256']==SOURCED_PLAN
assert old['package']['retryCount']==2
assert len(old['package']['retainedFailures'])==5
assert old['package']['lastVerified']['receiptRef']['sha256']==ACCEPTED_RECEIPT
assert old['package']['lastVerified']['verifiedParts']==32
assert [p['partID'] for p in old['package']['operation']['parts']]==REQUIRED_PARTS
assert dispatcher.local_digest(root)==CANDIDATE_DIGEST, 'PR140 source not installed exactly'
report=recompute()
assert report['remainingParts']==90 and report['finalIndexes']==3
assert report['doubleCountsAccepted32'] is True
source_plan,auth=source_context(root/'accepted-source',old)
temporary=deepcopy(old)
temporary['controlDigest']=CANDIDATE_DIGEST
p=old['package']
cursor,plan,evidence=contract.allocate(
    source_plan,temporary,auth,p['operation'],p['carry'],
    27,p['previousCheckpoint'],EXPIRY)
assert cursor['operation']==p['operation'] and cursor['carry']==p['carry']
assert cursor['previousCheckpoint']==p['previousCheckpoint']
cursor['retryCount']=2
cursor['lastVerified']=deepcopy(p['lastVerified'])
cursor['retainedFailures']=deepcopy(p['retainedFailures'])
assert cursor['retryCount']==2 and len(cursor['retainedFailures'])==5
assert plan['limits']['sourceRequests']==plan['limits']['sourceBytes']==0
from gorge_campaign_budget import cost, monthly
charge=cost(plan['limits'])
assert Decimal(p['carry']['chargedUSD'])+charge<=Decimal('122.25')
assert monthly(p['carry']['storedBytes']+plan['limits']['storedBytes'])<=Decimal('2')
assert Decimal(report['totalModeledUSD'])+Decimal('0.75')<=Decimal('125')
print('RRGH_EXACT_OWNER_CONSENT_READ_ONLY '+json.dumps({
    'proposedExpiresAt':EXPIRY,
    'oldControllerGitBlobSHA':LIVE_BLOB_SHA,
    'candidateCodeDigest':CANDIDATE_DIGEST,
    'newPackagePlanSHA256':contract.digest(plan),
    'nextAllocationModeledUSD':str(charge),
    'wholeDeliveryModeledUSD':report['totalModeledUSD'],
    'monthlyStorageModeledUSD':report['modeledMonthlyStorageUSD'],
    'originalCampaignCeilingUSD':'125.00',
    'packageStopUSD':'122.25',
    'finalDeliveryReserveUSD':'0.75',
    'monthlyStorageCeilingUSD':'2.00',
    'newCloudReads':0,
    'ownerApprovalFileCreated':False,
    'controllerWrite':False,
    'cloudDispatch':False,
},sort_keys=True))
