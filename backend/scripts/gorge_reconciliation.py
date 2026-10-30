"""One owner-authorized transition only; no general closed-slot refund API."""
from dataclasses import asdict
import base64
import hashlib
import json
from pathlib import Path

from gorge_checkpoint import (BUCKET, PREFIX, DIMENSIONS, Ref, canonical, digest,
    integer, decode_record, MAX_METADATA, COMPACT_CLAIM, COMPACT_RECEIPT)

ORIGINAL='42a3aed271084ebc087eb0028ac4ec32b6f07b3fce3cf5262da90a7fd25de42b'
RECEIPTS=(
 ('1793309158922360',939,'439788ba2c96c71857fca1e39fb856f88eebdaa414acc30276dfc1eb46cea879'),
 ('1793309628197638',1174,'c6c9a26e5414cd32cfc941f02d6c00c6072401a735bcbe7418c42a42c778fc03'))
MIN_CARRY={'storedBytes':308693877+COMPACT_RECEIPT,'egressBytes':451641069+2**20,
 'classARequests':35,'classBRequests':13,'seconds':142,'attempts':0,'sourceBytes':0,'sourceRequests':0}

def validate_reconciliation(plan,evidence):
    r=plan.get('reconciliation')
    if r is None:return
    if r.get('format')=='rrgh-stage-reconciliation-v2':
        from gorge_stage_reconcile import validate
        return validate(plan,evidence)
    original=r['originalPlan']
    if (digest(canonical(original))!=ORIGINAL or r.get('originalPlanSHA256')!=ORIGINAL
        or r.get('format')!='rrgh-one-time-reconciliation-v1'
        or r.get('ownerApproval')!='Owner 2026-10-29: ONE-TIME RECONCILED CONTINUATION'
        or r.get('oneTimeOnly') is not True):raise ValueError('Specific reconciliation approval required')
    if (plan['limits']!=original['limits'] or plan['approvedJobIDs']!=original['approvedJobIDs']
        or plan['completedJobIDs']!=original['completedJobIDs']
        or plan['completedDependencies']!=original['completedDependencies']
        or plan['jobPolicies']!=original['jobPolicies']):raise ValueError('Original ceilings/jobs/history changed')
    if r.get('carriedUsage')!=MIN_CARRY:raise ValueError('Prior charges/failure allowance changed')
    if r.get('maxWorkflowSeconds')!=10380 or r['maxWorkflowSeconds']+MIN_CARRY['seconds']>original['limits']['seconds']:
        raise ValueError('Whole-workflow runtime not bounded')
    for k in DIMENSIONS:
        if MIN_CARRY[k]+sum(integer(s[k]) for s in plan['slots'])>original['limits'][k]:
            raise ValueError('Cumulative continuation exceeds '+k)
    refs=r['priorReceiptRefs']
    for slot,ref,known in zip((0,2),refs,RECEIPTS):
        if (ref['key']!=PREFIX+'plans/'+ORIGINAL+f'/slots/{slot:05d}/receipt.json'
            or (ref['generation'],ref['bytes'],ref['sha256'])!=known):raise ValueError('Unpinned original receipt')
    if len(refs)!=2 or len(r['seedRefs'])!=6 or len(r['seedCatalogRefs'])!=6:
        raise ValueError('Complete original checkpoint references required')
    if plan.get('seedIngress')!='reuse-generation-pinned-v1':raise ValueError('Seed must be reused')
    if evidence.get('oneTimeReconciliationSHA256')!=digest(canonical(r)):
        raise ValueError('Approval must bind exact reconciliation')

def transition(slot,plan,evidence,root):
    """Fence old unused slot with a create-only object, then verify old history.

    This costs the NEW bootstrap meter. No old claim is reopened or changed.
    A prior old worker claim or competing transition returns 412 and stops.
    """
    if plan['reconciliation'].get('format')=='rrgh-stage-reconciliation-v2':
        from gorge_stage_reconcile import transition as stage_transition
        return stage_transition(slot,plan,evidence,root)
    validate_reconciliation(plan,evidence);r=plan['reconciliation']
    key=PREFIX+'plans/'+ORIGINAL+'/slots/00001/claim.json'
    raw=canonical({'format':'rrgh-one-time-reconciliation-fence-v1',
        'originalPlanSHA256':ORIGINAL,'continuationPlanSHA256':digest(canonical(plan)),
        'continuationClaim':asdict(slot.claim),'ownerApproval':r['ownerApproval'],
        'oldWorkerPermanentlyRetired':True,'carriedUsage':r['carriedUsage']})
    if len(raw)>COMPACT_CLAIM:raise ValueError('Transition fence bound')
    slot.meter.reserve(classARequests=1,storedBytes=len(raw),egressBytes=MAX_METADATA+1)
    response,_,_=slot.store._request('POST',key,{'uploadType':'media','name':key,
        'ifGenerationMatch':'0'},MAX_METADATA,data=raw)
    m=json.loads(response)
    if (m.get('bucket')!=BUCKET or m.get('name')!=key or int(m['size'])!=len(raw)
        or m.get('md5Hash')!=base64.b64encode(hashlib.md5(raw,usedforsecurity=False).digest()).decode()):
        raise ValueError('Transition fence verification failed')
    fence=Ref(key,str(m['generation']),len(raw),digest(raw))
    history=[]
    for index,ref,run in zip((0,2),r['priorReceiptRefs'],('40957497769','40958769659')):
        record=decode_record(slot.get(Ref(**ref)))
        if (record.get('format')!='rrgh-slot-receipt-v1' or record.get('slot')!=index
            or record.get('planSHA256')!=ORIGINAL
            or record.get('nonrefundableAllocation')!=r['originalPlan']['slots'][index]):
            raise ValueError('Closed reservation identity changed')
        claim=Ref(**record['claim'])
        if claim.key!=PREFIX+'plans/'+ORIGINAL+f'/slots/{index:05d}/claim.json':
            raise ValueError('Wrong historical claim')
        c=json.loads(slot.get(claim))
        if c.get('owner')!=run or c.get('allocation')!=record['nonrefundableAllocation']:
            raise ValueError('Wrong historical execution')
        if any(integer(record['used'][k])>record['nonrefundableAllocation'][k] for k in DIMENSIONS):
            raise ValueError('Historical reservations escaped limits')
        history.append(record)
    first=history[0]['result'];second=history[1]['result']
    if first.get('status')!='failed' or first.get('phase')!='bootstrap':raise ValueError('Original worker may have run')
    if any(s not in (200,206,308) for s in first['gcs']['statuses']+second['gcsBeforeFinalReceipt']['statuses']):
        raise ValueError('Ambiguous historical HTTP reservation cannot be reclaimed')
    if (second.get('rasterAttempts')!=0 or second.get('priorBootstrap')!=first
        or second.get('priorBootstrapReceipt')!=r['priorReceiptRefs'][0]):
        raise ValueError('Reconciliation history changed')
    if (sorted((x['ref'] for x in first['preservedIngress']),key=lambda x:x['sha256'])
        !=sorted(r['seedRefs'],key=lambda x:x['sha256'])
        or not all(x['accepted'] for x in first['preservedIngress'])):
        raise ValueError('Seed lineage is not fully accepted')
    # The failed Base operation consumed its full length reservation. Retain it
    # plus 1 MiB metadata/receipt uncertainty above the measured aggregate.
    if first['gcs']['mediaReadBytes']!=449433764:raise ValueError('Historical Base read changed')
    result={'fenceRef':asdict(fence),'priorReceiptRefs':r['priorReceiptRefs'],
        'carriedUsage':r['carriedUsage'],'historicalReservations':[x['used'] for x in history],
        'historicalAllocations':[x['nonrefundableAllocation'] for x in history],
        'oldWorkerRetired':True,'oneTimeOnly':True}
    transition_ref=slot.put(canonical(result),'indexes')
    slot.get(transition_ref)
    result['transitionRef']=asdict(transition_ref)
    from gorge_stage_inputs import private_write
    private_write(Path(root)/'TRANSITION.json',canonical(result))
    print(json.dumps({'oneTimeTransition':result},sort_keys=True),flush=True)
    return result
