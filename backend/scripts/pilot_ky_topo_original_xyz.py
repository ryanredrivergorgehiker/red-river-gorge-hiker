#!/usr/bin/env python3
"""ONE original KyTopo COG -> georeferenced z16 XYZ QA tile, max 32 MB HTTP206.

Original is an S3 COG, selected through the official nine-quad index and
complete public S3 listing. This creates a new 256px derivative, not a final
offline hiking map, consumer archive, source-TIFF download, or entitlement.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Thread
from http.server import ThreadingHTTPServer

from pilot_official_cog_xyz import (
    HOST, COG_HOST, RangeBudget, proxy_handler, mercator_bounds,
    verify_derived_grid, xyz,
)

QUAD = "N14E30"
MAX_SOURCE_BYTES = 32_000_000
LON, LAT, ZOOM = -83.575, 37.795, 16


def source(index, quad_id=QUAD):
    if (index.get("status") !=
            "OFFICIAL GORGE-INTERSECTING KYTOPO QUAD METADATA ONLY"
            or index.get("allOriginalKeysInS3") is not True
            or index.get("rasterBytesFetched") != 0):
        raise ValueError("Only complete official Gorge KyTopo COG inventory")
    matches = [q for q in index.get("quadrangles", []) if q.get("id") == quad_id]
    if len(matches) != 1:
        raise ValueError("Expected one unique original KyTopo source")
    q = matches[0]
    uri = q.get("officialOriginalCogURL")
    exact = "https://" + COG_HOST + "/elevation/KyTopoMapSeries/COGs/"
    if (not isinstance(uri, str) or not uri.startswith(exact)
            or not uri.endswith("_cog.tif")
            or quad_id + "_" not in uri or q.get("inOfficialS3Listing") is not True
            or q.get("sourceSelection") != "exact-current-cog-in-official-s3"):
        raise ValueError("Missing expected verified original current topographic GeoTIFF")
    b = q.get("boundsWGS84")
    if not b or len(b) != 4 or not (b[0] < b[2] and b[1] < b[3]):
        raise ValueError("Missing original source quadrangle geometry")
    if quad_id == QUAD and not (b[0] < LON < b[2] and b[1] < LAT < b[3]):
        raise ValueError("Original Pine Ridge sample point outside source quad")
    length = q.get("officialOriginalSourceBytes")
    if not isinstance(length, int) or not (1_000_000 < length < 1_000_000_000):
        raise ValueError("No original S3 byte-length evidence")
    return {"url": uri, "length": length, "sourceQuad": quad_id,
            "quadName": q["quadrangle"], "etag": None}


def pilot(index, out, quad_id=QUAD, byte_budget=MAX_SOURCE_BYTES):
    original = source(index, quad_id)
    bb = next(q["boundsWGS84"] for q in index["quadrangles"] if q["id"] == quad_id)
    region = index["boundsWGS84"]
    clip = [max(bb[0], region[0]), max(bb[1], region[1]),
            min(bb[2], region[2]), min(bb[3], region[3])]
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        raise ValueError("Source quadrangle does not intersect Gorge region")
    lon, lat = (LON, LAT) if quad_id == QUAD else (
        (clip[0]+clip[2])/2, (clip[1]+clip[3])/2)
    x, y = xyz(lon, lat, ZOOM)
    target = out / f"kentucky-topo/{ZOOM}/{x}/{y}.jpg"
    evidence = out / "KYTOPO-ORIGINAL-COG-ONE-TILE-QA.json"
    if target.exists() or evidence.exists():
        raise FileExistsError("Never replace previous original-source QA")
    if not 1_000_000 <= byte_budget <= MAX_SOURCE_BYTES:
        raise ValueError("Pilot source-transfer cap must be bounded")
    budget = RangeBudget(byte_budget)
    srv = ThreadingHTTPServer((HOST, 0), proxy_handler(original, budget))
    srv.daemon_threads = True
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    location = f"/vsicurl/http://{HOST}:{srv.server_port}/source.tif"
    bbox = mercator_bounds(x, y, ZOOM)
    env = dict(os.environ,
               GDAL_DISABLE_READDIR_ON_OPEN="YES",
               CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
               CPL_VSIL_CURL_USE_HEAD="YES",
               CPL_VSIL_CURL_CHUNK_SIZE="16384",
               CPL_VSIL_CURL_CACHE_SIZE="262144",
               GDAL_HTTP_MAX_RETRY="0",
               GDAL_HTTP_TIMEOUT="12",
               GDAL_CACHEMAX="64")
    try:
        with tempfile.TemporaryDirectory(prefix="rrgh-kytopo-z16-") as tmp:
            raster = Path(tmp) / "authentic-kytopo-3857.tif"
            subprocess.run([
                "gdalwarp", "-q", "-overwrite", "-of", "GTiff",
                "-t_srs", "EPSG:3857", "-te", *map(str, bbox),
                "-ts", "256", "256", "-dstalpha", "-r", "bilinear",
                "-wm", "32", "-wo", "NUM_THREADS=1", location, str(raster),
            ], env=env, check=True, timeout=120, capture_output=True)
            info = json.loads(subprocess.run(
                ["gdalinfo", "-json", "-stats", str(raster)],
                check=True, capture_output=True, timeout=35,
            ).stdout)
            geographic = verify_derived_grid(info, bbox)
            alpha = [band for band in info.get("bands", [])
                     if band.get("colorInterpretation") == "Alpha"]
            if len(alpha) != 1:
                raise ValueError("No single verified topographic raster alpha band")
            minimum = alpha[0].get("metadata", {}).get("", {}).get("STATISTICS_MINIMUM")
            if minimum is None or float(minimum) < 255:
                raise ValueError("Topographic source tile is incomplete at this location")
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "gdal_translate", "-q", "-of", "JPEG", "-b", "1", "-b", "2",
                "-b", "3", "-co", "QUALITY=90", str(raster), str(target),
            ], check=True, capture_output=True, timeout=35)
        if target.stat().st_size < 1200:
            raise ValueError("Generated KyTopo map tile may be blank")
        report = {
            "status": "ONE ORIGINAL KYTOPO-SOURCED GEOREFERENCED XYZ QA ONLY",
            "original": original,
            "sampleWGS84": [lon, lat],
            "originalTiffDownloaded": False,
            "derivedImageFormat": "JPEG",
            "xyz": {"z": ZOOM, "x": x, "y": y},
            "derivedImageBytes": target.stat().st_size,
            "derivedSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "sourceBytesTransferred": budget.used,
            "sourcePartialRequests": budget.calls,
            "maxSourceTransfer": byte_budget,
            "alphaMin": float(minimum),
            "rasterQA": geographic,
            "noRegionalCoverageOrFieldAcceptance": True,
            "geoProcess": "GDAL bilinear reprojection of original KyTopo to XYZ EPSG3857",
        }
        evidence.write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gorge-kytopo", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--quad-id", default=QUAD)
    p.add_argument("--byte-limit", type=int, default=MAX_SOURCE_BYTES)
    a = p.parse_args()
    r = pilot(json.loads(a.gorge_kytopo.read_text()), a.out,
              a.quad_id, a.byte_limit)
    print(json.dumps({k: r[k] for k in ("status", "xyz",
                                         "sourceBytesTransferred",
                                         "derivedImageBytes", "alphaMin")}, indent=2))
