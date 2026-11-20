#!/usr/bin/env python3
"""Create ONE true georeferenced original-source Kentucky COG XYZ QA tile.

This is private source-development QA, NOT a Base map package. A localhost-only
proxy forwards strictly bounded HTTP206 byte ranges to an approved official
Kentucky COG. GDAL works with the proxy URL, never the full remote 1GB asset.
The 256px XYZ tile is a declared GDAL reprojection DERIVATIVE, not a
byte-identical copy of the original GeoTIFF and not invented source detail.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import subprocess
from threading import Lock, Thread
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
MAX_TRANSFER = 64_000_000
MAX_REQUEST = 2_000_000
MAX_REQUESTS = 400
RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")
RESPONSE_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
COG_HOST = "kyfromabove.s3.us-west-2.amazonaws.com"


def xyz(lon, lat, zoom):
    if not (10 <= zoom <= 16 and -83.81 <= lon <= -83.39
            and 37.64 <= lat <= 37.96):
        raise ValueError("Only bounded Gorge source-pilot XYZ camera allowed")
    n = 2 ** zoom
    t = math.radians(lat)
    return int((lon + 180) / 360 * n), int(
        (1 - math.log(math.tan(t) + 1 / math.cos(t)) / math.pi) / 2 * n
    )


def mercator_bounds(x, y, zoom):
    # EPSG:3857 meters for exactly ONE full 256px XYZ tile.
    n = 2 ** zoom
    circumference = 40075016.68557849
    return [
        (x / n - 0.5) * circumference,
        (0.5 - (y + 1) / n) * circumference,
        ((x + 1) / n - 0.5) * circumference,
        (0.5 - y / n) * circumference,
    ]


def select(stac, headers, geotiff):
    if not (stac.get("noImageryDownloaded") is True and
            geotiff.get("status", "").startswith("BOUNDED ORIGINAL GEOTIFF IFD")):
        raise ValueError("Provenanced Kentucky source chain is missing")
    header_lookup = {v.get("url"): v for v in headers.get("assets", [])}
    geo_lookup = {v.get("url"): v for v in geotiff.get("assets", [])}
    for group in stac.get("results", []):
        if group.get("kind") != "leaf-off-ortho-candidate":
            continue
        for item in group.get("candidates", []):
            bbox = item.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            for asset in item.get("assets", []):
                uri = asset.get("href")
                u = urlparse(uri or "")
                if (u.scheme != "https" or u.hostname != COG_HOST or
                        not u.path.startswith("/imagery/orthos/Phase3/") or
                        not u.path.lower().endswith(".tif") or u.query):
                    continue
                header = header_lookup.get(uri)
                metadata = geo_lookup.get(uri, {}).get("metadata", {})
                if not header or header.get("tiffHeaderConfirmed") is not True:
                    continue
                if not (metadata.get("georeferenceTagEvidence") is True and
                        metadata.get("internalTiled") is True and
                        metadata.get("projectedOrGeographicEPSG") == 3089):
                    continue
                return {"url": uri, "itemID": item.get("itemID"), "bbox": bbox,
                        "length": int(header["fileByteLength"]),
                        "etag": header.get("etag"),
                        "sourceWidth": metadata.get("sourceWidthPixels"),
                        "sourceHeight": metadata.get("sourceHeightPixels"),
                        "nativePixelScale": metadata.get("pixelScaleNativeCRSUnits")}
    raise ValueError("No SHA/provenance-linked actual Kentucky Phase3 ortho COG")


class RangeBudget:
    def __init__(self, limit=MAX_TRANSFER):
        self.limit = limit
        self.used = 0
        self.calls = 0
        self.lock = Lock()

    def reserve(self, amount):
        with self.lock:
            if (amount < 1 or amount > MAX_REQUEST or self.calls >= MAX_REQUESTS
                    or self.used + amount > self.limit):
                return False
            self.calls += 1
            self.used += amount
            return True


def proxy_handler(origin, budget, opener=urlopen):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            if self.path != "/source.tif":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/tiff")
            self.send_header("Content-Length", str(origin["length"]))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            if self.path != "/source.tif":
                self.send_error(404)
                return
            m = RANGE.fullmatch(self.headers.get("Range", ""))
            if not m:
                self.send_error(416, "No unbounded or multipart file reads")
                return
            start, end = map(int, m.groups())
            amount = end - start + 1
            if start < 0 or end >= origin["length"] or not budget.reserve(amount):
                self.send_error(416, "Per-request or cumulative source budget exceeded")
                return
            req = Request(origin["url"], headers={
                "Range": f"bytes={start}-{end}",
                "Accept-Encoding": "identity",
                "User-Agent": "RRGH-local-COG-pilot-proxy/1.0",
            })
            try:
                with opener(req, timeout=20) as upstream:
                    if upstream.status != 206:
                        raise ValueError("Official source HTTP206 required")
                    if urlparse(upstream.geturl()).hostname != COG_HOST:
                        raise ValueError("Unexpected redirect")
                    match = RESPONSE_RANGE.fullmatch(
                        upstream.headers.get("Content-Range", ""))
                    if not match or tuple(map(int, match.groups())) != (
                            start, end, origin["length"]):
                        raise ValueError("Original source Range or size changed")
                    etag = upstream.headers.get("ETag")
                    if origin.get("etag") and etag and origin["etag"] != etag:
                        raise ValueError("Original source ETag changed")
                    raw = upstream.read(amount + 1)
                    if len(raw) != amount:
                        raise ValueError("Truncated or oversized source range")
                self.send_response(206)
                self.send_header("Content-Type", "image/tiff")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range",
                                 f"bytes {start}-{end}/{origin['length']}")
                self.send_header("Content-Length", str(amount))
                self.end_headers()
                self.wfile.write(raw)
            except Exception:
                # Never substitute fake pixels or issue unbounded retries.
                self.send_error(502, "Official partial source read failed")
    return Handler


def verify_derived_grid(info, bounds):
    if info.get("size") != [256, 256]:
        raise ValueError("Derived offline raster is not exact 256x256")
    affine = info.get("geoTransform")
    if not isinstance(affine, list) or len(affine) != 6:
        raise ValueError("Derived XYZ raster lacks georeferencing")
    pixel = (bounds[2] - bounds[0]) / 256
    checks = [
        (affine[0], bounds[0]), (affine[3], bounds[3]),
        (affine[1], pixel), (affine[5], -pixel),
        (affine[2], 0), (affine[4], 0),
    ]
    if any(abs(float(actual) - expected) > 0.02 for actual, expected in checks):
        raise ValueError("Actual GDAL output is not aligned to requested XYZ grid")
    bands = info.get("bands") or []
    if len(bands) < 3:
        raise ValueError("Aerial output lacks source RGB")
    stdevs = []
    for band in bands[:3]:
        data = band.get("metadata", {})
        value = data.get("", {}).get("STATISTICS_STDDEV")
        if value is not None:
            stdevs.append(float(value))
    if len(stdevs) != 3 or max(stdevs) < 1:
        raise ValueError("Flat, black or statistically unverified aerial source")
    return {"pixelSizeEPSG3857": pixel, "rgbStddev": stdevs,
            "pixelAndGeographicAlignmentVerified": True}


def run_pilot(stac, headers, geotiff, out, zoom=16):
    origin = select(stac, headers, geotiff)
    bbox = origin["bbox"]
    lon, lat = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    x, y = xyz(lon, lat, zoom)
    output = out / f"leaf-off-aerial/{zoom}/{x}/{y}.jpg"
    report = out / "COG-PILOT-ONLY.json"
    if output.exists() or report.exists():
        raise FileExistsError("Never overwrite verified pilot source tiles")
    out.mkdir(parents=True, exist_ok=True)
    temp = out / "pilot-source-projected.tif"
    budget = RangeBudget()
    server = ThreadingHTTPServer((HOST, 0), proxy_handler(origin, budget))
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    addr = f"/vsicurl/http://{HOST}:{server.server_port}/source.tif"
    box = mercator_bounds(x, y, zoom)
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
        subprocess.run([
            "gdalwarp", "-q", "-overwrite", "-of", "GTiff",
            "-t_srs", "EPSG:3857", "-te", *map(str, box),
            "-ts", "256", "256", "-r", "bilinear",
            "-wm", "32", "-wo", "NUM_THREADS=1",
            addr, str(temp)
        ], env=env, check=True, timeout=110, capture_output=True)
        raster_info = subprocess.run(
            ["gdalinfo", "-json", "-stats", str(temp)],
            check=True, capture_output=True, timeout=35
        )
        qa = verify_derived_grid(json.loads(raster_info.stdout), box)
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "gdal_translate", "-q", "-of", "JPEG",
            "-b", "1", "-b", "2", "-b", "3",
            "-co", "QUALITY=90", str(temp), str(output)
        ], check=True, timeout=35, capture_output=True)
        if not output.is_file() or output.stat().st_size < 1024:
            raise ValueError("No nontrivial 256px aerial derivative")
        source_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        details = {
            "status": "ONE ORIGINAL-COG-SOURCED GEOREFERENCED XYZ DERIVATIVE — NOT FULL GORGE BASE",
            "originalSource": origin, "sourceFileNotDownloaded": True,
            "sourceRangeTransferBytes": budget.used,
            "sourceRangeRequests": budget.calls,
            "maxAllowedSourceTransfer": MAX_TRANSFER,
            "xyz": {"z": zoom, "x": x, "y": y},
            "tileBoundsEPSG3857": box,
            "derivedImageFormat": "JPEG",
            "resampling": "GDAL bilinear reprojection to EPSG3857; NO sharpening or invented data",
            "derivedImageBytes": output.stat().st_size,
            "derivedImageSha256": source_hash,
            "rasterQA": qa,
            "derivedImageRelativePath": output.relative_to(out).as_posix(),
            "notCustomerReady": True,
        }
        report.write_text(json.dumps(details, indent=2) + "\n")
        return details
    finally:
        server.shutdown()
        server.server_close()
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stac", type=Path, required=True)
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--geotiff", type=Path, required=True)
    p.add_argument("--pilot-root", type=Path, required=True)
    p.add_argument("--zoom", type=int, default=16)
    a = p.parse_args()
    result = run_pilot(json.loads(a.stac.read_text()),
                       json.loads(a.headers.read_text()),
                       json.loads(a.geotiff.read_text()),
                       a.pilot_root, a.zoom)
    print(json.dumps({"status": result["status"],
                      "xyz": result["xyz"],
                      "rangeBytes": result["sourceRangeTransferBytes"],
                      "sourceRequests": result["sourceRangeRequests"]}, indent=2))
