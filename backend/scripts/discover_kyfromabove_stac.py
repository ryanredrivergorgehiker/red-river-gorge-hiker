#!/usr/bin/env python3
"""Bounded, metadata-only KyFromAbove STAC discovery for Gorge Base v4.

Search official Kentucky public-domain DEM and leaf-off ortho COG assets.
NO pixel reads, whole-county archives, catalog upload, account tokens or
package signing. This is evidence inventory, never proof of closed coverage
or permission to pretend a new layer (especially leaf-ON imagery) exists.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com"
MAX_RESPONSE_BYTES = 2_000_000
MAX_COLLECTIONS = 2
MAX_ITEMS_PER_COLLECTION = 3
GORGE_BOUNDS = (-83.80, 37.65, -83.40, 37.95)


def valid_bbox(b):
    if not isinstance(b, (list, tuple)) or len(b) != 4:
        return False
    try:
        west, south, east, north = map(float, b)
    except (ValueError, TypeError):
        return False
    return (-83.81 <= west < east <= -83.39 and
            37.64 <= south < north <= 37.96)


def intersects(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def fetch_json(path, params=None, opener=urlopen):
    if not path.startswith("/") or "//" in path:
        raise ValueError("STAC path must be rooted and not external")
    uri = API + path + ("?" + urlencode(params) if params else "")
    req = Request(uri, headers={
        "Accept": "application/geo+json, application/json",
        "User-Agent": "RRGH-private-source-metadata/1.0",
    })
    with opener(req, timeout=18) as response:
        if urlparse(response.geturl()).netloc != urlparse(API).netloc:
            raise ValueError("STAC redirect outside official endpoint")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("STAC metadata response exceeds bounded limit")
    return json.loads(data)


def source_kind(entry):
    text = (str(entry.get("id", "")) + " " + str(entry.get("title", "")) +
            " " + str(entry.get("description", ""))).lower()
    if any(v in text for v in ("point cloud", "pointcloud", "copc", "laz")):
        return None
    if "dem" in text or "digital elevation model" in text:
        return "terrain-dem-candidate"
    if ("ortho" in text or "nadir" in text) and "imag" in text:
        return "leaf-off-ortho-candidate"
    return None


def collections(payload):
    # STAC lists Phase1 before newer sources. Phase1 orthos do NOT provide
    # statewide Gorge coverage; Phase2 is complete, while higher-resolution
    # Phase3 is preferred where actually available. Avoid blind first-match.
    candidate = {}
    for item in payload.get("collections", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        kind = source_kind(item)
        if not kind:
            continue
        ident = item["id"].lower().replace("-", "").replace("_", "")
        if kind == "terrain-dem-candidate":
            priority = (3 if "phase2" in ident else
                        2 if "phase3" in ident else 1)
        else:
            priority = (3 if "phase3" in ident else
                        2 if "phase2" in ident else 1)
        candidate.setdefault(kind, []).append((priority, item["id"]))
    selected = []
    for kind in ("terrain-dem-candidate", "leaf-off-ortho-candidate"):
        if kind in candidate:
            best = sorted(candidate[kind], key=lambda x: (-x[0], x[1]))[0]
            selected.append((kind, best[1]))
    return selected[:MAX_COLLECTIONS]


def public_asset(href):
    if not isinstance(href, str):
        return False
    if href.startswith("s3://kyfromabove/"):
        return True
    parsed = urlparse(href)
    return parsed.scheme == "https" and (
        parsed.hostname == "kyfromabove.s3.us-west-2.amazonaws.com" or
        (parsed.hostname == "s3.us-west-2.amazonaws.com" and
         parsed.path.startswith("/kyfromabove/"))
    )


def summarise_item(item, kind, bounds):
    if item.get("type") != "Feature" or not isinstance(item.get("id"), str):
        return None
    tile_bbox = item.get("bbox")
    if (not isinstance(tile_bbox, list) or len(tile_bbox) != 4 or
            not all(isinstance(v, (int, float)) for v in tile_bbox) or
            not intersects(tile_bbox, bounds)):
        return None
    sources = []
    for asset_name, asset in (item.get("assets") or {}).items():
        if not isinstance(asset, dict):
            continue
        href = asset.get("href")
        if not public_asset(href):
            continue
        if not urlparse(href).path.lower().endswith((".tif", ".tiff", ".cog")):
            continue
        sources.append({"name": str(asset_name), "href": href,
                        "type": asset.get("type"),
                        "roles": asset.get("roles", [])})
    return {
        "collection": item.get("collection"), "itemID": item["id"],
        "kind": kind, "bbox": tile_bbox, "assets": sources,
        "assetAvailability": "CANDIDATE ONLY, NO TIFF RANGE VALIDATION",
    }


def discover(bounds, reader=fetch_json):
    if not valid_bbox(bounds):
        raise ValueError("Only bounded Gorge metadata searches permitted")
    meta = reader("/collections")
    selected = collections(meta)
    if not selected:
        raise ValueError("No recognized Kentucky DEM or orthophoto collections")
    result = []
    for kind, collection in selected:
        response = reader("/search", {
            "bbox": ",".join(str(v) for v in bounds),
            "collections": collection, "limit": MAX_ITEMS_PER_COLLECTION,
        })
        if response.get("type") != "FeatureCollection":
            raise ValueError("Invalid STAC search result")
        features = response.get("features")
        if not isinstance(features, list) or len(features) > MAX_ITEMS_PER_COLLECTION:
            raise ValueError("STAC metadata exceeds bounded item count")
        candidates = [summarise_item(f, kind, bounds) for f in features]
        result.append({
            "collection": collection, "kind": kind,
            "reportedItems": len(features),
            "candidates": [c for c in candidates if c is not None],
            "paginationExhausted": False,
        })
    return {
        "publisher": "Kentucky Division of Geographic Information",
        "catalog": API,
        "boundsWGS84": list(bounds),
        "status": "METADATA ONLY — NOT COMPLETE COVERAGE OR FIELD MAP SOURCE",
        "publicDomainWithAttribution": "Verify per-asset source conditions",
        "noImageryDownloaded": True,
        "layerRolesNotEstablished": [
            "kentucky-topo", "usgs-topo", "terrain-relief",
            "leaf-on-aerial", "leaf-off-aerial",
        ],
        "results": result,
        "next": "Inspect candidate COG resolution/rights/coverage with STRICT bounded range reads.",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bbox", nargs=4, type=float,
                   default=list(GORGE_BOUNDS))
    p.add_argument("--output-json", required=True, type=Path)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Do not overwrite previous intake evidence")
    result = discover(a.bbox)
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "status": result["status"],
        "collections": [x["collection"] for x in result["results"]],
        "items": sum(x["reportedItems"] for x in result["results"]),
    }, indent=2))
