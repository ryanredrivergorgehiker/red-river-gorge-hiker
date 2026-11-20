#!/usr/bin/env python3
"""Enumerate only metadata for Kentucky Phase2 DEM/Phase3 leaf-off COG coverage.

Finite official-STAC pages, finite item/result budget, fixed Gorge bounds.
DOES NOT download pixels, certify all imagery, or alter a customer package.
The bbox sample grid is an approximate gap diagnostic, not final XYZ coverage.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from discover_kyfromabove_stac import API, valid_bbox, public_asset, intersects

PAGE_LIMIT = 100
MAX_PAGES = 12
MAX_PAGE_BYTES = 2_000_000
MAX_RECORDS = PAGE_LIMIT * MAX_PAGES


def official_search_url(uri):
    p = urlparse(uri)
    return (p.scheme == "https" and p.hostname ==
            urlparse(API).hostname and p.path == "/search" and
            not p.fragment and not p.username and not p.password and
            p.port is None and 0 < len(p.query) < 4096)


def fetch(uri, opener=urlopen):
    if not official_search_url(uri):
        raise ValueError("Only official bounded Kentucky STAC pagination URLs")
    req = Request(uri, headers={
        "Accept": "application/geo+json, application/json",
        "User-Agent": "RRGH-Kentucky-Gorge-metadata-coverage/1.0",
    })
    with opener(req, timeout=18) as response:
        if not official_search_url(response.geturl()):
            raise ValueError("Official STAC redirected outside allowlist")
        raw = response.read(MAX_PAGE_BYTES + 1)
    if len(raw) > MAX_PAGE_BYTES:
        raise ValueError("Oversized public source metadata page")
    return json.loads(raw)


def next_page(payload):
    links = [v for v in payload.get("links", [])
             if isinstance(v, dict) and v.get("rel") == "next"]
    if not links:
        return None
    if len(links) != 1:
        raise ValueError("Ambiguous STAC continuation")
    item = links[0]
    if item.get("method", "GET").upper() != "GET" or item.get("body"):
        raise ValueError("STAC pagination requires unsupported POST continuation")
    uri = item.get("href")
    if not official_search_url(uri):
        raise ValueError("STAC continuation escaped official search endpoint")
    return uri


def grid_score(bounds, boxes, cols=40, rows=30):
    if not boxes:
        return {"samples": cols*rows, "covered": 0, "fraction": 0.0,
                "exactClosedXYZProof": False}
    hits = 0
    for ix in range(cols):
        lon = bounds[0] + (ix + 0.5) * (bounds[2]-bounds[0]) / cols
        for iy in range(rows):
            lat = bounds[1] + (iy + 0.5) * (bounds[3]-bounds[1]) / rows
            if any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3]
                   for b in boxes):
                hits += 1
    return {"samples": cols*rows, "covered": hits,
            "fraction": round(hits/(cols*rows), 6),
            "exactClosedXYZProof": False}


def inventory(first_report, reader=fetch):
    bounds = first_report.get("boundsWGS84")
    if not valid_bbox(bounds) or first_report.get("catalog") != API:
        raise ValueError("Input must be official Gorge-bounded STAC metadata")
    groups = first_report.get("results", [])
    if len(groups) > 2:
        raise ValueError("Too many source categories in discovery")
    records = []
    for source in groups:
        kind, collection = source.get("kind"), source.get("collection")
        if (kind not in ("terrain-dem-candidate", "leaf-off-ortho-candidate")
                or not isinstance(collection, str) or len(collection) > 80):
            raise ValueError("Unrecognized Kentucky STAC imagery role")
        params = {
            "bbox": ",".join(str(v) for v in bounds),
            "collections": collection,
            "limit": PAGE_LIMIT,
        }
        uri = API + "/search?" + urlencode(params)
        visited, items, boxes, pages = set(), {}, [], 0
        exhausted, failure = False, None
        while uri:
            if uri in visited:
                raise ValueError("Cyclic official STAC pagination")
            if pages >= MAX_PAGES:
                failure = "PAGE_BUDGET_LIMIT — NOT VERIFIED COMPLETE"
                break
            visited.add(uri)
            payload = reader(uri)
            if payload.get("type") != "FeatureCollection":
                raise ValueError("Bad STAC FeatureCollection")
            features = payload.get("features")
            if not isinstance(features, list) or len(features) > PAGE_LIMIT:
                raise ValueError("STAC exceeded accepted per-page bounds")
            for feature in features:
                bbox = feature.get("bbox")
                item_id = feature.get("id")
                if (feature.get("type") != "Feature" or
                        not isinstance(item_id, str) or not isinstance(bbox, list)
                        or len(bbox) != 4 or
                        not all(isinstance(v, (int, float)) for v in bbox)
                        or not intersects(bbox, bounds)):
                    continue
                approved = sorted({
                    asset["href"]
                    for asset in (feature.get("assets") or {}).values()
                    if isinstance(asset, dict) and
                    public_asset(asset.get("href")) and
                    urlparse(asset["href"]).path.lower().endswith((".tif", ".tiff"))
                })
                if not approved:
                    continue
                item = {"id": item_id, "bbox": bbox, "officialCogURL": approved[0]}
                if item_id in items and items[item_id] != item:
                    raise ValueError("Duplicate STAC item contradicts source geometry")
                items[item_id] = item
                if len(items) > MAX_RECORDS:
                    raise ValueError("STAC metadata item budget exceeded")
            pages += 1
            uri = next_page(payload)
            if uri is None:
                exhausted = True
        for item in items.values():
            boxes.append(item["bbox"])
        records.append({
            "kind": kind, "collection": collection, "pages": pages,
            "count": len(items), "paginationExhausted": exhausted,
            "stoppedReason": failure,
            "approximateSpatialSample": grid_score(bounds, boxes),
            "sourceFiles": sorted(items.values(), key=lambda i: i["id"]),
        })
    return {
        "status": "OFFICIAL STAC FULL-EXTENT METADATA INTAKE — NOT IMAGE/XYZ COVERAGE PROOF",
        "source": API, "boundsWGS84": bounds,
        "noOriginalPixelDataDownloaded": True,
        "records": records,
        "requires": "Exact GeoTIFF coverage, source rights, derived XYZ pixel validation and 1.5 GB package checks",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initial-stac", type=Path, required=True)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Never replace prior metadata source record")
    result = inventory(json.loads(a.initial_stac.read_text()))
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "groups": [{
            "kind": v["kind"], "count": v["count"], "pages": v["pages"],
            "exhausted": v["paginationExhausted"],
            "approxCoverage": v["approximateSpatialSample"]["fraction"]
        } for v in result["records"]]
    }, indent=2))
