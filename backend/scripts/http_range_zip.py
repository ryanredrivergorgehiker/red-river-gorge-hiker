"""Seekable HTTP byte-range reader for approved official Kentucky TPKX ZIPs.

Fetches only requested byte ranges, with identity headers, fixed request caps,
ETag/size consistency checks and an explicit transfer budget. Never falls
back to downloading full multi-GB county archives.
"""
from collections import OrderedDict
import io
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class RangeZipReader(io.RawIOBase):
    def __init__(self, url, *, opener=urlopen,
                 chunk_size=262_144, max_transfer_bytes=1_500_000_000,
                 max_cache_chunks=16):
        super().__init__()
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "ky.box.com" or \
                not parsed.path.startswith("/shared/static/"):
            raise ValueError("Only direct official Kentucky Box TPKX references")
        if not (4096 <= chunk_size <= 2_097_152 and
                1 <= max_cache_chunks <= 64 and
                max_transfer_bytes >= chunk_size):
            raise ValueError("Unsafe range reader configuration")
        self.url = url
        self._opener = opener
        self.chunk_size = chunk_size
        self.max_transfer_bytes = max_transfer_bytes
        self.max_cache_chunks = max_cache_chunks
        self.cache = OrderedDict()
        self.position = 0
        self.transfer_bytes = 0
        self.etag = None
        # Probe precisely one byte, never a blind HEAD or unbounded GET.
        first, total, etag = self._range(0, 0)
        if len(first) != 1 or total <= 0:
            raise ValueError("Provider does not support safe ranged access")
        self.length = total
        self.etag = etag

    def _range(self, start, end):
        if end < start or end - start > self.chunk_size:
            raise ValueError("Unbounded HTTP source read refused")
        requested = end - start + 1
        if self.transfer_bytes + requested > self.max_transfer_bytes:
            raise ValueError("Per-source byte-range transfer budget exceeded")
        request = Request(self.url, headers={
            "Range": f"bytes={start}-{end}",
            "Accept-Encoding": "identity",
            "User-Agent": "RRGH-private-offline-map-builder/1.0",
        })
        with self._opener(request, timeout=30) as response:
            if response.status != 206:
                raise ValueError("Server refused HTTP 206 byte-range response")
            match = RANGE.fullmatch(response.headers.get("Content-Range", ""))
            if not match:
                raise ValueError("Invalid content range metadata")
            low, high, total = (int(v) for v in match.groups())
            if low != start or high != end or (hasattr(self, "length") and
                                                total != self.length):
                raise ValueError("Source changed or remote byte range mismatch")
            etag = response.headers.get("ETag")
            if self.etag and etag and etag != self.etag:
                raise ValueError("Source ETag changed during extraction")
            data = response.read(requested + 1)
            if len(data) != requested:
                raise ValueError("Incomplete or oversized ranged response")
        self.transfer_bytes += len(data)
        return data, total, etag

    def _block(self, start):
        if start in self.cache:
            self.cache.move_to_end(start)
            return self.cache[start]
        end = min(self.length - 1, start + self.chunk_size - 1)
        data, _, _ = self._range(start, end)
        self.cache[start] = data
        if len(self.cache) > self.max_cache_chunks:
            self.cache.popitem(last=False)
        return data

    def read(self, size=-1):
        if self.closed:
            raise ValueError("Reader is closed")
        if size is None or size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)
        parts = []
        while size > 0:
            aligned = (self.position // self.chunk_size) * self.chunk_size
            block = self._block(aligned)
            offset = self.position - aligned
            piece = block[offset:offset + size]
            if not piece:
                raise ValueError("Empty block in ranged ZIP")
            parts.append(piece)
            self.position += len(piece)
            size -= len(piece)
        return b"".join(parts)

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_END:
            new = self.length + offset
        elif whence == io.SEEK_CUR:
            new = self.position + offset
        elif whence == io.SEEK_SET:
            new = offset
        else:
            raise ValueError("Invalid seek mode")
        if new < 0:
            raise ValueError("Negative source offset")
        self.position = new
        return new

    def tell(self):
        return self.position

    def readable(self):
        return True

    def seekable(self):
        return True

    def close(self):
        self.cache.clear()
        super().close()

    @property
    def provenance(self):
        return {"sourceURL": self.url, "contentLength": self.length,
                "etag": self.etag, "rangeBytesTransferred": self.transfer_bytes,
                "hasFullArchiveSHA256": False}
