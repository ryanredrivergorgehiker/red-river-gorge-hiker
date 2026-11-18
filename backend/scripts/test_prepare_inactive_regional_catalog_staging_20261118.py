import copy
import unittest

from test_preflight_verified_regional_catalog_20261118 import fixture
from prepare_inactive_regional_catalog_staging_20261118 import staging_plan


class InactiveRegionalStagingPlanTests(unittest.TestCase):
    def test_exact_catalog_is_never_download_enabled(self):
        controller, candidates = fixture()
        plan = staging_plan(controller, candidates)
        self.assertEqual(plan["mode"], "READ_ONLY_PREPARATION_NO_FIRESTORE_WRITES")
        self.assertFalse(plan["nonproductionCatalogActivation"])
        self.assertFalse(plan["productionCatalogActivation"])
        self.assertEqual(len(plan["entries"]), 125)
        self.assertEqual(
            len({row["documentId"] for row in plan["entries"]}), 125
        )
        for entry in plan["entries"]:
            data = entry["data"]
            self.assertEqual(entry["collection"], "packageCatalog")
            self.assertIs(data["active"], False)
            self.assertIs(data["contentReady"], False)
            self.assertEqual(data["deliveryState"], "not_ready")
            self.assertEqual(data["lifecycle"], "staged")
            self.assertEqual(data["requiredEntitlement"], "base")
            self.assertEqual(
                data["storageBucket"],
                "rrgh-nonproduction-protected-packages",
            )
            self.assertIsInstance(data["objectGeneration"], str)

    def test_candidate_data_is_unchanged_by_preparation(self):
        controller, candidates = fixture()
        before = copy.deepcopy(candidates)
        staging_plan(controller, candidates)
        self.assertEqual(candidates, before)

    def test_incomplete_or_prematurely_active_catalog_cannot_be_staged(self):
        for mode in ("missing", "active", "generation", "entitlement"):
            with self.subTest(mode=mode):
                controller, candidates = fixture()
                if mode == "missing":
                    candidates["catalogs"].pop()
                elif mode == "active":
                    candidates["catalogs"][0]["active"] = True
                elif mode == "generation":
                    candidates["catalogs"][0]["objectGeneration"] = ""
                else:
                    candidates["catalogs"][0]["requiredEntitlement"] = "guest"
                with self.assertRaises(ValueError):
                    staging_plan(controller, candidates)


if __name__ == "__main__":
    unittest.main()
