#!/usr/bin/env python3
"""Generate a staging-only Clifty Wilderness 1,000–1,100 ft sunlight test overlay.

Safety contract:
- Never modify the accepted Gorge-wide Sunrise / Sunset Potential files.
- Reuse the accepted terrain algorithm from generate-rrg-lidar-sun.py.
- Emit only cells from 1,000 ft inclusive to 1,100 ft exclusive.
- Clip output to two owner-approved Clifty Wilderness test scopes:
  1) the wilderness south side of Douglas Trail;
  2) the wilderness northeast of the Osborne Bend Loop center.
- This output is a separate, off-by-default staging test layer.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from shapely.geometry import LineString, box, shape
from shapely.ops import linemerge, split, transform as shapely_transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SCRIPT = ROOT / "scripts/generate-rrg-lidar-sun.py"
OUT_DIR = ROOT / "public/data/map/clifty-sun-1000-1100-test"
OUT_MANIFEST = ROOT / "public/data/map/clifty-sun-1000-1100-test-manifest.json"
OSM_CACHE = ROOT / "public/data/map/osm-informal-trails.geojson"
ACCEPTED_MANIFEST = ROOT / "public/data/map/rrg-lidar-sun-manifest.json"
ACCEPTED_DIR = ROOT / "public/data/map/rrg-lidar-sun"

WILDERNESS_SERVICE = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_Wilderness_01/MapServer/0"
TRAIL_SERVICE = "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublishWithDataStatus_01/MapServer/0"
RRG_QUERY_BOUNDS = (-83.745, 37.73, -83.475, 37.93)
LOW_ELEVATION_FT = 1000.0
HIGH_ELEVATION_FT = 1100.0
FEET_PER_METER = 3.280839895013123


def load_accepted_module():
    spec = importlib.util.spec_from_file_location("rrgh_accepted_sun", ACCEPTED_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load accepted Sunrise / Sunset Potential generator")
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


def query_geojson(service: str, out_fields: str) -> list[dict]:
    west, south, east, north = RRG_QUERY_BOUNDS
    params = {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    response = requests.get(service + "/query", params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features")
    if not isinstance(features, list):
        raise RuntimeError(f"Unexpected GeoJSON response from {service}")
    return features


def text_values(feature: dict) -> str:
    values = feature.get("properties") or {}
    return " ".join(str(value) for value in values.values() if value is not None).lower()


def select_geometry(features: Iterable[dict], terms: tuple[str, ...], label: str):
    matches = []
    for feature in features:
        text = text_values(feature)
        if all(term.lower() in text for term in terms):
            geom = feature.get("geometry")
            if geom:
                parsed = shape(geom)
                if not parsed.is_empty:
                    matches.append(parsed)
    if not matches:
        raise RuntimeError(f"No {label} geometry matched terms {terms}")
    merged = unary_union(matches)
    return merged.buffer(0) if merged.geom_type in ("Polygon", "MultiPolygon") else merged


def cached_trail_geometry(term: str):
    if not OSM_CACHE.exists():
        return None
    payload = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
    matches = []
    for feature in payload.get("features", []):
        if term.lower() not in text_values(feature):
            continue
        geom = feature.get("geometry")
        if geom:
            parsed = shape(geom)
            if not parsed.is_empty:
                matches.append(parsed)
    if not matches:
        return None
    merged = unary_union(matches)
    return merged.buffer(0) if merged.geom_type in ("Polygon", "MultiPolygon") else merged


def longest_line(geometry):
    if geometry.geom_type == "LineString":
        return geometry
    merged = linemerge(geometry)
    if merged.geom_type == "LineString":
        return merged
    lines = [part for part in getattr(merged, "geoms", []) if part.geom_type == "LineString"]
    if not lines:
        raise RuntimeError("Expected trail line geometry")
    return max(lines, key=lambda line: line.length)


def extended_line(line: LineString) -> LineString:
    coords = list(line.coords)
    if len(coords) < 2:
        raise RuntimeError("Trail line is too short to build a split boundary")

    def extend(a, b, distance_deg=1.0):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        norm = math.hypot(dx, dy)
        if norm == 0:
            return a
        scale = distance_deg / norm
        return (a[0] + dx * scale, a[1] + dy * scale)

    start = extend(coords[0], coords[1])
    end = extend(coords[-1], coords[-2])
    return LineString([start, *coords, end])


def build_test_scope():
    wilderness_features = query_geojson(WILDERNESS_SERVICE, "wildernessname,areaid,gis_acres,boundarystatus")
    clifty = select_geometry(wilderness_features, ("clifty",), "Clifty Wilderness")

    trail_features = query_geojson(TRAIL_SERVICE, "trail_name,trail_no,trail_class,attributesubset")
    try:
        douglas = select_geometry(trail_features, ("douglas",), "Douglas Trail")
        douglas_source = "USDA Forest Service NFS Trails"
    except RuntimeError:
        douglas = cached_trail_geometry("douglas")
        if douglas is None:
            raise
        douglas_source = "RRGH-hosted OSM Community / Informal trail cache fallback"

    try:
        osborne = select_geometry(trail_features, ("osborne",), "Osborne Bend Loop")
        osborne_source = "USDA Forest Service NFS Trails"
    except RuntimeError:
        osborne = cached_trail_geometry("osborne")
        if osborne is None:
            raise
        osborne_source = "RRGH-hosted OSM Community / Informal trail cache fallback"

    douglas_line = longest_line(douglas)
    divider = extended_line(douglas_line)
    split_result = split(clifty, divider)
    split_parts = [part for part in split_result.geoms if not part.is_empty]
    if len(split_parts) < 2:
        raise RuntimeError("Douglas Trail divider did not split Clifty Wilderness; refusing broad test scope")
    south_parts = [
        part for part in split_parts
        if part.representative_point().y < douglas_line.centroid.y
    ]
    if not south_parts:
        raise RuntimeError("Douglas Trail did not produce a south-side Clifty test zone")
    south_douglas = unary_union(south_parts).buffer(0)
    south_fraction = south_douglas.area / clifty.area
    if not 0.03 <= south_fraction <= 0.70:
        raise RuntimeError(f"Douglas south-side scope is unexpectedly broad/narrow ({south_fraction:.3f}); refusing generation")

    ominx, ominy, omaxx, omaxy = osborne.bounds
    ocenter_x = (ominx + omaxx) / 2.0
    ocenter_y = (ominy + omaxy) / 2.0
    cminx, cminy, cmaxx, cmaxy = clifty.bounds
    osborne_ne = clifty.intersection(box(ocenter_x, ocenter_y, cmaxx + 0.01, cmaxy + 0.01)).buffer(0)
    if osborne_ne.is_empty:
        raise RuntimeError("Osborne Bend Loop did not produce a northeast Clifty test zone")
    osborne_fraction = osborne_ne.area / clifty.area
    if not 0.01 <= osborne_fraction <= 0.45:
        raise RuntimeError(f"Osborne northeast scope is unexpectedly broad/narrow ({osborne_fraction:.3f}); refusing generation")

    scope = unary_union([south_douglas, osborne_ne]).buffer(0)
    scope_fraction = scope.area / clifty.area
    if scope_fraction >= 0.80:
        raise RuntimeError(f"Combined test scope covers too much of Clifty Wilderness ({scope_fraction:.3f}); refusing generation")
    return {
        "clifty": clifty,
        "douglas": douglas,
        "osborne": osborne,
        "south_douglas": south_douglas,
        "osborne_ne": osborne_ne,
        "scope": scope,
        "douglas_source": douglas_source,
        "osborne_source": osborne_source,
        "osborne_center": [ocenter_x, ocenter_y],
        "south_fraction": south_fraction,
        "osborne_fraction": osborne_fraction,
        "scope_fraction": scope_fraction,
    }


def process_sector(rrg, sector: dict, scope: dict) -> dict | None:
    bounds = sector["boundsWgs84"]
    core_ll = box(*bounds)
    zone_ll = scope["scope"].intersection(core_ll)
    if zone_ll.is_empty:
        return None

    sector_id = str(sector["id"])
    print(f"Processing Clifty test {sector_id} {bounds}", flush=True)
    dem, transform, request_params = rrg.request_dem(bounds)
    dem_digest = rrg.array_sha256(dem)

    original_threshold = rrg.MIN_ELEVATION_M
    rrg.MIN_ELEVATION_M = LOW_ELEVATION_FT / FEET_PER_METER
    try:
        fields = rrg.terrain_fields(dem, transform)
        east_alpha = rrg.trace_alpha(
            dem, transform, fields["east_lip"], fields["allowed"],
            fields["east_distance"], fields["east_indices"], fields["smooth"]
        )
        west_alpha = rrg.trace_alpha(
            dem, transform, fields["west_lip"], fields["allowed"],
            fields["west_distance"], fields["west_indices"], fields["smooth"]
        )
    finally:
        rrg.MIN_ELEVATION_M = original_threshold

    low_m = LOW_ELEVATION_FT / FEET_PER_METER
    high_m = HIGH_ELEVATION_FT / FEET_PER_METER
    band = (dem >= low_m) & (dem < high_m)
    east_alpha *= band
    west_alpha *= band
    east_hard = fields["east_lip"] & band
    west_hard = fields["west_lip"] & band

    zone_web = shapely_transform(rrg.TO_WEB.transform, zone_ll)
    core_web = rrg.core_polygon_web(bounds)
    clip_web = zone_web.intersection(core_web)
    features = []
    features.extend(rrg.vectorize(east_alpha, east_hard, transform, "sunrise", clip_web, sector_id))
    features.extend(rrg.vectorize(west_alpha, west_hard, transform, "sunset", clip_web, sector_id))
    for feature in features:
        lon, lat = shape(feature["geometry"]).representative_point().coords[0]
        point = shape({"type": "Point", "coordinates": [lon, lat]})
        in_south = scope["south_douglas"].covers(point)
        in_osborne = scope["osborne_ne"].covers(point)
        feature["properties"]["testBandFeet"] = [LOW_ELEVATION_FT, HIGH_ELEVATION_FT]
        feature["properties"]["testZone"] = (
            "south-of-douglas+osborne-ne" if in_south and in_osborne
            else "south-of-douglas" if in_south
            else "osborne-ne"
        )

    output = {
        "type": "FeatureCollection",
        "name": f"Clifty 1000-1100 ft sunlight test {sector_id}",
        "features": features,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{sector_id}.geojson"
    path = OUT_DIR / filename
    rrg.write_json(path, output, compact=True)
    return {
        "id": sector_id,
        "boundsWgs84": bounds,
        "file": f"data/map/clifty-sun-1000-1100-test/{filename}",
        "features": len(features),
        "sunriseHardCells": int(east_hard.sum()),
        "sunsetHardCells": int(west_hard.sum()),
        "sunriseGradientCells": int(np.count_nonzero(east_alpha)),
        "sunsetGradientCells": int(np.count_nonzero(west_alpha)),
        "demArraySha256": dem_digest,
        "geojsonSha256": sha256_file(path),
        "request": request_params,
    }


def main() -> None:
    rrg = load_accepted_module()
    accepted_before = accepted_overlay_fingerprint()
    scope = build_test_scope()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.geojson"):
        old.unlink()

    sectors = []
    total_features = 0
    for sector in rrg.sector_grid():
        result = process_sector(rrg, sector, scope)
        if result is None:
            continue
        sectors.append(result)
        total_features += result["features"]

    accepted_after = accepted_overlay_fingerprint()
    if accepted_before != accepted_after:
        raise RuntimeError("Accepted 1,100+ Sunrise / Sunset Potential files changed during test generation")

    manifest = {
        "version": "clifty-1000-1100-test-v1",
        "status": "staging-owner-uat-only",
        "defaultEnabled": False,
        "acceptedLayerModified": False,
        "acceptedOverlayFingerprintSha256": accepted_after,
        "acceptedGeneratorSha256": sha256_file(ACCEPTED_SCRIPT),
        "elevationBandFeet": {"minimumInclusive": LOW_ELEVATION_FT, "maximumExclusive": HIGH_ELEVATION_FT},
        "scope": {
            "wilderness": "Clifty Wilderness",
            "zoneA": "Official Clifty Wilderness south side of Douglas Trail, split by the extended Douglas Trail line",
            "zoneB": "Official Clifty Wilderness northeast quadrant from the Osborne Bend Loop envelope center",
            "douglasGeometrySource": scope["douglas_source"],
            "osborneGeometrySource": scope["osborne_source"],
            "osborneEnvelopeCenterWgs84": scope["osborne_center"],
            "usesWholeCliftyWilderness": False,
            "southOfDouglasCliftyAreaFraction": scope["south_fraction"],
            "osborneNortheastCliftyAreaFraction": scope["osborne_fraction"],
            "combinedCliftyAreaFraction": scope["scope_fraction"],
        },
        "algorithm": {
            "source": "scripts/generate-rrg-lidar-sun.py",
            "sameTerrainRulesAsAcceptedLayer": True,
            "onlyThresholdDifference": "accepted algorithm evaluated from 1,000 ft, then output restricted to cells below 1,100 ft",
        },
        "source": {
            "dem": "KyFromAbove Phase 2 2-foot LiDAR-derived bare-earth DEM",
            "wildernessBoundary": WILDERNESS_SERVICE,
            "trailService": TRAIL_SERVICE,
        },
        "counts": {"sectors": len(sectors), "features": total_features},
        "sectors": sectors,
        "disclaimer": (
            "Staging test supplement only. Terrain-only heuristic for owner comparison. "
            "The accepted 1,100+ Sunrise / Sunset Potential layer is unchanged."
        ),
    }
    rrg.write_json(OUT_MANIFEST, manifest)
    print(json.dumps(manifest["counts"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
