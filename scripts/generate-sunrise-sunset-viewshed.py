#!/usr/bin/env python3
import io
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from scipy.ndimage import distance_transform_edt, gaussian_filter, label as ndi_label, maximum_filter, minimum_filter, uniform_filter
from shapely.geometry import LineString, Polygon, mapping
from skimage.morphology import h_minima, remove_small_objects, skeletonize
from skimage.segmentation import watershed

ELEVATION_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
NAIP_SERVICE = "https://apps.geo.fpac.usda.gov/geo-imagery/rest/services/naip/conus_naip/ImageServer"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.maprva.org/api/interpreter",
]
# Calibration pilot only: Pinch-Em-Tight / Sheltowee suspension-bridge terrain.
# Keep this small until the ridge/valley and directional-overlook geometry is
# visually correct, then apply the same rules to an independent validation area.
BOUNDS = {"west": -83.6505, "south": 37.8060, "east": -83.6170, "north": 37.8345}
PIXEL_METERS = 2.0
SUNRISE_AZIMUTHS = [58.0, 90.0, 121.0]
SUNSET_AZIMUTHS = [239.0, 270.0, 302.0]
SUNRISE_RGB = np.array([255.0, 111.0, 97.0], dtype=np.float32)
SUNSET_RGB = np.array([64.0, 85.0, 216.0], dtype=np.float32)
DISPLAY_CANDIDATE_QUANTILE = 0.58
STRONG_CANDIDATE_QUANTILE = 0.86
PEAK_CANDIDATE_QUANTILE = 0.98
OVERLOOK_SUPPORT_MIN = 0.42
NEAR_DROP_MIN = 0.42
DIRECTIONAL_VIEW_MIN = 0.50
DUAL_VIEW_MIN = 0.82
VERSION = 10

OUT_DIR = Path("public/data/map")
PNG_PATH = OUT_DIR / "sunrise-sunset-potential.png"
META_PATH = OUT_DIR / "sunrise-sunset-potential.meta.json"
OLD_SVG_PATH = OUT_DIR / "sunrise-sunset-potential.svg"
DIAG_SKELETON_PATH = OUT_DIR / "sunrise-sunset-calibration-ridge-skeleton.png"
DIAG_CREST_PATH = OUT_DIR / "sunrise-sunset-calibration-crest.png"
DIAG_OVERLOOK_PATH = OUT_DIR / "sunrise-sunset-calibration-overlook.png"
DIAG_OPEN_PATH = OUT_DIR / "sunrise-sunset-calibration-open-ground.png"
DIAG_SUNRISE_PATH = OUT_DIR / "sunrise-sunset-calibration-sunrise-pass.png"
DIAG_SUNSET_PATH = OUT_DIR / "sunrise-sunset-calibration-sunset-pass.png"

MID_LAT = (BOUNDS["south"] + BOUNDS["north"]) / 2
WIDTH_METERS = 111320.0 * math.cos(math.radians(MID_LAT)) * (BOUNDS["east"] - BOUNDS["west"])
HEIGHT_METERS = 111320.0 * (BOUNDS["north"] - BOUNDS["south"])
COLS = max(512, int(round(WIDTH_METERS / PIXEL_METERS)))
ROWS = max(512, int(round(HEIGHT_METERS / PIXEL_METERS)))
X_METERS = WIDTH_METERS / COLS
Y_METERS = HEIGHT_METERS / ROWS
TRANSFORM = from_bounds(BOUNDS["west"], BOUNDS["south"], BOUNDS["east"], BOUNDS["north"], COLS, ROWS)

session = requests.Session()
session.headers.update({"User-Agent": "RedRiverGorgeHiker/1.0 (+https://redrivergorgehiker.com/)"})

def clamp01(value):
    return np.clip(value, 0.0, 1.0)

def smoothstep(value, low, high):
    if high <= low:
        return (value >= high).astype(np.float32)
    x = clamp01((value - low) / (high - low))
    return x * x * (3.0 - 2.0 * x)

def request_json(url, *, params=None, data=None, timeout=120, attempts=4):
    last = None
    for attempt in range(attempts):
        try:
            if data is None:
                response = session.get(url, params=params, timeout=timeout)
            else:
                response = session.post(url, data=data, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(json.dumps(payload["error"]))
            return payload
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.0 + attempt * 1.5)
    raise last

def export_image(service, *, pixel_type, band_ids=None):
    params = {
        "f": "json",
        "bbox": f'{BOUNDS["west"]},{BOUNDS["south"]},{BOUNDS["east"]},{BOUNDS["north"]}',
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{COLS},{ROWS}",
        "format": "tiff",
        "pixelType": pixel_type,
        "interpolation": "RSP_BilinearInterpolation",
        "returnSquarePixels": "false",
    }
    if band_ids is not None:
        params["bandIds"] = ",".join(str(x) for x in band_ids)
    payload = request_json(service + "/exportImage", params=params, timeout=180)
    href = payload.get("href")
    if not href:
        raise RuntimeError(f"Image service returned no href: {payload}")
    last = None
    for attempt in range(4):
        try:
            response = session.get(href, timeout=180)
            response.raise_for_status()
            with MemoryFile(response.content) as mem:
                with mem.open() as src:
                    data = src.read()
                    if src.width != COLS or src.height != ROWS:
                        raise RuntimeError(f"Unexpected raster size {src.width}x{src.height}; expected {COLS}x{ROWS}")
                    return data
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(1.5 + attempt * 2)
    raise last

def shift(arr, dr, dc, fill=np.nan):
    out = np.full(arr.shape, fill, dtype=np.float32)
    rows, cols = arr.shape
    src_r0 = max(0, dr)
    src_r1 = min(rows, rows + dr)
    src_c0 = max(0, dc)
    src_c1 = min(cols, cols + dc)
    dst_r0 = max(0, -dr)
    dst_r1 = min(rows, rows - dr)
    dst_c0 = max(0, -dc)
    dst_c1 = min(cols, cols - dc)
    if src_r1 > src_r0 and src_c1 > src_c0 and dst_r1 > dst_r0 and dst_c1 > dst_c0:
        out[dst_r0:dst_r1, dst_c0:dst_c1] = arr[src_r0:src_r1, src_c0:src_c1]
    return out


def bilateral_ridge_relief(dem):
    """Measure whether terrain falls away on both sides of some local ridge axis."""
    best_relief = np.zeros(dem.shape, dtype=np.float32)
    mean_cell = (X_METERS + Y_METERS) / 2.0
    distances_m = [12.0, 24.0, 48.0, 80.0]
    weights = [0.34, 0.30, 0.23, 0.13]

    # These are cross-ridge normals. Taking the best orientation makes the
    # detector agnostic to the direction the ridge itself runs.
    for normal_degrees in [0.0, 30.0, 60.0, 90.0, 120.0, 150.0]:
        angle = math.radians(normal_degrees)
        east = math.sin(angle)
        north = math.cos(angle)
        plus_score = np.zeros(dem.shape, dtype=np.float32)
        minus_score = np.zeros(dem.shape, dtype=np.float32)

        for distance_m, weight in zip(distances_m, weights):
            distance_px = max(1, int(round(distance_m / mean_cell)))
            dr = int(round(-north * distance_px))
            dc = int(round(east * distance_px))
            plus = shift(dem, dr, dc)
            minus = shift(dem, -dr, -dc)
            plus_drop = np.where(np.isfinite(plus), np.maximum(0.0, dem - plus), 0.0)
            minus_drop = np.where(np.isfinite(minus), np.maximum(0.0, dem - minus), 0.0)
            plus_score += weight * plus_drop
            minus_score += weight * minus_drop

        bilateral = np.minimum(plus_score, minus_score)
        best_relief = np.maximum(best_relief, bilateral)

    ridge_score = smoothstep(best_relief, 3.0, 18.0)
    return best_relief, ridge_score



def topological_ridge_skeleton(dem, relative_height, prominence, broad_tpi, bilateral_relief_m, convexity):
    """
    Extract hydrologic drainage divides from the LiDAR DEM, then thin and prune
    them into an actual ridge skeleton. This line is topological geometry, not a
    fuzzy upper-slope score.
    """
    mean_cell = (X_METERS + Y_METERS) / 2.0
    hydro_sigma = max(1.0, 6.0 / mean_cell)
    hydro_dem = gaussian_filter(dem, sigma=hydro_sigma)

    # Suppress tiny LiDAR pits so watershed basins represent real hollows.
    minima_depth_m = 2.5
    minima = h_minima(hydro_dem, minima_depth_m)
    markers, basin_count = ndi_label(minima)

    if basin_count < 8:
        minima_depth_m = 1.25
        minima = h_minima(hydro_dem, minima_depth_m)
        markers, basin_count = ndi_label(minima)
    elif basin_count > 320:
        minima_depth_m = 4.0
        minima = h_minima(hydro_dem, minima_depth_m)
        markers, basin_count = ndi_label(minima)

    if basin_count < 2:
        raise RuntimeError(f"Too few hydrologic basins for ridge extraction: {basin_count}")

    basin_labels = watershed(
        hydro_dem,
        markers=markers,
        connectivity=np.ones((3, 3), dtype=np.uint8),
        watershed_line=True,
    )
    raw_divide = basin_labels == 0
    raw_skeleton = skeletonize(raw_divide)

    # Prune low saddles and incidental basin boundaries without moving the
    # divide line. The remaining pixels must still occupy locally elevated,
    # ridge-like terrain.
    ridge_keep = (
        (relative_height >= 0.14)
        & (prominence >= 0.10)
        & (broad_tpi >= -1.5)
        & ((bilateral_relief_m >= 2.5) | (convexity >= 0.56))
    )
    skeleton = raw_skeleton & ridge_keep
    min_segment_pixels = max(6, int(round(24.0 / mean_cell)))
    skeleton = remove_small_objects(skeleton, min_size=min_segment_pixels, connectivity=2)
    skeleton = skeletonize(skeleton)

    return skeleton, raw_skeleton, basin_count, minima_depth_m

def fetch_trail_elements():
    bbox = f'{BOUNDS["south"]},{BOUNDS["west"]},{BOUNDS["north"]},{BOUNDS["east"]}'
    query = f"""[out:json][timeout:40];
(
  way["highway"~"^(path|footway|track)$"]({bbox});
  way["route"="hiking"]({bbox});
);
out tags geom qt;"""
    last = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            payload = request_json(endpoint, data={"data": query}, timeout=55, attempts=1)
            elements = [
                element for element in payload.get("elements", [])
                if element.get("type") == "way" and element.get("geometry")
            ]
            return elements, endpoint
        except Exception as exc:
            last = exc
    raise last


def diagnostic_rgba(strength, rgb, alpha_max=0.78):
    strength = clamp01(strength.astype(np.float32))
    rgba = np.zeros((ROWS, COLS, 4), dtype=np.uint8)
    rgba[..., :3] = np.array(rgb, dtype=np.uint8)
    rgba[..., 3] = np.clip(strength * alpha_max * 255.0, 0, 255).astype(np.uint8)
    return rgba

def directional_metrics(dem, vegetation, azimuths):
    best_score = np.zeros(dem.shape, dtype=np.float32)
    best_open = np.zeros(dem.shape, dtype=np.float32)
    best_drop = np.zeros(dem.shape, dtype=np.float32)
    best_near_drop = np.zeros(dem.shape, dtype=np.float32)
    best_aerial = np.zeros(dem.shape, dtype=np.float32)

    # V6 distinguishes a true overlook edge from a broad ridge by measuring a
    # near-field terrain break separately from the long-range horizon.
    for azimuth in azimuths:
        seasonal_score = np.zeros(dem.shape, dtype=np.float32)
        seasonal_open = np.zeros(dem.shape, dtype=np.float32)
        seasonal_drop = np.zeros(dem.shape, dtype=np.float32)
        seasonal_near_drop = np.zeros(dem.shape, dtype=np.float32)
        seasonal_aerial = np.zeros(dem.shape, dtype=np.float32)

        for fan_offset, fan_weight in [(-20.0, 0.76), (-10.0, 0.90), (0.0, 1.0), (10.0, 0.90), (20.0, 0.76)]:
            bearing = math.radians(azimuth + fan_offset)
            east = math.sin(bearing)
            north = math.cos(bearing)

            max_angle = np.full(dem.shape, -90.0, dtype=np.float32)
            max_drop = np.zeros(dem.shape, dtype=np.float32)
            max_near_drop = np.zeros(dem.shape, dtype=np.float32)
            veg_samples = []

            for distance_px in [3, 6, 12, 24, 48, 96, 192, 320]:
                dr = int(round(-north * distance_px))
                dc = int(round(east * distance_px))
                target = shift(dem, dr, dc)
                horizontal = max(1.0, math.hypot(dr * Y_METERS, dc * X_METERS))
                angle = np.degrees(np.arctan2(target - dem, horizontal)).astype(np.float32)
                valid = np.isfinite(target)
                max_angle = np.where(valid, np.maximum(max_angle, angle), max_angle)
                max_drop = np.where(valid, np.maximum(max_drop, dem - target), max_drop)
                if distance_px <= 40:
                    max_near_drop = np.where(valid, np.maximum(max_near_drop, dem - target), max_near_drop)

            for distance_px in [2, 4, 8, 16, 24]:
                dr = int(round(-north * distance_px))
                dc = int(round(east * distance_px))
                sample = shift(vegetation, dr, dc, fill=1.0)
                veg_samples.append(sample)

            terrain_open = clamp01((7.0 - max_angle) / 14.0)
            drop_score = smoothstep(max_drop, 12.0, 100.0)
            near_drop_score = smoothstep(max_near_drop, 7.0, 38.0)
            sector_vegetation = np.mean(np.stack(veg_samples, axis=0), axis=0)
            aerial_open = clamp01(1.0 - sector_vegetation)

            direction_score = (
                0.31 * terrain_open
                + 0.27 * drop_score
                + 0.27 * near_drop_score
                + 0.15 * aerial_open
            ) * fan_weight

            seasonal_score = np.maximum(seasonal_score, direction_score)
            seasonal_open = np.maximum(seasonal_open, terrain_open * fan_weight)
            seasonal_drop = np.maximum(seasonal_drop, drop_score * fan_weight)
            seasonal_near_drop = np.maximum(seasonal_near_drop, near_drop_score * fan_weight)
            seasonal_aerial = np.maximum(seasonal_aerial, aerial_open * fan_weight)

        best_score = np.maximum(best_score, seasonal_score)
        best_open = np.maximum(best_open, seasonal_open)
        best_drop = np.maximum(best_drop, seasonal_drop)
        best_near_drop = np.maximum(best_near_drop, seasonal_near_drop)
        best_aerial = np.maximum(best_aerial, seasonal_aerial)

    return best_score, best_open, best_drop, best_near_drop, best_aerial

def angle_distance(aspect, target):
    delta = np.abs(aspect - target) % 360.0
    return np.minimum(delta, 360.0 - delta)

def aspect_score(aspect, slope_degrees, azimuths):
    best = np.zeros(aspect.shape, dtype=np.float32)
    for az in azimuths:
        alignment = np.maximum(0.0, np.cos(np.radians(angle_distance(aspect, az))))
        best = np.maximum(best, alignment.astype(np.float32))
    slope_strength = clamp01(slope_degrees / 18.0)
    return (0.58 * (1.0 - slope_strength) + best * slope_strength).astype(np.float32)

def fetch_water_elements():
    tiles_x = 3
    tiles_y = 3
    elements = {}
    used = set()
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            west = BOUNDS["west"] + tx / tiles_x * (BOUNDS["east"] - BOUNDS["west"])
            east = BOUNDS["west"] + (tx + 1) / tiles_x * (BOUNDS["east"] - BOUNDS["west"])
            north = BOUNDS["north"] - ty / tiles_y * (BOUNDS["north"] - BOUNDS["south"])
            south = BOUNDS["north"] - (ty + 1) / tiles_y * (BOUNDS["north"] - BOUNDS["south"])
            bbox = f"{south},{west},{north},{east}"
            query = f"""[out:json][timeout:40];
(
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["waterway"="riverbank"]({bbox});
  relation["waterway"="riverbank"]({bbox});
  way["waterway"~"^(river|stream|creek|canal)$"]({bbox});
);
out tags geom qt;"""
            last = None
            payload = None
            for endpoint in OVERPASS_ENDPOINTS:
                try:
                    payload = request_json(endpoint, data={"data": query}, timeout=55, attempts=1)
                    used.add(endpoint)
                    break
                except Exception as exc:
                    last = exc
            if payload is None:
                raise last
            for element in payload.get("elements", []):
                if element.get("type") and element.get("id") is not None:
                    elements[f'{element["type"]}:{element["id"]}'] = element
            print(f"OpenStreetMap water query {ty * tiles_x + tx + 1}/{tiles_x * tiles_y}: {len(elements)} unique elements")
    return list(elements.values()), sorted(used)

def coords(geometry):
    result = []
    for point in geometry or []:
        try:
            result.append((float(point["lon"]), float(point["lat"])))
        except Exception:
            pass
    return result

def water_shapes(elements):
    polygon_shapes = []
    line_shapes = []
    for element in elements:
        tags = element.get("tags") or {}
        is_polygon = tags.get("natural") == "water" or tags.get("waterway") == "riverbank"
        is_line = str(tags.get("waterway") or "") in {"river", "stream", "creek", "canal"}

        if element.get("type") == "way":
            xy = coords(element.get("geometry"))
            if len(xy) < 2:
                continue
            if is_polygon and len(xy) >= 4 and xy[0] == xy[-1]:
                try:
                    poly = Polygon(xy)
                    if poly.is_valid and not poly.is_empty:
                        polygon_shapes.append(poly)
                except Exception:
                    pass
            elif is_polygon or is_line:
                try:
                    line_shapes.append(LineString(xy))
                except Exception:
                    pass
            continue

        if element.get("type") == "relation" and is_polygon:
            # Overpass relation members include geometry. Closed outer member rings
            # are sufficient for the water-mask purpose; unclosed fragments are
            # treated as direct-water lines rather than broadly buffered.
            for member in element.get("members") or []:
                xy = coords(member.get("geometry"))
                if len(xy) < 2:
                    continue
                if member.get("role") == "outer" and len(xy) >= 4 and xy[0] == xy[-1]:
                    try:
                        poly = Polygon(xy)
                        if poly.is_valid and not poly.is_empty:
                            polygon_shapes.append(poly)
                    except Exception:
                        pass
                else:
                    try:
                        line_shapes.append(LineString(xy))
                    except Exception:
                        pass
    return polygon_shapes, line_shapes

print(f"V7 Pinch-Em-Tight calibration viewshed grid: {COLS} x {ROWS} at approximately {X_METERS:.1f} m x {Y_METERS:.1f} m")
dem_bands = export_image(ELEVATION_SERVICE, pixel_type="F32")
dem = dem_bands[0].astype(np.float32)
bad_dem = ~np.isfinite(dem) | (dem < -500.0) | (dem > 5000.0)
if np.any(bad_dem):
    replacement = float(np.nanmedian(np.where(bad_dem, np.nan, dem)))
    dem[bad_dem] = replacement

naip = export_image(NAIP_SERVICE, pixel_type="U8", band_ids=[0, 1, 2, 3]).astype(np.float32)
if naip.shape[0] < 3:
    raise RuntimeError(f"NAIP export returned only {naip.shape[0]} bands")

red = naip[0]
green = naip[1]
blue = naip[2]
if naip.shape[0] >= 4:
    nir = naip[3]
    ndvi = (nir - red) / np.maximum(nir + red, 1.0)
    valid_ndvi = ndvi[np.isfinite(ndvi) & ((nir + red) > 8.0)]
    if valid_ndvi.size < 1000:
        raise RuntimeError("NAIP NDVI returned too few valid pixels for local calibration.")
    ndvi_open = float(np.quantile(valid_ndvi, 0.30))
    ndvi_dense = float(np.quantile(valid_ndvi, 0.78))
    if ndvi_dense - ndvi_open < 0.035:
        ndvi_dense = ndvi_open + 0.035
    vegetation = smoothstep(ndvi, ndvi_open, ndvi_dense)
    vegetation_method = "NAIP NIR/red NDVI calibrated to local 30th–78th percentiles"
    vegetation_stats = {
        "ndviP05": round(float(np.quantile(valid_ndvi, 0.05)), 4),
        "ndviP30Open": round(ndvi_open, 4),
        "ndviP50": round(float(np.quantile(valid_ndvi, 0.50)), 4),
        "ndviP78Dense": round(ndvi_dense, 4),
        "ndviP95": round(float(np.quantile(valid_ndvi, 0.95)), 4),
    }
else:
    # Fallback if an unexpected mosaic omits NIR: calibrate excessive-green
    # locally so the forest/open-ground split remains specific to this imagery.
    exg = 2.0 * green - red - blue
    valid_exg = exg[np.isfinite(exg)]
    exg_open = float(np.quantile(valid_exg, 0.30))
    exg_dense = float(np.quantile(valid_exg, 0.78))
    vegetation = smoothstep(exg, exg_open, exg_dense)
    vegetation_method = "NAIP visible-band excessive-green fallback calibrated locally"
    vegetation_stats = {
        "exgP30Open": round(exg_open, 2),
        "exgP78Dense": round(exg_dense, 2),
    }

vegetation = gaussian_filter(vegetation.astype(np.float32), sigma=0.8)
local_canopy = uniform_filter(vegetation, size=3, mode="nearest")
brightness = clamp01((red + green + blue) / (3.0 * 255.0))
open_ground = clamp01((1.0 - vegetation) * (0.58 + 0.42 * smoothstep(brightness, 0.18, 0.58)))

radius_px = max(5, int(round(550.0 / ((X_METERS + Y_METERS) / 2.0))))
size = radius_px * 2 + 1
local_low = minimum_filter(dem, size=size, mode="nearest")
local_high = maximum_filter(dem, size=size, mode="nearest")
local_relief = np.maximum(0.0, local_high - local_low)
relative_height = clamp01((dem - local_low) / 125.0)
prominence = clamp01((dem - local_low) / np.maximum(local_relief, 1.0))
relief_score = clamp01(local_relief / 145.0)
smoothed_dem = gaussian_filter(dem, sigma=max(2.0, 120.0 / ((X_METERS + Y_METERS) / 2.0)))
convexity = clamp01((dem - smoothed_dem + 5.0) / 28.0)

elevation_q25 = float(np.quantile(dem, 0.25))
elevation_q90 = float(np.quantile(dem, 0.90))
regional_elevation = clamp01((dem - elevation_q25) / max(1.0, elevation_q90 - elevation_q25))

grad_y, grad_x = np.gradient(dem, Y_METERS, X_METERS)
slope_degrees = np.degrees(np.arctan(np.hypot(grad_x, grad_y))).astype(np.float32)
aspect = (np.degrees(np.arctan2(-grad_x, grad_y)) + 360.0) % 360.0

ridge_core = clamp01(
    0.36 * relative_height
    + 0.25 * prominence
    + 0.20 * convexity
    + 0.12 * relief_score
    + 0.07 * regional_elevation
)

# Explicit ridge/spur support. Positive topographic position at both a short and
# broader scale distinguishes crest/shoulder terrain from nearby hollows.
fine_sigma = max(1.5, 70.0 / ((X_METERS + Y_METERS) / 2.0))
broad_sigma = max(4.0, 280.0 / ((X_METERS + Y_METERS) / 2.0))
fine_tpi = dem - gaussian_filter(dem, sigma=fine_sigma)
broad_tpi = dem - gaussian_filter(dem, sigma=broad_sigma)
fine_ridge = smoothstep(fine_tpi, -1.5, 10.0)
broad_ridge = smoothstep(broad_tpi, -4.0, 28.0)
height_gate = smoothstep(relative_height, 0.18, 0.62)
prominence_gate = smoothstep(prominence, 0.14, 0.58)

# V10 topological geometry: derive the actual drainage-divide skeleton first.
# Sunrise, sunset, aerial, and trail inputs are not allowed to create or move it.
bilateral_relief_m, bilateral_ridge = bilateral_ridge_relief(dem)
ridge_skeleton, raw_ridge_skeleton, watershed_basin_count, watershed_minima_depth_m = topological_ridge_skeleton(
    dem,
    relative_height,
    prominence,
    broad_tpi,
    bilateral_relief_m,
    convexity,
)

mean_cell_m = (X_METERS + Y_METERS) / 2.0
CREST_CORRIDOR_METERS = 12.0
ridge_distance_m = distance_transform_edt(
    ~ridge_skeleton,
    sampling=(Y_METERS, X_METERS),
)
skeleton_proximity = clamp01(1.0 - ridge_distance_m / CREST_CORRIDOR_METERS)
crest_mask = ridge_distance_m <= CREST_CORRIDOR_METERS

# The score can vary inside the corridor, but the corridor location itself is
# determined only by distance to the topological ridge skeleton.
crest_strength = clamp01(
    0.58 * skeleton_proximity
    + 0.20 * bilateral_ridge
    + 0.10 * ridge_core
    + 0.07 * convexity
    + 0.05 * broad_ridge
)
ridge_corridor = crest_strength * crest_mask.astype(np.float32)

valley_zone = (
    (~crest_mask)
    & (
        (relative_height < 0.28)
        | (broad_tpi < -2.0)
        | ((fine_tpi < -0.5) & (prominence < 0.30))
    )
)

valley_penalty = (
    0.22 * clamp01((0.34 - relative_height) / 0.34)
    + 0.16 * clamp01((0.30 - prominence) / 0.30)
    + 0.10 * clamp01((-broad_tpi - 1.0) / 18.0)
)

sunrise_direction, sunrise_horizon, sunrise_drop, sunrise_near_drop, sunrise_aerial = directional_metrics(dem, vegetation, SUNRISE_AZIMUTHS)
sunset_direction, sunset_horizon, sunset_drop, sunset_near_drop, sunset_aerial = directional_metrics(dem, vegetation, SUNSET_AZIMUTHS)
sunrise_aspect = aspect_score(aspect, slope_degrees, SUNRISE_AZIMUTHS)
sunset_aspect = aspect_score(aspect, slope_degrees, SUNSET_AZIMUTHS)

# V6: seed compact overlook/outcrop lobes instead of whole ridge corridors.
# A candidate must sit on high/convex terrain AND show a short-range terrain
# break toward the sunrise or sunset horizon. This follows the reference map's
# small colored lobes at projecting noses and cliff edges.
sunrise_canopy_penalty = local_canopy * (1.0 - 0.78 * sunrise_near_drop)
sunset_canopy_penalty = local_canopy * (1.0 - 0.78 * sunset_near_drop)

sunrise_view = clamp01(
    0.34 * sunrise_near_drop
    + 0.24 * sunrise_drop
    + 0.18 * sunrise_horizon
    + 0.15 * sunrise_aerial
    + 0.09 * sunrise_aspect
)
sunset_view = clamp01(
    0.34 * sunset_near_drop
    + 0.24 * sunset_drop
    + 0.18 * sunset_horizon
    + 0.15 * sunset_aerial
    + 0.09 * sunset_aspect
)

trail_elements, trail_overpass_endpoint = fetch_trail_elements()
trail_lines = []
for element in trail_elements:
    xy = coords(element.get("geometry"))
    if len(xy) >= 2:
        try:
            trail_lines.append(LineString(xy))
        except Exception:
            pass

trail_mask = rasterize(
    [(mapping(shape), 1) for shape in trail_lines],
    out_shape=(ROWS, COLS),
    transform=TRANSFORM,
    fill=0,
    all_touched=True,
    dtype="uint8",
).astype(bool)
trail_distance_m = distance_transform_edt(~trail_mask, sampling=(Y_METERS, X_METERS))
trail_support = 1.0 - smoothstep(trail_distance_m, 10.0, 55.0)

# Crest/nose support is intentionally narrower than the v5 ridge corridor.
# Strong positive TPI plus convexity/prominence favors projecting ridge noses
# and cliff rims, not broad wooded plateau interiors.
# Geometry remains LiDAR-only and is centered on the divide skeleton.
overlook_support = clamp01(
    0.52 * skeleton_proximity
    + 0.20 * bilateral_ridge
    + 0.12 * convexity
    + 0.09 * prominence_gate
    + 0.07 * height_gate
)
overlook_support *= crest_mask.astype(np.float32)

site_open = clamp01(
    0.68 * (1.0 - local_canopy)
    + 0.32 * open_ground
)
sunrise_opening_gate = 0.18 + 0.82 * smoothstep(
    0.62 * sunrise_aerial + 0.38 * site_open,
    0.20,
    0.70,
)
sunset_opening_gate = 0.18 + 0.82 * smoothstep(
    0.62 * sunset_aerial + 0.38 * site_open,
    0.20,
    0.70,
)

# Both colors are uncommon: require two independently excellent overlook
# sectors rather than two merely plausible ridge scores.
dual_open = (
    (sunrise_view >= DUAL_VIEW_MIN)
    & (sunset_view >= DUAL_VIEW_MIN)
    & (sunrise_near_drop >= 0.72)
    & (sunset_near_drop >= 0.72)
    & (overlook_support >= 0.68)
    & (sunrise_aerial >= 0.42)
    & (sunset_aerial >= 0.42)
)
view_difference = sunrise_view - sunset_view
sunrise_direction_gate = np.where(
    dual_open,
    1.0,
    smoothstep(view_difference, 0.025, 0.16),
).astype(np.float32)
sunset_direction_gate = np.where(
    dual_open,
    1.0,
    smoothstep(-view_difference, 0.025, 0.16),
).astype(np.float32)

sunrise_edge_gate = smoothstep(sunrise_near_drop, NEAR_DROP_MIN, 0.82)
sunset_edge_gate = smoothstep(sunset_near_drop, NEAR_DROP_MIN, 0.82)
support_gate = smoothstep(overlook_support, OVERLOOK_SUPPORT_MIN, 0.78)

sunrise_seed = clamp01(
    (
        0.34 * overlook_support
        + 0.34 * sunrise_view
        + 0.16 * sunrise_near_drop
        + 0.08 * regional_elevation
        + 0.08 * relief_score
        - 0.22 * sunrise_canopy_penalty
        - valley_penalty
    )
    * support_gate
    * sunrise_edge_gate
    * sunrise_opening_gate
    * sunrise_direction_gate
)
sunset_seed = clamp01(
    (
        0.34 * overlook_support
        + 0.34 * sunset_view
        + 0.16 * sunset_near_drop
        + 0.08 * regional_elevation
        + 0.08 * relief_score
        - 0.22 * sunset_canopy_penalty
        - valley_penalty
    )
    * support_gate
    * sunset_edge_gate
    * sunset_opening_gate
    * sunset_direction_gate
)

# Trail support is applied only after a LiDAR/aerial candidate exists. This
# small multiplier can increase confidence at an already valid overlook but can
# never create geometry, shift a seed, or pull a lobe toward the trail.
trail_confidence = 1.0 + 0.03 * trail_support
sunrise_seed = clamp01(sunrise_seed * trail_confidence)
sunset_seed = clamp01(sunset_seed * trail_confidence)

# The reference map uses compact lobes: strong at the exposed edge, fading only
# a short distance back onto the same crest. Keep propagation to roughly
# 20–120 m and multiply every step by high-ground support.
def crest_connected_propagation(seed):
    """
    Propagate only through connected crest pixels. This is a graph-like
    geodesic walk over the raster mask, not a 2-D blur, so a seed cannot jump
    across a hollow or drift toward a nearby trail.
    """
    support = (
        crest_mask
        & (~valley_zone)
        & (skeleton_proximity > 0.0)
        & (crest_strength >= 0.36)
    )
    result = np.where(support, seed, 0.0).astype(np.float32)
    current = result.copy()

    mean_cell_m = (X_METERS + Y_METERS) / 2.0
    max_distance_m = 100.0
    steps = max(1, int(round(max_distance_m / mean_cell_m)))
    # About 18% of source intensity remains at the 100 m extent.
    decay = math.exp(math.log(0.18) / steps)
    support_weight = (
        0.90
        + 0.10 * smoothstep(crest_strength, 0.40, 0.72)
    ).astype(np.float32)

    for _ in range(steps):
        current = maximum_filter(current, size=3, mode="constant", cval=0.0)
        current = current * decay * support_weight
        current[~support] = 0.0
        result = np.maximum(result, current)

    result[~support] = 0.0
    return clamp01(result)


sunrise_score = crest_connected_propagation(sunrise_seed)
sunset_score = crest_connected_propagation(sunset_seed)

sunrise_candidate = (
    crest_mask
    & (overlook_support >= OVERLOOK_SUPPORT_MIN)
    & (sunrise_near_drop >= NEAR_DROP_MIN)
    & (sunrise_view >= DIRECTIONAL_VIEW_MIN)
    & crest_mask
    & ((sunrise_aerial >= 0.24) | (site_open >= 0.30))
    & (~valley_zone)
)
sunset_candidate = (
    crest_mask
    & (overlook_support >= OVERLOOK_SUPPORT_MIN)
    & (sunset_near_drop >= NEAR_DROP_MIN)
    & (sunset_view >= DIRECTIONAL_VIEW_MIN)
    & crest_mask
    & ((sunset_aerial >= 0.24) | (site_open >= 0.30))
    & (~valley_zone)
)
sunrise_score[~sunrise_candidate] = 0.0
sunset_score[~sunset_candidate] = 0.0

water_elements, overpass_used = fetch_water_elements()
water_polygons, water_lines = water_shapes(water_elements)
poly_mask = rasterize(
    [(mapping(shape), 1) for shape in water_polygons],
    out_shape=(ROWS, COLS),
    transform=TRANSFORM,
    fill=0,
    all_touched=True,
    dtype="uint8",
).astype(bool)
line_mask = rasterize(
    [(mapping(shape), 1) for shape in water_lines],
    out_shape=(ROWS, COLS),
    transform=TRANSFORM,
    fill=0,
    all_touched=True,
    dtype="uint8",
).astype(bool)
water_mask = poly_mask | line_mask
sunrise_score[water_mask] = 0.0
sunset_score[water_mask] = 0.0

# Preserve the hard water mask after ridge-constrained propagation.
sunrise_score[water_mask] = 0.0
sunset_score[water_mask] = 0.0

valid = ~water_mask
def breaks(score, candidate_mask):
    values = score[valid & candidate_mask & (score > 0.0)]
    if values.size < 1000:
        raise RuntimeError("Too few ridge/viewshed candidates for stable display calibration.")
    return {
        "display": float(np.quantile(values, DISPLAY_CANDIDATE_QUANTILE)),
        "strong": float(np.quantile(values, STRONG_CANDIDATE_QUANTILE)),
        "peak": float(np.quantile(values, PEAK_CANDIDATE_QUANTILE)),
    }

sunrise_breaks = breaks(sunrise_score, sunrise_candidate)
sunset_breaks = breaks(sunset_score, sunset_candidate)

def display_strength(score, b):
    strength = clamp01((score - b["display"]) / max(0.001, b["peak"] - b["display"]))
    return np.where(score >= b["display"], strength, 0.0).astype(np.float32)

sunrise_strength = display_strength(sunrise_score, sunrise_breaks)
sunset_strength = display_strength(sunset_score, sunset_breaks)
both = sunrise_strength + sunset_strength
visible = both > 0.0
weight_sum = np.maximum(both, 1e-6)
rgb = (
    sunrise_strength[..., None] * SUNRISE_RGB
    + sunset_strength[..., None] * SUNSET_RGB
) / weight_sum[..., None]
alpha_strength = np.maximum(sunrise_strength, sunset_strength)
alpha = np.where(visible, 0.10 + 0.76 * np.power(alpha_strength, 0.85), 0.0)
rgba = np.zeros((ROWS, COLS, 4), dtype=np.uint8)
rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
rgba[..., 3] = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)
rgba[water_mask, 3] = 0

OUT_DIR.mkdir(parents=True, exist_ok=True)
Image.fromarray(rgba, mode="RGBA").save(PNG_PATH, optimize=True, compress_level=9)

# Staging calibration diagnostics. These are intentionally separate from the
# final composite so the user can verify the LiDAR crest model first.
skeleton_diag = diagnostic_rgba(ridge_skeleton.astype(np.float32), (255, 255, 80), 0.98)
crest_diag = diagnostic_rgba(skeleton_proximity * crest_mask.astype(np.float32), (255, 176, 32), 0.78)
overlook_diag_strength = clamp01(overlook_support * np.maximum(sunrise_near_drop, sunset_near_drop))
overlook_diag = diagnostic_rgba(overlook_diag_strength, (255, 70, 220), 0.82)
open_diag = diagnostic_rgba(site_open, (70, 220, 120), 0.66)
sunrise_diag_strength = clamp01(sunrise_view * sunrise_edge_gate * sunrise_direction_gate * crest_mask.astype(np.float32))
sunset_diag_strength = clamp01(sunset_view * sunset_edge_gate * sunset_direction_gate * crest_mask.astype(np.float32))
sunrise_diag = diagnostic_rgba(sunrise_diag_strength, (255, 111, 97), 0.80)
sunset_diag = diagnostic_rgba(sunset_diag_strength, (64, 85, 216), 0.80)

Image.fromarray(skeleton_diag, mode="RGBA").save(DIAG_SKELETON_PATH, optimize=True, compress_level=9)
Image.fromarray(crest_diag, mode="RGBA").save(DIAG_CREST_PATH, optimize=True, compress_level=9)
Image.fromarray(overlook_diag, mode="RGBA").save(DIAG_OVERLOOK_PATH, optimize=True, compress_level=9)
Image.fromarray(open_diag, mode="RGBA").save(DIAG_OPEN_PATH, optimize=True, compress_level=9)
Image.fromarray(sunrise_diag, mode="RGBA").save(DIAG_SUNRISE_PATH, optimize=True, compress_level=9)
Image.fromarray(sunset_diag, mode="RGBA").save(DIAG_SUNSET_PATH, optimize=True, compress_level=9)

if OLD_SVG_PATH.exists():
    OLD_SVG_PATH.unlink()

def percent(mask):
    return round(float(np.count_nonzero(mask)) / mask.size * 100.0, 2)

metadata = {
    "version": VERSION,
    "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "source": {
        "id": "rrgh-pinch-em-tight-ridge-skeleton-v10",
        "elevation": {
            "id": "usgs-3dep-bare-earth-dem",
            "service": ELEVATION_SERVICE,
            "pixelType": "F32",
        },
        "aerial": {
            "id": "usda-naip-four-band",
            "service": NAIP_SERVICE,
            "bandsRequested": [0, 1, 2, 3],
            "vegetationMethod": vegetation_method,
            "vegetationCalibration": vegetation_stats,
        },
        "trailSupport": {
            "id": "openstreetmap-trails-pilot-support",
            "attribution": "© OpenStreetMap contributors",
            "via": "Overpass API",
            "endpointUsed": trail_overpass_endpoint,
            "lineFeatures": len(trail_lines),
            "role": "late confidence only; trail proximity cannot create, move, or broaden crest/outcrop geometry"
        },
        "waterMask": {
            "id": "openstreetmap-water",
            "attribution": "© OpenStreetMap contributors",
            "via": "Overpass API",
            "endpointsUsed": overpass_used,
            "polygonFeatures": len(water_polygons),
            "flowlineFeatures": len(water_lines),
        },
    },
    "bounds": BOUNDS,
    "grid": {
        "cols": COLS,
        "rows": ROWS,
        "approximateCellMeters": [round(X_METERS, 1), round(Y_METERS, 1)],
        "output": "PNG RGBA",
    },
    "method": (
        "Pinch-Em-Tight topological ridge-skeleton calibration pilot. Two-meter bare-earth LiDAR is smoothed only enough to suppress tiny pits, hydrologic basins are delineated by watershed segmentation, their drainage divides are thinned to a ridge skeleton, and only a narrow crest corridor around that skeleton is eligible before any aerial, trail, or sunrise/sunset evidence is considered. "
        "then requires a near-field terrain break in the sunrise or sunset direction in addition to the longer horizon, aspect, and NAIP "
        "aerial openness. Strong seeds represent likely overlook/outcrop edges; display propagation is deliberately short and constrained "
        "to the same high-ground crest so lobes fade back from an edge rather than painting whole ridge systems or adjacent valleys. The "
        "weaker sunrise/sunset direction is suppressed unless both overlook sectors are independently excellent; mapped water is excluded."
    ),
    "seasonalAzimuths": {"sunrise": SUNRISE_AZIMUTHS, "sunset": SUNSET_AZIMUTHS},
    "ridgeTopology": {
        "method": "watershed drainage divides from smoothed bare-earth LiDAR",
        "watershedBasinCount": watershed_basin_count,
        "minimaDepthMeters": watershed_minima_depth_m,
        "crestCorridorMeters": CREST_CORRIDOR_METERS,
        "trailOrAerialAffectsSkeleton": False
    },
    "thresholds": {
        "displayCandidateQuantile": DISPLAY_CANDIDATE_QUANTILE,
        "strongCandidateQuantile": STRONG_CANDIDATE_QUANTILE,
        "peakCandidateQuantile": PEAK_CANDIDATE_QUANTILE,
        "overlookSupportMin": OVERLOOK_SUPPORT_MIN,
        "nearDropMin": NEAR_DROP_MIN,
        "directionalViewMin": DIRECTIONAL_VIEW_MIN,
        "dualViewMin": DUAL_VIEW_MIN,
        "sunriseDisplayScore": round(sunrise_breaks["display"], 4),
        "sunriseStrongScore": round(sunrise_breaks["strong"], 4),
        "sunsetDisplayScore": round(sunset_breaks["display"], 4),
        "sunsetStrongScore": round(sunset_breaks["strong"], 4),
    },
    "coverage": {
        "waterMaskPercent": percent(water_mask),
        "sunriseDisplayPercent": percent(sunrise_strength > 0),
        "sunsetDisplayPercent": percent(sunset_strength > 0),
        "sunriseStrongPercent": percent(sunrise_score >= sunrise_breaks["strong"]),
        "sunsetStrongPercent": percent(sunset_score >= sunset_breaks["strong"]),
        "denseCanopyPercent": percent(local_canopy >= 0.72),
        "highRidgeCorePercent": percent(ridge_core >= 0.62),
        "ridgeCorridorPercent": percent(ridge_corridor >= 0.38),
        "overlookSupportPercent": percent(overlook_support >= OVERLOOK_SUPPORT_MIN),
        "ridgeSkeletonPercent": percent(ridge_skeleton),
        "rawRidgeSkeletonPercent": percent(raw_ridge_skeleton),
        "crestMaskPercent": percent(crest_mask),
        "watershedBasinCount": watershed_basin_count,
        "bilateralRidgeCorePercent": percent(bilateral_relief_m >= 5.0),
        "trailSupportPercent": percent(trail_support >= 0.5),
        "openGroundPercent": percent(open_ground >= 0.55),
        "sunriseSeedPercent": percent(sunrise_seed > 0.10),
        "sunsetSeedPercent": percent(sunset_seed > 0.10),
        "valleyZonePercent": percent(valley_zone),
        "sunriseValleyLeakPercent": percent((sunrise_strength > 0) & valley_zone),
        "sunsetValleyLeakPercent": percent((sunset_strength > 0) & valley_zone),
        "dualDisplayPercent": percent((sunrise_strength > 0) & (sunset_strength > 0)),
    },
    "diagnostics": [
        {"id": "ridge-skeleton", "file": DIAG_SKELETON_PATH.name, "meaning": "thin LiDAR watershed/divide ridge skeleton"},
        {"id": "crest", "file": DIAG_CREST_PATH.name, "meaning": "12 m crest corridor around the topological ridge skeleton"},
        {"id": "overlook", "file": DIAG_OVERLOOK_PATH.name, "meaning": "crest-qualified overlook/outcrop support"},
        {"id": "open-ground", "file": DIAG_OPEN_PATH.name, "meaning": "NAIP/local-site open-ground confidence"},
        {"id": "sunrise-pass", "file": DIAG_SUNRISE_PATH.name, "meaning": "crest-qualified sunrise directional pass"},
        {"id": "sunset-pass", "file": DIAG_SUNSET_PATH.name, "meaning": "crest-qualified sunset directional pass"}
    ],
    "display": {
        "sunriseColor": "#ff6f61",
        "sunsetColor": "#4055d8",
        "maximumOpacity": 0.86,
        "designIntent": "Calibration pilot: a thin LiDAR watershed/divide skeleton defines the ridge centerline first; final geometry is limited to a roughly 12 m corridor around that line. Aerial and trail evidence cannot move the skeleton. Sunrise/sunset scoring and connected propagation happen only inside that corridor.",
    },
    "calibrationArea": {
        "name": "Pinch-Em-Tight / Sheltowee suspension-bridge pilot",
        "status": "staging topological-ridge calibration only",
        "expandOnlyAfterVisualApproval": True,
        "reviewOrder": [
            "LiDAR ridge skeleton",
            "Narrow crest corridor",
            "Overlook/outcrop candidates",
            "Aerial open-ground confidence",
            "Sunrise directional pass",
            "Sunset directional pass",
            "Final sunrise/sunset composite"
        ]
    },
    "calibrationIntent": [
        "First verify that the thin LiDAR watershed/divide skeleton follows the actual ridge tops in the user-provided Pinch-Em-Tight screenshots; no trail or aerial input is permitted to alter that line.",
        "Only after ridge placement is correct should aerial openness and directional sunrise/sunset scoring affect the seed; trail support may only slightly increase confidence in an already valid seed.",
        "Match the compact lobe shape of the user-provided overlook reference rather than painting whole ridge corridors.",
        "Require a near-field terrain break toward the sunrise/sunset horizon before seeding color.",
        "Propagate the display by connected crest pixels rather than Gaussian/radial blur, preventing drift across slopes, hollows, or toward nearby trails.",
        "Suppress valley-floor trail endpoints even when a seasonal sun azimuth is geometrically favorable.",
        "Reduce forested ridge false positives when NAIP indicates dense vegetation in the viewing sector.",
        "Favor projecting ridge/cliff noses with terrain falling away toward the sunrise or sunset horizon.",
        "Suppress the weaker sunrise/sunset color unless both viewing sectors are independently strong.",
    ],
    "limitations": [
        "NAIP vegetation/open-ground classification is a proxy, not a direct tree-by-tree canopy-height model.",
        "Bare-earth terrain and aerial imagery do not capture every small obstruction, seasonal leaf-off condition, access issue, or current weather condition.",
        "The layer is a generalized planning aid and does not guarantee a visible sunrise, sunset, legal access, or a good photographic view.",
    ],
}
META_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
print(json.dumps(metadata["coverage"], indent=2))
print(f"Generated {PNG_PATH} ({COLS}x{ROWS})")
