#!/usr/bin/env python3
"""No-network proof that a shared original COG boundary needs a mosaic."""
import unittest

from plan_ky_cog_mosaic_xyz import plan, sampled_covered, xyz_bounds

AOI = [-83.8, 37.65, -83.4, 37.95]
HOST = "https://kyfromabove.s3.us-west-2.amazonaws.com/"


def fixture():
    return {
        "boundsWGS84": AOI, "noOriginalPixelDataDownloaded": True,
        "records": [{
            "kind": "leaf-off-ortho-candidate",
            "collection": "orthos-phase3",
            "paginationExhausted": True,
            "sourceFiles": [
                {"id":"west", "bbox":[-83.82,37.63,-83.6,37.97],
                 "officialCogURL":HOST+"imagery/orthos/west.tif"},
                {"id":"east", "bbox":[-83.6,37.63,-83.38,37.97],
                 "officialCogURL":HOST+"imagery/orthos/east.tif"},
            ],
        }]
    }


class MosaicPlanningTests(unittest.TestCase):
    def test_exact_xyz_selection_flags_cross_source_tiles(self):
        o=plan(fixture(),13,13)
        layer=o["results"][0]
        self.assertEqual(layer["officialSourceFileCount"],2)
        self.assertTrue(layer["levels"][0]["multiSourceTileCount"]>0)
        self.assertEqual(layer["approximateGapsSample"],[])
        self.assertTrue(any(t["cogs"]==["east","west"]
                            for t in layer["plannedTiles"]))
        self.assertTrue(o["mustMosaicEveryIntersectingCOG"])
        self.assertFalse(layer["actualSourceImagePixelsValidated"])

    def test_incomplete_inventory_or_unofficial_sources_rejected(self):
        v=fixture()
        v["records"][0]["paginationExhausted"]=False
        with self.assertRaises(ValueError):
            plan(v)
        v=fixture()
        v["records"][0]["sourceFiles"][0]["officialCogURL"]="https://evil.example/a.tif"
        with self.assertRaises(ValueError):
            plan(v)

    def test_bbox_samples_are_not_raster_pixel_proof(self):
        clip=[-83.7,37.7,-83.5,37.8]
        self.assertTrue(sampled_covered(clip,[
            [-83.7,37.7,-83.6,37.8],[-83.6,37.7,-83.5,37.8]
        ]))
        self.assertFalse(sampled_covered(clip,[
            [-83.7,37.7,-83.61,37.8],[-83.59,37.7,-83.5,37.8]
        ]))


if __name__ == "__main__":
    unittest.main()
