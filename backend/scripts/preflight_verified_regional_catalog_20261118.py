#!/usr/bin/env python3
"""Source-only structural preflight for immutable, INACTIVE regional candidates.

Input is an independently decoded candidate JSON document and current
controller JSON. This is NOT remote GCS readback, catalog activation, a
Firestore import or permission to deliver paid content. NO network/write calls.
"""
import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{64}$")
GEN = re.compile(r"^[1-9][0-9]*$")
ROOT = "engineering/map-production/"
BUCKET = "rrgh-nonproduction-protected-packages"
INDEX_IDS = {"gorge-core", "gorge-aerial-leaf-on", "gorge-aerial-leaf-off"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(controller, candidate_document):
    package = controller.get("package") or {}
    verified = package.get("lastVerified") or {}
    authority = package.get("authority") or {}
    candidate_ref = verified.get("catalogCandidates") or {}
    require(controller.get("status") == "package-validation-waiting"
            and package.get("status") == "verified-awaiting-catalog"
            and authority.get("activateCatalogs") is False,
            "Controller is not in an inactive, fully verified delivery hold")
    require(verified.get("verifiedParts") == 122
            and verified.get("verifiedIndexes") == 3
            and verified.get("packageBytesIndependentlyVerified") is True
            and verified.get("operation") == {"kind": "indexes", "groups": 3, "parts": 122},
            "Independently accepted full package checkpoint missing")
    require(isinstance(candidate_ref.get("sha256"), str)
            and SHA.fullmatch(candidate_ref["sha256"])
            and isinstance(candidate_ref.get("bytes"), int)
            and 0 < candidate_ref["bytes"] <= 1_048_576
            and isinstance(candidate_ref.get("generation"), str)
            and GEN.fullmatch(candidate_ref["generation"])
            and isinstance(candidate_ref.get("key"), str)
            and candidate_ref["key"].startswith(ROOT),
            "Missing complete immutable catalog-candidate reference")
    require(candidate_document.get("format") ==
            "rrgh-final-package-catalog-candidates-v1"
            and candidate_document.get("authoritySHA256") == package.get("authoritySHA256")
            and candidate_document.get("active") is False
            and candidate_document.get("contentReady") is False
            and candidate_document.get("physicalIPhoneTestComplete") is False,
            "Catalog record not bound to inactive verified package authority")
    rows = candidate_document.get("catalogs")
    require(isinstance(rows, list) and len(rows) == 125,
            "Exactly 122 parts and 3 indexes must be represented")
    seen_ids = set()
    seen_objects = set()
    indexes = set()
    part_counts = {key: 0 for key in INDEX_IDS}
    versions = set()
    for row in rows:
        require(isinstance(row, dict), "Catalog entry must be an object")
        package_id = row.get("packageId")
        require(isinstance(package_id, str) and package_id not in seen_ids,
                "Duplicate or missing package ID")
        seen_ids.add(package_id)
        index_id = package_id if package_id in INDEX_IDS else None
        group = index_id
        if group is None:
            for candidate in INDEX_IDS:
                if package_id.startswith(candidate + "-"):
                    group = candidate
                    part_counts[candidate] += 1
                    break
        require(group is not None, "Unknown group/package identity")
        if index_id is not None:
            indexes.add(index_id)
        sha = row.get("sha256")
        nbytes = row.get("byteCount")
        version = row.get("version")
        require(isinstance(sha, str) and SHA.fullmatch(sha)
                and type(nbytes) is int and 0 < nbytes <= 256_000_000
                and isinstance(version, str) and version,
                "Invalid immutable package size, SHA or version")
        if index_id is not None:
            require(nbytes <= 1_048_576
                    and version.startswith("2026.11.10.regional."),
                    "Invalid regional signed index identity")
            versions.add(version)
        else:
            require(package_id == group + "-" + sha and version == sha[:24],
                    "Part name and version must be derived from immutable SHA")
        manifest = row.get("offlineManifest")
        require(isinstance(manifest, dict)
                and all(manifest.get(k) == row.get(v) for k, v in (
                    ("packageID", "packageId"), ("version", "version"),
                    ("sha256", "sha256"), ("byteCount", "byteCount")))
                and isinstance(manifest.get("sources"), list)
                and bool(manifest["sources"]),
                "Catalog authorization manifest/provenance mismatch")
        require(row.get("active") is False
                and row.get("contentReady") is False
                and row.get("packageType") == "offline_base"
                and row.get("requiredEntitlement") == "base"
                and row.get("storageBucket") == BUCKET,
                "Candidate grants delivery or violates private Base destination")
        generation = row.get("objectGeneration")
        name = row.get("objectName")
        require(isinstance(generation, str) and GEN.fullmatch(generation)
                and isinstance(name, str) and name.startswith(ROOT)
                and ".." not in name.split("/") and not name.endswith("/")
                and "\\" not in name and "//" not in name,
                "Unpinned or unsafe protected object identity")
        require((name, generation) not in seen_objects,
                "Duplicate object reference in distinct candidate packages")
        seen_objects.add((name, generation))
        require(row.get("objectMetadata") == {
            "rrgh-sha256": sha,
            "rrgh-package-id": package_id,
            "rrgh-version": version,
        }, "Catalog object metadata does not pin immutable package")
    require(indexes == INDEX_IDS and sum(part_counts.values()) == 122
            and all(part_counts.values()) and len(versions) == 1,
            "Missing one of three index groups or regional parts")
    return {
        "status": "SOURCE_ONLY_STRUCTURE_PASS_NOT_ACTIVATION",
        "partEntries": 122,
        "indexEntries": 3,
        "corePartEntries": part_counts["gorge-core"],
        "aerialLeafOnPartEntries": part_counts["gorge-aerial-leaf-on"],
        "aerialLeafOffPartEntries": part_counts["gorge-aerial-leaf-off"],
        "candidateReference": candidate_ref,
        "objectBytesReadBack": False,
        "remoteGenerationReverified": False,
        "signedCatalogActivated": False,
        "physicalIPhoneRegionalMapAccepted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--decoded-candidates", type=Path, required=True)
    args = parser.parse_args()
    result = validate(json.loads(args.controller.read_text()),
                      json.loads(args.decoded_candidates.read_text()))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
