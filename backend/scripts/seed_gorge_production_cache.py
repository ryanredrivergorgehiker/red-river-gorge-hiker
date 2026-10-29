#!/usr/bin/env python3
"""Seed a NEW bounded production ledger with verified bytes from an old cache.

The source ledger is locked and read-only. Its reservations are not reset or
increased. Imported bytes retain their source identities and hashes, and the
new ledger accounts only for subsequent new transfers. No network operations.
"""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from cached_cog_source import Cache, atomic, digest
from benchmark_ky_naip_usgs import ServiceCache
from benchmark_gorge_pipeline import json_bytes


def seed(source, destination, kind, byte_limit, request_limit=120):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source in destination.parents or destination.exists():
        raise ValueError('New, separate destination required; existing ledgers are immutable')
    database = 'cache.sqlite' if kind == 'cog' else 'requests.sqlite'
    if kind not in ('cog', 'service') or not (source/database).is_file():
        raise ValueError('Existing recognized source cache required')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (source/'producer.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(f'file:{source/database}?mode=ro', uri=True)
        temporary = Path(tempfile.mkdtemp(prefix='.seed-', dir=destination.parent))
        target = None
        try:
            snapshot = temporary/'seed-origin.sqlite'
            with sqlite3.connect(snapshot) as backup:
                db.backup(backup)
            origin_hash = digest(snapshot.read_bytes())
            files = []
            if kind == 'cog':
                target = Cache(temporary, limit=byte_limit, maximum_limit=1_000_000_000_000)
                for row in db.execute('SELECT url,identity,metadata FROM sources'):
                    target.db.execute('INSERT INTO sources VALUES (?,?,?)', row)
                for identity, number, sha, size in db.execute('SELECT identity,number,sha,bytes FROM blocks ORDER BY identity,number'):
                    relative = Path('blocks')/identity/str(number)
                    old = source/relative
                    if old.is_symlink() or not old.is_file():
                        raise ValueError('Missing or unsafe source block')
                    raw = old.read_bytes()
                    if len(raw) != size or digest(raw) != sha:
                        raise ValueError('Source cache corruption; no silent redownload')
                    atomic(temporary/relative, raw)
                    target.db.execute('INSERT INTO blocks VALUES (?,?,?,?)', (identity, number, sha, size))
                    files.append({'path': str(relative), 'bytes': size, 'sha256': sha})
                old_limits = db.execute('SELECT ceiling FROM config WHERE id=1').fetchone()
                old_usage = db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0) FROM transfers').fetchone()
            else:
                target = ServiceCache(temporary, byte_limit=byte_limit, request_limit=request_limit)
                for old in sorted(source.glob('*.json')):
                    if len(old.stem) != 64:
                        continue
                    metadata = json.loads(old.read_bytes())
                    data = old.with_suffix('.bin')
                    if old.is_symlink() or data.is_symlink() or not data.is_file():
                        raise ValueError('Missing or unsafe service response')
                    raw = data.read_bytes()
                    if len(raw) != metadata['bytes'] or digest(raw) != metadata['sha256']:
                        raise ValueError('Source response corruption; no silent redownload')
                    atomic(temporary/old.name, old.read_bytes())
                    atomic(temporary/data.name, raw)
                    files.append({'path': data.name, 'bytes': len(raw), 'sha256': digest(raw)})
                old_limits = db.execute('SELECT bytes,requests FROM budget').fetchone()
                old_usage = db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0) FROM calls').fetchone()
            target.db.commit()
            target.close()
            target = None
            receipt = {'format': 'rrgh-cache-seed-v1', 'kind': kind,
                       'originDatabaseSHA256': origin_hash,
                       'originLimits': old_limits, 'originRequestsReservedReceived': old_usage,
                       'importedFiles': files, 'importedBytes': sum(f['bytes'] for f in files),
                       'newTransferBytes': 0, 'newByteLimit': byte_limit,
                       'newRequestLimit': request_limit if kind == 'service' else None}
            atomic(temporary/'SEED-RECEIPT.json', json_bytes(receipt))
            temporary.rename(destination)
            return receipt
        finally:
            if target is not None:
                target.close()
            db.close()
            if temporary.exists():
                shutil.rmtree(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--kind', required=True, choices=['cog', 'service'])
    parser.add_argument('--byte-limit', required=True, type=int)
    parser.add_argument('--request-limit', type=int, default=120)
    args = parser.parse_args()
    result = seed(args.source, args.destination, args.kind, args.byte_limit, args.request_limit)
    print(json.dumps({k:v for k,v in result.items() if k != 'importedFiles'}, indent=2))
