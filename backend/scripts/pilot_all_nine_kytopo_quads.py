#!/usr/bin/env python3
"""Nine authentic Kentucky Topo source samples, strictly bounded, QA only.

One source-derived z16 XYZ tile per verified Gorge quadrangle. Neither nine
samples nor their summed JPEG bytes establish complete coverage or pack size.
No whole-TIFF transfer, owner Base package, entitlement or deployment.
"""
import argparse
import json
from pathlib import Path

from pilot_ky_topo_original_xyz import pilot, source

EXPECTED = {f"N{n}E{e}" for n in (13, 14, 15) for e in (29, 30, 31)}
PER_QUAD_LIMIT = 5_000_000
TOTAL_LIMIT = 45_000_000


def run(index, dest, renderer=pilot):
    if (index.get("count") != 9
            or index.get("allOriginalKeysInS3") is not True
            or index.get("rasterBytesFetched") != 0
            or index.get("boundsWGS84") != [-83.80, 37.65, -83.40, 37.95]):
        raise ValueError("Only approved complete official nine-quad Gorge source inventory")
    quads = index.get("quadrangles", [])
    if len(quads) != 9 or {q.get("id") for q in quads} != EXPECTED:
        raise ValueError("Duplicate, missing or foreign original KyTopo sources")
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError("Refuse to replace existing QA source evidence")
    results, bytes_used = [], 0
    for quad in sorted(EXPECTED):
        # Ensure official source identity and public object length, before any
        # network request by the reader.
        source(index, quad)
        receipt = renderer(index, dest / quad, quad, PER_QUAD_LIMIT)
        amount = receipt.get("sourceBytesTransferred")
        addr = receipt.get("xyz")
        if (not isinstance(amount, int) or not 0 < amount <= PER_QUAD_LIMIT
                or not isinstance(addr, dict) or addr.get("z") != 16
                or receipt.get("original", {}).get("sourceQuad") != quad
                or receipt.get("alphaMin") != 255.0
                or not receipt.get("rasterQA", {}).get("pixelAndGeographicAlignmentVerified")
                or not isinstance(receipt.get("derivedSha256"), str)
                or len(receipt["derivedSha256"]) != 64):
            raise ValueError("Unacceptable original-source QA for " + quad)
        bytes_used += amount
        if bytes_used > TOTAL_LIMIT:
            raise ValueError("Aggregate pilot source-transfer limit exceeded")
        results.append({
            "quad": quad, "xyz": addr,
            "sourceRangeBytes": amount,
            "jpegBytes": receipt.get("derivedImageBytes"),
            "jpegSha256": receipt["derivedSha256"],
        })
    result = {
        "status": "NINE GENUINE KYTOPO CENTER-SAMPLE XYZ TILES VERIFIED — NOT REGIONAL COVERAGE",
        "sourceQuadCount": 9, "samples": results,
        "actualPartialSourceBytes": bytes_used,
        "maxAllowedPartialSourceBytes": TOTAL_LIMIT,
        "originalWholeTiffsDownloaded": False,
        "completeGorgePixelCoverage": False,
        "finalCoreDownloadBytes": None,
        "finalCoreInstalledBytes": None,
        "customerBasePackageReady": False,
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "NINE-QUAD-PILOT-ONLY.json").write_text(json.dumps(result, indent=2)+"\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-quads", type=Path, required=True)
    p.add_argument("--qa-root", type=Path, required=True)
    a = p.parse_args()
    r = run(json.loads(a.official_quads.read_text()), a.qa_root)
    print(json.dumps({"status": r["status"], "quadCount": r["sourceQuadCount"],
                      "rangeBytes": r["actualPartialSourceBytes"],
                      "samples": r["samples"]}, indent=2))
