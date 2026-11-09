"""One independent, source-free recovery of the inspected wave105 checkpoints.

Uses only original unused recovery slot 2. Producer slots are never replayed,
and the full failed allocation remains charged. Original records are immutable.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

MANIFEST=Path(__file__).with_name('wave105-salvage.json')
PIN_FIELDS=('url','length','etag','identity','lastModified','pinnedAtUTC')


def require(ok,message):
    if not ok:raise ValueError(message)


def merge_pins(database,records,region):
    """Preserve every prior pin; derive new pins only from immutable job evidence."""
    jobs={j['id']:j for j in region['jobs']}
    added=0;seen={}
    with sqlite3.connect(database) as db:
        before=dict(db.execute('SELECT url,identity FROM sources'))
        for row in records:
            job=jobs[row['job']];family='dem' if job['layer']=='terrain' else job['layer']
            allowed={s['id']:s['url'] for s in region['inventory']['sources'][family] if s['id'] in job['sourceIDs']}
            evidence=row['result']['originalReceipt']['sourceEvidence']
            require(len({s['id'] for s in evidence})==len(evidence) and
                    {s['id'] for s in evidence}==set(allowed),'Incomplete source evidence')
            for source in evidence:
                require(source['url']==allowed[source['id']],'Unapproved recovered source')
                pin={k:source[k] for k in PIN_FIELDS}
                expected=hashlib.sha256(json.dumps([pin['url'],pin['etag'],pin['length']]).encode()).hexdigest()
                require(pin['identity']==expected and type(pin['length']) is int and
                        100000<=pin['length']<=10000000000 and pin['etag'].startswith('"') and
                        pin['etag'].endswith('"'),'Recovered source identity mismatch')
                old=db.execute('SELECT identity,metadata FROM sources WHERE url=?',(pin['url'],)).fetchone()
                if old:
                    require(old[0]==pin['identity'],'Prior source identity conflict')
                    prior=json.loads(old[1])
                    require(all(prior[k]==pin[k] for k in ('url','length','etag','identity')),
                            'Prior source metadata conflict')
                else:
                    db.execute('INSERT INTO sources VALUES (?,?,?)',(pin['url'],pin['identity'],json.dumps(pin)))
                    added+=1
                require(pin['url'] not in seen or seen[pin['url']]==pin['identity'],'Conflicting job source pins')
                seen[pin['url']]=pin['identity']
        after=dict(db.execute('SELECT url,identity FROM sources'))
        require(all(after.get(k)==v for k,v in before.items()),'Prior source pin lost')
        require(db.execute('PRAGMA integrity_check(10)').fetchall()==[('ok',)],'Recovered SQLite integrity')
    return dict(priorPins=len(before),newPins=added,completedSourcePins=len(seen),
                allPriorPinsPreserved=True,derivation='prior-independent-ledger-plus-exact-job-source-evidence')


def recover_usgs_ledger(cog_database,service_database,records,region,plan,uncertain):
    """Retain both old ledgers and reconstruct service usage without a request.

    Uncertain positions keep a full one-request reservation. Successful tile
    bytes themselves are already immutable, independently verified outputs.
    """
    from rrgh_completion_phase import checkpoint_bounds
    checkpoint_bounds(plan,plan['completionPhase']['authority'])
    jobs={j['id']:j for j in region['jobs']}
    accepted={r['job']:r['result']['originalReceipt'] for r in records}
    require(len(accepted)==len(records) and set(accepted).isdisjoint(uncertain) and
        set(accepted)|set(uncertain)==set(plan['approvedJobIDs']), 'Service recovery allocation changed')
    base='https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/'
    with sqlite3.connect(service_database) as db:
        before=db.execute('SELECT * FROM calls ORDER BY id').fetchall()
        budget=db.execute('SELECT * FROM budget').fetchall()
        for jid in plan['approvedJobIDs']:
            job=jobs[jid]
            require(job['layer']=='usgs-topo' and job['operation']=='usgs-tile' and
                job['sourceIDs']==[], 'Service recovery source changed')
            url=base+f"{job['z']}/{job['y']}/{job['x']}"
            key=hashlib.sha256(url.encode()).hexdigest()
            require(db.execute('SELECT 1 FROM calls WHERE key=?',(key,)).fetchone() is None,
                'Service position already has retained usage; no duplicate recovery')
            received=0;reserved=plan['jobPolicies'][jid]['sourceBytes'];status='recovered-uncertain'
            if jid in accepted:
                receipt=accepted[jid];evidence=receipt['sourceEvidence'];outputs=receipt['outputs']
                require(len(evidence)==len(outputs)==1,'One original USGS response and tile required')
                pin=evidence[0];out=outputs[0];usage=receipt['execution']['sourceUsage']
                prefix=f"tiles/usgs-topo/{job['z']}/{job['x']}/{job['y']}."
                require(pin['url']==url and pin['parameters']=={} and
                    pin['bytes']==out['bytes'] and pin['sha256']==out['sha256'] and
                    out['path'] in (prefix+'jpg',prefix+'png') and
                    0<pin['bytes']<=500000 and usage['actual']['operations']==1 and
                    usage['actual']['receivedBodyBytes']==pin['bytes'] and
                    usage['reserved']['sourceRequests']==1 and
                    usage['reserved']['sourceBytes']<=plan['jobPolicies'][jid]['sourceBytes'],
                    'Original service response or usage proof changed')
                received=reserved=pin['bytes'];status='recovered-complete'
            db.execute('INSERT INTO calls(key,reserved,received,status,seconds) VALUES (?,?,?,?,0)',
                (key,reserved,received,status))
        require(db.execute('SELECT * FROM calls ORDER BY id LIMIT ?', (len(before),)).fetchall()==before and
            db.execute('SELECT * FROM budget').fetchall()==budget and
            db.execute('PRAGMA integrity_check(10)').fetchall()==[('ok',)],'Prior service ledger changed')
    with sqlite3.connect(cog_database) as db:
        count=db.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
    return dict(priorPins=count,newPins=0,completedSourcePins=0,allPriorPinsPreserved=True,
        derivation='prior-ledgers-plus-verified-USGS-responses-and-full-uncertain-reservations',
        recoveredServiceRequests=len(accepted),uncertainServiceRequestsRetained=len(uncertain),
        allPriorServiceUsagePreserved=True)


def run(source_root,reviewed=None):
    source=Path(source_root).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    from gorge_campaign import configuration,load_large,save_large,check_states,state_snapshot,assemble,emit
    from gorge_checkpoint import GCS,Slot,Ref,canonical,digest,decode_record,MAX_METADATA
    from gorge_campaign_budget import settle,add_usage
    from gorge_stage_coordinator import private_root,CountedOpener,verify_outputs
    from gorge_second_stage import record,recover_catalogs
    from gorge_producer_identity import require_owner
    from rrgh_wif_credentials import token
    m=json.loads(MANIFEST.read_bytes()) if reviewed is None else reviewed
    plan,evidence,region=configuration()
    from rrgh_checkpoint_recovery import bounds
    limits=bounds(plan)
    require(digest(canonical(plan))==m['planSHA256']==os.environ['RRGH_PLAN_SHA256'] and
            os.environ['RRGH_SOURCE_SHA']==m['sourceSHA'] and
            plan['campaign']['sequence']==m['sequence'] and plan['campaign']['carry']==m['priorCarry'],
            'Exact reviewed salvage source changed')
    require(plan['approvedJobIDs']==m['completedJobIDs']+m['uncertainJobIDs'] and
            ((len(m['completedJobIDs'])==7 and len(m['uncertainJobIDs'])==2) if reviewed is None else
             (m.get('format')=='bounded-native-checkpoint-recovery-v1' and
              0<len(m['completedJobIDs'])<=len(plan['approvedJobIDs'])<=limits['jobs'] and
              plan.get('resumableBatch') is None and plan.get('overviewPilot') is None)), 'Salvage subset changed')
    require_owner(plan,'recovery')
    root=private_root();opener=CountedOpener();store=GCS(plan,evidence,token,opener)
    slot=Slot(store,plan,2,os.environ['GITHUB_RUN_ID']);opener.deadline=slot.meter.deadline
    try:
        if reviewed is not None:slot.meter.reserve(**m['inspectionUsage'])
        # Read-after-inspection: late receipts are not silently overlooked.
        missing=[slot.prefix+'slots/00001/receipt.json']+[
            slot.prefix+'slots/00001/jobs/'+j+'.json' for j in m['uncertainJobIDs']]
        for key in missing:
            slot.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
            try:store._request('GET',key,{'fields':'name,generation,size'},MAX_METADATA)
            except RuntimeError as error:
                if str(error)!='GCS HTTP 404':raise
            else:raise ValueError('Inspection absence changed; salvage refused')
        claim=json.loads(slot.get(Ref(**m['producerClaim'])))
        require(claim['owner']==str(m['originalRunID']) and claim['planSHA256']==m['planSHA256'] and
                claim['slot']==1 and claim['allocation']==plan['slots'][1],'Original producer claim changed')
        bootref,boot=slot.recover_receipt(0)
        require(asdict(bootref)==m['bootstrapReceipt'] and boot['result']['status']=='ready' and
                boot['result']['inputProofValidated'] is True,'Bootstrap proof changed')
        initial=load_large(slot,boot['result']['bootstrapDataRef'])
        records=[record(slot,r,'rrgh-checkpoint-job-v1') for r in m['completedJobRefs']]
        require([r['job'] for r in records]==m['completedJobIDs'] and all(
            r['planSHA256']==m['planSHA256'] and r['slot']==1 for r in records),'Checkpoint lineage changed')
        catalogs=[c for r in records for c in r['result']['outputPacks']]
        paths=[e['path'] for c in catalogs for e in c['members']]
        require(len(paths)==len(set(paths))==m['tiles'],'Exact checkpoint output inventory changed')
        recover_catalogs(slot,catalogs,paths,root/'outputs')
        neighbors=initial['neighbors'];oldpaths=[e['path'] for c in neighbors for e in c['members']]
        if oldpaths:recover_catalogs(slot,neighbors,oldpaths,root/'old')
        qa=verify_outputs(plan,region,records,root/'outputs',root/'old')
        require(qa['jobs']==m['jobs'] and qa['files']==m['tiles'] and qa['adjacentEdgesMeasured']>0,
                'Independent full-quality subset verification failed')
        previous=record(slot,plan['campaign']['previousRecovery'])['result']
        require((previous['status']=='verified' or (reviewed is not None and previous['status']=='partial-verified' and
                previous['settlement']['ambiguousAllocationRetained'] is True)) and previous['nextCarry']==plan['campaign']['carry'] and
                previous['settlement']['sequence']==(104 if reviewed is None else m['sequence']-1),'Accepted predecessor changed')
        prior_detail=load_large(slot,previous['detailRef'])
        prior_states=load_large(slot,prior_detail['stateRef'])
        prior_root=root/'prior-state';prior_root.mkdir();check_states(prior_states,prior_root)
        for kind,file in [('cog','cache.sqlite'),('service','requests.sqlite')]:
            destination=root/('working-'+kind);destination.mkdir()
            shutil.copyfile(prior_root/(kind+'.sqlite'),destination/file)
        if plan.get('completionPhase'):
            pins=recover_usgs_ledger(root/'working-cog/cache.sqlite',root/'working-service/requests.sqlite',
                records,region,plan,m['uncertainJobIDs'])
        else:
            pins=merge_pins(root/'working-cog/cache.sqlite',records,region)
        states=state_snapshot(root);state_ref=save_large(slot,states)
        require(load_large(slot,state_ref)==states,'Recovered state readback mismatch')
        verify_state=root/'verified-state';verify_state.mkdir();check_states(states,verify_state)
        parts=assemble(slot,records,root)
        from rrgh_verified_tile_catalog import catalog
        qa.update(sourceLedgerVerification=pins,parts=parts,regionComplete=False)
        qa['verifiedTileCatalog']=catalog(plan,region,records,m['completedJobRefs'],qa,parts,root)
        qa['verifiedTileCatalogStatus']='verified'
        qaref=save_large(slot,qa)
        usage=[r['result']['originalReceipt']['execution']['sourceUsage']['actual'] for r in records]
        detail=dict(completedJobReceipts=m['completedJobRefs'],stateRef=state_ref,
            sourceBytesReceived=sum(u['receivedBodyBytes'] for u in usage),sourceRequests=sum(u['operations'] for u in usage),
            outputBytes=qa['bytes'],seconds=None,sourcePixelGapJobs=[],pixelGapAttemptsConsumed=0,
            rawCachePolicy=plan['cachePolicy'],incompleteProducerLedger=True,uncertainJobIDs=m['uncertainJobIDs'],
            allUnknownAttemptsRetained=True,sourcePinsReconstructed=pins,priorStateRef=prior_detail['stateRef'])
        detailref=save_large(slot,detail)
        # Producer usage is unknown: retain its entire reservation, and the
        # settlement retains every dimension of the entire failed wave.
        used=add_usage(boot['used'],plan['slots'][1],slot.meter.used)
        ledger=settle(plan,used,False)
        carry=dict(chargedUSD=ledger['chargedUSD'],storedBytes=ledger['storedBytes'],
            priorCompletedJobs=plan['campaign']['carry']['priorCompletedJobs']+qa['jobs'],
            priorRasterTiles=plan['campaign']['carry']['priorRasterTiles']+qa['files'],priorSunlightAssets=320)
        result=dict(status='partial-verified',salvage=('wave105-missing-producer-closure-v1' if reviewed is None else m['format']),
            originalProducerRunID=m['originalRunID'],producerClaim=m['producerClaim'],workerReceipt=None,
            completedJobRefs=m['completedJobRefs'],completedJobIDs=m['completedJobIDs'],uncertainJobIDs=m['uncertainJobIDs'],
            jobs=qa['jobs'],tiles=qa['files'],outputBytes=qa['bytes'],qaRef=qaref,detailRef=detailref,
            packageParts=len(parts),packageBytes=sum(p['byteCount'] for p in parts),adjacentEdgesMeasured=len(qa['seams']),
            bootstrapReceipt=asdict(bootref),settlement=ledger,nextCarry=carry,
            sourcePixelGapJobs=[],pixelGapAttemptsConsumed=0,allOutputHashesAndPixelsVerified=True,
            allNewPackageChunksReadBack=True,allExistingCachesPreserved=True,sourcePinsReconstructed=pins,
            sourceJobsExecuted=0,verifiedTileCatalogTiles=qa['verifiedTileCatalog']['tileCount'],
            producerUsageMeasured=False,unacceptedAttemptsQuarantined=True)
        require_owner(plan,'recovery')
        ref=slot.finish(result)
        emit(phase='independent-checkpoint-salvage',receiptRef=asdict(ref),result=result,gcsIncludingReceipt=opener.summary())
    except Exception as error:
        if not slot.closed:
            try:slot.finish(dict(status='failed',allWaveAllocationsRetained=True,errorClass=type(error).__name__))
            except Exception:pass
        raise


if __name__=='__main__':run(sys.argv[1])
