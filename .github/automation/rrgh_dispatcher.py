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
import time
from urllib.error import HTTPError, URLError
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
    'rrgh_native_repair.py',
    'rrgh_typed_child_receipts.py','rrgh_crosswave_batch.py','fixtures/completion-receipt-index.json.z.b64','rrgh_crosswave_phase.py','rrgh_crosswave_runtime.py','rrgh_crosswave_dependencies.py','crosswave-pilot-bindings.json',
    'rrgh_completion_phase.py','rrgh_dispatcher.py','rrgh_dispatch_audit.py','rrgh_handoff.py','rrgh_prepare_dispatch_successor.py',
    'rrgh_campaign_budget_v2.py','rrgh_expanded_production.py','rrgh_source_window_intake.py',
    'rrgh_required_inventory.py','rrgh_recovery_catalog_integration.py','rrgh_verified_tile_catalog.py','rrgh_recovery_only.py','rrgh_checkpoint_diagnostics.py','rrgh_checkpoint_salvage.py','rrgh_salvage_audit.py',
    'rrgh_wif_credentials.py','rrgh_credential_integration.py','rrgh_checkpoint_recovery.py','wave105-salvage.json',
    'rrgh_completion_contract.py','rrgh_checkpoint_completion.py','rrgh_completion_audit.py','rrgh_completion_catalog.py','wave289-completion.json',
    'rrgh_cloud_render_trial.py','rrgh_render_pilot.py',
    'rrgh_batch_contract.py','rrgh_pair_cache.py','rrgh_pair_worker.py','rrgh_batch_integration.py',
    'rrgh_overview_pilot.py','rrgh_overview_integration.py','rrgh_verified_overview.py','overview-pilot.json','overview-candidates.json',
    'source-templates/run_gorge_checkpoint_slot.py',
    'expanded-source-rights-20261102.json',
    'source-templates/benchmark_gorge_pipeline.py')] + [
    'backend/config/official-source-intake-20261102/official-source-candidates.json'] + ['.github/workflows/'+x for x in (
    WORKFLOW,'rrgh-controller-launch.yml','rrgh-controller-handoff.yml')]

READ_DELAYS=(5,15,30,60)


def source_file_limit(path):
    return 4_000_000 if re.fullmatch(r'backend/config/gorge-campaign-wave-\d+-\d{8}/PLAN\.json',path) else 2_000_000


class Halt(Exception):pass


class TransientGitHubError(Halt):pass


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
        # Only idempotent reads may retry a transient server response. An
        # ambiguous write/dispatch retains its durable claim and never retries.
        for attempt in range(3):
            try:
                with build_opener(NoRedirect).open(req,timeout=40) as response:body=response.read(8_000_001)
                break
            except HTTPError as exc:
                if method=='GET' and exc.code in (500,502,503,504) and attempt<2:
                    time.sleep(attempt+1)
                    continue
                error=TransientGitHubError if exc.code in (500,502,503,504) else Halt
                raise error('GitHub '+method+' '+path.split('?')[0]+' HTTP '+str(exc.code)+'; no automatic retry') from None
        guard(len(body)<=8_000_000,'GitHub response limit exceeded')
        return json.loads(body) if body else {}
    def file(self,path,ref=WORKER):
        obj=self.call('GET','contents/'+path+'?ref='+quote(ref,safe=''))
        if obj.get('encoding')=='none':
            # Growing immutable plans can exceed the Contents API inline limit.
            # Fetch only its exact bounded blob; never follow a mutable raw URL.
            guard(type(obj.get('size')) is int and 0<obj['size']<=source_file_limit(path) and
                  re.fullmatch('[0-9a-f]{40}',obj.get('sha','')) is not None,
                  'Non-inline GitHub file exceeds supported source bounds')
            blob=self.call('GET','git/blobs/'+obj['sha'])
            guard(blob.get('sha')==obj['sha'] and blob.get('encoding')=='base64',
                  'GitHub blob identity or encoding changed')
            raw=base64.b64decode(blob['content'])
            guard(len(raw)==obj['size'] and
                hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==obj['sha'],
                'GitHub blob size or hash mismatch')
            return obj,raw
        return obj,base64.b64decode(obj['content'])
    def state(self):
        blob,raw=self.file(STATE);return blob['sha'],json.loads(raw)
    def cas(self,old_sha,state,message):
        # Reconcile only this SHA-conditional state write. Dispatches and other
        # mutations remain single-attempt. Never overwrite a competing owner.
        raw=canonical(state)
        wanted_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        payload={'message':'Lane20 controller: '+message+' [skip ci]',
            'branch':WORKER,'sha':old_sha,'content':base64.b64encode(raw).decode()}
        for attempt in range(3):
            try:
                result=self.call('PUT','contents/'+STATE,payload)
                return result['content']['sha']
            except (TransientGitHubError,URLError,TimeoutError,ConnectionError) as exc:
                print(f'STATE_RECONCILE attempt={attempt+1} cause={type(exc).__name__}: {exc}',file=sys.stderr)
                observed_sha,observed=self.state()
                if observed_sha==wanted_sha and canonical(observed)==raw:
                    return observed_sha
                guard(observed_sha==old_sha,'State write reconciliation found a different owner; no retry')
                guard(attempt<2,'State write unchanged after three conditional attempts; stopped')
                time.sleep(attempt+1)


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
              upgrade.get('authorizedOn') in ('2026-11-02','2026-11-03','2026-11-09') and
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


class IncompleteActiveRunSnapshot(Halt):pass


def scan_active_runs(api,allowed_run=None):
    """Read one complete inventory; a changing page set is never clearance."""
    paths={ORIGINAL,'.github/workflows/'+WORKFLOW}
    for status in ('queued','in_progress','waiting','pending','requested'):
        page=1;seen=set();expected=None
        while True:
            data=api.call('GET',f'actions/runs?status={status}&per_page=100&page={page}')
            guard(isinstance(data,dict),'Malformed active-run response')
            runs=data.get('workflow_runs');total=data.get('total_count')
            guard(type(total) is int and total>=0 and isinstance(runs,list) and len(runs)<=100,
                  'Malformed active-run count or page')
            guard(all(isinstance(r,dict) and type(r.get('id')) is int and r['id']>0 and
                      isinstance(r.get('path'),str) and bool(r['path']) for r in runs),
                  'Malformed active-run identity')
            # A conflicting producer is decisive, even on an inconsistent page.
            guard(not any(r.get('path') in paths and r.get('id')!=allowed_run for r in runs),'Another producer is active')
            ids={r['id'] for r in runs}
            reason=f'status={status} page={page} seen={len(seen)} returned={len(runs)} total={total}'
            if ((expected is not None and total!=expected) or len(ids)!=len(runs) or
                    bool(ids & seen) or len(seen)+len(ids)>total):
                raise IncompleteActiveRunSnapshot('Active-run pagination changed: '+reason)
            expected=total;seen.update(ids)
            if len(seen)==total:break
            if not runs:
                raise IncompleteActiveRunSnapshot('Active-run pagination incomplete: '+reason)
            guard(page<20,'Active-run pagination limit exceeded: '+reason)
            page+=1


def assert_no_other_producers(api,allowed_run=None):
    # GitHub's filtered run count and pages can disagree while jobs transition.
    # Restart only these GETs, from page one and every status, over 110 seconds.
    # Never retry a claim, source publication, workflow dispatch or Cloud slot.
    for attempt in range(len(READ_DELAYS)+1):
        try:
            return scan_active_runs(api,allowed_run)
        except IncompleteActiveRunSnapshot as exc:
            if attempt==len(READ_DELAYS):raise Halt(str(exc)+'; bounded read-only scans exhausted') from None
            print('CONTROLLER_READ_RETRY: '+str(exc)+'; restarting active-run inventory',file=sys.stderr)
            time.sleep(READ_DELAYS[attempt])


def read_audit_run(api,rid):
    """Wait only for transient run-status metadata; identity checks still follow."""
    for attempt in range(len(READ_DELAYS)+1):
        run=api.call('GET','actions/runs/'+str(rid))
        if run.get('status') not in ('queued','waiting','pending','requested'):return run
        guard(attempt<len(READ_DELAYS),f'Run {rid} status={run.get("status")!r}; bounded metadata reads exhausted')
        print(f'CONTROLLER_READ_RETRY: run={rid} status={run.get("status")!r}',file=sys.stderr)
        time.sleep(READ_DELAYS[attempt])


def dispatch(api,root,state_sha,state,mode,allowed_run=None):
    validate_state(state,root)
    guard(state.get('enabled') is True,'Controller paused')
    guard(state['status'] in (('awaiting-auth','auth-required','ready') if mode=='probe' else
          ('checkpoint-recovery-ready',) if mode=='checkpoints' else ('completion-ready',) if mode=='complete' else ('salvage-ready',) if mode=='salvage' else ('recovery-ready',) if mode=='recover' else ('inspection-ready',) if mode=='inspect' else ('ready',)),
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
        state.setdefault('sourcePolicyMode','expanded')
        if upgrade.get('enableOverviewPilot') is True:state['overviewPilotEnabled']=True
        if upgrade.get('enableBatchPilot') is True:state['batchPilotEnabled']=True
        if upgrade.get('completionPolicy') is not None:
            from rrgh_completion_phase import authorized
            authorized(upgrade['completionPolicy'])
            state['completionPolicy']=upgrade['completionPolicy']
    state['status']='probing' if inputs['mode']=='probe' else 'running';state['runID']=run_id
    api.cas(old,state,'worker claimed '+state['dispatchID'])
    return state


def resume_unclaimed(api,root):
    """Owner-reviewed admission failure -> read-only probe, never producer replay.

    Eligibility is intentionally limited to the initial state GET failing before
    claim. Failed writes, unknown job outcomes and duplicate runs stay unresolved.
    The existing probe must additionally prove the Cloud allocation unused.
    """
    caller('launch')
    old,state=api.state();validate_state(state,root,allow_upgrade=True)
    request=json.loads((Path(root)/'.github/automation/rrgh-controller-request.json').read_bytes())
    guard(request.get('action')=='resume-unclaimed' and
          request.get('authorizedBy')=='ryanredrivergorgehiker' and
          request.get('date')=='2026-11-03','Exact owner admission-resume request missing')
    guard(state.get('enabled') is True and state.get('status')=='dispatching' and
          state.get('mode')=='produce' and state.get('runID') is None,
          'Allocation was claimed, disabled or is not a producer admission')
    for field,key in [('source_sha','sourceSHA'),('plan_sha256','planSHA256'),('dispatch_id','dispatchID')]:
        guard(request.get(field)==state.get(key),'Admission resume identity differs: '+field)
    rid=request.get('original_run');head=request.get('failure_head_sha')
    guard(type(rid) is int and rid>0 and re.fullmatch(r'[0-9a-f]{40}',head or ''),
          'Failed execution identity missing')
    run=api.call('GET','actions/runs/'+str(rid))
    guard(run.get('id')==rid and run.get('head_sha')==head and run.get('head_branch')==WORKER and
          run.get('path')=='.github/workflows/'+WORKFLOW and run.get('event')=='workflow_dispatch' and
          (run.get('actor') or {}).get('login')=='github-actions[bot]' and
          (run.get('triggering_actor') or {}).get('login')=='github-actions[bot]' and
          run.get('run_attempt')==1 and run.get('status')=='completed' and run.get('conclusion')=='failure' and
          run.get('display_title')=='RRGH production '+str(state['sequence'])+' '+state['dispatchID'],
          'Failed run does not bind this unclaimed allocation')
    _,original_raw=api.file(STATE,ref=head);original=json.loads(original_raw)
    for key in ('sourceSHA','planSHA256','dispatchID','sequence','controlDigest','checkpoint','lastRecovered','launchCounter'):
        guard(original.get(key)==state.get(key),'Failed-head allocation changed: '+key)
    guard(original.get('status')=='dispatching' and original.get('runID') is None,
          'Original allocation was already claimed')
    jobs=api.call('GET','actions/runs/'+str(rid)+'/jobs?per_page=100')
    rows=jobs.get('jobs',[])
    guard(jobs.get('total_count')==len(rows) and len(rows)==10,
          'Incomplete or unexpected admission-failure jobs')
    required={'admit','bounded-stage','authentication-probe','checkpoint-inspection','finish-inspection',
              'activate','independent-recovery','independent-salvage','advance','retain-failure'}
    guard({j.get('name') for j in rows}==required,'Unexpected admission-failure job set')
    admission=[j for j in rows if j['name']=='admit'][0]
    guard(all(j.get('status')=='completed' and j.get('run_id')==rid and
              j.get('conclusion')==('failure' if j['name']=='admit' else 'skipped') for j in rows),
          'Cloud work started or downstream outcome is ambiguous')
    failed=[s for s in admission.get('steps',[]) if s.get('conclusion')=='failure']
    guard(len(failed)==1 and failed[0].get('name')==
          'Atomically claim the exact controller allocation before Cloud authentication',
          'Failure was not the controller admission step')
    from rrgh_dispatch_audit import gh
    log=gh('actions/jobs/'+str(admission['id'])+'/logs',api.token,raw=True)
    stops=[line.split('CONTROLLER_STOP: ',1)[1].strip() for line in log.splitlines() if 'CONTROLLER_STOP: ' in line]
    guard(len(stops)==1 and re.fullmatch(
        r'GitHub GET contents/\.github/automation/rrgh-controller-state\.json HTTP (500|502|503|504); no automatic retry',
        stops[0]) is not None,'Cannot establish read-only admission failure')
    duplicates=api.call('GET','actions/runs?head_sha='+head+'&per_page=100')
    candidates=duplicates.get('workflow_runs',[])
    guard(duplicates.get('total_count')==len(candidates) and
          [r.get('id') for r in candidates if r.get('path')=='.github/workflows/'+WORKFLOW]==[rid],
          'Duplicate or incompletely enumerated worker execution')
    assert_no_other_producers(api)
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    # Preserve the failed request before a new unique probe dispatch. CAS failure
    # or a lost dispatch response halts; neither path repeats source production.
    retained={k:state[k] for k in ('sequence','sourceSHA','planSHA256','dispatchID','launchCounter')}
    retained.update(runID=rid,headSHA=head,admissionJobID=admission['id'],reason=stops[0],
                    cloudJobsSkipped=True,logSHA256=digest(log.encode()))
    if state['controlDigest']!=local_digest(root):
        upgrade=state.pop('pendingControllerUpgrade')
        state.setdefault('controllerUpgradeHistory',[]).append({**upgrade,'failedAdmissionRunID':rid,
            'sequence':state['sequence']})
        state['controlDigest']=upgrade['toDigest']
    state.setdefault('unclaimedAdmissionHistory',[]).append(retained)
    state.update(status='ready',runID=None,dispatchID=None)
    old=api.cas(old,state,'proven unused admission retained; authenticated probe required')
    return dispatch(api,root,old,state,'probe')


def current_run(api,root,status):
    old,state=api.state();validate_state(state,root)
    guard(state.get('status')==status and str(state.get('runID'))==os.environ.get('GITHUB_RUN_ID') and
          state.get('dispatchID')==os.environ.get('RRGH_DISPATCH_ID'),'Current execution no longer owns claim')
    return old,state


def audit_current(api,root):
    _,state=current_run(api,root,'running')
    return audit_state(api,root,state)


def audit_state(api,root,state,allow_failed_controller=False):
    if state.get('mode')=='checkpoints':
        from rrgh_checkpoint_recovery import audit
        return audit(api,state,allow_failed_controller=allow_failed_controller)
    if state.get('mode')=='complete':
        from rrgh_completion_audit import audit
        return audit(api,state)
    if state.get('mode')=='salvage':
        from rrgh_salvage_audit import audit
        return audit(api,state)
    rid=state['runID']
    run=read_audit_run(api,rid)
    jobs=api.call('GET','actions/runs/'+str(rid)+'/jobs?per_page=100')
    guard(jobs['total_count']==len(jobs['jobs'])<=100,'Job pagination not complete')
    from rrgh_dispatch_audit import audit_run,gh
    recovery_execution=None;expected=state;producer_jobs=jobs['jobs']
    if state.get('mode')=='recover':
        recovery_execution=dict(run=run,jobs=jobs['jobs'],state=state)
        expected=state['recoveryOnlyOf']
        run=api.call('GET','actions/runs/'+str(expected['runID']))
        original=api.call('GET','actions/runs/'+str(expected['runID'])+'/jobs?per_page=100')
        guard(original['total_count']==len(original['jobs'])<=100,'Original job pagination not complete')
        producer_jobs=original['jobs']
    selected={name:[j for j in (producer_jobs if name=='bounded-stage' else jobs['jobs']) if j['name']==name]
              for name in ('bounded-stage','independent-recovery')}
    guard(all(len(v)==1 for v in selected.values()),'Producer/recovery job multiplicity')
    logs={name:gh('actions/jobs/'+str(items[0]['id'])+'/logs',api.token,raw=True).splitlines()
          for name,items in selected.items()}
    report=audit_run(run,producer_jobs,logs['independent-recovery'],logs['bounded-stage'],
        expected_dispatch=expected,allow_failed_controller=allow_failed_controller,recovery_execution=recovery_execution)
    guard(report['planSHA256']==state['planSHA256'] and report['wave']==state['sequence'],'Recovery identity changed')
    report['controllerDispatchID']=state['dispatchID'];report['controllerParentRun']=state.get('parentRunID')
    report['sourcePolicyMode']=state.get('sourcePolicyMode','expanded')
    report['overviewPilotEnabled']=state.get('overviewPilotEnabled') is True
    if state.get('completionPolicy') is not None:
        from rrgh_completion_phase import authorized
        authorized(state['completionPolicy'])
        report['completionPolicy']=state['completionPolicy']
    if state.get('crosswavePolicy') is not None:
        from rrgh_crosswave_phase import authorized as authorize_crosswave
        authorize_crosswave(state['crosswavePolicy']);report['crosswavePolicy']=state['crosswavePolicy']
    report['batchPilotEnabled']=state.get('batchPilotEnabled') is True
    if state.get('nativeRepairPolicy') is not None:
        from rrgh_native_repair import authorized as authorize_native_repair
        authorize_native_repair(state['nativeRepairPolicy']);report['nativeRepairPolicy']=state['nativeRepairPolicy']
    if recovery_execution is not None:report['recoveryRunID']=state['runID']
    return report


def arm_unstarted_recovery(api,root,automatic=False,detached=False):
    if detached:
        from rrgh_handoff import caller as handoff_caller,policy
        handoff_caller()
        guard(automatic,'Detached recovery requires the authorized handoff')
    elif not automatic:caller('launch')
    old,state=api.state();validate_state(state,root)
    if detached:policy(state)
    guard(state.get('enabled') is True and state.get('mode')=='produce' and
          state.get('status') in (('running','halted') if detached else ('running',) if automatic else ('halted',)) and
          'recoveryOnlyOf' not in state,'Recovery-only resume is not eligible')
    if automatic and not detached:guard(str(state['runID'])==os.environ.get('GITHUB_RUN_ID'),'Another run owns this allocation')
    run=api.call('GET','actions/runs/'+str(state['runID']))
    jobs=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
    guard(jobs['total_count']==len(jobs['jobs'])<=100,'Incomplete parent jobs')
    from rrgh_recovery_only import eligible_parent,one,producer_receipt
    eligible_parent(run,jobs['jobs'],state,active=automatic and not detached)
    from rrgh_dispatch_audit import gh
    producer=one(jobs['jobs'],'bounded-stage')
    receipt=producer_receipt(gh('actions/jobs/'+str(producer['id'])+'/logs',api.token,raw=True).splitlines(),state['planSHA256'])
    if not automatic:
        auth=state.get('recoveryStartAuthorization',{})
        guard(auth.get('authorizedBy')=='ryanredrivergorgehiker' and auth.get('authorizedOn') in ('2026-11-02','2026-11-09') and
              all(auth.get(k)==state.get(k) for k in ('runID','planSHA256','sourceSHA','dispatchID')) and
              auth.get('producerReceipt')==receipt,'Exact recovery-start authorization missing')
    assert_no_other_producers(api,state['runID'] if automatic else None)
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    parent={k:state[k] for k in ('runID','planSHA256','sourceSHA','dispatchID','sequence')}
    parent.update(mode='produce',producerReceipt=receipt)
    state.update(status='recovery-ready',recoveryOnlyOf=parent)
    state.pop('recoveryStartAuthorization',None)
    old=api.cas(old,state,'verified recovery never started; preserve exact producer')
    return dispatch(api,root,old,state,'recover',allowed_run=parent['runID'])


def complete_halted(api,root):
    caller('launch');old,state=api.state();validate_state(state,root)
    from rrgh_completion_contract import manifest,manifest_sha,funding
    from rrgh_completion_audit import original
    m=manifest()
    previous=m.get('retainedCompletions',[])
    if previous:
        prior=previous[-1]
        eligible=(len(previous)==1 and state.get('mode')=='complete' and state.get('runID')==prior['runID'] and
                  state.get('dispatchID')==prior['dispatchID'] and
                  state.get('completionOf',{}).get('manifestSHA256')==prior['manifestSHA256'])
    else:
        eligible=(state.get('mode')=='produce' and state.get('runID')==m['originalRunID'] and
                  state.get('dispatchID')==m['originalDispatchID'] and 'completionOf' not in state)
    guard(state.get('enabled') is True and state.get('status')=='halted' and eligible and
          all(state.get(k)==m[k] for k in ('sourceSHA','planSHA256','sequence')),
          'Only the exact original or fully retained consumed recovery can be completed')
    auth=state.get('completionAuthorization',{})
    guard(auth=={'authorizedBy':'ryanredrivergorgehiker','authorizedOn':'2026-11-04',
                 'manifestSHA256':manifest_sha()},'Exact owner completion authorization missing')
    original(api);funding()
    assert_no_other_producers(api)
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==state['sourceSHA'],'Source lease changed')
    if previous:state.setdefault('retainedCompletionHistory',[]).append(previous[-1])
    state['completionOf']={k:m[v] for k,v in [('runID','originalRunID'),('dispatchID','originalDispatchID'),
        ('sourceSHA','sourceSHA'),('planSHA256','planSHA256'),('sequence','sequence')]}
    state['completionOf'].update(manifestSHA256=manifest_sha(),failedRecoveryReceipt=m['failedRecoveryReceipt'])
    state.pop('completionAuthorization')
    state['status']='completion-ready'
    old=api.cas(old,state,'retain consumed recovery; reserve one separately funded completion')
    return dispatch(api,root,old,state,'complete',allowed_run=m['originalRunID'])


def salvage_halted(api,root):
    caller('launch');old,state=api.state();validate_state(state,root)
    from rrgh_salvage_audit import original,manifest_sha
    m=original(api)
    guard(state.get('status')=='halted' and state.get('mode')=='produce' and
          state.get('runID')==m['originalRunID'] and state.get('dispatchID')==m['originalDispatchID'] and
          state.get('sourceSHA')==m['sourceSHA'] and state.get('planSHA256')==m['planSHA256'] and
          state.get('sequence')==105,'Only the exact inspected failed allocation is eligible')
    auth=state.get('salvageAuthorization',{})
    guard(auth.get('authorizedBy')=='ryanredrivergorgehiker' and auth.get('authorizedOn')=='2026-11-02' and
          auth.get('manifestSHA256')==manifest_sha(),'Reviewed owner salvage authorization missing')
    assert_no_other_producers(api)
    state['salvageOf']={k:state[k] for k in ('runID','dispatchID','sourceSHA','planSHA256','sequence')}
    state['salvageOf']['manifestSHA256']=manifest_sha()
    state['status']='salvage-ready';state.pop('salvageAuthorization')
    old=api.cas(old,state,'salvage exact durable checkpoints; producer will not run')
    return dispatch(api,root,old,state,'salvage')


def inspect_halted(api,root):
    caller('launch');old,state=api.state();validate_state(state,root)
    guard(state.get('status')=='halted' and state.get('mode')=='produce','Only halted production may be inspected')
    auth=state.get('inspectionAuthorization',{})
    guard(auth.get('authorizedBy')=='ryanredrivergorgehiker' and auth.get('authorizedOn')=='2026-11-02' and
          all(auth.get(k)==state.get(k) for k in ('runID','planSHA256','sourceSHA','dispatchID')),
          'Exact read-only inspection authorization missing')
    assert_no_other_producers(api)
    state['inspectionOf']={k:state.get(k) for k in ('runID','dispatchID','parentRunID','mode')}
    state['status']='inspection-ready';state.pop('inspectionAuthorization')
    old=api.cas(old,state,'owner-authorized bounded read-only checkpoint inspection')
    return dispatch(api,root,old,state,'inspect')


def finish_inspection(api,root):
    old,state=current_run(api,root,'running')
    guard(state.get('mode')=='inspect' and state.get('inspectionOf'),'No inspection owns this allocation')
    previous=state.pop('inspectionOf')
    state.setdefault('inspectionHistory',[]).append(dict(runID=state['runID'],sourceRunID=previous['runID'],cloudWrites=0))
    state.update(previous);state['status']='halted'
    api.cas(old,state,'inspection finished; original failed allocation preserved')
    return dict(status='HALTED_ALLOCATION_PRESERVED',cloudWrites=0)


def audit_recovered(api,root):
    caller('launch')
    _,state=api.state();validate_state(state,root)
    phase_resume=state.get('status')=='completion-waiting'
    guard(state.get('enabled') is True and state.get('status') in ('halted','completion-waiting') and state.get('mode')=='produce',
          'Only an independently recovered production allocation can advance')
    auth=state.get('recoveredResumeAuthorization',{})
    if phase_resume:
        if state.get('nativeRepairPolicy') is not None:
            from rrgh_native_repair import authorized as authorize_native_repair
            authorize_native_repair(state['nativeRepairPolicy'])
            CW_POLICY=state['nativeRepairPolicy']
            guard(state['lastRecovered']['recoveryReceipt']==CW_POLICY['baselineRecovery'],
                'Exact independently verified native repair baseline receipt required')
        else:
            from rrgh_crosswave_phase import authorized as authorize_crosswave
            authorize_crosswave(state.get('crosswavePolicy'))
            CW_POLICY=state['crosswavePolicy']
        guard(state['sequence']==CW_POLICY['baselineSequence'] and state['planSHA256']==CW_POLICY['baselinePlanSHA256'] and
            state['lastRecovered']['acceptedRasterTiles']==CW_POLICY['baselineAcceptedTiles'] and
            all(state['lastRecovered'].get(k)==state.get(k) for k in ('runID','planSHA256','sourceSHA','dispatchID')),
            'Exact settled phase boundary required')
        auth={'recoveryReceipt':state['lastRecovered']['recoveryReceipt']}
    else:
        guard(auth.get('authorizedBy')=='ryanredrivergorgehiker' and auth.get('authorizedOn') in ('2026-11-02','2026-11-03','2026-11-04','2026-11-09','2026-11-10') and
              all(auth.get(k)==state.get(k) for k in ('runID','planSHA256','sourceSHA','dispatchID')),
              'Exact owner-authorized recovered continuation missing')
    assert_no_other_producers(api)
    # This exact batch boundary settled successful production and independent
    # recovery despite the original controller-only edge guard failure.
    batch_boundary=phase_resume and state['crosswavePolicy']['format']=='rrgh-crosswave-batch-authority-v2'
    report=audit_state(api,root,state,allow_failed_controller=(not phase_resume or batch_boundary))
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
    if audit.get('completedConsumedRecovery') is True:
        from rrgh_completion_contract import check_report
        check_report(audit)
    guard(new_dir!=old_dir and plan['campaign']['sequence']==prior['campaign']['sequence']+1,'Allocation not advanced')
    guard(plan['campaign']['previousRecovery']==audit['receiptRef'] and plan['campaign']['carry']==audit['nextCarry'],
          'Exact predecessor settlement lost')
    guard(plan['campaign']['controllerEpoch']==state['epoch'] and plan['campaign']['ceilingUSD']=='125.00' and
          plan['campaign']['storageTargetUSDPerMonth']=='2.00','Authority changed')
    jobs=plan['approvedJobIDs']
    guard(0<len(jobs)<=512 and len(set(jobs))==len(jobs) and
          not set(jobs)&set(plan['completedJobIDs']) and
          (plan.get('nativeRepairPhase') is not None or all(plan['priorAttemptCounts'].get(j,0)==0 for j in jobs)),
          'Replayed or malformed successor jobs')
    guard(len(plan['completedJobIDs'])==len(set(plan['completedJobIDs']))==audit['acceptedJobs'],'Accepted inventory mismatch')
    previous_quarantine=prior['campaign'].get('checkpointRecoveryQuarantines',[])
    if audit.get('checkpointRecovery'):
        from rrgh_checkpoint_recovery import validate_planning
        recovered=validate_planning(prior,audit)
        guard(plan['completedJobIDs']==prior['completedJobIDs']+recovered['completedJobIDs'] and
            all(plan['priorAttemptCounts'].get(j)==1 for j in prior['approvedJobIDs']),
            'Checkpoint accepted prefix or consumed allocation lost')
        previous_quarantine=previous_quarantine+recovered['uncertainJobIDs']
    guard(plan['campaign'].get('checkpointRecoveryQuarantines',[])==previous_quarantine,
          'Checkpoint quarantine lineage changed')
    from rrgh_recovery_catalog_integration import augment_campaign, TARGET as CATALOG_TARGET
    from rrgh_overview_integration import augment as augment_overview, MODULES as OVERVIEW_MODULES,validate_recovery
    validate_recovery(prior,audit)
    from rrgh_batch_integration import strip as strip_batch, augment as augment_batch, installed as batch_installed, MODULES as BATCH_MODULES
    expected_code=augment_overview(augment_campaign(strip_batch(old_code)))
    if batch_installed(root):expected_code=augment_batch(expected_code)
    guard(new_code==expected_code.replace(old_dir.name,new_dir.name),'Unreviewed source code edit')
    from rrgh_expanded_production import validate_publication, ENGINE
    validate_publication(root,old_dir,new_dir,plan,audit)
    guard(plan['limits']=={**prior['limits'],'attempts':len(jobs)} and plan['maxConcurrency']==1 and
          plan['automaticRetryPermitted'] is False and plan['deleteAllowed'] is False,'Resource/protection drift')
    snapshot={p.name:digest(p.read_bytes()) for p in sorted((root/'backend/scripts').glob('*.py')) if not p.name.startswith('test_')}
    guard(digest(canonical(snapshot))==plan['sourceSnapshotSHA256'],'Executable source snapshot mismatch')
    allowed={str(new_dir.relative_to(root)/name) for name in ('PLAN.json','ALLOWANCE.json','REGION-PLAN.json.z.b64')}
    allowed.add('backend/scripts/gorge_campaign.py')
    catalog_tracked=subprocess.run(['git','-C',str(root),'cat-file','-e','HEAD:'+CATALOG_TARGET],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not catalog_tracked:allowed.add(CATALOG_TARGET)
    from rrgh_credential_integration import validate as validate_credentials, TARGET as CRED_TARGET, MODULE as CRED_MODULE
    old_credentials=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+CRED_TARGET],text=True)
    validate_credentials(root,old_credentials)
    if (root/CRED_TARGET).read_text()!=old_credentials:allowed.add(CRED_TARGET)
    cred_module='backend/scripts/'+CRED_MODULE
    tracked=subprocess.run(['git','-C',str(root),'cat-file','-e','HEAD:'+cred_module],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not tracked:allowed.add(cred_module)
    else:
        from rrgh_credential_integration import validate_module
        before=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+cred_module])
        after=(root/cred_module).read_bytes();validate_module(before,after)
        if before!=after:allowed.add(cred_module)
    for module in OVERVIEW_MODULES:
        target='backend/scripts/'+module
        tracked=subprocess.run(['git','-C',str(root),'cat-file','-e','HEAD:'+target],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        if not tracked:allowed.add(target)
        else:
            from rrgh_overview_integration import validate_prior_module
            before=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+target])
            after=(root/target).read_bytes()
            validate_prior_module(module,before,after)
            if before!=after:allowed.add(target)
    if batch_installed(root):
        for module in BATCH_MODULES:
            target='backend/scripts/'+module
            tracked=subprocess.run(['git','-C',str(root),'cat-file','-e','HEAD:'+target],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
            if not tracked:allowed.add(target)
            else:
                guard(subprocess.check_output(['git','-C',str(root),'show','HEAD:'+target])==(root/target).read_bytes(),
                      'Installed batch module changed')
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
        raw=(root/name).read_bytes();guard(0<len(raw)<=source_file_limit(name),'Source publication file bound')
        entries.append({'path':name,'mode':'100644','type':'blob','content':raw.decode()})
    return parent,plan_hash,plan,entries


def publish_and_advance(api,root,source_root,audit,recovered=False,automatic=False):
    if automatic:
        from rrgh_handoff import audit_pending,caller as handoff_caller
        handoff_caller();old,state=api.state();validate_state(state,root)
    elif recovered:
        caller('launch');old,state=api.state();validate_state(state,root)
    else:
        old,state=current_run(api,root,'running')
    guard(state.get('enabled') is True,'Controller paused after recovery')
    # Re-read live successful producer/recovery evidence; do not trust a caller's flag.
    guard((audit_pending(api,root) if automatic else audit_recovered(api,root) if recovered else audit_current(api,root))==audit,
          'Audit does not match live independent recovery')
    if audit.get('completionPolicy') is not None and (Path(source_root)/'RRGH-COMPLETION-WAIT.json').exists():
        return settle_completion_wait(api,root,source_root,old,state,audit)
    parent,plan_hash,plan,entries=candidate_entries(source_root,audit,state)
    assert_no_other_producers(api,state['runID'])
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==parent,'Source publication lease moved')
    state['status']='publishing';state['recoveredReceipt']=audit['receiptRef']
    # A later failure must not turn an ambiguous source publication into an
    # automatic retry. Only an exact recorded successor may later be reconciled.
    state['publicationOf']={k:state[k] for k in ('runID','dispatchID','sourceSHA','planSHA256','sequence')}
    state.pop('recoveredResumeAuthorization',None)
    old=api.cas(old,state,'recovered '+state['dispatchID'])
    base=api.call('GET','git/commits/'+parent)
    tree=api.call('POST','git/trees',{'base_tree':base['tree']['sha'],'tree':entries})
    commit=api.call('POST','git/commits',{'message':'Lane20: autonomous immutable wave '+str(plan['campaign']['sequence'])+' [skip ci]',
        'tree':tree['sha'],'parents':[parent]})
    # Bind the already-validated immutable candidate BEFORE changing the source
    # ref. A lost final state write can then settle this exact commit by reads;
    # it cannot authorize replanning or replaying an uncertain publication.
    state['publicationOf']['successor']={'sourceSHA':commit['sha'],'planSHA256':plan_hash,
        'sequence':plan['campaign']['sequence'],
        'planPath':next(e['path'] for e in entries if e['path'].endswith('/PLAN.json'))}
    old=api.cas(old,state,'record exact validated successor before source publication')
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==parent,'Source publication lease moved')
    api.call('PATCH','git/refs/heads/'+SOURCE,{'sha':commit['sha'],'force':False})
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==commit['sha'],'Published source readback mismatch')
    return settle_successor(api,root,old,state,audit,plan,commit['sha'],plan_hash,automatic=automatic)


def settle_completion_wait(api,root,source_root,old,state,audit):
    """Settle the last verified wave without inventing an empty successor."""
    from rrgh_completion_phase import waiting_summary
    from rrgh_expanded_production import read_region
    source_root=Path(source_root)
    parent=subprocess.check_output(['git','-C',str(source_root),'rev-parse','HEAD'],text=True).strip()
    guard(parent==state['sourceSHA'],'Phase boundary source lease changed')
    folder,plan,_=config(source_root)
    guard(digest(canonical(plan))==state['planSHA256']==audit['planSHA256'],
          'Phase boundary plan changed')
    if plan.get('crosswavePhase'):
        from rrgh_crosswave_phase import waiting_summary
    if plan.get('nativeRepairPhase'):
        from rrgh_native_repair import waiting_summary
    expected=waiting_summary(plan,read_region(folder),audit)
    guard(json.loads((source_root/'RRGH-COMPLETION-WAIT.json').read_bytes())==expected,
          'Phase boundary settlement differs')
    changed=subprocess.check_output(['git','-C',str(source_root),'ls-files','--modified','--others','--exclude-standard'],text=True).splitlines()
    guard(changed==['RRGH-COMPLETION-WAIT.json'],'Phase boundary must not change source or prior plans')
    assert_no_other_producers(api,state['runID'])
    guard(api.call('GET','git/ref/heads/'+SOURCE)['object']['sha']==parent,'Phase boundary source moved')
    completed={k:state[k] for k in ('runID','sequence','dispatchID','sourceSHA','planSHA256')}
    completed.update(recoveryReceipt=audit['receiptRef'],acceptedJobs=audit['acceptedJobs'],
        acceptedRasterTiles=audit['acceptedRasterTiles'],jobsNew=audit['jobsNew'],tilesNew=audit['tilesNew'])
    if state.get('handoffPending'):
        state.setdefault('handoffRecoveryHistory',[]).append(state.pop('handoffPending'))
    state.update(status='completion-waiting',checkpoint=audit['receiptRef'],
        lastRecovered=completed,completionProgress=expected)
    api.cas(old,state,'verified lower-zoom queue complete; awaiting remaining completion phases')
    return {'status':'COMPLETION_PHASE_SETTLED','progress':expected,'producerReplays':0,'sourceWrites':0}


def settle_successor(api,root,old,state,audit,plan,source_sha,plan_hash,automatic=False,reconciled=False):
    """Commit one inclusive settlement; dispatch only after its CAS succeeds."""
    completed={'runID':state['runID'],'sequence':state['sequence'],'dispatchID':state['dispatchID'],
        'parentRunID':state.get('parentRunID'),'sourceSHA':state['sourceSHA'],'planSHA256':state['planSHA256'],
        'recoveryReceipt':audit['receiptRef'],'acceptedJobs':audit['acceptedJobs'],
        'acceptedRasterTiles':audit['acceptedRasterTiles'],'jobsNew':audit['jobsNew'],
        'tilesNew':audit.get('tilesNew'),'recoveryCycleSeconds':audit.get('recoveryCycleSeconds'),
        'cycleTilesPerSecond':audit.get('cycleTilesPerSecond')}
    if audit.get('batchClosure'):completed['batchClosure']=audit['batchClosure']
    if state.get('mode')=='checkpoints':
        completed['checkpointRecoveryOf']=state.pop('checkpointRecoveryOf')
    if state.get('mode')=='complete':
        completed['consumedRecoveryCompletionOf']=state.pop('completionOf')
        completed['completionSettlement']=audit['completionSettlement']
    if state.get('mode')=='salvage':
        completed['checkpointSalvageOf']=state.pop('salvageOf')
    if state.get('mode')=='recover':
        completed['originalProducerRunID']=state['recoveryOnlyOf']['runID']
        completed['originalProducerReceipt']=state['recoveryOnlyOf']['producerReceipt']
        state.pop('recoveryOnlyOf')
    if state.get('batchPilotEnabled') and audit.get('batchClosure') and not plan.get('resumableBatch'):
        state['batchPilotEnabled']=False
        state.setdefault('batchFallbackHistory',[]).append({'runID':state['runID'],'sequence':state['sequence'],
            'recoveryReceipt':audit['receiptRef'],'reason':audit.get('fallbackReason') or audit['batchClosure'].get('stopReason') or 'measured throughput gate',
            'acceptedHistoryPreserved':True,'nextWorkers':1,'nextJobLimit':12})
    if automatic and state.get('handoffPending'):
        state.setdefault('handoffRecoveryHistory',[]).append(state['handoffPending'])
    if reconciled:
        state.setdefault('publicationRecoveryHistory',[]).append({
            **state['publicationOf'],'reconcilerRunID':int(os.environ['GITHUB_RUN_ID']),
            'recoveryReceipt':audit['receiptRef'],'sourceWrites':0,'producerReplays':0})
    state.pop('handoffPending',None);state.pop('publicationOf',None)
    state.update(status='ready',sequence=plan['campaign']['sequence'],sourceSHA=source_sha,planSHA256=plan_hash,
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
    if (state.get('mode')=='produce' and state.get('status')=='running' and 'recoveryOnlyOf' not in state and
            str(state.get('runID'))==os.environ.get('GITHUB_RUN_ID')):
        try:return arm_unstarted_recovery(api,root,automatic=True)
        except ValueError:pass  # Not the exact pre-recovery setup incident; retain normally.
    state['status']='auth-required' if state.get('mode')=='probe' else 'halted'
    state['failureRunID']=run_id
    api.cas(old,state,'failure retained; no automatic retry')
    return {'status':state['status'],'runID':run_id,'automaticRetryPermitted':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['launch','claim','audit','publish','probe','activate','failed','audit-recovered','publish-recovered','recover-unstarted','inspect-halted','finish-inspection','salvage-halted','resume-unclaimed','complete-halted'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--source',type=Path)
    p.add_argument('--audit',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();caller('launch' if a.command.endswith('-recovered') or a.command in ('recover-unstarted','inspect-halted','salvage-halted','resume-unclaimed','complete-halted') else a.command)
    api=GitHub(os.environ.get('GH_TOKEN',''));run_id=int(os.environ['GITHUB_RUN_ID'])
    if a.command=='launch':
        old,state=api.state();result=dispatch(api,a.root,old,state,'probe')
    elif a.command=='claim':
        inputs={k:os.environ['INPUT_'+k.upper()] for k in ('mode','source_sha','plan_sha256','sequence','dispatch_id')}
        result=claim(api,a.root,inputs,run_id)
    elif a.command=='resume-unclaimed':result=resume_unclaimed(api,a.root)
    elif a.command=='audit':result=audit_current(api,a.root)
    elif a.command=='audit-recovered':result=audit_recovered(api,a.root)
    elif a.command=='recover-unstarted':result=arm_unstarted_recovery(api,a.root)
    elif a.command=='complete-halted':result=complete_halted(api,a.root)
    elif a.command=='salvage-halted':result=salvage_halted(api,a.root)
    elif a.command=='inspect-halted':result=inspect_halted(api,a.root)
    elif a.command=='finish-inspection':result=finish_inspection(api,a.root)
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
