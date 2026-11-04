"""Receipt-bound GitHub handoff recovery. Never executes a Cloud slot."""
import argparse
import json
import os
from pathlib import Path

import rrgh_dispatcher as d

WORKFLOW='rrgh-controller-handoff.yml'
PINS=('runID','dispatchID','sourceSHA','planSHA256','sequence')
POLICY={'enabled':True,'authorizedBy':'ryanredrivergorgehiker',
        'authorizedOn':'2026-11-04','maxPreparationAttempts':3}


def caller():
    event=os.environ.get('GITHUB_EVENT_NAME')
    actor=os.environ.get('GITHUB_ACTOR')
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


def evidence(api,root,state):
    # A live run, failed worker, or failed verification never qualifies.
    run=d.read_audit_run(api,state['runID'])
    d.guard(run.get('status')=='completed' and run.get('conclusion')=='failure',
            'Handoff requires an exact completed failed controller run')
    d.assert_no_other_producers(api)
    report=d.audit_state(api,root,state,allow_failed_controller=True)
    d.guard(api.call('GET','git/ref/heads/'+d.SOURCE)['object']['sha']==state['sourceSHA'],
            'Source lease changed')
    return report


def prepare(api,root):
    caller();old,state=api.state();d.validate_state(state,root)
    if state.get('enabled') is not True or state.get('automaticHandoffRecovery')!=POLICY:
        return {'active':False,'reason':'disabled'}
    if state.get('status')=='ready':
        # Publication settled but the following read-only inventory may have
        # failed. Only an unclaimed fresh successor can enter dispatch here.
        previous=state.get('lastRecovered',{})
        d.guard(state.get('runID') is None and state.get('dispatchID') is None and
            previous.get('sequence')==state['sequence']-1 and type(previous.get('runID')) is int and
            previous['runID']>0 and bool(state.get('checkpoint')) and
            state['checkpoint']==previous.get('recoveryReceipt') and not state.get('publicationOf'),
            'Ready successor lacks exact settled recovery')
        d.dispatch(api,root,old,state,'produce',allowed_run=previous['runID'])
        return {'active':False,'reason':'fresh successor dispatched'}
    if state.get('status') not in ('halted','handoff-pending') or state.get('mode')!='produce':
        return {'active':False,'reason':'no eligible handoff'}
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
        state.get('mode')=='produce' and not state.get('publicationOf') and
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
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','publish','release'])
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--source',type=Path)
    p.add_argument('--audit',type=Path);a=p.parse_args();caller()
    api=d.GitHub(os.environ.get('GH_TOKEN',''))
    if a.command=='prepare':
        result=prepare(api,a.root)
        if result['active']:a.audit.write_bytes(d.canonical(result.pop('audit')))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('active='+str(result['active']).lower()+'\nsource='+result.get('sourceSHA','')+'\n')
    elif a.command=='publish':
        result=d.publish_and_advance(api,a.root,a.source,json.loads(a.audit.read_bytes()),automatic=True)
    else:result=release(api,a.root)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
