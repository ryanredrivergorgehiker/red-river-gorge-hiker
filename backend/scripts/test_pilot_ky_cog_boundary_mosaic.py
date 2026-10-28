#!/usr/bin/env python3
"""No-network provenance and source-boundary guard for the real two-COG pilot."""
import unittest

from pilot_ky_cog_boundary_mosaic import (
    approved_sources, EXPECTED, X, Y, ZOOM, MAX_TRANSFER,
    COG_HOST,
)


def plan():
    source = {
        "kind": "leaf-off-ortho-candidate",
        "collection": "kyfromabove-orthos-phase3",
        "plannedTiles": [
            {"z": ZOOM, "x": X, "y": Y, "cogs": sorted(EXPECTED)}
        ],
        "sourceCatalog": {
            name: {
                "bbox": [-83.8, 37.65, -83.4, 37.95],
                "url": (
                    f"https://{COG_HOST}/imagery/orthos/Phase3/"
                    f"{name.split('_')[1]}/" + name
                ),
            }
            for name in EXPECTED
        },
    }
    return {
        "status": "SOURCE-FOOTPRINT MOSAIC PLAN ONLY — NOT MAP TILES OR SIGNED BASE",
        "noImageryDownloaded": True,
        "mustMosaicEveryIntersectingCOG": True,
        "results": [source],
    }


class BoundarySourceTests(unittest.TestCase):
    def test_exact_two_original_sources_are_required(self):
        sources = approved_sources(plan())
        self.assertEqual(len(sources), 2)
        self.assertEqual({item["name"] for item in sources}, EXPECTED)
        self.assertTrue(all("/imagery/orthos/Phase3/" in x["url"]
                            for x in sources))
        self.assertLess(MAX_TRANSFER, 1_000_000_000)

    def test_missing_second_source_fails_not_synthetic_gap(self):
        p = plan()
        p["results"][0]["plannedTiles"][0]["cogs"] = [sorted(EXPECTED)[0]]
        with self.assertRaises(ValueError):
            approved_sources(p)

    def test_refuse_tampered_or_external_source(self):
        p = plan()
        key = next(iter(EXPECTED))
        p["results"][0]["sourceCatalog"][key]["url"] = (
            "https://evil.example/imagery/orthos/Phase3/source.tif"
        )
        with self.assertRaises(ValueError):
            approved_sources(p)
        p = plan()
        p["mustMosaicEveryIntersectingCOG"] = False
        with self.assertRaises(ValueError):
            approved_sources(p)


if __name__ == "__main__":
    unittest.main()
