"""Mocked, network-free official county TPKX probe tests."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).with_name("probe_official_ky_tpkx_metadata.py")
s = importlib.util.spec_from_file_location("official_probe", p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


class ProbeTests(unittest.TestCase):
    def test_only_official_records_are_probed(self):
        index = {
            "reviewStatus": "NOT APPROVED OR DOWNLOADED",
            "records": [
                {"county": "Powell",
                 "topoDownloadURL": "https://ky.box.com/shared/static/topo.tpkx",
                 "aerialDownloadURL": "https://ky.box.com/shared/static/aerial.tpkx"},
                {"county": "Wolfe",
                 "topoDownloadURL": "https://untrusted.example.org/a.tpkx",
                 "aerialDownloadURL": None},
            ],
        }
        result = m.probe(index, inspector=lambda u: {
            "source": u, "bytes": 100, "rangeSupported": True,
            "status": "mock",
        })
        self.assertEqual(result["sourceCount"], 2)
        self.assertEqual(result["knownBytes"], 200)
        self.assertEqual(result["unknownSizeCount"], 0)
        self.assertTrue(all(row["county"] == "Powell"
                            for row in result["sources"]))

    def test_unapproved_and_non_official_sources_blocked(self):
        self.assertFalse(m.allowed("http://ky.box.com/public/a.tpkx"))
        self.assertFalse(m.allowed("https://ky.box.com.evil.org/x.tpkx"))
        self.assertTrue(m.allowed("https://ky.box.com/shared/static/x.tpkx"))
        with self.assertRaises(ValueError):
            m.probe({"reviewStatus": "APPROVED", "records": []})
        with self.assertRaises(ValueError):
            m.probe({"reviewStatus": "NOT APPROVED OR DOWNLOADED",
                     "records": []})


if __name__ == "__main__":
    unittest.main()
