"""Synthetic receipt-binding regressions; no real Cloud or trust enrollment."""
import hashlib
import json
import unittest
from rrgh_receipt_bound_protected_child import checked_receipt_bound_child


class ReceiptBoundChildTests(unittest.TestCase):
    def setUp(self):
        self.plan = "a" * 64
        self.base = "engineering/map-production/plans/" + self.plan + "/slots/00001/"
        self.raw = b"0123456789"
        self.obj = dict(key=self.base + "objects/tiles.bin", generation="123",
                        bytes=len(self.raw), sha256=hashlib.sha256(self.raw).hexdigest())
        self.tile = dict(job="hiking-1", path="tiles/hiking/1/0/0.png",
                         checkpointObject=self.obj, checkpointOffset=2, bytes=4,
                         sha256=hashlib.sha256(b"2345").hexdigest(),
                         pixelReadbackVerified=True)
        self.record = dict(format="rrgh-checkpoint-job-v1", planSHA256=self.plan,
                           slot=1, job="hiking-1",
                           result=dict(outputPacks=[dict(ref=self.obj, members=[
                               dict(path=self.tile["path"], offset=2, bytes=4,
                                    sha256=self.tile["sha256"])])]))
        self.refresh()

    def refresh(self):
        self.receipt_raw = json.dumps(self.record).encode()
        self.pin = dict(key=self.base + "jobs/hiking-1.json", generation="456",
                        bytes=len(self.receipt_raw),
                        sha256=hashlib.sha256(self.receipt_raw).hexdigest())
        self.tile["jobReceipt"] = dict(self.pin)

    def read(self, key, generation, limit):
        if key == self.pin["key"] and generation == self.pin["generation"]:
            return self.receipt_raw
        if key == self.obj["key"] and generation == self.obj["generation"]:
            return self.raw
        raise AssertionError("Unexpected protected read")

    def verify(self, pin=None):
        return checked_receipt_bound_child(self.tile, self.plan,
                                           self.pin if pin is None else pin, self.read)

    def test_exact_pinned_receipt_and_child(self):
        self.assertEqual(self.verify(), b"2345")

    def test_catalog_cannot_replace_trusted_pin(self):
        trusted = dict(self.pin)
        self.tile["jobReceipt"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.verify(trusted)

    def test_receipt_foreign_plan_rejected(self):
        self.record["planSHA256"] = "b" * 64
        self.refresh()
        with self.assertRaises(ValueError):
            self.verify()

    def test_receipt_member_hash_mismatch_rejected(self):
        self.record["result"]["outputPacks"][0]["members"][0]["sha256"] = "0" * 64
        self.refresh()
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_receipt_member_rejected(self):
        members = self.record["result"]["outputPacks"][0]["members"]
        members.append(dict(members[0]))
        self.refresh()
        with self.assertRaises(ValueError):
            self.verify()

    def test_untrusted_receipt_is_rejected_before_any_protected_read(self):
        trusted = dict(self.pin)
        self.tile["jobReceipt"]["sha256"] = "0" * 64
        reads = []
        def guarded_read(key, generation, limit):
            reads.append(key)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, trusted, guarded_read)
        self.assertEqual(reads, [])

    def test_authenticated_receipt_member_mismatch_never_reads_child(self):
        self.record["result"]["outputPacks"][0]["members"][0]["sha256"] = "0" * 64
        self.refresh()
        reads = []
        def guarded_read(key, generation, limit):
            reads.append(key)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, self.pin, guarded_read)
        self.assertEqual(reads, [self.pin["key"]])

    def test_corrupt_child_bytes_fail_after_receipt_binding(self):
        reads = []
        def corrupt_read(key, generation, limit):
            reads.append(key)
            if key == self.obj["key"]:
                return b"X" * len(self.raw)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, self.pin, corrupt_read)
        self.assertEqual(reads, [self.pin["key"], self.obj["key"]])

    def test_foreign_trusted_receipt_path_rejected_before_read(self):
        foreign = dict(self.pin, key=self.pin["key"].replace(self.plan, "b" * 64))
        self.tile["jobReceipt"] = dict(foreign)
        reads = []
        def guarded_read(key, generation, limit):
            reads.append(key)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, foreign, guarded_read)
        self.assertEqual(reads, [])

    def test_foreign_child_object_path_rejected_before_read(self):
        self.tile["checkpointObject"] = dict(
            self.obj, key=self.obj["key"].replace(self.plan, "b" * 64))
        reads = []
        def guarded_read(key, generation, limit):
            reads.append(key)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, self.pin, guarded_read)
        self.assertEqual(reads, [])

    def test_malformed_authenticated_member_range_never_reads_child(self):
        for bad_offset, bad_size in ((True, 4), (-1, 4), (2, True),
                                     (2, 0), (2, 512 * 1024 + 1),
                                     (len(self.raw), 4)):
            with self.subTest(offset=bad_offset, size=bad_size):
                self.setUp()
                member = self.record["result"]["outputPacks"][0]["members"][0]
                member["offset"] = bad_offset
                member["bytes"] = bad_size
                self.refresh()
                reads = []
                def guarded_read(key, generation, limit):
                    reads.append(key)
                    return self.read(key, generation, limit)
                with self.assertRaises(ValueError):
                    self.verify_with_reader(guarded_read)
                self.assertEqual(reads, [self.pin["key"]])

    def verify_with_reader(self, reader):
        return checked_receipt_bound_child(self.tile, self.plan, self.pin, reader)

    def test_duplicate_authenticated_receipt_field_rejected_before_child_read(self):
        # A duplicate key can otherwise give different parsers different identities.
        self.receipt_raw = self.receipt_raw.replace(
            b'"format": "rrgh-checkpoint-job-v1"',
            b'"format": "untrusted", "format": "rrgh-checkpoint-job-v1"', 1)
        self.pin = dict(self.pin, bytes=len(self.receipt_raw),
                        sha256=hashlib.sha256(self.receipt_raw).hexdigest())
        self.tile["jobReceipt"] = dict(self.pin)
        reads = []
        def guarded_read(key, generation, limit):
            reads.append(key)
            return self.read(key, generation, limit)
        with self.assertRaises(ValueError):
            checked_receipt_bound_child(self.tile, self.plan, self.pin, guarded_read)
        self.assertEqual(reads, [self.pin["key"]])

    def test_wrong_receipt_generation_fails_closed(self):
        trusted = dict(self.pin, generation="999")
        self.tile["jobReceipt"] = dict(trusted)
        with self.assertRaises(AssertionError):
            self.verify(trusted)


if __name__ == "__main__":
    unittest.main()
