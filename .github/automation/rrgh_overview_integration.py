"""Exact source integration for one preserved-child overview pilot."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MODULES=('rrgh_overview_pilot.py','rrgh_verified_overview.py','rrgh_crosswave_dependencies.py','rrgh_crosswave_runtime.py','rrgh_crosswave_batch.py','rrgh_typed_child_receipts.py')
MANIFEST=ROOT/'.github/automation/overview-pilot.json'
PRIOR_MODULE_SHA256={'rrgh_overview_pilot.py':('8a77ce04f710c74082e1a2ef8e9079d6e972025e417e5594debeef15bac38d58','5008d355028103e3cdc2beac42f98d3ee60a3a2d516057149308614ccb7fd44c')}
PRIOR_MODULE_SHA256.update({'rrgh_crosswave_dependencies.py': ('4d03849bea55f1a70e18b4210327591d61afc3c05b69099b48c042567b7a648b',), 'rrgh_crosswave_runtime.py': ('8db67538de04631995bec567af3400df2d04d9c6e638f01b06c75253a48f0fda',)})
for _name,_sha in {'rrgh_crosswave_batch.py': '8b36a38b4a7a8cbe4bccdf11886cd2497c49de88122c311b674e4c5ba7f6cf78', 'rrgh_crosswave_dependencies.py': 'b33b650c7a182bc2e9175002a75303c113d199cdd51ab281340df3f030399df9'}.items():
    PRIOR_MODULE_SHA256[_name]=PRIOR_MODULE_SHA256.get(_name,())+(_sha,)
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


def candidates():
    base=json.loads(MANIFEST.read_bytes())
    queue=json.loads((ROOT/'.github/automation/overview-candidates.json').read_bytes())
    if queue['format']!='rrgh-wave32-interior-overview-queue-v1' or queue['originalPilot']!=base['job']:
        raise ValueError('Unreviewed overview queue')
    result=[]
    for z,x,y in queue['parentsXYZ']:
        if z!=15 or type(x) is not int or type(y) is not int:raise ValueError('Unreviewed parent geometry')
        m=copy.deepcopy(base);m.update(z=z,x=x,y=y,job=f'leaf-on-{z}-{x}-{y}',
            children=[f'leaf-on-16-{2*x+dx}-{2*y+dy}' for dx in range(2) for dy in range(2)])
        result.append(m)
    if len(result)!=22 or len({m['job'] for m in result})!=22 or result[0]!=base:
        raise ValueError('Exact finite overview queue changed')
    return result


def manifest(job=None):
    for m in candidates():
        if job is None or m['job']==job:return m
    raise ValueError('Overview is outside the reviewed queue')


def strip(code):
    counts=[code.count(after) for before,after in HOOKS]
    if counts==[0]*len(HOOKS):return code
    if counts!=[1]*len(HOOKS):raise ValueError('Partial or duplicate overview integration')
    for before,after in HOOKS:code=code.replace(after,before)
    return code


PRIOR_MODULE_SHA256['rrgh_overview_pilot.py']=(*PRIOR_MODULE_SHA256.get('rrgh_overview_pilot.py',()),'6254ba3df69cbaa2f81646469dddb4cc3a661a60e803d7e54c01cd52fd908820')


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
    if previous!=template and hashlib.sha256(previous).hexdigest() not in PRIOR_MODULE_SHA256.get(name,()):
        raise ValueError('Overview module drift')


def validate_modules(root):
    for name in MODULES:
        if (Path(root)/'backend/scripts'/name).read_bytes()!=(ROOT/'.github/automation'/name).read_bytes():
            raise ValueError('Unreviewed overview module')


def pilot_job(job=None):
    from rrgh_overview_pilot import job_for
    return job_for(manifest(job))


def validate_previous(plan,region):
    if plan.get('finalOverviewPhase'):
        from rrgh_final_overviews import validate_plan,POLICY
        validate_plan(plan,region,POLICY)
        return
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_phase import validate_plan,POLICY
        validate_plan(plan,region,plan['crosswavePhase']['authority'])
        return
    overview=[j for j in region['jobs'] if j['operation']=='overview']
    if not overview:
        if plan.get('overviewPilot') is not None:raise ValueError('Unused overview authority')
        return
    if len(overview)!=1 or overview!=[pilot_job(overview[0]['id'])] or plan.get('overviewPilot')!=manifest(overview[0]['id']):
        raise ValueError('Unreviewed prior overview')
    from rrgh_overview_pilot import validate_scope
    validate_scope(plan,region,overview[0])


def select(picked,accepted,attempts,enabled):
    if not enabled:return picked,None
    queue=candidates()
    # Later parents are eligible only after the original pilot is present in
    # the independently recovered, publisher-validated accepted ledger.
    # An attempted or failed pilot cannot silently activate the broader queue.
    if queue[0]['job'] not in accepted:queue=queue[:1]
    eligible=[m for m in queue if m['job'] not in accepted and attempts.get(m['job'],0)==0
              and set(m['children'])<=set(accepted)]
    if not eligible:return picked,None
    m=eligible[0];candidate=pilot_job(m['job'])
    result=copy.deepcopy(picked)
    choices=[i for i,j in enumerate(result) if j['layer']=='leaf-off']
    if not choices:raise ValueError('Pilot requires a native job slot to replace')
    del result[choices[-1]];result.append(candidate)
    if len(result)>12:raise ValueError('Overview cannot increase batch ceiling')
    return result,m


def validate_verification(proof):
    if isinstance(proof,dict) and proof.get('format')=='rrgh-final-overview-verification-v1':
        from rrgh_final_overviews import validate_verification as final
        return final(proof)
    if proof is None:return None
    if isinstance(proof,dict) and proof.get('format')=='rrgh-crosswave-batch-verification-v2':
        from rrgh_crosswave_batch import validate_verification as batch
        return batch(proof)
    if isinstance(proof,dict) and proof.get('format')=='rrgh-crosswave-verification-v1':
        from rrgh_crosswave_runtime import validate_verification as validate_crosswave
        return validate_crosswave(proof)
    from rrgh_verified_tile_catalog import ref,require
    if not isinstance(proof,dict):raise ValueError('Invalid overview proof')
    m=manifest(proof.get('job'));prefix='engineering/map-production/plans/'+m['sourcePlanSHA256']+'/'
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
    if bool(plan.get('overviewPilot') or plan.get('crosswavePhase') or plan.get('finalOverviewPhase'))!=bool(proof):raise ValueError('Overview recovery omitted or invented')
    if plan.get('finalOverviewPhase'):
        from rrgh_final_overviews import digest,VERIFY
        if proof['format']!=VERIFY or proof['phaseSHA256']!=digest(plan['finalOverviewPhase']) or proof['planSHA256']!=audit['planSHA256'] or [p['job'] for p in proof['parents']]!=plan['approvedJobIDs']:
            raise ValueError('Final overview recovery belongs to another plan')
        return
    if plan.get('crosswavePhase',{}).get('format')=='rrgh-crosswave-batch-phase-v2':
        from rrgh_crosswave_batch import digest
        if proof['phaseSHA256']!=digest(plan['crosswavePhase']) or proof['planSHA256']!=audit['planSHA256'] or [p['job'] for p in proof['parents']]!=plan['approvedJobIDs']:
            raise ValueError('Batch recovery belongs to another plan')
        return
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_runtime import PHASE_SHA
        if proof.get('phaseSHA256')!=PHASE_SHA or proof.get('bindings')!=plan['crosswavePhase']['bindings']:
            raise ValueError('Cross-wave recovery belongs to another plan')
