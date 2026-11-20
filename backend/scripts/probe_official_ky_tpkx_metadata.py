#!/usr/bin/env python3
"""Bounded read-only HEAD/range probe of OFFICIAL county TPKX links.

Input: approved public county index metadata JSON. Does NOT download map
content, authorize redistribution, connect to Firebase or publish Base.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def allowed(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "ky.box.com"


def inspect_source(url, opener=urlopen):
    if not allowed(url):
        raise ValueError("Only official ky.box.com direct package links are allowed")
    result = {"source": url, "bytes": None, "rangeSupported": False,
              "status": "UNVERIFIED"}
    try:
        # The final redirected CDN URL is deliberately never stored.
        with opener(Request(url, method="HEAD"), timeout=12) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                result["bytes"] = int(length)
            result["rangeSupported"] = (
                "bytes" in response.headers.get("Accept-Ranges", "").lower())
            result["status"] = f"HTTP {response.status} (HEAD)"
    except Exception as exc:
        result["status"] = "HEAD unavailable: " + type(exc).__name__
    if result["bytes"] and result["rangeSupported"]:
        return result
    # Some Box download redirects accept byte ranges without advertising
    # them to HEAD. Read AT MOST ONE byte and close. A 200 response cannot
    # authorize downloading an entire package.
    try:
        with opener(Request(url, headers={"Range": "bytes=0-0"}),
                    timeout=12) as response:
            if response.status != 206:
                result["status"] = f"HTTP {response.status}; range unavailable"
                return result
            content_range = response.headers.get("Content-Range", "")
            if "/" in content_range and content_range.split("/")[-1].isdigit():
                result["bytes"] = int(content_range.split("/")[-1])
            if len(response.read(2)) > 1:
                result["status"] = "Range response larger than one byte"
                return result
            result["rangeSupported"] = True
            result["status"] = "HTTP 206; single-byte range"
    except Exception as exc:
        result["status"] = "Range unavailable: " + type(exc).__name__
    return result


def probe(index, max_items=16, inspector=inspect_source):
    if index.get("reviewStatus") != "NOT APPROVED OR DOWNLOADED":
        raise ValueError("Expected an unapproved official discovery report")
    records = index.get("records")
    if not isinstance(records, list) or not (1 <= len(records) <= 16):
        raise ValueError("Unsafe or empty county source discovery")
    items = []
    for entry in records:
        for kind, key in [("topo", "topoDownloadURL"),
                          ("leaf-off-aerial", "aerialDownloadURL")]:
            url = entry.get(key)
            if url and allowed(url):
                items.append((entry["county"], kind, url))
    if len(items) > max_items:
        raise ValueError("Too many package probes")
    with ThreadPoolExecutor(max_workers=4) as pool:
        inspections = list(pool.map(lambda rec: inspector(rec[2]), items))
    rows = [
        dict(county=county, category=kind, **inspection)
        for (county, kind, _), inspection in zip(items, inspections)
    ]
    return {
        "sources": rows,
        "sourceCount": len(rows),
        "knownBytes": sum(r["bytes"] or 0 for r in rows),
        "unknownSizeCount": sum(r["bytes"] is None for r in rows),
        "status": "READ-ONLY SOURCE PROBE; NO IMAGERY COPIED OR PERMISSION GRANTED",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-index-json", required=True, type=Path)
    p.add_argument("--output-json", required=True, type=Path)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Never overwrite a previous provenance probe")
    report = probe(json.loads(a.official_index_json.read_text()))
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"sources": report["sourceCount"],
                      "sizeKnown": report["sourceCount"] -
                          report["unknownSizeCount"],
                      "status": report["status"]}))
