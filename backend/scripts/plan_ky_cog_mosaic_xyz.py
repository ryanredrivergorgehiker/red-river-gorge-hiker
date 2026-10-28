#!/usr/bin/env python3
"""Plan real multi-source Gorge XYZ from bounded Kentucky COG footprints.

No network, no source pixel reads, no synthetic/bridged map imagery. Candidate
footprints are geographic BBOXES (not final pixel data coverage); downstream
GDAL must mosaic ALL intersecting source COGs and verify actual raster pixels.
Zoom 10–12 should be downsampled from genuine z13 derivatives, not fabricated.
"""
import argparse
import json
import math
from pathlib import Path

from build_gorge_base_native_v4 import xy

VALID_ROLES = ("terrain-dem-candidate", "leaf-off-ortho-candidate")


def xyz_bounds(x, y, z):
    n = 1 << z
    def lat(row):
        return math.degrees(math.atan(math.sinh(math.pi * (1-2*row/n))))
    return [x/n*360-180, lat(y+1), (x+1)/n*360-180, lat(y)]


def overlap(a, b):
    return (a[0] < b[2] and a[2] > b[0] and
            a[1] < b[3] and a[3] > b[1])


def intersection(a, b):
    if not overlap(a, b):
        return None
    return [max(a[0], b[0]), max(a[1], b[1]),
            min(a[2], b[2]), min(a[3], b[3])]


def sampled_covered(clip, sources):
    # Approximate BBOX cover probe, always followed by actual GDAL QA.
    for i in (1, 3, 5, 7, 9):
        lon = clip[0] + (clip[2]-clip[0])*i/10
        for j in (1, 3, 5, 7, 9):
            lat = clip[1] + (clip[3]-clip[1])*j/10
            if not any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3]
                       for b in sources):
                return False
    return True


def plan(official_inventory, min_zoom=13, max_zoom=16):
    bounds = official_inventory.get("boundsWGS84")
    if (official_inventory.get("noOriginalPixelDataDownloaded") is not True or
            not isinstance(bounds, list) or len(bounds) != 4 or
            not (-83.81 <= bounds[0] < bounds[2] <= -83.39 and
                 37.64 <= bounds[1] < bounds[3] <= 37.96) or
            not (13 <= min_zoom <= max_zoom <= 16)):
        raise ValueError("Only vetted Gorge COG footprints and z13–16 allowed")
    results = []
    for group in official_inventory.get("records", []):
        kind = group.get("kind")
        if kind not in VALID_ROLES or group.get("paginationExhausted") is not True:
            raise ValueError("Do not plan from incomplete official source inventory")
        sources = group.get("sourceFiles", [])
        if not isinstance(sources, list) or len(sources) > 1200:
            raise ValueError("Unexpected COG source inventory cardinality")
        catalog = {}
        for entry in sources:
            name, rect, url = (entry.get("id"), entry.get("bbox"),
                               entry.get("officialCogURL"))
            if (not isinstance(name, str) or name in catalog or
                    not isinstance(rect, list) or len(rect) != 4 or
                    not isinstance(url, str) or
                    not url.startswith("https://kyfromabove.s3.us-west-2.amazonaws.com/")):
                raise ValueError("Missing, duplicate or unofficial COG source")
            catalog[name] = {"bbox": rect, "url": url}
        tiles, levels, gaps = [], [], []
        for z in range(min_zoom, max_zoom+1):
            nw = xy(bounds[0], bounds[3], z)
            se = xy(bounds[2], bounds[1], z)
            level_count, multi = 0, 0
            for x in range(nw[0], se[0]+1):
                for y in range(nw[1], se[1]+1):
                    clipped = intersection(xyz_bounds(x,y,z), bounds)
                    if clipped is None:
                        continue
                    matching = [
                        name for name, asset in catalog.items()
                        if overlap(asset["bbox"], clipped)
                    ]
                    if not matching or not sampled_covered(
                            clipped, [catalog[name]["bbox"] for name in matching]):
                        if len(gaps) < 30:
                            gaps.append(f"{z}/{x}/{y}")
                    if len(matching) > 1:
                        multi += 1
                    tiles.append({"z":z, "x":x, "y":y, "cogs":sorted(matching)})
                    level_count += 1
            levels.append({"zoom":z, "candidateTiles":level_count,
                           "multiSourceTileCount":multi})
        results.append({
            "kind":kind, "collection":group["collection"],
            "officialSourceFileCount":len(catalog), "levels":levels,
            "tileCount":len(tiles), "approximateGapsSample":gaps,
            "noInventedCoverage":True,
            "actualSourceImagePixelsValidated":False,
            "sourceCatalog":catalog, "plannedTiles":tiles,
        })
    return {
        "status":"SOURCE-FOOTPRINT MOSAIC PLAN ONLY — NOT MAP TILES OR SIGNED BASE",
        "boundsWGS84":bounds, "minZoom":min_zoom, "maxZoom":max_zoom,
        "results":results, "noImageryDownloaded":True,
        "mustMosaicEveryIntersectingCOG":True,
        "downstream":"GDAL true CRS mosaic, per-XYZ pixels/hashes and missing-data checks. z10-12 from genuine higher-zoom images.",
    }


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--footprints",required=True,type=Path)
    p.add_argument("--output-json",required=True,type=Path)
    a=p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Refusing to overwrite immutable mosaic plan")
    result=plan(json.loads(a.footprints.read_text()))
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,separators=(",",":"))+"\n")
    print(json.dumps({"status":result["status"],
                      "layers":[{
                        "kind":v["kind"], "sourceFiles":v["officialSourceFileCount"],
                        "plannedXYZ":v["tileCount"],
                        "levels":v["levels"], "gapSamples":v["approximateGapsSample"],
                      } for v in result["results"]]},indent=2))
