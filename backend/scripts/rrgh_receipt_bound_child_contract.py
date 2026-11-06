"""Fail-closed structural binding for cross-wave catalog children.

This is NOT receipt authentication. A trusted caller must independently verify
the protected recovery receipt, plan, catalog and generation-pinned bytes before
using this function for production eligibility. No Cloud access is performed.
"""
import re
from rrgh_verified_tile_catalog import ref, require
from rrgh_protected_cross_wave_reader import checked_child

_PLAN = re.compile(r"engineering/map-production/plans/([0-9a-f]{64})/slots/00001/jobs/([^/]+)\\.json\\Z")


def checked_catalog_child(catalog, tile, read_generation, maximum_object_bytes=256000000):
    """Reject cross-plan/foreign-job child records before immutable byte readback."""
    require(type(catalog) is dict and catalog.get("format") == "rrgh-verified-tile-catalog-v1",
            "Verified catalog format required")
    plan = catalog.get("planSHA256")
    require(type(plan) is str and re.fullmatch(r"[0-9a-f]{64}", plan),
            "Exact immutable plan digest required")
    require(catalog.get("independentPixelsAndHashesVerified") is True and
            catalog.get("nativePackageMembershipVerified") is True and
            catalog.get("deliveryVerified") is False and
            catalog.get("physicalDeviceVerified") is False,
            "Catalog evidence or acceptance flags inconsistent")
    require(type(tile) is dict and type(tile.get("job")) is str,
            "Catalog child job required")
    job_receipt = ref(tile.get("jobReceipt"))
    match = _PLAN.fullmatch(job_receipt["key"])
    require(match is not None and match.group(1) == plan and match.group(2) == tile["job"],
            "Catalog child does not match exact plan and job receipt")
    checkpoint = ref(tile.get("checkpointObject"))
    require(checkpoint["key"].startswith("engineering/map-production/plans/" + plan + "/"),
            "Child checkpoint object belongs to a different plan")
    return checked_child(tile, read_generation, maximum_object_bytes)
