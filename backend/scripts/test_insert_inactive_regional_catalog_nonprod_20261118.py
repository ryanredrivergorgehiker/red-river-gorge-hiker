import copy
import json
import unittest

from preflight_verified_regional_catalog_20261118 import validate
from prepare_inactive_regional_catalog_staging_20261118 import staging_plan
from test_preflight_verified_regional_catalog_20261118 import fixture
from insert_inactive_regional_catalog_nonprod_20261118 import (
    URL, MAX_DOCUMENTS, build_immutable_staging_commit, insert_once,
)


class FakeReply:
    status = 200
    def geturl(self):
        return URL
    def read(self, maximum):
        return json.dumps({"writeResults": [{} for _ in range(MAX_DOCUMENTS)]}).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class StagingTests(unittest.TestCase):
    def good(self):
        controller, candidates = fixture()
        validate(controller, candidates)
        return staging_plan(controller, candidates)

    def test_exact_inactive_batch_is_all_or_nothing(self):
        plan = self.good()
        payload = build_immutable_staging_commit(plan)
        data = json.loads(payload)
        self.assertEqual(len(data["writes"]), 125)
        for item in data["writes"]:
            self.assertEqual(item["currentDocument"], {"exists": False})
            path = item["update"]["name"]
            self.assertTrue(path.startswith(
                "projects/rrgh-nonproduction/databases/(default)/documents/packageCatalog/"))
            fields = item["update"]["fields"]
            self.assertIs(fields["active"]["booleanValue"], False)
            self.assertIs(fields["contentReady"]["booleanValue"], False)
            self.assertEqual(fields["deliveryState"]["stringValue"], "not_ready")
            self.assertEqual(fields["lifecycle"]["stringValue"], "staged")
            self.assertEqual(fields["objectGeneration"].keys(), {"stringValue"})
            self.assertEqual(fields["byteCount"].keys(), {"integerValue"})

    def test_reject_activation_attempt_before_a_cloud_request(self):
        plan = self.good()
        for field, invalid in (("active", True), ("contentReady", True),
                               ("deliveryState", "ready"),
                               ("lifecycle", "active")):
            altered = copy.deepcopy(plan)
            altered["entries"][0]["data"][field] = invalid
            with self.assertRaises(ValueError):
                build_immutable_staging_commit(altered)

    def test_reject_foreign_project_and_unsafe_identity(self):
        plan = self.good()
        altered = copy.deepcopy(plan)
        altered["entries"][0]["data"]["storageBucket"] = "public-assets"
        with self.assertRaises(ValueError):
            build_immutable_staging_commit(altered)
        altered = copy.deepcopy(plan)
        altered["entries"][0]["documentId"] = "../foreign"
        with self.assertRaises(ValueError):
            build_immutable_staging_commit(altered)

    def test_reject_partial_duplicate_or_unpinned_inputs(self):
        plan = self.good()
        for variant in ("partial", "duplicate", "generation", "sha"):
            altered = copy.deepcopy(plan)
            if variant == "partial":
                altered["entries"].pop()
            elif variant == "duplicate":
                altered["entries"][1]["documentId"] = altered["entries"][0]["documentId"]
            elif variant == "generation":
                altered["entries"][0]["data"]["objectGeneration"] = 1794960002423784
            elif variant == "sha":
                altered["entries"][0]["data"]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                build_immutable_staging_commit(altered)

    def test_mocked_firestore_call_inserts_once_and_does_not_log_contents(self):
        plan = self.good()
        payload = build_immutable_staging_commit(plan)
        requests = []
        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeReply()
        result = insert_once(payload, "demo-token-" + "x"*35, opener=opener)
        self.assertEqual(result["documentsStaged"], 125)
        self.assertFalse(result["catalogActivated"])
        self.assertEqual(len(requests), 1)
        req = requests[0][0]
        self.assertEqual(req.full_url, URL)
        self.assertEqual(req.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
