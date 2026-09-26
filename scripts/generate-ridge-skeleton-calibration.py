#!/usr/bin/env python3
import json
import math
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from rasterio.io import MemoryFile
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter, maximum_filter, minimum_filter
from skimage.feature import peak_local_max
from skimage.morphology import remove_small_objects, skeletonize
from skimage.segmentation import watershed

BOUNDS = {"west": -83.6505, "south": 37.8060, "east": -83.6170, "north": 37.8345}
PIXEL_METERS = 4.0
CREST_CORRIDOR_METERS = 12.0
VERSION = 10

KENTUCKY_PHASE3_DEM_SERVICE = "https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase3_WGS84WM/ImageServer"
KENTUCKY_PHASE2_METERS_DEM_SERVICE = "https://kyraster.ky.gov/arcgis/rest/services/ElevationServices/Ky_DEM_KYAPED_2FT_Phase2_ZMeters_WGS84WM/ImageServer"
USGS_DEM_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"

MID_LAT = (BOUNDS["south"] + BOUNDS["north"]) / 2.0
WIDTH_METERS = 111320.0 * math.cos(math.radians(MID_LAT)) * (BOUNDS["east"] - BOUNDS["west"])
HEIGHT_METERS = 111320.0 * (BOUNDS["north"] - BOUNDS["south"])
COLS = max(512, int(round(WIDTH_METERS / PIXEL_METERS)))
ROWS = max(512, int(round(HEIGHT_METERS / PIXEL_METERS)))
X_METERS = WIDTH_METERS / COLS
Y_METERS = HEIGHT_METERS / ROWS
MEAN_CELL_METERS = (X_METERS + Y_METERS) / 2.0

OUT_DIR = Path("public/data/map")
SKELETON_PATH = OUT_DIR / "sunrise-sunset-calibration-ridge-skeleton.png"
CORRIDOR_PATH = OUT_DIR / "sunrise-sunset-calibration-crest.png"
META_PATH = OUT_DIR / "sunrise-sunset-ridge-calibration.meta.json"

session = requests.Session()
session.headers.update({"User-Agent": "RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)"})

def request_json(url, *, params, timeout=120, attempts=3):
    last = None
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(json.dumps(payload["error"]))
            return payload
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt)
    raise last

def lonlat_to_web_mercator(lon, lat):
    radius = 6378137.0
    x = radius * math.radians(lon)
    lat = max(-85.05112878, min(85.05112878, lat))
    y = radius * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y

def web_mercator_bbox():
    west, south = lonlat_to_web_mercator(BOUNDS["west"], BOUNDS["south"])
    east, north = lonlat_to_web_mercator(BOUNDS["east"], BOUNDS["north"])
    return west, south, east, north

def export_raster(service, bbox, bbox_sr, image_sr):
    params = {
        "f": "json",
        "bbox": ",".join(str(v) for v in bbox),
        "bboxSR": str(bbox_sr),
        "imageSR": str(image_sr),
        "size": f"{COLS},{ROWS}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "returnSquarePixels": "false",
    }
    payload = request_json(service + "/exportImage", params=params, timeout=180)
    href = payload.get("href")
    if not href:
        raise RuntimeError("Image service returned no export href.")
    response = session.get(href, timeout=180)
    response.raise_for_status()
    with MemoryFile(response.content) as mem:
        with mem.open() as src:
            data = src.read(1).astype(np.float32)
            if src.width != COLS or src.height != ROWS:
                raise RuntimeError(f"Unexpected DEM size {src.width}x{src.height}")
            return data

def validate(raw, source):
    valid = np.isfinite(raw) & (raw > source["validMin"]) & (raw < source["validMax"])
    fraction = float(np.count_nonzero(valid)) / raw.size
    if fraction < 0.90:
        raise RuntimeError(f"valid DEM coverage only {fraction:.3f}")
    values = raw[valid]
    relief = float(np.max(values) - np.min(values))
    std = float(np.std(values))
    if relief < source["minRelief"] or std < 1.0:
        raise RuntimeError(f"DEM lacks relief: relief={relief:.2f}, std={std:.2f}")
    return valid, relief, std, float(np.min(values)), float(np.max(values))

sources = [
    {
        "id": "kyfromabove-phase3-2ft-dem",
        "service": KENTUCKY_PHASE3_DEM_SERVICE,
        "bbox": web_mercator_bbox(),
        "bboxSR": 3857,
        "imageSR": 3857,
        "zToMeters": 0.3048,
        "validMin": 100.0,
        "validMax": 5000.0,
        "minRelief": 50.0,
    },
    {
        "id": "kyfromabove-phase2-2ft-dem-meters",
        "service": KENTUCKY_PHASE2_METERS_DEM_SERVICE,
        "bbox": web_mercator_bbox(),
        "bboxSR": 3857,
        "imageSR": 3857,
        "zToMeters": 1.0,
        "validMin": -100.0,
        "validMax": 2000.0,
        "minRelief": 15.0,
    },
    {
        "id": "usgs-3dep-bare-earth-dem",
        "service": USGS_DEM_SERVICE,
        "bbox": (BOUNDS["west"], BOUNDS["south"], BOUNDS["east"], BOUNDS["north"]),
        "bboxSR": 4326,
        "imageSR": 4326,
        "zToMeters": 1.0,
        "validMin": -500.0,
        "validMax": 5000.0,
        "minRelief": 15.0,
    },
]

raw_dem = None
valid_mask = None
source_used = None
source_errors = []
source_stats = None
for source in sources:
    try:
        candidate = export_raster(source["service"], source["bbox"], source["bboxSR"], source["imageSR"])
        candidate_valid, relief, std, minimum, maximum = validate(candidate, source)
        raw_dem = candidate
        valid_mask = candidate_valid
        source_used = source
        source_stats = {
            "rawRelief": relief,
            "rawStandardDeviation": std,
            "rawMin": minimum,
            "rawMax": maximum,
        }
        print(f'Using DEM {source["id"]}: relief={relief:.2f}, std={std:.2f}', flush=True)
        break
    except Exception as exc:
        source_errors.append({"id": source["id"], "error": str(exc)})
        print(f'DEM source failed {source["id"]}: {exc}')

if raw_dem is None or valid_mask is None or source_used is None:
    raise RuntimeError(f"No valid DEM source: {source_errors}")

dem = raw_dem * float(source_used["zToMeters"])
replacement = float(np.nanmedian(np.where(valid_mask, dem, np.nan)))
dem[~valid_mask] = replacement

# Hydrologic basin markers: spatially separated local low points on a lightly
# smoothed DEM. Watershed boundaries are drainage divides, i.e. ridge topology.
stage_started = time.monotonic()
print(f'Ridge calibration grid: {COLS} x {ROWS} at ~{MEAN_CELL_METERS:.2f} m; beginning watershed topology', flush=True)
hydro_dem = gaussian_filter(dem, sigma=max(1.0, 6.0 / MEAN_CELL_METERS))
minima_separation_m = 70.0
min_distance_px = max(8, int(round(minima_separation_m / MEAN_CELL_METERS)))
minima_coords = peak_local_max(
    -hydro_dem,
    min_distance=min_distance_px,
    exclude_border=False,
    num_peaks=220,
)
if minima_coords.shape[0] < 8:
    minima_separation_m = 40.0
    min_distance_px = max(6, int(round(minima_separation_m / MEAN_CELL_METERS)))
    minima_coords = peak_local_max(
        -hydro_dem,
        min_distance=min_distance_px,
        exclude_border=False,
        num_peaks=320,
    )

basin_count = int(minima_coords.shape[0])
print(f'Found {basin_count} drainage minima in {time.monotonic() - stage_started:.1f}s', flush=True)
if basin_count < 2:
    raise RuntimeError(f"Too few drainage minima for watershed segmentation: {basin_count}")

markers = np.zeros(dem.shape, dtype=np.int32)
for marker_id, (row, col) in enumerate(minima_coords, start=1):
    markers[int(row), int(col)] = marker_id

basins = watershed(
    hydro_dem,
    markers=markers,
    connectivity=np.ones((3, 3), dtype=np.uint8),
    watershed_line=True,
)
raw_skeleton = skeletonize(basins == 0)
print(f'Built raw watershed divide skeleton in {time.monotonic() - stage_started:.1f}s', flush=True)

# Prune basin divides that run through low saddles or flanks. The pruning can
# remove a line, but it cannot shift the surviving divide off its topological
# location.
radius_px = max(15, int(round(300.0 / MEAN_CELL_METERS)))
size = radius_px * 2 + 1
local_low = minimum_filter(dem, size=size, mode="nearest")
local_high = maximum_filter(dem, size=size, mode="nearest")
local_relief = np.maximum(local_high - local_low, 1.0)
relative_height = np.clip((dem - local_low) / local_relief, 0.0, 1.0)

# A 120 m broad TPI is sufficient for ridge-vs-flank pruning at the 4 m
# topology grid and avoids an unnecessarily expensive very-wide convolution.
broad_sigma = max(4.0, 120.0 / MEAN_CELL_METERS)
broad_tpi = dem - gaussian_filter(dem, sigma=broad_sigma)

near_radius_px = max(3, int(round(18.0 / MEAN_CELL_METERS)))
near_high = maximum_filter(dem, size=near_radius_px * 2 + 1, mode="nearest")
meters_below_near_high = near_high - dem

ridge_keep = (
    (relative_height >= 0.30)
    & (broad_tpi >= 0.0)
    & (meters_below_near_high <= 5.0)
)
ridge_skeleton = raw_skeleton & ridge_keep
min_segment_pixels = max(6, int(round(24.0 / MEAN_CELL_METERS)))
ridge_skeleton = remove_small_objects(ridge_skeleton, min_size=min_segment_pixels, connectivity=2)
ridge_skeleton = skeletonize(ridge_skeleton)
print(f'Pruned ridge skeleton in {time.monotonic() - stage_started:.1f}s', flush=True)

if np.count_nonzero(ridge_skeleton) < 50:
    raise RuntimeError("Topological ridge skeleton is too sparse after pruning.")

ridge_distance_m = distance_transform_edt(
    ~ridge_skeleton,
    sampling=(Y_METERS, X_METERS),
)
crest_corridor = ridge_distance_m <= CREST_CORRIDOR_METERS
corridor_strength = np.clip(1.0 - ridge_distance_m / CREST_CORRIDOR_METERS, 0.0, 1.0)

def rgba(mask_strength, rgb, alpha):
    strength = np.clip(mask_strength.astype(np.float32), 0.0, 1.0)
    out = np.zeros((ROWS, COLS, 4), dtype=np.uint8)
    out[..., :3] = np.array(rgb, dtype=np.uint8)
    out[..., 3] = np.clip(strength * alpha * 255.0, 0, 255).astype(np.uint8)
    return out

OUT_DIR.mkdir(parents=True, exist_ok=True)
visible_skeleton = binary_dilation(ridge_skeleton, iterations=1).astype(np.float32)
Image.fromarray(rgba(visible_skeleton, (255, 255, 80), 0.98), mode="RGBA").save(
    SKELETON_PATH, optimize=True, compress_level=9
)
Image.fromarray(rgba(corridor_strength * crest_corridor, (255, 176, 32), 0.76), mode="RGBA").save(
    CORRIDOR_PATH, optimize=True, compress_level=9
)

def percent(mask):
    return round(float(np.count_nonzero(mask)) / mask.size * 100.0, 3)

metadata = {
    "version": VERSION,
    "phase": "ridge-skeleton-only",
    "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "bounds": BOUNDS,
    "grid": {
        "cols": COLS,
        "rows": ROWS,
        "approximateCellMeters": [round(X_METERS, 2), round(Y_METERS, 2)],
    },
    "source": {
        "elevation": {
            "id": source_used["id"],
            "service": source_used["service"],
            "preferredSource": "kyfromabove-phase3-2ft-dem",
            "fallbackSources": ["kyfromabove-phase2-2ft-dem-meters", "usgs-3dep-bare-earth-dem"],
            "attemptErrors": source_errors,
            **source_stats,
        }
    },
    "topology": {
        "method": "watershed drainage divides thinned to a skeleton, then pruned without relocating surviving divide pixels",
        "watershedBasinCount": basin_count,
        "minimaSeparationMeters": minima_separation_m,
        "crestCorridorMeters": CREST_CORRIDOR_METERS,
        "calibrationGridMeters": PIXEL_METERS,
        "trailOrAerialAffectsSkeleton": False,
        "ridgeKeep": {
            "minimumRelativeHeight": 0.30,
            "minimumBroadTpiMeters": 0.0,
            "maximumMetersBelowNearbyHigh": 5.0,
            "nearbyHighRadiusMeters": 18.0,
        },
    },
    "coverage": {
        "rawDividePercent": percent(raw_skeleton),
        "ridgeSkeletonPercent": percent(ridge_skeleton),
        "crestCorridorPercent": percent(crest_corridor),
    },
    "review": {
        "order": [
            "1 · LiDAR ridge skeleton",
            "2 · Crest corridor (~12 m)",
        ],
        "instruction": "Do not tune sunrise/sunset until the thin ridge skeleton visually follows known ridge tops. This ridge-only calibration uses a ~4 m topology grid for fast iteration; final sun scoring may return to finer terrain sampling after geometry approval.",
        "finalCompositeStatus": "v9 composite retained but held; not recalculated in this ridge-only phase",
    },
}
META_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
print(json.dumps(metadata, indent=2), flush=True)
print(f'Ridge calibration complete in {time.monotonic() - stage_started:.1f}s', flush=True)
