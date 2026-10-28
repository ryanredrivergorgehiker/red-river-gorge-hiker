"""Prove selective reader extracts 1 tile, not megabytes of unused bundle."""
import importlib.util
import io
from pathlib import Path
import struct
import unittest
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "compact_v2_range_extract", HERE / "compact_v2_range_extract.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_png():
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    raw = (b"\x00" + b"\x22\x33\x44" * 256) * 256
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def bundle(tile, count=0, unsafe_offset=False):
    data = bytearray(64 + 131072)
    struct.pack_into("<II", data, 0, 3, count)
    struct.pack_into("<I", data, 12, 5)
    struct.pack_into("<Q", data, 32, 40)
    struct.pack_into("<I", data, 40, 20 + 131072)
    struct.pack_into("<I", data, 60, 131072)
    offset = len(data) + 4
    if unsafe_offset:
        offset += 6_000_000
    struct.pack_into("<Q", data, 64, (len(tile) << 40) | offset)
    # The huge unused tail is deliberately not a tile.
    return bytes(data) + struct.pack("<I", len(tile)) + tile + b"\0" * 3_000_000


class TrackingBytes(io.BytesIO):
    def __init__(self, contents):
        super().__init__(contents)
        self.bytes_read = 0

    def read(self, n=-1):
        result = super().read(n)
        self.bytes_read += len(result)
        return result


def xy(lon, lat, z):
    return (0, 0)


def valid_tile(data):
    return "png" if data.startswith(b"\x89PNG") else None


class V2RemoteIndexTests(unittest.TestCase):
    def make_zip(self, *, count=0, unsafe_offset=False, compressed=False):
        stream = io.BytesIO()
        compression = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("tile/L00/R0000C0000.bundle",
                       bundle(make_png(), count, unsafe_offset),
                       compress_type=compression)
        return TrackingBytes(stream.getvalue())

    def test_only_index_and_image_read_from_multi_megabyte_source(self):
        stream = self.make_zip()
        with zipfile.ZipFile(stream) as z:
            info = z.infolist()[0]
            output = list(module.select_xyz_tiles(
                stream, info, 0, 0, 0,
                [0, 0, 0.001, 0.001],
                xy, valid_tile
            ))
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0][:4], (0, 0, 0, "png"))
            self.assertLess(stream.bytes_read, 500_000)
            self.assertLess(stream.bytes_read, info.file_size // 5)

    def test_reject_invalid_tile_offset(self):
        stream = self.make_zip(unsafe_offset=True)
        with zipfile.ZipFile(stream) as z:
            with self.assertRaises(ValueError):
                list(module.select_xyz_tiles(
                    stream, z.infolist()[0], 0, 0, 0,
                    [0, 0, 0.001, 0.001], xy, valid_tile
                ))

    def test_reject_compressed_bundle_without_reading_it(self):
        stream = self.make_zip(compressed=True)
        with zipfile.ZipFile(stream) as z:
            with self.assertRaises(ValueError):
                module.entry_payload_start(stream, z.infolist()[0])


if __name__ == "__main__":
    unittest.main()
