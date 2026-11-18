import copy
import hashlib
import unittest

from preflight_verified_regional_catalog_20261118 import validate


GROUPS = ("gorge-core", "gorge-aerial-leaf-on", "gorge-aerial-leaf-off")
AUTH = "a" * 64


def entry(package_id, sha, size, version, i):
    return {
        "packageId": package_id,
        "packageType": "offline_base",
        "requiredEntitlement": "base",
        "version": version,
        "byteCount": size,
        "sha256": sha,
        "offlineManifest": {
            "packageID": package_id, "version": version,
            "byteCount": size, "sha256": sha,
            "sources": [{"provider": "Synthetic test only"}],
        },
        "active": False, "contentReady": False,
        "storageBucket": "rrgh-nonproduction-protected-packages",
        "objectName": f"engineering/map-production/synthetic/{i}/immutable.bin",
        "objectGeneration": str(1794960002423784 + i),
        "objectMetadata": {
            "rrgh-sha256": sha, "rrgh-package-id": package_id,
            "rrgh-version": version,
        },
    }


def fixture():
    rows = []
    i = 0
    for group, count in zip(GROUPS, (40, 41, 41)):
        for n in range(count):
            sha = hashlib.sha256(f"{group}-{n}".encode()).hexdigest()
            rows.append(entry(group + "-" + sha, sha, 1024,
                              sha[:24], i))
            i += 1
        index_sha = hashlib.sha256(("index:" + group).encode()).hexdigest()
        rows.append(entry(group, index_sha, 5678,
                          "2026.11.10.regional.0123456789abcdef", i))
        i += 1
    controller = {
        "status": "package-validation-waiting",
        "package": {
            "status": "verified-awaiting-catalog",
            "authority": {"activateCatalogs": False},
            "authoritySHA256": AUTH,
            "lastVerified": {
                "verifiedParts": 122,
                "verifiedIndexes": 3,
                "packageBytesIndependentlyVerified": True,
                "operation": {"kind": "indexes", "groups": 3, "parts": 122},
                "catalogCandidates": {
                    "key": "engineering/map-production/synthetic/candidate.json",
                    "generation": "1794960002423999",
                    "bytes": 26469,
                    "sha256": "d" * 64,
                },
            },
        },
    }
    candidates = {
        "format": "rrgh-final-package-catalog-candidates-v1",
        "authoritySHA256": AUTH,
        "catalogs": rows,
        "active": False,
        "contentReady": False,
        "physicalIPhoneTestComplete": False,
    }
    return controller, candidates


class RegionalCatalogPreflightTests(unittest.TestCase):
    def test_complete_inactive_source_only_candidate_shape(self):
        state, candidate = fixture()
        result = validate(state, candidate)
        self.assertEqual(result["partEntries"], 122)
        self.assertEqual(result["indexEntries"], 3)
        self.assertFalse(result["signedCatalogActivated"])
        self.assertFalse(result["objectBytesReadBack"])
        self.assertEqual(result["status"],
                         "SOURCE_ONLY_STRUCTURE_PASS_NOT_ACTIVATION")

    def test_no_partial_or_optimistic_release(self):
        state, candidate = fixture()
        cases = []
        partial = copy.deepcopy(candidate)
        partial["catalogs"].pop(0)
        cases.append((state, partial))
        early = copy.deepcopy(candidate)
        early["active"] = True
        cases.append((state, early))
        one_early = copy.deepcopy(candidate)
        one_early["catalogs"][0]["contentReady"] = True
        cases.append((state, one_early))
        no_index = copy.deepcopy(candidate)
        no_index["catalogs"][-1]["packageId"] = "gorge-aerial-leaf-off-incorrect"
        cases.append((state, no_index))
        no_generation = copy.deepcopy(candidate)
        no_generation["catalogs"][5]["objectGeneration"] = ""
        cases.append((state, no_generation))
        object_drift = copy.deepcopy(candidate)
        object_drift["catalogs"][7]["objectMetadata"]["rrgh-sha256"] = "f" * 64
        cases.append((state, object_drift))
        unpinned = copy.deepcopy(candidate)
        unpinned["catalogs"][9]["objectName"] = "../public/secret"
        cases.append((state, unpinned))
        with_old_rights = copy.deepcopy(candidate)
        with_old_rights["catalogs"][0]["requiredEntitlement"] = "guest"
        cases.append((state, with_old_rights))
        drift = copy.deepcopy(state)
        drift["package"]["authority"]["activateCatalogs"] = True
        cases.append((drift, candidate))
        old_receipt = copy.deepcopy(state)
        old_receipt["package"]["lastVerified"]["verifiedIndexes"] = 2
        cases.append((old_receipt, candidate))
        for idx, (controller, catalog) in enumerate(cases):
            with self.subTest(idx=idx):
                with self.assertRaises(ValueError):
                    validate(controller, catalog)


if __name__ == "__main__":
    unittest.main()
