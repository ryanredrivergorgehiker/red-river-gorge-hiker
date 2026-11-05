#!/usr/bin/env python3
"""Generate the Pinch-Em-Tight LiDAR-only sunrise/sunset pilot.

Locked pilot method:
- KyFromAbove Phase 2 two-foot bare-earth DEM only.
- No aerial imagery, canopy model, trail geometry, waypoint geometry, or marked review points.
- Ignore terrain below 1,100 ft.
- Sunrise: east-facing cliff/rim lip.
- Sunset: west-facing cliff/rim lip.
- Hard color at the lip; fade inward/uphill on the same high ridge surface until the local crest.
- Pilot area only; no Gorge-wide generation.

The DEM request is pinned to the exact source geometry and array hash previously retained
for Area A. If the returned DEM changes, generation fails closed.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.features import shapes
from rasterio.transform import Affine
import requests
from scipy.ndimage import (
    binary_dilation,
    distance_transform_edt,
    gaussian_filter,
    label,
    maximum_filter,
)
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT_GEOJSON = ROOT / "public/data/map/pinch-em-tight-lidar-sun-pilot.geojson"
OUT_META = ROOT / "public/data/map/pinch-em-tight-lidar-sun-pilot.meta.json"
OUT_REVIEW = ROOT / "docs/lidar-pilot/pinch-em-tight-lidar-review.png"

DEM_SERVICE = (
    "https://kyraster.ky.gov/arcgis/rest/services/"
    "ElevationServices/Ky_DEM_KYAPED_2FT_Phase2_ZMeters_WGS84WM/ImageServer"
)
# Exact retained Area A Phase 2 DEM export. This is intentionally broader than the pilot
# so the Pinch-Em-Tight crop is evaluated with stable surrounding terrain.
DEM_PARAMS = {
    "f": "json",
    "bbox": "-9313323.578345906,4550663.7389075495,-9306809.34791798,4557465.036251732",
    "bboxSR": "3857",
    "imageSR": "3857",
    "size": "2573,2687",
    "format": "tiff",
    "pixelType": "F32",
    "interpolation": "RSP_BilinearInterpolation",
    "adjustAspectRatio": "false",
    "returnSquarePixels": "false",
}
EXPECTED_DEM_ARRAY_SHA256 = "26eb2dd2f56fe2731f82df99392098d6f79301dc9b7894b71a65b106ef7552cc"

PILOT_BOUNDS_WGS84 = (-83.6365, 37.8130, -83.6175, 37.8255)
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

SUNRISE = (242, 104, 92)
SUNSET = (70, 64, 176)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def fetch_dem() -> tuple[np.ndarray, Affine]:
    response = requests.get(DEM_SERVICE + "/exportImage", params=DEM_PARAMS, timeout=180)
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
            if dem.shape != (2687, 2573):
                raise RuntimeError(f"Unexpected DEM shape: {dem.shape}")
            if not np.isfinite(dem).all():
                raise RuntimeError("DEM contains non-finite cells")
    actual = array_sha256(dem)
    if actual != EXPECTED_DEM_ARRAY_SHA256:
        raise RuntimeError(
            "Pinned LiDAR DEM changed; refusing silent regeneration. "
            f"expected={EXPECTED_DEM_ARRAY_SHA256} actual={actual}"
        )
    return dem.astype("float32", copy=False), transform


def clean_components(mask: np.ndarray, minimum: int) -> np.ndarray:
    groups, count = label(mask)
    if count == 0:
        return mask
    sizes = np.bincount(groups.ravel())
    keep = np.zeros(count + 1, dtype=bool)
    keep[np.where(sizes >= minimum)[0]] = True
    keep[0] = False
    return keep[groups]


def crop_window(
    dem: np.ndarray, transform: Affine
) -> tuple[np.ndarray, Affine, tuple[int, int, int, int]]:
    west, south, east, north = PILOT_BOUNDS_WGS84
    to_web = Transformer.from_crs(4326, 3857, always_xy=True)
    x1, y1 = to_web.transform(west, south)
    x2, y2 = to_web.transform(east, north)
    inv = ~transform
    c1, r2 = inv * (x1, y1)
    c2, r1 = inv * (x2, y2)
    r1i, r2i = int(math.floor(r1)), int(math.ceil(r2))
    c1i, c2i = int(math.floor(c1)), int(math.ceil(c2))
    crop = dem[r1i:r2i, c1i:c2i]
    crop_transform = transform * Affine.translation(c1i, r1i)
    return crop, crop_transform, (r1i, r2i, c1i, c2i)


def terrain_fields(dem: np.ndarray, transform: Affine) -> dict[str, np.ndarray]:
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)
    gy, gx = np.gradient(dem, cell_y, cell_x)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    # Downslope aspect clockwise from north.
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
        "slope": slope,
        "aspect": aspect,
        "high": high,
        "allowed": allowed,
        "east_lip": east_lip,
        "west_lip": west_lip,
        "east_distance": east_distance,
        "west_distance": west_distance,
        "east_indices": east_indices,
        "west_indices": west_indices,
        "smooth": smooth,
    }


NEIGHBORS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),            (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]


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
                # Stay on the same upper surface by never materially moving back
                # toward the originating cliff face.
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
            # 1.0 at the cliff lip, fading to 0.0 at the reached local crest.
            value = max(0.0, 1.0 - index / last)
            if value > alpha[rr, cc]:
                alpha[rr, cc] = value

    # Give the traced center paths a narrow physical band while retaining
    # the same high-ridge constraint. The hard rim is restored afterward.
    alpha = maximum_filter(alpha, size=7)
    alpha = gaussian_filter(alpha, sigma=1.2)
    alpha *= allowed
    alpha[seed_mask] = 1.0
    return alpha


def vectorize(
    alpha: np.ndarray,
    hard_mask: np.ndarray,
    transform: Affine,
    kind: str,
) -> list[dict]:
    categories = np.zeros(alpha.shape, dtype="uint8")
    categories[alpha >= 0.15] = 1
    categories[alpha >= 0.40] = 2
    categories[alpha >= 0.65] = 3
    categories[alpha >= 0.85] = 4
    strengths = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.00}
    to_ll = Transformer.from_crs(3857, 4326, always_xy=True).transform
    features: list[dict] = []

    for value, strength in strengths.items():
        mask = categories == value
        polygons = []
        for geom, _ in shapes(mask.astype("uint8"), mask=mask, transform=transform):
            polygon = shape(geom)
            if polygon.area >= 20.0:
                polygons.append(polygon)
        if not polygons:
            continue
        merged = unary_union(polygons).buffer(0).simplify(3.0, preserve_topology=True)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if polygon.area < 30.0:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {"kind": kind, "strength": strength, "hard": False},
                    "geometry": mapping(shapely_transform(to_ll, polygon)),
                }
            )

    hard_polygons = []
    for geom, _ in shapes(hard_mask.astype("uint8"), mask=hard_mask, transform=transform):
        polygon = shape(geom)
        if polygon.area >= 8.0:
            hard_polygons.append(polygon)
    if hard_polygons:
        merged = unary_union(hard_polygons).buffer(0).simplify(2.0, preserve_topology=True)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if polygon.area < 12.0:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {"kind": kind, "strength": 1.0, "hard": True},
                    "geometry": mapping(shapely_transform(to_ll, polygon)),
                }
            )
    return features


def hillshade(dem: np.ndarray, transform: Affine, azimuth: float) -> np.ndarray:
    cell_x = abs(transform.a)
    cell_y = abs(transform.e)
    gy, gx = np.gradient(dem, cell_y, cell_x)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(gx, -gy)
    az = math.radians(azimuth)
    altitude = math.radians(45.0)
    value = (
        math.sin(altitude) * np.cos(slope)
        + math.cos(altitude) * np.sin(slope) * np.cos(az - aspect)
    )
    return np.clip((value + 1.0) / 2.0, 0.0, 1.0)


def render_review(
    dem: np.ndarray,
    transform: Affine,
    east_alpha: np.ndarray,
    west_alpha: np.ndarray,
    east_lip: np.ndarray,
    west_lip: np.ndarray,
) -> None:
    shade = np.mean([hillshade(dem, transform, az) for az in (315, 45, 135, 225)], axis=0)
    lo, hi = np.percentile(shade, [2, 98])
    gray = np.clip((shade - lo) / max(1e-6, hi - lo) * 255.0, 0, 255)
    rgb = np.repeat(gray[..., None], 3, axis=2)
    high = dem >= MIN_ELEVATION_M
    rgb[high] = rgb[high] * 0.90 + np.array([255.0, 235.0, 140.0]) * 0.10

    e = np.clip(east_alpha * 0.86, 0, 0.86)
    w = np.clip(west_alpha * 0.86, 0, 0.86)
    opacity = np.maximum(e, w)
    ratio = e / (e + w + 1e-6)
    color = ratio[..., None] * np.array(SUNRISE) + (1.0 - ratio[..., None]) * np.array(SUNSET)
    rgb = rgb * (1.0 - opacity[..., None]) + color * opacity[..., None]
    rgb[east_lip] = np.array(SUNRISE)
    rgb[west_lip] = np.array(SUNSET)

    OUT_REVIEW.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rgb, 0, 255).astype("uint8")).save(OUT_REVIEW, optimize=True)


def main() -> None:
    dem, transform = fetch_dem()
    crop, crop_transform, window = crop_window(dem, transform)
    fields = terrain_fields(crop, crop_transform)

    east_alpha = trace_alpha(
        crop,
        crop_transform,
        fields["east_lip"],
        fields["allowed"],
        fields["east_distance"],
        fields["east_indices"],
        fields["smooth"],
    )
    west_alpha = trace_alpha(
        crop,
        crop_transform,
        fields["west_lip"],
        fields["allowed"],
        fields["west_distance"],
        fields["west_indices"],
        fields["smooth"],
    )

    features = []
    features.extend(vectorize(east_alpha, fields["east_lip"], crop_transform, "sunrise"))
    features.extend(vectorize(west_alpha, fields["west_lip"], crop_transform, "sunset"))
    output = {
        "type": "FeatureCollection",
        "name": "Pinch-Em-Tight LiDAR-only sunrise/sunset pilot",
        "features": features,
    }
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps(output, separators=(",", ":")) + "\n", encoding="utf-8")
    render_review(
        crop,
        crop_transform,
        east_alpha,
        west_alpha,
        fields["east_lip"],
        fields["west_lip"],
    )

    meta = {
        "version": "lidar-only-pilot-v1",
        "status": "staging-pilot-only",
        "area": "Pinch-Em-Tight",
        "boundsWgs84": list(PILOT_BOUNDS_WGS84),
        "minimumElevationFeet": MIN_ELEVATION_FT,
        "source": {
            "name": "KyFromAbove Phase 2 2-foot LiDAR-derived bare-earth DEM",
            "service": DEM_SERVICE,
            "expectedDemArraySha256": EXPECTED_DEM_ARRAY_SHA256,
            "fullAreaExportParams": DEM_PARAMS,
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
            "features": len(features),
            "sunriseHardCells": int(fields["east_lip"].sum()),
            "sunsetHardCells": int(fields["west_lip"].sum()),
            "sunriseGradientCells": int(np.count_nonzero(east_alpha)),
            "sunsetGradientCells": int(np.count_nonzero(west_alpha)),
        },
        "outputSha256": {
            "geojson": hashlib.sha256(OUT_GEOJSON.read_bytes()).hexdigest(),
            "reviewPng": hashlib.sha256(OUT_REVIEW.read_bytes()).hexdigest(),
        },
        "windowRowsCols": list(window),
        "disclaimer": (
            "Terrain-only planning heuristic. It identifies LiDAR-derived directional ridge/cliff exposure, "
            "not guaranteed standing room, legal access, safety, vegetation clearance, or an actual photographic viewpoint."
        ),
    }
    write_json(OUT_META, meta)
    print(json.dumps(meta, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
