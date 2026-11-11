"""Read the44 already accepted seed jobs through their original proof types.

Never invent a campaign receipt for an earlier seed or execute a raster job.
A prospective funded overview caller must bind this authority before reading.
"""
import copy,hashlib,io,json,re
from pathlib import Path

AUTHORITY={'format': 'rrgh-accepted-seed-authority-v1', 'history': {'acceptedBootstrap': {'bytes': 3323, 'generation': '1793326778242211', 'key': 'engineering/map-production/plans/9ba15a2a53ac9d9a49144a6865ae2f67c8cd68656cc54b2b22267e9b862c6eb7/slots/00000/receipt.json', 'sha256': 'd961178dc2c4bc4bf624e7e2fbdfe7fd85c0dcd4c49d3203ff615e02bac85282'}, 'proof': {'bytes': 2741819, 'generation': '1793326771724001', 'key': 'engineering/map-production/plans/9ba15a2a53ac9d9a49144a6865ae2f67c8cd68656cc54b2b22267e9b862c6eb7/slots/00000/indexes/85831cbba3137e60c319043fe35fb888bb38bb911f284313fec9102ea0781e3f', 'sha256': '85831cbba3137e60c319043fe35fb888bb38bb911f284313fec9102ea0781e3f'}, 'secondRecovery': {'bytes': 1997, 'generation': '1793361305573978', 'key': 'engineering/map-production/plans/afa534fa78d3341d242f1e53c916d914923849093fd708c916e315e7c0dd3b07/slots/00002/receipt.json', 'sha256': '1178d739bc4ab7fbf757201fa937cd4c27943af03bd29a6f7d004e619992b8c2'}, 'secondWorker': {'bytes': 2346, 'generation': '1793361191313030', 'key': 'engineering/map-production/plans/afa534fa78d3341d242f1e53c916d914923849093fd708c916e315e7c0dd3b07/slots/00001/receipt.json', 'sha256': '17519bf42d1e56a5f69a35b77567c4462aa1f3c4a3249b2998a718e61004dc02'}}, 'jobs': ['hiking-15-8772-12661', 'hiking-16-17544-25322', 'hiking-16-17544-25323', 'hiking-16-17545-25322', 'hiking-16-17545-25323', 'hiking-16-17545-25324', 'hiking-16-17545-25325', 'hiking-16-17546-25322', 'hiking-16-17546-25323', 'hiking-16-17546-25324', 'leaf-off-16-17544-25322', 'leaf-off-16-17544-25323', 'leaf-off-16-17545-25322', 'leaf-off-16-17545-25323', 'leaf-off-16-17545-25324', 'leaf-off-16-17545-25325', 'leaf-off-16-17546-25322', 'leaf-off-16-17546-25323', 'leaf-on-16-17544-25322', 'leaf-on-16-17544-25323', 'leaf-on-16-17545-25322', 'leaf-on-16-17545-25323', 'leaf-on-16-17545-25324', 'leaf-on-16-17545-25325', 'leaf-on-16-17546-25322', 'leaf-on-16-17546-25323', 'terrain-15-8772-12661', 'terrain-16-17544-25322', 'terrain-16-17544-25323', 'terrain-16-17545-25322', 'terrain-16-17545-25323', 'terrain-16-17545-25324', 'terrain-16-17545-25325', 'terrain-16-17546-25322', 'terrain-16-17546-25323', 'terrain-16-17546-25324', 'usgs-topo-16-17544-25322', 'usgs-topo-16-17544-25323', 'usgs-topo-16-17545-25322', 'usgs-topo-16-17545-25323', 'usgs-topo-16-17545-25324', 'usgs-topo-16-17545-25325', 'usgs-topo-16-17546-25322', 'usgs-topo-16-17546-25323'], 'originalJobs': 32, 'originalRasterTiles': 320, 'secondJobs': 12, 'secondRasterTiles': 116}
AUTHORITY_SHA='d111810d4f1226e43cfce8becf864d7a54ce9e0bd5711e8376691ef0b91f98ec'

def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)

HISTORICAL={'finalQA': {'bytes': 4780, 'generation': '1793330375899481', 'key': 'engineering/map-production/plans/94fe8e3708520332bd154ed5d759926ea60cea9b0b5d672ebab7d8152f4ba534/slots/00001/indexes/cdd62df681c6f290a93d6c0ba3e1439582909432f667f093f6e091a0acd5f0b4', 'sha256': 'cdd62df681c6f290a93d6c0ba3e1439582909432f667f093f6e091a0acd5f0b4'}, 'finalRecovery': {'bytes': 1849, 'generation': '1793330377762909', 'key': 'engineering/map-production/plans/94fe8e3708520332bd154ed5d759926ea60cea9b0b5d672ebab7d8152f4ba534/slots/00001/receipt.json', 'sha256': '736aa163445b697f82d485d070ec5aae90be3b0aaa4a82eac1aac404b6f596fa'}, 'restoredIndex': {'key': 'engineering/map-production/restorations/r4/fcdd9ba6ac9f8b61f032b28ee28aac7bcb48bf045932fcefc9f1130b7a9bbaed/preserved-jobs.json', 'generation': '1794345399715111', 'bytes': 68063, 'sha256': '278272b57c24bd01ecd9efe7503bcfb77455173d84ffb209bee2f8828aa0a394'}, 'restoredPack': {'key': 'engineering/map-production/restorations/r4/fcdd9ba6ac9f8b61f032b28ee28aac7bcb48bf045932fcefc9f1130b7a9bbaed/preserved-tiles.pack', 'generation': '1794345398952698', 'bytes': 4845866, 'sha256': 'fcdd9ba6ac9f8b61f032b28ee28aac7bcb48bf045932fcefc9f1130b7a9bbaed'}}
ARCHIVE_SHA='38f6bcb6337f8f087851d1ebbaafa5dd810a346b04c84f6fdffe892240c07290'

def validate_metadata(initial,proof,worker,recovered,records,first,qa,first_records,restored):
    h=AUTHORITY['history'];original=h['acceptedBootstrap']['key'].split('/')[3]
    second=h['secondRecovery']['key'].split('/')[3];completion=HISTORICAL['finalRecovery']['key'].split('/')[3]
    require(initial['planSHA256']==original and initial['slot']==0 and
        initial['result']['inputProofValidated'] is True and initial['result']['proofRef']==h['proof'] and
        initial['result']['acceptedBase']==proof['acceptedBase'] and
        proof['format']=='rrgh-stage-input-proof-v1','Original accepted seed proof changed')
    require(worker['planSHA256']==recovered['planSHA256']==second and worker['slot']==1 and recovered['slot']==2 and
        worker['result']['status']=='complete' and recovered['result']['status']=='verified' and
        recovered['result']['workerReceipt']==h['secondWorker'] and
        recovered['result']['historicalProofReused']==h['proof'] and
        recovered['result']['completedJobReceipts']==worker['result']['completedJobReceipts'] and
        recovered['result']['production']['jobs']==12 and recovered['result']['production']['files']==116 and
        recovered['result']['production']['priorJobsPreserved']==32 and
        recovered['result']['production']['priorRasterTilesPreserved']==320,
        'Second-stage seed independent verification changed')
    require(first['planSHA256']==completion and first['slot']==1 and
        first['result']['qaRef']==HISTORICAL['finalQA'] and
        all(first['result'][k]==qa[k] for k in qa) and
        qa['status']=='all-twelve-jobs-verified' and qa['jobs']==12 and qa['tiles']==108 and
        qa['allPreviousCachesAndJobsPreserved'] is True and qa['childrenGenerationPinned'] is True,
        'First-stage seed independent verification changed')
    require(restored['format']=='rrgh-preserved-r4-restoration-v1' and
        restored['archiveSHA256']==ARCHIVE_SHA and restored['jobCount']==12 and
        restored['rasterTiles']==172 and restored['bytes']==HISTORICAL['restoredPack']['bytes'],
        'Restored original archive identity changed')
    lookup={(e['kind'],e['path']):e for e in proof['files']}
    require(len(lookup)==len(proof['files']),'Duplicate seed input proof member')
    rows={}
    def add(receipt,outputs,kind,acceptance,reference):
        jid=receipt['job']
        require(jid not in rows and receipt['validated'] is True and
            re.fullmatch('[0-9a-f]{64}',receipt['recipeSHA256']) and outputs,
            'Invalid or duplicate accepted seed receipt')
        require(len({o['output']['path'] for o in outputs})==len(outputs),'Duplicate seed output')
        rows[jid]=dict(kind=kind,receipt=receipt,acceptance=acceptance,proof=reference,outputs=outputs)
    for receipt in proof['priorReceipts']:
        outputs=[]
        for out in receipt['outputs']:
            member=lookup.get(('prior',out['path']))
            require(member and all(member[k]==out[k] for k in ('bytes','sha256')),'Original seed output proof changed')
            outputs.append(dict(output=out,member=member,object=proof['checkpointRefs'][member['checkpointIndex']]))
        add(receipt,outputs,'original-accepted-seed',h['acceptedBootstrap'],h['proof'])
    require(len(rows)==8 and sum(len(r['outputs']) for r in rows.values())==40,'Original dependency subset changed')
    cursor=0;count=0
    for item in restored['jobs']:
        receipt=item['originalReceipt'];jid=item['job']
        require(jid==receipt['job'] and re.fullmatch(r'(leaf-on|leaf-off|usgs-topo)-16-(17544|17545)-(25322|25323)',jid),
            'Restored original job identity changed')
        outputs=[]
        for member,out in zip(item['members'],receipt['outputs'],strict=True):
            require(all(member[k]==out[k] for k in ('path','bytes','sha256')) and member['offset']==cursor and
                type(out['bytes']) is int and 0<out['bytes']<=512*1024,'Restored member differs from original receipt')
            cursor+=out['bytes'];count+=1
            outputs.append(dict(output=out,member=member,object=HISTORICAL['restoredPack']))
        add(receipt,outputs,'restored-original-accepted-seed',h['acceptedBootstrap'],HISTORICAL['restoredIndex'])
    require(len(rows)==20 and count==172 and cursor==HISTORICAL['restoredPack']['bytes'],'Restored archive inventory changed')
    def add_stage(refs,records,kind,acceptance,tiles,stage):
        require(len(refs)==len(records)==12 and len({r['key'] for r in refs})==12,'Seed stage receipt count changed')
        count=0
        for reference,row in zip(refs,records,strict=True):
            receipt=row['result']['originalReceipt'];jid=receipt['job']
            expected_plan,expected_slot=(completion,0) if stage=='first' and jid=='terrain-15-8772-12661' else (original,1) if stage=='first' else (second,1)
            prefix='engineering/map-production/plans/'+expected_plan+'/slots/'+str(expected_slot).zfill(5)+'/'
            require(row['job']==jid and row['planSHA256']==expected_plan and row['slot']==expected_slot and
                reference['key']==prefix+'jobs/'+jid+'.json','Seed checkpoint identity changed')
            outputs=[]
            for out in receipt['outputs']:
                matches=[(pack,member) for pack in row['result']['outputPacks'] for member in pack['members'] if member['path']==out['path']]
                require(len(matches)==1,'Ambiguous seed output')
                pack,member=matches[0]
                require(all(member[k]==out[k] for k in ('bytes','sha256')) and pack['ref']['key'].startswith(prefix+'outputs/'),
                    'Seed output member or namespace differs')
                outputs.append(dict(output=out,member=member,object=pack['ref']))
            count+=len(outputs);add(receipt,outputs,kind,acceptance,reference)
        require(count==tiles,'Seed stage raster inventory changed')
    add_stage(qa['completedJobReceipts'],first_records,'first-stage-accepted-seed',HISTORICAL['finalRecovery'],108,'first')
    add_stage(worker['result']['completedJobReceipts'],records,'second-stage-accepted-seed',h['secondRecovery'],116,'second')
    require(set(rows)==set(AUTHORITY['jobs']) and len(rows)==44 and sum(len(r['outputs']) for r in rows.values())==436,
        'Accepted seed union differs from the immutable44 jobs')
    return rows

def inventory(slot,authority,cache):
    require(authority==AUTHORITY and digest(authority)==AUTHORITY_SHA,'Exact accepted seed authority required')
    if AUTHORITY_SHA in cache:return cache[AUTHORITY_SHA]
    from gorge_second_stage import record
    from gorge_checkpoint import Ref
    h=authority['history']
    initial=record(slot,h['acceptedBootstrap']);proof=record(slot,h['proof'],'rrgh-stage-input-proof-v1')
    worker=record(slot,h['secondWorker']);recovered=record(slot,h['secondRecovery'])
    first=record(slot,HISTORICAL['finalRecovery'])
    qa=json.loads(slot.get(Ref(**HISTORICAL['finalQA'])))
    restored=json.loads(slot.get(Ref(**HISTORICAL['restoredIndex'])))
    refs=worker['result']['completedJobReceipts'];first_refs=qa['completedJobReceipts']
    require(len(refs)==len(first_refs)==12,'Bounded historical seed records required')
    records=[record(slot,r,'rrgh-checkpoint-job-v1') for r in refs]
    first_records=[record(slot,r,'rrgh-checkpoint-job-v1') for r in first_refs]
    rows=validate_metadata(initial,proof,worker,recovered,records,first,qa,first_records,restored)
    cache[AUTHORITY_SHA]=rows;return rows

def read(slot,authority,jid,destination,cache):
    from PIL import Image
    from gorge_second_stage import recover_catalogs
    from rrgh_verified_tile_catalog import ref
    from rrgh_overview_coverage import verify
    require(jid in authority['jobs'],'Unaccepted seed job')
    row=inventory(slot,authority,cache)[jid];layer,z,x,y=jid.rsplit('-',3);z,x,y=map(int,(z,x,y))
    paths={f'tiles/{layer}/{z}/{x}/{y}.{extension}' for extension in ('png','jpg')}
    matches=[entry for entry in row['outputs'] if entry['output']['path'] in paths]
    require(len(matches)==1,'One exact accepted seed tile required')
    entry=matches[0];out=entry['output'];member=entry['member'];obj=ref(entry['object'])
    require(0<out['bytes']<=512*1024 and 0<=member['offset'] and member['offset']+out['bytes']<=obj['bytes'],
        'Seed tile exceeds its immutable extent')
    destination=Path(destination);require(not destination.exists(),'Fresh seed readback directory required')
    recover_catalogs(slot,[dict(ref=obj,members=[{k:member[k] for k in ('path','bytes','sha256','offset')}])],[out['path']],destination)
    raw=(destination/out['path']).read_bytes()
    require(len(raw)==out['bytes'] and hashlib.sha256(raw).hexdigest()==out['sha256'],'Accepted seed tile bytes changed')
    with Image.open(io.BytesIO(raw)) as image:image.load();coverage=verify(image,z,x,y)
    return dict(tile=[layer,z,x,y],job=jid,path=out['path'],bytes=out['bytes'],sha256=out['sha256'],
        checkpointObject=obj,checkpointOffset=member['offset'],pixelReadbackVerified=True,coverage=coverage,
        sourceRecipeSHA256=row['receipt']['recipeSHA256'],seedAcceptanceProof=dict(
            format='rrgh-accepted-seed-child-v1',authoritySHA256=AUTHORITY_SHA,kind=row['kind'],
            acceptanceReceipt=row['acceptance'],originalProof=row['proof']))
