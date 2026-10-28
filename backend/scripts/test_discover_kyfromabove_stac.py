#!/usr/bin/env python3
"""No-network tests for official Kentucky COG catalog source discovery."""
import unittest

from discover_kyfromabove_stac import (
    discover, collections, valid_bbox, intersects, public_asset, source_kind, MAX_ITEMS_PER_COLLECTION
)

BBOX = [-83.80, 37.65, -83.40, 37.95]


class CatalogTests(unittest.TestCase):
    def fake(self, path, params=None):
        if path == "/collections":
            return {"collections": [
                {"id": "pointcloud", "description": "LiDAR point cloud COPC"},
                {"id": "kfa-dem-p2", "description": "LiDAR derived digital elevation models DEM"},
                {"id": "kfa-ortho-p3", "title": "Ortho imagery tiles"},
            ]}
        if path == "/search":
            self.assertEqual(params["limit"], MAX_ITEMS_PER_COLLECTION)
            self.assertEqual(params["bbox"], ",".join(map(str, BBOX)))
            return {"type": "FeatureCollection", "features": [
                {"type": "Feature", "collection": params["collections"],
                 "id": "N081E279", "bbox": [-83.7, 37.7, -83.6, 37.8],
                 "assets": {"data": {"href":
                     "https://kyfromabove.s3.us-west-2.amazonaws.com/imagery/orthos/area.tif",
                     "type": "image/tiff; application=geotiff"}}},
                {"type": "Feature", "id": "outside",
                 "bbox": [-90, 39, -89, 40], "assets": {}},
            ]}
        raise AssertionError(path)

    def test_approved_bbox_and_bounded_collection_search(self):
        result = discover(BBOX, self.fake)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["kind"], "terrain-dem-candidate")
        self.assertEqual(len(result["results"][0]["candidates"]), 1)
        self.assertEqual(result["results"][1]["kind"], "leaf-off-ortho-candidate")
        self.assertTrue(result["noImageryDownloaded"])
        self.assertIn("leaf-on-aerial", result["layerRolesNotEstablished"])

    def test_prefer_complete_newer_sources_not_phase1_list_order(self):
        p = {"collections": [
            {"id": "dem-phase1", "title": "DEM LiDAR elevation"},
            {"id": "orthos-phase1", "title": "Ortho aerial imagery"},
            {"id": "dem-phase3", "title": "DEM LiDAR elevation"},
            {"id": "orthos-phase2", "title": "Ortho aerial imagery"},
            {"id": "dem-phase2", "title": "DEM LiDAR elevation"},
            {"id": "orthos-phase3", "title": "Ortho aerial imagery"},
        ]}
        self.assertEqual(collections(p), [
            ("terrain-dem-candidate", "dem-phase2"),
            ("leaf-off-ortho-candidate", "orthos-phase3"),
        ])

    def test_refuse_wide_or_invalid_aoi(self):
        for invalid in (
            [-85, 37.65, -83.4, 37.95],
            [-83.4, 37.6, -83.8, 38],
            [-83.8, 37.6, -83.4],
        ):
            self.assertFalse(valid_bbox(invalid))
            with self.assertRaises(ValueError):
                discover(invalid, self.fake)

    def test_reject_external_assets_and_unrelated_collections(self):
        self.assertFalse(public_asset("https://elsewhere.example.com/source.tif"))
        self.assertFalse(public_asset("http://kyfromabove.s3.us-west-2.amazonaws.com/a.tif"))
        self.assertTrue(public_asset("s3://kyfromabove/elevation/DEM/a.tif"))
        self.assertIsNone(source_kind({"id": "pointcloud", "title": "LiDAR point cloud"}))
        self.assertTrue(intersects([-83.75, 37.7, -83.6, 37.8], BBOX))

    def test_fail_on_unexpected_oversized_result(self):
        def many(path, params=None):
            if path == "/collections":
                return {"collections": [{"id": "dem", "title": "DEM"}]}
            return {"type": "FeatureCollection", "features": [
                {"type": "Feature", "id": str(i), "bbox": BBOX, "assets": {}}
                for i in range(MAX_ITEMS_PER_COLLECTION + 1)
            ]}
        with self.assertRaises(ValueError):
            discover(BBOX, many)


if __name__ == "__main__":
    unittest.main()
