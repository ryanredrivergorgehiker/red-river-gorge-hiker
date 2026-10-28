#!/usr/bin/env python3
"""Resumable, original-source multi-layer benchmark; never a deploy command.

One z18-resolution metatile generates identical-ground z16/17/18 pyramids.
Original HTTP ranges persist across jobs; DEM is reused for relief and the
existing accepted sunlight algorithm. Outputs are explicitly NOT installable.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import platform
import time
import tarfile
import traceback

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from pyproj import CRS

from cached_cog_source import Cache, atomic, digest
from build_gorge_base_native_v4 import xy
from pilot_official_cog_xyz import mercator_bounds

VERSION = "rrgh-multilayer-benchmark-v1"
AOI = [-83.80, 37.65, -83.40, 37.95]
REPO = Path(__file__).resolve().parents[2]
ROLES = ("hiking", "terrain", "sunlight", "leaf-on", "leaf-off")
SUN_PATH = REPO / "scripts/generate-rrg-lidar-sun.py"
PRESENTATION_PATH = REPO / "scripts/generate-rrg-lidar-sun-continuous.py"


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def receipt_valid(root, receipt, recipe):
    if receipt.get("recipeSHA256") != recipe or not receipt.get("validated"):
        raise ValueError("Recipe changed or incomplete receipt; use a new run directory")
    for item in receipt["outputs"]:
        path = root / item["path"]
        if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve())
                or path.stat().st_size != item["bytes"] or digest(path.read_bytes()) != item["sha256"]):
            raise ValueError("Output integrity failure; do not silently reuse")
    return True


def mosaic(cache, candidates, bounds, width, height, dem=False):
    """Warp exact source pixels with masks; no invented/fallback pixels."""
    ll = transform_bounds("EPSG:3857", "EPSG:4326", *bounds, densify_pts=21)
    sources = [s for s in candidates if intersects(s["bbox"], ll)]
    if not sources:
        raise ValueError("No official source covers requested sample")
    transform = from_bounds(*bounds, width, height)
    data = np.zeros((1 if dem else 3, height, width), dtype="float32" if dem else "uint8")
    filled = np.zeros((height, width), dtype=bool)
    metadata = []
    with cache.serve(sources) as urls:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="0",
                          GDAL_HTTP_TIMEOUT="30", GDAL_CACHEMAX=64_000_000,
                          CPL_VSIL_CURL_CHUNK_SIZE="65536", CPL_VSIL_CURL_CACHE_SIZE="4194304"):
            for candidate, url in zip(sources, urls):
                with rasterio.open(url) as ds:
                    if not ds.crs or ds.count < (1 if dem else 3):
                        raise ValueError("Missing original georeference/bands")
                    native_crs = CRS(ds.crs)
                    unit_scale = native_crs.axis_info[0].unit_conversion_factor
                    if not native_crs.is_projected:
                        raise ValueError("Benchmark native resolution requires projected CRS")
                    with WarpedVRT(ds, crs="EPSG:3857", transform=transform,
                                   width=width, height=height, resampling=Resampling.bilinear,
                                   add_alpha=True, warp_mem_limit=64) as vrt:
                        values = vrt.read([1] if dem else [1, 2, 3])
                        if dem:
                            unit = candidate.get("verticalUnit")
                            if unit not in ("US survey foot", "metre"):
                                raise ValueError("Exact DEM asset vertical unit not established")
                            if unit == "US survey foot":
                                values = values * (1200.0 / 3937.0)
                        alpha = vrt.read(vrt.count)
                        valid = (alpha > 0) & np.isfinite(values).all(axis=0)
                        # First valid source wins deterministically; alpha gaps never become black.
                        take = valid & ~filled
                        data[:, take] = values[:, take]
                        filled |= valid
                    metadata.append({**candidate, **cache.source(candidate["url"]),
                                     "sourceCRS": ds.crs.to_string(), "sourceSize": [ds.width, ds.height],
                                     "sourcePixelSizeMeters": [abs(ds.transform.a) * unit_scale,
                                                               abs(ds.transform.e) * unit_scale],
                                     "sourceDtypes": ds.dtypes, "sourceUnits": ds.units,
                                     "sourceTags": ds.tags(), "validPixelsInWindow": int(valid.sum())})
    if not filled.all():
        raise ValueError(f"Original source pixel gap: {int((~filled).sum())}/{filled.size}")
    if dem:
        if np.ptp(data) < 0.01:
            raise ValueError("Flat/invalid DEM benchmark")
    elif max(float(v.std()) for v in data) < 1:
        raise ValueError("Flat/invalid source imagery")
    return data, transform, metadata


def file_entry(path, root):
    raw = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": digest(raw)}


def pyramid(image, root, layer, x16, y16):
    outputs, zooms = [], []
    for zoom in (16, 17, 18):
        factor = 2 ** (zoom - 16)
        reduced = image.resize((256 * factor, 256 * factor), Image.Resampling.LANCZOS)
        count = byte_count = 0
        for dx in range(factor):
            for dy in range(factor):
                tile = reduced.crop((dx * 256, dy * 256, (dx + 1) * 256, (dy + 1) * 256))
                ext = "png" if tile.mode == "RGBA" else "jpg"
                path = root / "tiles" / layer / str(zoom) / str(x16 * factor + dx) / f"{y16 * factor + dy}.{ext}"
                buffer = io.BytesIO()
                tile.save(buffer, format="PNG" if ext == "png" else "JPEG", **({} if ext == "png" else {"quality": 90, "subsampling": 0}))
                atomic(path, buffer.getvalue())
                with Image.open(path) as actual:
                    actual.load()
                    if actual.size != (256, 256):
                        raise ValueError("Tile decode/dimension failure")
                entry = file_entry(path, root)
                outputs.append(entry)
                count += 1
                byte_count += entry["bytes"]
        zooms.append({"zoom": zoom, "tileCount": count, "bytes": byte_count})
    return outputs, zooms


def detail_metrics(image):
    """Signal difference, NOT a claim of new semantic detail or visual acceptance."""
    results = []
    for high in (17, 18):
        n = 256 * 2 ** (high - 16)
        actual = image.convert("RGB").resize((n, n), Image.Resampling.LANCZOS)
        lower = image.convert("RGB").resize((n // 2, n // 2), Image.Resampling.LANCZOS).resize((n, n), Image.Resampling.BICUBIC)
        delta = np.asarray(actual).astype(float) - np.asarray(lower).astype(float)
        results.append({"zoom": high, "RMSEAgainstUpscaledLowerZoom": float(np.sqrt(np.mean(delta * delta))),
                        "meanAbsolutePixelDifference": float(np.abs(delta).mean()),
                        "semanticDetailAccepted": False})
    return results


def render_rgb(cache, job, root, sources):
    bounds = mercator_bounds(job["x"], job["y"], 16)
    array, transform, metadata = mosaic(cache, sources, bounds, 1024, 1024)
    image = Image.fromarray(array.transpose(1, 2, 0))
    outputs, zooms = pyramid(image, root, job["role"], job["x"], job["y"])
    return {"outputs": outputs, "zooms": zooms, "sourceObjects": metadata,
            "sourcePixelCoverage": 1.0, "grid": list(transform), "boundsEPSG3857": bounds,
            "detailMetrics": detail_metrics(image), "mosaicPixels": 1024 * 1024}


def render_terrain_sun(cache, job, root, sources, z_unit):
    if z_unit != "metre-after-per-source-conversion":
        raise ValueError("DEM elevation units must be normalized from exact asset metadata")
    bounds = mercator_bounds(job["x"], job["y"], 16)
    # Accepted sunlight uses 2.5 Web-Mercator metres and 180m context halo.
    # Use that exact algorithm and resolution. High-resolution hillshade is a separate derivative.
    sun = load_module(SUN_PATH, "accepted_sun")
    presentation = load_module(PRESENTATION_PATH, "accepted_presentation")
    padded = [bounds[0] - 180, bounds[1] - 180, bounds[2] + 180, bounds[3] + 180]
    width = math.ceil((padded[2] - padded[0]) / sun.TARGET_PIXEL_M)
    height = math.ceil((padded[3] - padded[1]) / sun.TARGET_PIXEL_M)
    dem, transform, metadata = mosaic(cache, sources, padded, width, height, dem=True)
    dem = dem[0]
    begin = time.perf_counter()
    fields = sun.terrain_fields(dem, transform)
    alphas = [sun.trace_alpha(dem, transform, fields[kind + "_lip"], fields["allowed"],
                             fields[kind + "_distance"], fields[kind + "_indices"], fields["smooth"])
              for kind in ("east", "west")]
    sun_compute = time.perf_counter() - begin
    outputs, zooms = [], []
    from rasterio.warp import reproject
    target_transform = from_bounds(*bounds, 1024, 1024)
    for alpha, kind, rgb in zip(alphas, ("sunrise", "sunset"),
                                (presentation.SUNRISE_RGB, presentation.SUNSET_RGB)):
        rgba = presentation.rgba_for_kind(alpha, rgb)
        warped = np.zeros((4, 1024, 1024), dtype="uint8")
        for band in range(4):
            reproject(rgba[:, :, band], warped[band], src_transform=transform, src_crs="EPSG:3857",
                      dst_transform=target_transform, dst_crs="EPSG:3857", resampling=Resampling.bilinear)
        o, z = pyramid(Image.fromarray(warped.transpose(1, 2, 0)), root, "sunlight-" + kind, job["x"], job["y"])
        outputs += o
        zooms += [{"layer": "sunlight-" + kind, **r} for r in z]
    # Derive hillshade at the finest requested image grid, reuse the identical original block cache.
    relief_bounds = [bounds[0] - (bounds[2] - bounds[0]) / 1024,
                     bounds[1] - (bounds[3] - bounds[1]) / 1024,
                     bounds[2] + (bounds[2] - bounds[0]) / 1024,
                     bounds[3] + (bounds[3] - bounds[1]) / 1024]
    high, tr, high_meta = mosaic(cache, sources, relief_bounds, 1026, 1026, dem=True)
    ll = transform_bounds("EPSG:3857", "EPSG:4326", *bounds)
    ground_pixel = abs(tr.a) * math.cos(math.radians((ll[1] + ll[3]) / 2))
    gy, gx = np.gradient(high[0], ground_pixel, ground_pixel)
    az, altitude = math.radians(315), math.radians(45)
    # Array y grows south; dz/dnorth = -gy. Unit surface normal is (-gx,+gy,1).
    shade = (-gx * math.sin(az) * math.cos(altitude) + gy * math.cos(az) * math.cos(altitude)
             + math.sin(altitude)) / np.sqrt(1 + gx * gx + gy * gy)
    shade = np.uint8(np.clip(255 * (0.25 + 0.75 * np.maximum(shade, 0)), 0, 255))[1:-1, 1:-1]
    image = Image.fromarray(shade).convert("RGB")
    o, z = pyramid(image, root, "terrain", job["x"], job["y"])
    outputs += o
    zooms += [{"layer": "terrain", **r} for r in z]
    return {"outputs": outputs, "zooms": zooms, "sourceObjects": metadata,
            "reliefSourceObjects": high_meta, "sourcePixelCoverage": 1.0,
            "sunAlgorithmSHA256": digest(SUN_PATH.read_bytes()),
            "sunPresentationSHA256": digest(PRESENTATION_PATH.read_bytes()),
            "sunComputeSeconds": sun_compute, "sunDEMShape": list(dem.shape),
            "sunDEMArraySHA256": digest(dem.tobytes()), "sunGrid": list(transform),
            "sunElevationRangeMeters": [float(dem.min()), float(dem.max())],
            "sunNonzeroPixels": [int(np.count_nonzero(a)) for a in alphas],
            "sunMinimumElevationFeet": sun.MIN_ELEVATION_FT,
            "sunlightIsPotentialNotTimeOfDayShadow": True,
            "terrainStyleAccepted": False, "detailMetrics": detail_metrics(image)}


def run(plan, root, cache_root, max_jobs=12, byte_limit=250_000_000):
    if plan.get("version") != VERSION or plan.get("boundsWGS84") != AOI or len(plan.get("samples", [])) > 12:
        raise ValueError("Expected bounded official Gorge benchmark plan")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    recipe = digest(json_bytes({"plan": plan, "engine": digest(Path(__file__).read_bytes()),
                               "cache": digest((Path(__file__).parent / "cached_cog_source.py").read_bytes()),
                               "sun": digest(SUN_PATH.read_bytes()), "presentation": digest(PRESENTATION_PATH.read_bytes()),
                               "rasterio": rasterio.__version__, "GDAL": rasterio.__gdal_version__,
                               "numpy": np.__version__}))
    pinned = root / "PLAN.json"
    if pinned.exists() and pinned.read_bytes() != json_bytes(plan):
        raise ValueError("Cannot reuse output directory for a different plan")
    atomic(pinned, json_bytes(plan))
    begin = time.perf_counter()
    cache = Cache(cache_root, limit=byte_limit)
    before = cache.metrics()
    receipts, failures, skipped = [], [], []
    executed = 0
    try:
        for sample in plan["samples"]:
            x, y = xy(sample["lon"], sample["lat"], 16)
            if not AOI[0] <= sample["lon"] <= AOI[2] or not AOI[1] <= sample["lat"] <= AOI[3]:
                raise ValueError("Sample outside approved Gorge bounds")
            for role in ("hiking", "terrain-sunlight", "leaf-off", "leaf-on"):
                key = f"{sample['id']}-{role}"
                if not all(c.isalnum() or c in "-_" for c in key):
                    raise ValueError("Unsafe job identity")
                source_role = "dem" if role == "terrain-sunlight" else role
                sources = plan["sources"].get(source_role, [])
                if not sources:
                    skipped.append({"job": key, "reason": "Official original source not yet resolved"})
                    continue
                path = root / "receipts" / (key + ".json")
                if path.exists():
                    receipt = json.loads(path.read_text())
                    receipt_valid(root, receipt, recipe)
                    receipts.append({**receipt, "reused": True})
                    continue
                if executed >= max_jobs:
                    skipped.append({"job": key, "reason": "Bounded invocation job limit"})
                    continue
                executed += 1
                start, metrics = time.perf_counter(), cache.metrics()
                job = {"x": x, "y": y, "role": role, "id": sample["id"]}
                try:
                    result = (render_terrain_sun(cache, job, root, sources, plan.get("demElevationUnit"))
                              if role == "terrain-sunlight" else render_rgb(cache, job, root, sources))
                    after = cache.metrics()
                    receipt = {"job": key, "recipeSHA256": recipe, "validated": True, "reused": False,
                               "elapsedSeconds": time.perf_counter() - start,
                               "sourceBytes": after["receivedBytes"] - metrics["receivedBytes"],
                               "sourceRequests": after["requests"] - metrics["requests"], **result}
                    atomic(path, json_bytes(receipt))
                    receipts.append(receipt)
                    print(json.dumps({k: receipt[k] for k in ("job", "elapsedSeconds", "sourceBytes", "sourceRequests")}), flush=True)
                except Exception as error:
                    failure = {"job": key, "error": str(error)[:1200], "elapsedSeconds": time.perf_counter() - start,
                               "traceback": traceback.format_exc()[-6000:],
                               "sourceLedger": cache.metrics()}
                    atomic(root / "failures" / f"{key}-{time.time_ns()}.json", json_bytes(failure))
                    failures.append(failure)
                    print(json.dumps(failure), flush=True)
        report = {"status": "BENCHMARK ONLY; NOT INSTALLABLE OR REGIONAL ACCEPTANCE",
                  "recipeSHA256": recipe, "elapsedThisInvocationSeconds": time.perf_counter() - begin,
                  "runtime": {"platform": platform.platform(), "rasterio": rasterio.__version__, "GDAL": rasterio.__gdal_version__},
                  "before": before, "after": cache.metrics(), "receipts": receipts, "failures": failures, "skipped": skipped,
                  "actualIPhoneMeasured": False, "productionAuthorized": False, "actionsTriggered": False}
        atomic(root / "BENCHMARK.json", json_bytes(report))
        return report
    finally:
        cache.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cache", required=True, type=Path)
    p.add_argument("--max-jobs", type=int, default=12, choices=range(1, 49))
    p.add_argument("--max-source-bytes", type=int, default=250_000_000)
    p.add_argument("--live-source-benchmark", action="store_true")
    a = p.parse_args()
    if not a.live_source_benchmark:
        p.error("Explicit --live-source-benchmark required; no source requests made")
    r = run(json.loads(a.plan.read_text()), a.output, a.cache, a.max_jobs, a.max_source_bytes)
    if r["failures"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
