"""Acquire real child receipt authority from exact historical Git plans.

No Cloud requests or production writes. This proves manifest acquisition only;
protected child-byte readback still requires a fresh approved production slot.
"""
import base64
import json
from pathlib import Path
import sys
import zlib
from build_completion_receipt_index import build,canonical,sha
from rrgh_crosswave_dependencies import manifest

root=Path(__file__).resolve().parent
audit=json.loads((root/'fixtures/wave1322-audit.json').read_bytes())
index=build(sys.argv[1],audit)
assert sha(canonical(index))=='1fea8db2f65861e50130856a152cec5862baee2a483ace4eef328a96930c4974'
assert index['indexedJobs']==25504 and len(index['unindexedAcceptedJobs'])==44 and len(index['waves'])==1322
accepted={j for wave in index['waves'] for j in wave['acceptedJobIDs']}|set(index['unindexedAcceptedJobs'])
bindings=[]
for layer,x,y in [('hiking',8756,12645),('terrain',8756,12645),('leaf-on',8756,12646),('leaf-off',8756,12645)]:
    job=dict(id=f'{layer}-15-{x}-{y}',layer=layer,z=15,x=x,y=y,
        operation='overview',sourceIDs=[],outputTiles=[[15,x,y]])
    assert job['id'] not in accepted
    m=manifest(index,job,accepted)
    assert len({c['source']['sequence'] for c in m['children']})>1
    bindings.append(m)
result=dict(format='rrgh-reviewed-crosswave-candidates-v1',baseline=index['anchor'],
    receiptIndexSHA256=sha(canonical(index)),bindings=bindings,
    protectedByteReadbackPerformed=False,productionEnrolled=False)
raw=canonical(result)
print(json.dumps(dict(verified='real immutable cross-wave child manifest acquisition',
    indexedJobs=25504,seedJobsRequiringSeparateProof=44,parentCandidates=[m['job']['id'] for m in bindings],
    bindingSHA256=sha(raw),bindingBytes=len(raw),sourceRequests=0,cloudRequests=0,productionEnrolled=False)))
print('RRGH_CROSSWAVE_BINDING_ZLIB_BASE64='+base64.b64encode(zlib.compress(raw,9)).decode())
