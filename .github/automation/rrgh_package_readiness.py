#!/usr/bin/env python3
"""Read-only release gate for exact package membership and verified bytes.

The input is a normalized private package evidence record, not a replacement for
the native app's signed index or entitlement contract. This gate deliberately
cannot promote reconstructed historical tiles with missing per-tile hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3

from rrgh_required_inventory import canonical, sha, require


def check_file(root, entry):
    name = entry.get("path", "")
    relative = PurePosixPath(name)
    require(name and not relative.is_absolute() and ".." not in relative.parts and
            "\\" not in name and str(relative) == name, "Unsafe package member path")
    target = root.joinpath(*relative.parts)
    require(all(not root.joinpath(*relative.parts[:i]).is_symlink()
                for i in range(1, len(relative.parts)+1)), "Symlink package member")
    require(target.is_file() and target.resolve().is_relative_to(root.resolve()), "Missing package member")
    require(type(entry.get("bytes")) is int and entry["bytes"] > 0 and
            target.stat().st_size == entry["bytes"], "Package member size mismatch")
    h = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    require(h.hexdigest() == entry.get("sha256"), "Package member hash mismatch")


def assess(db, package, root):
    meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM metadata")}
    require(package.get("format") == "rrgh-package-evidence-v1", "Unknown package evidence format")
    require(bool(package.get("packageID")) and bool(package.get("version")), "Exact package version required")
    group = package.get("group")
    require(group in ("core", "leaf-on", "leaf-off"), "Unknown download group")
    require(package.get("requiredManifestSHA256") == meta["requiredManifestSHA256"], "Wrong required manifest")
    required = {tuple(r) for r in db.execute("SELECT layer,z,x,y FROM required WHERE download_group=?", (group,))}
    accepted = {tuple(r[:4]): r[4:] for r in db.execute("SELECT layer,z,x,y,sha256,bytes,receipt_ref FROM accepted")}
    tiles, paths, errors = set(), set(), []
    for member in package.get("tiles", []):
        tile = tuple(member["tile"])
        require(tile not in tiles and member["path"] not in paths, "Duplicate package tile or path")
        require(tile in required, "Package tile outside exact group/manifest")
        tiles.add(tile)
        paths.add(member["path"])
        record = accepted.get(tile)
        if record is None or record[0] is None or record[1] is None:
            errors.append({"tile": tile, "reason": "missing_tile_byte_verification"})
            continue
        if record[0] != member.get("sha256") or record[1] != member.get("bytes") or not record[2]:
            errors.append({"tile": tile, "reason": "accepted_evidence_mismatch"})
            continue
        try:
            check_file(root, member)
        except ValueError as exc:
            errors.append({"tile": tile, "reason": str(exc)})
    supporting_complete = group != "core"
    if group == "core":
        inventory = package.get("supportingInventory", {})
        groups = set(meta["spec"]["coreSupportingGroups"])
        supporting_complete = (inventory.get("status") == "approved" and
            bool(inventory.get("approvalReference")) and set(inventory.get("groups", {})) == groups)
        listed, supplied = {}, {}
        if supporting_complete:
            for g, members in inventory["groups"].items():
                if not members:
                    supporting_complete = False
                for member in members:
                    require(member["path"] not in listed and member["path"] not in paths,
                            "Duplicate supporting member")
                    listed[member["path"]] = member
            for member in package.get("supportingMembers", []):
                require(member["path"] not in supplied, "Duplicate supplied support file")
                supplied[member["path"]] = member
            supporting_complete = supporting_complete and listed == supplied
            for member in supplied.values():
                if not member.get("verificationReceipt"):
                    supporting_complete = False
                try:
                    check_file(root, member)
                except ValueError:
                    supporting_complete = False
    artifact_sha = package.get("packageSHA256")
    artifact_valid = isinstance(artifact_sha, str) and len(artifact_sha) == 64 and all(c in "0123456789abcdef" for c in artifact_sha)
    try:
        artifact = package.get("artifact", {})
        require(artifact.get("sha256") == artifact_sha, "Wrong package artifact identity")
        check_file(root, artifact)
    except ValueError:
        artifact_valid = False
    delivery = package.get("delivery", {})
    delivered = (artifact_valid and delivery.get("status") == "passed" and
        delivery.get("packageID") == package["packageID"] and delivery.get("version") == package["version"] and
        delivery.get("packageSHA256") == artifact_sha and delivery.get("authenticated") is True and
        bool(delivery.get("evidenceRef")))
    device = package.get("deviceAcceptance", {})
    installed = (delivered and device.get("status") == "passed" and device.get("physicalIPhone") is True and
        device.get("airplaneMode") is True and bool(device.get("appVersion")) and bool(device.get("evidenceRef")) and
        device.get("packageSHA256") == artifact_sha and device.get("packageID") == package["packageID"] and
        device.get("version") == package["version"])
    missing = required - tiles
    raster_complete = not missing and not errors
    complete = raster_complete and supporting_complete and artifact_valid and delivered and installed and meta["scopeStatus"] == "approved"
    return {"format": "rrgh-package-readiness-v1", "packageID": package["packageID"],
        "version": package["version"], "evidenceSHA256": sha(package), "group": group,
        "scopeStatus": meta["scopeStatus"], "requiredRasterTiles": len(required),
        "includedRasterTiles": len(tiles), "missingRasterTiles": len(missing),
        "missingExamples": sorted(missing)[:12], "tileEvidenceErrors": len(errors), "errorExamples": errors[:12],
        "rasterMembershipAndBytesComplete": raster_complete, "supportingAssetsComplete": supporting_complete,
        "packageArtifactBytesVerified": artifact_valid,
        "authenticatedDeliveryPassed": delivered, "physicalIPhoneAcceptancePassed": installed,
        "complete": complete, "productionTriggered": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True, type=Path)
    p.add_argument("--package-evidence", required=True, type=Path)
    p.add_argument("--package-root", required=True, type=Path)
    args = p.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri()+"?mode=ro", uri=True) as db:
        result = assess(db, json.loads(args.package_evidence.read_bytes()), args.package_root)
    print(canonical(result).decode(), end="")
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
