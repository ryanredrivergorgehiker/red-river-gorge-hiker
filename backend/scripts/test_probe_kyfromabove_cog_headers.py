#!/usr/bin/env python3
"""No-network strict range and source identity checks for Kentucky COG intake."""
import io
import unittest

from probe_kyfromabove_cog_headers import (
    check_url, official_candidates, probe_one, probe_report, STAC_API,
    COG_HOST, READ_BYTES
)


def fixture():
    return {"catalog": STAC_API, "noImageryDownloaded": True, "results": [
        {"kind": "terrain-dem-candidate", "collection": "dem-phase2",
         "candidates": [{"itemID": "dem", "assets": [{
             "href": f"https://{COG_HOST}/elevation/DEM/Phase2/real.tif"}]}]},
        {"kind": "leaf-off-ortho-candidate", "collection": "orthos-phase3",
         "candidates": [{"itemID": "ortho", "assets": [{
             "href": f"https://{COG_HOST}/imagery/orthos/Phase3/real.tif"}]}]},
    ]}


class FakeResponse(io.BytesIO):
    def __init__(self, *, status=206, content_range=None, data=None,
                 url=None):
        super().__init__(data if data is not None
                         else b"II*\x00" + b"\x00" * (READ_BYTES - 4))
        self.status = status
        self.headers = {"Content-Range":
            content_range or f"bytes 0-{READ_BYTES-1}/100000"}
        self._url = url or f"https://{COG_HOST}/elevation/DEM/Phase2/real.tif"

    def geturl(self):
        return self._url


class StrictHeaderTests(unittest.TestCase):
    def test_exact_source_budget_no_images(self):
        items = official_candidates(fixture())
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["kind"], "terrain-dem-candidate")
        self.assertEqual(items[1]["kind"], "leaf-off-ortho-candidate")
        self.assertFalse(check_url("https://example.com/x.tif"))
        self.assertFalse(check_url(f"http://{COG_HOST}/x.tif"))

    def test_real_range_shape_proves_only_tiff_header(self):
        u = f"https://{COG_HOST}/elevation/DEM/Phase2/real.tif"
        def fake(req, timeout):
            self.assertEqual(req.headers["Range"], f"bytes=0-{READ_BYTES-1}")
            return FakeResponse()
        result = probe_one(u, fake)
        self.assertEqual(result["rangedBytesRead"], 4096)
        self.assertTrue(result["tiffHeaderConfirmed"])
        self.assertFalse(result["cogLayoutGeorefResolutionVerified"])

    def test_reject_provider_ignoring_range_or_wrong_geo_header(self):
        u = f"https://{COG_HOST}/elevation/DEM/Phase2/real.tif"
        for res in (
            FakeResponse(status=200),
            FakeResponse(content_range=f"bytes 1-{READ_BYTES}/100000"),
            FakeResponse(data=b"not TIFF" + b"x" * (READ_BYTES-8)),
            FakeResponse(url="https://evil.example.org/asset.tif"),
        ):
            with self.subTest(status=res.status, url=res.geturl()):
                with self.assertRaises(ValueError):
                    probe_one(u, lambda req, timeout: res)

    def test_fail_on_unofficial_manifest_or_noncompliant_candidates(self):
        d = fixture()
        d["catalog"] = "https://spoof.example.org"
        with self.assertRaises(ValueError):
            official_candidates(d)
        d = fixture()
        d["results"][0]["candidates"][0]["assets"][0]["href"] = "https://evil.example/a.tif"
        found = official_candidates(d)
        self.assertEqual(len(found), 1)

    def test_output_is_not_claim_of_complete_coverage(self):
        q = probe_report(fixture(), lambda url: {
            "rangedBytesRead": READ_BYTES, "tiffHeaderConfirmed": True,
            "cogLayoutGeorefResolutionVerified": False,
        })
        self.assertEqual(q["totalReadBytes"], READ_BYTES * 2)
        self.assertIn("NOT FULL", q["status"])


if __name__ == "__main__":
    unittest.main()
