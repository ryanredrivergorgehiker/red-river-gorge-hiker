#!/usr/bin/env python3
"""Synthetic-only original-file hash and shared-vs-legacy sizing tests."""
import json
from pathlib import Path
import tempfile
import unittest

from build_gorge_base_native_v4 import sha256
from measure_inherited_gorge_assets import measure


class SharedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def file(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"path": rel, "sha256": sha256(p)}

    def fixture(self):
        vectors = self.file("vectors/fs.json", b"authentic vector fixture")
        sun = self.file("sun/potential.json", b"sun content")
        weather = self.file("weather/forecast.json", b"forecast content")
        topo = self.file("legacy/topo.png", b"old raster")
        relief = self.file("legacy/terrain.png", b"old relief")
        m = {"schemaVersion": 3, "packageID": "gorge-base",
             "packageVersion": "v3-fixture",
             "vectors": [vectors, vectors], "staticAssets": [],
             "sunPotentialManifest": sun, "weatherManifest": weather,
             "usgsTopo": topo, "terrainRelief": relief, "baseRasters": []}
        (self.root / "NATIVE-MAP.json").write_text(json.dumps(m))
        return m

    def test_shared_sources_measured_once_without_legacy_double_count(self):
        self.fixture()
        r = measure(self.root)
        self.assertTrue(r["allFilesHashVerified"])
        self.assertEqual(r["groups"]["shared-core"]["actualFiles"], 3)
        self.assertEqual(r["groups"]["legacy-single-image-rasters"]["actualFiles"], 2)
        self.assertEqual(r["groups"]["shared-core"]["actualBytes"],
                         len(b"authentic vector fixture") +
                         len(b"sun content") + len(b"forecast content"))
        self.assertIsNone(r["finalCoreTransferBytes"])

    def test_source_hash_tampering_rejected(self):
        self.fixture()
        (self.root / "vectors/fs.json").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            measure(self.root)

    def test_no_legacy_promotion_or_cross_group_duplicates(self):
        m = self.fixture()
        m["baseRasters"] = [m["vectors"][0]]
        (self.root / "NATIVE-MAP.json").write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, "source collision"):
            measure(self.root)

    def test_invalid_v3_fails_closed(self):
        m = self.fixture()
        m["schemaVersion"] = 4
        (self.root / "NATIVE-MAP.json").write_text(json.dumps(m))
        with self.assertRaises(ValueError):
            measure(self.root)


if __name__ == "__main__":
    unittest.main()
