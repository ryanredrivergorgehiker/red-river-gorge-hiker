#!/usr/bin/env python3
"""Fail-closed, ONCE-ONLY, INACTIVE Firestore insert of previously attested 125 regional objects.

This script must run in the same ephemeral, pre-existing WIF-authenticated
nonproduction job as a complete 131-call immutable-GCS audit. The local private
staging plan is never checked into GitHub, uploaded as an Actions artifact,
printed, or reused across a different authentication epoch.

Writes only new packageCatalog records with active=false, contentReady=false,
lifecycle=staged, deliveryState=not_ready. No archive reads, IAM, production
catalog, deployment, updates to existing docs, or customer activation.
"""
import argparse
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "rrgh-nonproduction"
COLLECTION = "packageCatalog"
BUCKET = "rrgh-nonproduction-protected-packages"
URL = ("https://firestore.googleapis.com/v1/projects/" + PROJECT +
       "/databases/(default)/documents:commit")
MAX_DOCUMENTS = 125
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")
GEN = re.compile(r"^[1-9][0-9]{0,19}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,512}$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def value(x):
    if x is None:
        return {"nullValue": None}
    if type(x) is bool:
        return {"booleanValue": x}
    if type(x) is int:
        return {"integerValue": str(x)}
    if type(x) is float:
        require(math.isfinite(x), "Nonfinite Firestore input")
        return {"doubleValue": x}
    if isinstance(x, str):
        return {"stringValue": x}
    if isinstance(x, list):
        return {"arrayValue": {"values": [value(v) for v in x]}}
    if isinstance(x, dict):
        require(all(isinstance(k, str) for k in x), "Invalid Firestore map keys")
        return {"mapValue": {"fields": {k: value(v) for k, v in x.items()}}}
    raise ValueError("Unsupported Firestore type")


def build_immutable_staging_commit(plan):
    require(isinstance(plan, dict) and
            plan.get("format") == "rrgh-regional-nonprod-staging-plan-v1" and
            plan.get("mode") == "READ_ONLY_PREPARATION_NO_FIRESTORE_WRITES" and
            plan.get("preflightStatus") == "SOURCE_ONLY_STRUCTURE_PASS_NOT_ACTIVATION" and
            plan.get("requiredIndependentRemoteReadback") is True and
            plan.get("productionCatalogActivation") is False and
            plan.get("nonproductionCatalogActivation") is False and
            plan.get("physicalIPhoneRegionalAcceptance") is False and
            isinstance(plan.get("authoritySHA256"), str) and
            HEX.fullmatch(plan["authoritySHA256"]),
            "Nonproduction inactive staging authority is incomplete")
    ref = plan.get("candidateRecordReference", {})
    require(isinstance(ref, dict) and
            isinstance(ref.get("sha256"), str) and HEX.fullmatch(ref["sha256"]) and
            isinstance(ref.get("generation"), str) and GEN.fullmatch(ref["generation"]),
            "Missing immutable verified private candidate reference")
    rows = plan.get("entries")
    require(isinstance(rows, list) and len(rows) == MAX_DOCUMENTS,
            "Exactly 125 original verified catalog documents required")
    ids = set()
    writes = []
    for row in rows:
        require(isinstance(row, dict) and
                row.get("collection") == COLLECTION and
                isinstance(row.get("documentId"), str) and
                SAFE_ID.fullmatch(row["documentId"]) and
                row["documentId"] not in ids,
                "Unsafe/duplicate regional document ID")
        ids.add(row["documentId"])
        data = row.get("data")
        require(isinstance(data, dict) and
                data.get("active") is False and
                data.get("contentReady") is False and
                data.get("lifecycle") == "staged" and
                data.get("deliveryState") == "not_ready" and
                data.get("requiredEntitlement") == "base" and
                data.get("packageType") == "offline_base" and
                data.get("storageBucket") == BUCKET and
                isinstance(data.get("objectGeneration"), str) and
                GEN.fullmatch(data["objectGeneration"]) and
                isinstance(data.get("byteCount"), int) and
                data["byteCount"] > 0 and
                isinstance(data.get("sha256"), str) and
                HEX.fullmatch(data["sha256"]) and
                isinstance(data.get("offlineManifest"), dict) and
                data["offlineManifest"].get("sha256") == data["sha256"] and
                data["offlineManifest"].get("byteCount") == data["byteCount"] and
                isinstance(data.get("objectMetadata"), dict),
                "Candidate cannot become an active public or unpinned package")
        doc = ("projects/" + PROJECT + "/databases/(default)/documents/" +
               COLLECTION + "/" + row["documentId"])
        writes.append({
            "update": {
                "name": doc,
                "fields": {k: value(v) for k, v in data.items()},
            },
            # Entire batch is atomic; NEVER overwrite existing catalog records.
            "currentDocument": {"exists": False},
        })
    require(len(writes) == MAX_DOCUMENTS and len(ids) == MAX_DOCUMENTS,
            "Incomplete regional object coverage")
    payload = json.dumps({"writes": writes}, separators=(",", ":"), sort_keys=True).encode()
    require(len(payload) <= MAX_REQUEST_BYTES,
            "Bounded Firestore batch exceeded private request limit")
    return payload


def insert_once(payload, token, opener=None):
    require(isinstance(token, str) and len(token) > 20,
            "Existing nonproduction workload identity token required")
    require(isinstance(payload, bytes) and len(payload) <= MAX_REQUEST_BYTES,
            "Invalid staging request")
    opener = opener or urllib.request.build_opener().open
    req = urllib.request.Request(
        URL, data=payload, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with opener(req, timeout=40) as response:
            require(response.status == 200 and response.geturl() == URL,
                    "Firestore nonproduction stage response invalid")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_RESPONSE_BYTES,
                    "Firestore stage response exceeded cap")
            output = json.loads(raw)
            require(len(output.get("writeResults", [])) == MAX_DOCUMENTS,
                    "Firestore did not acknowledge 125 atomic writes")
    except urllib.error.HTTPError as error:
        raise RuntimeError("INACTIVE_STAGE_FAIL_HTTP_" + str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("INACTIVE_STAGE_TRANSPORT_FAILURE") from None
    return {
        "status": "NONPRODUCTION_INACTIVE_125_DOCUMENTS_STAGED",
        "documentsStaged": MAX_DOCUMENTS,
        "catalogActivated": False,
        "customerRelease": False,
        "precondition": "ALL_NEW_DOCUMENTS_OR_ATOMIC_ABORT",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-stage-plan", type=Path, required=True)
    args = parser.parse_args()
    path = args.private_stage_plan.resolve()
    require(path.is_file() and path.stat().st_mode & 0o777 == 0o600,
            "Staging plan must be a private 0600 file")
    require(path.stat().st_size <= MAX_REQUEST_BYTES,
            "Staging plan exceeded cap")
    plan = json.loads(path.read_text(encoding="utf-8"))
    payload = build_immutable_staging_commit(plan)
    token = os.environ.get("RRGH_GOOGLE_ACCESS_TOKEN", "")
    print(json.dumps(insert_once(payload, token), sort_keys=True))


if __name__ == "__main__":
    main()
