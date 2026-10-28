#!/usr/bin/env python3
"""Validate benchmark receipts, make private evidence TARs, and model storage.

These evidence archives deliberately do not implement the native install schema.
No upload, catalog mutation, deployment, or Actions dispatch is performed.
"""
import argparse
import io
import json
import math
from pathlib import Path
import tarfile

from benchmark_gorge_pipeline import AOI, json_bytes, receipt_valid
from build_gorge_base_native_v4 import xy
from cached_cog_source import atomic, digest

GIB = 1024 ** 3


def archive_bytes(sizes):
    # Python USTAR emits two EOF blocks, then pads to a 10240-byte record.
    logical = sum(512 + math.ceil(size / 512) * 512 for size in sizes) + 1024
    return math.ceil(logical / 10240) * 10240


def storage_model(archive, extracted, previous_generations=()):
    old = sum(a + e for a, e in previous_generations)
    return {"downloadBytes": archive, "installedLogicalBytes": archive + extracted,
            "cleanInstallPeakLogicalBytes": 2 * archive + extracted,
            "updatePeakLogicalBytes": old + 2 * archive + extracted,
            "steadyWithOneRollbackLogicalBytes": archive + extracted +
                (sum(previous_generations[0]) if previous_generations else 0),
            "freeSpacePreflightAfterStagingBytes": 2 * archive,
            "physicalIPhoneStorageMeasured": False,
            "notes": "Includes retained installed TAR. APFS allocation/clones, metadata, app binary and transport buffers are unmeasured."}


def tile_counts():
    rows = []
    for z in range(10, 19):
        left, bottom = xy(AOI[0], AOI[1], z)
        right, top = xy(AOI[2], AOI[3], z)
        rows.append({"zoom": z, "tileCount": (right - left + 1) * (bottom - top + 1)})
    return rows


def build_archive(root, destination, entries, label):
    manifest = json_bytes({"status": "BENCHMARK EVIDENCE ONLY; NOT INSTALLABLE", "group": label, "files": entries})
    payloads = [("BENCHMARK-MANIFEST.json", manifest)] + [(e["path"], (root / e["path"]).read_bytes()) for e in entries]
    temporary = destination.with_suffix(".partial")
    with tarfile.open(temporary, "w", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in payloads:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(raw), 0o644, 0
            tar.addfile(info, io.BytesIO(raw))
    expected = archive_bytes([len(raw) for _, raw in payloads])
    if temporary.stat().st_size != expected:
        raise ValueError("USTAR padding measurement mismatch")
    with tarfile.open(temporary, "r:") as tar:
        for (name, raw), member in zip(payloads, tar.getmembers(), strict=True):
            if member.name != name or digest(tar.extractfile(member).read()) != digest(raw):
                raise ValueError("TAR member readback mismatch")
    temporary.replace(destination)
    extracted = sum(len(raw) for _, raw in payloads)
    return {"file": destination.name, "sha256": digest(destination.read_bytes()),
            "files": len(payloads), "archiveBytes": expected, "extractedLogicalBytes": extracted,
            "iphoneModel": storage_model(expected, extracted)}


def measure(root, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report = json.loads((root / "BENCHMARK.json").read_text())
    receipts = report["receipts"]
    grouped, layer_samples = {}, {}
    seen = set()
    for receipt in receipts:
        receipt_valid(root, receipt, report["recipeSHA256"])
        for entry in receipt["outputs"]:
            if entry["path"] in seen:
                raise ValueError("Duplicate output across sample jobs")
            seen.add(entry["path"])
            layer = entry["path"].split("/")[1]
            group = layer if layer in ("leaf-on", "leaf-off") else "core"
            grouped.setdefault(group, []).append(entry)
        for level in receipt["zooms"]:
            layer = level.get("layer", receipt["job"].split("-")[-1])
            if "leaf-off" in receipt["job"]: layer = "leaf-off"
            if "leaf-on" in receipt["job"]: layer = "leaf-on"
            layer_samples.setdefault((layer, level["zoom"]), []).append(level["bytes"] / level["tileCount"])
    archives = {g: build_archive(root, out / (g + ".benchmark.tar"), sorted(es, key=lambda e: e["path"]), g)
                for g, es in grouped.items()}
    counts = tile_counts()
    projected = []
    for (layer, zoom), values in sorted(layer_samples.items()):
        # Lower zooms were not sampled: conservative explicit approximation
        # uses the measured z16 bytes/tile for all z10-15 positions.
        selected = [row for row in counts if row["zoom"] <= zoom]
        if not all((layer, max(16, row["zoom"])) in layer_samples for row in selected):
            continue
        estimates = {}
        for name, reducer in [("sampleLow", min), ("sampleMean", lambda a: sum(a)/len(a)), ("sampleHigh", max)]:
            content = sum(row["tileCount"] * reducer(layer_samples[(layer, max(16, row["zoom"]))]) for row in selected)
            n = sum(row["tileCount"] for row in selected)
            # Approximate average 255.5 bytes padding; exact member sizes unknown regionally.
            archive = content + n * (512 + 255.5) + 10240
            estimates[name] = {"extractedBytes": round(content), "archiveBytes": round(archive),
                               "gcsRegionalStorageUSDPerMonth": archive / GIB * .020,
                               "northAmericaEgressUSDPerFullDownload": archive / GIB * .12}
        projected.append({"layer": layer, "maxZoom": zoom, "sampleCount": len(values),
                          "tileCountThroughZoom": sum(r["tileCount"] for r in selected),
                          "meanBytesPerTileAtZoom": sum(values)/len(values), "estimates": estimates})
    result = {"status": "MEASURED BENCHMARK; REGIONAL EXTRAPOLATION NOT FULL COVERAGE ACCEPTANCE",
              "archives": archives, "regionalTileCounts": counts, "regionalLayerEstimates": projected,
              "sourceLedger": report["after"], "runnerTimingIsGitHubActions": False,
              "sourceFailures": report["failures"], "skipped": report["skipped"],
              "assumptions": ["Three convenience windows are not a statistical confidence interval.",
                  "Full rectangle includes boundary overcoverage; no area clipping.",
                  "z10-15 bytes/tile approximated from measured z16; no full-region images produced.",
                  "Regional outputs exclude USGS Topo, vectors, manifests and unresolved leaf-on unless separately measured.",
                  "Sunlight XYZ experiment is not accepted mobile sunlight; use inherited accepted assets for shipping.",
                  "GCS rate scenario .020 USD/GiB-month regional Standard; .12 USD/GiB North America egress, no free-tier credit.",
                  "Backend stream egress counted once; same-region bucket-to-function transfer is free. Cross-region/Tier-1 destinations differ."]}
    atomic(out / "MEASUREMENTS.json", json_bytes(result))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = measure(a.benchmark, a.output)
    print(json.dumps({"archives": result["archives"], "regionalTileCounts": result["regionalTileCounts"]}, indent=2))
