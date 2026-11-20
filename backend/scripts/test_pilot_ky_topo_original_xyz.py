#!/usr/bin/env python3
"""No-network original KyTopo source and regional-pilot guards."""
import unittest

from pilot_ky_topo_original_xyz import source, QUAD, MAX_SOURCE_BYTES, COG_HOST


def fixture():
    return {
        "status": "OFFICIAL GORGE-INTERSECTING KYTOPO QUAD METADATA ONLY",
        "allOriginalKeysInS3": True,
        "rasterBytesFetched": 0,
        "quadrangles": [{
            "id": QUAD, "quadrangle": "Pine Ridge",
            "officialOriginalCogURL": (
                f"https://{COG_HOST}/elevation/KyTopoMapSeries/COGs/"
                "KyTopo_24K_N14E30_Pine%20Ridge_cog.tif"
            ),
            "boundsWGS84": [-83.68, 37.73, -83.46, 37.86],
            "sourceSelection": "exact-current-cog-in-official-s3",
            "officialOriginalSourceBytes": 77463884,
            "inOfficialS3Listing": True,
        }]
    }


class GenuineTopoPilotTests(unittest.TestCase):
    def test_real_metadata_must_be_verified_before_32mb_qa(self):
        original = source(fixture())
        self.assertEqual(original["quadName"], "Pine Ridge")
        self.assertEqual(original["length"], 77463884)
        self.assertLess(MAX_SOURCE_BYTES, original["length"])

    def test_no_legacy_phase1_or_source_host_spoofing(self):
        a = fixture()
        a["quadrangles"][0]["officialOriginalCogURL"] = (
            f"https://{COG_HOST}/elevation/KyTopoMapSeries/COGs_phase1/a.tif"
        )
        with self.assertRaises(ValueError):
            source(a)
        a = fixture()
        a["quadrangles"][0]["officialOriginalCogURL"] = "https://bad.example.org/a.tif"
        with self.assertRaises(ValueError):
            source(a)

    def test_incomplete_inventory_and_missing_gorge_quad_fail(self):
        a = fixture()
        a["allOriginalKeysInS3"] = False
        with self.assertRaises(ValueError):
            source(a)
        a = fixture()
        a["quadrangles"][0]["id"] = "N00E00"
        with self.assertRaises(ValueError):
            source(a)

    def test_location_must_truly_intersect_original_quad(self):
        a = fixture()
        a["quadrangles"][0]["boundsWGS84"] = [-90, 38, -85, 39]
        with self.assertRaises(ValueError):
            source(a)


if __name__ == "__main__":
    unittest.main()
