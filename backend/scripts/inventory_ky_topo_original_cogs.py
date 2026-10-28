#!/usr/bin/env python3
"""Bounded public Kentucky S3 object inventory for original KyTopo map COGs.

Only official S3 ListObjectsV2 XML metadata; never reads GeoTIFF image bytes,
downloads quadrangles, or claims that filenames prove Gorge geographic cover.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

HOST = "kyfromabove.s3.us-west-2.amazonaws.com"
PREFIX = "elevation/KyTopoMapSeries/"
MAX_PAGES = 8
PER_PAGE = 500
MAX_XML_BYTES = 900_000
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def fetch(params, opener=urlopen):
    url = "https://" + HOST + "/?" + urlencode(params)
    req = Request(url, headers={"Accept": "application/xml",
                                "User-Agent": "RRGH-KyTopo-metadata-only/1.0"})
    with opener(req, timeout=20) as response:
        p = urlparse(response.geturl())
        if p.scheme != "https" or p.hostname != HOST:
            raise ValueError("KyTopo metadata redirected outside official AWS host")
        raw = response.read(MAX_XML_BYTES + 1)
    if len(raw) > MAX_XML_BYTES:
        raise ValueError("KyTopo metadata response exceeded finite limit")
    return raw


def inventory(reader=fetch):
    continuation = None
    seen = set()
    entries = []
    finished = False
    for page in range(MAX_PAGES):
        args = {"list-type": "2", "prefix": PREFIX, "max-keys": PER_PAGE}
        if continuation is not None:
            args["continuation-token"] = continuation
        root = ET.fromstring(reader(args))
        if root.tag != "{" + NS["s"] + "}ListBucketResult":
            raise ValueError("Not an official S3 object-list response")
        def field(name):
            return root.findtext("s:" + name, namespaces=NS)
        if field("Prefix") != PREFIX or field("Name") != "kyfromabove":
            raise ValueError("Unexpected bucket or source folder")
        for obj in root.findall("s:Contents", NS):
            key = obj.findtext("s:Key", namespaces=NS)
            size = int(obj.findtext("s:Size", namespaces=NS) or "-1")
            if (not key or not key.startswith(PREFIX) or key in seen
                    or size < 0):
                raise ValueError("Invalid or duplicate KyTopo original object")
            seen.add(key)
            if key.lower().endswith((".tif", ".tiff")):
                entries.append({"key": key, "sourceFileBytes": size})
        truncated = field("IsTruncated") == "true"
        if not truncated:
            finished = True
            break
        continuation = field("NextContinuationToken")
        if not continuation:
            raise ValueError("Truncated official S3 listing lacks cursor")
    cog_bytes = sum(i["sourceFileBytes"] for i in entries)
    return {
        "status": "PUBLIC S3 COG FILE INVENTORY — NO SOURCE PIXELS OR GORGE COVERAGE",
        "source": "Kentucky KyFromAbove original KyTopoMapSeries",
        "bucket": HOST, "prefix": PREFIX,
        "pagesRetrieved": page + 1, "listingExhausted": finished,
        "originalGeoTiffFileCount": len(entries),
        "originalGeoTiffFileBytes": cog_bytes,
        "notAnOfflinePackageSize": True,
        "originalCOGs": entries,
        "missingEvidence": [
            "Exact intersecting quadrangle footprints and geographic CRS",
            "Per-asset original color/detail and partial-read suitability",
            "Actual converted Gorge XYZ per-tile image size and rights",
            "Full source coverage, shared vectors, Sunlight and installed bytes"
        ]
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Never overwrite original metadata inventory")
    r = inventory()
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps({k: r[k] for k in ("status", "pagesRetrieved",
                                        "listingExhausted", "originalGeoTiffFileCount",
                                        "originalGeoTiffFileBytes")}, indent=2))
