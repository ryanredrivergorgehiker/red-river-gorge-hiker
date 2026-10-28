#!/usr/bin/env python3
"""No-network limits and honest-state tests for rejected seam neighborhood QA."""
import tempfile
from pathlib import Path
import unittest

from test_plan_kytopo_quad_seams import index
from probe_kytopo_failed_seam_neighbors import examine, OFFSETS, MAX_TOTAL


class SeamForensicsTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.root=Path(self.dir.name)/"qa"
    def tearDown(self):
        self.dir.cleanup()

    def test_metadata_only_diagnostic_never_asserts_regional_coverage(self):
        def reject(original,candidate,folder):
            raise ValueError("original source alpha says no pixels")
        r=examine(index(),self.root,reject)
        self.assertIsNone(r["acceptedAlternateXYZ"])
        self.assertTrue(r["notFullRegionEvidence"])
        self.assertTrue(r["notOwnerAcceptedMap"])
        self.assertLessEqual(len(r["attempts"]),len(OFFSETS))
        self.assertLessEqual(len(OFFSETS)*5_000_000,MAX_TOTAL)
        self.assertTrue((self.root/"SEAM-NEIGHBORHOOD-FORENSICS.json").is_file())

    def test_disallow_tampered_index_and_overwriting_forensics(self):
        with self.assertRaises(ValueError):
            examine({"count":0,"quadrangles":[]},self.root,lambda *a:None)
        self.root.mkdir()
        (self.root/"prior.txt").write_text("old evidence")
        with self.assertRaises(FileExistsError):
            examine(index(),self.root,lambda *a:None)


if __name__=="__main__":
    unittest.main()
