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
    raw = checked_object(object_ref, read_generation, maximum_object_bytes)
    child = raw[offset:offset + size]
    require(hashlib.sha256(child).hexdigest() == tile["sha256"],
            "Independent child hash mismatch")
    require(tile.get("pixelReadbackVerified") is True,
            "Catalog independent pixel verification missing")
    return child
