"""Lossless SQLite checkpoint encoding; original ledgers are never modified."""
import json,sqlite3,zlib
from pathlib import Path
from gorge_checkpoint import canonical,digest
MAGIC=b'RRGH-SQLITE-Z1\n'
MAX_RAW=8*2**20

def encode(raw):
    if not raw.startswith(b'SQLite format 3\x00') or len(raw)>MAX_RAW:raise ValueError('Invalid SQLite snapshot')
    return MAGIC+canonical({'bytes':len(raw),'sha256':digest(raw)})+zlib.compress(raw,9)

def decode(raw):
    if not raw.startswith(MAGIC):raise ValueError('Unknown state encoding')
    header,body=raw[len(MAGIC):].split(b'\n',1);meta=json.loads(header)
    if type(meta['bytes'])is not int or not 0<meta['bytes']<=MAX_RAW:raise ValueError('State expansion bound')
    decoder=zlib.decompressobj();data=decoder.decompress(body,meta['bytes']+1)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(data)!=meta['bytes'] or digest(data)!=meta['sha256']:raise ValueError('State integrity mismatch')
    return data

def recover(path):
    path=Path(path);out=path.with_suffix('');raw=decode(path.read_bytes())
    with out.open('xb') as stream:stream.write(raw)
    with sqlite3.connect('file:'+str(out)+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('Recovered SQLite integrity failure')
    return {'bytes':len(raw),'sha256':digest(raw)}
