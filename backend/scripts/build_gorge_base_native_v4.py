#!/usr/bin/env python3
"""Build a deterministic, PRIVATE schema-4 Gorge Base native XYZ package.

Reads only an approved existing extracted schema-3 native package and already
approved 256x256 PNG XYZ tile files. No network, secrets, masters, downloads,
server entitlement changes or deployment. Output is an unsigned .rrghpkg TAR
plus a delivery metadata report. Backend must separately authorize/sign it.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tarfile

REQUIRED = ("kentucky-topo", "usgs-topo", "terrain-relief",
            "leaf-on-aerial", "leaf-off-aerial")
MAX_TILES_PER_SET = 100000
MAX_ARCHIVE_BYTES = 1_500_000_000
# Align the private source archive with the bounded native TAR extractor.
MAX_ARCHIVE_FILES = 60_000


def safe(root: Path, relative: str) -> Path:
    parts = Path(relative).parts
    if (not relative or relative.startswith("/") or
            any(part in (".", "..", "") for part in parts) or
            "\\" in relative):
        raise ValueError("Unsafe relative source path")
    candidate = root.joinpath(*parts)
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("Missing, non-file or symlink source: " + relative)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source escapes approved package directory")
    return candidate


def xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 1 << z
    lat = max(-85.05112878, min(85.05112878, lat))
    radians = math.radians(lat)
    x = math.floor((lon + 180) / 360 * n)
    y = math.floor((1 - math.log(math.tan(radians) +
                                 1 / math.cos(radians)) / math.pi) / 2 * n)
    return (max(0, min(n - 1, x)), max(0, min(n - 1, y)))


def sha256(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def png_256(file: Path) -> bool:
    with file.open("rb") as stream:
        header = stream.read(24)
    return (len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n"
            and header[12:16] == b"IHDR"
            and int.from_bytes(header[16:20], "big") == 256
            and int.from_bytes(header[20:24], "big") == 256)


def jpeg_256(file: Path) -> bool:
    """Read JPEG SOF dimensions without a Pillow dependency."""
    with file.open("rb") as image:
        if image.read(2) != b"\xff\xd8":
            return False
        while True:
            first = image.read(1)
            if first != b"\xff":
                return False
            marker = image.read(1)
            while marker == b"\xff":
                marker = image.read(1)
            if not marker:
                return False
            code = marker[0]
            if code in (0xD9, 0xDA):
                return False
            if code in (0x01, *range(0xD0, 0xD8)):
                continue
            size = image.read(2)
            if len(size) != 2:
                return False
            length = int.from_bytes(size, "big")
            if length < 2:
                return False
            if code in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                sof = image.read(5)
                return (len(sof) == 5 and
                        int.from_bytes(sof[1:3], "big") == 256 and
                        int.from_bytes(sof[3:5], "big") == 256)
            image.seek(length - 2, 1)


def build(base: Path, tiles: Path, output: Path,
          version: str, min_zoom: int, max_zoom: int) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]{4,90}", version):
        raise ValueError("Version must be a distinct release-safe identifier")
    if not (8 <= min_zoom <= max_zoom <= 18 and max_zoom >= 15):
        raise ValueError("Require complete 8-18 compatible tile zooms through at least z15")
    if output.exists() or output.with_suffix(output.suffix + ".build.json").exists():
        raise FileExistsError("Never overwrite prior package or provenance report")
    source_manifest = json.loads(safe(base, "NATIVE-MAP.json").read_text())
    if source_manifest.get("schemaVersion") != 3 or source_manifest.get("packageID") != "gorge-base":
        raise ValueError("Input must be approved existing Gorge Base schema 3")
    if source_manifest.get("packageVersion") == version:
        raise ValueError("The schema-4 archive requires a NEW immutable version")
    bounds = source_manifest["boundsWgs84"]
    if not (-180 < bounds["west"] < bounds["east"] < 180 and
            -85 < bounds["south"] < bounds["north"] < 85):
        raise ValueError("Invalid approved map bounds")
    references = [source_manifest["usgsTopo"], source_manifest["terrainRelief"]]
    for field in ("baseRasters", "vectors", "staticAssets"):
        references += source_manifest.get(field) or []
    for field in ("sunPotentialManifest", "weatherManifest"):
        if source_manifest.get(field):
            references.append(source_manifest[field])
    paths: dict[str, Path] = {}
    for item in references:
        path = item["path"]
        source = safe(base, path)
        if sha256(source).lower() != item["sha256"].lower():
            raise ValueError("Existing approved source digest mismatch: " + path)
        paths[path] = source

    sets = []
    for layer in REQUIRED:
        layer_tiles = []
        image_formats = set()
        for z in range(min_zoom, max_zoom + 1):
            nw = xy(bounds["west"], bounds["north"], z)
            se = xy(bounds["east"], bounds["south"], z)
            columns = range(min(nw[0], se[0]), max(nw[0], se[0]) + 1)
            rows = range(min(nw[1], se[1]), max(nw[1], se[1]) + 1)
            if len(columns) * len(rows) > MAX_TILES_PER_SET:
                raise ValueError("Map bounds/zoom exceed capped package budget")
            for x in columns:
                for y in rows:
                    stem = f"{layer}/{z}/{x}/{y}"
                    formats = [ext for ext in ("png", "jpg", "jpeg")
                               if (tiles / f"{stem}.{ext}").is_file()]
                    if len(formats) != 1:
                        raise ValueError("Need exactly one approved image for " + stem)
                    image_format = formats[0]
                    image_formats.add(image_format)
                    rel = f"{stem}.{image_format}"
                    source = safe(tiles, rel)
                    if image_format == "png":
                        dimensions_ok = png_256(source)
                    else:
                        dimensions_ok = jpeg_256(source)
                    if not dimensions_ok:
                        raise ValueError("Invalid or non-256px source tile: " + rel)
                    target = "tiles/" + rel
                    paths[target] = source
                    layer_tiles.append({"z": z, "x": x, "y": y,
                                        "path": target, "sha256": sha256(source)})
                    if len(layer_tiles) > MAX_TILES_PER_SET:
                        raise ValueError("Too many tiles for a single layer")
        sets.append({"id": layer, "minZoom": min_zoom, "maxZoom": max_zoom,
                     "tileFormat": (next(iter(image_formats))
                                    if len(image_formats) == 1 else "mixed"),
                     "tiles": layer_tiles})
    manifest = dict(source_manifest)
    manifest.update({"schemaVersion": 4, "packageVersion": version,
                     "tileSets": sets})
    manifest_blob = (json.dumps(manifest, sort_keys=True,
                                separators=(",", ":")) + "\n").encode("utf-8")
    if len(paths) + 1 > MAX_ARCHIVE_FILES:
        raise ValueError("Package has too many separate tile/files for native extraction")
    size = len(manifest_blob) + sum(p.stat().st_size for p in paths.values())
    if size > MAX_ARCHIVE_BYTES:
        raise ValueError("Package exceeds 1.5 GB uncompressed storage budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Force USTAR: iOS extractor deliberately rejects PAX/GNU
        # extension records and permits only regular safe file entries.
        with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
            for name, path in sorted(paths.items()):
                info = archive.gettarinfo(str(path), arcname=name)
                if not info.isfile():
                    raise ValueError("Unexpected nonregular archive entry")
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            info = tarfile.TarInfo("NATIVE-MAP.json")
            info.size = len(manifest_blob)
            info.uid = info.gid = 0
            info.mtime = 0
            import io
            archive.addfile(info, io.BytesIO(manifest_blob))
        report = {"packageID": "gorge-base", "packageVersion": version,
                  "schemaVersion": 4, "archiveFormat": "tar",
                  "sha256": sha256(output), "byteLength": output.stat().st_size,
                  "tileCountByLayer": {s["id"]: len(s["tiles"]) for s in sets},
                  "coverage": bounds, "minZoom": min_zoom, "maxZoom": max_zoom,
                  "status": "LOCAL BUILD ONLY — NOT AUTHORIZED/SIGNED/DEPLOYED"}
        output.with_suffix(output.suffix + ".build.json").write_text(
            json.dumps(report, indent=2) + "\n")
        return report
    except BaseException:
        output.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approved-v3-root", type=Path, required=True)
    p.add_argument("--approved-xyz-root", type=Path, required=True)
    p.add_argument("--output-rrghpkg", type=Path, required=True)
    p.add_argument("--new-version", required=True)
    p.add_argument("--min-zoom", type=int, default=8)
    p.add_argument("--max-zoom", type=int, default=15)
    args = p.parse_args()
    print(json.dumps(build(args.approved_v3_root, args.approved_xyz_root,
                           args.output_rrghpkg, args.new_version,
                           args.min_zoom, args.max_zoom), indent=2))
