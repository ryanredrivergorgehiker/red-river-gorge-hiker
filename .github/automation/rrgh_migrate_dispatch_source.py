#!/usr/bin/env python3
"""Forward-only replacement of the unstarted Wave058 plan after owner authorization.

Historical plans remain byte-identical. All resource/source/quality policies and
the previous independent receipt remain unchanged. New executable bytes receive
a new immutable plan identity before any production allocation is consumed.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys
import zlib

EXPECTED = '982bf03c6053808daeb55929cd33d6ed1f1bf00c11d0de1ba247fbb742b73833'
OLD = 'gorge-campaign-wave-058-20261031'
NEW = 'gorge-campaign-wave-058-20261102'


def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def migrate(root):
    root=Path(root); scripts=root/'backend/scripts'; old=root/'backend/config'/OLD; new=old.with_name(NEW)
    plan=json.loads((old/'PLAN.json').read_bytes())
    if digest(canonical(plan)) != EXPECTED or new.exists():
        raise ValueError('Wrong or already-migrated immutable predecessor source')
    allowance=json.loads((old/'ALLOWANCE.json').read_bytes())
    region=json.loads(zlib.decompress(base64.b64decode((old/'REGION-PLAN.json.z.b64').read_bytes())))
    if digest(canonical(region)) != plan['regionPlanSHA256']:
        raise ValueError('Original region hash mismatch')
    code=scripts/'gorge_campaign.py'; text=code.read_text()
    pointer="CONFIG=SOURCE.parent/'config/"+OLD+"'"
    if text.count(pointer)!=1:raise ValueError('Source pointer drift')
    code.write_text(text.replace(pointer,"CONFIG=SOURCE.parent/'config/"+NEW+"'"))
    for name in region['engineHashes']:
        region['engineHashes'][name]=digest((scripts/name).read_bytes())
    region['engineHashes']['gorge_producer_identity.py']=digest((scripts/'gorge_producer_identity.py').read_bytes())
    plan['campaign']['controllerEpoch']=1
    plan['campaign']['controllerAuthorization']='Owner 2026-11-02: exact restricted workflow_dispatch identity and autonomous controller'
    plan['regionPlanSHA256']=digest(canonical(region))
    plan['sourceSnapshotSHA256']=digest(canonical({p.name:digest(p.read_bytes())
        for p in sorted(scripts.glob('*.py')) if not p.name.startswith('test_')}))
    allowance['cloudStorageAllowance']['planSHA256']=digest(canonical(plan))
    new.mkdir()
    (new/'PLAN.json').write_bytes(canonical(plan))
    (new/'ALLOWANCE.json').write_bytes(canonical(allowance))
    (new/'REGION-PLAN.json.z.b64').write_bytes(base64.b64encode(zlib.compress(canonical(region),9)))
    return {'sequence':58,'previousPreparedPlanSHA256':EXPECTED,'planSHA256':digest(canonical(plan)),
            'sourceSnapshotSHA256':plan['sourceSnapshotSHA256'],'previousRecovery':plan['campaign']['previousRecovery'],
            'jobs':len(plan['approvedJobIDs']),'cloudProductionStarted':False}


if __name__=='__main__':
    print(json.dumps(migrate(sys.argv[1]),sort_keys=True))
