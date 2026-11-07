"""Isolated fail-closed protected-object readback contract for cross-wave work.

This module does not acquire Cloud credentials, allocate work, or grant trust to
catalog flags. The injected read_generation callback MUST be an authenticated,
generation-pinned protected-object reader. Until that caller is reviewed and
wired, this is NOT a production acceptance path.
"""
import hashlib
from rrgh_verified_tile_catalog import ref, require


def checked_object(reference, read_generation, limit):
    """Read an immutable protected object and verify exact generation/bytes/hash.

    read_generation(key, generation, maximum_bytes) must fail closed on absent
    generation, unauthenticated reads, redirects, and size-limit violations.
    """
    r = ref(reference)
    require(type(limit) is int and 0 < limit <= 256000000, "Positive bounded read ceiling required")
    require(callable(read_generation), "Authenticated generation-pinned reader required")
    require(r["bytes"] <= limit, "Protected object exceeds bounded read limit")
    data = read_generation(r["key"], r["generation"], limit)
    require(type(data) is bytes and len(data) == r["bytes"],
            "Protected generation byte count mismatch")
    require(hashlib.sha256(data).hexdigest() == r["sha256"],
            "Protected generation SHA256 mismatch")
    return data


def checked_child(tile, read_generation, maximum_object_bytes=256000000):
    """Re-read an independently cataloged child from its exact checkpoint object.

    Does not assert independent receipt authenticity or native package acceptance.
    Those must be established separately before eligibility or rendering.
    """
    require(type(tile) is dict, "Child record required")
    object_ref = ref(tile["checkpointObject"])
    offset, size = tile["checkpointOffset"], tile["bytes"]
    require(type(offset) is int and offset >= 0 and type(size) is int
            and 0 < size <= 512 * 1024 and offset + size <= object_ref["bytes"],
            "Invalid checkpoint child byte range")
    require(tile.get("pixelReadbackVerified") is True,
            "Catalog independent pixel verification missing")
    raw = checked_object(object_ref, read_generation, maximum_object_bytes)
    child = raw[offset:offset + size]
    require(hashlib.sha256(child).hexdigest() == tile["sha256"],
            "Independent child hash mismatch")
    return child


def checked_plan_bound_child(tile, plan_sha256, read_generation,
                             maximum_object_bytes=256000000):
    """Fail closed on cross-plan catalog/job lineage before any protected read.

    Structural binding only: the caller must independently authenticate the
    catalog and receipt and supply an authenticated generation-pinned reader.
    """
    import re
    require(type(plan_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", plan_sha256),
            "Exact immutable plan digest required")
    require(type(tile) is dict and type(tile.get("job")) is str and
            re.fullmatch(r"[A-Za-z0-9_-]{1,128}", tile["job"]),
            "Exact catalog job identity required")
    receipt = ref(tile["jobReceipt"])
    obj = ref(tile["checkpointObject"])
    prefix = "engineering/map-production/plans/" + plan_sha256 + "/"
    require(receipt["key"] == prefix + "slots/00001/jobs/" + tile["job"] + ".json",
            "Catalog job receipt does not belong to exact plan")
    require(obj["key"].startswith(prefix + "slots/00001/"),
            "Catalog child object does not belong to exact plan checkpoint")
    return checked_child(tile, read_generation, maximum_object_bytes)
