#!/usr/bin/env python3
"""Single-transaction NONPRODUCTION regional catalog activation, with fail-closed readback.

Never mutates any GCS object, identity, stored SHA/generation, account, lease or
production catalog. Requires a fresh temporary private staging plan created only
after the 131-object independent read-only cloud audit in the SAME trusted job.

Budget: at most 125 Firestore document GETs before the commit, one 125-write
atomic transaction, 125 confirmation GETs. A failed confirmation permits at
most one fail-closed rollback transaction and its 125 checks.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from insert_inactive_regional_catalog_nonprod_20261118 import (
    MAX_DOCUMENTS, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
    PROJECT, URL, build_immutable_staging_commit, value,
)

COLLECTION = "packageCatalog"
DOCUMENT_BASE = ("projects/" + PROJECT +
                 "/databases/(default)/documents/" + COLLECTION + "/")
DOCUMENT_URL = "https://firestore.googleapis.com/v1/"
FIELDS = ("active", "contentReady", "deliveryState", "lifecycle")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode_value(data):
    require(isinstance(data, dict) and len(data) == 1,
            "Firestore field has malformed wire value")
    k, v = next(iter(data.items()))
    if k == "nullValue":
        return None
    if k == "booleanValue":
        require(type(v) is bool, "Invalid boolean type")
        return v
    if k == "integerValue":
        require(isinstance(v, str) and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", v),
                "Invalid Firestore integer")
        return int(v)
    if k == "stringValue":
        require(isinstance(v, str), "Invalid Firestore string")
        return v
    if k == "doubleValue":
        require(type(v) in (int, float), "Invalid Firestore float")
        return float(v)
    if k == "arrayValue":
        require(isinstance(v, dict), "Invalid Firestore array")
        return [decode_value(x) for x in v.get("values", [])]
    if k == "mapValue":
        require(isinstance(v, dict), "Invalid Firestore map")
        return {key:decode_value(x) for key,x in v.get("fields", {}).items()}
    raise ValueError("Unexpected Firestore type in catalog")


def decode_document(snapshot):
    fields = snapshot.get("fields")
    require(isinstance(fields, dict), "Firestore catalog fields missing")
    return {key: decode_value(v) for key,v in fields.items()}


def plan_rows(plan):
    # Uses the same 125-document full preflight as the previous successful
    # inactive staging, never trusting an arbitrary input plan.
    build_immutable_staging_commit(plan)
    return {row["documentId"]: row["data"] for row in plan["entries"]}


def fetch_all(plan, token, opener=None, *, expected_active=False):
    rows = plan_rows(plan)
    require(len(rows) == MAX_DOCUMENTS, "Incomplete plan")
    opener = opener or urllib.request.build_opener().open
    snapshots = {}
    for package_id, expected in sorted(rows.items()):
        path = DOCUMENT_BASE + package_id
        req = urllib.request.Request(
            DOCUMENT_URL + path,
            headers={"Authorization":"Bearer " + token,
                     "Accept-Encoding":"identity"},
            method="GET",
        )
        try:
            with opener(req, timeout=16) as response:
                require(response.status == 200 and
                        response.geturl() == req.full_url,
                        "Unexpected Firestore response")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                require(len(raw) <= MAX_RESPONSE_BYTES,
                        "Firestore document exceeded bound")
                doc = json.loads(raw)
        except urllib.error.HTTPError as error:
            raise RuntimeError("FIRESTORE_READ_HTTP_" + str(error.code)) from None
        except urllib.error.URLError:
            raise RuntimeError("FIRESTORE_READ_TRANSPORT_FAILURE") from None

        expected_data = dict(expected)
        expected_data.update({
            "active": expected_active,
            "contentReady": expected_active,
            "lifecycle": "active" if expected_active else "staged",
            "deliveryState": "ready" if expected_active else "not_ready",
        })
        require(doc.get("name") == path,
                "Catalog document path mismatch")
        actual = decode_document(doc)
        require(actual == expected_data and
                set(actual) == set(expected_data),
                "Catalog document contents differ from independently attested source")
        require(isinstance(doc.get("updateTime"), str) and
                doc["updateTime"].endswith("Z"),
                "Missing exact Firestore updateTime precondition")
        snapshots[package_id] = doc["updateTime"]
    require(len(snapshots) == MAX_DOCUMENTS, "Incomplete verified catalog")
    return snapshots


def build_transition(plan, timestamps, *, activate):
    rows = plan_rows(plan)
    require(isinstance(timestamps, dict) and
            len(timestamps) == len(rows) == MAX_DOCUMENTS and
            set(timestamps) == set(rows), "Missing catalog optimistic locks")
    writes = []
    for package_id in sorted(rows):
        stamp = timestamps[package_id]
        require(isinstance(stamp, str) and stamp.endswith("Z"),
                "Invalid Firestore optimistic lock")
        fields = {
            "active": value(activate),
            "contentReady": value(activate),
            "deliveryState": value("ready" if activate else "not_ready"),
            "lifecycle": value("active" if activate else "staged"),
        }
        writes.append({
            "update":{
                "name":DOCUMENT_BASE + package_id,
                "fields":fields,
            },
            "updateMask":{"fieldPaths":list(FIELDS)},
            "currentDocument":{"updateTime":stamp},
        })
    body = json.dumps({"writes":writes},separators=(",",":"),sort_keys=True).encode()
    require(len(body) <= MAX_REQUEST_BYTES,
            "Atomic nonproduction activation body exceeds bound")
    return body


def commit_once(payload, token, opener=None):
    opener = opener or urllib.request.build_opener().open
    require(isinstance(payload, bytes) and
            len(payload) <= MAX_REQUEST_BYTES,"Invalid commit body")
    req = urllib.request.Request(
        URL, data=payload, method="POST",
        headers={"Authorization":"Bearer " + token,
                 "Content-Type":"application/json",
                 "Accept-Encoding":"identity"},
    )
    try:
        with opener(req, timeout=45) as response:
            require(response.status == 200 and
                    response.geturl() == URL,
                    "Atomic Firestore commit response invalid")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_RESPONSE_BYTES,
                    "Atomic response exceeds limit")
            receipt = json.loads(raw)
            require(len(receipt.get("writeResults",[])) == MAX_DOCUMENTS,
                    "Incomplete Firestore atomic transaction receipt")
    except urllib.error.HTTPError as error:
        raise RuntimeError("FIRESTORE_ATOMIC_COMMIT_HTTP_" + str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("FIRESTORE_ATOMIC_COMMIT_TRANSPORT_FAILURE") from None


def run(plan, token, opener=None):
    require(isinstance(token, str) and len(token) > 20,
            "Existing bounded nonproduction WIF token required")
    preconditions = fetch_all(plan, token, opener, expected_active=False)
    commit_once(build_transition(plan, preconditions, activate=True), token, opener)
    try:
        fetch_all(plan, token, opener, expected_active=True)
    except Exception:
        # A successful atomic commit with a failed post-read must never be
        # represented as ready. Re-read safely and reverse the same 125 fields,
        # preserving all original immutable identity/provenance properties.
        try:
            locks = fetch_all(plan, token, opener, expected_active=True)
            commit_once(build_transition(plan, locks, activate=False), token, opener)
            fetch_all(plan, token, opener, expected_active=False)
        except Exception:
            raise RuntimeError(
                "NONPROD_ACTIVATION_UNCONFIRMED_ROLLBACK_UNCONFIRMED_STOP_AND_AUDIT"
            ) from None
        raise RuntimeError("NONPROD_ACTIVATION_ROLLED_BACK_AFTER_FAILED_READBACK")
    return {
        "status":"AUTHENTICATED_NONPROD_REGIONAL_CATALOG_125_ACTIVE_VERIFIED",
        "parts":122,
        "indexes":3,
        "catalogActivatedNonproduction":True,
        "productionCatalogActivation":False,
        "customerRelease":False,
        "documentsWritten":MAX_DOCUMENTS,
        "archivalObjectWrites":0,
        "rasterJobsDispatched":0,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-stage-plan",type=Path,required=True)
    args=parser.parse_args()
    plan_path=args.private_stage_plan.resolve()
    require(plan_path.is_file() and
            plan_path.stat().st_mode & 0o777 == 0o600 and
            plan_path.stat().st_size <= MAX_REQUEST_BYTES,
            "Private authenticated plan missing/unsafe")
    plan=json.loads(plan_path.read_text(encoding="utf-8"))
    token=os.environ.get("RRGH_GOOGLE_ACCESS_TOKEN","")
    print(json.dumps(run(plan,token),sort_keys=True))


if __name__ == "__main__":
    main()
