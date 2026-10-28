#!/usr/bin/env python3
"""No-network original-size pack audit tests; synthetic images only."""
import struct
import tempfile
from pathlib import Path
import unittest
import zlib
from measure_gorge_offline_packs import measure, GROUPS


def png():
    def chunk(name, raw):
        return (struct.pack(">I", len(raw)) + name + raw +
                struct.pack(">I", zlib.crc32(name + raw) & 0xffffffff))
    scan = (b"\x00" + b"\x12\x34\x56" * 256) * 256
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(scan)) + chunk(b"IEND", b""))


class PackMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.bbox = [-83.6400, 37.8200, -83.6399, 37.8201]

    def tearDown(self):
        self.dir.cleanup()

    def put(self, layer, content=None):
        from build_gorge_base_native_v4 import xy
        x, y = xy(self.bbox[0], self.bbox[3], 10)
        dest = self.root / layer / "10" / str(x) / f"{y}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png() if content is None else content)
        return dest

    def test_no_assets_yields_unknown_final_sizes(self):
        report = measure(self.root, self.bbox, 10, 10)
        self.assertEqual(len(report["packs"]), 3)
        for pack in report["packs"]:
            self.assertIsNone(pack["finalDownloadBytes"])
            self.assertFalse(pack["sourceCoverageComplete"])
            self.assertEqual(pack["validTiles"], 0)

    def test_five_real_dimension_images_split_into_three_groups(self):
        for layers in GROUPS.values():
            for layer in layers:
                self.put(layer)
        report = measure(self.root, self.bbox, 10, 10)
        core, leaf_on, leaf_off = report["packs"]
        self.assertEqual(core["validTiles"], 3)
        self.assertEqual(leaf_on["validTiles"], 1)
        self.assertEqual(leaf_off["validTiles"], 1)
        self.assertTrue(all(p["sourceCoverageComplete"]
                            for p in report["packs"]))
        self.assertEqual(core["measuredSourceTileBytes"], 3 * len(png()))
        self.assertIsNone(core["finalInstalledBytes"])
        self.assertTrue(core["required"])
        self.assertFalse(leaf_on["required"])

    def test_broken_optional_aerial_does_not_corrupt_required_core(self):
        for layer in GROUPS["required-core"]:
            self.put(layer)
        self.put("leaf-on-aerial", b"fake map pixels")
        report = measure(self.root, self.bbox, 10, 10)
        self.assertTrue(report["packs"][0]["sourceCoverageComplete"])
        self.assertEqual(report["packs"][1]["missingOrInvalid"], 1)
        self.assertEqual(report["packs"][1]["validTiles"], 0)

    def test_reject_wide_or_reversed_invalid_bounds(self):
        for bounds in ([-84, 38, -85, 37], [0, 0, 1]):
            with self.assertRaises(ValueError):
                measure(self.root, bounds, 10, 10)


if __name__ == "__main__":
    unittest.main()
