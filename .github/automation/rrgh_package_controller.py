"""Receipt-bound package succession without moving the accepted source branch."""
import copy
import json
import os
from pathlib import Path
import re
import sys

from rrgh_package_authority import digest,require
import rrgh_package_contract as contract
from rrgh_package_funding import settle


def reports(lines,phase):
    result=[]
    for line in lines:
        if '"phase": "'+phase+'"' not in line:continue
        try:row=json.loads(line[line.index('{'):])
        except (ValueError,TypeError):continue
        if row.get('phase')==phase:result.append(row)
    require(len(result)==1,'Exactly one package receipt report required')
    return result[0]


def audit_run(state,plan,run,jobs,stage_lines,verify_lines):
    from rrgh_dispatcher import REPO,WORKER,WORKFLOW
    from rrgh_verified_tile_catalog import ref
    require(run.get('repository',{}).get('full_name')==REPO and
        run.get('head_branch')==WORKER and run.get('event')=='workflow_dispatch' and
        run.get('path')=='.github/workflows/'+WORKFLOW and
        run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('run_attempt')==1 and run.get('id')==state['runID'] and
        run.get('display_title')==f"RRGH package {state['sequence']} {state['dispatchID']}" and
        run.get('status') in ('in_progress','completed'), 'Package execution ownership changed')
    for name in ('admit','package-stage','package-verify'):
        selected=[j for j in jobs if j['name']==name]
        require(len(selected)==1 and selected[0]['conclusion']=='success' and
                selected[0]['status']=='completed','Incomplete package worker verification')
    stage=reports(stage_lines,'final-package-stage');verified=reports(verify_lines,'final-package-verify')
    prefix='engineering/map-production/plans/'+digest(plan)+'/slots/'
    for report,index in ((stage,0),(verified,1)):
        ref(report['receiptRef'])
        require(report['receiptRef']['key']==prefix+f'{index:05d}/receipt.json' and
                report['receiptRef']['bytes']<=16384 and
                report['result']['packagePlanSHA256']==digest(plan) and
                report['result']['operation']==plan['finalPackagePhase']['operation'] and
                report['result']['sourceRequests']==report['result']['sourceBytes']==0,
                'Package receipt allocation or source-free scope changed')
    result=verified['result']
    require(stage['result']['status']=='staged' and result['status']=='verified' and
        result['workerReceipt']==stage['receiptRef'] and result['authoritySHA256']==state['package']['authoritySHA256'] and
        result['ordinal']==state['package']['ordinal'] and result['rasterTiles']==278278 and
        result['finalPackageDeliveryComplete'] is False and result['physicalIPhoneTestComplete'] is False,
        'Package verification receipt lineage changed')
    ref(result['checkpoint'])
    require(result['checkpoint']['key'].startswith(prefix+'00001/indexes/') and
        result['checkpoint']['bytes']<=2**20 and
        result['settlement']==settle(plan,result['settlement']['observedUsage'],True),
        'Package checkpoint or budget settlement changed')
    next_op=result['nextOperation']
    require(result['packageBytesIndependentlyVerified']==(next_op is None), 'False package completion flag')
    op=result['operation']
    if op['kind']=='inventory':
        require(next_op is not None and ((next_op['kind']=='inventory' and next_op['start']==op['stop']) or
                next_op['kind']=='layout'),'Package metadata queue skipped a prerequisite')
    elif op['kind']=='layout':require(next_op is not None and next_op['kind']=='parts','Layout did not lead to parts')
    elif op['kind'] in ('part','parts'):require(next_op is not None and next_op['kind'] in ('part','parts','indexes'),'Part skipped indexes')
    elif op['kind']=='indexes':
        require(next_op is None and result['verifiedIndexes']==3 and result['catalogCandidates'],
                'Final indexes incomplete')
        ref(result['catalogCandidates'])
    else:raise ValueError('Unreviewed package operation')
    return dict(result,receiptRef=verified['receiptRef'])


def source_context(source,state):
    import subprocess
    from rrgh_dispatcher import config
    source=Path(source).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    require(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==state['sourceSHA'],
            'Package source checkout differs from accepted anchor')
    _,plan,_=config(source)
    return plan,contract.authority(source,plan,state)


def enroll(api,root,source):
    from rrgh_dispatcher import validate_state,audit_state,assert_no_other_producers,dispatch
    old,state=api.state();validate_state(state,root)
    require(state['enabled'] is True and state['status']=='completion-waiting' and
        state['mode']=='produce' and 'package' not in state,'Only exact raster completion can enroll packages')
    assert_no_other_producers(api)
    source_plan,auth=source_context(source,state)
    audit=audit_state(api,root,state)
    require(audit['acceptedRasterTiles']==278278 and audit['acceptedJobs']==34750 and
        audit['receiptRef']==state['checkpoint'] and audit['nextCarry']['priorRasterTiles']==278278,
        'Raster completion independent audit changed')
    cursor,_,_=contract.allocate(source_plan,state,auth,contract.inventory_operation(auth,0),
                                audit['nextCarry'],0,None)
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'enroll bounded source-free final package assembly')
    return dispatch(api,root,old,state,'package')


def finish(api,root,source,recovering=False):
    from rrgh_dispatcher import current_run,read_audit_run,dispatch
    from rrgh_dispatch_audit import gh
    old,state=current_run(api,root,'halted' if recovering else 'running')
    require(state['mode']=='package','Wrong package controller mode')
    source_plan,auth=source_context(source,state);plan,_=contract.funding(source_plan,state,auth)
    run=read_audit_run(api,state['runID']);response=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
    jobs=response['jobs'];require(response['total_count']==len(jobs)<=100,'Incomplete package job inventory')
    lines={}
    for name in ('package-stage','package-verify'):
        selected=[j for j in jobs if j['name']==name];require(len(selected)==1,'Ambiguous package worker')
        lines[name]=gh('actions/jobs/'+str(selected[0]['id'])+'/logs',api.token,raw=True).splitlines()
    result=audit_run(state,plan,run,jobs,lines['package-stage'],lines['package-verify'])
    previous=state['runID']
    summary={k:result[k] for k in ('ordinal','operation','receiptRef','checkpoint','inventorySlices',
        'verifiedParts','verifiedIndexes','packageBytesIndependentlyVerified','catalogCandidates')}
    summary.update(runID=previous,planSHA256=digest(plan))
    if result['nextOperation'] is None:
        state['package'].update(status='verified-awaiting-catalog',carry=result['settlement']['nextCarry'],
            lastVerified=summary,verifiedCheckpoint=result['checkpoint'])
        state.update(status='package-validation-waiting')
        api.cas(old,state,'all package bytes independently verified; catalog activation and phone test pending')
        return dict(status='PACKAGE_BYTES_VERIFIED',verifiedParts=result['verifiedParts'],verifiedIndexes=3,
            acceptedRasterTiles=278278,remainingRasterTiles=0,finalPackageDeliveryComplete=False,
            physicalIPhoneTestComplete=False,catalogCandidates=result['catalogCandidates'])
    cursor,_,_=contract.allocate(source_plan,state,auth,result['nextOperation'],result['settlement']['nextCarry'],
                                state['package']['ordinal']+1,result['checkpoint'])
    cursor['lastVerified']=summary
    if state['package'].get('retainedFailures'):cursor['retainedFailures']=state['package']['retainedFailures']
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'independently verified package operation; allocate exact successor')
    return dispatch(api,root,old,state,'package',allowed_run=previous)


def recovery_allocation(source_plan,state,auth,error):
    """A failed operation may use two new allocations; no old claim is replayed."""
    plan,_=contract.funding(source_plan,state,auth);p=state['package']
    require(error['phase']=='final-package-error' and error['packagePlanSHA256']==digest(plan) and
        error['workerPhase'] in ('stage','verify') and error['transientTransport'] is True and
        error['entireAllocationRetained'] is True and error['sourceRequests']==0 and
        p.get('retryCount',0)<2,'Package failure is not eligible for bounded transport recovery')
    retained=settle(plan,dict.fromkeys(plan['limits'],0),False)
    cursor,_,_=contract.allocate(source_plan,state,auth,p['operation'],retained['nextCarry'],
                                p['ordinal']+1,p['previousCheckpoint'])
    cursor['retryCount']=p.get('retryCount',0)+1
    cursor['retainedFailures']=copy.deepcopy(p.get('retainedFailures',[]))+[dict(
        runID=state['runID'],dispatchID=state['dispatchID'],ordinal=p['ordinal'],planSHA256=digest(plan),
        operation=copy.deepcopy(p['operation']),settlement=retained,errorClass=error['errorClass'])]
    require(len(cursor['retainedFailures'])<=24,'Cumulative package recovery ceiling reached')
    if p.get('lastVerified'):cursor['lastVerified']=copy.deepcopy(p['lastVerified'])
    return cursor


def recover(api,root,source):
    from rrgh_dispatcher import validate_state,dispatch,read_audit_run
    from rrgh_dispatch_audit import gh
    old,state=api.state();validate_state(state,root)
    run_id=int(os.environ['GITHUB_RUN_ID'])
    if state.get('package',{}).get('lastVerified',{}).get('runID')==run_id and state['runID']!=run_id:
        return dict(status='PACKAGE_SUCCESSOR_PRESERVED',sourceWrites=0,producerReplays=0)
    require(state['status']=='halted' and state['mode']=='package' and state['runID']==run_id and
            state['dispatchID']==os.environ['RRGH_DISPATCH_ID'],'Wrong halted package owner')
    run=read_audit_run(api,run_id)
    response=api.call('GET','actions/runs/'+str(run_id)+'/jobs?per_page=100')
    require(response['total_count']==len(response['jobs'])<=100,'Incomplete package recovery job inventory')
    selected={name:[j for j in response['jobs'] if j['name']==name] for name in ('package-stage','package-verify')}
    require(all(len(v)==1 for v in selected.values()),'Ambiguous package recovery workers')
    if all(v[0]['conclusion']=='success' for v in selected.values()):
        return finish(api,root,source,recovering=True)
    failed=[(name,v[0]) for name,v in selected.items() if v[0]['conclusion']=='failure']
    require(len(failed)==1 and all(v[0]['status']=='completed' for v in selected.values()),
            'Only one conclusively failed package worker can recover')
    name,job=failed[0]
    lines=gh('actions/jobs/'+str(job['id'])+'/logs',api.token,raw=True).splitlines()
    error=reports(lines,'final-package-error')
    require(error['workerPhase']==('stage' if name=='package-stage' else 'verify'),
            'Transport failure phase differs from failed worker')
    source_plan,auth=source_context(source,state)
    cursor=recovery_allocation(source_plan,state,auth,error)
    state.update(package=cursor,status='package-ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'retain failed package allocation; fund bounded transport recovery')
    return dispatch(api,root,old,state,'package',allowed_run=run_id)


def main():
    from rrgh_dispatcher import GitHub,caller
    command=sys.argv[1];require(command in ('enroll','finish','recover'),'Unknown package command')
    caller('launch' if command=='enroll' else 'package')
    result={'enroll':enroll,'finish':finish,'recover':recover}[command](GitHub(os.environ['GH_TOKEN']),Path('.'),sys.argv[2])
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
