#!/usr/bin/env python3
"""Strict bounded HTTP Range COG header pilot from official Kentucky STAC.

Reads at most 4096 bytes each from two recognized Kentucky DEM/leaf-off
candidate assets. No pixel or complete TIFF downloads. TIFF signature does
NOT prove valid GeoTIFF, COG optimization, geolocation, rights or map quality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

STAC_API = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com"
COG_HOST = "kyfromabove.s3.us-west-2.amazonaws.com"
RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
READ_BYTES = 4096
MAX_SOURCES = 2
TIFF_MARKERS = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def check_url(uri):
    if not isinstance(uri, str):
        return False
    u = urlparse(uri)
    return (u.scheme == "https" and u.hostname == COG_HOST and
            not u.query and not u.fragment and u.port is None and
            u.path.lower().endswith((".tif", ".tiff")))


def official_candidates(report):
    if report.get("catalog") != STAC_API or report.get("noImageryDownloaded") is not True:
        raise ValueError("Only an original metadata-only official STAC intake is allowed")
    selected = []
    seen = set()
    for entry in report.get("results", []):
        kind = entry.get("kind")
        if kind not in ("terrain-dem-candidate", "leaf-off-ortho-candidate"):
            continue
        if kind in seen:
            continue
        for candidate in entry.get("candidates", []):
            for asset in candidate.get("assets", []):
                uri = asset.get("href")
                if not check_url(uri):
                    continue
                selected.append({"kind": kind, "sourceItem": candidate.get("itemID"),
                                 "sourceCollection": entry.get("collection"), "url": uri})
                seen.add(kind)
                break
            if kind in seen:
                break
        if len(selected) == MAX_SOURCES:
            break
    if not selected:
        raise ValueError("No approved-host candidate COGs to inspect")
    return selected


def probe_one(uri, opener=urlopen):
    if not check_url(uri):
        raise ValueError("Only official Kentucky original COG HTTPS assets")
    req = Request(uri, headers={
        "Range": f"bytes=0-{READ_BYTES - 1}",
        "Accept-Encoding": "identity",
        "User-Agent": "RRGH-official-COG-range-preflight/1.0",
    })
    with opener(req, timeout=20) as response:
        if response.status != 206:
            raise ValueError("Provider did not honor strict HTTP 206 partial read")
        if urlparse(response.geturl()).hostname != COG_HOST:
            raise ValueError("COG provider redirect outside official data host")
        value = response.headers.get("Content-Range", "")
        m = RANGE.fullmatch(value)
        if not m:
            raise ValueError("Missing or invalid Content-Range")
        begin, end, length = map(int, m.groups())
        if (begin != 0 or end != READ_BYTES - 1 or
                length < READ_BYTES or length > 30_000_000_000):
            raise ValueError("Provider returned wrong range/implausible source size")
        data = response.read(READ_BYTES + 1)
        if len(data) != READ_BYTES:
            raise ValueError("Truncated or oversized header response")
        etag = response.headers.get("ETag")
    if not any(data.startswith(t) for t in TIFF_MARKERS):
        raise ValueError("Official asset does not have TIFF/BigTIFF header")
    return {"fileByteLength": length, "rangedBytesRead": len(data),
            "headerSha256": hashlib.sha256(data).hexdigest(),
            "etag": etag, "tiffHeaderConfirmed": True,
            "cogLayoutGeorefResolutionVerified": False}


def probe_report(report, probe=probe_one):
    outputs = []
    for candidate in official_candidates(report):
        details = probe(candidate["url"])
        outputs.append({**candidate, **details})
    return {
        "status": "STRICT REAL RANGE-HEADER PILOT ONLY — NOT FULL IMAGE/COG VALIDATION",
        "count": len(outputs),
        "totalReadBytes": sum(item["rangedBytesRead"] for item in outputs),
        "assets": outputs,
        "next": "Verify GDAL COG internal tiling, actual CRS, extent, source GSD, rights before selective derived XYZ."
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-stac-report", type=Path, required=True)
    p.add_argument("--output-json", type=Path, required=True)
    args = p.parse_args()
    if args.output_json.exists():
        raise FileExistsError("Refuse to overwrite prior COG probe evidence")
    source = json.loads(args.official_stac_report.read_text())
    output = probe_report(source)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"count": output["count"],
                      "bytesRead": output["totalReadBytes"],
                      "status": output["status"]}, indent=2))
