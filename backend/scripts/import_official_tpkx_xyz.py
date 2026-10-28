#!/usr/bin/env python3
"""Import LOCAL, rights-reviewed Esri TPKX Compact Cache V2 tiles into XYZ.

No network access; no tile synthesis, reprojection, resampling, or deployment.
Each official county package must be downloaded separately with approved
reuse/attribution. Output is suitable as ONE named layer input for the
schema-4 package builder, not proof that all five layers exist.

Reference: Esri/raster-tiles-compactcache CompactCacheV2.md (Apache-2.0).
"""
import argparse
import tempfile
import hashlib
import os
import json
from pathlib import Path
import re
import struct
import zipfile
from http_range_zip import RangeZipReader
from compact_v2_range_extract import select_xyz_tiles

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
# Keep the importer bounded before the later 1.5 GB schema-4 build.
MAX_STAGED_BYTES = 1_500_000_000


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


def web_mercator_256(root, required_levels):
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
    if not (abs(origin.get("x", 0) + 20037508.342789244) < 2 and
            abs(origin.get("y", 0) - 20037508.342789244) < 2):
        return False
    # A Web Mercator origin alone does not prove XYZ tile scale. An ArcGIS
    # cache may have custom/shifted LODs: explicitly reject mismatched
    # resolutions rather than misaligning trails and raster geography.
    lods = ti.get("lods") or []
    try:
        resolutions = {int(lod["level"]): float(lod["resolution"])
                       for lod in lods}
        return all(
            z in resolutions and
            abs(resolutions[z] / (156543.03392804097 / (2 ** z)) - 1) < 0.0001
            for z in required_levels
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def tiles_from_bundle(bundle, origin_y, origin_x, z, bounds):
    if len(bundle) < HEADER_SIZE + INDEX_SIZE:
        raise ValueError("Truncated Compact V2 bundle")
    version, count = struct.unpack_from("<II", bundle, 0)
    # Kentucky's October-2026 published Powell TPKX uses CompactV2
    # version 3, but declares a zero record count in its bundle header.
    # This is an observed encoder variant (NOT permission to invent tiles):
    # the FULL fixed index still must be present and every requested tile
    # must pass the offset, size and 256px image checks below.
    if version != 3 or count not in (0, 16384):
        raise ValueError(
            f"Unsupported CompactV2 version/count: {version}/{count}"
        )
    if struct.unpack_from("<I", bundle, 12)[0] != 5:
        raise ValueError("Invalid 5-byte offset declaration")
    if struct.unpack_from("<Q", bundle, 32)[0] != 40:
        raise ValueError("Invalid bundle user-header offset")
    if struct.unpack_from("<I", bundle, 40)[0] != (20 + INDEX_SIZE):
        raise ValueError("Invalid bundle user-header width")
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
                provenance, max_remote_bytes=1_500_000_000):
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
    remote = isinstance(tpkx, str)
    if remote:
        # For approved official Box packages, do not pull 4-40 GB just
        # to calculate the SHA. Authenticate the extracted map tiles in
        # the v4 package separately; retain honest remote metadata.
        source = RangeZipReader(
            tpkx, max_transfer_bytes=max_remote_bytes
        )
        source_hash = hashlib.sha256((
            source.url + "\n" + str(source.length) + "\n" +
            str(source.etag)
        ).encode()).hexdigest()
        source_name = tpkx.rsplit("/", 1)[-1]
    else:
        if not tpkx.is_file() or not zipfile.is_zipfile(tpkx):
            raise ValueError("Local TPKX ZIP file required")
        source_digest = hashlib.sha256()
        with tpkx.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                source_digest.update(chunk)
        source_hash = source_digest.hexdigest()
        source_name = tpkx.name
        source = tpkx
    report_path = output_root / f"{layer_id}.sources.json"
    existing_report = None
    if report_path.exists():
        existing_report = json.loads(report_path.read_text())
        if existing_report.get("layerID") != layer_id:
            raise ValueError("Inconsistent source-report layer")
        if any(item.get("sourceIdentity") == source_hash
               for item in existing_report.get("imports", [])):
            raise ValueError("Source TPKX already imported; immutable replay refused")
        if (existing_report.get("boundsWGS84") != bounds or
            existing_report.get("zoomMin") != zoom_min or
            existing_report.get("zoomMax") != zoom_max):
            raise ValueError("Cannot mix different geographic coverage contracts")
    # Spool tiles to an anonymous disk file, not a RAM list of image bytes.
    # ZIP integrity/overlaps are checked before any destination tile is added.
    planned = []  # (relative_path, offset, byte_count)
    spool = tempfile.TemporaryFile(mode="w+b")
    bundle_stats = []
    with zipfile.ZipFile(source) as pkg:
        roots = [name for name in pkg.namelist() if name.endswith("root.json")]
        if len(roots) != 1:
            raise ValueError("Unambiguous TPKX root.json required")
        root = json.loads(pkg.read(roots[0]))
        if not web_mercator_256(root, range(zoom_min, zoom_max + 1)):
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
            # County archives can contain thousands of CompactV2 bundles.
            # Test geographic intersection BEFORE fetching the 131 KiB
            # index (or decompressing a bundle). A bundle is 128x128 XYZ
            # tiles at this level. This is an exact integer tile test:
            # no geometry or image is synthesized or discarded in-bounds.
            nw = xyz(bounds[0], bounds[3], zoom)
            se = xyz(bounds[2], bounds[1], zoom)
            min_x, max_x = sorted((nw[0], se[0]))
            min_y, max_y = sorted((nw[1], se[1]))
            if (orig_x > max_x or orig_x + 127 < min_x or
                    orig_y > max_y or orig_y + 127 < min_y):
                continue
            if entry.file_size > 350_000_000:
                raise ValueError("Unexpectedly large source cache bundle")
            bundle_stats.append({
                "zoom": zoom, "entry": entry.filename,
                "zipMethod": entry.compress_type,
                "uncompressedBytes": entry.file_size,
                "compressedBytes": entry.compress_size,
            })
            # Official TPKX ZIP entries are usually STORED. Read only
            # the 128x128 index and selected image offsets using bounded
            # HTTP ranges, NOT the entire many-megabyte bundle.
            if remote and entry.compress_type == zipfile.ZIP_STORED:
                selected = select_xyz_tiles(
                    source, entry, orig_y, orig_x, zoom, bounds,
                    xyz, valid_tile
                )
            else:
                # Local files and uncommon compressed bundles retain full
                # native CompactV2 verification; remote compressed entries
                # remain limited by the per-source transfer byte budget.
                selected = tiles_from_bundle(
                    pkg.read(entry), orig_y, orig_x, zoom, bounds
                )
            for z, x, y, image_format, raw in selected:
                relative = f"{layer_id}/{z}/{x}/{y}.{image_format}"
                if spool.tell() + len(raw) > MAX_STAGED_BYTES:
                    raise ValueError("Source intake exceeds bounded staging budget")
                offset = spool.tell()
                spool.write(raw)
                planned.append((relative, offset, len(raw)))
    if not planned:
        raise ValueError("TPKX has no approved tiles inside requested region")
    # A complete v4 map may combine several county packages. Reject
    # contradictions and preserve existing exact matching bytes.
    # Official KyFromAbove TPKX uses MIXED JPEG/PNG imagery by zoom.
    # Preserve each source image's original bytes and exact tile extension,
    # never recompress, rescale, or pretend a new image exists.
    for rel, offset, byte_count in planned:
        spool.seek(offset)
        raw = spool.read(byte_count)
        if len(raw) != byte_count:
            raise ValueError("Truncated staged source tile")
        dest = output_root / rel
        if dest.is_file() and dest.read_bytes() != raw:
            raise ValueError("Conflicting county overlap: " + rel)
        if any(dest.with_suffix(ext).exists()
               for ext in (".png", ".jpg", ".jpeg")
               if ext != dest.suffix.lower()):
            raise ValueError("Conflicting image formats for the same XYZ tile")
    for rel, offset, byte_count in planned:
        dest = output_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            spool.seek(offset)
            raw = spool.read(byte_count)
            if len(raw) != byte_count:
                raise ValueError("Truncated staged source tile")
            # Stage destination creation to a temporary name and replace only
            # an absent tile; existing approved originals are not overwritten.
            with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".pending",
                                             delete=False) as scratch:
                scratch.write(raw)
                staged = Path(scratch.name)
            try:
                # Link-to-new destination fails rather than overwrite a file
                # that appeared between conflict check and promotion.
                os.link(staged, dest)
            except FileExistsError:
                if dest.read_bytes() != raw:
                    raise ValueError("Concurrent conflicting county tile: " + rel)
            finally:
                staged.unlink(missing_ok=True)
    record = {
        "layerID": layer_id, "boundsWGS84": bounds,
        "zoomMin": zoom_min, "zoomMax": zoom_max,
        "imports": (existing_report or {}).get("imports", []) + [{
            "sourceIdentity": source_hash,
            "sourceIdentityMethod": ("URL+length+ETag" if remote
                                     else "verified-full-archive-SHA256"),
            "sourceArchiveSHA256": None if remote else source_hash,
            "sourceFilename": source_name,
            "sourceRangeProvenance": source.provenance if remote else None,
            "tileCountRead": len(planned), "bundleReadStats": bundle_stats,
            "source": provenance,
        }],
        "result": "LOCAL IMPORT ONLY, NOT complete-v4 coverage or permission to deploy",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(".pending")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(report_path)
    spool.close()
    if remote:
        source.close()
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--tpkx", type=Path,
                        help="Already-downloaded approved local TPKX")
    choice.add_argument("--tpkx-url",
                        help="Official ky.box.com URL, selective HTTP 206 ranges")
    p.add_argument("--approved-xyz-root", required=True, type=Path)
    p.add_argument("--layer-id", required=True, choices=sorted(ALLOWED_LAYERS))
    p.add_argument("--bbox", required=True, type=float, nargs=4,
                   metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    p.add_argument("--min-zoom", type=int, default=10)
    p.add_argument("--max-zoom", type=int, default=16)
    p.add_argument("--approved-provenance", required=True, type=Path)
    p.add_argument("--max-remote-bytes", type=int, default=1_500_000_000)
    a = p.parse_args()
    print(json.dumps(import_tpkx(
        a.tpkx_url or a.tpkx, a.approved_xyz_root, a.layer_id,
        a.bbox, a.min_zoom, a.max_zoom,
        json.loads(a.approved_provenance.read_text()),
        max_remote_bytes=a.max_remote_bytes
    ), indent=2))
