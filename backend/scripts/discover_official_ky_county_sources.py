#!/usr/bin/env python3
"""Discover OFFICIAL Kentucky county offline map-package URLs for RRG bounds.

Metadata-only ArcGIS REST query; downloads no imagery and grants no license.
Review county source/attribution before passing files to the TPKX importer.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

SERVICE = (
    "https://kygisserver.ky.gov/arcgis/rest/services/"
    "WGS84WM_Services/Ky_County_TilePackages_WGS84WM/MapServer/0/query"
)
FIELDS = [
    "County", "TCM_TKPX_Name", "TCM_Download_URL",
    "KyFromAboveImagery_TPKX_Name", "KyFromAbove_Download_URL",
]


def parse_records(payload):
    if payload.get("error"):
        raise ValueError("Official GIS service returned an error")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Official county query returned no intersecting features")
    output = []
    for feature in features:
        attributes = feature.get("attributes") or {}
        county = attributes.get("County")
        if not county or not isinstance(county, str):
            raise ValueError("County metadata is incomplete")
        output.append({
            "county": county,
            "topoPackage": attributes.get("TCM_TKPX_Name"),
            "topoDownloadURL": attributes.get("TCM_Download_URL"),
            "aerialPackage": attributes.get("KyFromAboveImagery_TPKX_Name"),
            "aerialDownloadURL": attributes.get("KyFromAbove_Download_URL"),
            "usage": "REFERENCE ONLY; verify package provenance and offline redistribution",
        })
    return sorted(output, key=lambda item: item["county"])


def discover(bounds, response=None):
    if not (len(bounds) == 4 and -180 < bounds[0] < bounds[2] < 180 and
            -85 < bounds[1] < bounds[3] < 85):
        raise ValueError("Invalid WGS84 Gorge rectangle")
    params = {
        "f": "json", "where": "1=1",
        "geometry": json.dumps({
            "xmin": bounds[0], "ymin": bounds[1],
            "xmax": bounds[2], "ymax": bounds[3],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": 4326,
        "outFields": ",".join(FIELDS),
        "returnGeometry": "false",
    }
    url = SERVICE + "?" + urlencode(params)
    if response is None:
        with urlopen(url, timeout=25) as stream:
            response = json.load(stream)
    return {
        "officialMetadataURL": url,
        "bboxWGS84": bounds,
        "records": parse_records(response),
        "reviewStatus": "NOT APPROVED OR DOWNLOADED",
    }


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--bbox", type=float, nargs=4,
                   default=[-83.80, 37.65, -83.40, 37.95])
    a.add_argument("--output-json", required=True, type=Path)
    a.add_argument("--offline-response-json", type=Path,
                   help="Optional local ArcGIS JSON for network-free verification")
    args = a.parse_args()
    if args.output_json.exists():
        raise FileExistsError("Refusing to overwrite original discovery report")
    payload = (json.loads(args.offline_response_json.read_text())
               if args.offline_response_json else None)
    report = discover(args.bbox, payload)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"counties": [v["county"] for v in report["records"]],
                      "result": report["reviewStatus"]}, indent=2))
