#!/usr/bin/env python3
"""Inspect official Kentucky GeoTIFF geospatial IFD tags by bounded HTTP206.

Only small TIFF/BigTIFF directory tags are retrieved; NO imagery blocks or
large tile-offset arrays, no COG transcode/reprojection/map package creation.
This metadata probe cannot establish final source completeness or image quality.
"""
import argparse
import json
from pathlib import Path
import struct

from http_range_zip import RangeZipReader

MAX_REMOTE_BYTES = 8_000_000
MAX_IFD_ENTRIES = 256
MAX_TAG_BYTES = 8192
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4,
             12: 8, 16: 8, 17: 8, 18: 8}
TAGS = {256, 257, 259, 322, 323, 330, 33550, 33922, 34735, 34264}


def read_at(stream, offset, size):
    if size < 0 or size > MAX_TAG_BYTES:
        raise ValueError("Unsafe TIFF metadata tag read size")
    if offset < 0 or offset + size > stream.length:
        raise ValueError("TIFF source tag beyond original file length")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("TIFF source tag truncated")
    return data


def extract_tags(stream):
    header = read_at(stream, 0, 16)
    if header[:2] == b"II":
        order = "<"
    elif header[:2] == b"MM":
        order = ">"
    else:
        raise ValueError("Not a TIFF byte-order header")
    magic = struct.unpack(order + "H", header[2:4])[0]
    if magic == 42:
        big = False
        pointer = struct.unpack(order + "I", header[4:8])[0]
        count_bytes, entry_bytes, slot_bytes = 2, 12, 4
    elif magic == 43:
        if struct.unpack(order + "HH", header[4:8]) != (8, 0):
            raise ValueError("Invalid BigTIFF offset header")
        big = True
        pointer = struct.unpack(order + "Q", header[8:16])[0]
        count_bytes, entry_bytes, slot_bytes = 8, 20, 8
    else:
        raise ValueError("Invalid TIFF/BigTIFF magic")
    count = struct.unpack(order + ("Q" if big else "H"),
                          read_at(stream, pointer, count_bytes))[0]
    if not (1 <= count <= MAX_IFD_ENTRIES):
        raise ValueError("Unsafe original TIFF IFD count")
    entries = read_at(stream, pointer + count_bytes, count * entry_bytes)
    result = {}
    for i in range(count):
        entry = entries[i * entry_bytes:(i + 1) * entry_bytes]
        if big:
            tag, typ, items = struct.unpack_from(order + "HHQ", entry, 0)
            slot = entry[12:20]
        else:
            tag, typ, items = struct.unpack_from(order + "HHI", entry, 0)
            slot = entry[8:12]
        if tag not in TAGS:
            continue
        if typ not in TYPE_SIZE or items < 1 or items > 2048:
            raise ValueError("Invalid critical TIFF metadata tag type/count")
        length = TYPE_SIZE[typ] * items
        if length > MAX_TAG_BYTES:
            # Image tile offsets/byte-count arrays can be enormous. Their
            # values are deliberately NOT downloaded by this metadata probe.
            if tag == 330:
                result[tag] = {"deferredSubIFDCount": int(items)}
                continue
            raise ValueError("Critical geospatial metadata exceeds capped read")
        if length <= slot_bytes:
            data = slot[:length]
        else:
            pos = struct.unpack(order + ("Q" if big else "I"), slot)[0]
            data = read_at(stream, pos, length)
        if typ in (3, 4, 16):
            spec = {3: "H", 4: "I", 16: "Q"}[typ]
            values = struct.unpack(order + spec * items, data)
        elif typ == 12:
            values = struct.unpack(order + "d" * items, data)
        elif typ == 11:
            values = struct.unpack(order + "f" * items, data)
        else:
            continue
        result[tag] = list(values)
    return big, result


def describe(stream):
    big, tags = extract_tags(stream)
    def scalar(k):
        v = tags.get(k)
        return int(v[0]) if isinstance(v, list) and len(v) == 1 else None
    width, height = scalar(256), scalar(257)
    tile_w, tile_h = scalar(322), scalar(323)
    scale, tie = tags.get(33550), tags.get(33922)
    keys = tags.get(34735) or []
    epsg = None
    if len(keys) >= 4:
        declared = int(keys[3])
        if len(keys) != 4 + declared * 4:
            raise ValueError("Malformed GeoTIFF GeoKeyDirectory")
        for i in range(4, len(keys), 4):
            key_id, location, item_count, val = map(int, keys[i:i+4])
            if key_id in (3072, 2048) and location == 0 and item_count == 1:
                epsg = val
    geo = (isinstance(scale, list) and len(scale) >= 2 and
           isinstance(tie, list) and len(tie) >= 6 and
           scale[0] > 0 and scale[1] > 0 and epsg is not None)
    if width is None or height is None or width <= 0 or height <= 0:
        raise ValueError("Missing or invalid source raster dimensions")
    return {
        "isBigTiff": big, "sourceWidthPixels": width,
        "sourceHeightPixels": height,
        "internalTiled": bool(tile_w and tile_h),
        "internalTileWidth": tile_w, "internalTileHeight": tile_h,
        "compressionCode": scalar(259),
        "projectedOrGeographicEPSG": epsg,
        "pixelScaleNativeCRSUnits": scale[:2] if isinstance(scale, list) else None,
        "tiepointNativeCRS": tie[:6] if isinstance(tie, list) else None,
        "georeferenceTagEvidence": geo,
        "sourceImageryPixelsRetrieved": False,
        "fullCOGConformanceCoverageAndRightsVerified": False,
    }


def inspect_report(header_report, open_reader=RangeZipReader):
    out = []
    for rec in header_report.get("assets", []):
        if rec.get("tiffHeaderConfirmed") is not True:
            raise ValueError("Unverified official TIFF source")
        uri = rec["url"]
        with open_reader(uri, source_kind="kentucky_cog", chunk_size=65_536,
                         max_cache_chunks=8, max_transfer_bytes=MAX_REMOTE_BYTES) as source:
            details = describe(source)
            receipt = source.provenance
        out.append({
            "sourceItem": rec["sourceItem"], "kind": rec["kind"],
            "sourceCollection": rec["sourceCollection"], "url": uri,
            "metadata": details, "rangeProvenance": receipt,
        })
    return {
        "status": "BOUNDED ORIGINAL GEOTIFF IFD PROBE — NOT SOURCE COVERAGE OR OFFLINE PACKAGE",
        "assets": out, "count": len(out),
        "totalDownloadedBytes": sum(x["rangeProvenance"]["rangeBytesTransferred"]
                                    for x in out),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-header-report", required=True, type=Path)
    p.add_argument("--output-json", required=True, type=Path)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Never overwrite source geotiff intake report")
    result = inspect_report(json.loads(a.official_header_report.read_text()))
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"],
                      "count": result["count"],
                      "rangeBytes": result["totalDownloadedBytes"]}, indent=2))
