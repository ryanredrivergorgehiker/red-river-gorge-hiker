#!/usr/bin/env python3
"""Bind expanded catalog candidates to full windows; metadata coverage only.

An intersecting source bbox is insufficient: compute union coverage of every
window, including the terrain halo. Pixel masks, georeferencing, seams, vertical
units and commercial/offline rights remain separate production gates.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from rrgh_required_inventory import Manifest, canonical, extent, require

CATALOG_SHA = "fbffbb972a32e6b226519b94370443dc5e47d55759c2a85b55eeb6b993489193"
EXPECTED = {"hiking": 9, "dem": 558, "leaf-off": 558}
PREFIXES = {"hiking": "elevation/KyTopoMapSeries/COGs/", "dem": "elevation/DEM/Phase2/",
            "leaf-off": "imagery/orthos/Phase3/"}


def clip(a, b):
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[0] < box[2] and box[1] < box[3] else None


def union_fraction(window, boxes):
    """Exact rectangle union in lon/lat coordinates, never an earth-area percentage."""
    rects = [r for b in boxes if (r := clip(window, b)) is not None]
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        ys = sorted((r[1], r[3]) for r in rects if r[0] < right and r[2] > left)
        total, start, end = 0.0, None, None
        for bottom, top in ys:
            if start is None:
                start, end = bottom, top
            elif bottom > end:
                total += end-start
                start, end = bottom, top
            else:
                end = max(end, top)
        if start is not None:
            total += end-start
        area += (right-left)*total
    return min(1.0, area / ((window[2]-window[0])*(window[3]-window[1])))


def load_catalog(path):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == CATALOG_SHA, "Reviewed catalog bytes changed")
    catalog = json.loads(raw)
    require(catalog["metadataCandidateCounts"] == EXPECTED, "Candidate counts changed")
    result = {}
    for family, count in EXPECTED.items():
        rows, seen = [], set()
        for obj in catalog["catalog"][family]:
            identity = obj["id"]
            url = obj.get("officialOriginalCogURL", obj.get("officialCogURL"))
            b = obj.get("boundsWGS84", obj.get("bbox"))
            require(identity not in seen and url.startswith("https://kyfromabove.s3.us-west-2.amazonaws.com/"+PREFIXES[family]) and
                    url.endswith(".tif"), "Duplicate or unreviewed original source")
            require(len(b) == 4 and b[0] < b[2] and b[1] < b[3], "Invalid source bbox")
            seen.add(identity)
            rows.append({"id": identity, "url": url, "bbox": b})
        require(len(rows) == count, "Incomplete candidate family")
        result[family] = rows
    return result


def windows(manifest, catalog):
    for layer in ("hiking", "terrain", "leaf-off"):
        family = "dem" if layer == "terrain" else layer
        left, right, top, bottom = manifest.grids[layer, 16]
        for x in range(left, right+1):
            for y in range(top, bottom+1):
                # Same fractional finest-grid halo used by current production.
                halo = 1/512 if layer == "terrain" else 0
                w, _, _, n = extent(16, x-halo, y-halo)
                _, s, e, _ = extent(16, x+halo, y+halo)
                window = [w, s, e, n]
                candidates = [obj for obj in catalog[family] if clip(window, obj["bbox"])]
                fraction = union_fraction(window, [c["bbox"] for c in candidates])
                inside = clip(window, manifest.spec["boundsWGS84"])
                inside_fraction = union_fraction(inside, [c["bbox"] for c in candidates]) if inside else None
                yield {"layer": layer, "z": 16, "x": x, "y": y, "boundsWGS84": window,
                    "catalogSHA256": CATALOG_SHA, "manifestRevision": manifest.revision,
                    "sourceCandidates": [c["id"] for c in candidates],
                    "metadataUnionFraction": fraction, "metadataFullWindowCovered": fraction >= 1-1e-10,
                    "withinRectangleMetadataUnionFraction": inside_fraction,
                    "withinRectangleFullMetadataCoverage": inside_fraction is not None and inside_fraction >= 1-1e-10,
                    "requiresMosaic": len(candidates) > 1,
                    "sourceCoverage": "awaiting_source_validation", "productionReady": False,
                    "requiredValidation": ["object_identity_and_native_resolution", "full_window_masks",
                        "mosaic_seams", "crs_georeferencing", "vertical_units_if_dem",
                        "commercial_offline_rights", "attribution", "resource_reservation"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("spec", "catalog", "windows", "summary"):
        p.add_argument("--"+name, required=True, type=Path)
    args = p.parse_args()
    require(not args.windows.exists() and not args.summary.exists(), "Refuse to replace evidence")
    manifest = Manifest(json.loads(args.spec.read_bytes()))
    catalog = load_catalog(args.catalog)
    counts, digest = Counter(), hashlib.sha256()
    with args.windows.open("xb") as out:
        for row in windows(manifest, catalog):
            data = canonical(row)
            digest.update(data); out.write(data)
            layer = row["layer"]
            counts[layer+"Windows"] += 1
            counts[layer+"FullMetadataWindows"] += row["metadataFullWindowCovered"]
            counts[layer+"RectangleIntersectionCovered"] += row["withinRectangleFullMetadataCoverage"]
            counts[layer+"MosaicWindows"] += row["requiresMosaic"]
    summary = {"format": "rrgh-expanded-source-window-intake-v1", "catalogSHA256": CATALOG_SHA,
               "windowsSHA256": digest.hexdigest(), "counts": dict(counts),
               "fullPixelCoverageProved": False, "licenseReviewComplete": False,
               "demUnitsConversionApplied": False, "promotedToProduction": False}
    with args.summary.open("xb") as out:
        out.write(canonical(summary))
    print(canonical(summary).decode(), end="")


if __name__ == "__main__":
    main()
