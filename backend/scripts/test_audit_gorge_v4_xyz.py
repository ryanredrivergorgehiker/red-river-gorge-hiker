#!/usr/bin/env python3
"""No-network regression tests for Gorge map coverage and storage preflight."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from audit_gorge_v4_xyz import audit, REQUIRED, xy


def png_256():
    def chunk(label, payload):
        return (struct.pack(">I", len(payload)) + label + payload +
                struct.pack(">I", zlib.crc32(label + payload) & 0xffffffff))
    rgb = (b"\\x00" + b"\\x12\\x34\\x56" * 256) * 256
    return (b"\\x89PNG\\r\\n\\x1a\\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rgb)) + chunk(b"IEND", b""))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bounds = [-83.64, 37.82, -83.639, 37.821]
        self.x, self.y = xy(self.bounds[0], self.bounds[3], 10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_files_means_not_build_ready_and_no_network(self):
        result = audit(self.root, self.bounds, 10, 10)
        self.assertEqual(result["status"], "NOT BUILD READY")
        self.assertEqual(result["totals"]["present"], 0)
        self.assertEqual(result["totals"]["expected"], len(REQUIRED))
        self.assertEqual(result["totals"]["missing"], len(REQUIRED))
        self.assertFalse(result["layers"][0]["sourceDeclarationPresent"])

    def test_complete_five_layer_tile_coverage_plus_declarations(self):
        for layer in REQUIRED:
            file = self.root / f"{layer}/10/{self.x}/{self.y}.png"
            file.parent.mkdir(parents=True)
            file.write_bytes(png_256())
            (self.root / f"{layer}.sources.json").write_text(json.dumps({
                "layerID": layer, "boundsWGS84": self.bounds,
                "zoomMin": 10, "zoomMax": 10,
                "imports": [{"source": {"verifiedOfflineReuse": True}}]
            }))
        result = audit(self.root, self.bounds, 10, 10)
        self.assertEqual(result["totals"]["present"], len(REQUIRED))
        self.assertEqual(result["totals"]["missing"], 0)
        self.assertEqual(result["totals"]["invalid"], 0)
        self.assertTrue(result["rasterOnlyBudgetPossible"])
        self.assertEqual(result["status"],
                         "INPUT COVERAGE COMPLETE; FULL BUILD STILL REQUIRED")
        file = self.root / f"{REQUIRED[0]}/10/{self.x}/{self.y}.png"
        file.write_bytes(b"not an original-resolution PNG")
        broken = audit(self.root, self.bounds, 10, 10)
        self.assertEqual(broken["status"], "NOT BUILD READY")
        self.assertEqual(broken["totals"]["invalid"], 1)

    def test_reject_invalid_bounds(self):
        with self.assertRaises(ValueError):
            audit(self.root, [-83.8, 38, -83.4, 37], 10, 10)


if __name__ == "__main__":
    unittest.main()
