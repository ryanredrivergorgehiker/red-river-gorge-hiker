"""Exact source integration for one preserved-child overview pilot."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MODULES=('rrgh_overview_pilot.py','rrgh_verified_overview.py')
MANIFEST=ROOT/'.github/automation/overview-pilot.json'
PRIOR_MODULE_SHA256={'rrgh_overview_pilot.py':'8a77ce04f710c74082e1a2ef8e9079d6e972025e417e5594debeef15bac38d58'}
HOOKS=[
    ("    (root/'worker').mkdir(mode=0o700)\n",
     "    (root/'worker').mkdir(mode=0o700)\n    from rrgh_overview_pilot import read_dependencies\n    overview_proof=read_dependencies(slot,plan,region,root/'worker')\n"),
    ("        'campaignFence':fence,'workingCachePolicy':plan['cachePolicy'],'workerHandoff':json.loads(r.stdout)}",
     "        'campaignFence':fence,'workingCachePolicy':plan['cachePolicy'],'workerHandoff':json.loads(r.stdout),\n        'overviewPilot':overview_proof}"),
    ("        if j['operation']=='overview':raise ValueError('First sustained wave must use explicit source windows')",
     "        if j['operation']=='overview':\n            from rrgh_overview_pilot import validate_scope\n            validate_scope(plan,region,j)"),
    ("                receipt=bounded_child(slot,plan,root/'REGION-PLAN.json',job,root)\n",
     "                receipt=bounded_child(slot,plan,root/'REGION-PLAN.json',job,root)\n                from rrgh_overview_pilot import attach_proof\n                receipt=attach_proof(plan,region,receipt,initial)\n"),
    ("        qa['sourceLedgerVerification']=states;qa['parts']=parts;qa['regionComplete']=False\n",
     "        qa['sourceLedgerVerification']=states;qa['parts']=parts;qa['regionComplete']=False\n        from rrgh_overview_pilot import verify as verify_overview\n        qa['overviewPilotVerification']=verify_overview(slot,plan,region,records,root,SOURCE.parent.parent)\n"),
    ("            'allOutputHashesAndPixelsVerified':True,'allNewPackageChunksReadBack':True,'allExistingCachesPreserved':True}",
     "            'allOutputHashesAndPixelsVerified':True,'allNewPackageChunksReadBack':True,'allExistingCachesPreserved':True,\n            'overviewPilotVerification':qa.get('overviewPilotVerification')}")
]


def manifest():return json.loads(MANIFEST.read_bytes())


def strip(code):
    counts=[code.count(after) for before,after in HOOKS]
    if counts==[0]*len(HOOKS):return code
    if counts!=[1]*len(HOOKS):raise ValueError('Partial or duplicate overview integration')
    for before,after in HOOKS:code=code.replace(after,before)
    return code


def augment(code):
    from rrgh_recovery_catalog_integration import augment_campaign
    code=augment_campaign(strip(code))
    for before,after in HOOKS:
        if code.count(before)!=1:raise ValueError('Overview source anchor changed')
        code=code.replace(before,after)
    return code


def install(root):
    root=Path(root);path=root/'backend/scripts/gorge_campaign.py'
    code=augment(path.read_text())
    for name in MODULES:
        template=(ROOT/'.github/automation'/name).read_bytes();target=root/'backend/scripts'/name
        if target.exists():validate_prior_module(name,target.read_bytes(),template)
        target.write_bytes(template)
    path.write_text(code)


def validate_prior_module(name,previous,template):
    if previous!=template and hashlib.sha256(previous).hexdigest()!=PRIOR_MODULE_SHA256.get(name):
        raise ValueError('Overview module drift')


def validate_modules(root):
    for name in MODULES:
        if (Path(root)/'backend/scripts'/name).read_bytes()!=(ROOT/'.github/automation'/name).read_bytes():
            raise ValueError('Unreviewed overview module')


def pilot_job():
    from rrgh_overview_pilot import job_for
    return job_for(manifest())


def validate_previous(plan,region):
    overview=[j for j in region['jobs'] if j['operation']=='overview']
    if not overview:
        if plan.get('overviewPilot') is not None:raise ValueError('Unused overview authority')
        return
    if overview!=[pilot_job()] or plan.get('overviewPilot')!=manifest():raise ValueError('Unreviewed prior overview')
    from rrgh_overview_pilot import validate_scope
    validate_scope(plan,region,overview[0])


def select(picked,accepted,attempts,enabled):
    m=manifest();candidate=pilot_job()
    if not enabled or m['job'] in accepted or attempts.get(m['job'],0)>0:return picked,None
    if not set(m['children'])<=set(accepted):return picked,None
    result=copy.deepcopy(picked)
    choices=[i for i,j in enumerate(result) if j['layer']=='leaf-off']
    if not choices:raise ValueError('Pilot requires a native job slot to replace')
    del result[choices[-1]];result.append(candidate)
    if len(result)>12:raise ValueError('Overview cannot increase batch ceiling')
    return result,m


def validate_verification(proof):
    if proof is None:return None
    from rrgh_verified_tile_catalog import ref,require
    m=manifest();prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
    require(isinstance(proof,dict) and proof.get('job')==m['job'] and
            all(proof.get(k) is True for k in ('fourChildrenHashAndPixelVerified',
                'independentParentRecomputationMatches','sourceQualityUnchanged')) and
            proof.get('officialSourceRequests')==0,'Overview verification missing')
    children=proof.get('childProof',{})
    require(children.get('format')=='rrgh-overview-dependency-proof-v1' and children.get('job')==m['job'] and
            children.get('originalIndependentRecovery')==m['recovery'] and
            children.get('sourceRecipeSHA256')==m['sourceRecipeSHA256'] and
            children.get('officialSourceRequests')==0 and children.get('priorChildrenUnmodified') is True,
            'Overview accepted-child provenance differs')
    rows=children.get('children',[])
    require(len(rows)==4 and [r.get('job') for r in rows]==m['children'],'Four exact child jobs required')
    for row,jid in zip(rows,m['children'],strict=True):
        x,y=map(int,jid.rsplit('-',2)[1:]);receipt=ref(row['jobReceipt']);obj=ref(row['checkpointObject'])
        require(row.get('tile')==['leaf-on',16,x,y] and row.get('pixelReadbackVerified') is True and
                row.get('path') in (f'tiles/leaf-on/16/{x}/{y}.jpg',f'tiles/leaf-on/16/{x}/{y}.png') and
                receipt['key']==prefix+'slots/00001/jobs/'+jid+'.json' and
                obj['key'].startswith(prefix+'slots/00001/outputs/'),'Child checkpoint lineage differs')
        require(type(row['bytes']) is int and 0<row['bytes']<=512*1024 and
                type(row['checkpointOffset']) is int and 0<=row['checkpointOffset'] and
                row['checkpointOffset']+row['bytes']<=obj['bytes'] and
                len(row['sha256'])==64 and all(c in '0123456789abcdef' for c in row['sha256']),
                'Child checkpoint byte range invalid')
    return proof


def validate_recovery(plan,audit):
    proof=validate_verification(audit.get('overviewPilotVerification'))
    if bool(plan.get('overviewPilot'))!=bool(proof):raise ValueError('Overview recovery omitted or invented')
