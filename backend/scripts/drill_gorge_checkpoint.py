#!/usr/bin/env python3
"""One explicitly authorized $0.05 private recovery drill, never production.

Only a retained synthetic checkpoint and a 64 KiB deterministic test member are
used. No protected package, source cache, raster worker, IAM or bucket mutation.
"""
import argparse
from dataclasses import asdict
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import build_opener

from gorge_checkpoint import (BUCKET, PREFIX, MAX_METADATA, GCS, NoRedirect, Slot,
    canonical, digest, pack_delta, recover_members, require_live_allowance)

AUTHORIZATION = 'owner-authorized-single-recovery-drill-20261029'
OLD_KEY = PREFIX+'ci-checkpoints/40c9ff16cfde2daf84b1428a1b31936db412efae/checkpoint.txt'
OLD_SHA = 'e7e1023f022dab7019dfdb803b23aa4a1ac42fa3614a21da2295a6cc16b42df5'
RATES = {'storageUSDPerGiBMonth':'.03','egressUSDPerGiB':'.23',
         'classAUSDPer1000':'.01','classBUSDPer1000':'.001'}


def configuration():
    caps=dict(storedBytes=4*2**20,egressBytes=4*2**20,classARequests=10,
              classBRequests=20,sourceBytes=0,sourceRequests=0,seconds=240,attempts=0)
    here=Path(__file__).parent
    code={n:digest((here/n).read_bytes()) for n in ('gorge_checkpoint.py','drill_gorge_checkpoint.py')}
    plan={'format':'rrgh-checkpoint-plan-v1','purpose':'one-off-recovery-drill','authorization':AUTHORIZATION,
          'bucket':BUCKET,'deleteAllowed':False,'bulkProductionEnabled':False,
          'expiresAt':'2026-10-30T03:59:00+00:00','sourceSnapshotSHA256':digest(canonical(code)),
          'slots':[caps.copy(),caps.copy()],'limits':{k:v*2 for k,v in caps.items()}}
    evidence={'cloudStorageAllowance':{'scope':'one-off-recovery-drill','approvedUSD':'.05',
        'approvalReference':AUTHORIZATION,'planSHA256':digest(canonical(plan)),
        'reservedWorstCaseUSD':'.02','chargedRetentionMonths':60},
        'planningRates':RATES,'github':{'hardCeilingUSD':350,'stopAtLimitVerified':True}}
    require_live_allowance(plan,evidence)
    return plan,evidence


class ObservedResponse:
    def __init__(self,r,entry):self.r=r;self.entry=entry
    def __enter__(self):self.r.__enter__();return self
    def __exit__(self,*args):return self.r.__exit__(*args)
    def __getattr__(self,name):return getattr(self.r,name)
    def read(self,size=-1):
        raw=self.r.read(size);self.entry['responseBodyBytes']+=len(raw);return raw


class ObservedHTTP:
    """Counts actual attempted GCS operations and body bytes; never logs secrets."""
    def __init__(self,open_fn=None):
        self.open_fn=open_fn or build_opener(NoRedirect()).open
        self.entries=[]
    def __call__(self,req,timeout):
        q=parse_qs(urlparse(req.full_url).query)
        entry={'method':req.method,'class':'A' if req.method=='POST' else 'B',
               'kind':'upload' if req.method=='POST' else 'media' if q.get('alt')==['media'] else 'metadata',
               'requestBodyBytes':len(req.data or b''),'responseBodyBytes':0,
               'generationPinned':q.get('generation')==q.get('ifGenerationMatch') and 'generation' in q,
               'rangeRequest':bool(req.get_header('Range')),'status':None}
        self.entries.append(entry);start=time.monotonic()
        try:
            r=self.open_fn(req,timeout=timeout);entry['status']=r.status
            return ObservedResponse(r,entry)
        except HTTPError as e:entry['status']=e.code;raise
        finally:entry['headerLatencySeconds']=round(time.monotonic()-start,6)
    def summary(self):
        return {'operations':len(self.entries),'classA':sum(x['class']=='A' for x in self.entries),
                'classB':sum(x['class']=='B' for x in self.entries),
                'uploadedObjectBytes':sum(x['requestBodyBytes'] for x in self.entries),
                'downloadedObjectBytes':sum(x['responseBodyBytes'] for x in self.entries if x['kind']=='media'),
                'responseBodyBytesIncludingMetadata':sum(x['responseBodyBytes'] for x in self.entries),
                'rangeReads':sum(x['rangeRequest'] for x in self.entries),
                'generationPinnedReads':sum(x['generationPinned'] for x in self.entries),
                'statuses':[x['status'] for x in self.entries]}


def token():
    p=subprocess.run(['gcloud','auth','print-access-token','--quiet'],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30,check=False)
    value=p.stdout.strip()
    if p.returncode or not value or any(c.isspace() for c in value):raise RuntimeError('WIF credential unavailable')
    return value


def check_context():
    expected={'GITHUB_REPOSITORY_ID':'1325611891','GITHUB_REPOSITORY_OWNER_ID':'313924954',
      'GITHUB_REF':'refs/heads/lane20/offline-production-preflight-20261029','GITHUB_EVENT_NAME':'push',
      'GITHUB_RUN_ATTEMPT':'1',
      'GITHUB_WORKFLOW_REF':'ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029'}
    if any(os.environ.get(k)!=v for k,v in expected.items()):raise ValueError('Wrong authorized workflow context')
    if not os.environ.get('GITHUB_RUN_ID','').isdigit():raise ValueError('Run identity required')


def stage(plan,store,observed):
    slot=Slot(store,plan,0,os.environ['GITHUB_RUN_ID']+':stage')
    # Small pre-existing engineering fixture only. Reserve metadata before GET,
    # and reserve exact body length before its generation-pinned media GET.
    slot.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
    def reserve_old(size):
        if size>512:raise ValueError('Unexpected old checkpoint size')
        slot.meter.reserve(classBRequests=1,egressBytes=size+1)
    old_ref,old=store.receipt(OLD_KEY,reserve_old)
    if digest(old)!=OLD_SHA:raise ValueError('Retained fixture hash mismatch')
    padding=bytes(range(256))*256
    with tempfile.TemporaryDirectory(prefix='rrgh-drill-') as td:
        root=Path(td);(root/'retained-checkpoint.bin').write_bytes(old);(root/'range-probe.bin').write_bytes(padding)
        entries=[{'path':n,'bytes':len(raw),'sha256':digest(raw)} for n,raw in
                 [('retained-checkpoint.bin',old),('range-probe.bin',padding)]]
        packs=list(pack_delta(root,entries));assert len(packs)==1
        raw,info=packs[0];ref=slot.put(raw)
        if slot.get(ref)!=raw:raise ValueError('Immediate exact-generation read mismatch')
        manifest=[{'ref':asdict(ref),'members':info['members']}]
    receipt=slot.finish({'packManifest':manifest,'retainedFixture':asdict(old_ref),
                        'fixtureType':'retained synthetic checkpoint plus 64KiB synthetic range probe',
                        'transportBeforeFinalReceipt':observed.summary(),'requestTraceBeforeFinalReceipt':observed.entries})
    return {'integrity':'PASS','planSHA256':digest(canonical(plan)),
            'packSHA256':ref.sha256,'packBytes':ref.bytes,
            'generations':{'oldFixture':old_ref.generation,'stageClaim':slot.claim.generation,
                           'pack':ref.generation,'stageReceipt':receipt.generation},
            'reserved':slot.meter.used,'transport':observed.summary()}


def recovery(plan,store,observed):
    slot=Slot(store,plan,1,os.environ['GITHUB_RUN_ID']+':fresh-recovery')
    stage_ref,saved=slot.recover_receipt(0)
    manifests=saved['result']['packManifest']
    if len(manifests)!=1:raise ValueError('Expected one bounded pack')
    with tempfile.TemporaryDirectory(prefix='rrgh-independent-') as td:
        target=Path(td)/'selected'
        recovered=recover_members(slot,manifests,{'retained-checkpoint.bin'},target)
        if digest((target/'retained-checkpoint.bin').read_bytes())!=OLD_SHA:raise ValueError('Independent fixture mismatch')
        if (target/'range-probe.bin').exists():raise ValueError('Unselected payload fetched')
        from gorge_checkpoint import Ref
        ref=Ref(**manifests[0]['ref']);probe=next(x for x in manifests[0]['members'] if x['path']=='range-probe.bin')
        # Independently prove a second byte range, without downloading its whole member.
        sample=bytes(range(256))*4
        slot.get(ref,probe['offset']+1024,1024,digest(sample))
    result={'integrity':'PASS','selectiveRecovery':recovered,'extraProbeBytes':1024,
            'stageReceipt':asdict(stage_ref),'packGeneration':ref.generation,
            'fullPackRestored':False,'sourceTransfers':0,'rasterJobs':0,
            'transportBeforeFinalReceipt':observed.summary(),'requestTraceBeforeFinalReceipt':observed.entries}
    final=slot.finish(result)
    return {'integrity':'PASS','planSHA256':digest(canonical(plan)),
            'selectiveRecovery':recovered,'extraProbeBytes':1024,'fullPackRestored':False,
            'generations':{'recoveryClaim':slot.claim.generation,'stageReceipt':stage_ref.generation,
                           'pack':ref.generation,'recoveryReceipt':final.generation},
            'reserved':slot.meter.used,'transport':observed.summary()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['plan','stage','recovery'],default='plan')
    args=p.parse_args();plan,evidence=configuration()
    if args.phase=='plan':
        print(json.dumps({'plan':plan,'funding':evidence,'liveOperations':0},sort_keys=True));return
    check_context();observed=ObservedHTTP();store=GCS(plan,evidence,token,opener=observed)
    try:
        result=(stage if args.phase=='stage' else recovery)(plan,store,observed)
        result.update(phase=args.phase,approvedUSD=.05,reservedWorstCaseUSD=.02,prepaidStorageMonths=60,
                      automaticRetries=0,bulkProductionEnabled=False)
        print('RRGH_DRILL_RESULT='+json.dumps(result,sort_keys=True))
    except Exception as e:
        # Preserve aggregate evidence even on failure; never dump credential/body/URL.
        print('RRGH_DRILL_FAILURE='+json.dumps({'phase':args.phase,'errorType':type(e).__name__,
              'transport':observed.summary(),'automaticRetry':False},sort_keys=True))
        raise SystemExit(1)


if __name__=='__main__':main()
