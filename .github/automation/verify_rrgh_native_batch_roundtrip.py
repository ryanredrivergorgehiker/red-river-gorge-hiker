"""Actual1419 settlement -> mask-approved final attempts -> safe settled hold."""
import base64,copy,json,os,subprocess,sys,tempfile,zlib
from pathlib import Path
import rrgh_dispatcher as d
import rrgh_native_batch as b
from rrgh_dispatch_audit import audit_run
from rrgh_expanded_production import read_region

ROOT=Path(__file__).resolve().parents[2];source=Path(sys.argv[1]).resolve()
f=json.loads(zlib.decompress(base64.b64decode((ROOT/'.github/automation/fixtures/wave1419-audit-input.json.z.b64').read_bytes())))
audit=audit_run(f['run'],f['jobs'],f['recovery'],f['producer'],expected_dispatch=f['state'])
for k in ('completionPolicy','crosswavePolicy','sourcePolicyMode','overviewPilotEnabled','batchPilotEnabled'):audit[k]=f['state'][k]
audit['nativeRepairPolicy']=b.POLICY
original_dir,original,_=d.config(source)
assert d.digest(d.canonical(original))==b.BASELINE
original_bytes=(original_dir/'PLAN.json').read_bytes()

def prepare(a):
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'audit.json';p.write_text(json.dumps(a))
        subprocess.run([sys.executable,str(ROOT/'.github/automation/rrgh_prepare_dispatch_successor.py'),str(source),str(p)],
            check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})

def candidate(a):
    parent=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    prepare(a)
    if (source/'RRGH-COMPLETION-WAIT.json').exists():return None
    state=dict(sourceSHA=parent,planSHA256=a['planSHA256'],sequence=a['wave'],epoch=1)
    return d.candidate_entries(source,a,state)

def settlement(a,plan,sha,region,fail_last=False):
    x=copy.deepcopy(a);ids=plan['approvedJobIDs'];accepted=ids[:-1] if fail_last else ids
    tiles=sum(len(j['outputTiles']) for j in region['jobs'] if j['id'] in accepted)
    x.update(wave=plan['campaign']['sequence'],planSHA256=sha,jobsNew=len(accepted),tilesNew=tiles,
        acceptedJobs=len(plan['completedJobIDs'])+len(accepted),
        acceptedRasterTiles=plan['campaign']['carry']['priorRasterTiles']+tiles,
        sourcePixelGapJobs=ids[-1:] if fail_last else [],sourceCompletedJobIDs=accepted if fail_last else [])
    x['receiptRef']=dict(key='engineering/map-production/plans/'+sha+'/slots/00002/receipt.json',
        bytes=2000,generation=str(90000+x['wave']),sha256='a'*64)
    x['receiptSHA256']='a'*64
    x['nextCarry']['priorCompletedJobs']=x['acceptedJobs'];x['nextCarry']['priorRasterTiles']=x['acceptedRasterTiles']
    return x

seen=set();waves=0;mutation_cases=0;initial_count=len(b.masks())
while True:
    result=candidate(audit)
    if result is None:break
    _,sha,plan,entries=result;folder,_,_=d.config(source);region=read_region(folder)
    ids=plan['approvedJobIDs'];assert 0<len(ids)<=12 and not seen.intersection(ids)
    assert all(plan['priorAttemptCounts'][j]==1 for j in ids)
    assert plan['campaign']['sourcePixelGapQuarantines']==original['campaign']['sourcePixelGapQuarantines']
    b.validate_plan(plan,region,b.POLICY)
    if waves==0:
        for fault in ('attempt_reset','attempt_three','history_attempt','historical_ledger','quarantine','accepted_drop','history_receipt','mask_source','budget'):
            bad=copy.deepcopy(plan);r=copy.deepcopy(region)
            if fault=='attempt_reset':bad['priorAttemptCounts'][ids[0]]=0
            elif fault=='attempt_three':bad['priorAttemptCounts'][ids[0]]=2
            elif fault=='history_attempt':bad['priorAttemptCounts'][b.pilot.JOBS[0]]=1
            elif fault=='historical_ledger':bad['priorAttemptCounts'].pop(next(iter(original['priorAttemptCounts'])))
            elif fault=='quarantine':bad['campaign']['sourcePixelGapQuarantines'].remove(ids[0])
            elif fault=='accepted_drop':bad['completedJobIDs'].pop(0)
            elif fault=='history_receipt':bad['nativeRepairHistory'][0]['recoveryReceipt']['generation']='999'
            elif fault=='mask_source':r['jobs'][0]['sourceIDs'].reverse()
            else:bad['slots'][1]['sourceBytes']+=1
            try:b.validate_publication(original,read_region(original_dir),bad,r,audit)
            except ValueError:mutation_cases+=1
            else:raise AssertionError('Unsafe native batch accepted: '+fault)
    # A hypothetical failed last job must retain its final attempt and remain
    # unaccepted. This is a test only; it never becomes live evidence.
    hypothetical=settlement(audit,plan,sha,region,fail_last=True)
    accepted,attempts,history,index=b.advance(plan,region,hypothetical)
    assert ids[-1] not in accepted and attempts[ids[-1]]==2
    assert ids[-1] not in [j['id'] for j in b.select(index,accepted,attempts)]
    subprocess.run(['git','-C',str(source),'add',*[e['path'] for e in entries]],check=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=Offline QA','-c','user.email=offline-qa@example.invalid','commit','-qm','SYNTHETIC native repair batch fixture'],check=True)
    audit=settlement(audit,plan,sha,region);seen.update(ids);waves+=1
    assert waves<=60
summary=json.loads((source/'RRGH-COMPLETION-WAIT.json').read_bytes())
assert summary['nativeRepairSettlements'][0]['planSHA256']==b.BASELINE
assert len(seen)==initial_count and summary['acceptedRasterTiles']==audit['acceptedRasterTiles']
assert (original_dir/'PLAN.json').read_bytes()==original_bytes
changed=subprocess.check_output(['git','-C',str(source),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
assert changed==['RRGH-COMPLETION-WAIT.json'],changed
print(json.dumps(dict(verified='actual1419 through finite mask-verified native queue and settled hold',
    verifiedMaskJobs=initial_count,syntheticWaves=waves,unsafeMutationsRejected=mutation_cases,
    preservedAcceptedHistory=True,preservedBothAttempts=True,neverThirdAttempt=True,
    unchangedHistoricalQuarantines=True,unchangedResourceCeilings=True,liveProduction=False)))
