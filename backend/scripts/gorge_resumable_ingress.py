#!/usr/bin/env python3
"""Native GCS ingress under an already claimed, funded checkpoint Slot.

No credential discovery, CLI execution, workflow trigger or session handoff.
Caller supplies the existing GCS/WIF transport and a private local journal.
Process loss consumes the original slot; this API never resets its allowance.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request

from gorge_checkpoint import BUCKET, MAX_METADATA, Ref, canonical, digest

CHUNK = 16 * 2**20
MAX_INPUT = 2**30


class IngressError(RuntimeError):
    """Messages deliberately exclude request URLs, credentials and bodies."""


def reservation(size, chunk=CHUNK, recoveries=2):
    if (type(size) is not int or not 0 < size <= MAX_INPUT
            or type(chunk) is not int or not 256*1024 <= chunk <= 64*2**20
            or chunk % (256*1024) or type(recoveries) is not int
            or not 0 <= recoveries <= 2):
        raise ValueError('Invalid bounded ingress dimensions')
    # Treat EVERY HTTP write/status request as Class A, conservatively, even
    # though Google bills a completed resumable upload as one Class A operation.
    count = 1 + math.ceil(size/chunk) + 2*recoveries
    return {'storedBytes': size, 'classARequests': count, 'classBRequests': 1,
            'egressBytes': count*(MAX_METADATA+1)+size+1}


def validate_session(uri, key):
    p = urlsplit(uri)
    q = parse_qs(p.query, keep_blank_values=True)
    if (p.scheme != 'https' or p.netloc != 'storage.googleapis.com'
            or p.path != '/upload/storage/v1/b/'+BUCKET+'/o'
            or p.fragment or q.get('name') != [key]
            or q.get('uploadType') != ['resumable']
            or len(q.get('upload_id', [])) != 1 or not q['upload_id'][0]
            or any(len(v) != 1 for v in q.values())
            or ('ifGenerationMatch' in q and q['ifGenerationMatch'] != ['0'])):
        raise IngressError('Unexpected resumable endpoint or object')
    return uri


class _Journal:
    def __init__(self, path, state):
        self.path = Path(path)
        parent = self.path.parent
        if (parent.is_symlink() or not parent.is_dir()
                or stat.S_IMODE(parent.stat().st_mode) & 0o077):
            raise ValueError('Journal parent must be an existing private directory')
        self.state = state
        with os.fdopen(os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as f:
            f.write(canonical(state)); f.flush(); os.fsync(f.fileno())

    def save(self, **updates):
        self.state.update(updates)
        tmp = self.path.with_name(self.path.name+'.next')
        with os.fdopen(os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as f:
            f.write(canonical(self.state)); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)


def put_file(slot, path, expected_bytes, expected_sha256, journal_path,
             chunk=CHUNK, recoveries=2):
    """Upload + pinned full SHA256 readback, or fail without accepting a seed.

    Reserve the complete upload/status/readback envelope before the first POST.
    HTTP timeouts/5xx may use at most two prepaid status queries. Never restart
    a session, overwrite, delete, list, or accept an unverified remote object.
    A retained session journal is a credential: never publish it as evidence.
    A new worker needs a separately allocated recovery slot and coordinator
    reconciliation; reusing this journal/claim is intentionally unsupported.
    """
    caps = reservation(expected_bytes, chunk, recoveries)
    if slot.closed or slot.claim.key != slot.prefix+f'slots/{slot.index:05d}/claim.json':
        raise ValueError('An open, durably claimed slot is required')
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected_bytes:
        raise ValueError('Ingress source size/path mismatch')
    sha = hashlib.sha256(); md5 = hashlib.md5(usedforsecurity=False)
    with path.open('rb') as f:
        while data := f.read(CHUNK): sha.update(data); md5.update(data)
    if sha.hexdigest() != expected_sha256:
        raise ValueError('Ingress source SHA256 mismatch')
    key = slot.prefix+f'slots/{slot.index:05d}/packs/'+expected_sha256
    store = slot.store
    if key[:len(store.plan_prefix)] != store.plan_prefix:
        raise ValueError('Transport/slot plan mismatch')
    journal = _Journal(journal_path, {'format':'rrgh-private-ingress-session-v1',
        'planSHA256':digest(canonical(slot.plan)), 'claim':slot.claim.__dict__,
        'key':key, 'bytes':expected_bytes, 'sha256':expected_sha256,
        'accepted':False, 'sessionURI':None, 'confirmedOffset':0})
    slot.meter.reserve(**caps)
    journal.save(nonrefundableReservation=caps)
    used = {'writeRequests':0, 'readRequests':0, 'uploadBodyBytesAttempted':0,
            'responseBodyBytes':0, 'readbackBytes':0, 'statusQueries':0}

    def timeout():
        seconds = min(slot.meter.deadline-time.monotonic(),
                      (store.expiry-datetime.now(timezone.utc)).total_seconds(), 60)
        if seconds <= 0: raise IngressError('Funded ingress deadline reached')
        return seconds

    def exchange(method, url, body, headers):
        if used['writeRequests'] >= caps['classARequests']:
            raise IngressError('Prepaid request count exhausted')
        sent = len(body) if method == 'PUT' and body else 0
        if used['uploadBodyBytesAttempted']+sent > expected_bytes+recoveries*chunk:
            raise IngressError('Bounded retransmission bytes exhausted')
        seconds = timeout()
        used['writeRequests'] += 1
        used['uploadBodyBytesAttempted'] += sent
        journal.save(usage=used)
        req = Request(url, data=body, headers=headers, method=method)
        try:
            try: response = store.opener(req, timeout=seconds)
            except HTTPError as e: response = e
            with response as r:
                if r.geturl() != url: raise IngressError('Redirect rejected')
                raw = r.read(MAX_METADATA+1)
                used['responseBodyBytes'] += len(raw)
                if len(raw) > MAX_METADATA: raise IngressError('Oversized response')
                return r.code if isinstance(r, HTTPError) else r.status, dict(r.headers), raw
        except (URLError, OSError, TimeoutError):
            raise IngressError('Ambiguous transport failure') from None
        finally:
            journal.save(usage=used)

    endpoint = 'https://storage.googleapis.com/upload/storage/v1/b/'+BUCKET+'/o'
    url = endpoint+'?'+urlencode({'uploadType':'resumable','name':key,'ifGenerationMatch':'0'})
    metadata = canonical({'name':key, 'contentType':'application/octet-stream',
                          'md5Hash':base64.b64encode(md5.digest()).decode()})
    status, headers, raw = exchange('POST', url, metadata, {
        'Authorization':'Bearer '+store.token_provider(), 'Content-Type':'application/json',
        'X-Upload-Content-Length':str(expected_bytes),
        'X-Upload-Content-Type':'application/octet-stream', 'Accept-Encoding':'identity'})
    if status != 200: raise IngressError('Session initiation rejected: '+str(status))
    low = {k.lower():v for k,v in headers.items()}
    session = validate_session(low.get('location',''), key)
    journal.save(sessionURI=session)
    offset = 0; obj = None; remaining_recoveries = recoveries
    with path.open('rb') as f:
        while obj is None:
            f.seek(offset); body = f.read(min(chunk, expected_bytes-offset))
            if not body: raise IngressError('Missing bytes or completion metadata')
            end = offset+len(body)
            try:
                status, headers, raw = exchange('PUT', session, body, {
                    'Content-Type':'application/octet-stream',
                    'Content-Range':f'bytes {offset}-{end-1}/{expected_bytes}',
                    'Accept-Encoding':'identity'})
            except IngressError as e:
                if str(e) != 'Ambiguous transport failure': raise
                status = 599
            if status >= 500:
                if not remaining_recoveries: raise IngressError('Recovery allowance exhausted')
                remaining_recoveries -= 1; used['statusQueries'] += 1
                status, headers, raw = exchange('PUT', session, b'', {
                    'Content-Range':f'bytes */{expected_bytes}', 'Accept-Encoding':'identity'})
            if status in (200, 201):
                obj = json.loads(raw)
            elif status == 308:
                low = {k.lower():v for k,v in headers.items()}
                value = low.get('range')
                match = re.fullmatch(r'bytes=0-([0-9]+)', value) if value else None
                if value and not match: raise IngressError('Invalid acknowledged range')
                confirmed = int(match[1])+1 if match else 0
                if not offset <= confirmed <= end or confirmed >= expected_bytes:
                    raise IngressError('Acknowledged range outside transmitted extent')
                if confirmed == offset and used['statusQueries'] == 0:
                    raise IngressError('Upload made no confirmed progress')
                offset = confirmed
                journal.save(confirmedOffset=offset)
            else:
                raise IngressError('Resumable upload rejected: '+str(status))
    if (obj.get('bucket') != BUCKET or obj.get('name') != key
            or str(obj.get('size')) != str(expected_bytes)
            or obj.get('md5Hash') != base64.b64encode(md5.digest()).decode()):
        raise IngressError('Uploaded object metadata/checksum mismatch')
    ref = Ref(key, str(obj.get('generation')), expected_bytes, expected_sha256)
    journal.save(uploadedRef=ref.__dict__, confirmedOffset=expected_bytes)
    # Custom SHA metadata is NOT evidence of bytes. Hash the pinned media stream.
    url = 'https://storage.googleapis.com/storage/v1/b/'+BUCKET+'/o/'+quote(key,safe='')+'?'+urlencode({
        'alt':'media','generation':ref.generation,'ifGenerationMatch':ref.generation})
    seconds = timeout()
    used['readRequests'] += 1; journal.save(usage=used)
    request = Request(url, headers={'Authorization':'Bearer '+store.token_provider(),
                                   'Accept-Encoding':'identity'}, method='GET')
    hashed = hashlib.sha256(); count = 0
    try:
        with store.opener(request, timeout=seconds) as r:
            low = {k.lower():v for k,v in r.headers.items()}
            if (r.geturl() != url or r.status != 200
                    or low.get('x-goog-generation') != ref.generation
                    or low.get('content-encoding', 'identity') != 'identity'):
                raise IngressError('Readback generation/status/encoding mismatch')
            while True:
                timeout()
                data = r.read(min(CHUNK, expected_bytes+1-count))
                if not data: break
                count += len(data); used['readbackBytes'] = count
                if count > expected_bytes: raise IngressError('Readback exceeds reserved length')
                hashed.update(data)
    except (HTTPError, URLError, OSError, TimeoutError):
        raise IngressError('Pinned readback failed; object remains unaccepted') from None
    finally:
        journal.save(usage=used)
    if count != expected_bytes or hashed.hexdigest() != expected_sha256:
        raise IngressError('Readback size/SHA256 mismatch')
    journal.save(accepted=True, sessionURI=None, usage=used)
    return {'format':'rrgh-verified-ingress-v1', 'ref':ref.__dict__,
            'sha256ReadbackVerified':True, 'usage':used, 'nonrefundableReservation':caps}
