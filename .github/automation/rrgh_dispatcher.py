#!/usr/bin/env python3
"""Authenticated production succession with durable GitHub CAS ownership.

GITHUB_TOKEN is confined to trusted controller code. Source planning runs in a
separate token-free step. A claim is persisted BEFORE each dispatch; ambiguous
HTTP failures retain it and are never blindly retried. Cloud slots add their
existing create-only campaign/plan fences and independent recovery protections.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO='ryanredrivergorgehiker/red-river-gorge-hiker'
WORKER='lane20/offline-production-preflight-20261029'
SOURCE='lane20/map-producer-iam-design-20261029'
WORKFLOW='offline-map-restricted-dispatch.yml'
STATE='.github/automation/rrgh-controller-state.json'
ORIGINAL='.github/workflows/offline-map-producer-access.yml'
LEGACY_PLANNER='.github/workflows/rrgh-push-successor-planning.yml'
LEGACY_SUPERVISOR='lane20/unattended-supervisor-20261031'
CODE_FILES=['.github/automation/'+x for x in (
    'rrgh_dispatcher.py','rrgh_dispatch_audit.py','rrgh_prepare_dispatch_successor.py',
    'rrgh_campaign_budget_v2.py','rrgh_expanded_production.py','rrgh_source_window_intake.py',
    'rrgh_required_inventory.py','expanded-source-rights-20261102.json',
    'source-templates/benchmark_gorge_pipeline.py')] + [
    'backend/config/official-source-intake-20261102/official-source-candidates.json'] + ['.github/workflows/'+x for x in (
    WORKFLOW,'rrgh-controller-launch.yml')]


class Halt(Exception):pass


def guard(ok,message):
    if not ok:raise Halt(message)


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def digest(raw):return hashlib.sha256(raw).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class GitHub:
    def __init__(self,token):
        guard(bool(token),'GitHub credential absent');self.token=token
    def call(self,method,path,payload=None):
        guard(not path.startswith('/') and '..' not in path,'Unsafe GitHub resource')
        raw=canonical(payload) if payload is not None else None
        req=Request('https://api.github.com/repos/'+REPO+'/'+path,data=raw,method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                     'Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'})
        try:
            with build_opener(NoRedirect).open(req,timeout=40) as response:body=response.read(8_000_001)
        except HTTPError as exc:
            raise Halt('GitHub '+method+' '+path.split('?')[0]+' HTTP '+str(exc.code)+'; no automatic retry') from None
        guard(len(body)<=8_000_000,'GitHub response limit exceeded')
        return json.loads(body) if body else {}
    def file(self,path,ref=WORKER):
        obj=self.call('GET','contents/'+path+'?ref='+quote(ref,safe=''))
        return obj,base64.b64decode(obj['content'])
    def state(self):
        blob,raw=self.file(STATE);return blob['sha'],json.loads(raw)
    def cas(self,old_sha,state,message):
        result=self.call('PUT','contents/'+STATE,{'message':'Lane20 controller: '+message+' [skip ci]',
            'branch':WORKER,'sha':old_sha,'content':base64.b64encode(canonical(state)).decode()})
        return result['content']['sha']


def local_digest(root):
    return digest(canonical({p:digest((Path(root)/p).read_bytes()) for p in CODE_FILES}))


def validate_state(state,root,allow_upgrade=False):
    guard(state.get('format')=='rrgh-controller-state-v1' and state.get('owner')=='autonomous-v1'
          and state.get('epoch')==1,'Exclusive controller owner missing')
    current=local_digest(root)
    if state.get('controlDigest')!=current:
        upgrade=state.get('pendingControllerUpgrade',{})
        guard(allow_upgrade and state.get('status')=='dispatching' and
              upgrade.get('fromDigest')==state.get('controlDigest') and
              upgrade.get('toDigest')==current and
              upgrade.get('authorizedBy')=='ryanredrivergorgehiker' and
              upgrade.get('authorizedOn')=='2026-11-02' and
              upgrade.get('preserveAcceptedHistory') is True,
              'Reviewed controller code changed')
    guard(type(state.get('sequence')) is int and state['sequence']>=58,'Bad sequence')
    guard(re.fullmatch(r'[0-9a-f]{40}',state.get('sourceSHA','')) is not None and
          re.fullmatch(r'[0-9a-f]{64}',state.get('planSHA256','')) is not None,'Bad source/plan binding')


def caller(mode):
    guard(os.environ.get('GITHUB_REPOSITORY')==REPO and os.environ.get('GITHUB_REF')=='refs/heads/'+WORKER
          and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','Wrong repository/branch or rerun')
    if mode=='launch':
        guard(os.environ.get('GITHUB_EVENT_NAME')=='push' and
              os.environ.get('GITHUB_ACTOR')=='ryanredrivergorgehiker' and
              os.environ.get('GITHUB_WORKFLOW_REF')==REPO+'/.github/workflows/rrgh-controller-launch.yml@refs/heads/'+WORKER,
              'Only the owner-authenticated launch or resume is allowed')
    else:
        guard(os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and
              os.environ.get('GITHUB_ACTOR')=='github-actions[bot]' and
              os.environ.get('GITHUB_WORKFLOW_REF')==REPO+'/.github/workflows/'+WORKFLOW+'@refs/heads/'+WORKER,
              'Wrong authenticated dispatcher identity')


def assert_no_other_producers(api,allowed_run=None):
    paths={ORIGINAL,'.github/workflows/'+WORKFLOW}
    for status in ('queued','in_progress','waiting','pending','requested'):
        page=1;seen=0
        while True:
            data=api.call('GET',f'actions/runs?status={status}&per_page=100&page={page}')
            runs=data.get('workflow_runs',[]);seen+=len(runs)
            guard(not any(r.get('path') in paths and r.get('id')!=allowed_run for r in runs),'Another producer is active')
            if seen>=data.get('total_count',0):break
            guard(bool(runs) and page<20,'Active-run pagination incomplete');page+=1


def dispatch(api,root,state_sha,state,mode,allowed_run=None):
    validate_state(state,root)
    guard(state.get('enabled') is True,'Controller paused')
    guard(state['status'] in (('awaiting-auth','auth-required','ready') if mode=='probe' else ('ready',)),
          'Allocation already claimed, running or unresolved')
    if mode=='probe' and state['status']=='ready':
        previous=state.get('lastRecovered',{})
        guard(state.get('runID') is None and state.get('dispatchID') is None and
              previous.get('sequence')==state['sequence']-1 and
              isinstance(previous.get('runID'),int) and previous['runID']>0 and
              bool(state.get('checkpoint')) and
              previous.get('recoveryReceipt')==state['checkpoint'],
              'Prepared resume lacks an exact recovered predecessor')
    policy=state.get('githubBudgetPolicy',{})
    guard(policy.get('enforcement')=='github-platform' and
          policy.get('authorizedBy')=='ryanredrivergorgehiker' and
          policy.get('authorizedOn')=='2026-11-02' and
          policy.get('stopProtectionConfirmedByOwner') is True,
          'Owner-authorized GitHub platform budget policy missing')
    assert_no_other_producers(api,allowed_run)
    _,legacy=api.file(ORIGINAL)
    guard(digest(legacy)==state.get('legacyFenceSHA256') and
          b'# RRGH_LEGACY_INITIATION_FENCED_EPOCH_1' in legacy and b'if: false' in legacy,
          'Legacy producer fence missing')
    _,planner=api.file(LEGACY_PLANNER,ref=LEGACY_SUPERVISOR)
    guard(digest(planner)==state.get('legacyPlannerFenceSHA256') and b'if: false' in planner,
          'Legacy source writer fence missing')
    head=api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']
    guard(head==state['sourceSHA'],'Source lease moved')
    current=copy.deepcopy(state)
    # The owner retired the stale October estimate on 2026-11-02. GitHub's
    # account-level stop protection is authoritative; do not invent a second bill.
    current['launchCounter']=current.get('launchCounter',0)+1
    current['dispatchID']=digest(canonical({'epoch':current['epoch'],'plan':current['planSHA256'],
        'counter':current['launchCounter'],'mode':mode}))
    current.update(status='dispatching',mode=mode,runID=None,parentRunID=allowed_run)
    # CAS precedes API dispatch. Any exception after here leaves a durable claim.
    api.cas(state_sha,current,'claim '+mode+' '+current['dispatchID'])
    api.call('POST','actions/workflows/'+WORKFLOW+'/dispatches',{'ref':WORKER,'inputs':{
        'mode':mode,'source_sha':current['sourceSHA'],'plan_sha256':current['planSHA256'],
        'sequence':str(current['sequence']),'dispatch_id':current['dispatchID']}})
    return {'status':'DISPATCH_ACCEPTED','mode':mode,'sequence':current['sequence'],
            'dispatchID':current['dispatchID'],'independentRecoveryComplete':False}


def claim(api,root,inputs,run_id):
    old,state=api.state();validate_state(state,root,allow_upgrade=True)
    guard(state.get('enabled') is True and state['status']=='dispatching' and state.get('runID') is None,
          'Duplicate or disabled dispatch')
    for field,key in [('source_sha','sourceSHA'),('plan_sha256','planSHA256'),('dispatch_id','dispatchID'),('mode','mode')]:
        guard(inputs[field]==state[key],'Dispatch input differs from durable claim: '+field)
    guard(inputs['sequence']==str(state['sequence']),'Dispatch sequence mismatch')
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    if state['controlDigest']!=local_digest(root):
        upgrade=state.pop('pendingControllerUpgrade')
        state.setdefault('controllerUpgradeHistory',[]).append({**upgrade,'claimedRunID':run_id,
            'sequence':state['sequence']})
        state['controlDigest']=upgrade['toDigest']
        state['sourcePolicyMode']='expanded'
    state['status']='probing' if inputs['mode']=='probe' else 'running';state['runID']=run_id
    api.cas(old,state,'worker claimed '+state['dispatchID'])
    return state


def current_run(api,root,status):
    old,state=api.state();validate_state(state,root)
    guard(state.get('status')==status and str(state.get('runID'))==os.environ.get('GITHUB_RUN_ID') and
          state.get('dispatchID')==os.environ.get('RRGH_DISPATCH_ID'),'Current execution no longer owns claim')
    return old,state


def audit_current(api,root):
    _,state=current_run(api,root,'running')
    return audit_state(api,root,state)


def audit_state(api,root,state,allow_failed_controller=False):
    rid=state['runID']
    run=api.call('GET','actions/runs/'+str(rid))
    jobs=api.call('GET','actions/runs/'+str(rid)+'/jobs?per_page=100')
    guard(jobs['total_count']<=100,'Job pagination not complete')
    from rrgh_dispatch_audit import audit_run,gh
    selected={name:[j for j in jobs['jobs'] if j['name']==name] for name in ('bounded-stage','independent-recovery')}
    guard(all(len(v)==1 for v in selected.values()),'Producer/recovery job multiplicity')
    logs={name:gh('actions/jobs/'+str(items[0]['id'])+'/logs',api.token,raw=True).splitlines()
          for name,items in selected.items()}
    report=audit_run(run,jobs['jobs'],logs['independent-recovery'],logs['bounded-stage'],
        expected_dispatch=state,allow_failed_controller=allow_failed_controller)
    guard(report['planSHA256']==state['planSHA256'] and report['wave']==state['sequence'],'Recovery identity changed')
    report['controllerDispatchID']=state['dispatchID'];report['controllerParentRun']=state.get('parentRunID')
    report['sourcePolicyMode']=state.get('sourcePolicyMode','expanded')
    return report


def audit_recovered(api,root):
    caller('launch')
    _,state=api.state();validate_state(state,root)
    guard(state.get('enabled') is True and state.get('status')=='halted' and state.get('mode')=='produce',
          'Only a halted independently recovered production allocation can advance')
    auth=state.get('recoveredResumeAuthorization',{})
    guard(auth.get('authorizedBy')=='ryanredrivergorgehiker' and auth.get('authorizedOn')=='2026-11-02' and
          all(auth.get(k)==state.get(k) for k in ('runID','planSHA256','sourceSHA','dispatchID')),
          'Exact owner-authorized recovered continuation missing')
    assert_no_other_producers(api)
    report=audit_state(api,root,state,allow_failed_controller=True)
    guard(report['receiptRef']==auth.get('recoveryReceipt'), 'Reviewed independent recovery changed')
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    return report


def config(root,original=False):
    root=Path(root)
    code=(subprocess.check_output(['git','-C',str(root),'show','HEAD:backend/scripts/gorge_campaign.py'],text=True)
          if original else (root/'backend/scripts/gorge_campaign.py').read_text())
    match=re.search(r"CONFIG=SOURCE.parent/'config/(gorge-campaign-wave-\d{3,9}-\d{8})'",code)
    guard(match is not None,'Unknown source configuration pointer')
    folder=root/'backend/config'/match.group(1)
    return folder,json.loads((folder/'PLAN.json').read_bytes()),code


def candidate_entries(source_root,audit,state):
    root=Path(source_root)
    parent=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    guard(parent==state['sourceSHA'],'Local source parent differs from durable ownership')
    old_dir,prior,old_code=config(root,True);new_dir,plan,new_code=config(root)
    guard(digest(canonical(prior))==state['planSHA256']==audit['planSHA256'],'Prior plan differs from recovery')
    guard(new_dir!=old_dir and plan['campaign']['sequence']==prior['campaign']['sequence']+1,'Allocation not advanced')
    guard(plan['campaign']['previousRecovery']==audit['receiptRef'] and plan['campaign']['carry']==audit['nextCarry'],
          'Exact predecessor settlement lost')
    guard(plan['campaign']['controllerEpoch']==state['epoch'] and plan['campaign']['ceilingUSD']=='125.00' and
          plan['campaign']['storageTargetUSDPerMonth']=='2.00','Authority changed')
    jobs=plan['approvedJobIDs']
    guard(0<len(jobs)<=512 and len(set(jobs))==len(jobs) and
          not set(jobs)&set(plan['completedJobIDs']) and
          all(plan['priorAttemptCounts'].get(j,0)==0 for j in jobs),'Replayed or malformed successor jobs')
    guard(len(plan['completedJobIDs'])==len(set(plan['completedJobIDs']))==audit['acceptedJobs'],'Accepted inventory mismatch')
    guard(new_code==old_code.replace(old_dir.name,new_dir.name),'Unreviewed source code edit')
    from rrgh_expanded_production import validate_publication, ENGINE
    validate_publication(root,old_dir,new_dir,plan,audit)
    guard(plan['limits']=={**prior['limits'],'attempts':len(jobs)} and plan['maxConcurrency']==1 and
          plan['automaticRetryPermitted'] is False and plan['deleteAllowed'] is False,'Resource/protection drift')
    snapshot={p.name:digest(p.read_bytes()) for p in sorted((root/'backend/scripts').glob('*.py')) if not p.name.startswith('test_')}
    guard(digest(canonical(snapshot))==plan['sourceSnapshotSHA256'],'Executable source snapshot mismatch')
    allowed={str(new_dir.relative_to(root)/name) for name in ('PLAN.json','ALLOWANCE.json','REGION-PLAN.json.z.b64')}
    allowed.add('backend/scripts/gorge_campaign.py')
    before_engine=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+ENGINE])
    if (root/ENGINE).read_bytes()!=before_engine:allowed.add(ENGINE)
    changed=subprocess.check_output(['git','-C',str(root),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
    guard(set(changed)==allowed,'Unexpected files in source publication')
    allowance=json.loads((new_dir/'ALLOWANCE.json').read_bytes())['cloudStorageAllowance']
    plan_hash=digest(canonical(plan))
    guard(allowance['planSHA256']==plan_hash,'Wrong allowance plan')
    guard(Decimal(audit['nextCarry']['chargedUSD'])+Decimal(allowance['reservedWorstCaseUSD'])<=Decimal('123'),
          'Protected completion reserve exhausted')
    entries=[]
    for name in sorted(allowed):
        raw=(root/name).read_bytes();guard(0<len(raw)<=2_000_000,'Source publication file bound')
        entries.append({'path':name,'mode':'100644','type':'blob','content':raw.decode()})
    return parent,plan_hash,plan,entries


def publish_and_advance(api,root,source_root,audit,recovered=False):
    if recovered:
        caller('launch');old,state=api.state();validate_state(state,root)
    else:
        old,state=current_run(api,root,'running')
    guard(state.get('enabled') is True,'Controller paused after recovery')
    # Re-read live successful producer/recovery evidence; do not trust a caller's flag.
    guard((audit_recovered(api,root) if recovered else audit_current(api,root))==audit,
          'Audit does not match live independent recovery')
    parent,plan_hash,plan,entries=candidate_entries(source_root,audit,state)
    assert_no_other_producers(api,state['runID'])
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==parent,'Source publication lease moved')
    state['status']='publishing';state['recoveredReceipt']=audit['receiptRef']
    state.pop('recoveredResumeAuthorization',None)
    old=api.cas(old,state,'recovered '+state['dispatchID'])
    base=api.call('GET','git/commits/'+parent)
    tree=api.call('POST','git/trees',{'base_tree':base['tree']['sha'],'tree':entries})
    commit=api.call('POST','git/commits',{'message':'Lane20: autonomous immutable wave '+str(plan['campaign']['sequence'])+' [skip ci]',
        'tree':tree['sha'],'parents':[parent]})
    api.call('PATCH','git/refs/heads/'+SOURCE,{'sha':commit['sha'],'force':False})
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==commit['sha'],'Published source readback mismatch')
    completed={'runID':state['runID'],'sequence':state['sequence'],'dispatchID':state['dispatchID'],
        'parentRunID':state.get('parentRunID'),'sourceSHA':state['sourceSHA'],'planSHA256':state['planSHA256'],
        'recoveryReceipt':audit['receiptRef'],'acceptedJobs':audit['acceptedJobs'],
        'acceptedRasterTiles':audit['acceptedRasterTiles'],'jobsNew':audit['jobsNew']}
    state.update(status='ready',sequence=plan['campaign']['sequence'],sourceSHA=commit['sha'],planSHA256=plan_hash,
        checkpoint=audit['receiptRef'],lastRecovered=completed,runID=None,dispatchID=None)
    old=api.cas(old,state,'successor source prepared')
    return dispatch(api,root,old,state,'produce',allowed_run=completed['runID'])


def probe_source(source_root,state):
    """One bounded authenticated readback; no GCS creation, slot consumption or IAM write."""
    sys.path.insert(0,str(Path(source_root)/'backend/scripts'))
    from gorge_campaign import configuration
    from gorge_checkpoint import GCS,Ref,decode_record
    from run_gorge_checkpoint_slot import token
    from gorge_producer_identity import validate_context
    validate_context(os.environ)
    plan,evidence,_=configuration()
    guard(digest(canonical(plan))==state['planSHA256'],'Probe source plan mismatch')
    store=GCS(plan,evidence,token)
    ref=Ref(**state['checkpoint'])
    raw=store.read(ref,0,ref.bytes)
    guard(digest(raw)==ref.sha256,'Authenticated predecessor readback hash mismatch')
    previous=decode_record(raw)['result']
    guard(previous['status']=='verified' and previous['nextCarry']==plan['campaign']['carry'],
          'Authenticated previous recovery mismatch')
    # A consumed same-sequence fence or either old/new bootstrap claim forbids activation.
    keys=['engineering/map-production/campaigns/'+plan['campaign']['id']+f"/wave-{state['sequence']:05d}.json"]
    for plan_hash in (state['planSHA256'],state['replacedPreparedPlanSHA256']):
        keys.append('engineering/map-production/plans/'+plan_hash+'/slots/00000/claim.json')
    for key in keys:
        req=Request('https://storage.googleapis.com/storage/v1/b/'+plan['bucket']+'/o/'+quote(key,safe='')+'?fields=generation',
                    headers={'Authorization':'Bearer '+token()})
        try:
            with build_opener(NoRedirect).open(req,timeout=25) as response:response.read(16385)
        except HTTPError as exc:
            guard(exc.code==404,'Unable to establish unconsumed allocation')
        else:raise Halt('Existing Cloud claim: reconcile; never replay')
    return {'authenticatedPredecessorReadback':True,'unconsumedSequenceVerified':True,
            'sourceContextPassed':True,'cloudWrites':0,'receiptSHA256':ref.sha256}


def retain_failure(api,root,run_id,dispatch_id):
    old,state=api.state();validate_state(state,root)
    previous=state.get('lastRecovered',{})
    if (previous.get('runID')==run_id and previous.get('dispatchID')==dispatch_id and
            previous.get('sequence')==state['sequence']-1 and
            bool(state.get('checkpoint')) and previous.get('recoveryReceipt')==state['checkpoint']):
        # Recovery was already committed and ownership advanced. Keep the new
        # allocation intact, including any ambiguous dispatch claim; never replay.
        return {'status':'RECOVERED_SUCCESSOR_PRESERVED','runID':run_id,
                'successorSequence':state['sequence'],'successorStatus':state['status'],
                'automaticRetryPermitted':False,'stateChanged':False}
    guard(str(state.get('runID'))==str(run_id) and state.get('dispatchID')==dispatch_id,
          'Failed run cannot modify another allocation')
    state['status']='auth-required' if state.get('mode')=='probe' else 'halted'
    state['failureRunID']=run_id
    api.cas(old,state,'failure retained; no automatic retry')
    return {'status':state['status'],'runID':run_id,'automaticRetryPermitted':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['launch','claim','audit','publish','probe','activate','failed','audit-recovered','publish-recovered'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--source',type=Path)
    p.add_argument('--audit',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();caller('launch' if a.command.endswith('-recovered') else a.command)
    api=GitHub(os.environ.get('GH_TOKEN',''));run_id=int(os.environ['GITHUB_RUN_ID'])
    if a.command=='launch':
        old,state=api.state();result=dispatch(api,a.root,old,state,'probe')
    elif a.command=='claim':
        inputs={k:os.environ['INPUT_'+k.upper()] for k in ('mode','source_sha','plan_sha256','sequence','dispatch_id')}
        result=claim(api,a.root,inputs,run_id)
    elif a.command=='audit':result=audit_current(api,a.root)
    elif a.command=='audit-recovered':result=audit_recovered(api,a.root)
    elif a.command=='publish-recovered':result=publish_and_advance(api,a.root,a.source,json.loads(a.audit.read_bytes()),recovered=True)
    elif a.command=='publish':result=publish_and_advance(api,a.root,a.source,json.loads(a.audit.read_bytes()))
    elif a.command=='probe':
        _,state=current_run(api,a.root,'probing');result=probe_source(a.source,state)
    elif a.command=='activate':
        old,state=current_run(api,a.root,'probing')
        jobs=api.call('GET','actions/runs/'+str(run_id)+'/jobs?per_page=100')
        check=[j for j in jobs['jobs'] if j['name']=='authentication-probe']
        guard(jobs['total_count']<=100 and len(check)==1 and check[0]['conclusion']=='success','Authentication probe not successful')
        state['status']='ready';state['authenticationProbeRun']=run_id;state['runID']=None
        old=api.cas(old,state,'authenticated source and Cloud probe passed')
        result=dispatch(api,a.root,old,state,'produce',allowed_run=run_id)
    else:result=retain_failure(api,a.root,run_id,os.environ.get('RRGH_DISPATCH_ID'))
    if a.output:a.output.write_bytes(canonical(result))
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except (Halt,ValueError,KeyError) as exc:
        print('CONTROLLER_STOP: '+str(exc),file=sys.stderr);raise SystemExit(2)
