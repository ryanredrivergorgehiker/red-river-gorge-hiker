#!/usr/bin/env python3
"""Network-free proof that 12 real seam pilots cannot silently pass incomplete QA."""
import tempfile
from pathlib import Path
import unittest

from test_plan_kytopo_quad_seams import index
from pilot_kytopo_12_source_seams import run, PER_SEAM_MAX


def accepted(original, seam, root):
    return {"pair":seam["pair"],"xyz":seam["xyz"],
            "mosaicAlphaMin":255.0,"mosaicAlphaMax":255.0,
            "geoQA":{"pixelAndGeographicAlignmentVerified":True},
            "sourceBytesTransferred":2048,"jpegSha256":"c"*64,
            "jpegBytes":22000}


class TwelveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.root=Path(self.dir.name)/"seams"
    def tearDown(self):
        self.dir.cleanup()

    def test_all_twelve_receipts_never_claim_region(self):
        r=run(index(),self.root,accepted)
        self.assertEqual(r["candidateCount"],12)
        self.assertEqual(r["originalBytesTransferred"],12*2048)
        self.assertFalse(r["completeGorgePixelCoverage"])
        self.assertFalse(r["seamAppearanceOwnerAccepted"])
        self.assertIsNone(r["finalCoreDownloadBytes"])
        self.assertTrue((self.root/"TWELVE-SOURCE-BOUNDARY-PILOT.json").is_file())

    def test_one_bad_alpha_blocks_full_success_and_creates_failure_receipt(self):
        def fail(original,seam,root):
            r=accepted(original,seam,root)
            r["mosaicAlphaMin"]=0
            return r
        with self.assertRaises(ValueError):
            run(index(),self.root,fail)
        self.assertTrue((self.root/"BOUNDARY-FAILED-NOT-ACCEPTED.json").is_file())
        self.assertFalse((self.root/"TWELVE-SOURCE-BOUNDARY-PILOT.json").exists())

    def test_unbounded_original_transfer_fails_closed(self):
        def overflow(original,seam,root):
            r=accepted(original,seam,root)
            r["sourceBytesTransferred"]=PER_SEAM_MAX+1
            return r
        with self.assertRaises(ValueError):
            run(index(),self.root,overflow)

    def test_refuse_existing_qa_artifact_overwrite(self):
        self.root.mkdir()
        (self.root/"previous.json").write_text("previous source QA")
        with self.assertRaises(FileExistsError):
            run(index(),self.root,accepted)


if __name__=="__main__":
    unittest.main()
