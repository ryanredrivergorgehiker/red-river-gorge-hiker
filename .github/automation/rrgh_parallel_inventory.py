"""Read-only benchmark of disjoint coverage planning shards."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
from time import perf_counter


def scan_shard(task):
    uri, layer = task
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute("""
            SELECT r.z,r.x,r.y,
              (SELECT count(*) FROM accepted c
               WHERE c.layer=r.layer AND c.z=r.z+1
               AND c.x BETWEEN 2*r.x AND 2*r.x+1
               AND c.y BETWEEN 2*r.y AND 2*r.y+1),
              (SELECT count(*) FROM required c
               WHERE c.layer=r.layer AND c.z=r.z+1
               AND c.x BETWEEN 2*r.x AND 2*r.x+1
               AND c.y BETWEEN 2*r.y AND 2*r.y+1)
            FROM required r LEFT JOIN accepted a USING(layer,z,x,y)
            WHERE r.layer=? AND a.layer IS NULL ORDER BY r.z,r.x,r.y
        """, (layer,)).fetchall()
    return layer, rows


def benchmark(database, workers):
    uri = Path(database).resolve().as_uri() + '?mode=ro&immutable=1'
    with sqlite3.connect(uri, uri=True) as db:
        tasks = [(uri, row[0]) for row in db.execute(
            'SELECT DISTINCT layer FROM required ORDER BY layer')]
    start = perf_counter()
    if workers == 1:
        result = list(map(scan_shard, tasks))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            result = list(pool.map(scan_shard, tasks))
    elapsed = perf_counter() - start
    encoded = json.dumps(result, separators=(',', ':')).encode()
    return {'workers': workers, 'seconds': round(elapsed, 3),
            'missing': sum(len(rows) for _, rows in result),
            'sha256': hashlib.sha256(encoded).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', help='Closed, immutable SQLite snapshot')
    args = parser.parse_args()
    results = [benchmark(args.snapshot, n) for n in (1, 2, 4)]
    if len({r['sha256'] for r in results}) != 1:
        raise SystemExit('Parallel result differs from serial result')
    print(json.dumps(results))
