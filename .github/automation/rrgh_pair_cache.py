"""Isolated SQLite writers, immutable range reuse, and lossless ledger unions."""
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from rrgh_batch_contract import require


@contextmanager
def connect(path):
    db=sqlite3.connect(path)
    try:
        require(db.execute('PRAGMA integrity_check(10)').fetchall()==[('ok',)],'Cache ledger integrity')
        with db:yield db
    finally:db.close()


def link(source,target):
    require(source.is_file() and not source.is_symlink(),'Unsafe cache input')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():os.link(source,target)
    else:require(os.path.samefile(source,target),'Unexpected immutable cache replacement')


def seed(root,target):
    """Called only between pairs: both child processes have exited."""
    target.mkdir(mode=0o700)
    marks={}
    for kind,name,table in [('cog','cache.sqlite','transfers'),('service','requests.sqlite','calls')]:
        source=root/('working-'+kind);dest=target/('working-'+kind);dest.mkdir(mode=0o700)
        with connect(source/name) as src, connect(dest/name) as dst:
            src.backup(dst)
            marks[kind]=src.execute('SELECT COALESCE(MAX(id),0) FROM '+table).fetchone()[0]
            if kind=='cog':
                marks['sources']=src.execute('SELECT * FROM sources').fetchall()
                marks['blocks']=src.execute('SELECT * FROM blocks').fetchall()
        for p in source.rglob('*'):
            if p.is_file() and (('blocks' in p.relative_to(source).parts) or p.suffix in ('.bin','.json')):
                link(p,dest/p.relative_to(source))
    (target/'worker').mkdir(mode=0o700)
    return marks


def usage(root):
    with connect(root/'working-cog/cache.sqlite') as db:
        total=db.execute('SELECT COALESCE(SUM(bytes),0) FROM blocks').fetchone()[0]
    return total+sum(p.stat().st_size for p in (root/'working-service').glob('*.bin'))


def merge(root,child,marks):
    from hashlib import sha256
    reused=0
    with connect(child/'working-cog/cache.sqlite') as src, connect(root/'working-cog/cache.sqlite') as dst:
        require(src.execute('SELECT * FROM config').fetchall()==dst.execute('SELECT * FROM config').fetchall(),
                'Cache allowance changed')
        for table in ('sources','blocks'):
            require(set(marks[table])<=set(src.execute('SELECT * FROM '+table).fetchall()),
                    'Prior cache rows changed or disappeared')
        old=dst.execute('SELECT * FROM transfers WHERE id<=? ORDER BY id',(marks['cog'],)).fetchall()
        require(src.execute('SELECT * FROM transfers WHERE id<=? ORDER BY id',(marks['cog'],)).fetchall()==old,
                'Prior source transfers changed')
        for url,identity,metadata in src.execute('SELECT * FROM sources'):
            previous=dst.execute('SELECT identity,metadata FROM sources WHERE url=?',(url,)).fetchone()
            if previous:
                before=json.loads(previous[1]);after=json.loads(metadata)
                before.pop('pinnedAtUTC',None);after.pop('pinnedAtUTC',None)
                require(previous[0]==identity and before==after,'Source identity conflict between children')
            else:dst.execute('INSERT INTO sources VALUES (?,?,?)',(url,identity,metadata))
        for identity,number,sha,size in src.execute('SELECT * FROM blocks'):
            old=dst.execute('SELECT sha,bytes FROM blocks WHERE identity=? AND number=?',(identity,number)).fetchone()
            p=child/'working-cog/blocks'/identity/str(number)
            if old:
                require(old==(sha,size),'Immutable cache block conflict')
                target=root/'working-cog/blocks'/identity/str(number)
                require(p.is_file() and not p.is_symlink() and
                        (os.path.samefile(p,target) or
                         (p.stat().st_size==size and sha256(p.read_bytes()).hexdigest()==sha)),
                        'Conflicting parallel cache bytes')
                reused+=size
                continue
            require(p.is_file() and not p.is_symlink() and p.stat().st_size==size and
                    sha256(p.read_bytes()).hexdigest()==sha,'New cache range failed hash verification')
            target=root/'working-cog/blocks'/identity/str(number)
            link(p,target)
            dst.execute('INSERT INTO blocks VALUES (?,?,?,?)',(identity,number,sha,size))
        columns='url,start,end,reserved,received,status,seconds,error'
        for row in src.execute('SELECT '+columns+' FROM transfers WHERE id>? ORDER BY id',(marks['cog'],)):
            dst.execute('INSERT INTO transfers('+columns+') VALUES (?,?,?,?,?,?,?,?)',row)
    # This first integration deliberately accepts only the three original-COG
    # families. Service exports and overview dependencies keep their serial path.
    with connect(child/'working-service/requests.sqlite') as src, connect(root/'working-service/requests.sqlite') as dst:
        for table in ('budget','calls'):
            require(src.execute('SELECT * FROM '+table).fetchall()==dst.execute('SELECT * FROM '+table).fetchall(),
                    'Unexpected service source activity in COG pair')
    return reused
