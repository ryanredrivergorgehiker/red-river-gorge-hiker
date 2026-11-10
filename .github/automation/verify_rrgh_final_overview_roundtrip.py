"""Synthetic complete-native settlement ->691 final parents -> package hold.

Input is the finite native queue QA checkout, never a live production checkout.
"""
import base64,copy,hashlib,json,os,subprocess,sys,tempfile,zlib
from decimal import Decimal
from pathlib import Path
import rrgh_dispatcher as d
import rrgh_native_batch as n
import rrgh_final_overviews as f
from rrgh_dispatch_audit import audit_run
from rrgh_expanded_production import read_region

ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve();summary_path=Path(sys.argv[2]).resolve()
native_summary=json.loads(summary_path.read_bytes())
require=lambda ok,message:None if ok else (_ for _ in ()).throw(AssertionError(message))
require(native_summary['acceptedRasterTiles']==277587 and native_summary['remainingNativeRasterTiles']==0,
    'Complete synthetic native test fixture required')
raw=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1419-audit-input.json.z.b64').read_bytes())))
audit=audit_run(raw['run'],raw['jobs'],raw['recovery'],raw['producer'],expected_dispatch=raw['state'])
for key in ('completionPolicy','crosswavePolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled'):audit[key]=raw['state'][key]
audit['nativeRepairPolicy']=n.POLICY;audit['finalOverviewPolicy']=f.POLICY
folder,old,_=d.config(source);region=read_region(folder)
sys.path.insert(0,str(source/'backend/scripts'))
from gorge_campaign_budget import cost
ids=old['approvedJobIDs'];tiles=sum(len(j['outputTiles']) for j in region['jobs'])
require(native_summary['planSHA256']==d.digest(d.canonical(old)),'Synthetic native fixture identity mismatch')
audit.update(wave=old['campaign']['sequence'],planSHA256=native_summary['planSHA256'],jobsNew=len(ids),tilesNew=tiles,
    acceptedJobs=len(old['completedJobIDs'])+len(ids),acceptedRasterTiles=277587,
    sourcePixelGapJobs=[],sourceCompletedJobIDs=[],receiptRef=native_summary['recoveryReceipt'],
    receiptSHA256=native_summary['recoveryReceipt']['sha256'])
audit['nextCarry']=copy.deepcopy(old['campaign']['carry'])
audit['nextCarry'].update(priorCompletedJobs=audit['acceptedJobs'],priorRasterTiles=277587,
    chargedUSD=str(Decimal(old['campaign']['carry']['chargedUSD'])+cost(old['limits'])),
    storedBytes=old['campaign']['carry']['storedBytes']+tiles*512*1024)
seen=set();waves=0;mutations=0
while True:
    parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'audit.json';path.write_text(json.dumps(audit))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),
            str(source),str(path)],check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    if (source/'RRGH-COMPLETION-WAIT.json').exists():break
    state=dict(sourceSHA=parent,planSHA256=audit['planSHA256'],sequence=audit['wave'],epoch=1)
    _,sha,plan,entries=d.candidate_entries(source,audit,state)
    folder,_,_=d.config(source);region=read_region(folder)
    f.validate_plan(plan,region,f.POLICY);f.validate_history(plan,region)
    ids=plan['approvedJobIDs'];require(not seen.intersection(ids),'Repeated final overview')
    require(all(plan['priorAttemptCounts'].get(j,0)==0 for j in ids),'Consumed final overview replayed')
    require(plan['campaign']['sourcePixelGapQuarantines']==old['campaign']['sourcePixelGapQuarantines'],'Native quarantine history changed')
    if waves==0:
        bindings=f.expand(plan['finalOverviewPhase'])
        require(len(ids)==4 and any(len(b['children'])<4 for b in bindings) and
            any(c['source'].get('acceptanceKind')=='accepted-seed-authority-v1' for b in bindings for c in b['children']),
            'The first pilot must exercise actual seed and edge dependencies')
        for fault in ('missing_child','extra_child','seed_authority','native_history','native_attempt',
            'parent_attempt','bounds','read_allowance','accepted_drop'):
            bad=copy.deepcopy(plan);bad_region=copy.deepcopy(region)
            if fault=='missing_child':bad['finalOverviewPhase']['dependencies'][ids[0]].pop()
            elif fault=='extra_child':bad['finalOverviewPhase']['dependencies'][ids[0]].append(copy.deepcopy(bad['finalOverviewPhase']['dependencies'][ids[0]][0]))
            elif fault=='seed_authority':bad['finalOverviewPhase']['sources']['seed:'+f.SEED_SHA]['authoritySHA256']='f'*64
            elif fault=='native_history':bad['nativeRepairHistory'].pop()
            elif fault=='native_attempt':bad['priorAttemptCounts'][n.pilot.JOBS[0]]=1
            elif fault=='parent_attempt':bad['priorAttemptCounts'][ids[0]]=1
            elif fault=='bounds':bad_region['boundsWGS84'][0]-=.01
            elif fault=='read_allowance':bad['slots'][0]['classBRequests']-=1
            else:bad['completedJobIDs'].pop(0)
            try:f.validate_publication(old,read_region(source/'backend/config'/('gorge-campaign-wave-'+str(old['campaign']['sequence'])+'-20261102')),bad,bad_region,audit)
            except ValueError:mutations+=1
            else:raise AssertionError('Unsafe final overview accepted: '+fault)
        if '--first-only' in sys.argv:
            print(json.dumps(dict(smokeVerified=True,unsafeMutationsRejected=mutations,pilot=ids,liveProduction=False)))
            raise SystemExit(0)
    subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid',
        'commit','-qm','SYNTHETIC final overview fixture'],check=True)
    count=len(ids);seen.update(ids);waves+=1
    audit.update(wave=plan['campaign']['sequence'],planSHA256=sha,jobsNew=count,tilesNew=count,
        acceptedJobs=len(plan['completedJobIDs'])+count,acceptedRasterTiles=plan['campaign']['carry']['priorRasterTiles']+count,
        receiptRef=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/receipt.json',
            bytes=2000,generation=str(90000+plan['campaign']['sequence']),sha256='a'*64),receiptSHA256='a'*64)
    audit['nextCarry']=copy.deepcopy(plan['campaign']['carry'])
    audit['nextCarry'].update(priorCompletedJobs=audit['acceptedJobs'],priorRasterTiles=audit['acceptedRasterTiles'],
        chargedUSD=str(Decimal(plan['campaign']['carry']['chargedUSD'])+cost(plan['limits'])),
        storedBytes=plan['campaign']['carry']['storedBytes']+count*512*1024)
    audit['overviewPilotVerification']=dict(format=f.VERIFY,phaseSHA256=f.digest(plan['finalOverviewPhase']),planSHA256=sha,
        allChildrenHashAndPixelVerified=True,allParentsIndependentlyRecomputed=True,
        allCoverageMasksVerified=True,seedAuthoritySHA256=f.SEED_SHA,priorChildrenUnmodified=True,
        sourceQualityUnchanged=True,officialSourceRequests=0,
        parents=[dict(job=j,outputSHA256='b'*64,outputBytes=4096) for j in ids],
        detailRef=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/indexes/'+'c'*64,
            bytes=4096,generation=str(100000+audit['wave']),sha256='c'*64),detailSHA256='c'*64)
    print(json.dumps(dict(syntheticWave=audit['wave'],tiles=count,accepted=audit['acceptedRasterTiles'],
        cumulativeFullAllocationUSD=audit['nextCarry']['chargedUSD'],liveProduction=False)),flush=True)
    require(waves<=20,'Final queue did not converge')
summary=json.loads((source/'RRGH-COMPLETION-WAIT.json').read_bytes())
require(len(seen)==691 and summary['acceptedRasterTiles']==278278 and summary['remainingRasterTiles']==0 and
    summary['fullRasterCoverageComplete'] is True and summary['finalPackageDeliveryComplete'] is False,
    'Raster completion or package boundary incorrect')
require(summary['nativeRepairSettlements']==native_summary['nativeRepairSettlements'],'Native acceptance history changed')
print(json.dumps(dict(verified=True,syntheticWaves=waves,overviewTiles=len(seen),rasterTiles=278278,
    fullAllocationChargeUSD=audit['nextCarry']['chargedUSD'],unsafeMutationsRejected=mutations,
    packageDeliveryStillRequired=True,liveProduction=False)))
