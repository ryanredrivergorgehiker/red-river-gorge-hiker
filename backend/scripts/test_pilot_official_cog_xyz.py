#!/usr/bin/env python3
"""Network-free exact-source and transfer-budget safeguards for XYZ pilot."""
import unittest

from pilot_official_cog_xyz import (
    select, xyz, mercator_bounds, RangeBudget, MAX_REQUEST,
    MAX_TRANSFER, COG_HOST
)


def source_chain():
    url = (f"https://{COG_HOST}/imagery/orthos/Phase3/"
           "KY_KYAPED_2024_Season1_3IN/N119E344.tif")
    return (
        {"noImageryDownloaded": True,
         "results": [{"kind": "leaf-off-ortho-candidate",
                      "candidates": [{"itemID": "N119E344",
                        "bbox": [-83.768, 37.646, -83.750, 37.660],
                        "assets": [{"href": url}]}]}]},
        {"assets": [{"url": url, "tiffHeaderConfirmed": True,
                     "fileByteLength": 1_088_182_696, "etag": "abc"}]},
        {"status": "BOUNDED ORIGINAL GEOTIFF IFD PROBE",
         "assets": [{"url": url, "metadata": {
             "georeferenceTagEvidence": True, "internalTiled": True,
             "projectedOrGeographicEPSG": 3089,
             "sourceWidthPixels": 20000, "sourceHeightPixels": 20000,
             "pixelScaleNativeCRSUnits": [0.25, 0.25]}}]},
    )


class SourceGuardTests(unittest.TestCase):
    def test_only_approved_verified_phase3_original_source(self):
        stac, h, geo = source_chain()
        found = select(stac, h, geo)
        self.assertEqual(found["nativePixelScale"], [0.25, 0.25])
        self.assertEqual(found["length"], 1088182696)
        geo["assets"][0]["metadata"]["georeferenceTagEvidence"] = False
        with self.assertRaises(ValueError):
            select(stac, h, geo)

    def test_no_unbounded_ranges_or_budget_overflow(self):
        b = RangeBudget(10_000)
        self.assertFalse(b.reserve(MAX_REQUEST + 1))
        self.assertFalse(b.reserve(0))
        self.assertTrue(b.reserve(4096))
        self.assertFalse(b.reserve(7000))
        self.assertEqual(b.used, 4096)
        self.assertLess(MAX_TRANSFER, 1_088_182_696)

    def test_xyz_mercator_bounds_are_one_exact_tile(self):
        x, y = xyz(-83.759, 37.653, 16)
        bounds = mercator_bounds(x, y, 16)
        self.assertLess(bounds[0], bounds[2])
        self.assertLess(bounds[1], bounds[3])
        self.assertGreater(bounds[2] - bounds[0], 600)
        with self.assertRaises(ValueError):
            xyz(-100, 38, 16)
        with self.assertRaises(ValueError):
            xyz(-83.75, 37.65, 20)

    def test_bad_asset_host_is_not_probed(self):
        stac, h, geo = source_chain()
        stac["results"][0]["candidates"][0]["assets"][0]["href"] = (
            "https://bad.example.com/not-a-source.tif"
        )
        with self.assertRaises(ValueError):
            select(stac, h, geo)


if __name__ == "__main__":
    unittest.main()
