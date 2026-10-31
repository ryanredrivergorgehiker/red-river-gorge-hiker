#!/usr/bin/env python3
"""Two fresh one-shot slots salvage Wave011 checkpoints; no source rendering."""
import argparse,base64,json,os,tempfile,zlib
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from gorge_checkpoint import GCS,Slot,Ref,canonical,digest,decode_record,require_live_allowance
from gorge_campaign_budget import cost,monthly,RATES,CAMPAIGN,APPROVAL
from gorge_second_stage import record,recover_catalogs
from gorge_stage_coordinator import verify_outputs
from gorge_campaign import load_large,check_states
from run_gorge_checkpoint_slot import token,code_snapshot

SRC=Path(__file__).resolve().parent
CFG=SRC.parent/'config/gorge-wave011-recovery-only-20261030'
OLD=SRC.parent/'config/gorge-campaign-wave-011-20261030'
OLD_SHA='03edea40b63ad8d937064e10f7b221445a55da1fa87f7689657a70efab3d96eb'
PRODUCER=Ref('engineering/map-production/plans/'+OLD_SHA+'/slots/00001/receipt.json',
 '1793401709392186',728,'eaf01977e64789af249b51e12046a6007613ace8523271716fc8921455d0920c')
BOOT=Ref('engineering/map-production/plans/'+OLD_SHA+'/slots/00000/receipt.json',
 '1793401291750355',622,'ddf341a8a99175c0f9ed6b6901359dc0baf6c709834dc8c5fde0893d20ebabea')
EXPECTED_PART_SHA=('247c2d59314e24491c6a648014bc4fe882ee3991260a05bf6fe10761c8fad997',
                   '9fdbc0c659a64148788e4386715df46bfe0fae66e21962712b1ef77d6836b8ba')

def source():
    old=json.loads((OLD/'PLAN.json').read_bytes())
    d=zlib.decompressobj()
    raw=d.decompress(base64.b64decode((OLD/'REGION-PLAN.json.z.b64').read_bytes()),8*2**20)
    if not d.eof or d.unused_data or d.unconsumed_tail:raise ValueError('Old region bounds')
    region=json.loads(raw)
    if digest(canonical(old))!=OLD_SHA or digest(canonical(region))!=old['regionPlanSHA256']:
        raise ValueError('Old source pin')
    assert old['campaign']['sequence']==11 and len(old['completedJobIDs'])==1146
    assert old['campaign']['carry']['priorRasterTiles']==11362
    assert len(old['approvedJobIDs'])==128
    assert all(j.startswith('usgs-topo-16-') for j in old['approvedJobIDs'][:64])
    return old,region

def validate():
    p=json.loads((CFG/'PLAN.json').read_bytes())
    e=json.loads((CFG/'ALLOWANCE.json').read_bytes())
    old,region=source()
    require_live_allowance(p,e)
    if (p['purpose']!='wave011-checkpoint-salvage-only'
       or p['sourceSnapshotSHA256']!=code_snapshot(SRC)
       or p['approvedJobIDs']!=old['approvedJobIDs'][:64]
       or p['completedJobIDs']!=old['completedJobIDs']
       or p['priorAttemptCounts']!=old['priorAttemptCounts']
       or p['slotJobs'] or p['originalPlanSHA256']!=OLD_SHA
       or p['originalProducer']!=asdict(PRODUCER)
       or p['originalBootstrap']!=asdict(BOOT)
       or p['automaticRetryPermitted'] is not False
       or p['maxConcurrency']!=1 or len(p['slots'])!=2
       or any(p['limits'][k] for k in ('attempts','sourceBytes','sourceRequests'))):
        raise ValueError('Recovery-only source boundary')
    if e['planningRates']!=RATES:raise ValueError('Planning rates changed')
    charge=cost(p['limits'])
    c=p['campaign']
    assert c['id']==CAMPAIGN and c['ownerApproval']==APPROVAL
    assert c['chargedConservativeCarryUSD']=='5.658803284343367815017700196'
    assert c['storedConservativeCarryBytes']==12797880214
    if (charge>Decimal('.02') or Decimal(e['cloudStorageAllowance']['approvedUSD'])!=Decimal('.02')
        or Decimal(c['chargedConservativeCarryUSD'])+charge>Decimal('23')
        or monthly(c['storedConservativeCarryBytes']+p['limits']['storedBytes'])>1):
        raise ValueError('Recovery budget reserve breached')
    return p,e,old,region,charge

def original_records(slot,p,old,region,root):
    producer=decode_record(slot.get(PRODUCER))
    bootstrap=decode_record(slot.get(BOOT))
    assert producer['planSHA256']==bootstrap['planSHA256']==OLD_SHA
    assert producer['slot']==1 and bootstrap['slot']==0
    assert producer['result']['status']=='failed' and producer['result']['jobs']==64
    assert bootstrap['result']['status']=='ready'
    detail=load_large(slot,producer['result']['detailRef'])
    assert len(detail['completedJobReceipts'])==64 and not detail['sourcePixelGapJobs']
    rows=[record(slot,r,'rrgh-checkpoint-job-v1') for r in detail['completedJobReceipts']]
    assert [r['job'] for r in rows]==p['approvedJobIDs']
    assert all(r['slot']==1 and r['planSHA256']==OLD_SHA for r in rows)
    catalogs=[c for r in rows for c in r['result']['outputPacks']]
    paths=[e['path'] for c in catalogs for e in c['members']]
    assert len(paths)==len(set(paths))==64
    recover_catalogs(slot,catalogs,paths,root/'outputs')
    initial=load_large(slot,bootstrap['result']['bootstrapDataRef'])
    assert not [e for c in initial['neighbors'] for e in c['members']]
    qa=verify_outputs(old,region,rows,root/'outputs',None)
    assert qa['jobs']==qa['files']==64 and qa['adjacentEdgesMeasured']==44
    assert qa['pixelsDecoded'] and qa['gridAndAlphaVerified']
    (root/'state').mkdir()
    states=check_states(load_large(slot,detail['stateRef']),root/'state')
    assert states['ledgers']==2 and states['hashesAndSQLiteVerified']
    return rows,qa

def package_parts(rows,root):
    from build_gorge_map_bundles import PROFILE,partition,write_part
    groups={g:[] for g in PROFILE}
    for row in rows:
        for entry in row['result']['originalReceipt']['outputs']:
            f=entry['path'].split('/')
            group=next(g for g,v in PROFILE.items() if f[1] in v)
            groups[group].append({**entry,'source':str(root/'outputs'/entry['path']),
                'layer':f[1],'z':int(f[2]),'x':int(f[3]),'y':int(Path(f[4]).stem)})
    parts=[]
    for group,entries in groups.items():
        if not entries:continue
        folder=root/'parts'/group
        folder.mkdir(parents=True)
        for batch in partition(group,entries):
            meta=write_part(group,batch,folder)
            raw=(folder/meta['file']).read_bytes()
            parts.append({'group':group,'fileCount':meta['fileCount'],
                          'byteCount':len(raw),'sha256':digest(raw),'data':raw})
    assert len(parts)==2 and [p['sha256'] for p in parts]==list(EXPECTED_PART_SHA)
    assert [p['fileCount'] for p in parts]==[17,49]
    return parts

def stage(p,e,old,region,charge):
    slot=Slot(GCS(p,e,token),p,0,os.environ['GITHUB_RUN_ID'])
    try:
        root=Path(tempfile.mkdtemp(prefix='wave011-salvage-'))
        rows,qa=original_records(slot,p,old,region,root)
        parts=[]
        for part in package_parts(rows,root):
            ref=slot.put(part['data'],'outputs')
            assert slot.get(ref)==part['data']
            parts.append({k:v for k,v in part.items() if k!='data'}|{'ref':asdict(ref)})
        report={'status':'staged-verified','jobs':64,'tiles':64,'edges':44,
          'sourceProducer':asdict(PRODUCER),'sourceBootstrap':asdict(BOOT),
          'parts':parts,'allNewPackageChunksReadBack':True,'noSourceJobsExecuted':True}
        receipt=slot.finish(report)
        print(json.dumps({'phase':'recovery-only-stage','receiptRef':asdict(receipt),
                          'result':report},sort_keys=True),flush=True)
    except Exception:
        if not slot.closed:
            try:slot.finish({'status':'failed','allAllocationRetained':True})
            except Exception:pass
        raise

def independent(p,e,old,region,charge):
    slot=Slot(GCS(p,e,token),p,1,os.environ['GITHUB_RUN_ID'])
    try:
        firstref,first=slot.recover_receipt(0)
        report=first['result']
        assert report['status']=='staged-verified' and report['jobs']==64
        assert report['sourceProducer']==asdict(PRODUCER)
        root=Path(tempfile.mkdtemp(prefix='wave011-independent-'))
        rows,qa=original_records(slot,p,old,region,root)
        local=package_parts(rows,root)
        assert len(local)==len(report['parts'])==2
        for actual,prior in zip(local,report['parts']):
            assert actual['sha256']==prior['sha256'] and actual['fileCount']==prior['fileCount']
            assert actual['byteCount']==prior['byteCount']
            assert slot.get(Ref(**prior['ref']))==actual['data']
        result={'status':'verified','recoveryOnly':True,'sourceWave':11,
          'newlyAcceptedJobs':64,'newlyAcceptedTiles':64,
          'cumulativeAcceptedJobs':1210,'cumulativeAcceptedTiles':11426,
          'sunlightAssets':320,'quarantinedPriorAttempts':19,
          'ambiguousFirstLeafOnNotAccepted':True,
          'hashesPixelsEdgesSourceLedgersVerified':True,
          'packageChunksIndependentReadback':True,'parts':report['parts'],
          'sourceProducer':asdict(PRODUCER),'stageReceipt':asdict(firstref),
          'oldWaveProductionNotRepeated':True,'invoiceReading':False,
          'priorConservativeChargeUSD':p['campaign']['chargedConservativeCarryUSD'],
          'newRecoveryMaximumUSD':str(charge)}
        receipt=slot.finish(result)
        print(json.dumps({'phase':'recovery-only-independent','receiptRef':asdict(receipt),
                          'result':result},sort_keys=True),flush=True)
    except Exception:
        if not slot.closed:
            try:slot.finish({'status':'failed','allAllocationRetained':True})
            except Exception:pass
        raise

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['plan','stage','independent'],required=True)
    args=parser.parse_args()
    p,e,old,region,charge=validate()
    if args.phase=='plan':
        print(json.dumps({'phase':'verified-offline-recovery-only-plan',
          'planSHA256':digest(canonical(p)),'sourceJobs':64,'newSourceAttempts':0,
          'reserveUSD':str(charge),'cumulativeWorstUSD':str(
             Decimal(p['campaign']['chargedConservativeCarryUSD'])+charge)},sort_keys=True))
        return
    assert os.environ.get('GITHUB_RUN_ATTEMPT')=='1'
    assert os.environ.get('GITHUB_REPOSITORY')=='ryanredrivergorgehiker/red-river-gorge-hiker'
    assert os.environ.get('GITHUB_REF')=='refs/heads/lane20/offline-production-preflight-20261029'
    if args.phase=='stage':stage(p,e,old,region,charge)
    else:independent(p,e,old,region,charge)

if __name__=='__main__':main()
