#!/usr/bin/env python3
"""Measure real, approved local XYZ files for owner-approved offline pack groups.
Read only: no network, estimated missing pixels, package signing or deployment.
"""
import argparse
import json
from pathlib import Path
from build_gorge_base_native_v4 import xy, png_256, jpeg_256

GROUPS = {
    "required-core": ("kentucky-topo", "usgs-topo", "terrain-relief"),
    "optional-leaf-on": ("leaf-on-aerial",),
    "optional-leaf-off": ("leaf-off-aerial",),
}
LIMIT_BYTES = 1_500_000_000
LIMIT_FILES = 60_000


def measure(root, bounds, zmin, zmax):
    if (not root.is_dir() or root.is_symlink() or len(bounds) != 4
            or not (-180 < bounds[0] < bounds[2] < 180)
            or not (-85 < bounds[1] < bounds[3] < 85)
            or not 8 <= zmin <= zmax <= 18):
        raise ValueError("Invalid approved XYZ source root, bounds or zoom range")
    layers = {}
    for group_layers in GROUPS.values():
        for layer in group_layers:
            rows = []
            for z in range(zmin, zmax + 1):
                a, b = xy(bounds[0], bounds[3], z), xy(bounds[2], bounds[1], z)
                count = good = invalid = byte_count = 0
                for x in range(min(a[0], b[0]), max(a[0], b[0]) + 1):
                    for y in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
                        count += 1
                        base = root / layer / str(z) / str(x) / str(y)
                        found = [base.with_suffix("." + ext)
                                 for ext in ("png", "jpg", "jpeg")
                                 if base.with_suffix("." + ext).exists()
                                 or base.with_suffix("." + ext).is_symlink()]
                        if (len(found) == 1 and found[0].is_file()
                                and not found[0].is_symlink()
                                and found[0].resolve().is_relative_to(root.resolve())
                                and (png_256(found[0]) if found[0].suffix == ".png"
                                     else jpeg_256(found[0]))):
                            good += 1
                            byte_count += found[0].stat().st_size
                        elif found:
                            invalid += 1
                rows.append({"zoom": z, "expected": count, "valid": good,
                             "invalid": invalid, "missing": count - good - invalid,
                             "measuredBytes": byte_count})
            layers[layer] = rows
    packs = []
    for name, group_layers in GROUPS.items():
        records = [v for layer in group_layers for v in layers[layer]]
        count = sum(v["expected"] for v in records)
        valid = sum(v["valid"] for v in records)
        measured = sum(v["measuredBytes"] for v in records)
        complete = valid == count and sum(v["invalid"] for v in records) == 0
        packs.append({
            "id": name, "required": name == "required-core",
            "layers": list(group_layers), "expectedTiles": count,
            "validTiles": valid, "missingOrInvalid": count - valid,
            "measuredSourceTileBytes": measured,
            "minimalUncompressedTarBytes": measured + 512 * valid + 1024,
            "sourceCoverageComplete": complete,
            "finalDownloadBytes": None, "finalInstalledBytes": None,
            "finalPeakInstallBytes": None,
            "status": ("RASTER TILES PRESENT; PROVENANCE/SHARED ASSETS/BUILD OPEN"
                       if complete else "INCOMPLETE; FINAL SIZE UNKNOWN")
        })
    return {
        "status": "LOCAL MEASUREMENT ONLY — NOT A DOWNLOADABLE PACKAGE",
        "coverageLabel": "Red River Gorge region, not all Kentucky",
        "boundsWGS84": bounds, "zoomMin": zmin, "zoomMax": zmax,
        "packs": packs, "layers": layers,
        "existingSingleArchiveLimitBytes": LIMIT_BYTES,
        "existingSingleArchiveFileLimit": LIMIT_FILES,
        "cautions": [
            "A measured subset is not a forecast of missing tile bytes.",
            "Required core also needs shared trail, route, sun and metadata assets.",
            "Final network and installed sizes require built, validated archives.",
            "No approved numeric limit increase, backend change or device acceptance."
        ]
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approved-xyz-root", required=True, type=Path)
    p.add_argument("--bbox", type=float, nargs=4,
                   default=[-83.80, 37.65, -83.40, 37.95])
    p.add_argument("--min-zoom", type=int, default=10)
    p.add_argument("--max-zoom", type=int, default=16)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Refuse to overwrite existing measurement")
    result = measure(a.approved_xyz_root, a.bbox, a.min_zoom, a.max_zoom)
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["packs"], indent=2))
