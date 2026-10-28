"""Offline REST metadata discovery tests. Does not hit a live GIS server."""
import importlib.util
from pathlib import Path
import unittest

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "official_ky_source", here / "discover_official_ky_county_sources.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DiscoveryTests(unittest.TestCase):
    def test_intersecting_counties_are_recorded_without_approval(self):
        payload = {"features": [
            {"attributes": {
                "County": "Wolfe",
                "TCM_TKPX_Name": "Wolfe_TCMTopo.tpkx",
                "TCM_Download_URL": "https://example.org/wolfe-tpkx",
                "KyFromAboveImagery_TPKX_Name": "Wolfe_Imagery.tpkx",
                "KyFromAbove_Download_URL": "https://example.org/wolfe-imagery",
            }},
            {"attributes": {
                "County": "Powell",
                "TCM_TKPX_Name": "Powell_TCMTopo.tpkx",
                "TCM_Download_URL": "https://example.org/powell-tpkx",
                "KyFromAboveImagery_TPKX_Name": "Powell_Imagery.tpkx",
                "KyFromAbove_Download_URL": "https://example.org/powell-imagery",
            }},
        ]}
        result = mod.discover([-83.8, 37.65, -83.4, 37.95], payload)
        self.assertEqual([r["county"] for r in result["records"]],
                         ["Powell", "Wolfe"])
        self.assertEqual(result["reviewStatus"], "NOT APPROVED OR DOWNLOADED")
        self.assertIn("kygisserver.ky.gov", result["officialMetadataURL"])
        self.assertIn("geometryType=esriGeometryEnvelope",
                      result["officialMetadataURL"])

    def test_empty_or_error_or_invalid_bounds_rejected(self):
        for payload in ({}, {"features": []}, {"error": {"message": "No"}}):
            with self.assertRaises(ValueError):
                mod.discover([-83.8, 37.65, -83.4, 37.95], payload)
        with self.assertRaises(ValueError):
            mod.discover([-83.4, 37.65, -83.8, 37.95],
                         {"features": [{"attributes": {"County": "Wolfe"}}]})


if __name__ == "__main__":
    unittest.main()
