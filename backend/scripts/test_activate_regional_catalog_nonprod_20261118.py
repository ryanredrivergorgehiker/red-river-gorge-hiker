import copy
import json
import unittest
from test_preflight_verified_regional_catalog_20261118 import fixture
from prepare_inactive_regional_catalog_staging_20261118 import staging_plan
from insert_inactive_regional_catalog_nonprod_20261118 import value
from activate_regional_catalog_nonprod_20261118 import (
    DOCUMENT_BASE, URL, build_transition, fetch_all, run,
)


class Response:
    status = 200
    def __init__(self, url, data):
        self.url = url
        self.raw = json.dumps(data).encode()
    def geturl(self):
        return self.url
    def read(self, size):
        return self.raw[:size]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


class MockFirestore:
    def __init__(self,plan):
        self.docs = {r["documentId"]:copy.deepcopy(r["data"])
                     for r in plan["entries"]}
        self.reads = 0
        self.commits = 0
        self.corrupt_once = False
    def __call__(self,req,timeout):
        if req.get_method() == "GET":
            self.reads += 1
            assert req.full_url.startswith(
                "https://firestore.googleapis.com/v1/" + DOCUMENT_BASE)
            package_id = req.full_url.rsplit("/",1)[-1]
            doc = copy.deepcopy(self.docs[package_id])
            if self.corrupt_once and self.commits == 1:
                doc["objectGeneration"] = "123"
                self.corrupt_once = False
            return Response(req.full_url,{
                "name":DOCUMENT_BASE + package_id,
                "updateTime":"2026-11-18T19:00:00Z",
                "fields":{k:value(v) for k,v in doc.items()},
            })
        assert req.get_method() == "POST"
        assert req.full_url == URL
        data = json.loads(req.data)
        assert len(data["writes"]) == 125
        self.commits += 1
        for write in data["writes"]:
            package_id = write["update"]["name"].rsplit("/",1)[-1]
            assert write["currentDocument"] == {
                "updateTime":"2026-11-18T19:00:00Z"}
            assert set(write["updateMask"]["fieldPaths"]) == {
                "active","contentReady","deliveryState","lifecycle"}
            doc = self.docs[package_id]
            fields = write["update"]["fields"]
            for key,v in fields.items():
                doc[key] = (v["booleanValue"] if "booleanValue" in v
                            else v["stringValue"])
        return Response(URL,{"writeResults":[{} for _ in range(125)]})


class NonproductionActivationTests(unittest.TestCase):
    def plan(self):
        state,candidates = fixture()
        return staging_plan(state,candidates)

    def test_atomic_exact_four_field_activation_with_optimistic_locks(self):
        plan = self.plan()
        locks = {x["documentId"]:"2026-11-18T19:00:00Z"
                 for x in plan["entries"]}
        body = build_transition(plan,locks,activate=True)
        writes = json.loads(body)["writes"]
        self.assertEqual(len(writes),125)
        for w in writes:
            self.assertEqual(set(w["update"]["fields"]),{
                "active","contentReady","deliveryState","lifecycle"})
            self.assertEqual(w["currentDocument"],{
                "updateTime":"2026-11-18T19:00:00Z"})
            self.assertEqual(w["update"]["fields"]["deliveryState"],
                             {"stringValue":"ready"})
            self.assertEqual(w["update"]["fields"]["active"],
                             {"booleanValue":True})

    def test_success_is_actual_readback_of_every_nonproduction_record(self):
        plan=self.plan()
        fake=MockFirestore(plan)
        result=run(plan,"mock-token-"+"x"*36,opener=fake)
        self.assertEqual(result["status"],
            "AUTHENTICATED_NONPROD_REGIONAL_CATALOG_125_ACTIVE_VERIFIED")
        self.assertEqual(fake.reads,250)
        self.assertEqual(fake.commits,1)
        self.assertEqual(result["archivalObjectWrites"],0)
        self.assertTrue(all(doc["active"] and doc["contentReady"] and
            doc["deliveryState"]=="ready" for doc in fake.docs.values()))

    def test_snapshot_mismatch_prevents_all_writes(self):
        plan=self.plan()
        fake=MockFirestore(plan)
        fake.docs[plan["entries"][0]["documentId"]]["objectGeneration"]="42"
        with self.assertRaisesRegex(ValueError,"contents differ"):
            run(plan,"mock-token-"+"x"*36,opener=fake)
        self.assertEqual(fake.commits,0)

    def test_one_failed_post_readback_rolls_back_all_125(self):
        plan=self.plan()
        fake=MockFirestore(plan)
        fake.corrupt_once=True
        with self.assertRaisesRegex(RuntimeError,"ROLLED_BACK"):
            run(plan,"mock-token-"+"x"*36,opener=fake)
        self.assertEqual(fake.commits,2)
        self.assertTrue(all(doc["active"] is False and
            doc["deliveryState"]=="not_ready" for doc in fake.docs.values()))

    def test_missing_optimistic_lock_refuses_mutation(self):
        plan=self.plan()
        with self.assertRaises(ValueError):
            build_transition(plan,{},activate=True)

    def test_overridden_customer_release_never_authorized(self):
        plan=self.plan()
        plan["productionCatalogActivation"]=True
        locks={x["documentId"]:"2026-11-18T19:00:00Z"
               for x in plan["entries"]}
        with self.assertRaises(ValueError):
            build_transition(plan,locks,activate=True)


if __name__=="__main__":
    unittest.main()
