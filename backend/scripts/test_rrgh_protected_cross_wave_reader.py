"""Bounded contract tests; fake reader is never production authentication."""
import hashlib
import unittest
from rrgh_protected_cross_wave_reader import checked_child, checked_object


class ProtectedReadbackTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"0123456789"
        self.reference = dict(key="engineering/map-production/plans/" + "a"*64 +
                              "/slots/00001/objects/tile.bin",
                              generation="1793932545156669", bytes=len(self.raw),
                              sha256=hashlib.sha256(self.raw).hexdigest())
        self.reader = lambda key, generation, limit: self.raw

    def test_exact_generation_bytes(self):
        self.assertEqual(checked_object(self.reference, self.reader, 100), self.raw)

    def test_corrupt_hash_rejected(self):
        bad = dict(self.reference, sha256="0"*64)
        with self.assertRaises(ValueError):
            checked_object(bad, self.reader, 100)

    def test_oversized_rejected_before_read(self):
        with self.assertRaises(ValueError):
            checked_object(self.reference, lambda *args: self.fail("reader called"), 5)

    def test_wrong_generation_or_missing_bytes_rejected(self):
        with self.assertRaises(ValueError):
            checked_object(self.reference, lambda *args: b"", 100)

    def test_child_offset_and_hash(self):
        child = self.raw[2:6]
        tile = dict(checkpointObject=self.reference, checkpointOffset=2, bytes=4,
                    sha256=hashlib.sha256(child).hexdigest(),
                    pixelReadbackVerified=True)
        self.assertEqual(checked_child(tile, self.reader), child)
        tile["checkpointOffset"] = 8
        with self.assertRaises(ValueError):
            checked_child(tile, self.reader)

    def test_unverified_pixel_claim_rejected(self):
        tile = dict(checkpointObject=self.reference, checkpointOffset=2, bytes=4,
                    sha256=hashlib.sha256(self.raw[2:6]).hexdigest(),
                    pixelReadbackVerified=False)
        with self.assertRaises(ValueError):
            checked_child(tile, self.reader)

    def test_foreign_namespace_rejected_before_read(self):
        foreign = dict(self.reference, key="public/tile.bin")
        with self.assertRaises(ValueError):
            checked_object(foreign, lambda *args: self.fail("reader called"), 100)

    def test_missing_generation_rejected_before_read(self):
        missing = dict(self.reference, generation="")
        with self.assertRaises(ValueError):
            checked_object(missing, lambda *args: self.fail("reader called"), 100)

    def test_overlapping_child_boundary_rejected_before_read(self):
        tile = dict(checkpointObject=self.reference, checkpointOffset=9, bytes=2,
                    sha256=hashlib.sha256(b"9").hexdigest(),
                    pixelReadbackVerified=True)
        with self.assertRaises(ValueError):
            checked_child(tile, lambda *args: self.fail("reader called"))

    def test_catalog_pixel_flag_cannot_override_bad_child_hash(self):
        tile = dict(checkpointObject=self.reference, checkpointOffset=2, bytes=4,
                    sha256="0"*64, pixelReadbackVerified=True)
        with self.assertRaises(ValueError):
            checked_child(tile, self.reader)

    def test_unverified_child_rejected_without_protected_read(self):
        tile = dict(checkpointObject=self.reference, checkpointOffset=2, bytes=4,
                    sha256=hashlib.sha256(b"2345").hexdigest(),
                    pixelReadbackVerified=False)
        with self.assertRaises(ValueError):
            checked_child(tile, lambda *args: self.fail("unverified child triggered protected read"))

    def test_plan_bound_child_rejects_foreign_receipt_without_read(self):
        from rrgh_protected_cross_wave_reader import checked_plan_bound_child
        plan = "a" * 64
        tile = dict(job="hiking-1", checkpointObject=self.reference,
                    checkpointOffset=2, bytes=4,
                    sha256=hashlib.sha256(b"2345").hexdigest(),
                    pixelReadbackVerified=True,
                    jobReceipt=dict(self.reference, key="engineering/map-production/plans/" +
                                    "b"*64 + "/slots/00001/jobs/hiking-1.json"))
        with self.assertRaises(ValueError):
            checked_plan_bound_child(tile, plan, lambda *args: self.fail("read"))

    def test_plan_bound_child_accepts_structurally_bound_fake_reader(self):
        from rrgh_protected_cross_wave_reader import checked_plan_bound_child
        plan = "a" * 64
        tile = dict(job="hiking-1", checkpointObject=self.reference,
                    checkpointOffset=2, bytes=4,
                    sha256=hashlib.sha256(b"2345").hexdigest(),
                    pixelReadbackVerified=True,
                    jobReceipt=dict(self.reference, key="engineering/map-production/plans/" +
                                    plan + "/slots/00001/jobs/hiking-1.json"))
        self.assertEqual(checked_plan_bound_child(tile, plan, self.reader), b"2345")


if __name__ == "__main__":
    unittest.main()
