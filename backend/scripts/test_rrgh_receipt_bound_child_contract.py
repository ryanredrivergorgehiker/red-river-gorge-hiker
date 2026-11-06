"""Synthetic negative tests; no authenticated Cloud or receipt evidence is claimed."""
import hashlib
import unittest
from rrgh_receipt_bound_child_contract import checked_catalog_child


class StructuralBindingTests(unittest.TestCase):
    def setUp(self):
        self.plan = "a" * 64
        self.job = "terrain-15-1-2"
        self.raw = b"0123456789"
        base = "engineering/map-production/plans/" + self.plan + "/"
        self.tile = dict(job=self.job,
            jobReceipt=dict(key=base+"slots/00001/jobs/"+self.job+".json",
                            generation="123",bytes=8,sha256="1"*64),
            checkpointObject=dict(key=base+"slots/00001/objects/tile.bin",
                                  generation="123",bytes=len(self.raw),
                                  sha256=hashlib.sha256(self.raw).hexdigest()),
            checkpointOffset=2,bytes=4,
            sha256=hashlib.sha256(self.raw[2:6]).hexdigest(),
            pixelReadbackVerified=True)
        self.catalog = dict(format="rrgh-verified-tile-catalog-v1",
                            planSHA256=self.plan,
                            independentPixelsAndHashesVerified=True,
                            nativePackageMembershipVerified=True,
                            deliveryVerified=False,physicalDeviceVerified=False)
        self.reader = lambda key, generation, maximum: self.raw

    def test_structurally_bound_child(self):
        self.assertEqual(checked_catalog_child(self.catalog,self.tile,self.reader),b"2345")

    def test_foreign_job_receipt_rejected_before_read(self):
        self.tile["jobReceipt"]["key"] = self.tile["jobReceipt"]["key"].replace(self.job,"other")
        with self.assertRaises(ValueError):
            checked_catalog_child(self.catalog,self.tile,lambda *a:self.fail("read attempted"))

    def test_foreign_checkpoint_plan_rejected_before_read(self):
        self.tile["checkpointObject"]["key"] = self.tile["checkpointObject"]["key"].replace(self.plan,"b"*64)
        with self.assertRaises(ValueError):
            checked_catalog_child(self.catalog,self.tile,lambda *a:self.fail("read attempted"))

    def test_catalog_without_independent_package_membership_rejected(self):
        self.catalog["nativePackageMembershipVerified"] = False
        with self.assertRaises(ValueError):
            checked_catalog_child(self.catalog,self.tile,lambda *a:self.fail("read attempted"))

    def test_claimed_device_acceptance_rejected(self):
        self.catalog["physicalDeviceVerified"] = True
        with self.assertRaises(ValueError):
            checked_catalog_child(self.catalog,self.tile,lambda *a:self.fail("read attempted"))


if __name__ == "__main__":
    unittest.main()
