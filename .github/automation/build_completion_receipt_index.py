"""Read immutable Git plans only. Index pins; do not claim protected-byte QA.

Walk backward from the independently audited wave1322 acceptance. Every normal
predecessor is located by the exact recovery plan hash, not a filename guess.
Stop visibly at exceptional/missing lineage; never synthesize a receipt pin.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def build(source,audit):
    source=Path(source);folder=source/'backend/config/gorge-campaign-wave-1322-20261102'
    plan=json.loads((folder/'PLAN.json').read_bytes())
    assert sha(canonical(plan))==audit['planSHA256']=='e2631ee1ca7b5a8b0dd787afcabcf8abfbf9d76e3420f2dbdd28a2f33eaa4902'
    accepted=set(plan['completedJobIDs']+plan['approvedJobIDs'])
    assert len(accepted)==audit['acceptedJobs']==25548 and audit['acceptedRasterTiles']==265702
    remaining=set(accepted);next_accepted=set(accepted);recovery=audit['receiptRef']
    waves=[];stop=None
    while True:
        seq=plan['campaign']['sequence'];plan_sha=sha(canonical(plan))
        prefix='engineering/map-production/plans/'+plan_sha+'/slots/00002/receipt.json'
        special = {289:'wave289-consumed-recovery',11:'wave011-salvage'}
        assert recovery['key']==prefix or seq in special
        assert set(plan['completedJobIDs'])<=next_accepted
        delta=next_accepted-set(plan['completedJobIDs'])
        assert delta<=set(plan['approvedJobIDs']) and delta<=remaining
        region=json.loads(zlib.decompress(base64.b64decode((folder/'REGION-PLAN.json.z.b64').read_bytes())))
        assert sha(canonical(region))==plan['regionPlanSHA256']
        jobs={j['id']:j for j in region['jobs']}
        assert set(jobs)==set(plan['approvedJobIDs'])
        waves.append(dict(sequence=seq,sourcePlanSHA256=plan_sha,recovery=recovery,
            recipeSHA256=sha((json.dumps(region,indent=2,sort_keys=True)+'\n').encode()),
            sourceJobCount=len(delta),acceptedJobIDs=sorted(delta),
            expectedTiles=sum(len(jobs[j]['outputTiles']) for j in delta),
            acceptanceKind=(special[seq] if recovery['key']!=prefix else
                'ordinary' if delta==set(plan['approvedJobIDs']) else 'partial-needs-typed-receipt'),
            sourceConfig=str(folder.relative_to(source))))
        remaining-=delta;next_accepted=set(plan['completedJobIDs'])
        if seq==0:
            stop=dict(reason='pre-campaign accepted seed',remainingJobs=len(remaining));break
        recovery=plan['campaign']['previousRecovery']
        match=re.fullmatch(r'engineering/map-production/plans/([0-9a-f]{64})/slots/(00002|00000|00001)/receipt.json',recovery['key'])
        if not match or (match.group(2)!='00002' and seq-1 not in (289,11)):
            stop=dict(reason='exceptional recovery namespace',afterSequence=seq,recovery=recovery);break
        previous=[]
        exceptional_plan={289:'f5f2666692abc512b68445ea449314d26dad95be73ae7f12a139617490e3abdf',
            11:'03edea40b63ad8d937064e10f7b221445a55da1fa87f7689657a70efab3d96eb'}
        expected=exceptional_plan.get(seq-1,match.group(1))
        for f in sorted((source/'backend/config').glob(f'gorge-campaign-wave-{seq-1:03d}*/PLAN.json')):
            p=json.loads(f.read_bytes())
            if sha(canonical(p))==expected:previous.append((f.parent,p))
        if len(previous)!=1:
            stop=dict(reason='missing or ambiguous exact predecessor',afterSequence=seq,
                expectedPlanSHA256=match.group(1),matches=len(previous));break
        folder,plan=previous[0]
    return dict(format='rrgh-completion-receipt-index-v1',
        anchor=dict(sourceSHA='2c121dfba317d918749acaadd6842be81c88fee1',
            sequence=1322,planSHA256=audit['planSHA256'],recovery=audit['receiptRef'],
            acceptedJobs=25548,acceptedRasterTiles=265702),
        waves=waves,indexedJobs=len(accepted)-len(remaining),unindexedAcceptedJobs=sorted(remaining),
        stoppedAt=stop,protectedByteReadbackPerformed=False)

if __name__=='__main__':
    result=build(sys.argv[1],json.loads(Path(sys.argv[2]).read_bytes()))
    raw=canonical(result);packed=base64.b64encode(zlib.compress(raw,9)).decode()
    print(json.dumps(dict(indexedJobs=result['indexedJobs'],waves=len(result['waves']),
        unindexedJobs=len(result['unindexedAcceptedJobs']),stoppedAt=result['stoppedAt'],
        sha256=sha(raw),bytes=len(raw))))
    print('RRGH_COMPLETION_INDEX_ZLIB_BASE64='+packed)
