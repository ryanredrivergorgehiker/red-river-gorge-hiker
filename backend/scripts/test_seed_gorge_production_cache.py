import json
import sqlite3
import pytest
from cached_cog_source import Cache, atomic, digest
from seed_gorge_production_cache import seed
from benchmark_ky_naip_usgs import ServiceCache, NAIP


def source_cache(path):
    cache=Cache(path, limit=1000000)
    raw=b'original block'
    cache.db.execute('INSERT INTO blocks VALUES (?,?,?,?)', ('identity',0,digest(raw),len(raw)))
    cache.db.execute("INSERT INTO transfers(url,start,end,reserved,received,status) VALUES ('test',0,13,14,14,'complete')")
    atomic(path/'blocks/identity/0',raw)
    cache.db.commit();cache.close()
    return raw


def test_seed_preserves_old_ledger_and_reuses_verified_bytes(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new'
    raw=source_cache(old)
    before=(old/'cache.sqlite').read_bytes()
    receipt=seed(old,new,'cog',2000000)
    assert (old/'cache.sqlite').read_bytes()==before
    assert receipt['importedBytes']==len(raw)
    cache=Cache(new,limit=2000000)
    assert cache._block({'identity':'identity'},0)==raw
    assert cache.metrics()['receivedBytes']==0
    cache.close()
    with pytest.raises(ValueError,match='separate destination'):
        seed(old,new,'cog',3000000)


def test_corruption_fails_without_partial_destination(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new'
    source_cache(old)
    (old/'blocks/identity/0').write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='corruption'):
        seed(old,new,'cog',2000000)
    assert not new.exists()
    assert not list(tmp_path.glob('.seed-*'))


def test_active_source_cannot_be_seeded(tmp_path):
    old=tmp_path/'old';source_cache(old)
    cache=Cache(old,limit=1000000)
    try:
        with pytest.raises(BlockingIOError):
            seed(old,tmp_path/'new','cog',2000000)
    finally:
        cache.close()


def test_service_seed_reuses_response_without_changing_origin(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new'
    cache=ServiceCache(old,byte_limit=1000000,request_limit=3)
    raw=b'cached service data';key=digest(NAIP.encode())
    atomic(old/(key+'.bin'),raw)
    atomic(old/(key+'.json'),json.dumps({'sha256':digest(raw),'bytes':len(raw)}).encode())
    cache.db.execute("INSERT INTO calls(key,reserved,received,status,seconds) VALUES (?,?,?,'complete',1)",(key,len(raw),len(raw)))
    cache.db.commit();cache.close()
    before=(old/'requests.sqlite').read_bytes()
    receipt=seed(old,new,'service',2000000,5)
    assert (old/'requests.sqlite').read_bytes()==before
    assert receipt['originLimits']==(1000000,3)
    with sqlite3.connect(new/'seed-origin.sqlite') as db:
        assert db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]==1
    cache=ServiceCache(new,byte_limit=2000000,request_limit=5)
    try:
        assert cache.fetch(NAIP)[0]==raw
        assert cache.metrics()['requests']==0
    finally:
        cache.close()
