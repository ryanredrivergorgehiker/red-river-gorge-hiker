#!/usr/bin/env python3
"""Generate a broad Red River Gorge LiDAR-only sunrise/sunset staging overlay.

Locked method carried forward from the accepted Pinch-Em-Tight pilot:
- KyFromAbove Phase 2 two-foot LiDAR-derived bare-earth DEM only.
- No aerial imagery, canopy model, trail geometry, waypoint geometry, or marked review points.
- Ignore terrain below 1,100 ft.
- Sunrise: east-facing cliff/rim lip.
- Sunset: west-facing cliff/rim lip.
- Hard color at the lip; fade inward/uphill on the same high ridge surface until the local crest.

The Gorge is processed in overlapping sectors to preserve pilot-scale DEM detail while
keeping memory bounded. Sector source arrays are fingerprinted. On later regeneration,
a changed source array fails closed instead of silently replacing the accepted source.
"""

from __future__ import annotations

import gc
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine
import requests
from scipy.ndimage import distance_transform_edt, gaussian_filter, label, maximum_filter
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "public/data/map/rrg-lidar-sun"
OUT_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-manifest.json"

DEM_SERVICE = (
    "https://kyraster.ky.gov/arcgis/rest/services/"
    "ElevationServices/Ky_DEM_KYAPED_2FT_Phase2_ZMeters_WGS84WM/ImageServer"
)

# Broad working envelope around the Red River Gorge Geological Area and adjoining
# high-ridge country. This is a processing envelope, not a legal/ownership boundary.
GORGE_BOUNDS_WGS84 = (-83.7000, 37.7700, -83.5200, 37.8900)
SECTOR_COLS = 4
SECTOR_ROWS = 3
SECTOR_OVERLAP_M = 180.0
TARGET_PIXEL_M = 2.5

MIN_ELEVATION_FT = 1100.0
MIN_ELEVATION_M = MIN_ELEVATION_FT / 3.280839895013123

TOP_MAX_SLOPE_DEG = 30.0
TRACE_MAX_SLOPE_DEG = 35.0
CLIFF_MIN_SLOPE_DEG = 45.0
EAST_ASPECT_MIN = 30.0
EAST_ASPECT_MAX = 150.0
WEST_ASPECT_MIN = 210.0
WEST_ASPECT_MAX = 330.0
LIP_SEARCH_PIXELS = 3.0
MIN_LIP_COMPONENT_PIXELS = 3
TRACE_MAX_METERS = 100.0
TRACE_FLAT_STOP_AFTER_METERS = 12.0
TRACE_TPI_MIN_METERS = -1.8

NEIGHBORS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),            (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

TO_WEB = Transformer.from_crs(4326, 3857, always_xy=True)
TO_LL = Transformer.from_crs(3857, 4326, always_xy=True)


def write_json(path: Path, value: object, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(value, separators=(",", ":"))
    else:
        text = json.dumps(value, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def load_existing_hashes() -> dict[str, str]:
    if not OUT_MANIFEST.exists():
        return {}
    try:
        manifest = json.loads(OUT_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}
    hashes: dict[str, str] = {}
    for sector in manifest.get("sectors", []):
        sector_id = str(sector.get("id", ""))
        digest = str(sector.get("demArraySha256", ""))
        if sector_id and digest:
            hashes[sector_id] = digest
    return hashes


def sector_grid() -> list[dict]:
    west, south, east, north = GORGE_BOUNDS_WGS84
    lon_step = (east - west) / SECTOR_COLS
    lat_step = (north - south) / SECTOR_ROWS
    result = []
    for row in range(SECTOR_ROWS):
        sector_north = north - row * lat_step
        sector_south = north - (row + 1) * lat_step
        for col in range(SECTOR_COLS):
            sector_west = west + col * lon_step
            sector_east = west + (col + 1) * lon_step
            result.append(
                {
                    "id": f"r{row+1}c{col+1}",
                    "row": row + 1,
                    "col": col + 1,
                    "boundsWgs84": [sector_west, sector_south, sector_east, sector_north],
                }
            )
    return result


def request_dem(bounds_wgs84: list[float]) -> tuple[np.ndarray, Affine, dict]:
    west, south, east, north = bounds_wgs84
    x1, y1 = TO_WEB.transform(west, south)
    x2, y2 = TO_WEB.transform(east, north)
    x1 -= SECTOR_OVERLAP_M
    y1 -= SECTOR_OVERLAP_M
    x2 += SECTOR_OVERLAP_M
    y2 += SECTOR_OVERLAP_M
    width = x2 - x1
    height = y2 - y1
    cols = max(2, int(math.ceil(width / TARGET_PIXEL_M)))
    rows = max(2, int(math.ceil(height / TARGET_PIXEL_M)))
    if cols > 15000 or rows > 4100:
        raise RuntimeError(f"Sector export exceeds service limit: {cols}x{rows}")
    params = {
        "f": "json",
        "bbox": f"{x1:.6f},{y1:.6f},{x2:.6f},{y2:.6f}",
        "bboxSR": "3857",
        "imageSR": "3857",
        "size": f"{cols},{rows}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "adjustAspectRatio": "false",
        "returnSquarePixels": "false",
    }
    response = requests.get(DEM_SERVICE + "/exportImage", params=params, timeout=180)
    response.raise_for_status()
    payload = response.json()
    href = payload.get("href")
    if not href:
        raise RuntimeError(f"DEM export did not return href: {payload}")
    tif = requests.get(href, timeout=240)
    tif.raise_for_status()
    with rasterio.MemoryFile(tif.content) as mem:
        with mem.open() as ds:
            dem = ds.read(1)
            transform = ds.transform
            if ds.crs.to_epsg() != 3857:
                raise RuntimeError(f"Unexpected DEM CRS: {ds.crs}")
            if not np.isfinite(dem).all():
                raise RuntimeError("DEM contains non-finite cells")
    return dem.astype("float32", copy=False), transform, params


def clean_components(mask: np.ndarray, minimum: int) -> np.ndarray:
    groups, count = label(mask)
    if count == 0:
        return mask
    sizes = np.bincount(groups.ravel())
    keep = np.zeros(count + 1, dtype=bool)
    keep[np.where(sizes >= minimum)[0]] = True
    keep[0] = False
    return keep[groups]


def terrain_fields(dem: np.ndarray, transform: Affine) -> dict[str, np.ndarray]:
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)
    gy, gx = np.gradient(dem, cell_y, cell_x)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    aspect = (np.degrees(np.arctan2(-gx, -gy)) + 360.0) % 360.0
    high = dem >= MIN_ELEVATION_M
    top = high & (slope <= TOP_MAX_SLOPE_DEG)
    cliff = slope >= CLIFF_MIN_SLOPE_DEG
    east_face = cliff & (aspect >= EAST_ASPECT_MIN) & (aspect <= EAST_ASPECT_MAX)
    west_face = cliff & (aspect >= WEST_ASPECT_MIN) & (aspect <= WEST_ASPECT_MAX)

    east_distance, east_indices = distance_transform_edt(~east_face, return_indices=True)
    west_distance, west_indices = distance_transform_edt(~west_face, return_indices=True)
    east_lip = clean_components(top & (east_distance <= LIP_SEARCH_PIXELS), MIN_LIP_COMPONENT_PIXELS)
    west_lip = clean_components(top & (west_distance <= LIP_SEARCH_PIXELS), MIN_LIP_COMPONENT_PIXELS)

    pixel_m = (cell_x + cell_y) / 2.0
    tpi = dem - gaussian_filter(dem, sigma=12.0 / pixel_m)
    allowed = high & (slope <= TRACE_MAX_SLOPE_DEG) & (tpi > TRACE_TPI_MIN_METERS)
    smooth = gaussian_filter(dem, sigma=2.0)

    return {
        "allowed": allowed,
        "east_lip": east_lip,
        "west_lip": west_lip,
        "east_distance": east_distance,
        "west_distance": west_distance,
        "east_indices": east_indices,
        "west_indices": west_indices,
        "smooth": smooth,
    }


def trace_alpha(
    dem: np.ndarray,
    transform: Affine,
    seed_mask: np.ndarray,
    allowed: np.ndarray,
    distance_to_face: np.ndarray,
    face_indices: np.ndarray,
    smooth: np.ndarray,
) -> np.ndarray:
    pixel_m = (abs(transform.a) + abs(transform.e)) / 2.0
    max_steps = max(1, int(TRACE_MAX_METERS / pixel_m))
    flat_stop_step = max(1, int(TRACE_FLAT_STOP_AFTER_METERS / pixel_m))
    alpha = np.zeros(dem.shape, dtype="float32")
    alpha[seed_mask] = 1.0

    for r0, c0 in np.argwhere(seed_mask):
        face_r = int(face_indices[0, r0, c0])
        face_c = int(face_indices[1, r0, c0])
        vr = r0 - face_r
        vc = c0 - face_c
        norm = math.hypot(vr, vc)
        if norm < 0.5:
            continue
        inward_r, inward_c = vr / norm, vc / norm
        path = [(int(r0), int(c0))]
        r, c = int(r0), int(c0)
        visited = {(r, c)}

        for step in range(max_steps):
            current = float(smooth[r, c])
            best = None
            for dr, dc in NEIGHBORS:
                rr, cc = r + dr, c + dc
                if rr < 1 or cc < 1 or rr >= dem.shape[0] - 1 or cc >= dem.shape[1] - 1:
                    continue
                if not allowed[rr, cc] or (rr, cc) in visited:
                    continue
                if distance_to_face[rr, cc] < distance_to_face[r, c] - 0.25:
                    continue
                inward_dot = dr * inward_r + dc * inward_c
                if step < 8 and inward_dot < -0.25:
                    continue
                gain = float(smooth[rr, cc] - current)
                if gain < -0.12:
                    continue
                score = gain * 8.0 + inward_dot * 0.06 + float(distance_to_face[rr, cc]) * 0.012
                if best is None or score > best[0]:
                    best = (score, gain, rr, cc)

            if best is None:
                break
            _, gain, rr, cc = best
            if gain < 0.01 and step > flat_stop_step:
                break
            r, c = int(rr), int(cc)
            path.append((r, c))
            visited.add((r, c))

        if len(path) < 2:
            continue
        last = len(path) - 1
        for index, (rr, cc) in enumerate(path):
            value = max(0.0, 1.0 - index / last)
            if value > alpha[rr, cc]:
                alpha[rr, cc] = value

    alpha = maximum_filter(alpha, size=7)
    alpha = gaussian_filter(alpha, sigma=1.2)
    alpha *= allowed
    alpha[seed_mask] = 1.0
    return alpha


def core_polygon_web(bounds_wgs84: list[float]):
    west, south, east, north = bounds_wgs84
    x1, y1 = TO_WEB.transform(west, south)
    x2, y2 = TO_WEB.transform(east, north)
    return box(x1, y1, x2, y2)


def vectorize(alpha, hard_mask, transform, kind, core_clip, sector_id):
    categories = np.zeros(alpha.shape, dtype="uint8")
    categories[alpha >= 0.15] = 1
    categories[alpha >= 0.40] = 2
    categories[alpha >= 0.65] = 3
    categories[alpha >= 0.85] = 4
    strengths = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.00}
    features = []

    for value, strength in strengths.items():
        mask = categories == value
        polygons = []
        for geom, _ in shapes(mask.astype("uint8"), mask=mask, transform=transform):
            polygon = shape(geom)
            if polygon.area >= 20.0:
                clipped = polygon.intersection(core_clip)
                if not clipped.is_empty:
                    polygons.append(clipped)
        if not polygons:
            continue
        merged = unary_union(polygons).buffer(0).simplify(3.0, preserve_topology=True)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if polygon.is_empty or polygon.area < 30.0:
                continue
            features.append({
                "type": "Feature",
                "properties": {"kind": kind, "strength": strength, "hard": False, "sector": sector_id},
                "geometry": mapping(shapely_transform(TO_LL.transform, polygon)),
            })

    hard_polygons = []
    for geom, _ in shapes(hard_mask.astype("uint8"), mask=hard_mask, transform=transform):
        polygon = shape(geom)
        if polygon.area >= 8.0:
            clipped = polygon.intersection(core_clip)
            if not clipped.is_empty:
                hard_polygons.append(clipped)
    if hard_polygons:
        merged = unary_union(hard_polygons).buffer(0).simplify(2.0, preserve_topology=True)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if polygon.is_empty or polygon.area < 12.0:
                continue
            features.append({
                "type": "Feature",
                "properties": {"kind": kind, "strength": 1.0, "hard": True, "sector": sector_id},
                "geometry": mapping(shapely_transform(TO_LL.transform, polygon)),
            })
    return features


def process_sector(sector: dict, expected_hashes: dict[str, str]) -> dict:
    sector_id = sector["id"]
    bounds = sector["boundsWgs84"]
    print(f"Processing {sector_id} {bounds}", flush=True)
    dem, transform, request_params = request_dem(bounds)
    digest = array_sha256(dem)
    expected = expected_hashes.get(sector_id)
    if expected and expected != digest:
        raise RuntimeError(
            f"{sector_id}: pinned LiDAR DEM changed; refusing silent regeneration. "
            f"expected={expected} actual={digest}"
        )

    fields = terrain_fields(dem, transform)
    east_alpha = trace_alpha(dem, transform, fields["east_lip"], fields["allowed"], fields["east_distance"], fields["east_indices"], fields["smooth"])
    west_alpha = trace_alpha(dem, transform, fields["west_lip"], fields["allowed"], fields["west_distance"], fields["west_indices"], fields["smooth"])

    clip = core_polygon_web(bounds)
    features = []
    features.extend(vectorize(east_alpha, fields["east_lip"], transform, "sunrise", clip, sector_id))
    features.extend(vectorize(west_alpha, fields["west_lip"], transform, "sunset", clip, sector_id))
    output = {"type": "FeatureCollection", "name": f"RRG LiDAR sunrise/sunset {sector_id}", "features": features}
    filename = f"{sector_id}.geojson"
    path = OUT_DIR / filename
    write_json(path, output, compact=True)

    result = {
        **sector,
        "file": f"data/map/rrg-lidar-sun/{filename}",
        "features": len(features),
        "sunriseHardCells": int(fields["east_lip"].sum()),
        "sunsetHardCells": int(fields["west_lip"].sum()),
        "sunriseGradientCells": int(np.count_nonzero(east_alpha)),
        "sunsetGradientCells": int(np.count_nonzero(west_alpha)),
        "demArraySha256": digest,
        "geojsonSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "request": request_params,
        "rasterShape": [int(dem.shape[0]), int(dem.shape[1])],
        "pixelSizeMeters": [abs(float(transform.a)), abs(float(transform.e))],
    }

    del dem, fields, east_alpha, west_alpha, features, output
    gc.collect()
    return result


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    expected_hashes = load_existing_hashes()
    sectors = []
    total_features = 0
    total_sunrise_hard = 0
    total_sunset_hard = 0

    for sector in sector_grid():
        result = process_sector(sector, expected_hashes)
        sectors.append(result)
        total_features += result["features"]
        total_sunrise_hard += result["sunriseHardCells"]
        total_sunset_hard += result["sunsetHardCells"]

    manifest = {
        "version": "lidar-only-gorge-v1",
        "status": "staging-expansion",
        "area": "Red River Gorge broad working envelope",
        "boundsWgs84": list(GORGE_BOUNDS_WGS84),
        "processingEnvelopeNotLegalBoundary": True,
        "minimumElevationFeet": MIN_ELEVATION_FT,
        "sectorGrid": {"rows": SECTOR_ROWS, "cols": SECTOR_COLS, "overlapMeters": SECTOR_OVERLAP_M},
        "targetPixelMeters": TARGET_PIXEL_M,
        "source": {
            "name": "KyFromAbove Phase 2 2-foot LiDAR-derived bare-earth DEM",
            "service": DEM_SERVICE,
            "zUnits": "meters",
        },
        "generationInputs": {
            "usesAerial": False,
            "usesCanopy": False,
            "usesTrails": False,
            "usesMarkedReviewPoints": False,
            "usesOnlyLidarDerivedBareEarthTerrain": True,
        },
        "rules": {
            "topMaxSlopeDegrees": TOP_MAX_SLOPE_DEG,
            "cliffMinSlopeDegrees": CLIFF_MIN_SLOPE_DEG,
            "eastAspectDegrees": [EAST_ASPECT_MIN, EAST_ASPECT_MAX],
            "westAspectDegrees": [WEST_ASPECT_MIN, WEST_ASPECT_MAX],
            "lipSearchPixels": LIP_SEARCH_PIXELS,
            "traceMaxMeters": TRACE_MAX_METERS,
            "traceFlatStopAfterMeters": TRACE_FLAT_STOP_AFTER_METERS,
            "traceTpiMinMeters": TRACE_TPI_MIN_METERS,
            "gradient": "hard line at directional cliff lip; fade inward/uphill to local crest",
        },
        "counts": {
            "sectors": len(sectors),
            "features": total_features,
            "sunriseHardCells": total_sunrise_hard,
            "sunsetHardCells": total_sunset_hard,
        },
        "sectors": sectors,
        "disclaimer": (
            "Terrain-only planning heuristic. It identifies LiDAR-derived directional ridge/cliff exposure "
            "above 1,100 ft, not guaranteed standing room, legal access, safety, vegetation clearance, "
            "or an actual photographic viewpoint."
        ),
    }
    write_json(OUT_MANIFEST, manifest)
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
