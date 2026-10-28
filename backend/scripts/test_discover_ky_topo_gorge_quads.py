#!/usr/bin/env python3
"""No-network spatial KyTopo grid and S3 evidence integrity tests."""
import unittest

from discover_ky_topo_gorge_quads import discover, source_key, PREFIX, COG_HOST, BBOX


def feature(name, url):
    return {"attributes": {"Name": name, "QuadName": "Gorge fixture",
                           "AWS_COG_url": url},
            "geometry": {"rings": [[[-83.8, 37.65], [-83.6, 37.65],
                                    [-83.6, 37.95], [-83.8, 37.95],
                                    [-83.8, 37.65]]]}}


def url(name):
    return f"https://{COG_HOST}{PREFIX}{name}.tif"


class KyTopoRegionTests(unittest.TestCase):
    def test_gorge_quad_with_original_source_linked_to_full_s3_listing(self):
        f = feature("Q24", url("Q24"))
        listed = {"prefix": PREFIX.lstrip("/"), "listingExhausted": True,
                  "originalCOGs": [{"key": PREFIX.lstrip("/") + "Q24.tif"}]}
        report = discover(BBOX, listed, lambda bounds: {"features": [f]})
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["withOriginalCOGURL"], 1)
        self.assertTrue(report["allOriginalKeysInS3"])
        self.assertEqual(report["rasterBytesFetched"], 0)
        self.assertTrue(report["noFinalCoverageOrXYZSizeClaim"])

    def test_grid_quad_joins_exact_current_source_not_phase1_duplicate(self):
        current = PREFIX.lstrip("/") + "COGs/KyTopo_24K_N14E30_Pine Ridge_cog.tif"
        legacy = PREFIX.lstrip("/") + "COGs_phase1/KyTopo_24K_N14E30_Pine Ridge_cog.tif"
        listed = {"prefix": PREFIX.lstrip("/"), "listingExhausted": True,
                  "originalCOGs": [{"key": current, "sourceFileBytes": 77463884},
                                   {"key": legacy, "sourceFileBytes": 123747745}]}
        f = feature("N14E30", None)
        r = discover(BBOX, listed, lambda _: {"features": [f]})
        q = r["quadrangles"][0]
        self.assertEqual(r["withOriginalCOGURL"], 1)
        self.assertEqual(r["allOriginalKeysInS3"], True)
        self.assertEqual(q["officialOriginalSourceBytes"], 77463884)
        self.assertIn("Pine%20Ridge_cog.tif", q["officialOriginalCogURL"])
        self.assertEqual(q["sourceSelection"], "exact-current-cog-in-official-s3")

    def test_ambiguous_current_source_never_selected(self):
        start = PREFIX.lstrip("/") + "COGs/KyTopo_24K_N14E30_"
        listed = {"prefix": PREFIX.lstrip("/"), "listingExhausted": True,
                  "originalCOGs": [{"key": start + "A_cog.tif", "sourceFileBytes": 100},
                                   {"key": start + "B_cog.tif", "sourceFileBytes": 100}]}
        r = discover(BBOX, listed, lambda _: {
            "features": [feature("N14E30", None)]})
        self.assertEqual(r["withOriginalCOGURL"], 0)
        self.assertFalse(r["allOriginalKeysInS3"])
        self.assertEqual(r["quadrangles"][0]["sourceSelection"],
                         "ambiguous-current-cogs")

    def test_no_false_complete_inventory_for_missing_asset(self):
        listed = {"prefix": PREFIX.lstrip("/"), "listingExhausted": True,
                  "originalCOGs": []}
        r = discover(BBOX, listed, lambda bounds:
                     {"features": [feature("Q25", url("Q25"))]})
        self.assertFalse(r["allOriginalKeysInS3"])

    def test_spoofed_source_and_invalid_bounds_rejected(self):
        self.assertIsNone(source_key("https://evil.example.com/a.tif"))
        self.assertIsNone(source_key(f"http://{COG_HOST}{PREFIX}Q24.tif"))
        self.assertIsNone(source_key(f"https://{COG_HOST}/other/a.tif"))
        with self.assertRaises(ValueError):
            discover([-90, 30, -80, 40], None, lambda bounds: {"features": []})

    def test_incomplete_arcgis_or_non_wgs84_geometry_fails_closed(self):
        with self.assertRaises(ValueError):
            discover(BBOX, None, lambda bounds: {"features": [],
                                                 "exceededTransferLimit": True})
        f = feature("Q26", url("Q26"))
        f["geometry"]["rings"][0][0][0] = 1_000_000
        with self.assertRaises(ValueError):
            discover(BBOX, None, lambda bounds: {"features": [f]})

    def test_duplicate_quad_is_rejected(self):
        f = feature("Q24", url("Q24"))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            discover(BBOX, None, lambda bounds: {"features": [f, f]})


if __name__ == "__main__":
    unittest.main()
