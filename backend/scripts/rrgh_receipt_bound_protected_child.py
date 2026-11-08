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
    import re
    require(type(plan_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", plan_sha256),
            "Exact immutable plan digest required before protected read")
    require(type(tile.get("job")) is str and
            re.fullmatch(r"[A-Za-z0-9_-]{1,128}", tile["job"]),
            "Exact catalog job identity required before protected read")
    trusted = ref(trusted_receipt_ref)
    catalog_ref = ref(tile["jobReceipt"])
    prefix = "engineering/map-production/plans/" + plan_sha256 + "/slots/00001/"
    require(trusted["key"] == prefix + "jobs/" + tile["job"] + ".json",
            "Independent receipt pin is outside exact plan/job slot")
    require(ref(tile["checkpointObject"])["key"].startswith(prefix),
            "Catalog child object is outside exact plan slot")
    require(trusted == catalog_ref, "Catalog receipt differs from independent pin")
    raw = checked_object(trusted, read_generation, maximum_object_bytes)
    def reject_duplicate_fields(pairs):
        fields = {}
        for name, value in pairs:
            require(name not in fields, "Duplicate authenticated receipt JSON field")
            fields[name] = value
        return fields

    try:
        record = json.loads(raw, object_pairs_hook=reject_duplicate_fields)
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
            require(type(member) is dict and type(member.get("offset")) is int and
                    member["offset"] >= 0 and type(member.get("bytes")) is int and
                    0 < member["bytes"] <= 512 * 1024 and
                    member["offset"] + member["bytes"] <= pack_ref["bytes"],
                    "Invalid authenticated member range")
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
