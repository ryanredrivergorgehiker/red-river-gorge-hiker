"""Finite ordinary-receipt overview queue, compact bindings and funded read bounds."""
import base64
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import zlib

INDEX_SHA='1fea8db2f65861e50130856a152cec5862baee2a483ace4eef328a96930c4974'
POLICY=dict(format='rrgh-crosswave-batch-authority-v2',enabled=True,
    authorizedBy='ryanredrivergorgehiker',authorizedOn='2026-11-09',
    baselineSequence=1357,baselinePlanSHA256='e7497a08e69b1e429d2cb4e61b3854ef3a07ff788b1284301007c5f9bd1173ff',
    baselineAcceptedTiles=267476,requiredRasterTiles=278278,maxJobs=128,jobSeconds=60,
    receiptIndexSHA256=INDEX_SHA,verifiedPilotRecovery={'bytes': 11398, 'generation': '1794245559746794', 'sha256': '52a4fc9b273c75b434b0312895965f84c80a581f54f3769a4ed01ad98b0e8e77', 'key': 'engineering/map-production/plans/e7497a08e69b1e429d2cb4e61b3854ef3a07ff788b1284301007c5f9bd1173ff/slots/00002/receipt.json'},
    preserveAcceptedOutputs=True,preserveConsumedAttempts=True)
FORMAT='rrgh-crosswave-batch-phase-v2'
VERIFY='rrgh-crosswave-batch-verification-v2'
SOURCE_KEYS=('sequence','sourcePlanSHA256','recovery','recipeSHA256','sourceJobCount','expectedTiles','acceptedJobIDs')
JOB_POLICY=dict(seconds=60,sourceBytes=0,sourceRequests=0)


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


@lru_cache(maxsize=1)
def original_index():
    data=Path(__file__).with_name('fixtures')/'completion-receipt-index.json.z.b64'
    raw=zlib.decompress(base64.b64decode(data.read_bytes()))
    require(hashlib.sha256(raw).hexdigest()==INDEX_SHA,'Original immutable receipt inventory changed')
    index=json.loads(raw)
    require(index['indexedJobs']==25504 and len(index['unindexedAcceptedJobs'])==44,
        'Original receipt inventory count changed')
    return index


def advance_history(old,region,audit):
    require(old.get('crosswavePhase') and audit['jobsNew']==len(old['approvedJobIDs']) and
        audit['tilesNew']==len(old['approvedJobIDs']) and not audit.get('partialRecovered') and
        not audit.get('sourcePixelGapJobs') and not audit.get('checkpointRecovery'),
        'Only completely accepted overview waves may extend ordinary provenance')
    history=copy.deepcopy(old.get('crosswaveHistory',[]))
    row=dict(sequence=old['campaign']['sequence'],sourcePlanSHA256=audit['planSHA256'],
        recovery=copy.deepcopy(audit['receiptRef']),recipeSHA256=hashlib.sha256(
            (json.dumps(region,indent=2,sort_keys=True)+'\n').encode()).hexdigest(),
        sourceJobCount=len(old['approvedJobIDs']),expectedTiles=len(old['approvedJobIDs']),
        acceptedJobIDs=sorted(old['approvedJobIDs']))
    require(not any(w['sourcePlanSHA256']==row['sourcePlanSHA256'] for w in history),'Overview provenance duplicated')
    history.append(row);return history


def source_map(history,accepted):
    accepted=set(accepted);sources={}
    waves=[{k:w[k] for k in SOURCE_KEYS} for w in original_index()['waves'] if w['acceptanceKind']=='ordinary']+history
    for wave in waves:
        require(set(wave['acceptedJobIDs'])<=accepted,'Historical accepted child removed')
        for jid in wave['acceptedJobIDs']:
            require(jid not in sources,'Ambiguous historical child acceptance')
            sources[jid]=wave
    return sources


def read_bounds(p):
    children=sum(len(v) for v in p['dependencies'].values())
    waves=len(p['sources']);jobs=len(p['jobs'])
    # Per unique source: recovery, worker, detail. Per child: job receipt and
    # selected output range. Metadata cache exists only within a funded slot.
    requests=3*waves+2*children
    bytes_bound=waves*(16*1024+16*1024+256*1024)+children*(64*1024+512*1024)
    return dict(dependencyRequests=requests,dependencyBytes=bytes_bound,
        bootstrapRequests=requests+96,recoveryRequests=requests+2*jobs+64,
        bootstrapBytes=bytes_bound+240*2**20)


def fits(p):
    b=read_bounds(p)
    return (len(p['jobs'])<=128 and b['bootstrapRequests']<=1400 and
        b['recoveryRequests']<=1598 and b['bootstrapBytes']<=768*2**20)


def fund(plan):
    """Redistribute only existing read allowances; aggregate ceiling unchanged."""
    for i,requests,mib in ((0,1400,768),(1,2,64),(2,1598,1216)):
        plan['slots'][i]['classBRequests']=requests
        plan['slots'][i]['egressBytes']=mib*2**20


def validate_funding(prior,plan):
    expected=copy.deepcopy(prior['slots'])
    holder={'slots':expected};fund(holder)
    expected[1]['attempts']=len(plan['approvedJobIDs'])
    require(plan['slots']==expected and plan['limits']==dict(prior['limits'],attempts=len(plan['approvedJobIDs'])),
        'Only exact existing read allowance redistribution permitted')
    require(sum(s['classBRequests'] for s in expected)==3000==plan['limits']['classBRequests'] and
        sum(s['egressBytes'] for s in expected)==2**31==plan['limits']['egressBytes'],
        'Aggregate read envelope changed')


def adjacent_pairs(parents):
    positions={tuple(p['job'].rsplit('-',3)) for p in parents}
    return sum((layer,z,str(int(x)+dx),str(int(y)+dy)) in positions
        for layer,z,x,y in positions for dx,dy in ((1,0),(0,1)))


def expand(p):
    from rrgh_crosswave_dependencies import FORMAT as CHILD_FORMAT,child_ids
    require(p.get('format')==FORMAT and p.get('authority')==POLICY and
        p.get('readBounds')==read_bounds(p) and 0<len(p['jobs'])<=128 and fits(p),
        'Cross-wave batch authority or funded envelope changed')
    sources=p['sources'];used=set();result=[]
    require(set(p['dependencies'])=={j['id'] for j in p['jobs']},'Dependency/job mismatch')
    for job in p['jobs']:
        ids=child_ids(job);dep=p['dependencies'][job['id']]
        require([x['job'] for x in dep]==ids,'Four exact child positions required')
        children=[]
        for entry in dep:
            sha=entry['source'];used.add(sha)
            require(sha in sources and sources[sha]['sourcePlanSHA256']==sha,'Unknown source wave')
            children.append(dict(job=entry['job'],source=copy.deepcopy(sources[sha])))
        result.append(dict(format=CHILD_FORMAT,job=copy.deepcopy(job),children=children))
    require(used==set(sources),'Unused source authority')
    return result


def select(accepted,attempts,authority,history):
    require(authority==POLICY,'Exact measured batch policy required')
    from rrgh_completion_phase import lower_usgs_index,BOUNDS
    from rrgh_crosswave_dependencies import child_ids,LAYERS
    index=lower_usgs_index(dict(boundsWGS84=BOUNDS,profiles={'core':{'usgs-topo':16}}))
    sources=source_map(history,accepted);done=set(accepted)
    p=dict(format=FORMAT,authority=copy.deepcopy(POLICY),jobs=[],sources={},dependencies={})
    for tile in sorted(index.values(),key=lambda j:(-j['z'],j['x'],j['y'])):
        for layer in LAYERS:
            z,x,y=(tile[k] for k in ('z','x','y'))
            job=dict(id=f'{layer}-{z}-{x}-{y}',layer=layer,z=z,x=x,y=y,
                operation='overview',sourceIDs=[],outputTiles=[[z,x,y]])
            if job['id'] in done or attempts.get(job['id'],0):continue
            ids=child_ids(job)
            if not all(j in done and j in sources for j in ids):continue
            # Every child must itself be within the original required extent.
            # The accepted-job ledger cannot expand geography through adjacency.
            from rrgh_required_inventory import xy
            lo=xy(BOUNDS[0],BOUNDS[3],z+1);hi=xy(BOUNDS[2],BOUNDS[1],z+1)
            if not all(lo[0]<=int(j.rsplit('-',2)[1])<=hi[0] and
                lo[1]<=int(j.rsplit('-',1)[1])<=hi[1] for j in ids):continue
            candidate=copy.deepcopy(p);candidate['jobs'].append(job)
            candidate['dependencies'][job['id']]=[dict(job=j,source=sources[j]['sourcePlanSHA256']) for j in ids]
            for jid in ids:candidate['sources'][sources[jid]['sourcePlanSHA256']]=copy.deepcopy(sources[jid])
            if not fits(candidate):
                if p['jobs']:
                    p['readBounds']=read_bounds(p);return p['jobs'],p
                raise ValueError('One parent cannot fit existing funded envelope')
            p=candidate
            if len(p['jobs'])==128:
                p['readBounds']=read_bounds(p);return p['jobs'],p
    if not p['jobs']:return [],None
    p['readBounds']=read_bounds(p);return p['jobs'],p


def scope(plan,region,job=None):
    p=plan.get('crosswavePhase');bindings=expand(p)
    jobs=p['jobs'];accepted=set(plan['completedJobIDs'])
    require(region['jobs']==jobs and region['boundsWGS84']==[-83.8,37.65,-83.4,37.95] and
        plan['approvedJobIDs']==[j['id'] for j in jobs] and plan.get('overviewPilot') is None and
        not plan.get('completionPhase') and not plan.get('resumableBatch') and
        plan['jobPolicies']=={j['id']:JOB_POLICY for j in jobs} and
        all(j['id'] not in accepted and plan['priorAttemptCounts'].get(j['id'],0)==0 for j in jobs) and
        all(c['job'] in accepted for b in bindings for c in b['children']),
        'Batch scope, zero-source policy or fresh attempts changed')
    require(plan['slots'][0]['classBRequests']==1400 and plan['slots'][2]['classBRequests']==1598 and
        plan['slots'][0]['egressBytes']==768*2**20 and plan['slots'][2]['egressBytes']==1216*2**20,
        'Dependency reads are not funded')
    if job is not None:require(job in jobs,'Unallocated parent')
    return dict(bindings=bindings)


def validate_plan(plan,region,authority):
    require(authority==POLICY,'Unreviewed batch enrollment')
    jobs,p=select(plan['completedJobIDs'],plan['priorAttemptCounts'],authority,plan.get('crosswaveHistory',[]))
    require(p is not None and plan['crosswavePhase']==p,'Published dependency selection differs')
    scope(plan,region)


def validate_history(prior,old_region,plan,audit):
    require(plan['crosswaveHistory']==advance_history(prior,old_region,audit),'Unreviewed accepted parent history')
    require(plan['completedJobIDs']==prior['completedJobIDs']+prior['approvedJobIDs'],
        'Inclusive accepted job identities changed')
    expected=dict(prior['priorAttemptCounts'])
    for job in prior['approvedJobIDs']:
        require(expected.get(job,0)==0,'Prior ordinary allocation was already consumed');expected[job]=1
    require(plan['priorAttemptCounts']==expected,'Historical attempts changed')


def validate_verification(proof):
    from rrgh_verified_tile_catalog import ref
    require(isinstance(proof,dict) and proof.get('format')==VERIFY and
        re.fullmatch('[0-9a-f]{64}',proof.get('phaseSHA256','')) is not None and
        all(proof.get(k) is True for k in ('allChildrenHashAndPixelVerified','allParentsIndependentlyRecomputed',
            'priorChildrenUnmodified','sourceQualityUnchanged')) and proof.get('officialSourceRequests')==0,
        'Incomplete independent batch recomputation')
    parents=proof.get('parents',[])
    require(0<len(parents)<=128 and len({p['job'] for p in parents})==len(parents),'Invalid verified parent count')
    for parent in parents:
        require(re.fullmatch(r'(hiking|terrain|leaf-on|leaf-off)-(1[0-5])-\d+-\d+',parent['job']) is not None and
            re.fullmatch('[0-9a-f]{64}',parent['outputSHA256']) is not None and
            type(parent['outputBytes']) is int and 0<parent['outputBytes']<=512*1024,
            'Invalid verified parent identity')
    detail=ref(proof['detailRef']);sha=proof.get('planSHA256','')
    require(re.fullmatch('[0-9a-f]{64}',sha) is not None and
        detail['key'].startswith('engineering/map-production/plans/'+sha+'/slots/00002/indexes/') and
        detail['bytes']<=4*2**20 and re.fullmatch('[0-9a-f]{64}',proof.get('detailSHA256','')) is not None,
        'Independent batch proof must be immutable and bounded')
    return proof


def waiting_summary(plan,region,audit):
    validate_plan(plan,region,audit.get('crosswavePolicy'));validate_verification(audit.get('overviewPilotVerification'))
    require(audit['jobsNew']==len(plan['approvedJobIDs']) and audit['tilesNew']==audit['jobsNew'],
        'Incomplete overview batch cannot settle')
    return dict(format='rrgh-crosswave-batch-wait-v2',phase='ordinary-interior-overviews',
        sequence=plan['campaign']['sequence'],planSHA256=audit['planSHA256'],recoveryReceipt=audit['receiptRef'],
        acceptedRasterTiles=audit['acceptedRasterTiles'],requiredRasterTiles=278278,
        remainingRasterTiles=278278-audit['acceptedRasterTiles'],fullRasterCoverageComplete=False,
        nextPhase='typed-recovered-children-boundaries-and-native-repairs')
