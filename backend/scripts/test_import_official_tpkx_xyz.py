#!/usr/bin/env python3
"""Network-free CompactV2 tile source importer tests. No real protected data."""
import importlib.util
import io
from unittest.mock import patch
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ky_offline_import", HERE / "import_official_tpkx_xyz.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def png(rgb=100):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)
    raw = (b"\x00" + bytes([rgb, 99, 123]) * 256) * 256
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def bundle(x, y, tile):
    header = bytearray(mod.HEADER_SIZE + mod.INDEX_SIZE)
    struct.pack_into("<II", header, 0, 3, 16384)
    struct.pack_into("<I", header, 60, mod.INDEX_SIZE)
    start = len(header) + 4
    offset = mod.HEADER_SIZE + ((y % 128) * 128 + (x % 128)) * 8
    struct.pack_into("<Q", header, offset, (len(tile) << 40) | start)
    return bytes(header) + struct.pack("<I", len(tile)) + tile


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bounds = [-83.64, 37.82, -83.639, 37.821]
        self.x, self.y = mod.xyz(self.bounds[0], self.bounds[3], 10)
        self.origin_y = (self.y // 128) * 128
        self.origin_x = (self.x // 128) * 128
        self.provenance = dict(
            publisher="Kentucky geographic data program",
            sourceTitle="Synthetic official-shape QA package",
            sourceURL="https://example.org/for-qa-only",
            licenseURL="https://example.org/licensing-test",
            attribution="Synthetic source",
            verifiedOfflineReuse=True,
        )
        self.out = self.root / "local-tiles"

    def tearDown(self):
        self.tmp.cleanup()

    def make_source(self, filename, tile=None, projection=102100,
                    shifted_resolution=False):
        out = self.root / filename
        metadata = dict(tileInfo=dict(
            rows=256, cols=256, spatialReference=dict(wkid=projection),
            origin=dict(x=-20037508.342789244, y=20037508.342789244),
            lods=[dict(level=zoom,
                       resolution=(156543.03392804097 / (2 ** zoom)) *
                       (1.25 if shifted_resolution else 1))
                  for zoom in range(8, 19)],
        ))
        t = png() if tile is None else tile
        name = f"tile/L10/R{self.origin_y:04x}C{self.origin_x:04x}.bundle"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as pkg:
            pkg.writestr("root.json", json.dumps(metadata))
            pkg.writestr(name, bundle(self.x, self.y, t))
            # Independent county sources can share the exact same tiles.
            pkg.writestr("county-source.txt", filename)
        return out

    def test_single_import_and_stable_duplicate_replay_block(self):
        source = self.make_source("powell.tpkx")
        report = mod.import_tpkx(source, self.out, "kentucky-topo", self.bounds, 10, 10, self.provenance)
        self.assertEqual(len(report["imports"]), 1)
        self.assertTrue((self.out / f"kentucky-topo/10/{self.x}/{self.y}.png").is_file())
        with self.assertRaises(ValueError):
            mod.import_tpkx(source, self.out, "kentucky-topo", self.bounds, 10, 10, self.provenance)

    def test_second_county_preserves_provenance_and_refuses_conflict(self):
        one = self.make_source("powell.tpkx")
        two = self.make_source("wolfe.tpkx")
        mod.import_tpkx(one, self.out, "leaf-on-aerial", self.bounds, 10, 10, self.provenance)
        report = mod.import_tpkx(two, self.out, "leaf-on-aerial", self.bounds, 10, 10, self.provenance)
        self.assertEqual(len(report["imports"]), 2)
        three = self.make_source("menifee.tpkx", tile=png(150))
        with self.assertRaises(ValueError):
            mod.import_tpkx(three, self.out, "leaf-on-aerial", self.bounds, 10, 10, self.provenance)

    def test_bounded_range_zip_source_preserves_honest_provenance(self):
        local = self.make_source("official.tpkx")
        data = local.read_bytes()

        class FakeRanges(io.BytesIO):
            def __init__(self, url):
                super().__init__(data)
                self.url = url
                self.length = len(data)
                self.etag = '"synthetic"'
                self.provenance = {
                    "sourceURL": url,
                    "contentLength": len(data),
                    "etag": self.etag,
                    "rangeBytesTransferred": len(data) // 4,
                    "hasFullArchiveSHA256": False,
                }

        url = "https://ky.box.com/shared/static/official.tpkx"
        with patch.object(mod, "RangeZipReader", FakeRanges):
            result = mod.import_tpkx(
                url, self.out, "leaf-off-aerial",
                self.bounds, 10, 10, self.provenance
            )
        record = result["imports"][0]
        self.assertEqual(record["sourceIdentityMethod"],
                         "URL+length+ETag")
        self.assertIsNone(record["sourceArchiveSHA256"])
        self.assertFalse(
            record["sourceRangeProvenance"]["hasFullArchiveSHA256"]
        )
        self.assertTrue(
            (self.out / f"leaf-off-aerial/10/{self.x}/{self.y}.png").exists()
        )

    def test_refuse_wrong_projection_and_unapproved_usage(self):
        invalid = self.make_source("unprojected.tpkx", projection=4326)
        with self.assertRaises(ValueError):
            mod.import_tpkx(invalid, self.out, "usgs-topo", self.bounds, 10, 10, self.provenance)
        shifted = self.make_source("shifted.tpkx",
                                   shifted_resolution=True)
        with self.assertRaises(ValueError):
            mod.import_tpkx(shifted, self.out, "usgs-topo",
                            self.bounds, 10, 10, self.provenance)
        valid = self.make_source("usgs.tpkx")
        rejected = dict(self.provenance, verifiedOfflineReuse=False)
        with self.assertRaises(ValueError):
            mod.import_tpkx(valid, self.out, "usgs-topo", self.bounds, 10, 10, rejected)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
