#!/usr/bin/env python3
"""Receive one exact private seed through a short-lived Actions secret.

The source URL is never a CLI argument, public input, log or receipt. No GCS
operation, source processing, credential creation or workflow dispatch occurs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

SEED_BYTES = 309600543
SEED_SHA256 = '307b31fe6fd2d0d77747a59454bed54f77357706d1732e19c718de19a4c997f8'
PARTS = (
 (83886080, '9d2c686ff4d957cd2210a00ff07058d2a67f447569f721df2b9eed5362c10abf'),
 (83886080, '8004013a1660bdf34f3137086d1a42ab3a03090c6a5d0a80dfdb90173bfa9919'),
 (83886080, '0506b27a82e9cf017d06ce7709681c3e3415daf596d66cce18bc18d23eafa61f'),
 (57942303, '31ebe035c9844ab587105090bff36d454659f41ddcbc6190b87b575fc5a95a2e'),
)
CONTEXT = {
 'GITHUB_REPOSITORY_ID':'1325611891',
 'GITHUB_REPOSITORY_OWNER_ID':'313924954',
 'GITHUB_REF':'refs/heads/lane20/offline-production-preflight-20261029',
 'GITHUB_EVENT_NAME':'push', 'GITHUB_RUN_ATTEMPT':'1',
 'GITHUB_WORKFLOW_REF':'ryanredrivergorgehiker/red-river-gorge-hiker/.github/workflows/offline-map-producer-access.yml@refs/heads/lane20/offline-production-preflight-20261029',
}


class SeedTransferError(RuntimeError): pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def validate_descriptor(descriptor, now=None):
    """Validate the actual provider-issued one-blob, read-only references."""
    now = now or datetime.now(timezone.utc)
    if (not isinstance(descriptor, dict)
            or descriptor.get('format') != 'rrgh-stage-seed-transfer-v1'
            or descriptor.get('seedSHA256') != SEED_SHA256
            or descriptor.get('seedBytes') != SEED_BYTES):
        raise SeedTransferError('Unexpected seed descriptor')
    parts = descriptor.get('parts')
    if not isinstance(parts, list) or len(parts) != len(PARTS):
        raise SeedTransferError('All four ordered seed parts required')
    references = []; seen = set()
    for index, (entry, expected) in enumerate(zip(parts, PARTS), 1):
        if (not isinstance(entry, dict) or entry.get('part') != index
                or entry.get('bytes') != expected[0] or entry.get('sha256') != expected[1]):
            raise SeedTransferError('Seed part identity changed')
        url = entry.get('download_url')
        if not isinstance(url, str) or len(url) > 8192 or any(c.isspace() for c in url):
            raise SeedTransferError('Invalid private download reference')
        try:
            p = urlsplit(url); q = parse_qs(p.query, keep_blank_values=True)
            expiry = datetime.fromisoformat(q['se'][0].replace('Z','+00:00'))
            valid = (p.scheme == 'https' and p.netloc == p.hostname
                and re.fullmatch(r'sdmntpr[a-z0-9-]+\.oaiusercontent\.com', p.hostname or '')
                and not p.fragment and p.path.startswith('/') and p.path != '/'
                and q.get('sp') == ['r'] and q.get('sr') == ['b']
                and len(q.get('sig',[])) == 1 and q['sig'][0]
                and all(len(v) == 1 for v in q.values())
                and expiry.tzinfo is not None and 30 < (expiry-now).total_seconds() <= 3600)
        except (ValueError, KeyError, TypeError): valid = False
        if not valid or url in seen:
            raise SeedTransferError('Reference must be private, read-only and unexpired')
        seen.add(url); references.append((url, expiry))
    return references


def receive(descriptor, destination, opener=None):
    references = validate_descriptor(descriptor)
    target = Path(destination)
    parent = target.parent
    if (parent.is_symlink() or not parent.is_dir()
            or stat.S_IMODE(parent.stat().st_mode) & 0o077
            or target.exists() or target.is_symlink()):
        raise SeedTransferError('A fresh private destination is required')
    partial = target.with_name(target.name+'.partial')
    if partial.exists() or partial.is_symlink():
        raise SeedTransferError('Previous transfer requires explicit reconciliation')
    open_url = opener or build_opener(NoRedirect()).open
    whole = hashlib.sha256(); total = 0; count = 0
    deadline = time.monotonic()+300
    try:
        with os.fdopen(os.open(partial, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as out:
            for (url, expiry), (size, expected_sha) in zip(references, PARTS):
                remaining = min(deadline-time.monotonic(),
                    (expiry-datetime.now(timezone.utc)).total_seconds(), 45)
                if remaining <= 0: raise SeedTransferError('Private transfer deadline reached')
                req = Request(url, headers={'Accept-Encoding':'identity'}, method='GET')
                count += 1; part_hash = hashlib.sha256(); received = 0
                with open_url(req, timeout=remaining) as response:
                    headers = {k.lower():v for k,v in response.headers.items()}
                    if (response.status != 200 or response.geturl() != url
                            or headers.get('content-encoding','identity') != 'identity'
                            or ('content-length' in headers and headers['content-length'] != str(size))):
                        raise SeedTransferError('Private response identity/length mismatch')
                    while True:
                        if time.monotonic() >= deadline:
                            raise SeedTransferError('Private transfer deadline reached')
                        raw = response.read(min(2**20, size+1-received))
                        if not raw: break
                        received += len(raw)
                        if received > size: raise SeedTransferError('Private response exceeds its bound')
                        part_hash.update(raw); whole.update(raw); out.write(raw); total += len(raw)
                if received != size or part_hash.hexdigest() != expected_sha:
                    raise SeedTransferError('Private part failed byte/hash verification')
            if total != SEED_BYTES or whole.hexdigest() != SEED_SHA256:
                raise SeedTransferError('Complete seed failed byte/hash verification')
            out.flush(); os.fsync(out.fileno())
        # Link is create-only: a concurrent target can never be replaced.
        os.link(partial, target); partial.unlink()
    except SeedTransferError: raise
    except Exception:
        # urllib errors include signed URLs. Never surface their text or chain.
        raise SeedTransferError('Private transfer failed; no retry or acceptance') from None
    return {'seedBytes':total,'seedSHA256':whole.hexdigest(),'privateReadRequests':count,
            'acceptedLocally':True,'gcsAccepted':False,'gcsOperations':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination',required=True,type=Path)
    args=p.parse_args()
    try:
        if any(os.environ.get(k)!=v for k,v in CONTEXT.items()):
            raise SeedTransferError('Exact existing producer workflow context required')
        raw=os.environ.pop('RRGH_STAGE_SEED_TRANSFER','')
        if not 0 < len(raw.encode()) <= 16384: raise SeedTransferError('Private input secret absent or oversized')
        descriptor=json.loads(raw); del raw
        root=Path(os.environ['RUNNER_TEMP']).resolve()
        checkout=Path(os.environ['GITHUB_WORKSPACE']).resolve()
        target=args.destination.resolve()
        if root not in target.parents or target==checkout or checkout in target.parents:
            raise SeedTransferError('Seed destination must be private runner temporary storage')
        print(json.dumps(receive(descriptor,target),sort_keys=True))
    except Exception:
        print('Private seed intake failed closed; secret values are not logged.')
        raise SystemExit(2) from None


if __name__=='__main__':main()
