"""Read accepted checkpoint subsets without converting failed attempts to success.

The prospective parent plan must pin this source to the immutable acceptance
inventory. This reader returns only exact accepted job refs; it never lists,
writes, retries a producer, or accepts an unresolved native position.
"""
import re

PARTIAL='partial-needs-typed-receipt'
COMPLETION='wave289-consumed-recovery'
COMPLETION_PLAN='cc8badd1cd3f48912d111d3e7d5db78a28741e5401af2d2d67228bd80345a3e0'
ORIGINAL289='f5f2666692abc512b68445ea449314d26dad95be73ae7f12a139617490e3abdf'
MANIFEST289='684135e243bda9d45e9b25d103115d078399a279ffe9d20f43675d2fa29996b9'


def require(ok,message):
    if not ok:raise ValueError(message)


def bounded(value,prefix,limit,exact=False):
    from rrgh_verified_tile_catalog import ref
    ref(value)
    require((value['key']==prefix if exact else value['key'].startswith(prefix)) and value['bytes']<=limit,
        'Typed child receipt scope/size changed')
    return value


def resolve(slot,source):
    from gorge_second_stage import record
    from gorge_campaign import load_large
    kind=source.get('acceptanceKind');sha=source['sourcePlanSHA256'];seq=source['sequence']
    require(kind in (PARTIAL,COMPLETION) and re.fullmatch('[0-9a-f]{64}',sha) and
        type(seq) is int and seq>0 and 0<source['sourceJobCount']<=512 and
        len(set(source['acceptedJobIDs']))==len(source['acceptedJobIDs'])==source['sourceJobCount'],
        'Explicit accepted-subset authority required')
    prefix='engineering/map-production/plans/'+sha+'/slots/'
    receipt_path=prefix+'00002/receipt.json'
    if kind==COMPLETION:
        require(seq==289 and sha==ORIGINAL289,'Unknown consumed-recovery completion')
        receipt_path='engineering/map-production/plans/'+COMPLETION_PLAN+'/slots/00000/receipt.json'
    recovered=record(slot,bounded(source['recovery'],receipt_path,16384,exact=True))
    r=recovered['result'];ledger=r['settlement']
    require(r['jobs']==source['sourceJobCount'] and r['tiles']==source['expectedTiles'] and
        ledger['sequence']==seq and all(r.get(k) is True for k in
            ('allOutputHashesAndPixelsVerified','allNewPackageChunksReadBack','allExistingCachesPreserved')),
        'Typed child lacks complete accepted-output verification')
    accepted=set(source['acceptedJobIDs'])
    require(not accepted.intersection(r.get('sourcePixelGapJobs',[])+r.get('uncertainJobIDs',[])),
        'Unaccepted attempt included in typed child inventory')
    if kind==COMPLETION:
        require(recovered['planSHA256']==ledger['planSHA256']==COMPLETION_PLAN and recovered['slot']==0 and
            r['status']=='verified' and r['originalPlanSHA256']==ledger['originalPlanSHA256']==sha and
            r['completionManifestSHA256']==MANIFEST289 and r.get('originalClaimsAndReceiptsUnchanged') is True and
            ledger['independentRecoveryComplete'] is True and ledger['ambiguousAllocationRetained'] is True and
            r.get('sourceJobsExecuted')==r.get('sourceRequests')==r.get('sourceBytesReceived')==0,
            'Consumed recovery allocation or completion lineage changed')
    else:
        require(recovered['planSHA256']==ledger['planSHA256']==sha and recovered['slot']==2 and
            r['status'] in ('verified','partial-verified') and
            ledger['independentRecoveryComplete'] is (r['status']=='verified') and
            ledger['ambiguousAllocationRetained'] is (r['status']=='partial-verified'),
            'Partial recovery disposition changed')
        if r['status']=='partial-verified':
            original=ledger.get('originalAllocation',{})
            require(original and ledger.get('retainedUsage')==original and
                ledger.get('demonstrablyUnused')==dict.fromkeys(original,0),
                'Failed allocation must remain fully consumed')
    worker_ref=r.get('workerReceipt')
    if worker_ref is not None:
        worker=record(slot,bounded(worker_ref,prefix+'00001/receipt.json',16384,exact=True))
        require(worker['planSHA256']==sha and worker['slot']==1 and
            worker['result']['detailRef']==r['detailRef'] and
            worker['result']['status'] in (('complete','bounded-stop') if r['status']=='verified' else ('failed',)),
            'Typed child producer closure changed')
        detail_ref=bounded(r['detailRef'],prefix+'00001/indexes/',256*1024)
    else:
        require(kind==PARTIAL and r['status']=='partial-verified' and
            r.get('salvage') in ('wave105-missing-producer-closure-v1','bounded-native-checkpoint-recovery-v1') and
            r.get('sourceJobsExecuted')==0 and r.get('unacceptedAttemptsQuarantined') is True and
            r.get('sourcePinsReconstructed',{}).get('allPriorPinsPreserved') is True and
            set(r.get('completedJobIDs',[]))==accepted and len(r['completedJobIDs'])==len(accepted),
            'Saved-checkpoint salvage lacks exact accepted subset')
        bounded(r['producerClaim'],prefix+'00001/claim.json',16384,exact=True)
        detail_ref=bounded(r['detailRef'],prefix+'00002/indexes/',256*1024)
    detail=load_large(slot,detail_ref,limit=256*1024)
    refs=detail['completedJobReceipts']
    if worker_ref is None:require(refs==r['completedJobRefs'],'Salvaged job references changed')
    expected={prefix+'00001/jobs/'+j+'.json' for j in accepted}
    require(len(refs)==len(expected) and {v['key'] for v in refs}==expected,'Typed accepted checkpoint inventory differs')
    for ref in refs:bounded(ref,prefix+'00001/jobs/',64*1024)
    return {v['key']:v for v in refs}
