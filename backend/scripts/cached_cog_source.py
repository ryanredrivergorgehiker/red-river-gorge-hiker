#!/usr/bin/env python3
"""Pinned, bounded, persistent original-COG range cache for offline engineering.

Single producer per cache, SQLite transfer reservations survive interruption,
64KiB blocks are content-checked on every reuse. No source data enters GitHub.
Only allowlisted official source objects; no cached web-map tile endpoints.
"""
from contextlib import contextmanager
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock, Thread
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BLOCK = 65536
MAX_REQUEST = 2_097_152
MAX_PROXY_READ = 8_388_608
HOSTS = {"kyfromabove.s3.us-west-2.amazonaws.com", "prd-tnm.s3.amazonaws.com"}
RANGE = re.compile(r"bytes=(\d+)-(\d+)$")
CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)$")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".partial")
    with temp.open("wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def official_url(url):
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname not in HOSTS or p.query or p.fragment
            or p.username or p.port or not p.path.lower().endswith((".tif", ".tiff"))):
        raise ValueError("Expected allowlisted original government GeoTIFF")
    if p.hostname == "kyfromabove.s3.us-west-2.amazonaws.com" and not p.path.startswith(
            ("/elevation/", "/imagery/orthos/")):
        raise ValueError("Not an approved Kentucky original-source family")
    return url


class Cache:
    def __init__(self, root, limit=250_000_000, opener=urlopen, maximum_limit=2_000_000_000):
        if type(maximum_limit) is not int or not 1 <= maximum_limit <= 1_000_000_000_000 or type(limit) is not int or not 1 <= limit <= maximum_limit:
            raise ValueError("Explicit cumulative source transfer ceiling required")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.file_lock = (self.root / "producer.lock").open("a+")
        try:
            fcntl.flock(self.file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file_lock.close()
            raise RuntimeError("Another producer holds this cache")
        self.lock = RLock()
        self.opener = opener
        self.db = sqlite3.connect(self.root / "cache.sqlite", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, ceiling INTEGER);
          CREATE TABLE IF NOT EXISTS sources (url TEXT PRIMARY KEY, identity TEXT, metadata TEXT);
          CREATE TABLE IF NOT EXISTS blocks (identity TEXT, number INTEGER, sha TEXT,
            bytes INTEGER, PRIMARY KEY(identity,number));
          CREATE TABLE IF NOT EXISTS transfers (id INTEGER PRIMARY KEY, url TEXT,
            start INTEGER, end INTEGER, reserved INTEGER, received INTEGER DEFAULT 0,
            status TEXT, seconds REAL DEFAULT 0, error TEXT);
        """)
        previous = self.db.execute("SELECT ceiling FROM config WHERE id=1").fetchone()
        if previous and previous[0] != limit:
            self.close()
            raise ValueError("Resume must preserve original cumulative transfer ceiling")
        self.db.execute("INSERT OR IGNORE INTO config VALUES (1,?)", (limit,))
        self.db.commit()
        self.limit = limit
        self.hits = self.hit_bytes = 0

    def close(self):
        self.db.close()
        fcntl.flock(self.file_lock, fcntl.LOCK_UN)
        self.file_lock.close()

    def source(self, url):
        """Pin exact length and strong S3 ETag once; future misses use If-Match."""
        official_url(url)
        with self.lock:
            row = self.db.execute("SELECT metadata FROM sources WHERE url=?", (url,)).fetchone()
            if row:
                return json.loads(row[0])
            req = Request(url, method="HEAD", headers={"Accept-Encoding": "identity"})
            with self.opener(req, timeout=25) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError("Source HEAD status/redirect rejected")
                length = int(response.headers.get("Content-Length", 0))
                etag = response.headers.get("ETag", "")
                modified = response.headers.get("Last-Modified")
            if not 100_000 <= length <= 10_000_000_000 or not etag.startswith('"') or not etag.endswith('"'):
                raise ValueError("Missing valid immutable object identity")
            identity = digest(json.dumps([url, etag, length]).encode())
            result = {"url": url, "length": length, "etag": etag, "identity": identity,
                      "lastModified": modified, "pinnedAtUTC": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            self.db.execute("INSERT INTO sources VALUES (?,?,?)", (url, identity, json.dumps(result)))
            self.db.commit()
            return result

    def _block(self, source, n, last=None):
        row = self.db.execute("SELECT sha,bytes FROM blocks WHERE identity=? AND number=?",
                              (source["identity"], n)).fetchone()
        path = self.root / "blocks" / source["identity"] / str(n)
        if row:
            if path.is_symlink() or not path.is_file():
                raise ValueError("Missing or unsafe committed cache block")
            raw = path.read_bytes()
            if len(raw) != row[1] or digest(raw) != row[0]:
                raise ValueError("Cache corruption; refuse silent reuse/redownload")
            self.hits += 1
            self.hit_bytes += len(raw)
            return raw
        last = n if last is None else min(last, n + MAX_REQUEST // BLOCK - 1)
        # Coalesce only adjacent missing blocks in the requested span.
        for candidate in range(n + 1, last + 1):
            if self.db.execute("SELECT 1 FROM blocks WHERE identity=? AND number=?",
                               (source["identity"], candidate)).fetchone():
                last = candidate - 1
                break
        start, end = n * BLOCK, min(source["length"], (last + 1) * BLOCK) - 1
        amount = end - start + 1
        used = self.db.execute("SELECT COALESCE(SUM(reserved),0) FROM transfers").fetchone()[0]
        if amount <= 0 or used + amount > self.limit:
            raise ValueError("Cumulative original-source byte ceiling reached")
        cursor = self.db.execute("INSERT INTO transfers(url,start,end,reserved,status) VALUES(?,?,?,?,?)",
                                  (source["url"], start, end, amount, "reserved"))
        ident = cursor.lastrowid
        self.db.commit()  # reserve BEFORE opening the network
        begin, received = time.perf_counter(), 0
        try:
            req = Request(source["url"], headers={
                "Range": f"bytes={start}-{end}", "If-Match": source["etag"],
                "Accept-Encoding": "identity", "User-Agent": "RRGH-original-COG-benchmark/1.0"})
            with self.opener(req, timeout=25) as response:
                m = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
                if (response.status != 206 or response.geturl() != source["url"] or not m
                        or tuple(map(int, m.groups())) != (start, end, source["length"])
                        or response.headers.get("ETag") != source["etag"]
                        or int(response.headers.get("Content-Length", -1)) != amount):
                    raise ValueError("Original object identity/206/length changed")
                raw = response.read(amount)
                received = len(raw)
                if received != amount:
                    raise ValueError("Truncated original source range")
            for number in range(n, last + 1):
                block = raw[(number - n) * BLOCK:(number - n + 1) * BLOCK]
                block_path = self.root / "blocks" / source["identity"] / str(number)
                atomic(block_path, block)
                self.db.execute("INSERT INTO blocks VALUES (?,?,?,?)", (source["identity"], number, digest(block), len(block)))
            self.db.execute("UPDATE transfers SET received=?,status='complete',seconds=? WHERE id=?",
                            (received, time.perf_counter() - begin, ident))
            self.db.commit()
            return raw[:BLOCK]
        except Exception as error:
            self.db.execute("UPDATE transfers SET received=?,status='failed',seconds=?,error=? WHERE id=?",
                            (received, time.perf_counter() - begin, str(error)[:300], ident))
            self.db.commit()
            raise

    def read(self, source, start, end):
        if not 0 <= start <= end < source["length"] or end - start + 1 > MAX_PROXY_READ:
            raise ValueError("Invalid/unbounded source range")
        with self.lock:
            chunks = [self._block(source, n, end // BLOCK) for n in range(start // BLOCK, end // BLOCK + 1)]
            return b"".join(chunks)[start % BLOCK:start % BLOCK + end - start + 1]

    def metrics(self):
        with self.lock:
            r = self.db.execute("SELECT COUNT(*),COALESCE(SUM(reserved),0),COALESCE(SUM(received),0),COALESCE(SUM(seconds),0) FROM transfers").fetchone()
            return dict(requests=r[0], reservedBytes=r[1], receivedBytes=r[2], networkSeconds=r[3],
                        cacheHitsThisProcess=self.hits, cacheHitBytesThisProcess=self.hit_bytes,
                        failedRequests=self.db.execute("SELECT COUNT(*) FROM transfers WHERE status!='complete'").fetchone()[0],
                        byteCeiling=self.limit)

    @contextmanager
    def serve(self, sources):
        cache = self
        lookup = {"/" + str(n) + ".tif": self.source(s["url"]) for n, s in enumerate(sources)}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_HEAD(self):
                s = lookup.get(self.path)
                if not s:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header("Content-Length", str(s["length"]))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
            def do_GET(self):
                s = lookup.get(self.path)
                m = RANGE.fullmatch(self.headers.get("Range", ""))
                if not s or not m:
                    self.send_error(416); return
                start, end = map(int, m.groups())
                try:
                    raw = cache.read(s, start, end)
                    self.send_response(206)
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Content-Range", f"bytes {start}-{end}/{s['length']}")
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as error:
                    print(f"COG proxy rejected bounded read {start}-{end} ({end-start+1} bytes): {error}", flush=True)
                    self.send_error(502, type(error).__name__)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield [f"http://127.0.0.1:{server.server_port}/{n}.tif" for n in range(len(sources))]
        finally:
            server.shutdown()
            server.server_close()
