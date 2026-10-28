#!/usr/bin/env python3
"""Network-free finite Kentucky STAC pagination and gap-diagnostic tests."""
import unittest

from inventory_kyfromabove_stac_coverage import (
    inventory, next_page, grid_score, official_search_url
)
from discover_kyfromabove_stac import API

BBOX = [-83.80, 37.65, -83.40, 37.95]


def item(id, bbox=BBOX):
    return {"type": "Feature", "id": id, "bbox": bbox, "assets": {
        "data": {"href":
            "https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/Phase2/real.tif"
        }}}


class MetadataInventoryTests(unittest.TestCase):
    def test_two_page_coverage_with_explicit_exhaustion(self):
        initial = {"catalog": API, "boundsWGS84": BBOX, "results": [
            {"kind": "terrain-dem-candidate", "collection": "dem-phase2"}
        ]}
        calls = []
        def fake(uri):
            calls.append(uri)
            if "page=two" in uri:
                return {"type": "FeatureCollection", "features": [
                    item("second", [-83.6, 37.65, -83.4, 37.95])
                ]}
            return {"type": "FeatureCollection", "features": [
                item("first", [-83.8, 37.65, -83.6, 37.95])
            ], "links": [{
                "rel": "next", "method": "GET",
                "href": API + "/search?page=two"
            }]}
        r = inventory(initial, fake)["records"][0]
        self.assertEqual(len(calls), 2)
        self.assertEqual(r["count"], 2)
        self.assertTrue(r["paginationExhausted"])
        self.assertGreaterEqual(r["approximateSpatialSample"]["fraction"], 0.99)
        self.assertFalse(r["approximateSpatialSample"]["exactClosedXYZProof"])

    def test_explicit_empty_page_is_not_imagery_coverage(self):
        initial = {"catalog": API, "boundsWGS84": BBOX, "results": [
            {"kind": "leaf-off-ortho-candidate", "collection": "orthos-phase3"}
        ]}
        r = inventory(initial, lambda uri: {
            "type": "FeatureCollection", "features": []
        })["records"][0]
        self.assertEqual(r["count"], 0)
        self.assertTrue(r["paginationExhausted"])
        self.assertEqual(r["approximateSpatialSample"]["fraction"], 0.0)

    def test_reject_external_and_post_continuation(self):
        self.assertFalse(official_search_url("https://evil.example.com/search?a=1"))
        self.assertFalse(official_search_url(API + "/packages?a=1"))
        with self.assertRaises(ValueError):
            next_page({"links": [{"rel": "next", "method": "POST",
                                  "href": API + "/search?token=x"}]})

    def test_grid_sampling_is_only_approximate(self):
        s = grid_score(BBOX, [BBOX], cols=4, rows=4)
        self.assertEqual(s["fraction"], 1.0)
        self.assertFalse(s["exactClosedXYZProof"])


if __name__ == "__main__":
    unittest.main()
