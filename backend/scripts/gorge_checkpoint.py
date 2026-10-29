#!/usr/bin/env python3
"""Bounded immutable checkpoints; no default network activity or credential lookup.

Finite, prepaid slots make crash reservations survive loss of the entire runner.
A slot is never resumed or refunded: recovery must use another allocated slot.
The plan and private receipt references are retained by the external coordinator.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import threading
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

BUCKET = 'rrgh-nonproduction-protected-packages'
PREFIX = 'engineering/map-production/'
MAX_PACK = 64 * 2**20
MAX_RECEIPT = 2**20
MAX_METADATA = 16384
DIMENSIONS = ('storedBytes', 'egressBytes', 'classARequests', 'classBRequests',
              'sourceBytes', 'sourceRequests', 'seconds', 'attempts')
SHA = re.compile(r'[0-9a-f]{64}\Z')


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(n):
    if type(n) is not int or n < 0:
        raise ValueError('Nonnegative integer required')
    return n


def safe_key(key):
    p = PurePosixPath(key)
    if not isinstance(key, str) or not key.startswith(PREFIX) or str(p) != key or any(x in ('..', '.') for x in p.parts) or '\\' in key or len(key)>900:
        raise ValueError('Outside dedicated private checkpoint prefix')
    return key


def relative_path(path):
    p = PurePosixPath(path)
    if not path or p.is_absolute() or str(p)!=path or '..' in p.parts or '\\' in path:
        raise ValueError('Unsafe member path')
    return path


@dataclass(frozen=True)
class Ref:
    key: str
    generation: str
    bytes: int
    sha256: str

    def __post_init__(self):
        safe_key(self.key)
        integer(self.bytes)
        if not re.fullmatch(r'[1-9][0-9]*', self.generation) or not SHA.fullmatch(self.sha256):
            raise ValueError('Numeric generation and SHA256 required')


class Meter:
    """Local submeter under a durable, nonrefundable slot reservation."""
    def __init__(self, caps):
        if set(caps)!=set(DIMENSIONS):
            raise ValueError('Every dimension must be explicitly bounded')
        self.caps = {k: integer(v) for k,v in caps.items()}
        self.used = dict.fromkeys(DIMENSIONS, 0)
        self.lock = threading.Lock()
        self.deadline = time.monotonic() + caps['seconds']

    def reserve(self, **amounts):
        with self.lock:
            if time.monotonic() > self.deadline:
                raise ValueError('Slot wall-clock limit reached')
            for k,v in amounts.items():
                integer(v)
                if k not in self.caps or self.used[k]+v > self.caps[k]:
                    raise ValueError('Slot limit reached: '+k)
            for k,v in amounts.items():
                self.used[k] += v  # Never refund failures, short reads or retries.


def validate_plan(plan, now=None):
    if plan.get('format')!='rrgh-checkpoint-plan-v1' or plan.get('bucket')!=BUCKET:
        raise ValueError('Unknown plan or bucket')
    if plan.get('deleteAllowed') is not False or plan.get('bulkProductionEnabled') is not False:
        raise ValueError('This readiness implementation does not enable bulk production')
    now = now or datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(plan['expiresAt'].replace('Z','+00:00'))
    if expiry.tzinfo is None or expiry <= now:
        raise ValueError('Plan expired')
    if not SHA.fullmatch(plan['sourceSnapshotSHA256']):
        raise ValueError('Source snapshot required')
    slots = plan['slots']
    if not isinstance(slots,list) or not 1<=len(slots)<=10000:
        raise ValueError('Explicit finite slot allocation required')
    totals = dict.fromkeys(DIMENSIONS,0)
    for slot in slots:
        meter = Meter(slot)
        if slot['classARequests']<2 or slot['storedBytes']<2*MAX_RECEIPT or slot['egressBytes']<2*(MAX_METADATA+1) or slot['seconds']<1:
            raise ValueError('Slot must reserve claim and final receipt overhead')
        for k in totals: totals[k] += meter.caps[k]
    if set(plan['limits'])!=set(DIMENSIONS):
        raise ValueError('All cumulative limits required')
    for k,v in totals.items():
        if v>integer(plan['limits'][k]):
            raise ValueError('Slot allocations exceed cumulative '+k)
    assignments=plan.get('slotJobs',{})
    completed=set(plan.get('completedJobIDs',[])); counts={}
    for index,jobs in assignments.items():
        if not index.isdigit() or str(int(index))!=index or int(index)>=len(slots) or len(jobs)!=len(set(jobs)):
            raise ValueError('Invalid slot job assignments')
        if len(jobs)>slots[int(index)]['attempts']:raise ValueError('Job attempts exceed slot')
        for job in jobs:
            if job in completed:raise ValueError('Completed work scheduled again')
            counts[job]=counts.get(job,0)+1
            if counts[job]>2:raise ValueError('Two-attempt global ceiling exceeded')
    return totals


def require_live_allowance(plan, evidence, now=None):
    """Trial credit is deliberately never read as a spending allowance."""
    validate_plan(plan, now)
    a = evidence.get('cloudStorageAllowance',{})
    amount = a.get('approvedUSD')
    if amount is None or not a.get('approvalReference') or a.get('planSHA256')!=digest(canonical(plan)):
        raise ValueError('No explicit plan-bound Cloud Storage allowance')
    approved = Decimal(str(amount)); reserve = Decimal(str(a.get('reservedWorstCaseUSD')))
    if not approved.is_finite() or not reserve.is_finite() or not 0<reserve<=approved:
        raise ValueError('Invalid funded reservation')
    if a.get('ongoingStorageAcknowledged') is not True:
        raise ValueError('No lifecycle: ongoing storage obligation must be acknowledged')
    rates=evidence.get('planningRates',{})
    r={k:Decimal(str(rates.get(k))) for k in ('storageUSDPerGiBMonth','egressUSDPerGiB','classAUSDPer1000','classBUSDPer1000')}
    floors={'storageUSDPerGiBMonth':'.02','egressUSDPerGiB':'.12','classAUSDPer1000':'.005','classBUSDPer1000':'.0004'}
    if any(not v.is_finite() or v<Decimal(floors[k]) for k,v in r.items()):
        raise ValueError('Invalid planning rates; no trial-credit deductions')
    months=Decimal(str(a.get('chargedRetentionMonths')))
    if not months.is_finite() or months<1:raise ValueError('At least one month funded retention required')
    c=plan['limits']; gib=Decimal(2**30)
    monthly=c['storedBytes']/gib*r['storageUSDPerGiBMonth']
    worst=(monthly*months+c['egressBytes']/gib*r['egressUSDPerGiB']+
           Decimal(c['classARequests'])/1000*r['classAUSDPer1000']+
           Decimal(c['classBRequests'])/1000*r['classBUSDPer1000'])*Decimal('1.2')
    if reserve<worst or Decimal(str(a.get('approvedRecurringStorageUSDPerMonth',0)))<monthly*Decimal('1.2'):
        raise ValueError('Reservation omits capped usage or continuing storage')
    if evidence.get('github',{}).get('hardCeilingUSD')!=350 or evidence['github'].get('stopAtLimitVerified') is not True:
        raise ValueError('Actions stop required')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GCS:
    """JSON API transport: exact bucket/prefix, no listing/deletion/overwrite/retry.

    Construct only after allowance validation. token_provider is short-lived WIF;
    it must not return a key, write credentials, or log its value.
    """
    def __init__(self, plan, evidence, token_provider, opener=None):
        require_live_allowance(plan,evidence)
        self.expiry=datetime.fromisoformat(plan['expiresAt'].replace('Z','+00:00'))
        self.plan_prefix=PREFIX+'plans/'+digest(canonical(plan))+'/'
        self.token_provider=token_provider
        self.opener=opener or build_opener(NoRedirect()).open

    def _request(self, method, key, query, maximum, data=None, headers=None):
        safe_key(key)
        if datetime.now(timezone.utc)>=self.expiry:raise ValueError('Funded plan expired')
        endpoint = '/upload/storage/v1/b/' if method=='POST' else '/storage/v1/b/'
        path = endpoint+BUCKET+'/o'+('' if method=='POST' else '/'+quote(key,safe=''))
        url = 'https://storage.googleapis.com'+path+'?'+urlencode(query)
        h={'Authorization':'Bearer '+self.token_provider(), 'Accept-Encoding':'identity'}
        if data is not None: h['Content-Type']='application/octet-stream'
        h.update(headers or {})
        try:
            with self.opener(Request(url,data=data,headers=h,method=method),timeout=60) as r:
                if r.geturl()!=url or r.status not in (200,206):
                    raise ValueError('GCS status/redirect rejected')
                raw=r.read(maximum+1)
                if len(raw)>maximum: raise ValueError('GCS response exceeds bound')
                return raw, dict(r.headers), r.status
        except HTTPError as exc:
            # Do not leak URL, private payload, bearer credential or error body.
            raise RuntimeError('GCS HTTP '+str(exc.code)) from None

    def create(self, key, raw):
        if not key.startswith(self.plan_prefix):raise ValueError('Write outside funded plan')
        raw_result,_,_=self._request('POST',key,{'uploadType':'media','name':key,
                                              'ifGenerationMatch':'0'},MAX_METADATA,data=raw)
        obj=json.loads(raw_result)
        if obj.get('bucket')!=BUCKET or obj.get('name')!=key or int(obj['size'])!=len(raw):
            raise ValueError('GCS creation metadata mismatch')
        md5=base64.b64encode(hashlib.md5(raw,usedforsecurity=False).digest()).decode()
        if obj.get('md5Hash')!=md5:raise ValueError('GCS uploaded content checksum mismatch')
        return Ref(key,str(obj['generation']),len(raw),digest(raw))

    def read(self, ref, start=0, length=None):
        length=ref.bytes if length is None else length
        if length<=0 or not 0<=start<ref.bytes or start+length>ref.bytes:
            raise ValueError('Invalid range')
        full=start==0 and length==ref.bytes
        headers={} if full else {'Range':f'bytes={start}-{start+length-1}'}
        raw,h,status=self._request('GET',ref.key,{'alt':'media','generation':ref.generation,
                                                'ifGenerationMatch':ref.generation},length,headers=headers)
        low={k.lower():v for k,v in h.items()}
        if low.get('x-goog-generation')!=ref.generation or len(raw)!=length:
            raise ValueError('Wrong generation or response length')
        if not full and (status!=206 or low.get('content-range')!=f'bytes {start}-{start+length-1}/{ref.bytes}'):
            raise ValueError('Invalid GCS range response')
        if full and (status!=200 or digest(raw)!=ref.sha256):
            raise ValueError('Full-object hash/status mismatch')
        return raw


    def receipt(self, key, before_media):
        raw,_,_=self._request('GET',key,{},MAX_METADATA)
        meta=json.loads(raw);size=int(meta['size']);generation=str(meta['generation'])
        if meta.get('bucket')!=BUCKET or meta.get('name')!=key or not 0<size<=MAX_RECEIPT:
            raise ValueError('Receipt metadata mismatch')
        before_media(size)
        raw,h,status=self._request('GET',key,{'alt':'media','generation':generation,
                                             'ifGenerationMatch':generation},size)
        low={k.lower():v for k,v in h.items()}
        md5=base64.b64encode(hashlib.md5(raw,usedforsecurity=False).digest()).decode()
        if status!=200 or low.get('x-goog-generation')!=generation or len(raw)!=size or md5!=meta.get('md5Hash'):
            raise ValueError('Receipt generation/content integrity mismatch')
        return Ref(key,generation,size,digest(raw)),raw


class Slot:
    """Durable maximum reservation BEFORE any source work or checkpoint read.

    Each numbered slot may be claimed exactly once. Collisions and ambiguous
    transport failures stop; a new process cannot reuse an existing claim.
    Unused allowance stays allocated, including when a worker dies.
    """
    def __init__(self, store, plan, index, owner):
        validate_plan(plan)
        if type(index)is not int or not 0<=index<len(plan['slots']) or not owner:
            raise ValueError('Invalid slot')
        self.store=store; self.plan=plan; self.index=index
        self.meter=Meter(plan['slots'][index]); self.closed=False
        expiry=datetime.fromisoformat(plan['expiresAt'].replace('Z','+00:00'))
        self.meter.deadline=min(self.meter.deadline,time.monotonic()+(expiry-datetime.now(timezone.utc)).total_seconds())
        self.prefix=PREFIX+'plans/'+digest(canonical(plan))+'/'
        claim=canonical({'format':'rrgh-slot-claim-v1','planSHA256':digest(canonical(plan)),
                         'slot':index,'owner':owner,'allocation':plan['slots'][index]})
        if len(claim)>MAX_RECEIPT: raise ValueError('Oversized claim')
        self.meter.reserve(classARequests=1,storedBytes=MAX_RECEIPT,egressBytes=MAX_METADATA+1)
        self.claim=store.create(self.prefix+f'slots/{index:05d}/claim.json',claim)
        # Conservatively keep MAX_RECEIPT reserved for both claim and receipt.
        self.meter.reserve(classARequests=1,storedBytes=MAX_RECEIPT,egressBytes=MAX_METADATA+1)

    def put(self, raw, kind='packs'):
        if self.closed or kind not in ('packs','outputs','indexes') or not 0<len(raw)<=MAX_PACK:
            raise ValueError('Invalid checkpoint write')
        self.meter.reserve(classARequests=1,storedBytes=len(raw),egressBytes=MAX_METADATA+1)
        key=self.prefix+f'slots/{self.index:05d}/{kind}/'+digest(raw)
        return self.store.create(key,raw)

    def get(self, ref, start=0, length=None, expected_sha256=None):
        if self.closed: raise ValueError('Slot is closed')
        length=ref.bytes if length is None else integer(length)
        if length>MAX_PACK: raise ValueError('Unbounded checkpoint recovery')
        self.meter.reserve(classBRequests=1,egressBytes=length+1)
        raw=self.store.read(ref,start,length)
        if expected_sha256 and digest(raw)!=expected_sha256:
            raise ValueError('Selected member hash mismatch')
        return raw

    def commit_job(self, job_id, result):
        if self.closed or not re.fullmatch(r'[a-z0-9-]+',job_id):raise ValueError('Invalid job receipt')
        if job_id not in self.plan.get('slotJobs',{}).get(str(self.index),[]):raise ValueError('Unallocated job')
        raw=canonical({'format':'rrgh-checkpoint-job-v1','job':job_id,'slot':self.index,
                       'planSHA256':digest(canonical(self.plan)),'result':result})
        if len(raw)>MAX_RECEIPT:raise ValueError('Job receipt too large')
        self.meter.reserve(classARequests=1,storedBytes=len(raw),egressBytes=MAX_METADATA+1)
        return self.store.create(self.prefix+f'slots/{self.index:05d}/jobs/{job_id}.json',raw)

    def recover_job(self, prior_index, job_id):
        if self.closed or type(prior_index)is not int or not 0<=prior_index<self.index:
            raise ValueError('Prior slot required')
        if job_id not in self.plan.get('slotJobs',{}).get(str(prior_index),[]):raise ValueError('Unallocated prior job')
        self.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
        ref,raw=self.store.receipt(self.prefix+f'slots/{prior_index:05d}/jobs/{job_id}.json',
            lambda size:self.meter.reserve(classBRequests=1,egressBytes=size+1))
        obj=json.loads(raw)
        if obj.get('format')!='rrgh-checkpoint-job-v1' or obj.get('job')!=job_id or obj.get('slot')!=prior_index or obj.get('planSHA256')!=digest(canonical(self.plan)):
            raise ValueError('Recovered job receipt identity mismatch')
        return ref,obj

    def recover_receipt(self, prior_index):
        if self.closed or type(prior_index)is not int or not 0<=prior_index<self.index:
            raise ValueError('Prior slot index required')
        self.meter.reserve(classBRequests=1,egressBytes=MAX_METADATA+1)
        ref,raw=self.store.receipt(self.prefix+f'slots/{prior_index:05d}/receipt.json',
            lambda size:self.meter.reserve(classBRequests=1,egressBytes=size+1))
        obj=json.loads(raw)
        if obj.get('format')!='rrgh-slot-receipt-v1' or obj.get('slot')!=prior_index or obj.get('planSHA256')!=digest(canonical(self.plan)):
            raise ValueError('Recovered receipt identity mismatch')
        claim=Ref(**obj['claim'])
        if claim.key!=self.prefix+f'slots/{prior_index:05d}/claim.json':
            raise ValueError('Recovered claim reference mismatch')
        return ref,obj

    def finish(self, result):
        if self.closed: raise ValueError('Slot is closed')
        raw=canonical({'format':'rrgh-slot-receipt-v1','claim':asdict(self.claim),
                       'planSHA256':digest(canonical(self.plan)),'slot':self.index,
                       'nonrefundableAllocation':self.plan['slots'][self.index],
                       'used':self.meter.used,'result':result})
        if len(raw)>MAX_RECEIPT: raise ValueError('Receipt bound exceeded')
        self.closed=True  # Any failure is ambiguous; never repeat this write.
        return self.store.create(self.prefix+f'slots/{self.index:05d}/receipt.json',raw)


def pack_delta(root, entries, known_hashes=(), maximum=MAX_PACK):
    """Raw concatenated packs allow exact-generation range recovery per member.

    The private manifest stores offsets and SHA256. Known hashes are explicit
    previously verified receipts; no remote existence probes or full scans.
    """
    if not 1<=maximum<=MAX_PACK: raise ValueError('Invalid pack size')
    root=Path(root).resolve(); known=set(known_hashes); seen=set()
    data=bytearray(); members=[]
    for entry in entries:
        path=relative_path(entry['path'])
        if path in seen: raise ValueError('Duplicate member path')
        seen.add(path); p=root/path
        if not SHA.fullmatch(entry['sha256']) or not 0<integer(entry['bytes'])<=maximum:
            raise ValueError('Invalid member identity/size')
        if p.is_symlink() or root not in p.resolve().parents or not p.is_file():
            raise ValueError('Unsafe or absent member')
        if p.stat().st_size!=entry['bytes']:raise ValueError('Member size changed')
        raw=p.read_bytes()
        if len(raw)!=entry['bytes'] or digest(raw)!=entry['sha256']:
            raise ValueError('Source delta corruption; never redownload silently')
        if entry['sha256'] in known: continue
        if len(data)+len(raw)>maximum:
            body=bytes(data)
            yield body,{'sha256':digest(body),'bytes':len(body),'members':members}
            data=bytearray();members=[]
        members.append({**entry,'offset':len(data)});data.extend(raw)
    if data:
        body=bytes(data)
        yield body,{'sha256':digest(body),'bytes':len(body),'members':members}



def recover_members(slot, manifest, requested_paths, destination):
    """Fetch only selected members, verify hash BEFORE atomic installation."""
    root=Path(destination).resolve()
    if root.exists(): raise ValueError('Recovery requires a new destination')
    requested=set(requested_paths); catalog={}
    for pack in manifest:
        ref=Ref(**pack['ref'])
        for e in pack['members']:
            path=relative_path(e['path']); integer(e['offset']);integer(e['bytes'])
            if path in catalog or not SHA.fullmatch(e['sha256']) or e['bytes']<=0 or e['offset']+e['bytes']>ref.bytes:
                raise ValueError('Invalid recovery catalog')
            catalog[path]=(ref,e)
    if not requested<=catalog.keys(): raise ValueError('Missing requested recovery members')
    total=sum(catalog[p][1]['bytes'] for p in requested)
    if total>slot.meter.caps['egressBytes']-slot.meter.used['egressBytes']:
        raise ValueError('Selective recovery exceeds remaining egress')
    # Stage all requested bytes before publishing destination; no partial success.
    temp=root.with_name(root.name+'.partial')
    temp.mkdir(parents=True,exist_ok=False)
    for path in sorted(requested):
        ref,e=catalog[path];raw=slot.get(ref,e['offset'],e['bytes'],e['sha256'])
        p=temp/path;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    temp.rename(root)
    return {'files':len(requested),'recoveredBytes':total}
