#!/usr/bin/env python3
"""Offline-only coverage/size audit before any Gorge Base v4 package build.

Inspects only already approved local XYZ tiles. Never contacts a provider,
downloads data, fills missing tiles, writes into the input tree or deploys.
Its size estimate is a LOWER BOUND: v3 inherited layers and the v4 manifest
must also fit the existing 1.5 GB native package limit.
"""
import argparse
import json
from pathlib import Path

from build_gorge_base_native_v4 import (
    REQUIRED, MAX_ARCHIVE_BYTES, MAX_ARCHIVE_FILES, xy, png_256, jpeg_256
)


def audit(root: Path, bounds: list[float], min_zoom: int, max_zoom: int) -> dict:
    if (len(bounds) != 4 or
            not (-180 < bounds[0] < bounds[2] < 180) or
            not (-85 < bounds[1] < bounds[3] < 85) or
            not (8 <= min_zoom <= max_zoom <= 18)):
        raise ValueError("Invalid Gorge WGS84 bounds or zoom interval")
    if not root.is_dir():
        raise ValueError("Approved XYZ root directory is missing")
    totals = {"expected": 0, "present": 0, "missing": 0,
              "invalid": 0, "bytes": 0, "tarLowerBound": 0}
    layers = []
    for layer in REQUIRED:
        levels = []
        sample = []
        for z in range(min_zoom, max_zoom + 1):
            nw = xy(bounds[0], bounds[3], z)
            se = xy(bounds[2], bounds[1], z)
            expected = present = invalid = size = 0
            for x in range(min(nw[0], se[0]), max(nw[0], se[0]) + 1):
                for y in range(min(nw[1], se[1]), max(nw[1], se[1]) + 1):
                    expected += 1
                    stem = root / layer / str(z) / str(x) / str(y)
                    existing = [stem.with_suffix("." + ext)
                                for ext in ("png", "jpg", "jpeg")
                                if stem.with_suffix("." + ext).exists()]
                    valid = False
                    if len(existing) == 1 and not existing[0].is_symlink():
                        file = existing[0]
                        valid = (file.is_file() and
                                 file.resolve().is_relative_to(root.resolve()) and
                                 (png_256(file) if file.suffix == ".png"
                                  else jpeg_256(file)))
                    if valid:
                        present += 1
                        length = file.stat().st_size
                        size += length
                        totals["tarLowerBound"] += 512 + ((length + 511) // 512) * 512
                    else:
                        if existing:
                            invalid += 1
                        if len(sample) < 10:
                            sample.append(f"{z}/{x}/{y}")
            totals["expected"] += expected
            totals["present"] += present
            totals["missing"] += expected - present - invalid
            totals["invalid"] += invalid
            totals["bytes"] += size
            levels.append({"zoom": z, "expected": expected,
                           "present": present, "missing": expected - present - invalid,
                           "invalid": invalid, "originalSourceBytes": size})
        report_file = root / f"{layer}.sources.json"
        declaration = False
        if report_file.is_file() and not report_file.is_symlink():
            try:
                report = json.loads(report_file.read_text())
                declaration = (
                    report.get("layerID") == layer and
                    report.get("boundsWGS84") == bounds and
                    report.get("zoomMin") <= min_zoom and
                    report.get("zoomMax") >= max_zoom and
                    bool(report.get("imports")) and
                    all(entry.get("source", {}).get("verifiedOfflineReuse") is True
                        for entry in report["imports"])
                )
            except (OSError, ValueError, TypeError, KeyError):
                declaration = False
        layers.append({"id": layer, "zooms": levels,
                       "missingOrInvalidSample": sample,
                       "sourceDeclarationPresent": declaration})
    # Tar records also require source metadata, inherited v3 layers,
    # manifest and TAR padding. Never treat this lower bound as a fit proof.
    file_count_lower_bound = totals["present"] + 1
    complete = (totals["missing"] == 0 and totals["invalid"] == 0 and
                all(layer["sourceDeclarationPresent"] for layer in layers))
    budget_possible = (totals["tarLowerBound"] < MAX_ARCHIVE_BYTES and
                       file_count_lower_bound <= MAX_ARCHIVE_FILES)
    return {"status": ("INPUT COVERAGE COMPLETE; FULL BUILD STILL REQUIRED"
                       if complete and budget_possible else "NOT BUILD READY"),
            "boundsWGS84": bounds, "minZoom": min_zoom, "maxZoom": max_zoom,
            "totals": totals, "tarFileCountLowerBound": file_count_lower_bound,
            "maxArchiveBytes": MAX_ARCHIVE_BYTES,
            "maxNativeTarEntries": MAX_ARCHIVE_FILES,
            "rasterOnlyBudgetPossible": budget_possible,
            "layers": layers,
            "caution": "Read-only audit, not signed Base or offline field acceptance"}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approved-xyz-root", required=True, type=Path)
    p.add_argument("--bbox", type=float, nargs=4,
                   default=[-83.80, 37.65, -83.40, 37.95])
    p.add_argument("--min-zoom", type=int, default=10)
    p.add_argument("--max-zoom", type=int, default=16)
    p.add_argument("--report-json", type=Path)
    a = p.parse_args()
    result = audit(a.approved_xyz_root, a.bbox, a.min_zoom, a.max_zoom)
    body = json.dumps(result, indent=2) + "\n"
    if a.report_json:
        if a.report_json.exists():
            raise FileExistsError("Never overwrite an existing audit report")
        a.report_json.parent.mkdir(parents=True, exist_ok=True)
        a.report_json.write_text(body)
    print(body)
