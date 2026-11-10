"""Finite completion of the691 remaining parents from immutable accepted children."""
import copy
import hashlib
import json
from rrgh_crosswave_batch import original_index,SOURCE_KEYS,TYPED_POLICY,fund,validate_funding
from rrgh_overview_coverage import child_positions,grid,inside,BOUNDS
from rrgh_seed_children import AUTHORITY as SEEDS,AUTHORITY_SHA as SEED_SHA

FORMAT='rrgh-final-overview-phase-v1'
DEPENDENCIES='rrgh-final-overview-dependencies-v1'
VERIFY='rrgh-final-overview-verification-v1'
POLICY=dict(format='rrgh-final-overview-authority-v1',enabled=True,
    authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-10',
    requiredRasterTiles=278278,nativeCompleteRasterTiles=277587,remainingOverviewTiles=691,
    nativeMaskManifestSHA256='5d057d172b4de609bdf34cd7529ffb596385cf8be10f31b5edf492ea8c4e01e5',
    seedAuthoritySHA256=SEED_SHA,maxJobs=128,pilotMaxJobs=4,
    preserveAcceptedOutputs=True,preserveConsumedAttempts=True,requireExactCoverageAlpha=True)
JOB_POLICY=dict(seconds=60,sourceBytes=0,sourceRequests=0)
LAYERS=('hiking','terrain','leaf-on','leaf-off')

def canonical(v):return (json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)

def children(job):
    layer,z,x,y=(job[k] for k in ('layer','z','x','y'))
    require(layer in LAYERS and type(z) is int and 10<=z<=15 and
        type(x) is int and type(y) is int and inside(z,x,y) and
        job==dict(id=f'{layer}-{z}-{x}-{y}',layer=layer,z=z,x=x,y=y,
            operation='overview',sourceIDs=[],outputTiles=[[z,x,y]]),'Exact final overview job required')
    return [f'{layer}-{cz}-{cx}-{cy}' for cz,cx,cy in child_positions(z,x,y)]

def source_map(accepted,crosswave_history,native_history,final_history):
    accepted=set(accepted);sources={};waves=[];unused_usgs=set()
    for wave in original_index()['waves']:
        kind=wave['acceptanceKind']
        if kind=='wave011-salvage':
            require(wave['sequence']==11 and len(wave['acceptedJobIDs'])==64 and
                all(j.startswith('usgs-topo-16-') for j in wave['acceptedJobIDs']),
                'Unreviewed historical salvage omitted from overview sources')
            unused_usgs.update(wave['acceptedJobIDs']);continue
        require(kind in TYPED_POLICY['acceptedReceiptKinds'],'Unsupported original acceptance kind')
        row={k:copy.deepcopy(wave[k]) for k in SOURCE_KEYS}
        if kind!='ordinary':row['acceptanceKind']=kind
        waves.append(row)
    waves+=copy.deepcopy(crosswave_history)
    for wave in native_history:
        require(wave['acceptanceKind']=='ordinary' and not wave['pixelGapJobIDs'] and
            wave['attemptedJobIDs']==wave['acceptedJobIDs'] and
            wave['sourceJobCount']==len(wave['acceptedJobIDs']),
            'Final overviews require fully accepted native repair settlements')
        waves.append(dict(sequence=wave['sequence'],sourcePlanSHA256=wave['planSHA256'],
            recovery=copy.deepcopy(wave['recoveryReceipt']),recipeSHA256=wave['recipeSHA256'],
            sourceJobCount=wave['sourceJobCount'],expectedTiles=wave['expectedTiles'],
            acceptedJobIDs=copy.deepcopy(wave['acceptedJobIDs'])))
    waves+=[{k:copy.deepcopy(row[k]) for k in SOURCE_KEYS} for row in final_history]
    for wave in waves:
        require(set(wave['acceptedJobIDs'])<=accepted,'An accepted child was removed')
        for jid in wave['acceptedJobIDs']:
            require(jid not in sources,'Ambiguous accepted child provenance')
            sources[jid]=wave
    seed_source=dict(acceptanceKind='accepted-seed-authority-v1',authoritySHA256=SEED_SHA)
    for jid in SEEDS['jobs']:
        require(jid in accepted and jid not in sources,'Seed acceptance missing or duplicated')
        sources[jid]=seed_source
    # USGS overviews are already complete and never inputs to these four
    # imagery/terrain layers. Their historical acceptance remains in the
    # pinned native baseline, without inventing an ordinary child receipt.
    require(set(sources)<=accepted and all(j.startswith('usgs-topo-') for j in accepted-set(sources)) and
        {j for j in accepted if j.rsplit('-',3)[0] in LAYERS}<=set(sources),
        'A required accepted child has no verified provenance')
    return sources

def source_key(source):
    return 'seed:'+SEED_SHA if source.get('acceptanceKind')=='accepted-seed-authority-v1' else source['sourcePlanSHA256']

def read_bounds(p):
    children_count=sum(len(v) for v in p['dependencies'].values())
    seed='seed:'+SEED_SHA in p['sources'];waves=len(p['sources'])-int(seed);jobs=len(p['jobs'])
    # Accepted seed inventory uses4 pinned base records and12 job records once
    # per slot; 4MiB bounds their known exact sizes with room for JSON framing.
    requests=3*waves+2*children_count+(16 if seed else 0)
    bytes_bound=waves*(16*1024+16*1024+256*1024)+children_count*(64*1024+512*1024)+(4*2**20 if seed else 0)
    return dict(dependencyRequests=requests,dependencyBytes=bytes_bound,
        bootstrapRequests=requests+96,recoveryRequests=requests+2*jobs+64,
        bootstrapBytes=bytes_bound+240*2**20)

def fits(p):
    b=read_bounds(p)
    return len(p['jobs'])<=128 and b['bootstrapRequests']<=1400 and b['recoveryRequests']<=1598 and b['bootstrapBytes']<=768*2**20

def select(accepted,attempts,crosswave_history,native_history,final_history,authority=POLICY):
    require(authority==POLICY,'Exact final overview authority required')
    sources=source_map(accepted,crosswave_history,native_history,final_history);done=set(accepted)
    pilot=not final_history
    p=dict(format=FORMAT,authority=copy.deepcopy(POLICY),pilot=pilot,jobs=[],sources={},dependencies={})
    candidates=[]
    native_jobs={j for row in native_history for j in row['acceptedJobIDs']}
    for z in range(15,9,-1):
        left,top,right,bottom=grid(z)
        for x,y in ((x,y) for x in range(left,right+1) for y in range(top,bottom+1)):
            for layer in LAYERS:
                job=dict(id=f'{layer}-{z}-{x}-{y}',layer=layer,z=z,x=x,y=y,
                    operation='overview',sourceIDs=[],outputTiles=[[z,x,y]])
                if job['id'] in done or attempts.get(job['id'],0):continue
                ids=children(job)
                if set(ids)<=done:candidates.append((job,ids))
    if pilot:
        # Exercise seed provenance, exact edge masks and repaired native
        # provenance in the first small allocation whenever already eligible.
        chosen=[]
        predicates=(lambda pair:any(j in SEEDS['jobs'] for j in pair[1]),
            lambda pair:len(pair[1])<4,
            lambda pair:any(j in native_jobs for j in pair[1]))
        for predicate in predicates:
            item=next((pair for pair in candidates if pair not in chosen and predicate(pair)),None)
            if item is not None:chosen.append(item)
        candidates=chosen+[pair for pair in candidates if pair not in chosen]
    for job,ids in candidates:
        trial=copy.deepcopy(p);trial['jobs'].append(job)
        trial['dependencies'][job['id']]=[dict(job=j,source=source_key(sources[j])) for j in ids]
        for j in ids:trial['sources'][source_key(sources[j])]=copy.deepcopy(sources[j])
        if not fits(trial):
            if p['jobs']:break
            raise ValueError('One final overview exceeds the existing read allowance')
        p=trial
        if len(p['jobs'])==(4 if pilot else 128):break
    if not p['jobs']:return [],None
    p['readBounds']=read_bounds(p)
    return p['jobs'],p

def expand(p):
    require(p.get('format')==FORMAT and p.get('authority')==POLICY and type(p.get('pilot')) is bool and
        p.get('readBounds')==read_bounds(p) and 0<len(p['jobs'])<=(4 if p['pilot'] else 128) and fits(p),
        'Final overview authority or funded envelope changed')
    require(set(p['dependencies'])=={j['id'] for j in p['jobs']},'Final dependency jobs differ')
    used=set();result=[]
    for job in p['jobs']:
        expected=children(job);bound=p['dependencies'][job['id']]
        require([v['job'] for v in bound]==expected,'Required in-map children changed')
        values=[]
        for v in bound:
            key=v['source'];source=p['sources'][key]
            require(source_key(source)==key,'Final child provenance key changed')
            if key.startswith('seed:'):
                require(source==dict(acceptanceKind='accepted-seed-authority-v1',authoritySHA256=SEED_SHA) and
                    v['job'] in SEEDS['jobs'],'Unreviewed seed child authority')
            used.add(key);values.append(dict(job=v['job'],source=copy.deepcopy(source)))
        result.append(dict(format=DEPENDENCIES,job=copy.deepcopy(job),children=values))
    require(used==set(p['sources']),'Unused final child authority')
    return result

def scope(plan,region,job=None):
    p=plan.get('finalOverviewPhase');bindings=expand(p);jobs=p['jobs'];done=set(plan['completedJobIDs'])
    require(region['jobs']==jobs and region['boundsWGS84']==list(BOUNDS) and
        plan['approvedJobIDs']==[j['id'] for j in jobs] and
        not any(plan.get(k) for k in ('crosswavePhase','nativeRepairPhase','overviewPilot','completionPhase','resumableBatch')) and
        plan['jobPolicies']=={j['id']:JOB_POLICY for j in jobs} and
        all(j['id'] not in done and plan['priorAttemptCounts'].get(j['id'],0)==0 for j in jobs) and
        all(c['job'] in done for b in bindings for c in b['children']),
        'Final overview scope, fresh attempts or accepted dependencies changed')
    require(plan['slots'][0]['classBRequests']==1400 and plan['slots'][2]['classBRequests']==1598 and
        plan['slots'][0]['egressBytes']==768*2**20 and plan['slots'][2]['egressBytes']==1216*2**20,
        'Final dependency reads are not funded')
    if job is not None:require(job in jobs,'Unallocated final parent')
    return dict(bindings=bindings)

def validate_plan(plan,region,authority):
    require(authority==POLICY,'Final overview authority changed')
    _,p=select(plan['completedJobIDs'],plan['priorAttemptCounts'],plan['crosswaveHistory'],
        plan['nativeRepairHistory'],plan.get('finalOverviewHistory',[]),authority)
    require(p is not None and p==plan['finalOverviewPhase'],'Final dependency selection differs')
    scope(plan,region)

def validate_verification(value):
    from rrgh_crosswave_batch import validate_verification as batch_verify,VERIFY as OLD_VERIFY
    require(isinstance(value,dict) and value.get('format')==VERIFY and
        value.get('allCoverageMasksVerified') is True and value.get('seedAuthoritySHA256')==SEED_SHA,
        'Exact edge and seed verification required')
    batch_verify(dict(value,format=OLD_VERIFY))
    return value

def advance(plan,region,audit):
    """Settle either the complete native queue or one complete final parent wave."""
    require(audit.get('finalOverviewPolicy')==POLICY and digest(plan)==audit['planSHA256'] and
        plan['campaign']['sequence']==audit['wave'] and
        not any(audit.get(k) for k in ('partialRecovered','checkpointRecovery','batchClosure','sourcePixelGapJobs')),
        'Only a complete independent settlement may advance final overviews')
    if plan.get('nativeRepairPhase'):
        from rrgh_native_batch import advance as native_advance,select as native_select
        accepted,attempts,native_history,index=native_advance(plan,region,audit)
        require(not native_select(index,accepted,attempts) and set(index)<=set(accepted) and
            audit['acceptedRasterTiles']==277587,'Native map is not completely accepted')
        return accepted,attempts,native_history,[]
    validate_plan(plan,region,POLICY)
    proof=validate_verification(audit.get('overviewPilotVerification'))
    require(proof['phaseSHA256']==digest(plan['finalOverviewPhase']) and proof['planSHA256']==digest(plan) and
        [r['job'] for r in proof['parents']]==plan['approvedJobIDs'] and
        audit['jobsNew']==audit['tilesNew']==len(plan['approvedJobIDs']) and
        audit['acceptedJobs']==len(plan['completedJobIDs'])+audit['jobsNew'] and
        audit['acceptedRasterTiles']==plan['campaign']['carry']['priorRasterTiles']+audit['tilesNew'],
        'Final overview independent count or provenance mismatch')
    attempts=copy.deepcopy(plan['priorAttemptCounts'])
    for jid in plan['approvedJobIDs']:
        require(attempts.get(jid,0)==0,'Final overview attempt was already consumed')
        attempts[jid]=1
    history=copy.deepcopy(plan.get('finalOverviewHistory',[]))
    history.append(dict(sequence=audit['wave'],sourcePlanSHA256=audit['planSHA256'],
        recovery=copy.deepcopy(audit['receiptRef']),recipeSHA256=hashlib.sha256(
            (json.dumps(region,sort_keys=True,indent=2)+'\n').encode()).hexdigest(),
        sourceJobCount=audit['jobsNew'],expectedTiles=audit['tilesNew'],
        acceptedJobIDs=copy.deepcopy(plan['approvedJobIDs']),finalOverviewVerification=copy.deepcopy(proof)))
    return plan['completedJobIDs']+plan['approvedJobIDs'],attempts,copy.deepcopy(plan['nativeRepairHistory']),history

def validate_history(plan,region):
    """Reconstruct the native baseline and every prospective parent allocation."""
    from rrgh_native_batch import history_ledger
    from rrgh_expanded_production import build_index
    final_history=plan.get('finalOverviewHistory',[]);base=copy.deepcopy(plan)
    completed=base['completedJobIDs'];attempts=base['priorAttemptCounts']
    for row in reversed(final_history):
        ids=row['acceptedJobIDs'];n=len(ids)
        require(n>0 and completed[-n:]==ids and row['sourceJobCount']==row['expectedTiles']==n,
            'Accepted final parent history changed')
        proof=validate_verification(row['finalOverviewVerification'])
        require(proof['planSHA256']==row['sourcePlanSHA256'] and [r['job'] for r in proof['parents']]==ids,
            'Final parent history lost its independent verification')
        del completed[-n:]
        for jid in ids:
            require(attempts.pop(jid,None)==1,'Final parent attempt history reset')
    base['campaign']['carry']['priorCompletedJobs']=len(completed)
    base['campaign']['carry']['priorRasterTiles']=277587
    index,_=build_index(region);history_ledger(base,index)
    require(set(index)<=set(completed),'Native coverage is incomplete')
    prior=[];sequence=base['nativeRepairHistory'][-1]['sequence']
    for row in final_history:
        selected,phase=select(completed,attempts,plan['crosswaveHistory'],plan['nativeRepairHistory'],prior)
        require(row['sequence']==sequence+1 and row['acceptedJobIDs']==[j['id'] for j in selected] and
            row['finalOverviewVerification']['phaseSHA256']==digest(phase),
            'Historical final allocation differs from the approved selector')
        completed.extend(row['acceptedJobIDs']);attempts.update({j:1 for j in row['acceptedJobIDs']})
        prior.append(row);sequence+=1
    require(completed==plan['completedJobIDs'] and attempts==plan['priorAttemptCounts'] and
        plan['campaign']['carry']['priorRasterTiles']==277587+sum(r['expectedTiles'] for r in final_history),
        'Final accepted or attempted ledger is inconsistent')

def validate_publication(old,old_region,plan,region,audit):
    accepted,attempts,native_history,final_history=advance(old,old_region,audit)
    validate_plan(plan,region,POLICY);validate_history(plan,region)
    require(plan['completedJobIDs']==accepted and plan['priorAttemptCounts']==attempts and
        plan['nativeRepairHistory']==native_history and plan.get('finalOverviewHistory',[])==final_history and
        plan['crosswaveHistory']==old['crosswaveHistory'],'Final publication lost accepted provenance')
    campaign=copy.deepcopy(old['campaign']);campaign.update(sequence=old['campaign']['sequence']+1,
        previousRecovery=audit['receiptRef'],carry=audit['nextCarry'])
    require(plan['campaign']==campaign,'Final campaign or quarantine history changed')
    validate_funding(old,plan)

def waiting_summary(plan,region,audit):
    accepted,attempts,native_history,history=advance(plan,region,audit)
    jobs,_=select(accepted,attempts,plan['crosswaveHistory'],native_history,history)
    require(not jobs and audit['acceptedRasterTiles']==278278 and
        sum(r['expectedTiles'] for r in history)==691,'Final overview queue is stuck or incomplete')
    return dict(format='rrgh-raster-complete-package-wait-v1',phase='all-raster-positions-verified',
        sequence=audit['wave'],planSHA256=audit['planSHA256'],recoveryReceipt=audit['receiptRef'],
        acceptedRasterTiles=278278,requiredRasterTiles=278278,remainingRasterTiles=0,
        fullRasterCoverageComplete=True,finalPackageDeliveryComplete=False,
        nativeRepairSettlements=native_history,finalOverviewSettlements=history,
        nextPhase='consolidated-offline-package-and-delivery-validation')

def prepare(root,audit):
    import base64,sys,zlib
    from pathlib import Path
    from datetime import datetime,timedelta,timezone
    root=Path(root).resolve();sys.path.insert(0,str(root/'backend/scripts'))
    from rrgh_dispatcher import config
    from rrgh_expanded_production import read_region
    from rrgh_native_context import augment
    from rrgh_final_integration import install,MODULES,COORDINATOR
    folder,old,code=config(root);old_region=read_region(folder)
    accepted,attempts,native_history,history=advance(old,old_region,audit)
    selected,phase=select(accepted,attempts,old['crosswaveHistory'],native_history,history)
    if not selected:
        summary=waiting_summary(old,old_region,audit)
        (root/'RRGH-COMPLETION-WAIT.json').write_bytes(canonical(summary));return summary
    from rrgh_recovery_catalog_integration import install as install_catalog
    install_catalog(root)
    from rrgh_overview_integration import install as install_overview_hooks
    install_overview_hooks(root)
    region=augment(old_region);install(root)
    code=(root/'backend/scripts/gorge_campaign.py').read_text()
    from rrgh_batch_integration import installed as batch_installed,augment as augment_batch
    if batch_installed(root):code=augment_batch(code)
    next_folder=folder.with_name('gorge-campaign-wave-'+str(old['campaign']['sequence']+1)+'-20261102')
    require(not next_folder.exists(),'Final overview successor already exists')
    old_pin="CONFIG=SOURCE.parent/'config/"+folder.name+"'"
    new_pin="CONFIG=SOURCE.parent/'config/"+next_folder.name+"'"
    require(code.count(old_pin)==1,'Final source configuration pin changed')
    code_path=root/'backend/scripts/gorge_campaign.py';code_path.write_text(code.replace(old_pin,new_pin))
    plan=copy.deepcopy(old);ids=[j['id'] for j in selected]
    for key in ('nativeRepairPhase','crosswavePhase','completionPhase','overviewPilot','resumableBatch'):plan.pop(key,None)
    plan.update(completedJobIDs=accepted,priorAttemptCounts=attempts,approvedJobIDs=ids,slotJobs={'1':ids},
        nativeRepairHistory=native_history,finalOverviewHistory=history,finalOverviewPhase=phase,
        jobPolicies={jid:copy.deepcopy(JOB_POLICY) for jid in ids},
        expiresAt=(datetime.now(timezone.utc)+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    plan['campaign'].update(sequence=old['campaign']['sequence']+1,previousRecovery=audit['receiptRef'],carry=audit['nextCarry'])
    plan['slots'][1]['attempts']=plan['limits']['attempts']=len(ids);fund(plan)
    region['jobs']=selected
    for name in (*MODULES,COORDINATOR,'gorge_campaign.py','rrgh_overview_pilot.py','rrgh_verified_tile_catalog.py'):
        region['engineHashes'][name]=hashlib.sha256((root/'backend/scripts'/name).read_bytes()).hexdigest()
    plan['regionPlanSHA256']=digest(region)
    from run_gorge_checkpoint_slot import code_snapshot
    plan['sourceSnapshotSHA256']=code_snapshot(root/'backend/scripts')
    env=json.loads((folder/'ALLOWANCE.json').read_bytes())
    from gorge_campaign_budget import admit,cost
    env['cloudStorageAllowance'].update(planSHA256=digest(plan),reservedWorstCaseUSD=str(cost(plan['limits'])))
    admission=admit(plan,env)
    from decimal import Decimal
    require(Decimal(admission['cumulativeAdmissionUSD'])<Decimal('123') and Decimal(admission['monthlyAdmissionUSD'])<Decimal('2'),
        'Final overview admission exhausted original budget or storage allowance')
    validate_publication(old,old_region,plan,region,audit)
    next_folder.mkdir()
    for name,value in [('PLAN.json',plan),('ALLOWANCE.json',env)]:
        (next_folder/name).write_bytes(canonical(value))
    (next_folder/'REGION-PLAN.json.z.b64').write_bytes(base64.b64encode(zlib.compress(canonical(region),9)))
    from gorge_campaign import configuration
    p,e,r=configuration(next_folder);require(p==plan and r==region,'Final overview source readback differs')
    return dict(nextSequence=plan['campaign']['sequence'],nextPlanSHA256=digest(plan),jobs=len(ids),tiles=len(ids),
        phase='final-overviews',pilot=phase['pilot'],cumulativeAdmissionUSD=str(admission['cumulativeAdmissionUSD']))
