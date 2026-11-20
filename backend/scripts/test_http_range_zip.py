"""Network-free tests of bounded official offline-archive byte ranges."""
import importlib.util
import io
from pathlib import Path
import re
import unittest
import zipfile

spec = importlib.util.spec_from_file_location(
    "bounded_ky_range", Path(__file__).with_name("http_range_zip.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("tile/L10/R0000C0000.bundle", b"tile")
        archive.writestr("unneeded-2mb-archive-entry.bin", b"x" * 2_000_000,
                         compress_type=zipfile.ZIP_STORED)
    return out.getvalue()


class Response(io.BytesIO):
    def __init__(self, content, start, end, size, etag='"stable"'):
        super().__init__(content)
        self.status = 206
        self.headers = {
            "Content-Range": f"bytes {start}-{end}/{size}",
            "ETag": etag,
        }


class RangeReaderTests(unittest.TestCase):
    def test_zip_reads_only_needed_bytes(self):
        data = sample_zip()
        calls = []
        def opener(req, timeout):
            text = req.get_header("Range")
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", text or "")
            self.assertIsNotNone(match)
            start, end = map(int, match.groups())
            calls.append((start, end))
            return Response(data[start:end + 1], start, end, len(data))

        with mod.RangeZipReader(
            "https://ky.box.com/shared/static/official.tpkx",
            opener=opener, chunk_size=4096, max_transfer_bytes=50_000
        ) as reader:
            with zipfile.ZipFile(reader) as archive:
                self.assertEqual(
                    archive.read("tile/L10/R0000C0000.bundle"), b"tile"
                )
            self.assertLess(reader.transfer_bytes, 50_000)
            self.assertLess(reader.transfer_bytes, len(data) // 2)
            self.assertTrue(reader.provenance["rangeBytesTransferred"] > 0)
        self.assertGreaterEqual(len(calls), 2)

    def test_reject_budget_overflow_and_untrusted_host(self):
        data = sample_zip()
        def opener(req, timeout):
            m = re.fullmatch(r"bytes=(\d+)-(\d+)", req.get_header("Range"))
            start, end = map(int, m.groups())
            return Response(data[start:end + 1], start, end, len(data))
        with self.assertRaises(ValueError):
            mod.RangeZipReader("https://evil.org/malware.tpkx", opener=opener)
        with mod.RangeZipReader(
            "https://ky.box.com/shared/static/official.tpkx",
            opener=opener, chunk_size=4096, max_transfer_bytes=4096
        ) as reader:
            with self.assertRaises(ValueError):
                reader.read(4096)

    def test_changing_etag_fails_closed(self):
        data = sample_zip()
        calls = []
        def opener(req, timeout):
            m = re.fullmatch(r"bytes=(\d+)-(\d+)", req.get_header("Range"))
            start, end = map(int, m.groups())
            calls.append(1)
            return Response(data[start:end + 1], start, end, len(data),
                            etag='"a"' if len(calls) == 1 else '"b"')
        with mod.RangeZipReader(
            "https://ky.box.com/shared/static/official.tpkx",
            opener=opener
        ) as reader:
            with self.assertRaises(ValueError):
                reader.read(32)


if __name__ == "__main__":
    unittest.main()
