#!/usr/bin/env python3
"""Generate a staging-only smoother duplicate of the accepted RRG sunlight overlay.

Safety contract:
- Never modify the accepted public/data/map/rrg-lidar-sun* files.
- Reuse the accepted terrain model and exact 1,100 ft minimum.
- Reuse the accepted hard cliff/rim lip geometry.
- Keep the accepted 0.15 outer alpha cutoff.
- Change only the presentation quantization: twelve fade bands instead of six.
- Emit a separate off-by-default owner-UAT dataset.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from rasterio.features import shapes
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SCRIPT = ROOT / "scripts/generate-rrg-lidar-sun.py"
ACCEPTED_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-manifest.json"
ACCEPTED_DIR = ROOT / "public/data/map/rrg-lidar-sun"
OUT_DIR = ROOT / "public/data/map/rrg-lidar-sun-smooth-test"
OUT_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-smooth-test-manifest.json"

# Same accepted outer cutoff (.15) and same accepted full-strength threshold (.85),
# but quantized into twelve equal presentation steps rather than six.
BAND_THRESHOLDS = [
    0.150000,
    0.213636,
    0.277273,
    0.340909,
    0.404545,
    0.468182,
    0.531818,
    0.595455,
    0.659091,
    0.722727,
    0.786364,
    0.850000,
]
BAND_STRENGTHS = [
    0.200000,
    0.272727,
    0.345455,
    0.418182,
    0.490909,
    0.563636,
    0.636364,
    0.709091,
    0.781818,
    0.854545,
    0.927273,
    1.000000,
]


def load_accepted_module():
    spec = importlib.util.spec_from_file_location("rrgh_accepted_sun", ACCEPTED_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load accepted sunlight generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_overlay_fingerprint() -> str:
    digest = hashlib.sha256()
    files = [ACCEPTED_MANIFEST, *sorted(ACCEPTED_DIR.glob("*.geojson"))]
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def accepted_dem_hashes() -> dict[str, str]:
    payload = json.loads(ACCEPTED_MANIFEST.read_text(encoding="utf-8"))
    if float(payload.get("minimumElevationFeet", 0)) != 1100.0:
        raise RuntimeError("Accepted sunlight manifest no longer has the locked 1,100 ft minimum")
    result: dict[str, str] = {}
    for sector in payload.get("sectors", []):
        sector_id = str(sector.get("id", ""))
        digest = str(sector.get("demArraySha256", ""))
        if sector_id and digest:
            result[sector_id] = digest
    if not result:
        raise RuntimeError("Accepted sunlight manifest has no pinned DEM fingerprints")
    return result


def vectorize_smooth(rrg, alpha, hard_mask, transform, kind, core_clip, sector_id):
    categories = np.zeros(alpha.shape, dtype="uint8")
    for index, threshold in enumerate(BAND_THRESHOLDS, start=1):
        categories[alpha >= threshold] = index

    features = []
    for value, strength in enumerate(BAND_STRENGTHS, start=1):
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
        # Match the accepted gradient geometry cleanup exactly.
        merged = unary_union(polygons).buffer(0).simplify(3.0, preserve_topology=True)
        parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for polygon in parts:
            if polygon.is_empty or polygon.area < 30.0:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "kind": kind,
                    "strength": float(strength),
                    "hard": False,
                    "sector": sector_id,
                    "test": "smooth-12-band",
                },
                "geometry": mapping(shapely_transform(rrg.TO_LL.transform, polygon)),
            })

    # Match the accepted hard-lip vectorization exactly.
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
                "properties": {
                    "kind": kind,
                    "strength": 1.0,
                    "hard": True,
                    "sector": sector_id,
                    "test": "smooth-12-band",
                },
                "geometry": mapping(shapely_transform(rrg.TO_LL.transform, polygon)),
            })
    return features


def process_sector(rrg, sector: dict, expected_hashes: dict[str, str]) -> dict:
    sector_id = str(sector["id"])
    bounds = sector["boundsWgs84"]
    print(f"Processing smooth sunlight test {sector_id} {bounds}", flush=True)

    dem, transform, request_params = rrg.request_dem(bounds)
    digest = rrg.array_sha256(dem)
    expected = expected_hashes.get(sector_id)
    if expected is None:
        raise RuntimeError(f"{sector_id}: no accepted DEM fingerprint exists")
    if expected != digest:
        raise RuntimeError(
            f"{sector_id}: pinned LiDAR DEM changed; refusing smooth-test regeneration. "
            f"expected={expected} actual={digest}"
        )

    fields = rrg.terrain_fields(dem, transform)
    east_alpha = rrg.trace_alpha(
        dem, transform, fields["east_lip"], fields["allowed"],
        fields["east_distance"], fields["east_indices"], fields["smooth"]
    )
    west_alpha = rrg.trace_alpha(
        dem, transform, fields["west_lip"], fields["allowed"],
        fields["west_distance"], fields["west_indices"], fields["smooth"]
    )

    clip = rrg.core_polygon_web(bounds)
    features = []
    features.extend(vectorize_smooth(rrg, east_alpha, fields["east_lip"], transform, "sunrise", clip, sector_id))
    features.extend(vectorize_smooth(rrg, west_alpha, fields["west_lip"], transform, "sunset", clip, sector_id))

    output = {
        "type": "FeatureCollection",
        "name": f"RRG LiDAR smooth sunrise/sunset TEST {sector_id}",
        "features": features,
    }
    filename = f"{sector_id}.geojson"
    path = OUT_DIR / filename
    rrg.write_json(path, output, compact=True)

    result = {
        **sector,
        "file": f"data/map/rrg-lidar-sun-smooth-test/{filename}",
        "features": len(features),
        "sunriseHardCells": int(fields["east_lip"].sum()),
        "sunsetHardCells": int(fields["west_lip"].sum()),
        "sunriseGradientCells": int(np.count_nonzero(east_alpha)),
        "sunsetGradientCells": int(np.count_nonzero(west_alpha)),
        "demArraySha256": digest,
        "geojsonSha256": sha256_file(path),
        "request": request_params,
        "rasterShape": [int(dem.shape[0]), int(dem.shape[1])],
        "pixelSizeMeters": [abs(float(transform.a)), abs(float(transform.e))],
    }

    del dem, fields, east_alpha, west_alpha, features, output
    gc.collect()
    return result


def main() -> None:
    rrg = load_accepted_module()
    if float(rrg.MIN_ELEVATION_FT) != 1100.0:
        raise RuntimeError("Accepted generator no longer has the locked 1,100 ft minimum")

    accepted_before = accepted_overlay_fingerprint()
    expected_hashes = accepted_dem_hashes()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.geojson"):
        old.unlink()

    sectors = []
    total_features = 0
    total_sunrise_hard = 0
    total_sunset_hard = 0
    for sector in rrg.sector_grid():
        result = process_sector(rrg, sector, expected_hashes)
        sectors.append(result)
        total_features += result["features"]
        total_sunrise_hard += result["sunriseHardCells"]
        total_sunset_hard += result["sunsetHardCells"]

    accepted_after = accepted_overlay_fingerprint()
    if accepted_before != accepted_after:
        raise RuntimeError("Accepted Sunrise / Sunset Potential files changed during smooth-test generation")

    manifest = {
        "version": "lidar-smooth-gradient-test-v1",
        "status": "staging-owner-uat-only",
        "defaultEnabled": False,
        "acceptedLayerModified": False,
        "acceptedOverlayFingerprintSha256": accepted_after,
        "acceptedGeneratorSha256": sha256_file(ACCEPTED_SCRIPT),
        "minimumElevationFeet": 1100.0,
        "area": "Red River Gorge default/Home map extent",
        "boundsWgs84": list(rrg.HOME_BOUNDS_WGS84),
        "processingEnvelopeNotLegalBoundary": True,
        "targetPixelMeters": rrg.TARGET_PIXEL_M,
        "presentationOnlyChange": {
            "acceptedGradientBands": 6,
            "testGradientBands": 12,
            "acceptedOuterAlphaCutoff": 0.15,
            "testOuterAlphaCutoff": 0.15,
            "acceptedFullStrengthThreshold": 0.85,
            "testFullStrengthThreshold": 0.85,
            "hardLipGeometryChanged": False,
            "terrainQualificationChanged": False,
            "bandThresholds": BAND_THRESHOLDS,
            "bandStrengths": BAND_STRENGTHS,
        },
        "source": {
            "name": "KyFromAbove Phase 2 2-foot LiDAR-derived bare-earth DEM",
            "service": rrg.DEM_SERVICE,
            "zUnits": "meters",
        },
        "counts": {
            "sectors": len(sectors),
            "features": total_features,
            "sunriseHardCells": total_sunrise_hard,
            "sunsetHardCells": total_sunset_hard,
        },
        "sectors": sectors,
        "disclaimer": (
            "Staging owner-UAT presentation test only. It uses the accepted 1,100+ terrain model "
            "and changes only the number of vector fade bands from six to twelve."
        ),
    }
    rrg.write_json(OUT_MANIFEST, manifest)
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
