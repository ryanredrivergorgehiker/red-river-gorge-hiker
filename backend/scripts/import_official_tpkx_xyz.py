#!/usr/bin/env python3
"""Import LOCAL, rights-reviewed Esri TPKX Compact Cache V2 tiles into XYZ.

No network access; no tile synthesis, reprojection, resampling, or deployment.
Each official county package must be downloaded separately with approved
reuse/attribution. Output is suitable as ONE named layer input for the
schema-4 package builder, not proof that all five layers exist.

Reference: Esri/raster-tiles-compactcache CompactCacheV2.md (Apache-2.0).
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

BUNDLE_RE = re.compile(
    r"(?:^|/)L([0-9A-Fa-f]{2})/R([0-9A-Fa-f]{4,8})C([0-9A-Fa-f]{4,8})\.bundle$",
    re.IGNORECASE,
)
ALLOWED_LAYERS = frozenset((
    "kentucky-topo", "usgs-topo", "terrain-relief",
    "leaf-on-aerial", "leaf-off-aerial",
))
HEADER_SIZE = 64
INDEX_SIZE = 131072
MAX_TILE_BYTES = 4 * 1024 * 1024


def xyz(lon, lat, z):
    import math
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 1 << z
    r = math.radians(lat)
    return (
        max(0, min(n - 1, int(math.floor((lon + 180) / 360 * n)))),
        max(0, min(n - 1, int(math.floor(
            (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
        )))),
    )


def valid_tile(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return ("png" if data[12:16] == b"IHDR" and
                int.from_bytes(data[16:20], "big") == 256 and
                int.from_bytes(data[20:24], "big") == 256 else None)
    if not data.startswith(b"\xff\xd8"):
        return None
    # JPEG Start-of-Frame dimension check, without Pillow or decompression.
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xff:
            return None
        while pos < len(data) and data[pos] == 0xff:
            pos += 1
        if pos >= len(data):
            return None
        marker = data[pos]
        pos += 1
        if marker in (0xd9, 0xda):
            return None
        if 0xd0 <= marker <= 0xd7 or marker == 0x01:
            continue
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > len(data):
            return None
        if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                      0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
            return ("jpg" if length >= 7 and
                    int.from_bytes(data[pos + 3:pos + 5], "big") == 256 and
                    int.from_bytes(data[pos + 5:pos + 7], "big") == 256 else None)
        pos += length
    return None


def web_mercator_256(root):
    # TPKX root.json has tileInfo and spatial reference in different
    # compatible ArcGIS metadata layouts. Reject anything not clearly
    # Web Mercator 256x256 using global Google/OSM top-left tile origin.
    ti = root.get("tileInfo") or root.get("tileinfo") or {}
    sr = ti.get("spatialReference") or root.get("spatialReference") or {}
    wkid = sr.get("latestWkid", sr.get("wkid"))
    if wkid not in (3857, 102100, 102113):
        return False
    if ti.get("rows") != 256 or ti.get("cols") != 256:
        return False
    origin = ti.get("origin") or {}
    return (abs(origin.get("x", 0) + 20037508.342789244) < 2 and
            abs(origin.get("y", 0) - 20037508.342789244) < 2)


def tiles_from_bundle(bundle, origin_y, origin_x, z, bounds):
    if len(bundle) < HEADER_SIZE + INDEX_SIZE:
        raise ValueError("Truncated Compact V2 bundle")
    version, count = struct.unpack_from("<II", bundle, 0)
    if version != 3 or count != 16384:
        raise ValueError("Not an Esri Compact Cache V2 bundle")
    width = struct.unpack_from("<I", bundle, 60)[0]
    if width != INDEX_SIZE:
        raise ValueError("Malformed Compact V2 index")
    nw = xyz(bounds[0], bounds[3], z)
    se = xyz(bounds[2], bounds[1], z)
    for y in range(max(origin_y, min(nw[1], se[1])),
                   min(origin_y + 127, max(nw[1], se[1])) + 1):
        for x in range(max(origin_x, min(nw[0], se[0])),
                       min(origin_x + 127, max(nw[0], se[0])) + 1):
            relative = (y - origin_y) * 128 + (x - origin_x)
            value = struct.unpack_from("<Q", bundle, HEADER_SIZE + relative * 8)[0]
            offset = value & ((1 << 40) - 1)
            size = value >> 40
            if size == 0:
                continue
            if size > MAX_TILE_BYTES or offset < HEADER_SIZE + INDEX_SIZE:
                raise ValueError("Unsafe tile offset or size in cache bundle")
            if offset + size > len(bundle):
                raise ValueError("Tile data exceeds bundle boundary")
            raw = bundle[offset:offset + size]
            image_format = valid_tile(raw)
            if not image_format:
                raise ValueError("Invalid / non-256px tile content")
            yield z, x, y, image_format, raw


def import_tpkx(tpkx, output_root, layer_id, bounds, zoom_min, zoom_max,
                provenance):
    if layer_id not in ALLOWED_LAYERS:
        raise ValueError("Unrecognized protected native raster ID")
    if not (8 <= zoom_min <= zoom_max <= 18):
        raise ValueError("Invalid bounded zoom interval")
    if len(bounds) != 4 or not (-180 < bounds[0] < bounds[2] < 180 and
                                 -85 < bounds[1] < bounds[3] < 85):
        raise ValueError("Invalid target WGS84 bounds")
    for field in ("publisher", "sourceTitle", "sourceURL",
                  "licenseURL", "attribution", "verifiedOfflineReuse"):
        if not provenance.get(field):
            raise ValueError("Approved source provenance missing " + field)
    if provenance["verifiedOfflineReuse"] is not True:
        raise ValueError("Offline redistribution has not been approved")
    if not tpkx.is_file() or not zipfile.is_zipfile(tpkx):
        raise ValueError("Local TPKX ZIP file required")
    source_hash = hashlib.sha256(tpkx.read_bytes()).hexdigest()
    report_path = output_root / f"{layer_id}.sources.json"
    if report_path.exists():
        raise FileExistsError("Refuse to overwrite prior provenance")
    planned = []
    with zipfile.ZipFile(tpkx) as pkg:
        roots = [name for name in pkg.namelist() if name.endswith("root.json")]
        if len(roots) != 1:
            raise ValueError("Unambiguous TPKX root.json required")
        root = json.loads(pkg.read(roots[0]))
        if not web_mercator_256(root):
            raise ValueError("TPKX is not 256px global Web Mercator XYZ")
        for entry in pkg.infolist():
            m = BUNDLE_RE.search(entry.filename)
            if not m:
                continue
            zstr, yhex, xhex = m.groups()
            zoom = int(zstr, 10) if zstr.isdecimal() else int(zstr, 16)
            if not (zoom_min <= zoom <= zoom_max):
                continue
            orig_y, orig_x = int(yhex, 16), int(xhex, 16)
            for z, x, y, image_format, raw in tiles_from_bundle(
                pkg.read(entry), orig_y, orig_x, zoom, bounds
            ):
                relative = f"{layer_id}/{z}/{x}/{y}.{image_format}"
                planned.append((relative, raw))
    if not planned:
        raise ValueError("TPKX has no approved tiles inside requested region")
    # A complete v4 map may combine several county packages. Reject
    # contradictions and preserve existing exact matching bytes.
    for rel, raw in planned:
        dest = output_root / rel
        if dest.is_file() and dest.read_bytes() != raw:
            raise ValueError("Conflicting county overlap: " + rel)
        if dest.with_suffix(".jpg" if dest.suffix == ".png" else ".png").exists():
            raise ValueError("Mixed image formats in tile overlap")
    for rel, raw in planned:
        dest = output_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(raw)
    record = {
        "layerID": layer_id, "sourceSHA256": source_hash,
        "sourceFilename": tpkx.name, "tileCountRead": len(planned),
        "boundsWGS84": bounds, "zoomMin": zoom_min, "zoomMax": zoom_max,
        "source": provenance,
        "result": "LOCAL IMPORT ONLY, NOT complete-v4 coverage or permission to deploy",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tpkx", required=True, type=Path)
    p.add_argument("--approved-xyz-root", required=True, type=Path)
    p.add_argument("--layer-id", required=True, choices=sorted(ALLOWED_LAYERS))
    p.add_argument("--bbox", required=True, type=float, nargs=4,
                   metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    p.add_argument("--min-zoom", type=int, default=10)
    p.add_argument("--max-zoom", type=int, default=16)
    p.add_argument("--approved-provenance", required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(import_tpkx(
        a.tpkx, a.approved_xyz_root, a.layer_id,
        a.bbox, a.min_zoom, a.max_zoom,
        json.loads(a.approved_provenance.read_text())
    ), indent=2))
