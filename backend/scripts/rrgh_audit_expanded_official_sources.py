#!/usr/bin/env python3
"""Offline, metadata-only coverage audit of the already-discovered official map sources.

NEVER authorizes production or asserts full pixel coverage, elevation units,
licenses, offline package readiness, or source read permissions.
"""
import argparse
import base64
import collections
import hashlib
import json
import math
from pathlib import Path
import zlib

BOUNDS = (-83.8, 37.65, -83.4, 37.95)
EXPECTED_COUNT = {"hiking": 9, "dem": 558, "leaf-off": 558}
PREFIX = {
    "hiking": "https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/KyTopoMapSeries/COGs/",
    "dem": "https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/Phase2/",
    "leaf-off": "https://kyfromabove.s3.us-west-2.amazonaws.com/imagery/orthos/Phase3/",
}
CATALOG_SHA = "fbffbb972a32e6b226519b94370443dc5e47d55759c2a85b55eeb6b993489193"


def xy(lon, lat, z):
    n = 2 ** z
    return (math.floor((lon + 180) / 360 * n),
            math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def window(z, x, y, halo=0):
    n = 2 ** z
    def lon(a):
        return a / n * 360 - 180
    def lat(b):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * b / n))))
    return (lon(x - halo), lat(y + 1 + halo), lon(x + 1 + halo), lat(y - halo))


def intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def audit(catalog_file, region_file):
    raw = Path(catalog_file).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA:
        raise ValueError("Candidate metadata digest differs from independently audited source")
    candidate = json.loads(raw)
    if (candidate["metadataCandidateCounts"] != EXPECTED_COUNT or
            candidate["unchangedPinnedSourceIDsVerified"] is not True or
            "NOT YET CERTIFIED" not in candidate["status"]):
        raise ValueError("Candidate provenance or explicit validation caveat missing")
    original = json.loads(zlib.decompress(base64.b64decode(Path(region_file).read_bytes())))
    if tuple(original["boundsWGS84"]) != BOUNDS:
        raise ValueError("Original regional geographic extent changed")
    orig = original["inventory"]["sources"]
    coverage = {}
    left, bottom = xy(BOUNDS[0], BOUNDS[1], 16)
    right, top = xy(BOUNDS[2], BOUNDS[3], 16)
    windows = [(x, y) for x in range(left, right + 1) for y in range(top, bottom + 1)]
    if len(windows) != 5180:
        raise ValueError("Original region grid changed")
    for layer in ("hiking", "terrain", "leaf-off"):
        family = "dem" if layer == "terrain" else layer
        source = candidate["catalog"][family]
        if len(source) != EXPECTED_COUNT[family]:
            raise ValueError("Expanded source count changed")
        by_id = {}
        boxes = []
        for obj in source:
            oid = obj["id"]
            u = obj["officialOriginalCogURL"] if family == "hiking" else obj["officialCogURL"]
            b = obj["boundsWGS84"] if family == "hiking" else obj["bbox"]
            if not isinstance(oid, str) or oid in by_id or not u.startswith(PREFIX[family]):
                raise ValueError("Original public source identity/URL invalid")
            if not u.endswith(".tif") or len(b) != 4 or any(not math.isfinite(v) for v in b):
                raise ValueError("Source asset or bbox invalid")
            by_id[oid] = (u, b)
            boxes.append(b)
        for previous in orig[family]:
            u, b = by_id[previous["id"]]
            if previous["url"] != u or any(abs(a - v) > 1e-9 for a, v in zip(previous["bbox"], b)):
                raise ValueError("Previously accepted original source identity changed")
        histogram = collections.Counter()
        sample_uncovered = []
        halo = 1 / 512 if layer == "terrain" else 0
        for x, y in windows:
            rect = window(16, x, y, halo)
            n = sum(intersects(b, rect) for b in boxes)
            histogram[n] += 1
            if n == 0 and len(sample_uncovered) < 8:
                sample_uncovered.append(f"{layer}-16-{x}-{y}")
        coverage[layer] = {
            "indexedOfficialCandidates": len(source),
            "existingPinnedSourceCount": len(orig[family]),
            "windowsWithAtLeastOneCandidateBBox": len(windows) - histogram[0],
            "windowsWithoutCandidateBBox": histogram[0],
            "metadataOverlapHistogram": dict(sorted(histogram.items())),
            "examplesMissing": sample_uncovered,
        }
    report = {
        "format": "rrgh-official-expanded-source-metadata-geometry-audit-v1",
        "regionBoundsWGS84": BOUNDS,
        "regionalZ16WindowsPerFamily": len(windows),
        "catalogSHA256": CATALOG_SHA,
        "originalExistingSourceIdentitiesUnchanged": True,
        "byLayer": coverage,
        "rasterPixelsValidated": False,
        "demVerticalUnitsValidatedForNewSources": False,
        "newSourceLicenseReviewComplete": False,
        "promotedToProduction": False,
        "dispatched": False,
    }
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True, type=Path)
    p.add_argument("--region", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    report = audit(args.catalog, args.region)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    if any(x["windowsWithoutCandidateBBox"] != 0 for x in report["byLayer"].values()):
        raise SystemExit("METADATA_COVERAGE_GAP: cannot claim complete bbox catalog")
    print("RRGH_OFFICIAL_SOURCE_METADATA_COVERS_FULL_Z16_REGION__NOT_PIXEL_QA")


if __name__ == "__main__":
    main()
