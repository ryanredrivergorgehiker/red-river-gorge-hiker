"""Isolated authenticated-evidence boundary for cross-wave protected children.

A caller must obtain the receipt reference from an INDEPENDENTLY trusted
immutable manifest, not from the tile catalog being checked. This module does
not establish that trust, acquire Cloud credentials, or authorize production.
"""
import json
from rrgh_verified_tile_catalog import ref, require
from rrgh_protected_cross_wave_reader import checked_object, checked_plan_bound_child


def checked_receipt_bound_child(tile, plan_sha256, trusted_receipt_ref,
                                read_generation, maximum_object_bytes=256000000):
    """Require a separately pinned receipt to bind job, plan, pack and child."""
    require(type(tile) is dict, "Child record required")
    trusted = ref(trusted_receipt_ref)
    catalog_ref = ref(tile["jobReceipt"])
    require(trusted == catalog_ref, "Catalog receipt differs from independent pin")
    raw = checked_object(trusted, read_generation, maximum_object_bytes)
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid authenticated job receipt JSON") from exc
    require(type(record) is dict and
            record.get("format") == "rrgh-checkpoint-job-v1" and
            record.get("planSHA256") == plan_sha256 and
            record.get("slot") == 1 and
            record.get("job") == tile.get("job"),
            "Authenticated receipt identity differs")
    result = record.get("result")
    require(type(result) is dict and type(result.get("outputPacks")) is list,
            "Authenticated output pack evidence missing")
    found = []
    for pack in result["outputPacks"]:
        require(type(pack) is dict and type(pack.get("members")) is list,
                "Invalid authenticated output pack")
        pack_ref = ref(pack["ref"])
        for member in pack["members"]:
            require(type(member) is dict, "Invalid authenticated member")
            if member.get("path") == tile.get("path"):
                found.append((pack_ref, member))
    require(len(found) == 1, "Child must occur exactly once in authenticated receipt")
    pack_ref, member = found[0]
    require(pack_ref == ref(tile["checkpointObject"]) and
            member.get("offset") == tile.get("checkpointOffset") and
            member.get("bytes") == tile.get("bytes") and
            member.get("sha256") == tile.get("sha256"),
            "Authenticated receipt child evidence differs")
    return checked_plan_bound_child(tile, plan_sha256, read_generation,
                                    maximum_object_bytes)
