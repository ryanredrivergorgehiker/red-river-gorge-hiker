#!/usr/bin/env python3
"""Explicit selected COG cache export/import; old ledgers remain read-only.

Selections are source identity + block number, never an implicit whole-cache scan.
The original ledger fingerprint and totals accompany the selection. New cache
limits are subordinate to the nonrefundable checkpoint slot allocation.
"""
import fcntl
import json
from pathlib import Path
import sqlite3
import tempfile

from gorge_checkpoint import digest, relative_path, integer, canonical


def select_cog_cache(root, selected_blocks):
    root=Path(root).resolve();keys=list(selected_blocks)
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate block selection')
    with (root/'producer.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=sqlite3.connect(f'file:{root / "cache.sqlite"}?mode=ro',uri=True)
        try:
            if db.execute('PRAGMA integrity_check(10)').fetchall()!=[('ok',)]:
                raise ValueError('Preserve damaged ledger; repair is not automatic')
            with tempfile.TemporaryDirectory() as td:
                snap=Path(td)/'snapshot.sqlite'
                with sqlite3.connect(snap) as dest:db.backup(dest)
                ledger_hash=digest(snap.read_bytes())
            limits=db.execute('SELECT ceiling FROM config WHERE id=1').fetchone()
            usage=db.execute('SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0) FROM transfers').fetchone()
            sources={};entries=[];blocks=[]
            for identity,number in sorted(keys):
                integer(number)
                row=db.execute('SELECT sha,bytes FROM blocks WHERE identity=? AND number=?',(identity,number)).fetchone()
                src=db.execute('SELECT url,metadata FROM sources WHERE identity=?',(identity,)).fetchall()
                if row is None or len(src)!=1:raise ValueError('Selected committed block absent/ambiguous')
                name=relative_path(f'blocks/{identity}/{number}');p=root/name
                if p.is_symlink() or root not in p.resolve().parents or not p.is_file():raise ValueError('Unsafe cache block')
                raw=p.read_bytes()
                if len(raw)!=row[1] or digest(raw)!=row[0]:raise ValueError('Selected block corrupt')
                sources[identity]={'url':src[0][0],'identity':identity,'metadata':src[0][1]}
                entries.append({'path':name,'bytes':row[1],'sha256':row[0]})
                blocks.append({'identity':identity,'number':number,'sha':row[0],'bytes':row[1]})
            return {'format':'rrgh-selected-cog-v1','originLedgerSHA256':ledger_hash,
                'originCeiling':limits[0], 'originRequestsReservedReceived':usage,
                'sources':list(sources.values()),'blocks':blocks,'entries':entries,
                'selectedBytes':sum(e['bytes'] for e in entries),'newSourceTransfers':0}
        finally:db.close()


def seed_selected_cog(selection, recovered, destination, byte_ceiling):
    """Assemble fresh local cache only from verified range-recovered members."""
    from cached_cog_source import Cache,atomic
    recovered=Path(recovered).resolve();destination=Path(destination).resolve()
    if destination.exists() or recovered==destination or recovered in destination.parents:
        raise ValueError('Separate new cache destination required')
    if selection.get('format')!='rrgh-selected-cog-v1':raise ValueError('Unknown cache selection')
    temporary=destination.with_name(destination.name+'.partial')
    if temporary.exists():raise ValueError('Existing partial cache must be inspected')
    target=Cache(temporary,limit=integer(byte_ceiling),maximum_limit=1_000_000_000_000)
    try:
        for source in selection['sources']:
            meta=json.loads(source['metadata'])
            if meta['identity']!=source['identity'] or meta['url']!=source['url']:
                raise ValueError('Source identity mismatch')
            identity=digest(json.dumps([meta['url'],meta['etag'],meta['length']]).encode())
            if identity!=meta['identity']:raise ValueError('Source identity hash mismatch')
            target.db.execute('INSERT INTO sources VALUES (?,?,?)',(source['url'],source['identity'],source['metadata']))
        for b in selection['blocks']:
            name=relative_path(f"blocks/{b['identity']}/{integer(b['number'])}");p=recovered/name
            if p.is_symlink() or recovered not in p.resolve().parents:raise ValueError('Unsafe recovered block')
            raw=p.read_bytes()
            if len(raw)!=b['bytes'] or digest(raw)!=b['sha']:raise ValueError('Recovered block hash mismatch')
            if not target.db.execute('SELECT 1 FROM sources WHERE identity=?',(b['identity'],)).fetchone():raise ValueError('Block has no source')
            source=json.loads(target.db.execute('SELECT metadata FROM sources WHERE identity=?',(b['identity'],)).fetchone()[0])
            if b['number']*65536>=source['length'] or len(raw)!=min(65536,source['length']-b['number']*65536):
                raise ValueError('Recovered block extent mismatch')
            atomic(temporary/name,raw)
            target.db.execute('INSERT INTO blocks VALUES (?,?,?,?)',(b['identity'],b['number'],b['sha'],b['bytes']))
        target.db.commit()
        atomic(temporary/'SELECTION-ORIGIN.json',canonical(selection))
    finally:target.close()
    temporary.rename(destination)
    return {'selectedBlocks':len(selection['blocks']),'selectedBytes':selection['selectedBytes'],
            'originLedgerSHA256':selection['originLedgerSHA256'],'newSourceTransfers':0}
