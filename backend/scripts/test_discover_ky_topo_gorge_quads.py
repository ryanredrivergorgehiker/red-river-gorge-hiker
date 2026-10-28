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
