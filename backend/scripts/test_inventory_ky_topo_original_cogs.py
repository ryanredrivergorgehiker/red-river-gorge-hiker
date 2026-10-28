#!/usr/bin/env python3
"""Offline original KyTopo S3 metadata bounds and pagination tests."""
import unittest
from inventory_ky_topo_original_cogs import inventory, PREFIX, MAX_PAGES


def xml(objects, truncated=False, token=None):
    payload = "".join(
        f"<Contents><Key>{name}</Key><Size>{size}</Size></Contents>"
        for name, size in objects
    )
    continuation = (f"<NextContinuationToken>{token}</NextContinuationToken>"
                    if token else "")
    return (f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Name>kyfromabove</Name><Prefix>{PREFIX}</Prefix>"
            f"<IsTruncated>{str(truncated).lower()}</IsTruncated>"
            f"{continuation}{payload}</ListBucketResult>").encode()


class TopoInventoryTests(unittest.TestCase):
    def test_complete_two_page_inventory_includes_tiffs_only(self):
        calls = []
        def fake(params):
            calls.append(params)
            if len(calls) == 1:
                return xml([(PREFIX + "KyTopo/Q1.tif", 400),
                            (PREFIX + "KyTopo/grid.gpkg", 200)],
                           truncated=True, token="next-one")
            return xml([(PREFIX + "KyTopo/Q2.tiff", 900)])
        r = inventory(fake)
        self.assertEqual(r["originalGeoTiffFileCount"], 2)
        self.assertEqual(r["originalGeoTiffFileBytes"], 1300)
        self.assertTrue(r["listingExhausted"])
        self.assertEqual(calls[1]["continuation-token"], "next-one")
        self.assertTrue(r["notAnOfflinePackageSize"])

    def test_truncated_missing_cursor_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "lacks cursor"):
            inventory(lambda _: xml([(PREFIX + "a.tif", 42)],
                                    truncated=True))

    def test_wrong_prefix_or_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            inventory(lambda _: xml([("other-bucket/a.tif", 13)]))
        with self.assertRaises(ValueError):
            inventory(lambda _: xml([(PREFIX + "same.tif", 10),
                                     (PREFIX + "same.tif", 10)]))

    def test_page_limit_never_claims_exhausted(self):
        count = 0
        def always_more(params):
            nonlocal count
            count += 1
            return xml([(PREFIX + f"Q{count}.tif", 1024)],
                       truncated=True, token=f"page-{count}")
        r = inventory(always_more)
        self.assertEqual(count, MAX_PAGES)
        self.assertFalse(r["listingExhausted"])


if __name__ == "__main__":
    unittest.main()
