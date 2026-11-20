#!/usr/bin/env python3
"""Read official KyTopo quad polygons and direct original COG metadata for Gorge.

No imagery downloads, no map rendering or protected catalog operations.
An index polygon is not evidence of valid TIFF pixels or reuse permission.
"""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlencode, urlparse, unquote, quote
from urllib.request import Request, urlopen

SERVICE = ("https://kygisserver.ky.gov/arcgis/rest/services/"
           "WGS84WM_Services/Ky_KyTopo_Quad_Index_Grid/MapServer/0/query")
COG_HOST = "kyfromabove.s3.us-west-2.amazonaws.com"
PREFIX = "/elevation/KyTopoMapSeries/"
BBOX = [-83.80, 37.65, -83.40, 37.95]
MAX_REPLY = 1_500_000


def request(bounds, opener=urlopen):
    geometry = {"xmin": bounds[0], "ymin": bounds[1],
                "xmax": bounds[2], "ymax": bounds[3],
                "spatialReference": {"wkid": 4326}}
    query = {
        "f": "json", "where": "1=1",
        "geometry": json.dumps(geometry, separators=(",", ":")),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "Name,QuadName,AWS_COG_url",
        "returnGeometry": "true", "resultRecordCount": "100",
    }
    url = SERVICE + "?" + urlencode(query)
    with opener(Request(url, headers={"Accept": "application/json",
                                       "User-Agent": "RRGH-KyTopo-AOI-metadata/1.0"}),
                timeout=20) as response:
        returned = urlparse(response.geturl())
        if (returned.scheme != "https" or
                returned.hostname != "kygisserver.ky.gov" or
                returned.path != urlparse(SERVICE).path):
            raise ValueError("KyTopo service redirected outside official index")
        data = response.read(MAX_REPLY + 1)
    if len(data) > MAX_REPLY:
        raise ValueError("Excessive map quadrangle metadata response")
    return json.loads(data)


def source_key(raw):
    if not isinstance(raw, str):
        return None
    p = urlparse(raw)
    if (p.scheme != "https" or p.hostname != COG_HOST
            or not p.path.startswith(PREFIX) or
            not p.path.lower().endswith((".tif", ".tiff"))
            or p.query or p.fragment or p.username or p.password):
        return None
    return unquote(p.path.lstrip("/"))


def polygon_bbox(geometry):
    rings = geometry.get("rings") if isinstance(geometry, dict) else None
    if not isinstance(rings, list) or not rings:
        raise ValueError("Official KyTopo feature lacks polygon rings")
    pairs = [pt for ring in rings if isinstance(ring, list)
             for pt in ring if isinstance(pt, list) and len(pt) >= 2]
    if not pairs:
        raise ValueError("Missing source quadrangle vertices")
    if not all(isinstance(v, (float, int)) and math.isfinite(v)
               for pt in pairs for v in pt[:2]):
        raise ValueError("Invalid quadrangle coordinates")
    lon = [v[0] for v in pairs]
    lat = [v[1] for v in pairs]
    if min(lon) < -91 or max(lon) > -81 or min(lat) < 35 or max(lat) > 41:
        raise ValueError("Source quadrangle not expressed as Kentucky WGS84")
    return [min(lon), min(lat), max(lon), max(lat)]


def choose_cog(quad_id, index_url, available):
    """Prefer exact current KyTopo COG key confirmed in official S3 listing.

    Existing index AWS_COG_url can be blank or legacy. Never interpret its
    absence as permission to fabricate a source or use a Phase1 backup.
    """
    supplied = source_key(index_url)
    if available is None:
        return supplied, "index-url-only" if supplied else "unresolved"
    prefix = PREFIX.lstrip("/") + "COGs/KyTopo_24K_" + quad_id + "_"
    candidates = sorted(
        k for k in available if k.startswith(prefix)
        and k.lower().endswith("_cog.tif")
    )
    if len(candidates) == 1:
        return candidates[0], "exact-current-cog-in-official-s3"
    if len(candidates) > 1:
        return None, "ambiguous-current-cogs"
    if supplied in available:
        return supplied, "index-url-confirmed-in-official-s3"
    return None, "missing-current-cog"


def discover(bounds, listing=None, reader=request):
    if (len(bounds) != 4 or not
            (-83.81 <= bounds[0] < bounds[2] <= -83.39 and
             37.64 <= bounds[1] < bounds[3] <= 37.96)):
        raise ValueError("Only bounded Gorge WGS84 query permitted")
    payload = reader(bounds)
    if payload.get("error") or payload.get("exceededTransferLimit"):
        raise ValueError("KyTopo index did not return an exhaustive response")
    features = payload.get("features")
    if not isinstance(features, list) or not 0 < len(features) < 100:
        raise ValueError("No complete bounded official quadrangle selection")
    available = None
    if listing is not None:
        if (listing.get("prefix") != PREFIX.lstrip("/") or
                not listing.get("listingExhausted")):
            raise ValueError("Only complete official KyTopo S3 inventory allowed")
        available = {entry["key"] for entry in listing["originalCOGs"]}
    result = []
    seen = set()
    for feature in features:
        properties = feature.get("attributes")
        if not isinstance(properties, dict):
            raise ValueError("Unexpected KyTopo feature attributes")
        name = properties.get("Name")
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Missing/duplicate KyTopo quadrangle name")
        seen.add(name)
        key, selection = choose_cog(name, properties.get("AWS_COG_url"),
                                    available)
        size = (listing and next((x["sourceFileBytes"]
                                 for x in listing["originalCOGs"]
                                 if x["key"] == key), None)) if key else None
        result.append({
            "id": name, "quadrangle": properties.get("QuadName"),
            "boundsWGS84": polygon_bbox(feature.get("geometry")),
            "officialOriginalCogURL":
                ("https://" + COG_HOST + "/" + quote(key, safe="/"))
                if key else None,
            "officialOriginalSourceBytes": size,
            "sourceSelection": selection,
            "inOfficialS3Listing": key in available if available is not None else None,
        })
    return {
        "status": "OFFICIAL GORGE-INTERSECTING KYTOPO QUAD METADATA ONLY",
        "boundsWGS84": bounds, "count": len(result),
        "withOriginalCOGURL": sum(v["officialOriginalCogURL"] is not None for v in result),
        "allOriginalKeysInS3": (all(v["inOfficialS3Listing"] for v in result)
                                if available is not None else None),
        "quadrangles": sorted(result, key=lambda v: v["id"]),
        "rasterBytesFetched": 0,
        "noFinalCoverageOrXYZSizeClaim": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--official-s3-listing", type=Path)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args()
    if a.output_json.exists():
        raise FileExistsError("Refuse to overwrite prior regional KyTopo source evidence")
    source = (json.loads(a.official_s3_listing.read_text())
              if a.official_s3_listing else None)
    result = discover(BBOX, source)
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"count": result["count"],
                      "withOriginalCOGURL": result["withOriginalCOGURL"],
                      "allOriginalKeysInS3": result["allOriginalKeysInS3"],
                      "quadrangles": [x["id"] for x in result["quadrangles"]]},
                     indent=2))
