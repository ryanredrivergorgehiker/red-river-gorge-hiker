"""One fresh recovery execution after a proven pre-recovery setup failure.

Never runs production again. The unchanged source still enforces its create-only
Cloud recovery slot; an existing or ambiguous slot cannot be reused.
"""
import json
import re

REPO='ryanredrivergorgehiker/red-river-gorge-hiker'
BRANCH='lane20/offline-production-preflight-20261029'
PATH='.github/workflows/offline-map-restricted-dispatch.yml'
RECOVERY_STEP='Independently recover pixels, hashes, packages and cache lineage on a fresh runner'
SETUP_STEP='Run google-github-actions/setup-gcloud@v3'

def require(ok,message):
    if not ok:raise ValueError(message)

def identity(run,state,mode):
    require(run.get('id')==state.get('runID') and run.get('run_attempt')==1 and
        run.get('head_branch')==BRANCH and run.get('event')=='workflow_dispatch' and
        run.get('path')==PATH and run.get('actor',{}).get('login')=='github-actions[bot]' and
        run.get('repository',{}).get('full_name')==REPO and
        run.get('display_title')==f"RRGH {mode} {state['sequence']} {state['dispatchID']}",
        'Recovery-only execution identity mismatch')

def one(jobs,name):
    rows=[j for j in jobs if j.get('name')==name]
    require(len(rows)==1,'Recovery-only job multiplicity: '+name)
    return rows[0]

def eligible_parent(run,jobs,state,active=False):
    identity(run,state,'production')
    require((active and run.get('status')=='in_progress' and run.get('conclusion') is None) or
        (run.get('status')=='completed' and run.get('conclusion')=='failure'),
        'Original production is not an eligible setup failure')
    producer=one(jobs,'bounded-stage')
    require(producer.get('status')=='completed' and producer.get('conclusion')=='success' and
        producer.get('run_id')==run['id'],'Original producer did not complete successfully')
    if not any(j.get('name')=='independent-recovery' for j in jobs):
        # A terminal GitHub scheduler failure can leave downstream jobs absent.
        # The caller must supply the complete, first-attempt job inventory. The
        # unchanged Cloud create-only claim remains the final no-replay fence.
        require(not active and run.get('status')=='completed' and
            one(jobs,'admit').get('conclusion')=='success' and
            one(jobs,'advance').get('conclusion')=='skipped' and
            len({j['name'] for j in jobs})==len(jobs) and
            all(j.get('run_id')==run['id'] and j.get('status')=='completed' and
                j.get('conclusion')==('success' if j['name'] in ('admit','bounded-stage') else 'skipped')
                for j in jobs),'Absent recovery is not a terminal scheduler-only failure')
        return
    recovery=one(jobs,'independent-recovery')
    require(recovery.get('status')=='completed' and recovery.get('conclusion')=='failure' and
        recovery.get('run_id')==run['id'],'Original recovery did not fail during setup')
    steps=recovery.get('steps') or []
    step=one(steps,RECOVERY_STEP);setup=one(steps,SETUP_STEP)
    require(step.get('status')=='completed' and step.get('conclusion')=='skipped' and
        setup.get('conclusion')=='failure' and setup.get('number',999)<step.get('number',0) and
        all(s.get('name')==SETUP_STEP for s in steps if s.get('conclusion')=='failure'),
        'Independent recovery may have started; consumed slots cannot be retried')
    require(one(jobs,'advance').get('conclusion')=='skipped' and
        all(j.get('name') in ('independent-recovery','retain-failure') for j in jobs if j.get('conclusion')=='failure'),
        'Failure is not limited to pre-recovery setup')

def producer_receipt(lines,plan_sha):
    reports=[]
    for line in lines:
        try:row=json.loads(line[line.index('{'):])
        except (ValueError,TypeError):continue
        if row.get('phase')=='production':reports.append(row)
    require(len(reports)==1,'Exact original production report required')
    p=reports[0];r=p.get('receiptRef',{})
    require(p.get('status') in ('complete','bounded-stop') and p.get('diagnostic') is None and
        r.get('key')=='engineering/map-production/plans/'+plan_sha+'/slots/00001/receipt.json' and
        re.fullmatch('[0-9a-f]{64}',str(r.get('sha256',''))) is not None and
        re.fullmatch('[1-9][0-9]*',str(r.get('generation',''))) is not None and
        type(r.get('bytes')) is int and r['bytes']>0,'Unverified original producer receipt')
    return r

def validate_split_recovery(original_run,original_jobs,original_state,execution):
    eligible_parent(original_run,original_jobs,original_state)
    run,jobs,state=execution['run'],execution['jobs'],execution['state']
    identity(run,state,'recovery')
    require(state.get('mode')=='recover' and
        all(state.get(k)==original_state.get(k) for k in ('sequence','sourceSHA','planSHA256')) and
        state['recoveryOnlyOf'].get('runID')==original_run['id'] and
        state['recoveryOnlyOf'].get('dispatchID')==original_state['dispatchID'],
        'Recovery-only parent or source binding changed')
    require((run.get('status')=='in_progress' and run.get('conclusion') is None) or
        (run.get('status')=='completed' and run.get('conclusion')=='success'),
        'Recovery-only run did not succeed')
    require(one(jobs,'bounded-stage').get('conclusion')=='skipped' and
        one(jobs,'independent-recovery').get('run_id')==run['id'],
        'Recovery-only execution attempted production or reused another recovery')
