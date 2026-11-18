import copy
import json
import tempfile
from pathlib import Path
import unittest
import zlib

from preflight_verified_regional_catalog_20261118 import validate
from test_preflight_verified_regional_catalog_20261118 import fixture, GROUPS
from verify_remote_regional_candidate_readonly_20261118 import (
    MAGIC, audit, decode_private_record, reconcile_verified_receipts
)


def private_fixture():
    state, candidate = fixture()
    checkpoint_ref = {
        "key": "engineering/map-production/synthetic/checkpoint",
        "generation": "1794960002423998",
        "bytes": 12,
        "sha256": "b" * 64,
    }
    receipt_ref = {
        "key": "engineering/map-production/synthetic/receipt",
        "generation": "1794960002423997",
        "bytes": 12,
        "sha256": "c" * 64,
    }
    state["package"]["authority"]["finalDeliveryReserveUSD"] = "0.75"
    state["package"]["lastVerified"]["ordinal"] = 41
    state["package"]["lastVerified"]["checkpoint"] = checkpoint_ref
    state["package"]["lastVerified"]["receiptRef"] = receipt_ref
    part_rows = [r for r in candidate["catalogs"] if r["packageId"] not in GROUPS]
    index_rows = [r for r in candidate["catalogs"] if r["packageId"] in GROUPS]
    def ref(row):
        return {
            "key": row["objectName"], "generation": row["objectGeneration"],
            "sha256": row["sha256"], "bytes": row["byteCount"]
        }
    checkpoint = {
        "format": "rrgh-final-package-checkpoint-v1",
        "authoritySHA256": candidate["authoritySHA256"],
        "ordinal": 41,
        "catalogCandidates": state["package"]["lastVerified"]["catalogCandidates"],
        "parts": [
            {"part": {"packageID": r["packageId"], "sha256": r["sha256"]},
             "object": ref(r)}
            for r in part_rows
        ],
        "indexes": [
            {"identity": {"packageID": r["packageId"], "sha256": r["sha256"]},
             "object": ref(r)}
            for r in index_rows
        ],
    }
    receipt = {
        "format": "rrgh-slot-receipt-v1",
        "result": {
            "status": "verified",
            "checkpoint": checkpoint_ref,
            "catalogCandidates": state["package"]["lastVerified"]["catalogCandidates"],
            "packageBytesIndependentlyVerified": True,
            "verifiedParts": 122, "verifiedIndexes": 3,
        },
    }
    return state, candidate, checkpoint, receipt


class SyntheticClient:
    def __init__(self, state, candidates, checkpoint, receipt):
        self.calls = 0
        self.documents = dict(zip(
            (state["package"]["lastVerified"][k]["key"] for k in
             ("catalogCandidates", "checkpoint", "receiptRef")),
            (candidates, checkpoint, receipt),
        ))
    def record(self, ref):
        self.calls += 2  # Synthetic count only; NO real external reads
        payload = json.dumps(self.documents[ref["key"]]).encode()
        # Every protected record may use the authenticated compressed format,
        # including independently verified terminal receipts.
        return MAGIC + zlib.compress(payload, 9)
    def candidate_objects(self, candidates):
        self.calls += len(candidates["catalogs"])


class CandidateRemoteContractTests(unittest.TestCase):
    def test_synthetic_accepted_receipts_are_consistent_and_inactive(self):
        state, candidates, checkpoint, receipt = private_fixture()
        validate(state, candidates)
        client = SyntheticClient(state, candidates, checkpoint, receipt)
        result = audit(state, client)
        self.assertEqual(result["status"], "READ_ONLY_PINNED_GCS_METADATA_VERIFIED")
        self.assertEqual(result["cloudMetadataAndMediaRequests"], 131)
        self.assertIs(result["catalogActivated"], False)
        self.assertEqual(result["archivalPartBodiesRedownloaded"], 0)

    def test_real_receipt_encoding_is_compressed_and_decodes_before_reconciliation(self):
        state, candidates, checkpoint, receipt = private_fixture()
        client = SyntheticClient(state, candidates, checkpoint, receipt)
        raw = client.record(state["package"]["lastVerified"]["receiptRef"])
        self.assertTrue(raw.startswith(MAGIC))
        decoded = decode_private_record(raw)
        self.assertEqual(decoded["format"], "rrgh-slot-receipt-v1")
        self.assertEqual(decoded["result"]["verifiedParts"], 122)
        reconcile_verified_receipts(state, candidates, checkpoint, decoded)

    def test_private_staging_artifact_requires_full_audit_and_is_mode_0600(self):
        state, candidates, checkpoint, receipt = private_fixture()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "inert-stage-plan.json"
            client = SyntheticClient(state, candidates, checkpoint, receipt)
            result = audit(state, client, private_staging_output=path)
            self.assertEqual(result["cloudMetadataAndMediaRequests"], 131)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            payload = json.loads(path.read_text())
            self.assertEqual(len(payload["entries"]), 125)
            self.assertFalse(payload["nonproductionCatalogActivation"])
            self.assertTrue(all(entry["data"]["active"] is False
                                for entry in payload["entries"]))
            with self.assertRaises(FileExistsError):
                audit(state, SyntheticClient(state,candidates,checkpoint,receipt),
                      private_staging_output=path)

    def test_rejects_broken_accepted_part_provenance(self):
        state, candidates, checkpoint, receipt = private_fixture()
        changed = copy.deepcopy(checkpoint)
        changed["parts"][0]["object"]["sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            reconcile_verified_receipts(state, candidates, changed, receipt)

    def test_compressed_decoding_rejects_trailing_data(self):
        good = MAGIC + zlib.compress(b'{"ok":true}')
        self.assertEqual(decode_private_record(good), {"ok": True})
        with self.assertRaises(ValueError):
            decode_private_record(good + b"junk")

    def test_activation_authority_blocks_before_any_private_read(self):
        state, candidates, checkpoint, receipt = private_fixture()
        state["package"]["authority"]["activateCatalogs"] = True
        client = SyntheticClient(state, candidates, checkpoint, receipt)
        with self.assertRaises(ValueError):
            audit(state, client)
        self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
