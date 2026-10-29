#!/usr/bin/env python3
"""One source-bounded native child under a durable checkpoint Slot.

No dispatch CLI is provided. The parent must first claim a finite slot and import
verified old receipts. Calling run_job never resumes an old mutable source ledger.
All official HTTP requests in the existing worker pass through SourceOpener.
"""
from dataclasses import asdict
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener
from urllib.parse import urlparse

from gorge_checkpoint import Meter, NoRedirect, canonical, digest, integer, relative_path, pack_delta


class LimitedResponse:
    def __init__(self,response,maximum,entry=None):
        self.response=response;self.remaining=maximum;self.entry=entry
    def __enter__(self):return self
    def __exit__(self,*args):return self.response.__exit__(*args)
    def __getattr__(self,name):return getattr(self.response,name)
    def read(self,size=-1):
        if size<0 or size>self.remaining:raise ValueError('Unbounded source response read')
        raw=self.response.read(size);self.remaining-=len(raw)
        if self.entry is not None:self.entry['receivedBodyBytes']+=len(raw)
        return raw


class SourceOpener:
    def __init__(self,meter,opener=None):
        self.meter=meter;self.opener=opener or build_opener(NoRedirect()).open
        self.entries=[]
    def summary(self):
        return {'operations':len(self.entries),
                'receivedBodyBytes':sum(e['receivedBodyBytes'] for e in self.entries),
                'reservedResponseBytes':sum(e['reservedResponseBytes'] for e in self.entries),
                'statuses':[e['status'] for e in self.entries]}
    def __call__(self,request,timeout=None):
        url=request.full_url;p=urlparse(url)
        if p.scheme!='https' or p.username or p.password or p.port or p.fragment:
            raise ValueError('Invalid official source URL')
        host=p.hostname
        if host in ('kyfromabove.s3.us-west-2.amazonaws.com','prd-tnm.s3.amazonaws.com'):
            from cached_cog_source import official_url, RANGE
            official_url(url)
            if request.get_method()=='HEAD':maximum=0
            else:
                match=RANGE.fullmatch(request.get_header('Range',''))
                if not match:raise ValueError('COG requires bounded range')
                start,end=map(int,match.groups());maximum=end-start+1
                if not 0<maximum<=2097152:raise ValueError('Unbounded COG request')
        elif host=='kyraster.ky.gov' and p.path.startswith('/arcgis/rest/services/ImageServices/Ky_NAIP_2022_2FT/ImageServer'):
            maximum=8_000_001 if p.path.endswith('/exportImage') else 1_000_001
        elif host=='basemap.nationalmap.gov' and p.path.startswith('/arcgis/rest/services/USGSTopo/MapServer'):
            maximum=500_001 if '/tile/' in p.path else 1_000_001
        else:raise ValueError('Unapproved source endpoint')
        reservation={'sourceRequests':1,'sourceBytes':maximum}
        # Optional coordinator cache-growth suballocation. Reserve before HTTP,
        # including metadata slack; never refund short responses or failed I/O.
        if self.meter.caps['storedBytes']:
            reservation['storedBytes']=maximum+8192
        self.meter.reserve(**reservation)
        entry={'method':request.get_method(),'reservedResponseBytes':maximum,
               'receivedBodyBytes':0,'status':None}
        self.entries.append(entry)
        try:
            response=self.opener(request,timeout=min(timeout or 45,45));entry['status']=response.status
            return LimitedResponse(response,maximum,entry)
        except Exception as error:
            entry['status']=getattr(error,'code',None)
            raise


def run_job(slot, plan_path, job_id, root, cog_cache, service_cache, source_caps, seconds, growth_cap=None):
    """Reserve entire child allowance before subprocess; crashes get no refunds."""
    plan=json.loads(Path(plan_path).read_bytes())
    if not any(j['id']==job_id for j in plan['jobs']):raise ValueError('Job absent from pinned plan')
    if not 1<=integer(seconds)<=600:raise ValueError('Child timeout required')
    expected=slot.plan.get('regionPlanSHA256')
    if expected!=digest(canonical(plan)):raise ValueError('Region plan not pinned to durable allocation')
    if job_id in slot.plan.get('completedJobIDs',[]):raise ValueError('Completed job must not run again')
    allowed=slot.plan.get('slotJobs',{}).get(str(slot.index),[])
    if job_id not in allowed:raise ValueError('Job not allocated to this slot')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    ticket=root/('gate-c-'+job_id+'.json')
    if ticket.exists():raise ValueError('Local job reservation already consumed')
    if seconds > slot.meter.deadline-time.monotonic():
        raise ValueError('Child cannot finish within remaining slot deadline')
    byte_cap=integer(source_caps['sourceBytes']);request_cap=integer(source_caps['sourceRequests'])
    slot.meter.reserve(attempts=1,seconds=seconds,sourceBytes=byte_cap,sourceRequests=request_cap)
    caps={k:0 for k in slot.meter.caps};caps.update(sourceBytes=byte_cap,sourceRequests=request_cap,seconds=seconds)
    if growth_cap is not None:
        caps['storedBytes']=integer(growth_cap)
        # A zero remaining growth allocation must forbid all new source I/O.
        if not growth_cap:caps.update(sourceBytes=0,sourceRequests=0)
    payload={'plan':str(Path(plan_path).resolve()),'planSHA256':expected,'job':job_id,
             'root':str(root),'cogCache':str(Path(cog_cache).resolve()),
             'serviceCache':str(Path(service_cache).resolve()),'caps':caps}
    with ticket.open('xb') as f:f.write(canonical(payload));f.flush();os.fsync(f.fileno())
    log=root/('gate-c-'+job_id+'.log')
    started=time.monotonic()
    with log.open('xb') as stream:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--ticket',str(ticket)],
            stdout=stream,stderr=subprocess.STDOUT,timeout=seconds,check=False,
            env={**os.environ,'GDAL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
    if result.returncode:raise RuntimeError('Bounded worker failed; reservation retained')
    receipt=validate_receipt(plan,job_id,root)
    usage=json.loads(ticket.with_suffix('.usage.json').read_bytes())
    if usage.get('completed') is not True:raise ValueError('Completed source-usage receipt required')
    receipt['execution']={'wallSeconds':round(time.monotonic()-started,6),'sourceUsage':usage}
    return receipt


def validate_receipt(plan, job_id, root):
    root=Path(root).resolve();r=json.loads((root/'receipts'/(job_id+'.json')).read_bytes())
    expected=digest((json.dumps(plan,sort_keys=True,indent=2)+'\n').encode())
    if r.get('validated') is not True or r.get('job')!=job_id or r.get('recipeSHA256')!=expected:
        raise ValueError('Worker receipt invalid')
    seen=set();total=0
    for e in r['outputs']:
        name=relative_path(e['path']);p=root/name
        if name in seen or p.is_symlink() or root not in p.resolve().parents:raise ValueError('Unsafe/duplicate output')
        seen.add(name);total+=integer(e['bytes'])
        if total>32_000_000 or p.stat().st_size!=e['bytes'] or digest(p.read_bytes())!=e['sha256']:
            raise ValueError('Worker output bound/hash mismatch')
    if not seen:raise ValueError('Empty worker receipt')
    return r


def checkpoint_job(slot, receipt, root):
    """Commit genuine outputs then a deterministic per-job recovery receipt.

    A crash after this receipt never requires rerendering this job. A crash before
    it leaves orphaned create-only packs charged; no silent rerender/retry occurs.
    """
    packs=[]
    for raw,info in pack_delta(root,receipt['outputs']):
        packs.append({'ref':asdict(slot.put(raw,'outputs')),'members':info['members']})
    return slot.commit_job(receipt['job'],{'originalReceipt':receipt,'outputPacks':packs})


def child(ticket):
    # Exclusive marker is written before imports/network/native work.
    ticket=Path(ticket);p=json.loads(ticket.read_bytes())
    marker=ticket.with_suffix('.consumed')
    with marker.open('xb') as f:f.write(b'consumed\n');f.flush();os.fsync(f.fileno())
    plan=json.loads(Path(p['plan']).read_bytes())
    if digest(canonical(plan))!=p['planSHA256']:raise ValueError('Region plan changed')
    import orchestrate_gorge_region as engine
    import cached_cog_source as cog
    import benchmark_ky_naip_usgs as services
    for name,sha in plan['engineHashes'].items():
        if Path(name).name!=name or digest((Path(__file__).parent/name).read_bytes())!=sha:
            raise ValueError('Pinned engine changed')
    meter=Meter(p['caps']);opener=SourceOpener(meter);original=cog.Cache
    def cache(*args,**kwargs):
        kwargs['opener']=opener
        return original(*args,**kwargs)
    engine.Cache=cache;services.urlopen=opener
    job=next(j for j in plan['jobs'] if j['id']==p['job'])
    from benchmark_gorge_pipeline import json_bytes
    from cached_cog_source import atomic
    completed=False
    try:
        receipt=engine.worker(plan,job,p['root'],p['cogCache'],p['serviceCache'])
        # Retain the existing recipe convention; never rewrite old receipts.
        atomic(Path(p['root'])/'receipts'/(job['id']+'.json'),json_bytes(receipt))
        completed=True
    finally:
        # Failures retain observed partial counts. A killed process still keeps
        # its full durable parent allocation; missing usage never means zero.
        atomic(ticket.with_suffix('.usage.json'),canonical({'reserved':meter.used,
            'actual':opener.summary(),'completed':completed}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ticket',required=True,type=Path)
    child(parser.parse_args().ticket)
