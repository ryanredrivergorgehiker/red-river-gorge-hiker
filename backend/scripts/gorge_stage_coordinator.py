#!/usr/bin/env python3
"""Exactly one already-authorized 12-job stage; immutable claims fail closed.

This is not a campaign dispatcher. A fresh workflow attempt, failed claim,
changed source, missing input, exceeded cache bound or ambiguous HTTP stops.
No public artifacts/cache, payload logging, retries, IAM, deletes or deployment.
"""
import argparse
import base64
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
from urllib.request import build_opener
import zlib

from gorge_checkpoint import (GCS, Slot, Ref, Meter, NoRedirect, canonical, digest,
    decode_record, recover_members, pack_delta, MAX_METADATA, MAX_CATALOG, DIMENSIONS)
from gorge_stage_preflight import require_stage_release, require_input_proof, install_prior_tiles
from run_gorge_checkpoint_slot import preflight, code_snapshot, token
from gorge_guarded_worker import run_job, checkpoint_job
from gorge_stage_inputs import bootstrap, unpack_seed, private_write, SHARED_NEW_CAP, PROOF_CAP
from inspect_gorge_stage_handoff import inspect_handoff
from fetch_gorge_private_seed import CONTEXT

SOURCE=Path(__file__).resolve().parent
CONFIG=SOURCE.parent/'config/gorge-stage-reconciled-20261029'
GROWTH_CAP=224*2**20
TILE_CAP=512*1024
TOTAL_OUTPUT_CAP=108*TILE_CAP
STATE_CAP=32*2**20


def configuration(directory=CONFIG):
    directory=Path(directory)
    plan=json.loads((directory/'PLAN.json').read_bytes())
    evidence=json.loads((directory/'ALLOWANCE.json').read_bytes())
    decoder=zlib.decompressobj();raw=decoder.decompress(base64.b64decode((directory/'REGION-PLAN.json.z.b64').read_bytes()),4*2**20)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('Region configuration bounds')
    region=json.loads(raw)
    require_stage_release(plan,evidence);preflight(plan,region,SOURCE)
    if plan.get('inputBinding')!='bootstrap-generation-pinned-proof-v1' or plan.get('inputProofSHA256') is not None:
        raise ValueError('Coordinator requires its exact bootstrap input binding')
    if plan.get('workerEnvelope')!={'cacheGrowthBytes':GROWTH_CAP,'outputBytesPerTile':TILE_CAP,'totalOutputBytes':TOTAL_OUTPUT_CAP,'stateBytes':STATE_CAP}:
        raise ValueError('Worker preservation envelope changed')
    if (plan['slots'][1]['storedBytes'] < GROWTH_CAP+TOTAL_OUTPUT_CAP+STATE_CAP+12*MAX_CATALOG+2**20
            or plan['slots'][2]['egressBytes'] < GROWTH_CAP+TOTAL_OUTPUT_CAP+STATE_CAP+SHARED_NEW_CAP+PROOF_CAP+12*2**20):
        raise ValueError('Outputs/cache/recovery envelope not prepaid')
    return plan,evidence,region


class CountedResponse:
    def __init__(self, response, entry):self.response=response;self.entry=entry
    def __getattr__(self,name):return getattr(self.response,name)
    def __enter__(self):self.response.__enter__();return self
    def __exit__(self,*args):return self.response.__exit__(*args)
    def read(self,*args):
        raw=self.response.read(*args);self.entry['responseBodyBytes']+=len(raw)
        if self.entry['method']!='GET' and self.entry['status'] in (200,201) and raw:
            try:
                obj=json.loads(raw)
                if (obj.get('bucket')=='rrgh-nonproduction-protected-packages'
                        and str(obj.get('name','')).startswith('engineering/map-production/')
                        and str(obj.get('generation','')).isdigit()):
                    self.entry['finalizedStoredBytes']=int(obj['size'])
            except (ValueError,TypeError,KeyError,AttributeError):pass
        return raw


class CountedOpener:
    def __init__(self):self.open=build_opener(NoRedirect()).open;self.entries=[];self.deadline=None
    def __call__(self,request,timeout=60):
        if self.deadline is not None:
            timeout=min(timeout,self.deadline-time.monotonic())
            if timeout<=0:raise ValueError('Stage network deadline reached')
        if urlsplit(request.full_url).hostname!='storage.googleapis.com':raise ValueError('Unexpected GCS host')
        method=request.get_method();q=parse_qs(urlsplit(request.full_url).query)
        e={'method':method,'mediaRead':method=='GET' and q.get('alt')==['media'],
           'requestBodyBytes':len(request.data or b''),'responseBodyBytes':0,'status':None}
        self.entries.append(e)
        try:r=self.open(request,timeout=timeout)
        except HTTPError as error:
            e['status']=error.code
            # Preserve HTTPError behavior, but its URL/body is never logged.
            raise
        e['status']=r.status
        return CountedResponse(r,e)
    def summary(self):
        return {'requests':len(self.entries),'classAHTTPRequests':sum(e['method']!='GET' for e in self.entries),
            'classBHTTPRequests':sum(e['method']=='GET' for e in self.entries),
            'requestBodyBytes':sum(e['requestBodyBytes'] for e in self.entries),
            'newFinalizedObjectBytes':sum(e.get('finalizedStoredBytes',0) for e in self.entries),
            'newFinalizedObjects':sum('finalizedStoredBytes' in e for e in self.entries),
            'responseBodyBytes':sum(e['responseBodyBytes'] for e in self.entries),
            'mediaReadBytes':sum(e['responseBodyBytes'] for e in self.entries if e['mediaRead']),
            'statuses':[e['status'] for e in self.entries]}


def signal(name):
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write(name+'=true\n')


def private_root():
    if any(os.environ.get(k)!=v for k,v in CONTEXT.items()):raise ValueError('Exact producer context required')
    root=Path(os.environ['RUNNER_TEMP']).resolve()/'rrgh-private'
    checkout=Path(os.environ['GITHUB_WORKSPACE']).resolve()
    if root==checkout or checkout in root.parents or root.is_symlink():raise ValueError('Private runner root required')
    root.mkdir(mode=0o700,exist_ok=True);root.chmod(0o700)
    if shutil.disk_usage(root).free<4*2**30:raise ValueError('Insufficient runner capacity')
    return root


def snapshot_cache(cog, service, destination, job, known, state_used):
    """Only new immutable cache members plus explicit closed-ledger snapshots."""
    dest=Path(destination);dest.mkdir(mode=0o700,exist_ok=False);entries=[];new_paths=[]
    for kind,root in [('cog',Path(cog)),('service',Path(service))]:
        paths=root.glob('blocks/*/*') if kind=='cog' else root.iterdir()
        for p in sorted(paths):
            if not p.is_file() or (kind=='service' and p.suffix not in ('.bin','.json')):continue
            name=kind+'/'+p.relative_to(root).as_posix()
            if name in known:continue
            if p.is_symlink():raise ValueError('Unsafe new cache member')
            raw=p.read_bytes()
            if not raw:continue
            entries.append({'path':name,'bytes':len(raw),'sha256':digest(raw)});new_paths.append(name)
            target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)
        database=root/('cache.sqlite' if kind=='cog' else 'requests.sqlite')
        target=dest/'state'/job/(kind+'.sqlite');target.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as src:
            if src.execute('PRAGMA integrity_check(10)').fetchall()!=[('ok',)]:raise ValueError('Cache ledger integrity failure')
            with sqlite3.connect(target) as dst:src.backup(dst)
        raw=target.read_bytes();state_used+=len(raw)
        if state_used>STATE_CAP:raise ValueError('Preservation state capacity reached')
        entries.append({'path':target.relative_to(dest).as_posix(),'bytes':len(raw),'sha256':digest(raw)})
    return entries,new_paths,state_used


def save_delta(slot,root,entries):
    refs=[]
    for raw,cat in pack_delta(root,entries):
        ref=slot.put(raw)
        catalog=slot.put_catalog({'format':'rrgh-cache-pack-catalog-v1','ref':asdict(ref),'members':cat['members']})
        refs.append(asdict(catalog))
    return refs


def run_stage(plan,evidence,region,root,store,opener):
    handoff=unpack_seed(root/'seed.zip',root/'handoff',plan)
    inspect_handoff(plan,evidence,handoff)
    private_write(root/'REGION-PLAN.json',canonical(region))
    slot=Slot(store,plan,0,os.environ['GITHUB_RUN_ID']);opener.deadline=slot.meter.deadline
    try:
        from gorge_reconciliation import transition
        transition(slot,plan,evidence,root, )
        initial,proof,roots=bootstrap(slot,plan,evidence,handoff,root)
    except Exception as error:
        if not slot.closed:
            import traceback
            refs=[]
            for p in (root/'sessions').glob('*.json') if (root/'sessions').exists() else []:
                j=json.loads(p.read_bytes())
                if j.get('uploadedRef'):refs.append({'ref':j['uploadedRef'],'accepted':j.get('accepted') is True})
            from gorge_stage_inputs import BaseValidationError
            diagnostic=({'code':error.code,'evidence':error.evidence}
                        if isinstance(error,BaseValidationError)
                        else {'code':'bootstrap-unclassified','errorClass':type(error).__name__,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]})
            final=slot.finish({'status':'failed','phase':'bootstrap','preservedIngress':refs,
                         'diagnostic':diagnostic,'gcs':opener.summary()})
            print(json.dumps({'bootstrapFailureReceipt':asdict(final),'gcsIncludingReceipt':opener.summary()},sort_keys=True),flush=True)
            print(json.dumps({'bootstrapDiagnostic':diagnostic},sort_keys=True),flush=True)
        raise
    signal('bootstrap_ready')
    output=root/'worker';service=root/'working-service'
    cog=root/'working-cog';known={'cog/'+p.relative_to(cog).as_posix() for p in cog.glob('blocks/*/*')}
    known|={'service/'+p.name for p in service.iterdir() if p.suffix in ('.bin','.json')}
    slot=Slot(store,plan,1,os.environ['GITHUB_RUN_ID']);opener.deadline=slot.meter.deadline
    completed=[];deltas=[];growth=0;state_bytes=0;attempts=0;source_bytes=0;source_requests=0;start=time.monotonic();failure=None
    try:
        for job in plan['approvedJobIDs']:
            policy=plan['jobPolicies'][job];attempts+=1;job_error=None;receipt=None
            try:
                receipt=run_job(slot,root/'REGION-PLAN.json',job,output,cog,service,policy,policy['seconds'],growth_cap=GROWTH_CAP-growth)
                if any(e['bytes']>TILE_CAP for e in receipt['outputs']) or sum(e['bytes'] for e in receipt['outputs'])>len(next(j for j in region['jobs'] if j['id']==job)['outputTiles'])*TILE_CAP:raise ValueError('Encoded output preservation cap exceeded')
            except Exception as error:
                job_error=error
                import traceback
                print(json.dumps({'workerDiagnostic':{'job':job,'errorClass':type(error).__name__,'frames':[{'file':Path(t.filename).name,'line':t.lineno,'function':t.name} for t in traceback.extract_tb(error.__traceback__)]}}),flush=True)
            usage_path=output/('gate-c-'+job+'.usage.json')
            if usage_path.exists():
                usage=json.loads(usage_path.read_bytes());growth+=usage['reserved']['storedBytes']
                source_bytes+=usage['actual']['receivedBodyBytes'];source_requests+=usage['actual']['operations']
                if usage.get('diagnostic'):print(json.dumps({'childDiagnostic':usage['diagnostic'],'job':job}),flush=True)
            else:
                growth=GROWTH_CAP  # Ambiguous child: no later source requests permitted.
            # Preservation precedes success receipt and the next job, including failures.
            destination=root/('delta-'+job)
            entries,new,state_bytes=snapshot_cache(cog,service,destination,job,known,state_bytes)
            new_payload=sum(e['bytes'] for e in entries if not e['path'].startswith('state/'))
            if new_payload>growth:raise ValueError('Cache growth escaped its prepaid source guard')
            delta_refs=save_delta(slot,destination,entries);deltas.extend(delta_refs);known.update(new)
            if job_error:raise RuntimeError('One bounded job failed; preserved cache and reservation retained') from None
            ref=checkpoint_job(slot,receipt,output);completed.append(asdict(ref))
            private_write(root/('checkpoint-'+job+'.json'),canonical({'jobReceipt':asdict(ref),'cacheCatalogs':delta_refs}))
            print(json.dumps({'completedJobs':len(completed),'sourceReceivedBytes':source_bytes,'sourceRequests':source_requests,'durableJobReceipt':asdict(ref)},sort_keys=True),flush=True)
    except Exception as error:failure=type(error).__name__
    result={'status':'complete' if failure is None else 'failed','failureClass':failure,
            'completedJobReceipts':completed,'cacheCatalogs':deltas,'proofRef':initial['proofRef'],
            'attempts':attempts,'sourceBytesReceived':source_bytes,'sourceRequests':source_requests,
            'cacheGrowthReservedBytes':growth,'stateSnapshotBytes':state_bytes,
            'wallSeconds':round(time.monotonic()-start,6),'gcs':opener.summary()}
    ref=slot.finish(result);signal('worker_receipt')
    private_write(root/'WORKER-RECEIPT-REF.json',canonical(asdict(ref)))
    print(json.dumps({'phase':'stage','status':result['status'],'jobsCompleted':len(completed),'attempts':attempts,
        'sourceBytesReceived':source_bytes,'sourceRequests':source_requests,'workerReceipt':asdict(ref),'gcs':opener.summary()},sort_keys=True))
    if failure:raise RuntimeError('Bounded stage stopped with durable reconciliation')


def verify_outputs(plan,region,records,root,prior_root=None):
    from PIL import Image
    import numpy as np
    jobs={j['id']:j for j in region['jobs']};seen=set();files=0;bytes_=0;seams=[];images={}
    recipe=digest((json.dumps(region,sort_keys=True,indent=2)+'\n').encode())
    for record in records:
        r=record['result']['originalReceipt'];job=r['job']
        if job in seen or job not in plan['approvedJobIDs'] or not r['validated'] or r['recipeSHA256']!=recipe:
            raise ValueError('Recovered production receipt mismatch')
        seen.add(job);wanted={tuple(v) for v in jobs[job]['outputTiles']};received=set()
        for e in r['outputs']:
            p=Path(root)/e['path'];raw=p.read_bytes()
            if len(raw)!=e['bytes'] or digest(raw)!=e['sha256']:raise ValueError('Recovered output hash mismatch')
            parts=e['path'].split('/');z,x,y=int(parts[2]),int(parts[3]),int(p.stem);received.add((z,x,y))
            with Image.open(p) as im:
                im.load()
                if im.size!=(256,256):raise ValueError('Recovered image grid mismatch')
                if im.mode=='RGBA' and im.getextrema()[3]!=(255,255):raise ValueError('Output has missing pixels')
                a=np.asarray(im.convert('RGB'))
                if max(float(v.std()) for v in a.transpose(2,0,1))<.1:raise ValueError('Blank production tile')
                images[(parts[1],z,x,y)]=a
            files+=1;bytes_+=len(raw)
        if received!=wanted:raise ValueError('Missing or unexpected produced tile')
    new_keys=set(images)
    if prior_root is not None:
        for p in sorted((Path(prior_root)/'prior/tiles').glob('*/*/*/*')):
            parts=p.relative_to(Path(prior_root)/'prior').parts
            key=(parts[1],int(parts[2]),int(parts[3]),int(p.stem))
            with Image.open(p) as im:
                im.load()
                if im.size!=(256,256):raise ValueError('Recovered prior grid mismatch')
                images[key]=np.asarray(im.convert('RGB'))
    # Measure new/new and new/preserved edges without reprocessing old tiles.
    for (layer,z,x,y),a in images.items():
        for direction,key in [('east',(layer,z,x+1,y)),('south',(layer,z,x,y+1))]:
            b=images.get(key)
            if b is None or ((layer,z,x,y) not in new_keys and key not in new_keys):continue
            edge=np.abs((a[:,-1] if direction=='east' else a[-1,:]).astype(float)-(b[:,0] if direction=='east' else b[0,:]).astype(float))
            seams.append({'layer':layer,'z':z,'x':x,'y':y,'direction':direction,
                'meanAbsoluteChannelDifference':round(float(edge.mean()),4),'p95':round(float(np.percentile(edge,95)),4)})
    return {'jobs':len(seen),'files':files,'bytes':bytes_,'allExpectedTilesPresent':True,
        'pixelsDecoded':True,'gridAndAlphaVerified':True,'adjacentEdgesMeasured':len(seams),'seams':seams}


def recover(plan,evidence,region,root,store,opener):
    slot=Slot(store,plan,2,os.environ['GITHUB_RUN_ID']);opener.deadline=slot.meter.deadline
    _,initial=slot.recover_receipt(0);_,worker=slot.recover_receipt(1)
    initial=initial['result'];worker=worker['result']
    if not initial.get('inputProofValidated') or worker['proofRef']!=initial['proofRef']:raise ValueError('Unbound input proof')
    proof=decode_record(slot.get(Ref(**initial['proofRef'])),PROOF_CAP)
    catalogs=[slot.get_catalog(Ref(**r)) for r in initial['seedCatalogs']+initial['sharedCatalogs']]
    # Verify selected old dependencies and complete shared content on this fresh runner.
    desired=[]
    for cat in catalogs:
        for e in cat['members']:
            if e['path'].startswith('prior/') or cat in catalogs[len(initial['seedCatalogs']):]:desired.append(e['path'])
    # Seed COG spot recovery checks actual ranges; full seed packs were SHA-readback verified at ingress.
    # Accepted original COG/Sunlight payloads are immutable and were fully
    # verified at ingress; only original neighboring tiles are needed for QA.
    recover_members(slot,catalogs,desired,root/'baseline-recovery')
    record_list=[];output_catalogs=[]
    for r in worker['completedJobReceipts']:
        record=decode_record(slot.get(Ref(**r)));record_list.append(record)
        output_catalogs.extend(record['result']['outputPacks'])
    output_paths=[e['path'] for c in output_catalogs for e in c['members']]
    if output_paths:recover_members(slot,output_catalogs,output_paths,root/'output-recovery')
    # Every new cache pack is read in full and every member SHA is checked.
    delta_catalogs=[slot.get_catalog(Ref(**r)) for r in worker['cacheCatalogs']]
    delta_paths=[e['path'] for c in delta_catalogs for e in c['members']]
    if delta_paths:recover_members(slot,delta_catalogs,delta_paths,root/'cache-recovery')
    qa=verify_outputs(plan,region,record_list,root/'output-recovery',root/'baseline-recovery') if output_paths else {'jobs':0,'files':0,'bytes':0}
    raw=canonical(qa);qa_ref=slot.put(raw,'indexes')
    result={'status':'verified' if worker['status']=='complete' and qa['jobs']==12 else 'partial-preservation-verified',
        'production':{k:v for k,v in qa.items() if k!='seams'},'qaRef':asdict(qa_ref),
        'allNewCachePacksRecovered':True,'newCacheFilesRecovered':len(delta_paths),
        'baselineFilesRecovered':len(desired),'gcs':opener.summary()}
    ref=slot.finish(result)
    print(json.dumps({'phase':'fresh-recovery','result':result,'receiptRef':asdict(ref),'gcsIncludingReceipt':opener.summary()},sort_keys=True))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['plan','stage','recovery'],default='plan');args=p.parse_args()
    try:
        plan,evidence,region=configuration()
        if args.phase=='plan':
            print(json.dumps({'planSHA256':digest(canonical(plan)),'jobs':len(plan['approvedJobIDs']),
                'maximumReservedUSD':evidence['cloudStorageAllowance']['reservedWorstCaseUSD'],'bulkProductionEnabled':False}));return
        root=private_root();opener=CountedOpener();store=GCS(plan,evidence,token,opener)
        if args.phase=='stage':run_stage(plan,evidence,region,root,store,opener)
        else:recover(plan,evidence,region,root,store,opener)
    except Exception as error:
        print(json.dumps({'phase':args.phase,'status':'failed-closed','errorClass':type(error).__name__,
            'reservationRetained':True,'automaticRetryPermitted':False}),flush=True)
        raise SystemExit(2) from None

if __name__=='__main__':main()
