"""Receipt-bound GitHub handoff recovery. Never executes a Cloud slot."""
import argparse
import json
import os
import re
from pathlib import Path

import rrgh_dispatcher as d

WORKFLOW='rrgh-controller-handoff.yml'
PINS=('runID','dispatchID','sourceSHA','planSHA256','sequence')
POLICY={'enabled':True,'authorizedBy':'ryanredrivergorgehiker',
        'authorizedOn':'2026-11-04','maxPreparationAttempts':3}


def in_run():
    return os.environ.get('GITHUB_JOB')=='resume-handoff' and os.environ.get('GITHUB_REF')=='refs/heads/'+d.WORKER


def caller():
    event=os.environ.get('GITHUB_EVENT_NAME')
    actor=os.environ.get('GITHUB_ACTOR')
    if in_run():
        d.guard(os.environ.get('GITHUB_REPOSITORY')==d.REPO and
            os.environ.get('GITHUB_RUN_ATTEMPT')=='1' and event=='workflow_dispatch' and actor=='github-actions[bot]' and
            os.environ.get('GITHUB_WORKFLOW_REF')==d.REPO+'/.github/workflows/'+d.WORKFLOW+'@refs/heads/'+d.WORKER,
            'Wrong authenticated in-run handoff identity')
        return
    d.guard(os.environ.get('GITHUB_REPOSITORY')==d.REPO and
        os.environ.get('GITHUB_REF')=='refs/heads/main' and
        os.environ.get('GITHUB_RUN_ATTEMPT')=='1' and
        os.environ.get('GITHUB_WORKFLOW_REF')==d.REPO+'/.github/workflows/'+WORKFLOW+'@refs/heads/main' and
        event in ('push','schedule','workflow_run','workflow_dispatch') and
        (actor=='ryanredrivergorgehiker' or (event=='workflow_run' and actor=='github-actions[bot]')),
        'Wrong authenticated handoff workflow identity')


def pins(state):return {k:state[k] for k in PINS}


def policy(state):
    d.guard(state.get('automaticHandoffRecovery')==POLICY,'Owner-authorized handoff policy missing')


def evidence(api,root,state,published_source=None):
    # Only the exact terminal failed run or its trusted in-run fallback may
    # continue; failed workers and failed verification never qualify.
    run=d.read_audit_run(api,state['runID'])
    if in_run():
        d.guard(str(state['runID'])==os.environ['GITHUB_RUN_ID'] and
            state['dispatchID']==os.environ.get('RRGH_DISPATCH_ID') and
            run.get('status')=='in_progress' and run.get('conclusion') is None,
            'In-run handoff must own this still-active exact allocation')
        jobs=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
        d.guard(jobs.get('total_count')==len(jobs.get('jobs',[]))<=100 and
            len([j for j in jobs['jobs'] if j.get('name')=='advance' and j.get('conclusion')=='failure'])==1 and
            all(j.get('name') in ('advance','retain-failure','resume-handoff')
                for j in jobs['jobs'] if j.get('conclusion')=='failure'),
            'In-run handoff lacks exact controller-only failure')
    else:
        d.guard(run.get('status')=='completed' and run.get('conclusion')=='failure',
                'Handoff requires an exact completed failed controller run')
    d.assert_no_other_producers(api,state['runID'] if in_run() else None)
    report=d.audit_state(api,root,state,allow_failed_controller=True)
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==(published_source or state['sourceSHA']),
            'Source lease changed')
    return report


def reconcile_publication(api,root,old,state):
    """Settle only an exact, pre-recorded publication. No source mutation."""
    policy(state)
    d.guard(state.get('enabled') is True and state.get('mode') in ('produce','checkpoints') and
        state.get('status') in ('halted','publishing'),'Published recovery is not eligible')
    marker=state.get('publicationOf') or {};successor=marker.get('successor') or {}
    d.guard(all(marker.get(k)==state.get(k) for k in PINS) and
        set(successor)=={'sourceSHA','planSHA256','sequence','planPath'} and
        re.fullmatch('[0-9a-f]{40}',successor.get('sourceSHA','')) is not None and
        successor['sourceSHA']!=state['sourceSHA'] and
        re.fullmatch('[0-9a-f]{64}',successor.get('planSHA256','')) is not None and
        type(successor.get('sequence')) is int and successor['sequence']==state['sequence']+1 and
        re.fullmatch(r'backend/config/gorge-campaign-wave-'+str(successor['sequence'])+r'-\d{8}/PLAN.json',
                     successor.get('planPath','')) is not None,
        'Source publication is unresolved; exact validated successor required')
    pending=state.get('handoffPending',{})
    if pending:
        d.guard(all(pending.get(k)==state[k] for k in PINS),'Pending recovery identity changed')
        owner=pending.get('reconcilerRunID')
        if owner and str(owner)!=os.environ['GITHUB_RUN_ID']:
            d.guard(api.call('GET','actions/runs/'+str(owner)).get('status')=='completed',
                    'Another reconciler still owns this publication')
    report=evidence(api,root,state,published_source=successor['sourceSHA'])
    d.guard(report['receiptRef']==state.get('recoveredReceipt') and
        (not pending or pending.get('recoveryReceipt')==report['receiptRef']),
        'Published successor recovery receipt changed')
    commit=api.call('GET','git/commits/'+successor['sourceSHA'])
    d.guard(commit.get('sha')==successor['sourceSHA'] and
        [p.get('sha') for p in commit.get('parents',[])]==[state['sourceSHA']],
        'Published successor is not the exact original child commit')
    _,raw=api.file(successor['planPath'],ref=successor['sourceSHA']);plan=json.loads(raw)
    campaign=plan['campaign'];jobs=plan['approvedJobIDs']
    d.guard(d.digest(d.canonical(plan))==successor['planSHA256'] and
        campaign['sequence']==successor['sequence'] and campaign['controllerEpoch']==state['epoch'] and
        campaign['previousRecovery']==report['receiptRef'] and campaign['carry']==report['nextCarry'] and
        campaign['ceilingUSD']=='125.00' and campaign['storageTargetUSDPerMonth']=='2.00' and
        len(plan['completedJobIDs'])==len(set(plan['completedJobIDs']))==report['acceptedJobs'] and
        0<len(jobs)<=512 and len(jobs)==len(set(jobs)) and not set(jobs)&set(plan['completedJobIDs']) and
        all(plan['priorAttemptCounts'].get(j,0)==0 for j in jobs) and
        plan['maxConcurrency']==1 and plan['automaticRetryPermitted'] is False and plan['deleteAllowed'] is False,
        'Published successor plan, settlement or fresh allocation mismatch')
    # A competing state writer fails CAS; a moved source fails this final read.
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==successor['sourceSHA'],
            'Published source moved before settlement')
    d.settle_successor(api,root,old,state,report,plan,successor['sourceSHA'],successor['planSHA256'],
        automatic=True,reconciled=True)
    return {'active':False,'reason':'exact published successor settled and dispatched'}


def prepare(api,root):
    caller();old,state=api.state();d.validate_state(state,root)
    if state.get('enabled') is not True or state.get('automaticHandoffRecovery')!=POLICY:
        return {'active':False,'reason':'disabled'}
    if (not in_run() and state.get('status') in ('running','halted') and
        state.get('mode')=='produce' and not state.get('publicationOf') and not state.get('recoveryOnlyOf')):
        run=d.read_audit_run(api,state['runID'])
        if run.get('status')=='completed' and run.get('conclusion')=='failure' and run.get('id')==state['runID']:
            jobs=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
            d.guard(jobs.get('total_count')==len(jobs.get('jobs',[]))<=100,'Incomplete recovery decision inventory')
            from rrgh_recovery_only import eligible_parent
            try:eligible_parent(run,jobs['jobs'],state)
            except ValueError:pass
            else:return {'active':False,'unusedRecovery':d.arm_unstarted_recovery(api,root,automatic=True,detached=True)}
    if state.get('status')=='ready':
        # Publication settled but the following read-only inventory may have
        # failed. Only an unclaimed fresh successor can enter dispatch here.
        previous=state.get('lastRecovered',{})
        if in_run():d.guard(str(previous.get('runID'))==os.environ['GITHUB_RUN_ID'] and
            previous.get('dispatchID')==os.environ.get('RRGH_DISPATCH_ID'),'In-run successor belongs to another run')
        d.guard(state.get('runID') is None and state.get('dispatchID') is None and
            previous.get('sequence')==state['sequence']-1 and type(previous.get('runID')) is int and
            previous['runID']>0 and bool(state.get('checkpoint')) and
            state['checkpoint']==previous.get('recoveryReceipt') and not state.get('publicationOf'),
            'Ready successor lacks exact settled recovery')
        d.dispatch(api,root,old,state,'produce',allowed_run=previous['runID'])
        return {'active':False,'reason':'fresh successor dispatched'}
    if state.get('publicationOf') and state.get('status') in ('halted','publishing') and state.get('mode') in ('produce','checkpoints'):
        return reconcile_publication(api,root,old,state)
    if state.get('status') not in ('halted','handoff-pending') or state.get('mode') not in ('produce','checkpoints'):
        return {'active':False,'reason':'no eligible handoff'}
    if state.get('status')=='halted' and state.get('mode')=='produce' and state.get('checkpointRecoveryPolicy'):
        jobs=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
        d.guard(jobs.get('total_count')==len(jobs.get('jobs',[]))<=100,'Incomplete recovery decision inventory')
        producers=[j for j in jobs['jobs'] if j.get('name')=='bounded-stage']
        if len(producers)==1 and producers[0].get('conclusion')=='failure':
            from rrgh_checkpoint_recovery import arm
            return {'active':False,'checkpointRecovery':arm(api,root,automatic=True)}
    d.guard(not state.get('publicationOf'),'Source publication is unresolved; manual reconciliation required')
    pending=state.get('handoffPending')
    if pending:
        d.guard(all(pending.get(k)==state[k] for k in PINS),'Pending recovery identity changed')
        owner=pending.get('reconcilerRunID')
        if owner:
            prior=api.call('GET','actions/runs/'+str(owner))
            d.guard(prior.get('status')=='completed','Another reconciler still owns this handoff')
        d.guard(pending['preparationAttempts']<POLICY['maxPreparationAttempts'],
                'Handoff preparation attempts exhausted; manual investigation required')
    report=evidence(api,root,state)
    if pending:d.guard(pending['recoveryReceipt']==report['receiptRef'],'Pending recovery receipt changed')
    state['handoffPending']={**pins(state),'recoveryReceipt':report['receiptRef'],
        'reconcilerRunID':int(os.environ['GITHUB_RUN_ID']),
        'preparationAttempts':(pending or {}).get('preparationAttempts',0)+1}
    state['status']='handoff-pending'
    api.cas(old,state,'verified recovery pending automatic successor handoff')
    return {'active':True,'sourceSHA':state['sourceSHA'],'audit':report}


def audit_pending(api,root):
    caller();_,state=api.state();d.validate_state(state,root);policy(state)
    pending=state.get('handoffPending',{})
    d.guard(state.get('enabled') is True and state.get('status')=='handoff-pending' and
        state.get('mode') in ('produce','checkpoints') and not state.get('publicationOf') and
        str(pending.get('reconcilerRunID'))==os.environ['GITHUB_RUN_ID'] and
        all(pending.get(k)==state.get(k) for k in PINS),'Automatic handoff no longer owns exact recovery')
    report=evidence(api,root,state)
    d.guard(pending.get('recoveryReceipt')==report['receiptRef'],'Pending recovery receipt changed')
    return report


def release(api,root):
    caller();old,state=api.state();d.validate_state(state,root);policy(state)
    pending=state.get('handoffPending',{})
    if str(pending.get('reconcilerRunID'))!=os.environ['GITHUB_RUN_ID']:
        return {'status':'OTHER_OR_ADVANCED_OWNER_PRESERVED'}
    d.guard(all(pending.get(k)==state.get(k) for k in PINS),'Pending ownership changed')
    if state.get('status')=='handoff-pending' and not state.get('publicationOf'):
        pending['reconcilerRunID']=None
        api.cas(old,state,'retain verified pending handoff for next bounded reconciliation')
        return {'status':'VERIFIED_HANDOFF_PENDING'}
    # Never erase the publication marker or an ambiguous dispatch claim.
    return {'status':'UNRESOLVED_WRITE_PRESERVED'}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','publish','release','resume-published','recover-checkpoints'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--source',type=Path)
    p.add_argument('--audit',type=Path);a=p.parse_args()
    if a.command in ('resume-published','recover-checkpoints'):d.caller('launch')
    else:caller()
    api=d.GitHub(os.environ.get('GH_TOKEN',''))
    if a.command=='recover-checkpoints':
        from rrgh_checkpoint_recovery import arm
        result=arm(api,a.root)
    elif a.command=='resume-published':
        old,state=api.state();d.validate_state(state,a.root)
        result=reconcile_publication(api,a.root,old,state)
    elif a.command=='prepare':
        result=prepare(api,a.root)
        if result['active']:a.audit.write_bytes(d.canonical(result.pop('audit')))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('active='+str(result['active']).lower()+'\nsource='+result.get('sourceSHA','')+'\n')
    elif a.command=='publish':
        result=d.publish_and_advance(api,a.root,a.source,json.loads(a.audit.read_bytes()),automatic=True)
    else:result=release(api,a.root)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
