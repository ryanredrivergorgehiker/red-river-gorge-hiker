"""Actual failed-source forward recovery -> all691 final parents, without Cloud writes."""
import base64,copy,json,os,subprocess,sys,tempfile,zlib
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import rrgh_dispatcher as d
import rrgh_final_overviews as f
import rrgh_seed_resume as resume
import rrgh_seed_bootstrap_recovery as recovery
from rrgh_expanded_production import read_region
ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve()
require=lambda ok,message:None if ok else (_ for _ in ()).throw(AssertionError(message))
verified=dict(sourceSHA=recovery.FAILED_SOURCE,planSHA256=recovery.FAILED_PLAN,marker=recovery.MARKER,
    expiresAt=(datetime.now(timezone.utc)+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ'))
old=json.loads((source/resume.OLD_FOLDER/'PLAN.json').read_bytes())
files,plan=resume.candidate(source,verified)
for fault in ('allocation','accepted','attempt','marker','previous'):
    bad=copy.deepcopy(plan)
    if fault=='allocation':bad['campaign']['carry']['chargedUSD']=old['campaign']['carry']['chargedUSD']
    elif fault=='accepted':bad['completedJobIDs'].pop()
    elif fault=='attempt':bad['priorAttemptCounts'][bad['approvedJobIDs'][0]]=1
    elif fault=='marker':bad['seedBootstrapRecovery']['retainEntireFailedAllocation']=False
    else:bad['campaign']['previousRecovery']['sha256']='f'*64
    try:recovery.validate(bad,old)
    except ValueError:pass
    else:raise AssertionError('Unsafe recovery accepted: '+fault)
from rrgh_recovery_catalog_integration import augment_campaign
augmented=augment_campaign(files['backend/scripts/gorge_campaign.py'].decode())
try:augment_campaign(augmented.replace("c['sequence']==1454", "c['sequence']>=1454"))
except ValueError:pass
else:raise AssertionError('Unreviewed recovery engine accepted')
resume.prepare(source,verified)
subprocess.run([sys.executable,str(source/'backend/scripts/gorge_campaign.py'),'--phase','plan'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['git','-C',str(source),'add',*files],check=True)
subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC seed recovery fixture'],check=True)
sys.path.insert(0,str(source/'backend/scripts'))
from gorge_campaign_budget import cost
state=json.loads((ROOT/'.github/automation/rrgh-controller-state.json').read_bytes())
from rrgh_dispatch_audit import audit_run
raw=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1419-audit-input.json.z.b64').read_bytes())))
audit=audit_run(raw['run'],raw['jobs'],raw['recovery'],raw['producer'],expected_dispatch=raw['state'])
audit.update({k:state[k] for k in ('completionPolicy','crosswavePolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled','nativeRepairPolicy','finalOverviewPolicy')})
audit.update(verified=True,sourcePixelGapJobs=[],sourceCompletedJobIDs=[],partial=False)
seen=set();waves=0
while True:
    folder,plan,_=d.config(source);region=read_region(folder)
    sha=d.digest(d.canonical(plan));ids=plan['approvedJobIDs']
    require(not seen.intersection(ids),'Repeated accepted overview')
    require(plan['seedBootstrapRecovery']==recovery.MARKER,'Failed allocation history lost')
    f.validate_plan(plan,region,f.POLICY);f.validate_history(plan,region)
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
    parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'audit.json';path.write_text(json.dumps(audit))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),str(source),str(path)],check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    if (source/'RRGH-COMPLETION-WAIT.json').exists():break
    current=dict(sourceSHA=parent,planSHA256=sha,sequence=plan['campaign']['sequence'],epoch=1)
    _,_,_,entries=d.candidate_entries(source,audit,current)
    subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC seed successor fixture'],check=True)
summary=json.loads((source/'RRGH-COMPLETION-WAIT.json').read_bytes())
require(len(seen)==691 and summary['acceptedRasterTiles']==278278 and summary['remainingRasterTiles']==0 and summary['fullRasterCoverageComplete'] is True and summary['finalPackageDeliveryComplete'] is False,'Raster completion boundary incorrect')
print(json.dumps(dict(verified=True,syntheticWaves=waves,overviewTiles=len(seen),rasterTiles=278278,fullAllocationChargeUSD=audit['nextCarry']['chargedUSD'],packageDeliveryStillRequired=True,liveProduction=False)))
