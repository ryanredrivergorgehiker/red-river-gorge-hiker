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
from rrgh_seed_children import inventory as seed_inventory, read as seed_read, AUTHORITY as SEED_AUTHORITY
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

def seed_proof_summary(obj):
    files=obj['files']
    return dict(format=obj['format'],acceptedBase=obj['acceptedBase'],
        priorReceipts=obj['priorReceipts'],checkpointRefs=obj['checkpointRefs'],
        priorFiles=[f for f in files if f['kind']=='prior'],
        fileCounts={k:sum(f['kind']==k for f in files) for k in sorted({f['kind'] for f in files})})


def seed_metadata_references(plan):
    if not plan.get('finalOverviewPhase'):return []
    from rrgh_seed_children import AUTHORITY
    h=AUTHORITY['history']
    first={"finalQA":{"bytes":4780,"generation":"1793330375899481","key":"engineering/map-production/plans/94fe8e3708520332bd154ed5d759926ea60cea9b0b5d672ebab7d8152f4ba534/slots/00001/indexes/cdd62df681c6f290a93d6c0ba3e1439582909432f667f093f6e091a0acd5f0b4","sha256":"cdd62df681c6f290a93d6c0ba3e1439582909432f667f093f6e091a0acd5f0b4"},"finalRecovery":{"bytes":1849,"generation":"1793330377762909","key":"engineering/map-production/plans/94fe8e3708520332bd154ed5d759926ea60cea9b0b5d672ebab7d8152f4ba534/slots/00001/receipt.json","sha256":"736aa163445b697f82d485d070ec5aae90be3b0aaa4a82eac1aac404b6f596fa"}}
    return [dict(name=k,ref=v) for k,v in list(h.items())+list(first.items())]



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
    seeds=seed_metadata_references(plan)
    pins={row['ref']['key']:row for row in seeds}
    keys+=list(pins)
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
        pin=pins.get(key);limit=3*2**20 if pin and pin['name']=='proof' else 512*1024
        if metadata['name']!=key or not 0<size<=limit:raise ValueError('Inspection object bound')
        if pin and (size!=pin['ref']['bytes'] or generation!=pin['ref']['generation']):raise ValueError('Pinned historical metadata changed')
        raw=get('alt=media&generation='+generation+'&ifGenerationMatch='+generation,size)
        if len(raw)!=size:raise ValueError('Inspection length mismatch')
        if pin and hashlib.sha256(raw).hexdigest()!=pin['ref']['sha256']:raise ValueError('Historical metadata hash changed')
        obj=json.loads(raw) if key.endswith('/claim.json') else decode_record(raw,decoded_maximum=4*2**20)
        if pin:
            if pin['name']=='proof':obj=seed_proof_summary(obj)
        elif obj.get('planSHA256')!=sha:raise ValueError('Inspection object belongs to another plan')
        rows.append(dict(key=key,exists=True,ref=dict(key=key,generation=generation,bytes=size,sha256=hashlib.sha256(raw).hexdigest()),record=obj))
    preflight=None
    if plan.get('finalOverviewPhase') and os.environ.get('RRGH_SEED_READER_PREFLIGHT')=='1':
        from gorge_checkpoint import GCS
        from tempfile import TemporaryDirectory
        _,evidence,_=configuration()
        store=GCS(plan,evidence,lambda:access)
        class ReadOnlySlot:
            def get(self,ref,start=0,length=None,expected_sha256=None):
                nonlocal requests,total
                length=ref.bytes if length is None else length
                requests+=1
                if requests>limits['requests'] or total+length>limits['bytes']:raise ValueError('Seed preflight exceeds inspection budget')
                raw=store.read(ref,start,length);total+=len(raw)
                if expected_sha256 and hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Seed preflight member changed')
                return raw
        reader=ReadOnlySlot();cache={};inventory=seed_inventory(reader,SEED_AUTHORITY,cache)
        samples=[]
        with TemporaryDirectory() as folder:
            for kind in sorted({r['kind'] for r in inventory.values()}):
                jid=next(j for j,r in inventory.items() if r['kind']==kind)
                proof=seed_read(reader,SEED_AUTHORITY,jid,Path(folder)/jid,cache)
                samples.append(dict(job=jid,kind=kind,sha256=proof['sha256'],pixelsVerified=True))
        preflight=dict(status='verified',jobs=len(inventory),rasterTiles=sum(len(r['outputs']) for r in inventory.values()),
            samples=samples,cloudWrites=0,rasterJobsExecuted=0)
    return dict(phase='checkpoint-inspection',planSHA256=sha,sequence=plan['campaign']['sequence'],
        cloudWrites=0,sourceRequests=0,readResponseBytes=total,readRequests=requests,objects=rows,productionAccepted=False,seedReaderPreflight=preflight)

if __name__=='__main__':print(json.dumps(inspect(Path(sys.argv[1])),sort_keys=True))

