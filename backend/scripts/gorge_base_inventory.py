"""Private reusable member index of the already verified Base generation."""
import json,tarfile
from dataclasses import asdict
from gorge_checkpoint import canonical,digest,Slot
from gorge_base_ranges import AcceptedBaseRanges,BASE_AUTHORITY
from gorge_stage_inputs import base_member_index

def archive_inventory(t,expected_manifest='0ed6f18d170724898961cfe69d52c424935a97afade61d51e97961efe244ce88'):
    members=base_member_index(t);member=members['NATIVE-MAP.json']
    raw=t.extractfile(member).read();manifest=json.loads(raw)
    if digest(raw)!=expected_manifest:raise ValueError('Accepted manifest changed')
    names={e['path'] for e in manifest['vectors']+[manifest['weatherManifest']]+[v for v in manifest['staticAssets'] if 'rrg-lidar-sun' not in v['path']]}
    wanted=[{'path':name,'bytes':members[name].size,'offset':members[name].offset_data} for name in sorted(names|{'NATIVE-MAP.json'})]
    result={'format':'rrgh-accepted-base-index-v1','acceptedBase':BASE_AUTHORITY,'manifest':manifest,'manifestSHA256':digest(raw),'members':wanted,'archiveMembers':len(members)}
    return result

def inventory(plan,evidence,root,store,opener):
    import os
    from gorge_stage_reconcile import transition
    slot=Slot(store,plan,0,os.environ['GITHUB_RUN_ID']);opener.deadline=slot.meter.deadline
    try:
        transition(slot,plan,evidence,root)
        with AcceptedBaseRanges(slot) as reader,tarfile.open(fileobj=reader,mode='r:') as t:
            result=archive_inventory(t)
            wanted=result['members']
            ref=slot.put(canonical(result),'indexes');slot.get(ref)
            summary={'status':'inventory-complete','indexRef':asdict(ref),'requiredSharedBytes':sum(x['bytes'] for x in wanted),'requiredMembers':len(wanted),'largestMemberBytes':max(x['bytes'] for x in wanted),'archiveMembers':result['archiveMembers'],'headerReadBytes':reader.received,'headerReadRequests':reader.requests,'rasterAttempts':0,'gcs':opener.summary()}
        receipt=slot.finish(summary)
        print(json.dumps({'baseInventory':summary,'receiptRef':asdict(receipt),'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
    except Exception as error:
        if not slot.closed:
            import traceback
            result={'status':'failed','phase':'inventory','diagnostic':{'errorClass':type(error).__name__,'frames':[{'file':t.name,'line':t.lineno} for t in traceback.extract_tb(error.__traceback__)]},'gcs':opener.summary()}
            ref=slot.finish(result);print(json.dumps({'inventoryFailure':result,'receiptRef':asdict(ref),'gcsIncludingReceipt':opener.summary()}),flush=True)
        raise
