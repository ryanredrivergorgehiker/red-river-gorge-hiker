"""Fail-closed, read-only cross-wave overview eligibility prefilter.

Inputs are independently recovered rrgh-verified-tile-catalog-v1 records.
This is NOT an allocation, a publisher, or an authorization to render.
The caller must independently validate each catalog's protected immutable
recovery receipt and byte-read the children before rendering.
"""
import re
from rrgh_verified_tile_catalog import ref, require, TILE

def eligible_parents(catalogs, required_children, required_parents):
    """Return only interior four-child parents; reject ambiguous evidence.

    required_children and required_parents are exact (layer,z,x,y) sets
    from the pinned geographic manifest, not inferred bbox overlap.
    """
    require(type(catalogs) is list and catalogs, "Catalog evidence required")
    require(type(required_children) is set and type(required_parents) is set,
            "Pinned exact XYZ requirement sets required")
    by_tile = {}
    for catalog in catalogs:
        require(catalog.get("format") == "rrgh-verified-tile-catalog-v1"
                and catalog.get("independentPixelsAndHashesVerified") is True
                and catalog.get("nativePackageMembershipVerified") is True
                and catalog.get("fullRegionalCoverageClaimed") is False,
                "Protected independently verified catalog required")
        require(type(catalog.get("sequence")) is int and catalog["sequence"] > 0
                and type(catalog.get("planSHA256")) is str
                and re.fullmatch(r"[0-9a-f]{64}", catalog["planSHA256"]) is not None,
                "Missing immutable catalog lineage")
        tiles = catalog.get("tiles")
        require(type(tiles) is list and len(tiles) == catalog.get("tileCount"),
                "Incomplete catalog tile count")
        for tile in tiles:
            identity = tile.get("tile")
            require(type(identity) is list and len(identity) == 4
                    and type(identity[0]) is str
                    and all(type(v) is int for v in identity[1:])
                    and 0 <= identity[1] <= 18
                    and all(0 <= v < 2**identity[1] for v in identity[2:]),
                    "Invalid XYZ identity")
            key = tuple(identity)
            require(key not in by_tile, "Duplicate or replayed tile identity")
            require(tile.get("pixelReadbackVerified") is True,
                    "Child lacks independent pixel verification")
            match = TILE.fullmatch(tile.get("path", ""))
            require(match is not None and
                    (match[1], int(match[2]), int(match[3]), int(match[4])) == key,
                    "Tile path/identity mismatch")
            ref(tile["jobReceipt"]); ref(tile["checkpointObject"])
            package = tile.get("package")
            require(type(package) is dict and package.get("memberPath") == tile["path"]
                    and type(package.get("chunks")) is list and package["chunks"],
                    "Native package membership missing")
            for chunk in package["chunks"]:
                ref(chunk["ref"])
            require(type(tile.get("checkpointOffset")) is int
                    and tile["checkpointOffset"] >= 0
                    and type(tile.get("bytes")) is int and tile["bytes"] > 0
                    and tile["checkpointOffset"] + tile["bytes"] <=
                    tile["checkpointObject"]["bytes"],
                    "Invalid immutable child byte range")
            by_tile[key] = tile
    result = []
    for layer, z, x, y in sorted(required_parents):
        require(layer in ("hiking", "terrain", "leaf-on", "leaf-off")
                and type(z) is int and 10 <= z <= 15
                and all(type(v) is int and 0 <= v < 2**z for v in (x, y)),
                "Unsupported parent/boundary policy")
        children = [(layer, z+1, 2*x+dx, 2*y+dy)
                    for dx in range(2) for dy in range(2)]
        # Missing boundary children cannot be silently synthesized.
        if not all(child in required_children for child in children):
            continue
        if not all(child in by_tile for child in children):
            continue
        result.append(dict(parent=[layer,z,x,y],
                           children=[by_tile[c] for c in children],
                           productionAccepted=False,
                           independentByteReadbackStillRequired=True))
    return result
