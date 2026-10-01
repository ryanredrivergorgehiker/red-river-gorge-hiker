#!/usr/bin/env python3
"""Generate the promoted continuous-raster Sunrise / Sunset Potential dataset.

This is the staging candidate that replaces stepped fade polygons in map rendering
while preserving the accepted terrain model, 1,100 ft minimum, outer cutoff,
colors, and hard rim-lip geometry.

Outputs separate sunrise and sunset WebP rasters so the existing child toggles
remain independently controllable.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SCRIPT = ROOT / "scripts/generate-rrg-lidar-sun.py"
ACCEPTED_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-manifest.json"
ACCEPTED_DIR = ROOT / "public/data/map/rrg-lidar-sun"
OUT_DIR = ROOT / "public/data/map/rrg-lidar-sun-continuous"
OUT_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-continuous-manifest.json"

OUTER_ALPHA_CUTOFF = 0.15
FULL_STRENGTH_ALPHA = 0.85
MIN_PRESENTATION_STRENGTH = 0.20
SUNRISE_RGB = np.array([0xF2, 0x68, 0x5C], dtype=np.uint8)
SUNSET_RGB = np.array([0x46, 0x40, 0xB0], dtype=np.uint8)


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


def accepted_manifest_payload() -> dict:
    payload = json.loads(ACCEPTED_MANIFEST.read_text(encoding="utf-8"))
    if float(payload.get("minimumElevationFeet", 0)) != 1100.0:
        raise RuntimeError("Accepted sunlight manifest no longer has the locked 1,100 ft minimum")
    if int(payload.get("counts", {}).get("sectors", 0)) != 30:
        raise RuntimeError("Accepted sunlight sector count changed; refusing continuous generation")
    return payload


def presentation_opacity(alpha: np.ndarray) -> np.ndarray:
    """Match accepted opacity endpoints continuously instead of six bands."""
    visible = alpha >= OUTER_ALPHA_CUTOFF
    progress = np.clip(
        (alpha - OUTER_ALPHA_CUTOFF) / (FULL_STRENGTH_ALPHA - OUTER_ALPHA_CUTOFF),
        0.0,
        1.0,
    )
    strength = MIN_PRESENTATION_STRENGTH + progress * (1.0 - MIN_PRESENTATION_STRENGTH)
    opacity = 0.12 + strength * 0.58
    return np.where(visible, opacity, 0.0).astype(np.float32)


def rgba_for_kind(alpha: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    opacity = presentation_opacity(alpha)
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[..., :3] = rgb[None, None, :]
    rgba[..., 3] = np.clip(np.rint(opacity * 255.0), 0, 255).astype(np.uint8)
    return rgba


def crop_to_core(rrg, array: np.ndarray, transform, bounds_wgs84: list[float]) -> np.ndarray:
    west, south, east, north = bounds_wgs84
    x1, y1 = rrg.TO_WEB.transform(west, south)
    x2, y2 = rrg.TO_WEB.transform(east, north)
    window = from_bounds(x1, y1, x2, y2, transform=transform).round_offsets().round_lengths()

    row0 = max(0, int(window.row_off))
    col0 = max(0, int(window.col_off))
    row1 = min(array.shape[0], row0 + int(window.height))
    col1 = min(array.shape[1], col0 + int(window.width))
    if row1 <= row0 or col1 <= col0:
        raise RuntimeError("Core crop produced an empty raster")
    return array[row0:row1, col0:col1]


def accepted_hard_features(sector_meta: dict) -> list[dict]:
    accepted_path = ROOT / "public" / str(sector_meta["file"])
    payload = json.loads(accepted_path.read_text(encoding="utf-8"))
    return [
        feature
        for feature in payload.get("features", [])
        if feature.get("properties", {}).get("hard") is True
    ]


def write_webp(path: Path, rgba: np.ndarray) -> None:
    Image.fromarray(rgba, mode="RGBA").save(
        path,
        format="WEBP",
        lossless=True,
        quality=100,
        method=4,
    )


def process_sector(rrg, sector: dict, accepted_sector: dict) -> dict:
    sector_id = str(sector["id"])
    bounds = sector["boundsWgs84"]
    print(f"Processing promoted continuous sunlight {sector_id} {bounds}", flush=True)

    dem, transform, request_params = rrg.request_dem(bounds)
    digest = rrg.array_sha256(dem)
    expected = str(accepted_sector.get("demArraySha256", ""))
    if not expected or expected != digest:
        raise RuntimeError(
            f"{sector_id}: pinned LiDAR DEM changed; refusing continuous regeneration. "
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

    east_core = crop_to_core(rrg, east_alpha, transform, bounds)
    west_core = crop_to_core(rrg, west_alpha, transform, bounds)
    if east_core.shape != west_core.shape:
        raise RuntimeError(f"{sector_id}: sunrise/sunset core raster shapes differ")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sunrise_name = f"{sector_id}-sunrise.webp"
    sunrise_path = OUT_DIR / sunrise_name
    write_webp(sunrise_path, rgba_for_kind(east_core, SUNRISE_RGB))

    sunset_name = f"{sector_id}-sunset.webp"
    sunset_path = OUT_DIR / sunset_name
    write_webp(sunset_path, rgba_for_kind(west_core, SUNSET_RGB))

    hard_features = accepted_hard_features(accepted_sector)
    hard_name = f"{sector_id}-hard.geojson"
    hard_path = OUT_DIR / hard_name
    rrg.write_json(
        hard_path,
        {
            "type": "FeatureCollection",
            "name": f"Accepted hard sunlight rim lip {sector_id}",
            "features": hard_features,
        },
        compact=True,
    )

    return {
        **sector,
        "sunriseRasterFile": f"data/map/rrg-lidar-sun-continuous/{sunrise_name}",
        "sunsetRasterFile": f"data/map/rrg-lidar-sun-continuous/{sunset_name}",
        "hardFile": f"data/map/rrg-lidar-sun-continuous/{hard_name}",
        "sunriseRasterSha256": sha256_file(sunrise_path),
        "sunsetRasterSha256": sha256_file(sunset_path),
        "hardSha256": sha256_file(hard_path),
        "sunriseRasterBytes": sunrise_path.stat().st_size,
        "sunsetRasterBytes": sunset_path.stat().st_size,
        "hardFeatures": len(hard_features),
        "rasterShape": [int(east_core.shape[0]), int(east_core.shape[1])],
        "demArraySha256": digest,
        "request": request_params,
    }


def main() -> None:
    rrg = load_accepted_module()
    if float(rrg.MIN_ELEVATION_FT) != 1100.0:
        raise RuntimeError("Accepted generator no longer has the locked 1,100 ft minimum")

    accepted_before = accepted_overlay_fingerprint()
    accepted = accepted_manifest_payload()
    accepted_by_id = {str(sector["id"]): sector for sector in accepted.get("sectors", [])}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.iterdir():
        if old.is_file():
            old.unlink()

    sectors = []
    total_raster_bytes = 0
    total_hard = 0
    for sector in rrg.sector_grid():
        sector_id = str(sector["id"])
        accepted_sector = accepted_by_id.get(sector_id)
        if accepted_sector is None:
            raise RuntimeError(f"{sector_id}: missing from accepted sunlight manifest")
        result = process_sector(rrg, sector, accepted_sector)
        sectors.append(result)
        total_raster_bytes += result["sunriseRasterBytes"] + result["sunsetRasterBytes"]
        total_hard += result["hardFeatures"]
        del result
        gc.collect()

    accepted_after = accepted_overlay_fingerprint()
    if accepted_before != accepted_after:
        raise RuntimeError("Accepted stepped sunlight files changed during continuous generation")

    manifest = {
        "version": "lidar-continuous-gradient-v1",
        "status": "staging-promotion-candidate",
        "acceptedSteppedLayerModified": False,
        "acceptedOverlayFingerprintSha256": accepted_after,
        "acceptedGeneratorSha256": sha256_file(ACCEPTED_SCRIPT),
        "minimumElevationFeet": 1100.0,
        "area": "Red River Gorge default/Home map extent",
        "boundsWgs84": list(rrg.HOME_BOUNDS_WGS84),
        "processingEnvelopeNotLegalBoundary": True,
        "rendering": {
            "gradient": "continuous raster alpha WebP",
            "separateSunriseSunsetRasters": True,
            "outerAlphaCutoff": OUTER_ALPHA_CUTOFF,
            "fullStrengthThreshold": FULL_STRENGTH_ALPHA,
            "terrainQualificationChanged": False,
            "hardLipGeometryChanged": False,
            "acceptedHardLipReusedVerbatim": True,
        },
        "source": {
            "name": "KyFromAbove Phase 2 2-foot LiDAR-derived bare-earth DEM",
            "service": rrg.DEM_SERVICE,
            "zUnits": "meters",
        },
        "counts": {
            "sectors": len(sectors),
            "rasterBytes": total_raster_bytes,
            "hardFeatures": total_hard,
        },
        "sectors": sectors,
        "disclaimer": (
            "Promoted staging candidate for Sunrise / Sunset Potential. Uses the accepted 1,100+ "
            "terrain model and hard rim-lip vectors, with continuous raster fade rendering."
        ),
    }
    rrg.write_json(OUT_MANIFEST, manifest)
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
