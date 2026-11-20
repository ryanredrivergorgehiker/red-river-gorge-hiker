#!/usr/bin/env python3
"""Read-only exact bytes of existing approved schema-3 Gorge Base shared assets.

Does not write source files, download data, infer future package sizes, or
promote obsolete low-resolution rasters as native high-resolution maps.
"""
import argparse
import json
from pathlib import Path

from build_gorge_base_native_v4 import safe, sha256

SHARED_ARRAYS = ("vectors", "staticAssets")
SHARED_OBJECTS = ("sunPotentialManifest", "weatherManifest")
LEGACY_OBJECTS = ("usgsTopo", "terrainRelief")
LEGACY_ARRAYS = ("baseRasters",)


def measure(root: Path):
    manifest = json.loads(safe(root, "NATIVE-MAP.json").read_text())
    if manifest.get("schemaVersion") != 3 or manifest.get("packageID") != "gorge-base":
        raise ValueError("Only a verified existing native schema3 Gorge Base input")
    seen = {}
    groups = {"shared-core": {}, "legacy-single-image-rasters": {}}

    def record(entry, category):
        name = entry["path"]
        path = safe(root, name)
        digest = entry["sha256"]
        if sha256(path).lower() != digest.lower():
            raise ValueError("Inherited source hash mismatch: " + name)
        prior = seen.get(name)
        if prior is not None and prior != category:
            raise ValueError("Shared and legacy source collision: " + name)
        if prior == category:
            return
        seen[name] = category
        groups[category][name] = path.stat().st_size

    for field in SHARED_ARRAYS:
        for entry in manifest.get(field) or []:
            record(entry, "shared-core")
    for field in SHARED_OBJECTS:
        if manifest.get(field):
            record(manifest[field], "shared-core")
    for field in LEGACY_OBJECTS:
        record(manifest[field], "legacy-single-image-rasters")
    for field in LEGACY_ARRAYS:
        for entry in manifest.get(field) or []:
            record(entry, "legacy-single-image-rasters")
    summary = {}
    for category, sources in groups.items():
        summary[category] = {
            "actualFiles": len(sources),
            "actualBytes": sum(sources.values()),
            "fileSizes": dict(sorted(sources.items())),
        }
    return {
        "status": "MEASURED EXISTING HASH-VERIFIED V3 FILES ONLY",
        "packageVersion": manifest["packageVersion"],
        "groups": summary,
        "allFilesHashVerified": True,
        "finalCoreTransferBytes": None,
        "finalCoreInstalledBytes": None,
        "notReleaseReady": True,
        "note": "The current v4 monolithic builder still includes legacy images. "
                "Shared vectors and Sunlight content may require referenced "
                "additional rasters; resolve before any modular final-size claim."
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approved-v3-root", type=Path, required=True)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Previous source-size evidence is immutable")
    result = measure(a.approved_v3_root)
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: {"actualFiles": v["actualFiles"],
                          "actualBytes": v["actualBytes"]}
                      for k, v in result["groups"].items()}, indent=2))
