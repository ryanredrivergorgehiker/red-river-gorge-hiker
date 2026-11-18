#!/usr/bin/env python3
"""Prepare a PRIVATE, INACTIVE Firestore staging plan from verified candidates.

No network access, Firebase SDK import, secret material, Firestore mutation,
object rewrite, or activation. The inputs MUST first have been independently
obtained from the exact immutable GCS generation and decoded by the approved
protected-record decoder. Structural validation alone is NOT remote readback.

The output contains nonpublic protected object paths: save in private storage,
never in GitHub, a chat, or a publicly accessible CI artifact.
"""
import argparse
import copy
import json
import os
from pathlib import Path

from preflight_verified_regional_catalog_20261118 import validate

ALLOWED_FIELDS = (
    "packageType", "requiredEntitlement", "version", "byteCount", "sha256",
    "offlineManifest", "storageBucket", "objectName", "objectGeneration",
    "objectMetadata"
)


def staging_plan(controller, candidates):
    evidence = validate(controller, candidates)
    entries = []
    for original in sorted(candidates["catalogs"], key=lambda row: row["packageId"]):
        fields = {field: copy.deepcopy(original[field]) for field in ALLOWED_FIELDS}
        fields.update({
            "active": False,
            "contentReady": False,
            "lifecycle": "staged",
            "deliveryState": "not_ready",
            "policyVersion": 2,
        })
        entries.append({
            "collection": "packageCatalog",
            "documentId": original["packageId"],
            "data": fields,
        })
    if len(entries) != 125:
        raise ValueError("Incomplete private staging plan")
    if any(entry["data"]["active"] is not False
           or entry["data"]["deliveryState"] != "not_ready"
           for entry in entries):
        raise ValueError("Staging cannot grant protected download access")
    return {
        "format": "rrgh-regional-nonprod-staging-plan-v1",
        "mode": "READ_ONLY_PREPARATION_NO_FIRESTORE_WRITES",
        "preflightStatus": evidence["status"],
        "candidateRecordReference": copy.deepcopy(evidence["candidateReference"]),
        "authoritySHA256": candidates["authoritySHA256"],
        "requiredIndependentRemoteReadback": True,
        "productionCatalogActivation": False,
        "nonproductionCatalogActivation": False,
        "physicalIPhoneRegionalAcceptance": False,
        "entries": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--decoded-candidates", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    plan = staging_plan(
        json.loads(args.controller.read_text()),
        json.loads(args.decoded_candidates.read_text()),
    )
    path = args.private_output.expanduser().resolve()
    # Never silently overwrite a manually reviewed staging artifact. File mode
    # 0600 limits other local users; the parent must already exist privately.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(plan, output, sort_keys=True, indent=2)
        output.write("\n")
    print("INACTIVE PRIVATE STAGING PLAN WRITTEN — 125 entries, zero activation. "
          "Do NOT upload this plan to GitHub. Remote GCS readback still required.")


if __name__ == "__main__":
    main()
