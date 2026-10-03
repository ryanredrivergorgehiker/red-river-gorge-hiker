#!/usr/bin/env python3
"""Generate bounded-memory mobile Sunrise / Sunset Potential rasters.

This derives mobile presentation assets strictly from the already accepted
continuous sunlight rasters and accepted hard-rim GeoJSON. It does not request
terrain data, alter terrain qualification, or change the 1,100 ft model.

Two fixed mobile resolutions are emitted:
- overview: 256 px sector width, used at mobile zoom <= 12
- detail:   768 px sector width, used at mobile zoom >= 13

Hard-rim geometry is precomposited into each sunrise/sunset raster so mobile
Safari never has to decode the ~2004x2250 source raster or parse/rasterize the
hard-rim geometry at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-continuous-manifest.json"
SOURCE_DIR = ROOT / "public/data/map/rrg-lidar-sun-continuous"
OUT_DIR = ROOT / "public/data/map/rrg-lidar-sun-mobile"
OUT_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-mobile-manifest.json"

OVERVIEW_WIDTH = 256
DETAIL_WIDTH = 768
SUNRISE_RGBA = (0xF2, 0x68, 0x5C, round(255 * 0.92))
SUNSET_RGBA = (0x46, 0x40, 0xB0, round(255 * 0.92))
SUNRISE_STROKE = (0xF2, 0x68, 0x5C, 255)
SUNSET_STROKE = (0x46, 0x40, 0xB0, 255)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def web_mercator_y(lat: float) -> float:
    clamped = max(-85.05112878, min(85.05112878, lat))
    radians = math.radians(clamped)
    return math.log(math.tan(math.pi / 4.0 + radians / 2.0))


def coordinate_to_pixel(
    coordinate: list[float],
    bounds: list[float],
    width: int,
    height: int,
) -> tuple[float, float]:
    west, south, east, north = map(float, bounds)
    lng = float(coordinate[0])
    lat = float(coordinate[1])
    span_x = max(1e-12, east - west)
    north_y = web_mercator_y(north)
    south_y = web_mercator_y(south)
    span_y = max(1e-12, north_y - south_y)
    x = ((lng - west) / span_x) * width
    y = ((north_y - web_mercator_y(lat)) / span_y) * height
    return (x, y)


def geometry_polygons(geometry: dict) -> list[list[list[list[float]]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return [coordinates]
    if kind == "MultiPolygon":
        return coordinates
    return []


def hard_overlay(
    hard_data: dict,
    kind: str,
    bounds: list[float],
    size: tuple[int, int],
) -> Image.Image:
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    fill_mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(fill_mask)
    boundaries: list[list[tuple[float, float]]] = []

    for feature in hard_data.get("features", []):
        feature_kind = "sunset" if feature.get("properties", {}).get("kind") == "sunset" else "sunrise"
        if feature_kind != kind:
            continue
        for polygon in geometry_polygons(feature.get("geometry") or {}):
            if not polygon:
                continue
            outer = [coordinate_to_pixel(point, bounds, width, height) for point in polygon[0]]
            if len(outer) >= 3:
                mask_draw.polygon(outer, fill=255)
                boundaries.append(outer)
            for hole_ring in polygon[1:]:
                hole = [coordinate_to_pixel(point, bounds, width, height) for point in hole_ring]
                if len(hole) >= 3:
                    mask_draw.polygon(hole, fill=0)
                    boundaries.append(hole)

    fill = SUNSET_RGBA if kind == "sunset" else SUNRISE_RGBA
    solid = Image.new("RGBA", size, fill)
    overlay = Image.composite(solid, overlay, fill_mask)

    stroke = SUNSET_STROKE if kind == "sunset" else SUNRISE_STROKE
    stroke_draw = ImageDraw.Draw(overlay)
    stroke_width = max(1, round(width / OVERVIEW_WIDTH * 1.5))
    for ring in boundaries:
        if len(ring) >= 2:
            stroke_draw.line([*ring, ring[0]], fill=stroke, width=stroke_width, joint="curve")

    return overlay


def write_mobile_variant(
    source: Image.Image,
    hard_data: dict,
    kind: str,
    bounds: list[float],
    width: int,
    path: Path,
) -> dict:
    target_height = max(1, round(source.height * width / source.width))
    target = source.resize((width, target_height), Image.Resampling.LANCZOS)
    overlay = hard_overlay(hard_data, kind, bounds, target.size)
    target = Image.alpha_composite(target, overlay)
    target.save(path, format="WEBP", lossless=True, quality=100, method=4)
    return {
        "file": path.relative_to(ROOT / "public").as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "shape": [target.height, target.width],
    }


def main() -> None:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("version") != "lidar-continuous-gradient-v1":
        raise RuntimeError("Unexpected continuous sunlight manifest version")
    if float(manifest.get("minimumElevationFeet", 0)) != 1100.0:
        raise RuntimeError("Continuous sunlight minimum elevation is no longer 1,100 ft")
    rendering = manifest.get("rendering") or {}
    if (
        rendering.get("gradient") != "continuous raster alpha WebP"
        or rendering.get("separateSunriseSunsetRasters") is not True
        or rendering.get("terrainQualificationChanged") is not False
        or rendering.get("hardLipGeometryChanged") is not False
        or rendering.get("acceptedHardLipReusedVerbatim") is not True
    ):
        raise RuntimeError("Continuous sunlight rendering contract changed")
    sectors = manifest.get("sectors") or []
    if len(sectors) != 30:
        raise RuntimeError(f"Expected 30 sunlight sectors, found {len(sectors)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*"):
        if old.is_file():
            old.unlink()

    output_sectors = []
    total_bytes = 0
    total_hard_features = 0

    for sector in sectors:
        sector_id = str(sector["id"])
        bounds = list(map(float, sector["boundsWgs84"]))
        shape = [int(v) for v in sector["rasterShape"]]
        if len(shape) != 2:
            raise RuntimeError(f"{sector_id}: invalid source raster shape")

        sunrise_path = ROOT / "public" / str(sector["sunriseRasterFile"])
        sunset_path = ROOT / "public" / str(sector["sunsetRasterFile"])
        hard_path = ROOT / "public" / str(sector["hardFile"])

        if sha256_file(sunrise_path) != str(sector["sunriseRasterSha256"]):
            raise RuntimeError(f"{sector_id}: sunrise source SHA mismatch")
        if sha256_file(sunset_path) != str(sector["sunsetRasterSha256"]):
            raise RuntimeError(f"{sector_id}: sunset source SHA mismatch")
        if sha256_file(hard_path) != str(sector["hardSha256"]):
            raise RuntimeError(f"{sector_id}: hard-rim source SHA mismatch")

        hard_data = json.loads(hard_path.read_text(encoding="utf-8"))
        hard_features = len(hard_data.get("features") or [])
        if hard_features != int(sector.get("hardFeatures", hard_features)):
            raise RuntimeError(f"{sector_id}: hard-rim feature count mismatch")
        total_hard_features += hard_features

        with Image.open(sunrise_path) as sunrise_source, Image.open(sunset_path) as sunset_source:
            sunrise_source = sunrise_source.convert("RGBA")
            sunset_source = sunset_source.convert("RGBA")
            expected_size = (shape[1], shape[0])
            if sunrise_source.size != expected_size or sunset_source.size != expected_size:
                raise RuntimeError(
                    f"{sector_id}: source raster dimensions changed "
                    f"(expected {expected_size}, got {sunrise_source.size}/{sunset_source.size})"
                )

            variants = {}
            for variant, width in (("overview", OVERVIEW_WIDTH), ("detail", DETAIL_WIDTH)):
                sunrise_out = OUT_DIR / f"{sector_id}-sunrise-{variant}.webp"
                sunset_out = OUT_DIR / f"{sector_id}-sunset-{variant}.webp"
                sunrise_meta = write_mobile_variant(
                    sunrise_source, hard_data, "sunrise", bounds, width, sunrise_out
                )
                sunset_meta = write_mobile_variant(
                    sunset_source, hard_data, "sunset", bounds, width, sunset_out
                )
                variants[variant] = {
                    "sunrise": sunrise_meta,
                    "sunset": sunset_meta,
                }
                total_bytes += sunrise_meta["bytes"] + sunset_meta["bytes"]

        output_sectors.append({
            "id": sector_id,
            "boundsWgs84": bounds,
            "sourceRasterShape": shape,
            "sourceSunriseSha256": sector["sunriseRasterSha256"],
            "sourceSunsetSha256": sector["sunsetRasterSha256"],
            "sourceHardSha256": sector["hardSha256"],
            "hardFeatures": hard_features,
            "variants": variants,
        })
        print(f"Generated mobile sunlight {sector_id}", flush=True)

    mobile_manifest = {
        "version": "lidar-continuous-mobile-v1",
        "sourceContinuousManifestSha256": sha256_file(SOURCE_MANIFEST),
        "sourceContinuousVersion": manifest["version"],
        "sourceAcceptedOverlayFingerprintSha256": manifest.get("acceptedOverlayFingerprintSha256"),
        "minimumElevationFeet": 1100.0,
        "terrainQualificationChanged": False,
        "hardLipGeometryChanged": False,
        "acceptedHardLipReusedVerbatim": True,
        "presentation": {
            "hardRimsPrecomposited": True,
            "separateSunriseSunsetRasters": True,
            "overviewMaxZoom": 12,
            "overviewSectorWidthPx": OVERVIEW_WIDTH,
            "detailMinZoom": 13,
            "detailSectorWidthPx": DETAIL_WIDTH,
        },
        "counts": {
            "sectors": len(output_sectors),
            "files": len(output_sectors) * 4,
            "bytes": total_bytes,
            "hardFeatures": total_hard_features,
        },
        "sectors": output_sectors,
    }
    OUT_MANIFEST.write_text(
        json.dumps(mobile_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(mobile_manifest["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
