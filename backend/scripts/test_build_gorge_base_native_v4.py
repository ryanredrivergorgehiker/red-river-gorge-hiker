#!/usr/bin/env python3
"""Strictly synthetic fixture tests; never fetch or publish protected map data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zlib

SCRIPT = Path(__file__).with_name("build_gorge_base_native_v4.py")
spec = importlib.util.spec_from_file_location("native_v4_builder", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def png():
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)
    pixels = (b"\x00" + b"\x88\x99\xaa" * 256) * 256
    return header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


class NativeV4BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.base = root / "approved-v3"
        self.tiles = root / "approved-xyz"
        self.out = root / "new-v4.rrghpkg"
        self.base.mkdir()
        self.tiles.mkdir()
        self.bounds = {"west": -83.640, "east": -83.639,
                       "south": 37.820, "north": 37.821}
        sample = png()
        self.assertTrue(builder.png_256(self._put(self.base, "base/topo.png", sample)))
        self.assertTrue(builder.png_256(self._put(self.base, "base/hill.png", sample)))
        def item(path):
            file = self._put(self.base, path, sample)
            return {"path": path, "sha256": builder.sha256(file)}
        self.manifest = {
            "schemaVersion": 3, "archiveFormat": "tar",
            "packageID": "gorge-base", "packageVersion": "v3-approved",
            "boundsWgs84": self.bounds,
            "usgsTopo": item("base/topo.png"),
            "terrainRelief": item("base/hill.png"),
            "baseRasters": [{"id": i, **item(f"base/{i}.png")}
                            for i in builder.REQUIRED],
            "vectors": [dict(id="forest-service-trails", **item("vectors/fs.geojson"))],
            "staticAssets": [item("website/static.png")],
            "weatherManifest": {**item("website/weather.json"), "sourceCommit": "qa"},
            "sunPotentialManifest": {**item("website/sun.json"), "sourceCommit": "qa"},
            "websiteAssetsRoot": "website"
        }
        self._put(self.base, "NATIVE-MAP.json",
                  json.dumps(self.manifest).encode())
        for layer in builder.REQUIRED:
            for zoom in range(8, 16):
                nw = builder.xy(self.bounds["west"], self.bounds["north"], zoom)
                se = builder.xy(self.bounds["east"], self.bounds["south"], zoom)
                for xx in range(min(nw[0], se[0]), max(nw[0], se[0]) + 1):
                    for yy in range(min(nw[1], se[1]), max(nw[1], se[1]) + 1):
                        self._put(self.tiles, f"{layer}/{zoom}/{xx}/{yy}.png", sample)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _put(root, name, data):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_build_complete_new_archive_and_immutable_metadata(self):
        report = builder.build(self.base, self.tiles, self.out,
                               "v4-qa-20261027", 8, 15)
        self.assertEqual(report["schemaVersion"], 4)
        self.assertEqual(len(report["tileCountByLayer"]), 5)
        self.assertEqual(report["sha256"], builder.sha256(self.out))
        with tarfile.open(self.out) as t:
            self.assertTrue(all(member.isfile() for member in t))
            output = json.load(t.extractfile("NATIVE-MAP.json"))
            self.assertEqual(output["schemaVersion"], 4)
            self.assertEqual(output["packageVersion"], "v4-qa-20261027")
            self.assertEqual(len(output["tileSets"]), 5)
            for set_ in output["tileSets"]:
                self.assertEqual(set_["maxZoom"], 15)
                self.assertTrue(set_["tiles"])
        with self.assertRaises(FileExistsError):
            builder.build(self.base, self.tiles, self.out,
                          "v4-qa-20261027", 8, 15)

    def test_preserves_mixed_png_jpg_source_bytes_and_manifest(self):
        z = 15
        x, y = builder.xy(self.bounds["west"], self.bounds["north"], z)
        old = self.tiles / f"leaf-off-aerial/{z}/{x}/{y}.png"
        renamed = old.with_suffix(".jpg")
        old.rename(renamed)
        # Isolate format dispatch with a synthetic JPEG validator mock.
        # The production validator still checks real JPEG SOF dimensions.
        with patch.object(builder, "jpeg_256", return_value=True):
            builder.build(self.base, self.tiles, self.out, "v4-mixed", 8, 15)
        with tarfile.open(self.out) as tar:
            manifest = json.load(tar.extractfile("NATIVE-MAP.json"))
            leaf = next(s for s in manifest["tileSets"]
                        if s["id"] == "leaf-off-aerial")
            self.assertEqual(leaf["tileFormat"], "mixed")
            self.assertTrue(any(v["path"].endswith(".jpg")
                                for v in leaf["tiles"]))
            self.assertTrue(any(v["path"].endswith(".png")
                                for v in leaf["tiles"]))
            self.assertIsNotNone(tar.getmember(
                f"tiles/leaf-off-aerial/{z}/{x}/{y}.jpg"))
        self.assertFalse(old.exists())

    def test_missing_close_tile_blocks_built_package(self):
        zoom = 15
        x, y = builder.xy(self.bounds["west"], self.bounds["north"], zoom)
        (self.tiles / f"usgs-topo/{zoom}/{x}/{y}.png").unlink()
        with self.assertRaises(ValueError):
            builder.build(self.base, self.tiles, self.out,
                          "v4-qa-20261027", 8, 15)
        self.assertFalse(self.out.exists())

    def test_source_tamper_and_resolution_fail_closed(self):
        (self.base / "base/topo.png").write_bytes(b"wrong")
        with self.assertRaises(ValueError):
            builder.build(self.base, self.tiles, self.out,
                          "v4-qa-20261027", 8, 15)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
