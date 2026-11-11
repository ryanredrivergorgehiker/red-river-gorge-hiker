"""Exact owner-authorized forward recovery of the unstarted final raster pilot."""
import argparse,base64,copy,json,os,subprocess,sys,zlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
import rrgh_dispatcher as d
import rrgh_final_overviews  # Bind trusted controller selectors before source imports.
from rrgh_seed_bootstrap_recovery import FAILED_SOURCE,FAILED_PLAN,FAILED_RUN,FAILED_REF,MARKER
ROOT=Path(__file__).resolve().parents[2]
OLD_FOLDER='backend/config/gorge-campaign-wave-1453-20261102'
NEW_FOLDER='backend/config/gorge-campaign-wave-1454-20261102'
MODULES=('rrgh_seed_children.py','rrgh_final_overviews.py','rrgh_final_overview_render.py','rrgh_seed_bootstrap_recovery.py')

def audit(api,root,expiry=None):
    d.caller('launch');_,s=api.state();d.validate_state(s,root)
    d.guard(s['status']=='halted' and s['mode']=='produce' and s['sequence']==1453 and s['runID']==FAILED_RUN and
        s['sourceSHA']==FAILED_SOURCE and s['planSHA256']==FAILED_PLAN,'Exact halted bootstrap owner required')
    d.assert_no_other_producers(api)
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==FAILED_SOURCE,'Source lease moved')
    from rrgh_salvage_audit import one,reports
    from rrgh_dispatch_audit import gh
    original=d.read_audit_run(api,FAILED_RUN)
    d.guard(original['status']=='completed' and original['conclusion']=='failure' and original['run_attempt']==1 and
        original['head_branch']==d.WORKER and original['event']=='workflow_dispatch' and original['actor']['login']=='github-actions[bot]',
        'Original failed run identity changed')
    jobs=api.call('GET',f'actions/runs/{FAILED_RUN}/jobs?per_page=100')
    d.guard(jobs['total_count']==len(jobs['jobs']) and one(jobs['jobs'],'bounded-stage')['conclusion']=='failure' and
        one(jobs['jobs'],'independent-recovery')['conclusion']=='skipped','Original worker closure changed')
    inspection=s['inspectionHistory'][-1];rid=inspection['runID']
    d.guard(inspection['sourceRunID']==FAILED_RUN and inspection['cloudWrites']==0,'Exact failure inspection required')
    run=d.read_audit_run(api,rid)
    d.guard(run['status']=='completed' and run['conclusion']=='success' and run['run_attempt']==1 and
        run['head_branch']==d.WORKER and run['path']=='.github/workflows/'+d.WORKFLOW and
        run['actor']['login']=='github-actions[bot]','Live seed preflight did not pass')
    jobs=api.call('GET',f'actions/runs/{rid}/jobs?per_page=100')
    d.guard(jobs['total_count']==len(jobs['jobs']),'Incomplete inspection job list')
    job=one(jobs['jobs'],'checkpoint-inspection');d.guard(job['conclusion']=='success','Seed inspection failed')
    log=gh('actions/jobs/'+str(job['id'])+'/logs',api.token,raw=True)
    rows=[r for r in reports(log.splitlines()) if r.get('phase')=='checkpoint-inspection']
    d.guard(len(rows)==1,'One complete exact inspection required');report=rows[0];proof=report.get('seedReaderPreflight',{})
    d.guard(report['planSHA256']==FAILED_PLAN and report['sequence']==1453 and report['cloudWrites']==report['sourceRequests']==0 and
        report['readRequests']<=64 and report['readResponseBytes']<=8*2**20 and proof.get('status')=='verified' and
        proof['jobs']==44 and proof['rasterTiles']==436 and len(proof['samples'])==4 and
        all(x['pixelsVerified'] for x in proof['samples']),'Historical reader has not passed its real-record preflight')
    objects={o['key']:o for o in report['objects']};prefix='engineering/map-production/plans/'+FAILED_PLAN+'/slots/'
    failed=objects[prefix+'00000/receipt.json']
    d.guard(failed['exists'] and failed['ref']==FAILED_REF and failed['record']['result']['status']=='failed' and
        failed['record']['used']['attempts']==0,'Failed bootstrap evidence changed')
    d.guard(all(not o['exists'] for key,o in objects.items() if key.startswith(prefix+'00001/') or key.startswith(prefix+'00002/')),
        'A raster or recovery slot was already started')
    old=json.loads(api.file(OLD_FOLDER+'/PLAN.json',ref=FAILED_SOURCE)[1])
    d.guard(d.digest(d.canonical(old))==FAILED_PLAN and s['lastRecovered']['sequence']==1452 and
        s['lastRecovered']['acceptedRasterTiles']==277587 and s['checkpoint']==old['campaign']['previousRecovery'],
        'Accepted predecessor or original plan changed')
    expiry=expiry or (datetime.now(timezone.utc)+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    expires=datetime.fromisoformat(expiry.replace('Z','+00:00'))
    d.guard(datetime.now(timezone.utc)<expires<datetime.now(timezone.utc)+timedelta(days=8),'Fresh bounded expiry required')
    return dict(format='rrgh-seed-resume-audit-v1',sourceSHA=FAILED_SOURCE,planSHA256=FAILED_PLAN,
        failedRunID=FAILED_RUN,inspectionRunID=rid,inspectionJobID=job['id'],inspectionLogSHA256=d.digest(log.encode()),
        checkpoint=s['checkpoint'],expiresAt=expiry,marker=MARKER)

def head(root,path):return subprocess.check_output(['git','-C',str(root),'show','HEAD:'+path])

def candidate(root,verified):
    root=Path(root).resolve()
    d.guard(subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==FAILED_SOURCE and
        verified['sourceSHA']==FAILED_SOURCE and verified['planSHA256']==FAILED_PLAN and verified['marker']==MARKER,
        'Exact failed source and audit required')
    old=json.loads(head(root,OLD_FOLDER+'/PLAN.json'));env=json.loads(head(root,OLD_FOLDER+'/ALLOWANCE.json'))
    region=json.loads(zlib.decompress(base64.b64decode(head(root,OLD_FOLDER+'/REGION-PLAN.json.z.b64'))))
    sys.path.insert(0,str(root/'backend/scripts'))
    from rrgh_seed_bootstrap_recovery import carry,validate
    from rrgh_final_overviews import select,validate_plan,validate_history,POLICY
    from gorge_campaign_budget import cost,admit
    code=head(root,'backend/scripts/gorge_campaign.py').decode()
    d.guard(d.digest(code.encode())=='80de4ff06db3e7a8afbcfdc3c0343659178c2a6adcabdb00f94c2ba6dc31d004','Failed source engine changed')
    from rrgh_seed_bootstrap_recovery import PREDECESSOR_BLOCK as block,PREDECESSOR_PATCH as replacement
    d.guard(code.count(block)==1,'Exact predecessor check missing')
    code=code.replace(block,replacement).replace("config/gorge-campaign-wave-1453-20261102'","config/gorge-campaign-wave-1454-20261102'")
    files={'backend/scripts/gorge_campaign.py':code.encode()}
    for name in MODULES:files['backend/scripts/'+name]=(ROOT/'.github/automation'/name).read_bytes()
    plan=copy.deepcopy(old);plan['seedBootstrapRecovery']=copy.deepcopy(MARKER)
    plan['campaign'].update(sequence=1454,carry=carry(old));plan['expiresAt']=verified['expiresAt']
    selected,phase=select(plan['completedJobIDs'],plan['priorAttemptCounts'],plan['crosswaveHistory'],plan['nativeRepairHistory'],[])
    d.guard([j['id'] for j in selected]==old['approvedJobIDs'],'Unstarted four-parent pilot changed')
    plan['finalOverviewPhase']=phase
    for name in ('gorge_campaign.py',*MODULES):region['engineHashes'][name]=d.digest(files['backend/scripts/'+name])
    plan['regionPlanSHA256']=d.digest(d.canonical(region))
    names=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','--name-only','HEAD','backend/scripts'],text=True).splitlines()
    hashes={Path(p).name:d.digest(files[p] if p in files else head(root,p)) for p in names if Path(p).parent==Path('backend/scripts') and p.endswith('.py') and not Path(p).name.startswith('test_')}
    hashes.update({Path(p).name:d.digest(raw) for p,raw in files.items()})
    plan['sourceSnapshotSHA256']=d.digest(d.canonical(hashes))
    env['cloudStorageAllowance'].update(planSHA256=d.digest(d.canonical(plan)),reservedWorstCaseUSD=str(cost(plan['limits'])))
    validate(plan,old);validate_plan(plan,region,POLICY);validate_history(plan,region);admit(plan,env)
    files.update({NEW_FOLDER+'/PLAN.json':d.canonical(plan),NEW_FOLDER+'/ALLOWANCE.json':d.canonical(env),
        NEW_FOLDER+'/REGION-PLAN.json.z.b64':base64.b64encode(zlib.compress(d.canonical(region),9))})
    return files,plan

def prepare(root,verified):
    files,plan=candidate(root,verified)
    for path,raw in files.items():
        target=Path(root)/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    return dict(prepared=True,sequence=1454,jobs=4,acceptedRasterTiles=277587,remainingRasterTiles=691,
        planSHA256=d.digest(d.canonical(plan)),carry=plan['campaign']['carry'])

def publish(api,root,source,verified):
    d.guard(audit(api,root,verified['expiresAt'])==verified,'Live seed recovery audit changed')
    files,plan=candidate(source,verified)
    changed=subprocess.check_output(['git','-C',str(source),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
    d.guard(set(changed)==set(files) and all((Path(source)/p).read_bytes()==raw for p,raw in files.items()),'Source differs from exact reviewed recovery')
    old,state=api.state();d.validate_state(state,root);d.assert_no_other_producers(api)
    d.guard(state['sourceSHA']==FAILED_SOURCE and state['status']=='halted' and state['runID']==FAILED_RUN,'Recovery lease moved')
    base=api.call('GET','git/commits/'+FAILED_SOURCE)
    tree=api.call('POST','git/trees',{'base_tree':base['tree']['sha'],'tree':[dict(path=p,mode='100644',type='blob',content=raw.decode()) for p,raw in files.items()]})
    commit=api.call('POST','git/commits',{'message':'Retain failed seed bootstrap and prepare fresh verified-input wave1454 [skip ci]','tree':tree['sha'],'parents':[FAILED_SOURCE]})
    saved=dict(runID=FAILED_RUN,sequence=1453,sourceSHA=FAILED_SOURCE,planSHA256=FAILED_PLAN,
        originalDispatchID=state['dispatchID'],audit=verified,successorSHA=commit['sha'],successorPlanSHA256=d.digest(d.canonical(plan)))
    state.update(status='seed-resume-publishing',seedBootstrapPublication=saved)
    old=api.cas(old,state,'retain failed bootstrap before exact fresh source publication')
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==FAILED_SOURCE,'Source lease moved before publication')
    api.call('PATCH','git/refs/heads/'+d.SOURCE,{'sha':commit['sha'],'force':False})
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==commit['sha'],'Source publication readback differs')
    state.setdefault('seedBootstrapRecoveryHistory',[]).append(state.pop('seedBootstrapPublication'))
    state.update(status='ready',sourceSHA=commit['sha'],planSHA256=d.digest(d.canonical(plan)),sequence=1454,runID=None,dispatchID=None)
    old=api.cas(old,state,'fresh allocation prepared; all prior cost and accepted inventory retained')
    return d.dispatch(api,root,old,state,'produce')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['audit','prepare','publish']);p.add_argument('--source');p.add_argument('--audit',required=True);a=p.parse_args()
    path=Path(a.audit)
    if a.mode=='audit':
        result=audit(d.GitHub(os.environ['GH_TOKEN']),ROOT);path.write_bytes(d.canonical(result))
    elif a.mode=='prepare':result=prepare(a.source,json.loads(path.read_bytes()))
    else:result=publish(d.GitHub(os.environ['GH_TOKEN']),ROOT,a.source,json.loads(path.read_bytes()))
    print(json.dumps(result,sort_keys=True))
