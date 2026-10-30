"""Owner-authorized stage-only settlement; never erase or reopen an old claim."""
from dataclasses import asdict
import base64,hashlib,json
from pathlib import Path
from gorge_checkpoint import (BUCKET,PREFIX,DIMENSIONS,Ref,canonical,digest,decode_record,
                              integer,MAX_METADATA,COMPACT_RECEIPT)

ORIGINAL='42a3aed271084ebc087eb0028ac4ec32b6f07b3fce3cf5262da90a7fd25de42b'
PREVIOUS='f13f5e5e70e8633d86fc1f7245178feff4424935f3d52a8f01e2b08bf8c45a11'
SECOND='1b2612084503c2760ab31c2ccd78dac6c8fda63086f76471666483f8792b60a0'
APPROVAL='Owner 2026-10-29: STAGE-SPECIFIC RECONCILIATION MECHANISM'
CARRY={'storedBytes':308705333+3*COMPACT_RECEIPT,'egressBytes':630659680+3*2**20,
       'classARequests':45,'classBRequests':98,'seconds':389,
       'attempts':0,'sourceBytes':0,'sourceRequests':0}
LAST=Ref(PREFIX+'plans/'+PREVIOUS+'/slots/00000/receipt.json','1793323231970462',686,
         '0ede931d64cfc9f08a8319e91cd5e8fd0fbbbc33545141ea884d809b05bfd2ca')

def settled_reservation(allocation,actual,padding,ambiguous=False):
    """An ambiguous operation retains its complete allocation, never zero."""
    result={}
    for k in DIMENSIONS:
        allocated=integer(allocation[k]);spent=integer(actual.get(k,0));pad=integer(padding.get(k,0))
        if spent+pad>allocated:raise ValueError('Settlement cannot conceal overrun')
        result[k]=allocated if ambiguous else spent+pad
    return {'retained':result,'demonstrablyUnused':{k:allocation[k]-result[k] for k in DIMENSIONS},
            'originalAllocation':allocation.copy(),'observedUsage':actual.copy(),
            'failurePadding':padding.copy(),'ambiguous':ambiguous}

def validate(plan,evidence):
    r=plan['reconciliation'];old=r['previousPlan'];original=r['originalPlan']
    if (r.get('format')!='rrgh-stage-reconciliation-v2' or r.get('ownerApproval')!=APPROVAL
        or digest(canonical(original))!=ORIGINAL or digest(canonical(old))!=PREVIOUS
        or r.get('previousReceiptRef')!=asdict(LAST) or r.get('carriedUsage')!=CARRY):
        raise ValueError('Exact stage-specific settlement authority required')
    oldr=old['reconciliation']
    if (r.get('priorReceiptRefs')!=oldr['priorReceiptRefs']+[oldr['previousReceiptRef']] or r.get('seedRefs')!=oldr['seedRefs']
        or r.get('seedCatalogRefs')!=oldr['seedCatalogRefs']):raise ValueError('Historical checkpoints changed')
    for k in ('limits','approvedJobIDs','completedJobIDs','completedDependencies','jobPolicies'):
        if plan[k]!=original[k]:raise ValueError('Owner limits/jobs/history changed')
    if r.get('maxWorkflowSeconds')+CARRY['seconds']>original['limits']['seconds']:
        raise ValueError('Cumulative workflow time exceeded')
    for k in DIMENSIONS:
        if CARRY[k]+sum(integer(s[k]) for s in plan['slots'])>original['limits'][k]:
            raise ValueError('Cumulative stage capacity exceeded: '+k)
    if evidence.get('stageReconciliationSHA256')!=digest(canonical(r)):
        raise ValueError('Settlement is not bound to the release')
    if plan.get('seedIngress')!='reuse-generation-pinned-v1' or plan.get('acceptedBaseAccess')!='verified-generation-selective-v1':
        raise ValueError('Verified seed and Base generations must be reused')

def create_fence(slot,key,payload):
    raw=canonical(payload)
    slot.meter.reserve(classARequests=1,storedBytes=len(raw),egressBytes=MAX_METADATA+1)
    response,_,_=slot.store._request('POST',key,{'uploadType':'media','name':key,'ifGenerationMatch':'0'},MAX_METADATA,data=raw)
    m=json.loads(response)
    if (m.get('bucket')!=BUCKET or m.get('name')!=key or int(m.get('size',-1))!=len(raw)
        or m.get('md5Hash')!=base64.b64encode(hashlib.md5(raw,usedforsecurity=False).digest()).decode()):
        raise ValueError('Settlement fence metadata mismatch')
    return asdict(Ref(key,str(m['generation']),len(raw),digest(raw)))

def transition(slot,plan,evidence,root):
    validate(plan,evidence);r=plan['reconciliation'];history=[]
    expected=[(ORIGINAL,0,'40957497769'),(ORIGINAL,2,'40958769659'),(SECOND,0,'40980260310'),(PREVIOUS,0,'40985011869')]
    refs=r['priorReceiptRefs']+[asdict(LAST)]
    for ref,(identity,index,owner) in zip(refs,expected):
        record=decode_record(slot.get(Ref(**ref)))
        parent=r['originalPlan'] if identity==ORIGINAL else r['previousPlan']['reconciliation']['previousPlan'] if identity==SECOND else r['previousPlan']
        if (record.get('format')!='rrgh-slot-receipt-v1' or record.get('planSHA256')!=identity
            or record.get('slot')!=index or record.get('nonrefundableAllocation')!=parent['slots'][index]):
            raise ValueError('Historical receipt identity mismatch')
        claim=Ref(**record['claim']);c=json.loads(slot.get(claim))
        if (claim.key!=PREFIX+'plans/'+identity+f'/slots/{index:05d}/claim.json'
            or c.get('owner')!=owner or c.get('allocation')!=record['nonrefundableAllocation']):
            raise ValueError('Historical claim identity mismatch')
        if any(integer(record['used'][k])>record['nonrefundableAllocation'][k] for k in DIMENSIONS):
            raise ValueError('Historical limit violation')
        history.append(record)
    first,diagnostic,second,last=[h['result'] for h in history]
    if first.get('phase')!='bootstrap' or last.get('phase')!='bootstrap' or first.get('status')!='failed' or last.get('status')!='failed' or second.get('status')!='failed' or diagnostic.get('rasterAttempts')!=0:
        raise ValueError('Possible historical raster use must be reconciled explicitly')
    summaries=[first['gcs'],diagnostic['gcsBeforeFinalReceipt'],second['gcs'],last['gcs']]
    if any(s not in (200,206,308) for summary in summaries for s in summary['statuses']):
        raise ValueError('Ambiguous historical operations retain allocation; no automatic settlement')
    actual={'storedBytes':sum(s['newFinalizedObjectBytes']+ref['bytes'] for s,ref in zip(summaries,refs)),
            'classARequests':sum(s['classAHTTPRequests']+1 for s in summaries),
            'classBRequests':sum(s['classBHTTPRequests'] for s in summaries),
            'mediaReadBytes':sum(s['mediaReadBytes'] for s in summaries)}
    if actual!={'storedBytes':308705333,'classARequests':45,'classBRequests':98,'mediaReadBytes':630599392}:
        raise ValueError('Prior measured operations changed')
    # One create-only successor record serializes all contenders. Old unused
    # worker/recovery claims are then fenced before any new input/source work.
    payload={'format':'rrgh-stage-successor-v2','stagePlanSHA256':ORIGINAL,
        'predecessorPlanSHA256':PREVIOUS,'successorPlanSHA256':digest(canonical(plan)),
        'successorClaim':asdict(slot.claim),'ownerApproval':APPROVAL,'carriedUsage':CARRY}
    fences=[create_fence(slot,PREFIX+'plans/'+PREVIOUS+'/successor.json',payload)]
    for index in (1,2):fences.append(create_fence(slot,PREFIX+'plans/'+PREVIOUS+f'/slots/{index:05d}/claim.json',payload))
    observed={**CARRY,'storedBytes':actual['storedBytes'],'egressBytes':630659680}
    settlement=settled_reservation(plan['limits'],observed,{'storedBytes':3*COMPACT_RECEIPT,'egressBytes':3*2**20})
    if settlement['retained']!=CARRY:raise ValueError('Audited retained capacity differs')
    result={'settlement':settlement,'format':'rrgh-stage-settlement-v2','originalPlanSHA256':ORIGINAL,'previousPlanSHA256':PREVIOUS,
        'priorReceiptRefs':refs,'historicalReservations':[h['used'] for h in history],
        'historicalAllocations':[h['nonrefundableAllocation'] for h in history],
        'historicalClaims':[h['claim'] for h in history],'measuredUsage':actual,'carriedUsage':CARRY,
        'failurePadding':{'storedBytes':3*COMPACT_RECEIPT,'egressBytes':3*2**20},
        'fenceRefs':fences,'stageSpecificApproval':APPROVAL,'noClosedClaimModified':True}
    ref=slot.put(canonical(result),'indexes');slot.get(ref);result['transitionRef']=asdict(ref)
    from gorge_stage_inputs import private_write
    private_write(Path(root)/'TRANSITION.json',canonical(result))
    print(json.dumps({'stageSettlement':result},sort_keys=True),flush=True)
    return result
