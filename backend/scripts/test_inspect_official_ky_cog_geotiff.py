#!/usr/bin/env python3
"""No-network fixtures proving bounded original GeoTIFF geotag parsing."""
import io
import struct
import unittest

from inspect_official_ky_cog_geotiff import describe, extract_tags
from http_range_zip import RangeZipReader


class Source(io.BytesIO):
    def __init__(self, contents):
        super().__init__(contents)
        self.length = len(contents)
        self.read_bytes = 0

    def read(self, n=-1):
        data = super().read(n)
        self.read_bytes += len(data)
        return data


def classic():
    n = 8
    first = 8 + 2 + n * 12 + 4
    scale = first
    tie = scale + 24
    geokeys = tie + 48
    data = bytearray(geokeys + 16)
    data[0:8] = b"II*\x00" + struct.pack("<I", 8)
    struct.pack_into("<H", data, 8, n)
    rows = [
        (256, 4, 1, 2048), (257, 4, 1, 2048),
        (259, 3, 1, 7), (322, 4, 1, 512), (323, 4, 1, 512),
        (33550, 12, 3, scale), (33922, 12, 6, tie),
        (34735, 3, 8, geokeys),
    ]
    for i, (tag, typ, count, val) in enumerate(rows):
        p = 10 + 12 * i
        data[p:p+12] = struct.pack("<HHII", tag, typ, count, val)
    struct.pack_into("<3d", data, scale, 2., 2., 0.)
    struct.pack_into("<6d", data, tie, 0., 0., 0., 123., 456., 0.)
    struct.pack_into("<8H", data, geokeys, 1, 1, 0, 1, 3072, 0, 1, 3089)
    return Source(bytes(data))


def bigtiff():
    data = bytearray(16 + 8 + 2*20 + 8)
    data[:16] = b"II+\x00" + struct.pack("<HHQ", 8, 0, 16)
    struct.pack_into("<Q", data, 16, 2)
    data[24:44] = struct.pack("<HHQQ", 256, 16, 1, 2048)
    data[44:64] = struct.pack("<HHQQ", 257, 16, 1, 2048)
    return Source(bytes(data))


class GeoTiffMetadataTests(unittest.TestCase):
    def test_original_classic_geo_crs_resolution_and_tiling(self):
        src = classic()
        result = describe(src)
        self.assertTrue(result["internalTiled"])
        self.assertTrue(result["georeferenceTagEvidence"])
        self.assertEqual(result["projectedOrGeographicEPSG"], 3089)
        self.assertEqual(result["pixelScaleNativeCRSUnits"], [2.0, 2.0])
        self.assertEqual(result["sourceWidthPixels"], 2048)
        self.assertFalse(result["sourceImageryPixelsRetrieved"])
        self.assertLess(src.read_bytes, 800)

    def test_64bit_big_tiff_directory_no_fake_geo_claim(self):
        result = describe(bigtiff())
        self.assertTrue(result["isBigTiff"])
        self.assertEqual(result["sourceWidthPixels"], 2048)
        self.assertFalse(result["georeferenceTagEvidence"])

    def test_invalid_ifd_or_geokeys_fail_closed(self):
        bad = bytearray(classic().getvalue())
        struct.pack_into("<H", bad, 8, 500)
        with self.assertRaises(ValueError):
            describe(Source(bad))
        invalid = bytearray(classic().getvalue())
        # GeoKey count declares two records but supplies only one.
        struct.pack_into("<H", invalid, len(invalid)-16 + 6, 2)
        with self.assertRaises(ValueError):
            describe(Source(invalid))

    def test_strict_cog_host_while_original_box_remains_supported(self):
        with self.assertRaises(ValueError):
            RangeZipReader("https://evil.example/a.tif", source_kind="kentucky_cog")
        with self.assertRaises(ValueError):
            RangeZipReader("https://ky.box.com/shared/static/a.tpkx",
                           source_kind="kentucky_cog")
        with self.assertRaises(ValueError):
            RangeZipReader("https://kyfromabove.s3.us-west-2.amazonaws.com/elevation/DEM/a.tif",
                           source_kind="unrecognized")


if __name__ == "__main__":
    unittest.main()
