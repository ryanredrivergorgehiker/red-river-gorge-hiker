#!/usr/bin/env python3
"""No-network bounded nine-original KyTopo source QA orchestration tests."""
import tempfile
from pathlib import Path
import unittest

from pilot_all_nine_kytopo_quads import run, EXPECTED, PER_QUAD_LIMIT


def official():
    quads = []
    for quad in sorted(EXPECTED):
        quads.append({
            "id": quad, "quadrangle": quad,
            "boundsWGS84": [-83.8, 37.65, -83.4, 37.95],
            "officialOriginalCogURL":
                "https://kyfromabove.s3.us-west-2.amazonaws.com/"
                "elevation/KyTopoMapSeries/COGs/KyTopo_24K_" + quad + "_Test_cog.tif",
            "sourceSelection": "exact-current-cog-in-official-s3",
            "inOfficialS3Listing": True,
            "officialOriginalSourceBytes": 77_000_000,
        })
    return {
        "count": 9, "allOriginalKeysInS3": True,
        "rasterBytesFetched": 0,
        "boundsWGS84": [-83.80, 37.65, -83.40, 37.95],
        "status": "OFFICIAL GORGE-INTERSECTING KYTOPO QUAD METADATA ONLY",
        "quadrangles": quads,
    }


def fake(index, folder, quad, cap):
    assert cap == PER_QUAD_LIMIT
    return {
        "original": {"sourceQuad": quad},
        "sourceBytesTransferred": 1024,
        "xyz": {"z": 16, "x": 17550, "y": 25325},
        "alphaMin": 255.0,
        "rasterQA": {"pixelAndGeographicAlignmentVerified": True},
        "derivedSha256": "b"*64,
        "derivedImageBytes": 23_000,
    }


class NineQuadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name) / "qa"
    def tearDown(self):
        self.temp.cleanup()

    def test_all_nine_retain_distinct_receipts_without_claiming_full_coverage(self):
        result = run(official(), self.out, fake)
        self.assertEqual(result["sourceQuadCount"], 9)
        self.assertEqual(result["actualPartialSourceBytes"], 9 * 1024)
        self.assertIsNone(result["finalCoreDownloadBytes"])
        self.assertFalse(result["completeGorgePixelCoverage"])
        self.assertTrue((self.out / "NINE-QUAD-PILOT-ONLY.json").exists())

    def test_reject_missing_quad_and_source_mismatch(self):
        report = official()
        report["quadrangles"].pop()
        with self.assertRaises(ValueError):
            run(report, self.out, fake)
        report = official()
        report["quadrangles"][0]["officialOriginalCogURL"] = "https://bad.example.com/x.tif"
        with self.assertRaises(ValueError):
            run(report, self.out, fake)

    def test_bad_alpha_or_unbounded_source_fails_without_success_manifest(self):
        def bad(index, folder, quad, cap):
            data = fake(index, folder, quad, cap)
            data["alphaMin"] = 0.0
            return data
        with self.assertRaises(ValueError):
            run(official(), self.out, bad)
        self.assertFalse((self.out / "NINE-QUAD-PILOT-ONLY.json").exists())

        def large(index, folder, quad, cap):
            data = fake(index, folder, quad, cap)
            data["sourceBytesTransferred"] = cap + 1
            return data
        with self.assertRaises(ValueError):
            run(official(), self.out, large)

    def test_refuse_overwriting_prior_evidence(self):
        self.out.mkdir()
        (self.out / "previous.json").write_text("previous QA")
        with self.assertRaises(FileExistsError):
            run(official(), self.out, fake)


if __name__ == "__main__":
    unittest.main()
