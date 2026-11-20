#!/usr/bin/env python3
"""Network-free adjacency and genuine source-footprint seam planner tests."""
import unittest
from plan_kytopo_quad_seams import plan, adjacent, EXPECTED, BBOX


def index():
    quads = []
    for n in (13, 14, 15):
        for e in (29, 30, 31):
            # Synthetic, overlapping 3x3 grid INSIDE the approved Gorge AOI.
            col, row = e - 29, n - 13
            west = BBOX[0] + col*(BBOX[2]-BBOX[0])/3 - 0.002
            east = BBOX[0] + (col+1)*(BBOX[2]-BBOX[0])/3 + 0.002
            south = BBOX[1] + row*(BBOX[3]-BBOX[1])/3 - 0.002
            north = BBOX[1] + (row+1)*(BBOX[3]-BBOX[1])/3 + 0.002
            key = f"N{n}E{e}"
            quads.append({
                "id": key, "quadrangle": key, "boundsWGS84": [west,south,east,north],
                "officialOriginalCogURL":
                    "https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/"
                    "KyTopoMapSeries/COGs/KyTopo_24K_" + key + "_QA_cog.tif",
                "officialOriginalSourceBytes": 70_000_000,
                "sourceSelection": "exact-current-cog-in-official-s3",
                "inOfficialS3Listing": True,
            })
    return {
        "status": "OFFICIAL GORGE-INTERSECTING KYTOPO QUAD METADATA ONLY",
        "boundsWGS84": BBOX, "quadrangles": quads, "count": 9,
        "allOriginalKeysInS3": True, "rasterBytesFetched": 0,
    }


class SeamPlannerTests(unittest.TestCase):
    def test_twelve_pairs_select_real_xyz_footprints_not_pixels(self):
        result = plan(index())
        self.assertEqual(result["candidateCount"], 12)
        self.assertEqual(len({tuple(x["pair"]) for x in result["candidates"]}), 12)
        self.assertTrue(all(c["xyz"]["z"] == 16 and
                            c["sourceIds"] == c["pair"] and
                            not c["sourcePixelCoverageVerified"]
                            for c in result["candidates"]))
        self.assertFalse(result["regionalPixelClosure"])
        self.assertIsNone(result["finalDownloadBytes"])

    def test_only_directly_adjacent_original_source_ids(self):
        self.assertTrue(adjacent("N13E29","N13E30"))
        self.assertTrue(adjacent("N14E30","N15E30"))
        self.assertFalse(adjacent("N13E29","N15E29"))
        self.assertFalse(adjacent("N13E29","N14E30"))

    def test_missing_and_spoofed_originals_fail_closed(self):
        report = index()
        report["quadrangles"].pop()
        with self.assertRaises(ValueError):
            plan(report)
        report = index()
        report["quadrangles"][0]["officialOriginalCogURL"] = "https://evil.example/t.tif"
        with self.assertRaises(ValueError):
            plan(report)

    def test_pixel_verified_special_source_fails_if_footprints_move(self):
        # The real Daysboro/Simpson original-source pair has a proven sample
        # z16/17578/25339. Synthetic quad geometry does not match that
        # pixel-proven position, so no unverified fallback is allowed.
        report = index()
        for q in report["quadrangles"]:
            if q["id"] in ("N14E31", "N15E31"):
                name = "Daysboro" if q["id"] == "N14E31" else "Simpson"
                q["officialOriginalCogURL"] = (
                    "https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/"
                    "KyTopoMapSeries/COGs/KyTopo_24K_" +
                    q["id"] + "_" + name + "_cog.tif"
                )
        with self.assertRaisesRegex(ValueError, "Prior pixel-verified"):
            plan(report)

    def test_duplicate_original_ids_fail_closed(self):
        report = index()
        report["quadrangles"][0] = report["quadrangles"][1]
        with self.assertRaises(ValueError):
            plan(report)


if __name__ == "__main__":
    unittest.main()
