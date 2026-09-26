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
from scipy.ndimage import gaussian_filter, maximum_filter, minimum_filter, uniform_filter
from shapely.geometry import LineString, Polygon, mapping

ELEVATION_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
NAIP_SERVICE = "https://apps.geo.fpac.usda.gov/geo-imagery/rest/services/naip/conus_naip/ImageServer"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.maprva.org/api/interpreter",
]
BOUNDS = {"west": -84.02, "south": 37.52, "east": -83.18, "north": 38.15}
PIXEL_METERS = 25.0
SUNRISE_AZIMUTHS = [58.0, 90.0, 121.0]
SUNSET_AZIMUTHS = [239.0, 270.0, 302.0]
SUNRISE_RGB = np.array([255.0, 111.0, 97.0], dtype=np.float32)
SUNSET_RGB = np.array([64.0, 85.0, 216.0], dtype=np.float32)
DISPLAY_CANDIDATE_QUANTILE = 0.65
STRONG_CANDIDATE_QUANTILE = 0.88
PEAK_CANDIDATE_QUANTILE = 0.98
RIDGE_CORRIDOR_MIN = 0.38
DIRECTIONAL_VIEW_MIN = 0.46
DUAL_VIEW_MIN = 0.78
VERSION = 5

OUT_DIR = Path("public/data/map")
PNG_PATH = OUT_DIR / "sunrise-sunset-potential.png"
META_PATH = OUT_DIR / "sunrise-sunset-potential.meta.json"
OLD_SVG_PATH = OUT_DIR / "sunrise-sunset-potential.svg"

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

def directional_metrics(dem, vegetation, azimuths):
    best_score = np.zeros(dem.shape, dtype=np.float32)
    best_open = np.zeros(dem.shape, dtype=np.float32)
    best_drop = np.zeros(dem.shape, dtype=np.float32)
    best_aerial = np.zeros(dem.shape, dtype=np.float32)

    # Evaluate each representative seasonal direction plus a small viewing fan.
    for azimuth in azimuths:
        seasonal_score = np.zeros(dem.shape, dtype=np.float32)
        seasonal_open = np.zeros(dem.shape, dtype=np.float32)
        seasonal_drop = np.zeros(dem.shape, dtype=np.float32)
        seasonal_aerial = np.zeros(dem.shape, dtype=np.float32)

        for fan_offset, fan_weight in [(-24.0, 0.72), (-12.0, 0.88), (0.0, 1.0), (12.0, 0.88), (24.0, 0.72)]:
            bearing = math.radians(azimuth + fan_offset)
            east = math.sin(bearing)
            north = math.cos(bearing)

            max_angle = np.full(dem.shape, -90.0, dtype=np.float32)
            max_drop = np.zeros(dem.shape, dtype=np.float32)
            veg_samples = []

            for distance_px in [2, 4, 8, 16, 32, 64, 96, 128]:
                dr = int(round(-north * distance_px))
                dc = int(round(east * distance_px))
                target = shift(dem, dr, dc)
                horizontal = max(1.0, math.hypot(dr * Y_METERS, dc * X_METERS))
                angle = np.degrees(np.arctan2(target - dem, horizontal)).astype(np.float32)
                valid = np.isfinite(target)
                max_angle = np.where(valid, np.maximum(max_angle, angle), max_angle)
                max_drop = np.where(valid, np.maximum(max_drop, dem - target), max_drop)

            for distance_px in [1, 2, 3, 5, 8, 12]:
                dr = int(round(-north * distance_px))
                dc = int(round(east * distance_px))
                sample = shift(vegetation, dr, dc, fill=1.0)
                veg_samples.append(sample)

            terrain_open = clamp01((7.0 - max_angle) / 14.0)
            drop_score = smoothstep(max_drop, 10.0, 95.0)
            sector_vegetation = np.mean(np.stack(veg_samples, axis=0), axis=0)
            aerial_open = clamp01(1.0 - sector_vegetation)

            direction_score = (
                0.43 * terrain_open
                + 0.37 * drop_score
                + 0.20 * aerial_open
            ) * fan_weight

            seasonal_score = np.maximum(seasonal_score, direction_score)
            seasonal_open = np.maximum(seasonal_open, terrain_open * fan_weight)
            seasonal_drop = np.maximum(seasonal_drop, drop_score * fan_weight)
            seasonal_aerial = np.maximum(seasonal_aerial, aerial_open * fan_weight)

        best_score = np.maximum(best_score, seasonal_score)
        best_open = np.maximum(best_open, seasonal_open)
        best_drop = np.maximum(best_drop, seasonal_drop)
        best_aerial = np.maximum(best_aerial, seasonal_aerial)

    return best_score, best_open, best_drop, best_aerial

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

print(f"V5 ridge-constrained photographic viewshed grid: {COLS} x {ROWS} at approximately {X_METERS:.1f} m x {Y_METERS:.1f} m")
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

ridge_corridor = clamp01(
    0.30 * ridge_core
    + 0.24 * broad_ridge
    + 0.17 * fine_ridge
    + 0.17 * height_gate
    + 0.12 * prominence_gate
)
# The support surface itself fades down a shoulder, but collapses before the
# valley floor. This is what keeps the displayed gradient on connected high ground.
ridge_corridor *= smoothstep(relative_height, 0.12, 0.48)
ridge_corridor *= smoothstep(prominence, 0.08, 0.44)

valley_zone = (relative_height < 0.16) | ((prominence < 0.16) & (broad_tpi < -3.0))
valley_penalty = (
    0.22 * clamp01((0.34 - relative_height) / 0.34)
    + 0.16 * clamp01((0.30 - prominence) / 0.30)
    + 0.10 * clamp01((-broad_tpi - 1.0) / 18.0)
)

sunrise_direction, sunrise_horizon, sunrise_drop, sunrise_aerial = directional_metrics(dem, vegetation, SUNRISE_AZIMUTHS)
sunset_direction, sunset_horizon, sunset_drop, sunset_aerial = directional_metrics(dem, vegetation, SUNSET_AZIMUTHS)
sunrise_aspect = aspect_score(aspect, slope_degrees, SUNRISE_AZIMUTHS)
sunset_aspect = aspect_score(aspect, slope_degrees, SUNSET_AZIMUTHS)

# Dense canopy matters most when the terrain does not sharply fall away in the
# viewing direction. A true cliff/nose can still see over lower trees, while a
# forested shoulder without a sharp drop is strongly downgraded.
sunrise_canopy_penalty = local_canopy * (1.0 - 0.72 * sunrise_drop)
sunset_canopy_penalty = local_canopy * (1.0 - 0.72 * sunset_drop)

sunrise_view = clamp01(
    0.40 * sunrise_drop
    + 0.28 * sunrise_horizon
    + 0.20 * sunrise_aerial
    + 0.12 * sunrise_aspect
)
sunset_view = clamp01(
    0.40 * sunset_drop
    + 0.28 * sunset_horizon
    + 0.20 * sunset_aerial
    + 0.12 * sunset_aspect
)

# A point may legitimately see both directions only when both viewsheds are
# genuinely strong on ridge terrain. Otherwise, favor the better direction and
# suppress the weaker color instead of painting purple/alternating noise.
dual_open = (
    (sunrise_view >= DUAL_VIEW_MIN)
    & (sunset_view >= DUAL_VIEW_MIN)
    & (ridge_corridor >= 0.64)
    & (sunrise_aerial >= 0.35)
    & (sunset_aerial >= 0.35)
)
view_difference = sunrise_view - sunset_view
sunrise_direction_gate = np.where(
    dual_open,
    1.0,
    smoothstep(view_difference, 0.02, 0.14),
).astype(np.float32)
sunset_direction_gate = np.where(
    dual_open,
    1.0,
    smoothstep(-view_difference, 0.02, 0.14),
).astype(np.float32)

sunrise_opening_gate = 0.20 + 0.80 * smoothstep(sunrise_aerial, 0.18, 0.68)
sunset_opening_gate = 0.20 + 0.80 * smoothstep(sunset_aerial, 0.18, 0.68)
ridge_seed_gate = smoothstep(ridge_corridor, 0.44, 0.76)

sunrise_seed = clamp01(
    (
        0.42 * ridge_corridor
        + 0.40 * sunrise_view
        + 0.10 * regional_elevation
        + 0.08 * relief_score
        - valley_penalty
        - 0.17 * sunrise_canopy_penalty
    )
    * ridge_seed_gate
    * sunrise_opening_gate
    * sunrise_direction_gate
)
sunset_seed = clamp01(
    (
        0.42 * ridge_corridor
        + 0.40 * sunset_view
        + 0.10 * regional_elevation
        + 0.08 * relief_score
        - valley_penalty
        - 0.17 * sunset_canopy_penalty
    )
    * ridge_seed_gate
    * sunset_opening_gate
    * sunset_direction_gate
)

# Allow the gradient to travel along supported ridge/shoulder terrain but not
# radially downhill. Multiplying every smoothing scale by ridge support prevents
# strong seeds from bleeding across adjacent hollows.
def ridge_constrained_gradient(seed):
    support = smoothstep(ridge_corridor, 0.22, 0.72)
    core = seed
    near = gaussian_filter(seed, sigma=1.15) * support
    shoulder = gaussian_filter(seed, sigma=2.6) * np.power(support, 1.15)
    extended = gaussian_filter(seed, sigma=4.8) * np.power(support, 1.45)
    result = np.maximum.reduce([
        core,
        0.92 * near,
        0.72 * shoulder,
        0.46 * extended,
    ])
    result[valley_zone] = 0.0
    return clamp01(result)

sunrise_score = ridge_constrained_gradient(sunrise_seed)
sunset_score = ridge_constrained_gradient(sunset_seed)

# Do not force a sunrise/sunset classification where neither directional
# viewshed is credible. These masks set the eligible ridge corridors.
sunrise_candidate = (
    (ridge_corridor >= RIDGE_CORRIDOR_MIN)
    & (sunrise_view >= DIRECTIONAL_VIEW_MIN)
    & (~valley_zone)
)
sunset_candidate = (
    (ridge_corridor >= RIDGE_CORRIDOR_MIN)
    & (sunset_view >= DIRECTIONAL_VIEW_MIN)
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
if OLD_SVG_PATH.exists():
    OLD_SVG_PATH.unlink()

def percent(mask):
    return round(float(np.count_nonzero(mask)) / mask.size * 100.0, 2)

metadata = {
    "version": VERSION,
    "generatedAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "source": {
        "id": "rrgh-ridge-constrained-viewshed-v5",
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
        "Ridge-constrained directional photographic viewshed proxy. High-resolution bare-earth terrain first defines ridge/spur/cliff-nose "
        "support using relative height, prominence, convexity, and positive topographic position at multiple scales. Sunrise and sunset "
        "seeds then require directional terrain drop, low horizon, aspect, and NAIP aerial openness. Gradient propagation is multiplied by "
        "ridge support so color can fade along connected high ground without bleeding into adjacent valleys. The weaker sunrise/sunset "
        "direction is suppressed unless both viewing sectors are genuinely strong; actual mapped water is excluded."
    ),
    "seasonalAzimuths": {"sunrise": SUNRISE_AZIMUTHS, "sunset": SUNSET_AZIMUTHS},
    "thresholds": {
        "displayCandidateQuantile": DISPLAY_CANDIDATE_QUANTILE,
        "strongCandidateQuantile": STRONG_CANDIDATE_QUANTILE,
        "peakCandidateQuantile": PEAK_CANDIDATE_QUANTILE,
        "ridgeCorridorMin": RIDGE_CORRIDOR_MIN,
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
        "ridgeCorridorPercent": percent(ridge_corridor >= RIDGE_CORRIDOR_MIN),
        "valleyZonePercent": percent(valley_zone),
        "sunriseValleyLeakPercent": percent((sunrise_strength > 0) & valley_zone),
        "sunsetValleyLeakPercent": percent((sunset_strength > 0) & valley_zone),
        "dualDisplayPercent": percent((sunrise_strength > 0) & (sunset_strength > 0)),
    },
    "display": {
        "sunriseColor": "#ff6f61",
        "sunsetColor": "#4055d8",
        "maximumOpacity": 0.86,
        "designIntent": "Sunrise/sunset color follows supported ridge, spur, and cliff-nose terrain; strongest at exposed directional cores, fading along connected high ground and stopping before valley floors.",
    },
    "calibrationIntent": [
        "Keep gradients on ridge/spur support rather than allowing radial bleed into adjacent valleys.",
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
