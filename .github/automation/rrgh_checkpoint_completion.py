"""Independently verify saved wave289 outputs in one new source-free slot."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from rrgh_completion_contract import (manifest, manifest_sha, funding, settlement,
                                      next_carry, require, sha, PREFIX)


def run(source_root):
    source = Path(source_root).resolve()
    sys.path.insert(0, str(source/'backend/scripts'))
    import gorge_campaign as campaign
    from gorge_checkpoint import GCS, Slot, Ref, decode_record
    from gorge_stage_coordinator import private_root, CountedOpener, verify_outputs
    from gorge_second_stage import record, recover_catalogs
    from gorge_producer_identity import require_owner, read_owner
    from rrgh_pair_worker import verify_closure
    from rrgh_wif_credentials import token
    m = manifest()
    plan, evidence, region = campaign.configuration()
    require(sha(plan) == m['planSHA256'] == os.environ['RRGH_PLAN_SHA256'] and
            os.environ['RRGH_SOURCE_SHA'] == m['sourceSHA'] and
            plan['campaign']['carry'] == m['priorCarry'] and plan['limits'] == m['originalAllocation'] and
            plan['approvedJobIDs'] == m['completedJobIDs'], 'Reviewed original source allocation changed')
    require_owner(plan, 'recovery')
    state = read_owner(os.environ)
    require(state.get('mode') == 'complete' and
            state.get('completionOf', {}).get('manifestSHA256') == manifest_sha(),
            'Exclusive completion authorization missing')
    funded, allowance = funding()
    root = private_root()
    opener = CountedOpener()
    store = GCS(funded, allowance, token, opener)
    slot = Slot(store, funded, 0, os.environ['GITHUB_RUN_ID'])
    opener.deadline = slot.meter.deadline
    try:
        def original(ref, index):
            obj = decode_record(slot.get(Ref(**ref)))
            require(obj.get('format') == 'rrgh-slot-receipt-v1' and obj.get('slot') == index and
                    obj.get('planSHA256') == m['planSHA256'], 'Original receipt lineage changed')
            claimref = Ref(**obj['claim'])
            require(claimref.key == PREFIX+m['planSHA256']+f'/slots/{index:05d}/claim.json',
                    'Original claim key changed')
            claim = json.loads(slot.get(claimref))
            require(claim['owner'] == str(m['originalRunID']) and claim['slot'] == index and
                    claim['planSHA256'] == m['planSHA256'] and claim['allocation'] == plan['slots'][index],
                    'Original claim ownership or reservation changed')
            return obj
        failed = original(m['failedRecoveryReceipt'], 2)
        require(failed['result'].get('status') == 'failed' and
                failed['result'].get('allWaveAllocationsRetained') is True and
                failed['result'].get('diagnostic') == m['originalFailure'], 'Consumed failure evidence changed')
        boot = original(m['bootstrapReceipt'], 0)
        worker = original(m['producerReceipt'], 1)
        require(boot['result']['status'] == 'ready' and boot['result']['inputProofValidated'] is True and
                worker['result']['status'] == 'complete', 'Original bootstrap/producer not closed')
        initial = campaign.load_large(slot, boot['result']['bootstrapDataRef'])
        detail = campaign.load_large(slot, worker['result']['detailRef'])
        require(detail['completedJobReceipts'] == m['completedJobRefs'], 'Saved job receipt inventory changed')
        records = [record(slot, ref, 'rrgh-checkpoint-job-v1') for ref in detail['completedJobReceipts']]
        require([r['job'] for r in records] == m['completedJobIDs'] and
                all(r['planSHA256'] == m['planSHA256'] and r['slot'] == 1 for r in records),
                'Saved job lineage changed')
        catalogs = [c for r in records for c in r['result']['outputPacks']]
        paths = [e['path'] for c in catalogs for e in c['members']]
        require(len(paths) == len(set(paths)) == m['tiles'], 'Saved tile membership changed')
        recover_catalogs(slot, catalogs, paths, root/'outputs')
        neighbors = initial['neighbors']
        oldpaths = [e['path'] for c in neighbors for e in c['members']]
        if oldpaths:
            recover_catalogs(slot, neighbors, oldpaths, root/'old')
        qa = verify_outputs(plan, region, records, root/'outputs', root/'old')
        require(qa['jobs'] == m['jobs'] and qa['files'] == m['tiles'] and len(qa['seams']) > 0,
                'Independent native output verification incomplete')
        (root/'state').mkdir()
        qa['sourceLedgerVerification'] = campaign.check_states(campaign.load_large(slot, detail['stateRef']), root/'state')
        parts = campaign.assemble(slot, records, root)
        qa.update(parts=parts, regionComplete=False)
        from rrgh_overview_pilot import verify as verify_overview
        qa['overviewPilotVerification'] = verify_overview(slot, plan, region, records, root, source)
        closure = verify_closure(slot, plan, detail, records, worker, vars(campaign))
        require(closure == m['batchClosure'], 'Independent closure differs from saved producer')
        from rrgh_completion_catalog import catalog
        qa['verifiedTileCatalog'] = catalog(plan, region, records, detail['completedJobReceipts'], qa, parts, root, recovery_plan_sha=sha(funded))
        qa['verifiedTileCatalogStatus'] = 'verified'
        qaref = campaign.save_large(slot, qa)
        ledger = settlement(dict(slot.meter.used))
        result = dict(status='verified', completionManifestSHA256=manifest_sha(),
            originalProducerRunID=m['originalRunID'], originalPlanSHA256=m['planSHA256'],
            failedRecoveryReceipt=m['failedRecoveryReceipt'], workerReceipt=m['producerReceipt'],
            bootstrapReceipt=m['bootstrapReceipt'], jobs=qa['jobs'], tiles=qa['files'],
            outputBytes=qa['bytes'], qaRef=qaref, detailRef=worker['result']['detailRef'],
            packageParts=len(parts), packageBytes=sum(p['byteCount'] for p in parts),
            adjacentEdgesMeasured=len(qa['seams']), sourceJobsExecuted=0, sourceRequests=0, sourceBytesReceived=0,
            settlement=ledger, nextCarry=next_carry(ledger), batchClosure=closure,
            sourcePixelGapJobs=[], pixelGapAttemptsConsumed=0, overviewPilotVerification=qa['overviewPilotVerification'],
            allOutputHashesAndPixelsVerified=True, allNewPackageChunksReadBack=True, allExistingCachesPreserved=True,
            originalClaimsAndReceiptsUnchanged=True, verifiedTileCatalogTiles=qa['verifiedTileCatalog']['tileCount'])
        require_owner(plan, 'recovery')
        receipt = slot.finish(result)
        campaign.emit(phase='independent-checkpoint-completion', receiptRef=asdict(receipt),
                      result=result, gcsIncludingReceipt=opener.summary())
    except Exception as error:
        if not slot.closed:
            try:
                slot.finish(dict(status='failed', originalAndCompletionAllocationsRetained=True,
                                 errorClass=type(error).__name__, automaticRetryPermitted=False))
            except Exception:
                pass
        raise


if __name__ == '__main__':
    run(sys.argv[1])
