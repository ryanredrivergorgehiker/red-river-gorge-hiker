"""Controller-side audit of the one exact missing-closure salvage incident."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

REPO='ryanredrivergorgehiker/red-river-gorge-hiker'
BRANCH='lane20/offline-production-preflight-20261029'
WORKFLOW='.github/workflows/offline-map-restricted-dispatch.yml'
MANIFEST=Path(__file__).with_name('wave105-salvage.json')


def require(ok,message):
    if not ok:raise ValueError(message)


def manifest():return json.loads(MANIFEST.read_bytes())


def manifest_sha():return hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def one(jobs,name):
    rows=[j for j in jobs if j['name']==name]
    require(len(rows)==1,'Missing or repeated '+name)
    return rows[0]


def reports(lines):
    result=[]
    for line in lines:
        if '{' not in line:continue
        try:row=json.loads(line[line.index('{'):])
        except ValueError:continue
        if isinstance(row,dict):result.append(row)
    return result


def identity(run,mode,rid,dispatch,conclusion=None):
    m=manifest()
    require(run.get('id')==rid and run.get('run_attempt')==1 and
        run.get('head_branch')==BRANCH and run.get('path')==WORKFLOW and
        run.get('event')=='workflow_dispatch' and (run.get('actor') or {}).get('login')=='github-actions[bot]' and
        run.get('repository',{}).get('full_name')==REPO and
        run.get('display_title')==f'RRGH {mode} 105 {dispatch}', 'Salvage workflow identity changed')
    if conclusion:require(run.get('status')=='completed' and run.get('conclusion')==conclusion,'Unexpected source run conclusion')


def original(api):
    m=manifest();rid=m['originalRunID']
    run=api.call('GET','actions/runs/'+str(rid))
    data=api.call('GET','actions/runs/'+str(rid)+'/jobs?per_page=100')
    require(data['total_count']<=100,'Incomplete original jobs')
    identity(run,'production',rid,m['originalDispatchID'],'failure')
    require(run['head_sha']==m['originalHeadSHA'],'Original execution code changed')
    jobs=data['jobs'];producer=one(jobs,'bounded-stage')
    require(producer['conclusion']=='failure' and one(jobs,'independent-recovery')['conclusion']=='skipped' and
            one(jobs,'admit')['conclusion']=='success','Original recovery started or producer not failed')
    from rrgh_dispatch_audit import gh
    rows=reports(gh('actions/jobs/'+str(producer['id'])+'/logs',api.token,raw=True).splitlines())
    checkpoints=[x for x in rows if 'durableJobReceipt' in x]
    require([x['job'] for x in checkpoints]==m['completedJobIDs'] and
            [x['durableJobReceipt'] for x in checkpoints]==m['completedJobRefs'] and
            sum(x['jobTiles'] for x in checkpoints)==m['tiles'],'Original durable job evidence changed')
    require(not [x for x in rows if x.get('phase')=='production'],'Closing producer receipt unexpectedly present')
    require(any(x.get('status')=='failed-closed' and x.get('errorClass')=='RuntimeError' and
                any(f.get('file')=='run_gorge_checkpoint_slot.py' and f.get('function')=='token' for f in x.get('frames',[]))
                for x in rows),'Original credential failure not established')
    inspection=api.call('GET','actions/runs/'+str(m['inspectionRunID']))
    require(inspection['status']=='completed' and inspection['conclusion']=='success' and
            inspection['path']==WORKFLOW and inspection['head_branch']==BRANCH and
            inspection.get('run_attempt')==1 and inspection.get('actor',{}).get('login')=='github-actions[bot]' and
            inspection.get('repository',{}).get('full_name')==REPO,'Read-only inspection incomplete')
    return m


def audit(api,state):
    m=original(api)
    require(state.get('mode')=='salvage' and state.get('salvageOf',{}).get('manifestSHA256')==manifest_sha() and
            state['sourceSHA']==m['sourceSHA'] and state['planSHA256']==m['planSHA256'] and
            state['sequence']==105,'Salvage ownership changed')
    run=api.call('GET','actions/runs/'+str(state['runID']))
    identity(run,'salvage',state['runID'],state['dispatchID'])
    require(run['status'] in ('in_progress','completed') and run.get('conclusion') in (None,'success'),
            'Salvage execution not eligible')
    data=api.call('GET','actions/runs/'+str(state['runID'])+'/jobs?per_page=100')
    require(data['total_count']<=100,'Incomplete salvage jobs')
    job=one(data['jobs'],'independent-salvage')
    require(job['status']=='completed' and job['conclusion']=='success' and
            one(data['jobs'],'bounded-stage')['conclusion']=='skipped' and
            one(data['jobs'],'independent-recovery')['conclusion']=='skipped','Salvage must not execute production')
    from rrgh_dispatch_audit import gh
    rows=[r for r in reports(gh('actions/jobs/'+str(job['id'])+'/logs',api.token,raw=True).splitlines())
          if r.get('phase')=='independent-checkpoint-salvage']
    require(len(rows)==1,'One independent salvage report required')
    r=rows[0]['result'];ref=rows[0]['receiptRef'];ledger=r['settlement'];carry=r['nextCarry']
    require(r.get('status')=='partial-verified' and r.get('salvage')=='wave105-missing-producer-closure-v1' and
            r.get('originalProducerRunID')==m['originalRunID'] and r.get('producerClaim')==m['producerClaim'] and
            r.get('workerReceipt') is None and r.get('bootstrapReceipt')==m['bootstrapReceipt'] and
            r.get('completedJobRefs')==m['completedJobRefs'] and r.get('completedJobIDs')==m['completedJobIDs'] and
            r.get('uncertainJobIDs')==m['uncertainJobIDs'],'Independent salvage lineage changed')
    require(r.get('jobs')==7 and r.get('tiles')==51 and r.get('verifiedTileCatalogTiles')==51 and
            r.get('sourceJobsExecuted')==0 and r.get('adjacentEdgesMeasured',0)>0 and
            r.get('packageParts',0)>0 and r.get('packageBytes',0)>0,'Salvage QA or package evidence missing')
    require(all(r.get(k) is True for k in ('allOutputHashesAndPixelsVerified','allNewPackageChunksReadBack',
            'allExistingCachesPreserved','unacceptedAttemptsQuarantined')) and
            r['sourcePinsReconstructed'].get('allPriorPinsPreserved') is True,'Salvage preservation incomplete')
    require(ledger['sequence']==105 and ledger['planSHA256']==m['planSHA256'] and
            ledger['originalAllocation']==ledger['retainedUsage']==m['originalAllocation'] and
            ledger['demonstrablyUnused']=={k:0 for k in m['originalAllocation']} and
            ledger['ambiguousAllocationRetained'] is True and ledger['independentRecoveryComplete'] is False,
            'Failed allocation must be fully retained')
    def cost(v):
        return (Decimal(v['storedBytes'])/2**30*Decimal('.03')+
                Decimal(v['egressBytes'])/2**30*Decimal('.23')+
                Decimal(v['classARequests'])/1000*Decimal('.01')+
                Decimal(v['classBRequests'])/1000*Decimal('.001'))*Decimal('1.2')
    def monthly(v):return Decimal(v)/2**30*Decimal('.036')
    expected=dict(m['priorCarry'],chargedUSD=str(Decimal(m['priorCarry']['chargedUSD'])+cost(m['originalAllocation'])),
        storedBytes=m['priorCarry']['storedBytes']+m['originalAllocation']['storedBytes'],
        priorCompletedJobs=m['priorCarry']['priorCompletedJobs']+7,priorRasterTiles=m['priorCarry']['priorRasterTiles']+51)
    require(carry==expected and ledger['chargedUSD']==carry['chargedUSD'] and ledger['storedBytes']==carry['storedBytes'],
            'Salvage conservative carry changed')
    require(Decimal(carry['chargedUSD'])<123 and monthly(carry['storedBytes'])<2,'Cloud guard exceeded')
    require(ref['key']=='engineering/map-production/plans/'+m['planSHA256']+'/slots/00002/receipt.json' and
            type(ref['bytes']) is int and 0<ref['bytes']<100000 and str(ref['generation']).isdigit() and
            len(ref['sha256'])==64 and all(c in '0123456789abcdef' for c in ref['sha256']),
            'Invalid immutable salvage receipt')
    return dict(verified=True,partialRecovered=True,salvagedCheckpointRecovery=True,
        salvageManifestSHA256=manifest_sha(),partialCompletedJobIDs=m['completedJobIDs'],failedJobID=None,
        uncertainJobIDs=m['uncertainJobIDs'],sourcePixelGapJobs=[],sourceCompletedJobIDs=[],wave=105,
        run=m['originalRunID'],recoveryRunID=state['runID'],jobsNew=7,acceptedJobs=carry['priorCompletedJobs'],
        acceptedRasterTiles=carry['priorRasterTiles'],sunlightAssets=320,historicalExclusions=45,
        receiptRef=ref,nextCarry=carry,receiptSHA256=ref['sha256'],receiptGeneration=ref['generation'],
        planSHA256=m['planSHA256'],modeledCumulativeUSD=carry['chargedUSD'],
        modeledMonthlyStorageUSD=str(monthly(carry['storedBytes'])),dispatchAuthorized=False,
        sourcePolicyMode=state.get('sourcePolicyMode','expanded'),controllerDispatchID=state['dispatchID'],
        controllerParentRun=state.get('parentRunID'))
