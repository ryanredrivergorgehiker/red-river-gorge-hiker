import sqlite3
import pytest
from cached_cog_source import Cache


def test_corrupt_database_fails_before_network_or_reservation_and_releases_lock(tmp_path):
    cache=Cache(tmp_path,limit=1000000)
    cache.close()
    with sqlite3.connect(tmp_path/'cache.sqlite') as db:
        db.execute('PRAGMA writable_schema=ON')
        # Deliberately break a secondary index definition in this disposable
        # fixture. It must fail closed without a source call or budget reset.
        db.execute("UPDATE sqlite_master SET rootpage=999999 WHERE name='sqlite_autoindex_blocks_1'")
    original=(tmp_path/'cache.sqlite').read_bytes()
    calls=[]
    with pytest.raises((sqlite3.DatabaseError,ValueError)):
        Cache(tmp_path,limit=1000000,opener=lambda *a,**kw:calls.append(a))
    assert calls==[]
    assert (tmp_path/'cache.sqlite').read_bytes()==original
    import fcntl
    with (tmp_path/'producer.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)


def test_healthy_existing_ledger_survives_integrity_gate(tmp_path):
    cache=Cache(tmp_path,limit=1000000)
    cache.db.execute("INSERT INTO transfers(url,start,end,reserved,received,status) VALUES ('fixture',0,99,100,0,'reserved')")
    cache.db.commit();cache.close()
    cache=Cache(tmp_path,limit=1000000)
    try:
        assert cache.metrics()['reservedBytes']==100
        assert cache.metrics()['receivedBytes']==0
        assert cache.db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
    finally:cache.close()
