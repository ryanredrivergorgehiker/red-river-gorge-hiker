#!/usr/bin/env python3
"""Twelve adjacent official KyTopo original-source seam candidates, metadata ONLY.

A source bounding-rectangle overlap is NOT proof the actual TIFF has pixels.
No image pixels, no package bytes estimated, no protected catalog writes.
"""
import argparse
import itertools
import json
import math
from pathlib import Path

from build_gorge_base_native_v4 import xy
from plan_ky_cog_mosaic_xyz import xyz_bounds
from pilot_ky_topo_original_xyz import source

BBOX = [-83.80, 37.65, -83.40, 37.95]
Z = 16
EXPECTED = {f"N{n}E{e}" for n in (13, 14, 15) for e in (29, 30, 31)}


def overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def adjacent(a, b):
    return abs(int(a[1:3])-int(b[1:3])) + abs(int(a[4:])-int(b[4:])) == 1


def plan(index):
    if (index.get("count") != 9 or index.get("allOriginalKeysInS3") is not True
            or index.get("rasterBytesFetched") != 0
            or index.get("boundsWGS84") != BBOX):
        raise ValueError("Requires exact verified Gorge KyTopo 9-source index")
    quads = index.get("quadrangles", [])
    if len(quads) != 9 or {q.get("id") for q in quads} != EXPECTED:
        raise ValueError("Missing or duplicated official Kentucky quadrangles")
    assets = {q["id"]: {**source(index, q["id"]), "bbox": q["boundsWGS84"]}
              for q in quads}
    west, north = xy(BBOX[0], BBOX[3], Z)
    east, south = xy(BBOX[2], BBOX[1], Z)
    selected = []
    for a, b in itertools.combinations(sorted(assets), 2):
        if not adjacent(a, b):
            continue
        box_a, box_b = assets[a]["bbox"], assets[b]["bbox"]
        intersection = [max(box_a[0], box_b[0], BBOX[0]),
                        max(box_a[1], box_b[1], BBOX[1]),
                        min(box_a[2], box_b[2], BBOX[2]),
                        min(box_a[3], box_b[3], BBOX[3])]
        if not intersection[0] < intersection[2] or not intersection[1] < intersection[3]:
            raise ValueError("Adjacent official quads lack intersecting source bboxes")
        center = [(intersection[0]+intersection[2])/2,
                  (intersection[1]+intersection[3])/2]
        candidates = []
        for x in range(west, east+1):
            for y in range(north, south+1):
                tile = xyz_bounds(x, y, Z)
                if not all(overlap(tile, region) for region in (BBOX, box_a, box_b)):
                    continue
                matched = sorted(name for name, item in assets.items()
                                 if overlap(tile, item["bbox"]))
                midpoint = [(tile[0]+tile[2])/2, (tile[1]+tile[3])/2]
                if not (BBOX[0] < midpoint[0] < BBOX[2]
                        and BBOX[1] < midpoint[1] < BBOX[3]):
                    continue
                distance = abs((midpoint[0]-center[0])*math.cos(math.radians(center[1]))) + abs(midpoint[1]-center[1])
                candidates.append((len(matched) != 2, distance, x, y, matched))
        if not candidates:
            raise ValueError("No bounded original-source seam sample for " + a+"/"+b)
        _, _, x, y, matched = min(candidates)
        if matched != sorted((a, b)):
            raise ValueError("Selected tile touches additional/unexpected sources")
        selected.append({
            "pair": [a, b], "xyz": {"z": Z, "x": x, "y": y},
            "sourceIds": matched,
            "indexOverlapWGS84": intersection,
            "sourceURLs": [assets[k]["url"] for k in matched],
            "sourceOriginalBytes": [assets[k]["length"] for k in matched],
            "sourcePixelCoverageVerified": False,
        })
    if len(selected) != 12 or len({tuple(r["pair"]) for r in selected}) != 12:
        raise ValueError("12 unique adjacent official source boundaries required")
    return {
        "status": "12 VERIFIED INDEX-FOOTPRINT KYTOPO SEAM SAMPLES — NO PIXELS",
        "gorgeRegionWGS84": BBOX, "zoom": Z, "candidateCount": 12,
        "candidates": selected, "originalPixelBytesRetrieved": 0,
        "regionalPixelClosure": False, "finalDownloadBytes": None,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-quads", type=Path, required=True)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Do not overwrite earlier source footprint evidence")
    result = plan(json.loads(a.official_quads.read_text()))
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"count": result["candidateCount"],
                      "xyz": [i["xyz"] for i in result["candidates"]]}, indent=2))
