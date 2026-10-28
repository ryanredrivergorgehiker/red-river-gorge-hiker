#!/usr/bin/env python3
"""ONE genuine two-source Kentucky Phase3 aerial mosaic into XYZ QA.

Tests a known z16 COG boundary, preserving year/source provenance. All pixel
reads are HTTP206 through two localhost-only proxies sharing ONE hard 64 MB
transfer budget. No protected Base export, whole-TIFF download, final atlas,
invented details, or production mutation.
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
from urllib.parse import urlparse

from http_range_zip import RangeZipReader
from pilot_official_cog_xyz import (
    HOST, COG_HOST, MAX_TRANSFER, RangeBudget, mercator_bounds,
    proxy_handler, verify_derived_grid,
)

ZOOM = 16
X = 17521
Y = 25359
EXPECTED = {
    "N119E344_2024_Season1_3IN_cog.tif",
    "N119E345_2023_Season2_3IN_cog.tif",
}


def approved_sources(mosaic_plan):
    if (mosaic_plan.get("status") !=
            "SOURCE-FOOTPRINT MOSAIC PLAN ONLY — NOT MAP TILES OR SIGNED BASE"
            or mosaic_plan.get("noImageryDownloaded") is not True
            or mosaic_plan.get("mustMosaicEveryIntersectingCOG") is not True):
        raise ValueError("Only complete known original Kentucky mosaic plan")
    kinds = [r for r in mosaic_plan.get("results", [])
             if r.get("kind") == "leaf-off-ortho-candidate"]
    if len(kinds) != 1 or kinds[0].get("collection") is None:
        raise ValueError("Missing unambiguous Kentucky leaf-off source role")
    source = kinds[0]
    if not ("phase3" in source["collection"].lower()):
        raise ValueError("Only original Kentucky Phase3 coverage for pilot")
    addresses = [t for t in source["plannedTiles"]
                 if (t.get("z"), t.get("x"), t.get("y")) == (ZOOM, X, Y)]
    if len(addresses) != 1 or set(addresses[0].get("cogs", [])) != EXPECTED:
        raise ValueError("Source footprint changed or boundary coverage incomplete")
    origins = []
    for name in sorted(EXPECTED):
        item = source["sourceCatalog"].get(name)
        if not isinstance(item, dict):
            raise ValueError("Missing exact Kentucky original source COG")
        uri = item.get("url")
        parsed = urlparse(uri or "")
        if (parsed.scheme != "https" or parsed.hostname != COG_HOST or
                not parsed.path.startswith("/imagery/orthos/Phase3/") or
                not parsed.path.lower().endswith(".tif") or
                parsed.query or parsed.fragment):
            raise ValueError("Unapproved source URL in geographic mosaic")
        origins.append({"name": name, "url": uri,
                        "bbox": item.get("bbox")})
    return origins


def run_pilot(plan, output_root):
    origins = approved_sources(plan)
    output = output_root / f"leaf-off-aerial/{ZOOM}/{X}/{Y}.jpg"
    provenance = output_root / "TWO-SOURCE-COG-MOSAIC-QA.json"
    if output.exists() or provenance.exists():
        raise FileExistsError("Never overwrite existing verified original-source QA")
    budget = RangeBudget(MAX_TRANSFER)
    servers, threads = [], []
    resolved = []
    try:
        for origin in origins:
            # One actual byte-range request to validate each source's size/ETag.
            with RangeZipReader(origin["url"], source_kind="kentucky_cog",
                                chunk_size=65536, max_cache_chunks=1,
                                max_transfer_bytes=131072) as source:
                resolved.append({
                    **origin, "length": source.length,
                    "etag": source.etag,
                })
                budget.reserve(source.transfer_bytes)
        local_uris = []
        for source in resolved:
            srv = ThreadingHTTPServer(
                (HOST, 0), proxy_handler(source, budget)
            )
            srv.daemon_threads = True
            worker = Thread(target=srv.serve_forever, daemon=True)
            worker.start()
            servers.append(srv)
            threads.append(worker)
            local_uris.append(
                f"/vsicurl/http://{HOST}:{srv.server_port}/source.tif"
            )
        env = dict(os.environ,
                   GDAL_DISABLE_READDIR_ON_OPEN="YES",
                   CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                   CPL_VSIL_CURL_USE_HEAD="YES",
                   CPL_VSIL_CURL_CHUNK_SIZE="16384",
                   CPL_VSIL_CURL_CACHE_SIZE="262144",
                   GDAL_HTTP_MAX_RETRY="0",
                   GDAL_HTTP_TIMEOUT="12",
                   GDAL_CACHEMAX="64")
        bounds = mercator_bounds(X, Y, ZOOM)
        with tempfile.TemporaryDirectory(prefix="rrgh-ky-mosaic-qa-") as root:
            root = Path(root)
            vrt = root / "two-original-sources.vrt"
            tiff = root / "one-xyz-warped.tif"
            subprocess.run([
                "gdalbuildvrt", "-q", "-overwrite", "-resolution", "highest",
                "-addalpha", str(vrt), *local_uris,
            ], env=env, check=True, timeout=90, capture_output=True)
            subprocess.run([
                "gdalwarp", "-q", "-overwrite",
                "-t_srs", "EPSG:3857", "-te", *map(str, bounds),
                "-ts", "256", "256", "-r", "bilinear",
                "-dstalpha", "-wm", "32", "-wo", "NUM_THREADS=1",
                "-of", "GTiff", str(vrt), str(tiff),
            ], env=env, check=True, timeout=120, capture_output=True)
            check = subprocess.run([
                "gdalinfo", "-json", "-stats", str(tiff),
            ], check=True, capture_output=True, timeout=40)
            info = json.loads(check.stdout)
            geographic = verify_derived_grid(info, bounds)
            bands = info.get("bands", [])
            if len(bands) < 4:
                raise ValueError("Mosaic lacks raster coverage alpha channel")
            alpha = (bands[3].get("metadata") or {}).get("", {})
            alpha_min = alpha.get("STATISTICS_MINIMUM")
            if alpha_min is None or float(alpha_min) < 255:
                raise ValueError("Mosaic has missing pixels; cannot present as full XYZ")
            output.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "gdal_translate", "-q", "-of", "JPEG",
                "-b", "1", "-b", "2", "-b", "3",
                "-co", "QUALITY=90", str(tiff), str(output),
            ], check=True, capture_output=True, timeout=35)
            if output.stat().st_size < 2048:
                raise ValueError("Aerial mosaic JPEG is suspiciously empty")
            manifest = {
                "status": "ONE VERIFIED TWO-COG GEOREFERENCED MOSAIC PILOT ONLY",
                "sourceRoles": ["leaf-off-aerial"],
                "originalCOGs": [
                    {"name": s["name"], "url": s["url"],
                     "sourceBytes": s["length"], "etag": s["etag"]}
                    for s in resolved],
                "sourceYears": [2024, 2023],
                "sourceSeamAcceptance": "Mosaic pixel coverage verified, seam visual parity NOT owner accepted",
                "xyz": {"z": ZOOM, "x": X, "y": Y},
                "boundsEPSG3857": bounds,
                "output": output.relative_to(output_root).as_posix(),
                "outputSha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "outputByteLength": output.stat().st_size,
                "rasterQA": geographic,
                "alphaMin": float(alpha_min),
                "http206RangeRequests": budget.calls,
                "http206SourceTransferBytes": budget.used,
                "maxSourceTransferBudget": MAX_TRANSFER,
                "originalCOGDownloaded": False,
                "productionOrFullBaseReady": False,
                "derivedResampling": "GDAL Phase3 COG mosaic to EPSG3857/256px",
            }
            provenance.write_text(json.dumps(manifest, indent=2) + "\n")
            return manifest
    finally:
        for srv in servers:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mosaic-plan", required=True, type=Path)
    p.add_argument("--pilot-root", required=True, type=Path)
    a = p.parse_args()
    result = run_pilot(json.loads(a.mosaic_plan.read_text()), a.pilot_root)
    print(json.dumps({
        "status": result["status"], "xyz": result["xyz"],
        "rangeBytes": result["http206SourceTransferBytes"],
        "requests": result["http206RangeRequests"],
        "alphaMin": result["alphaMin"],
    }, indent=2))
