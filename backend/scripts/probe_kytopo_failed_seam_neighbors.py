#!/usr/bin/env python3
"""Bounded search around ONE rejected KyTopo source seam. Private raster QA only.

A source bounding rectangle is not pixel coverage. Tries at most six nearby
z16 tiles that still intersect exactly the verified two original source
rectangles. Only genuine TIFF pixels read via existing capped HTTP206 proxy.
No fake coverage, archive generation, entitlement, or deployment.
"""
import argparse
import json
from pathlib import Path

from plan_kytopo_quad_seams import BBOX, overlap, plan, xyz_bounds
from pilot_kytopo_12_source_seams import render

PAIR = ["N14E31", "N15E31"]
# Start on the north side of the rejected bbox-only candidate.
OFFSETS = [(0,-1),(-1,-1),(1,-1),(0,-2),(-1,-2),(1,-2)]
MAX_TOTAL = 30_000_000


def examine(index, root, renderer=render):
    baseline = [r for r in plan(index)["candidates"] if r["pair"] == PAIR]
    if len(baseline) != 1:
        raise ValueError("Unique official source seam candidate required")
    ref = baseline[0]
    quads = {q["id"]:q for q in index["quadrangles"]}
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("Never overwrite real-source forensic samples")
    attempts = []
    total = 0
    winner = None
    for dx,dy in OFFSETS:
        if len(attempts) >= len(OFFSETS):
            break
        address = {**ref["xyz"], "x":ref["xyz"]["x"]+dx,
                   "y":ref["xyz"]["y"]+dy}
        bound = xyz_bounds(address["x"],address["y"],address["z"])
        if not overlap(bound,BBOX):
            continue
        matches = sorted(id for id,q in quads.items()
                         if overlap(bound,q["boundsWGS84"]))
        if matches != PAIR:
            continue
        trial = {**ref,"xyz":address}
        try:
            result = renderer(index,trial,root/f"trial_{len(attempts)+1}")
            amount = result["sourceBytesTransferred"]
            if not (0 < amount <= 5_000_000) or result["mosaicAlphaMin"] != 255:
                raise ValueError("Insufficient full-coverage source evidence")
            attempts.append({"xyz":address,"status":"PASSED ORIGINAL PIXEL QA",
                             "bytes":amount,"hash":result["jpegSha256"],
                             "sourcePixelAlpha":result["sourcePixelAlpha"]})
            winner = address
            total += amount
            break
        except Exception as exc:
            attempts.append({"xyz":address,"status":"REJECTED",
                             "error":type(exc).__name__+": "+str(exc)[:250]})
            # Strict per-candidate cap ensures even all six failures are bounded.
    result = {"status":"ONE ORIGINAL KYTOPO SEAM NEIGHBORHOOD SOURCE QA",
              "originalRejectedXYZ":ref["xyz"],"pair":PAIR,
              "attempts":attempts,"acceptedAlternateXYZ":winner,
              "maxCandidateReads":len(OFFSETS),"maxTransferBytes":MAX_TOTAL,
              "notFullRegionEvidence":True,"notOwnerAcceptedMap":True}
    root.mkdir(parents=True,exist_ok=True)
    (root/"SEAM-NEIGHBORHOOD-FORENSICS.json").write_text(json.dumps(result,indent=2)+"\n")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-quads",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=examine(json.loads(a.official_quads.read_text()),a.out)
    print(json.dumps(result,indent=2))
    if result["acceptedAlternateXYZ"] is None:
        raise SystemExit("No genuine substitute source boundary verified")
