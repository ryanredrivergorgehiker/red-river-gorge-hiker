#!/usr/bin/env python3
"""One-shot, read-only WIF verification of the ALREADY-produced regional catalog.

No bucket listing, object writes, IAM edits, Firestore, production deployment,
source regeneration, retry, object archive downloads or output artifacts.
Only controller-pinned candidate/checkpoint/receipt bytes (<1 MiB total)
and current metadata for exactly 125 pinned package objects are queried.
Print summary without object names, provenance or source payloads.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from preflight_verified_regional_catalog_20261118 import validate

BUCKET = "rrgh-nonproduction-protected-packages"
MAGIC = b"RRGH-CHECKPOINT-Z1\n"
MAX_CALLS = 132
MAX_WIRE_BYTES = 3 * 1024 * 1024
MAX_DECODED = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_private_record(raw):
    if raw.startswith(MAGIC):
        decoder = zlib.decompressobj()
        body = decoder.decompress(raw[len(MAGIC):], MAX_DECODED + 1)
        require(len(body) <= MAX_DECODED and decoder.eof
                and not decoder.unused_data and not decoder.unconsumed_tail,
                "Compressed private record failed structural integrity")
        raw = body
    require(len(raw) <= MAX_DECODED, "Decoded private record exceeded cap")
    return json.loads(raw)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ReadOnlyGCS:
    def __init__(self, token, opener=None):
        require(isinstance(token, str) and len(token) > 20,
                "Preexisting authorized WIF read-only access token required")
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect()).open
        self.calls = 0
        self.bytes = 0

    def get(self, key, *, media=False, generation=None, maximum=16_384):
        require(isinstance(key, str) and key.startswith("engineering/map-production/")
                and ".." not in key.split("/") and "\\" not in key,
                "Unsafe private object name")
        require(0 < maximum <= 1_048_576, "Remote response cap exceeded")
        self.calls += 1
        require(self.calls <= MAX_CALLS, "Cloud request ceiling reached")
        query = {"alt": "media"} if media else {"fields":
            "name,bucket,size,generation,md5Hash,crc32c,metadata"}
        if generation is not None:
            query["generation"] = generation
            if media:
                query["ifGenerationMatch"] = generation
        url = "https://storage.googleapis.com/storage/v1/b/" + BUCKET + "/o/" + (
            urllib.parse.quote(key, safe="")) + "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + self.token,
            "Accept-Encoding": "identity",
        })
        try:
            with self.opener(req, timeout=20) as response:
                require(response.status == 200 and response.geturl() == url,
                        "Non-200 or redirected GCS response")
                raw = response.read(maximum + 1)
                require(len(raw) <= maximum, "Remote object exceeded byte cap")
                self.bytes += len(raw)
                require(self.bytes <= MAX_WIRE_BYTES,
                        "Cloud transferred-byte ceiling reached")
                if media:
                    require(response.headers.get("x-goog-generation") == generation,
                            "Pinned generation media response mismatch")
                    return raw
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError("GCS access denied or missing: HTTP " +
                               str(error.code)) from None
        except urllib.error.URLError:
            raise RuntimeError("GCS network access unavailable") from None

    def record(self, ref):
        require(set(ref) == {"key", "generation", "sha256", "bytes"},
                "Controller reference is not complete")
        require(isinstance(ref["generation"], str) and
                re.fullmatch(r"[1-9][0-9]*", ref["generation"]) and
                isinstance(ref["sha256"], str) and
                re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) and
                type(ref["bytes"]) is int and 0 < ref["bytes"] <= 1_048_576,
                "Invalid immutable controller reference")
        meta = self.get(ref["key"])
        require(meta.get("name") == ref["key"] and meta.get("bucket") == BUCKET
                and meta.get("generation") == ref["generation"]
                and meta.get("size") == str(ref["bytes"]),
                "Current private record metadata changed")
        raw = self.get(ref["key"], media=True,
                       generation=ref["generation"], maximum=ref["bytes"])
        require(len(raw) == ref["bytes"] and digest(raw) == ref["sha256"],
                "Private immutable byte identity mismatch")
        return raw

    def candidate_objects(self, candidates):
        for row in candidates["catalogs"]:
            meta = self.get(row["objectName"])
            require(meta.get("name") == row["objectName"] and
                    meta.get("bucket") == BUCKET and
                    meta.get("generation") == row["objectGeneration"] and
                    meta.get("size") == str(row["byteCount"]),
                    "Regional package current generation or size drift")
            values = meta.get("metadata") or {}
            require(all(values.get(k) == v
                        for k, v in row["objectMetadata"].items()),
                    "Regional package immutable custom metadata mismatch")


def reconcile_verified_receipts(controller, candidates, checkpoint, receipt):
    verified = controller["package"]["lastVerified"]
    require(checkpoint.get("format") == "rrgh-final-package-checkpoint-v1"
            and checkpoint.get("authoritySHA256") ==
                candidates["authoritySHA256"]
            and checkpoint.get("ordinal") == verified["ordinal"]
            and len(checkpoint.get("parts", [])) == 122
            and len(checkpoint.get("indexes", [])) == 3
            and checkpoint.get("catalogCandidates") ==
                verified["catalogCandidates"],
            "Private checkpoint does not match accepted controller/catalog")
    require(receipt.get("format") == "rrgh-slot-receipt-v1" and
            receipt.get("result", {}).get("status") == "verified" and
            receipt["result"].get("checkpoint") == verified["checkpoint"] and
            receipt["result"].get("catalogCandidates") ==
                verified["catalogCandidates"] and
            receipt["result"].get("packageBytesIndependentlyVerified") is True
            and receipt["result"].get("verifiedParts") == 122
            and receipt["result"].get("verifiedIndexes") == 3,
            "Private final verified receipt differs from current controller")
    by_id = {r["packageId"]: r for r in candidates["catalogs"]}
    visited = set()
    for item in checkpoint["parts"]:
        identity = item["part"]
        record = by_id[identity["packageID"]]
        require(item["object"]["key"] == record["objectName"] and
                item["object"]["generation"] == record["objectGeneration"] and
                item["object"]["bytes"] == record["byteCount"] and
                item["object"]["sha256"] == record["sha256"] and
                identity["sha256"] == record["sha256"],
                "Regional part differs from independently accepted checkpoint")
        visited.add(identity["packageID"])
    for item in checkpoint["indexes"]:
        identity = item["identity"]
        record = by_id[identity["packageID"]]
        require(item["object"]["key"] == record["objectName"] and
                item["object"]["generation"] == record["objectGeneration"] and
                item["object"]["sha256"] == record["sha256"] and
                identity["sha256"] == record["sha256"],
                "Regional index differs from independently accepted checkpoint")
        visited.add(identity["packageID"])
    require(len(visited) == 125, "Checkpoint/candidate coverage not exact")


def audit(controller, client):
    package = controller.get("package", {})
    authority = package.get("authority", {})
    require(controller.get("status") == "package-validation-waiting" and
            package.get("status") == "verified-awaiting-catalog" and
            authority.get("activateCatalogs") is False and
            authority.get("finalDeliveryReserveUSD") == "0.75",
            "Delivery authority changed; refuse Cloud verification")
    verified = package["lastVerified"]
    # Read immutable records only, in this exact order. Do not read archives.
    candidate = decode_private_record(client.record(verified["catalogCandidates"]))
    checkpoint = decode_private_record(client.record(verified["checkpoint"]))
    receipt = json.loads(client.record(verified["receiptRef"]))
    outcome = validate(controller, candidate)
    reconcile_verified_receipts(controller, candidate, checkpoint, receipt)
    client.candidate_objects(candidate)
    require(client.calls == 131, "Unexpected number of authenticated GCS reads")
    return {
        "status": "READ_ONLY_PINNED_GCS_METADATA_VERIFIED",
        "candidateBytesHashGeneration": True,
        "checkpointBytesHashGeneration": True,
        "receiptBytesHashGeneration": True,
        "partsCurrentMetadataVerified": 122,
        "indexesCurrentMetadataVerified": 3,
        "archivalPartBodiesRedownloaded": 0,
        "cloudMetadataAndMediaRequests": client.calls,
        "transferredBytesUpperBound": MAX_WIRE_BYTES,
        "sourcePreflight": outcome["status"],
        "catalogActivated": False,
        "firestoreDocumentsWritten": 0,
        "rasterJobsDispatched": 0,
        "customerReleaseApproved": False,
        "physicalIPhoneRegionalAccepted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path, required=True)
    args = parser.parse_args()
    controller = json.loads(args.controller.read_text())
    token = os.environ.get("RRGH_GCS_READONLY_TOKEN", "")
    result = audit(controller, ReadOnlyGCS(token))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
