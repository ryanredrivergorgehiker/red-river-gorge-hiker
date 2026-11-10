"""Finite mask-verified native repair batches, preserving both consumed attempts."""
import base64
import copy
from datetime import datetime,timedelta,timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib
import rrgh_native_repair as pilot
import rrgh_native_context as context

BASELINE='943a8fc21d34ce6dda1492c1ad80c58e56d6aa61da6660ecc50d70296c90326d'
RECEIPT=dict(key='engineering/map-production/plans/'+BASELINE+'/slots/00002/receipt.json',
    bytes=1491,generation='1794320163909534',sha256='54ee342bcf4205229ec1450cea5f0b2914a9b0763193c9e8bb227afb54b6e8bf')
MASK_SHA='5d057d172b4de609bdf34cd7529ffb596385cf8be10f31b5edf492ea8c4e01e5'
FORMAT='rrgh-native-repair-batch-phase-v2'
POLICY=dict(format='rrgh-native-repair-batch-authority-v2',enabled=True,
    authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-10',
    baselineSequence=1419,baselinePlanSHA256=BASELINE,baselineAcceptedTiles=273868,
    baselineAcceptedJobs=33686,baselineRecovery=RECEIPT,requiredRasterTiles=278278,
    maskManifestSHA256=MASK_SHA,officialContextMetadataSHA256=context.SHA,
    plannedNativeJobs=373,plannedNativeTiles=3719,
    maxJobs=12,maxJobsPerFamily=4,maxGlobalAttempts=2,
    preserveAcceptedOutputs=True,preserveConsumedAttempts=True)
BASE_COMPLETED='cf078294288cfb8219c167851d8b1e2a76782facd4a6d330c9a4089cb64a8c1b'
BASE_ATTEMPTS='4a92c0298c9e8edb164899f6ab388aa1ec807c5528b38f48d93f27f2d85591bd'
BASE_CAMPAIGN='20b9db2fe884ffe088fc7a7be9aafeb3b5aabf94a0c87de8b5375b9d281d334d'
BASE_OVERVIEWS='c90693f7c335d0fe916c7e561fec1a15447aaee4c5f797c5f601e3a237bf9414'
BASE_RECIPE='d0695e32c23e5016a9818d682de1d443f6475f9c29ea2423204b6212ad55352f'
CAPS={'hiking':dict(seconds=600,sourceBytes=67108864,sourceRequests=150),
    'terrain':dict(seconds=600,sourceBytes=134217728,sourceRequests=200),
    'leaf-off':dict(seconds=600,sourceBytes=536870912,sourceRequests=750),
    'leaf-on':dict(seconds=600,sourceBytes=134217728,sourceRequests=49),
    'usgs-topo':dict(seconds=600,sourceBytes=1048576,sourceRequests=1)}
canonical=lambda v:(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
digest=lambda v:hashlib.sha256(canonical(v)).hexdigest()
require=pilot.require


def authorized(value):
    require(value in (pilot.POLICY,POLICY),'Exact reviewed native repair authority required')


@lru_cache(maxsize=1)
def masks():
    raw=Path(__file__).with_name('fixtures').joinpath('native-repair-verified-masks-20261110.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest()==MASK_SHA,'Native source-mask evidence changed')
    value=json.loads(raw)
    require(value['format']=='rrgh-native-repair-verified-masks-v1' and value['sourcePlanSHA256']==pilot.BASELINE and
        value['sourceSHA']=='895c01953481b2b5825abee9a4c0681f37211eb4' and
        len(value['jobs'])==373 and len({j['id'] for j in value['jobs']})==len(value['jobs']),
        'Native repair evidence inventory changed')
    for j in value['jobs']:
        proof=j['maskEvidence'];side={'terrain':514,'hiking':512,'leaf-on':1024,'leaf-off':1024,'usgs-topo':256}.get(j['layer'])
        require(j['layer'] in CAPS and proof['allPixelsPresent'] is True and proof['missingPixels']==0 and
            proof['width']==proof['height']==side and proof['validPixels']==side*side and
            proof['job']==j['id'] and proof['mapTilesWritten']==0 and proof['acceptedTilesAdded']==0 and
            proof['productionAttemptReplayed'] is False and proof['cloudRequests']==0,
            'Unverified or incomplete source mask cannot authorize a final attempt')
        cap=CAPS[j['layer']]
        require(0<proof['actual']['operations']<=cap['sourceRequests'] and
            0<proof['actual']['receivedBodyBytes']<=cap['sourceBytes'] and
            proof['reserved']['sourceRequests']<=cap['sourceRequests'] and
            proof['reserved']['sourceBytes']<=cap['sourceBytes'] and
            0<proof['seconds']<=cap['seconds'] and
            all(proof['reserved'].get(k,0)==0 for k in
                ('attempts','classARequests','classBRequests','egressBytes','storedBytes')),
            'Source mask preflight exceeded the original bounded read allowance')
    return value['jobs']


def jobs(index):
    result=[]
    for row in masks():
        require(digest(index[row['id']])==row['jobSHA256'],'Verified native source selection changed')
        result.append(index[row['id']])
    require(sum(len(j['outputTiles']) for j in result)==3719,'Frozen native repair tile count changed')
    return result


def select(index,accepted,attempts):
    accepted=set(accepted);counts=dict.fromkeys(CAPS,0);picked=[]
    for job in jobs(index):
        jid=job['id'];layer=job['layer']
        require(attempts.get(jid) in (1,2),'Lost original consumed native attempt')
        if jid in accepted or attempts[jid]==2:continue
        if counts[layer]>=4:continue
        picked.append(job);counts[layer]+=1
        if len(picked)==12:break
    return picked


def history_ledger(plan,index):
    history=plan.get('nativeRepairHistory',[])
    completed=list(plan['completedJobIDs']);attempts=dict(plan['priorAttemptCounts'])
    seen=set();tiles=0;valid=set(pilot.JOBS)|{j['id'] for j in masks()}
    require(valid<=set(plan['priorAttemptCounts']) and
        all(plan['priorAttemptCounts'][j] in (1,2) for j in valid),
        'Only inspected previously consumed native positions belong in this repair queue')
    for row in history:
        allocated=row['attemptedJobIDs'];accepted=row['acceptedJobIDs'];failed=row['pixelGapJobIDs']
        require(len(allocated)==len(set(allocated)) and len(accepted)==len(set(accepted)) and len(failed)==len(set(failed)) and
            not seen.intersection(allocated) and set(allocated)<=valid and set(accepted).isdisjoint(failed) and
            set(accepted)|set(failed)==set(allocated) and row['attemptNumber']==2,
            'Native repair history duplicated or altered its accepted/failed partition')
        count=sum(len(index[j]['outputTiles']) for j in accepted)
        require(row['tiles']==count and row['sourceJobCount']==len(allocated) and
            row['expectedTiles']==sum(len(index[j]['outputTiles']) for j in allocated) and
            re.fullmatch('[0-9a-f]{64}',row['recipeSHA256']) and
            row['acceptanceKind']==('ordinary' if not failed else 'native-repair-pixel-gap-subset-v1') and
            row['recoveryReceipt']['key']=='engineering/map-production/plans/'+row['planSHA256']+'/slots/00002/receipt.json' and
            re.fullmatch('[0-9a-f]{64}',row['planSHA256']) and re.fullmatch('[0-9a-f]{64}',row['recoveryReceipt']['sha256']) and
            str(row['recoveryReceipt']['generation']).isdigit() and row['recoveryReceipt']['bytes']>0,
            'Native repair history receipt or geometry changed')
        seen.update(allocated);tiles+=count
    require([r['sequence'] for r in history]==list(range(1419,1419+len(history))),
        'Native repair history sequence is not contiguous')
    if history:
        require(history[0]==dict(sequence=1419,planSHA256=BASELINE,recoveryReceipt=RECEIPT,
            attemptedJobIDs=pilot.JOBS,acceptedJobIDs=pilot.JOBS,pixelGapJobIDs=[],attemptNumber=2,tiles=31,
            recipeSHA256=BASE_RECIPE,sourceJobCount=3,expectedTiles=31,acceptanceKind='ordinary'),
            'Actual verified native pilot evidence changed')
    for row in reversed(history):
        accepted=row['acceptedJobIDs']
        if accepted:
            require(completed[-len(accepted):]==accepted,'Native repair accepted history reordered or erased')
            del completed[-len(accepted):]
        for jid in row['attemptedJobIDs']:
            require(attempts.get(jid)==2,'Historical second attempt reset')
            attempts[jid]=1
    require(digest(completed)==BASE_COMPLETED and digest(attempts)==BASE_ATTEMPTS and
        digest({k:v for k,v in plan['campaign'].items() if k not in ('sequence','carry','previousRecovery')})==BASE_CAMPAIGN and
        digest(plan['crosswaveHistory'])==BASE_OVERVIEWS and
        plan['campaign']['carry']['priorCompletedJobs']==len(plan['completedJobIDs']) and
        plan['campaign']['carry']['priorRasterTiles']==273837+tiles,
        'Immutable accepted, attempted, quarantined, budget or overview baseline changed')
    # Reconstruct each past finite selection from the immutable baseline too;
    # a fabricated historical row cannot smuggle extra or reordered work in.
    for number,row in enumerate(history):
        expected=pilot.JOBS if number==0 else [j['id'] for j in select(index,completed,attempts)]
        require(row['attemptedJobIDs']==expected,'Historical native allocation differs from the reviewed selector')
        completed.extend(row['acceptedJobIDs'])
        for jid in row['attemptedJobIDs']:attempts[jid]=2
    require(completed==plan['completedJobIDs'] and attempts==plan['priorAttemptCounts'],
        'Native history does not reconstruct the current accepted and consumed ledgers')
    return history


def validate_plan(plan,region,authority):
    require(authority==POLICY and plan.get('nativeRepairPhase')==dict(format=FORMAT,authority=POLICY,attemptNumber=2),
        'Exact finite native repair batch authority required')
    from rrgh_expanded_production import build_index
    context.validate(region)
    index,_=build_index(region);history=history_ledger(plan,index)
    require(history and plan['campaign']['sequence']==1420+len(history)-1 and
        plan['campaign']['previousRecovery']==history[-1]['recoveryReceipt'], 'Native predecessor lost')
    selected=select(index,plan['completedJobIDs'],plan['priorAttemptCounts'])
    ids=[j['id'] for j in selected]
    require(selected and region['jobs']==selected and plan['approvedJobIDs']==ids and plan['slotJobs']=={'1':ids} and
        not any(plan.get(k) for k in ('crosswavePhase','completionPhase','overviewPilot','resumableBatch')) and
        plan['jobPolicies']=={j['id']:CAPS[j['layer']] for j in selected},'Native batch selection changed')
    require(all(sum(plan['jobPolicies'][j][dimension] for j in ids)<=plan['slots'][1][dimension]
        for dimension in ('seconds','sourceBytes','sourceRequests')),'Native batch exceeds the unchanged slot envelope')


def advance(old,region,audit):
    require(audit.get('nativeRepairPolicy')==POLICY and digest(old)==audit['planSHA256'] and
        old['campaign']['sequence']==audit['wave'] and not audit.get('partialRecovered') and
        not audit.get('checkpointRecovery') and not audit.get('batchClosure') and not audit.get('overviewPilotVerification'),
        'Native settlement requires an exact independently verified producer')
    from rrgh_expanded_production import build_index
    index,_=build_index(region)
    if old['campaign']['sequence']==1419:
        require(digest(old)==BASELINE and audit['receiptRef']==RECEIPT and audit['acceptedRasterTiles']==273868 and
            audit['acceptedJobs']==33686,'Measured native batch baseline changed')
        pilot.validate_plan(old,region,pilot.POLICY)
        history_ledger(old,index)
    else:validate_plan(old,region,POLICY)
    allocated=old['approvedJobIDs'];failed=audit.get('sourcePixelGapJobs',[])
    accepted=audit.get('sourceCompletedJobIDs',[]) if failed else allocated
    require(len(failed)==len(set(failed)) and len(accepted)==len(set(accepted)) and set(accepted).isdisjoint(failed) and
        set(accepted)|set(failed)==set(allocated),'Native independent allocation partition changed')
    tiles=sum(len(index[j]['outputTiles']) for j in accepted)
    require(audit['jobsNew']==len(accepted) and audit['tilesNew']==tiles and
        audit['acceptedJobs']==len(old['completedJobIDs'])+len(accepted) and
        audit['acceptedRasterTiles']==old['campaign']['carry']['priorRasterTiles']+tiles,
        'Native independent tile or job count mismatch')
    attempts=copy.deepcopy(old['priorAttemptCounts'])
    for jid in allocated:
        require(attempts.get(jid)==1 and jid not in old['completedJobIDs'],'Native final attempt was already consumed or accepted')
        attempts[jid]=2
    history=copy.deepcopy(old.get('nativeRepairHistory',[]))
    history.append(dict(sequence=audit['wave'],planSHA256=audit['planSHA256'],recoveryReceipt=audit['receiptRef'],
        attemptedJobIDs=allocated,acceptedJobIDs=accepted,pixelGapJobIDs=failed,attemptNumber=2,tiles=tiles,
        recipeSHA256=hashlib.sha256((json.dumps(region,indent=2,sort_keys=True)+'\n').encode()).hexdigest(),
        sourceJobCount=len(allocated),expectedTiles=sum(len(j['outputTiles']) for j in region['jobs']),
        acceptanceKind='ordinary' if not failed else 'native-repair-pixel-gap-subset-v1'))
    return old['completedJobIDs']+accepted,attempts,history,index


def validate_publication(old,old_region,plan,region,audit):
    accepted,attempts,history,index=advance(old,old_region,audit)
    validate_plan(plan,region,POLICY)
    require(plan['completedJobIDs']==accepted and plan['priorAttemptCounts']==attempts and plan['nativeRepairHistory']==history,
        'Native publication lost or invented accepted or consumed history')
    campaign=copy.deepcopy(old['campaign']);campaign.update(sequence=old['campaign']['sequence']+1,
        previousRecovery=audit['receiptRef'],carry=audit['nextCarry'])
    slots=copy.deepcopy(old['slots']);slots[1]['attempts']=len(plan['approvedJobIDs'])
    require(plan['campaign']==campaign and plan['slots']==slots and
        plan['limits']==dict(old['limits'],attempts=len(plan['approvedJobIDs'])), 'Native history or resource envelope changed')


def waiting_summary(plan,region,audit):
    accepted,attempts,history,index=advance(plan,region,audit)
    require(not select(index,accepted,attempts),'Verified native repair jobs still remain eligible')
    accepted_set=set(accepted)
    native_remaining=sum(len(job['outputTiles']) for jid,job in index.items() if jid not in accepted_set)
    remaining=278278-audit['acceptedRasterTiles']
    require(0<=native_remaining<=remaining,'Native versus lower-zoom remainder disagrees')
    return dict(format='rrgh-native-repair-batch-wait-v2',phase='source-mask-verified-native-repairs',
        sequence=audit['wave'],planSHA256=audit['planSHA256'],recoveryReceipt=audit['receiptRef'],
        acceptedRasterTiles=audit['acceptedRasterTiles'],requiredRasterTiles=278278,
        remainingRasterTiles=remaining,remainingNativeRasterTiles=native_remaining,
        remainingLowerZoomRasterTiles=remaining-native_remaining,fullRasterCoverageComplete=False,
        nativeRepairSettlements=history,originalQuarantineHistoryPreserved=True,
        nextPhase='unresolved-native-positions-and-remaining-overviews' if native_remaining else
            'remaining-overviews-and-final-package-validation')


def prepare(root,audit):
    root=Path(root).resolve();sys.path.insert(0,str(root/'backend/scripts'))
    from rrgh_dispatcher import config
    from rrgh_expanded_production import read_region
    folder,old,code=config(root);region=read_region(folder)
    accepted,attempts,history,index=advance(old,region,audit)
    region=context.augment(region)
    from rrgh_expanded_production import build_index
    index,_=build_index(region)
    picked=select(index,accepted,attempts)
    if not picked:
        summary=waiting_summary(old,region,audit)
        (root/'RRGH-COMPLETION-WAIT.json').write_bytes(canonical(summary));return summary
    next_folder=folder.with_name('gorge-campaign-wave-'+str(old['campaign']['sequence']+1)+'-20261102')
    require(not next_folder.exists(),'Native successor configuration already exists')
    old_pin="CONFIG=SOURCE.parent/'config/"+folder.name+"'"
    new_pin="CONFIG=SOURCE.parent/'config/"+next_folder.name+"'"
    require(code.count(old_pin)==1,'Native source CONFIG pin changed')
    code_path=root/'backend/scripts/gorge_campaign.py';code_path.write_text(code.replace(old_pin,new_pin))
    from rrgh_native_transport import install as install_transport
    install_transport(root)
    plan=copy.deepcopy(old);ids=[j['id'] for j in picked]
    plan.update(completedJobIDs=accepted,priorAttemptCounts=attempts,approvedJobIDs=ids,slotJobs={'1':ids},
        nativeRepairHistory=history,nativeRepairPhase=dict(format=FORMAT,authority=POLICY,attemptNumber=2),
        jobPolicies={j['id']:copy.deepcopy(CAPS[j['layer']]) for j in picked},
        expiresAt=(datetime.now(timezone.utc)+timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    plan['campaign'].update(sequence=old['campaign']['sequence']+1,previousRecovery=audit['receiptRef'],carry=audit['nextCarry'])
    plan['slots'][1]['attempts']=plan['limits']['attempts']=len(ids)
    region['jobs']=picked;region['engineHashes']['gorge_campaign.py']=hashlib.sha256(code_path.read_bytes()).hexdigest()
    region['engineHashes']['gorge_guarded_worker.py']=hashlib.sha256((root/'backend/scripts/gorge_guarded_worker.py').read_bytes()).hexdigest()
    plan['regionPlanSHA256']=digest(region)
    from run_gorge_checkpoint_slot import code_snapshot
    plan['sourceSnapshotSHA256']=code_snapshot(root/'backend/scripts')
    env=json.loads((folder/'ALLOWANCE.json').read_bytes())
    from gorge_campaign_budget import admit,cost
    env['cloudStorageAllowance'].update(planSHA256=digest(plan),reservedWorstCaseUSD=str(cost(plan['limits'])))
    admission=admit(plan,env)
    from decimal import Decimal
    require(Decimal(admission['cumulativeAdmissionUSD'])<Decimal('123') and Decimal(admission['monthlyAdmissionUSD'])<Decimal('2'),
        'Native repair admission exhausted the unchanged campaign or storage budget')
    validate_publication(old,read_region(folder),plan,region,audit)
    next_folder.mkdir()
    for name,value in [('PLAN.json',plan),('ALLOWANCE.json',env)]:
        (next_folder/name).write_bytes(canonical(value))
    (next_folder/'REGION-PLAN.json.z.b64').write_bytes(base64.b64encode(zlib.compress(canonical(region),9)))
    from gorge_campaign import configuration
    p,e,r=configuration(next_folder)
    require(p==plan and r==region,'Native successor local readback differs')
    return dict(nextSequence=plan['campaign']['sequence'],nextPlanSHA256=digest(plan),jobs=len(ids),
        tiles=sum(len(j['outputTiles']) for j in picked),newScope=str(next_folder.relative_to(root)),
        preservedPriorAttempts=True,preservedHistoricalQuarantines=True,
        cumulativeAdmissionUSD=str(admission['cumulativeAdmissionUSD']),monthlyAdmissionUSD=str(admission['monthlyAdmissionUSD']))
