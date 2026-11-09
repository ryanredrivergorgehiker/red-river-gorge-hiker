"""Bounded read-only inspection of one failed immutable source allocation.

No Cloud writes, lists, source rendering, token output or permission changes.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request,build_opener,HTTPRedirectHandler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def credential():
    # Refreshing credentials is read-only. No failed storage request is replayed.
    for attempt in range(3):
        try:
            p=subprocess.run(['gcloud','auth','print-access-token','--quiet'],stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,timeout=30)
            value=p.stdout.strip()
            if p.returncode==0 and value and not any(c.isspace() for c in value):return value
        except subprocess.TimeoutExpired:pass
        if attempt<2:time.sleep(attempt+1)
    raise RuntimeError('Short-lived credential refresh failed after three bounded attempts')

def inspect(source_root):
    source=Path(source_root).resolve();sys.path.insert(0,str(source/'backend/scripts'))
    from gorge_campaign import configuration
    from gorge_checkpoint import canonical,digest,decode_record
    from gorge_producer_identity import require_owner
    plan,_,_=configuration();require_owner(plan,'recovery')
    sha=digest(canonical(plan))
    if sha!=os.environ.get('RRGH_PLAN_SHA256'):raise ValueError('Inspection plan changed')
    base='engineering/map-production/plans/'+sha+'/'
    keys=[base+f'slots/{slot:05d}/{name}.json' for slot in range(3) for name in ('claim','receipt')]
    keys += [base+'slots/00001/jobs/'+job+'.json' for job in plan['approvedJobIDs']]
    from rrgh_checkpoint_recovery import bounds
    limits=bounds(plan)
    if len(keys)>limits['objects']:raise ValueError('Inspection exact object bound')
    from rrgh_wif_credentials import token
    access=token();opener=build_opener(NoRedirect);total=0;requests=0;rows=[]
    for key in keys:
        url='https://storage.googleapis.com/storage/v1/b/'+plan['bucket']+'/o/'+quote(key,safe='')
        def get(query,maximum):
            nonlocal total,requests
            requests+=1
            if requests>limits['requests']:raise ValueError('Inspection request bound')
            req=Request(url+'?'+query,headers={'Authorization':'Bearer '+access,'Accept-Encoding':'identity'})
            with opener.open(req,timeout=30) as response:
                raw=response.read(maximum+1)
                if len(raw)>maximum:raise ValueError('Inspection response limit')
                total+=len(raw)
                if total>limits['bytes']:raise ValueError('Inspection total byte limit')
                return raw
        try:metadata=json.loads(get('fields=name,generation,size',16384))
        except HTTPError as exc:
            if exc.code==404:rows.append(dict(key=key,exists=False));continue
            raise RuntimeError('Inspection metadata HTTP '+str(exc.code)) from None
        size=int(metadata['size']);generation=str(metadata['generation'])
        if metadata['name']!=key or not 0<size<=512*1024:raise ValueError('Inspection object bound')
        raw=get('alt=media&generation='+generation+'&ifGenerationMatch='+generation,size)
        if len(raw)!=size:raise ValueError('Inspection length mismatch')
        obj=json.loads(raw) if key.endswith('/claim.json') else decode_record(raw)
        if obj.get('planSHA256')!=sha:raise ValueError('Inspection object belongs to another plan')
        rows.append(dict(key=key,exists=True,ref=dict(key=key,generation=generation,bytes=size,sha256=hashlib.sha256(raw).hexdigest()),record=obj))
    return dict(phase='checkpoint-inspection',planSHA256=sha,sequence=plan['campaign']['sequence'],
        cloudWrites=0,sourceRequests=0,readResponseBytes=total,readRequests=requests,objects=rows,productionAccepted=False)

if __name__=='__main__':print(json.dumps(inspect(Path(sys.argv[1])),sort_keys=True))
