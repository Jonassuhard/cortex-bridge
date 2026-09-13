#!/usr/bin/env python3
"""Review then archive an owned skill, optionally activating a prepared replacement.

No deletion, downloads, account changes or dependency installation. Cooperative
single-writer operation, not a hostile-writer sandbox or atomic two-rename swap.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

RECEIPT = ".cortex-install.json"


def physical(path):
    path = path.expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SYMLINK_PATH")
    return path


def inventory(path):
    if not path.is_dir():
        raise ValueError("INSTALLATION_MISSING")
    receipt_path = path / RECEIPT
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 100_000:
        raise ValueError("OWNERSHIP_RECEIPT_MISSING")
    receipt = json.loads(receipt_path.read_text())
    plan = receipt["plan"]
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != receipt["plan_hash"] or plan["protocol"] != "cortex-supervisor-install.v1":
        raise ValueError("INVALID_OWNERSHIP_RECEIPT")
    expected = {}
    for item in plan["files"]:
        name = item["path"]
        parts = PurePosixPath(name)
        if not isinstance(name, str) or parts.is_absolute() or ".." in parts.parts or "\\" in name or str(parts) != name or name in expected:
            raise ValueError("INVALID_OWNED_PATH")
        expected[name] = item
    if not expected or len(expected) > 100:
        raise ValueError("INVALID_OWNERSHIP_COUNT")
    actual = {}
    for entry in path.rglob("*"):
        if entry.is_symlink():
            raise ValueError("SYMLINK_ENTRY")
        name = entry.relative_to(path).as_posix()
        if entry.is_dir():
            if not any(p.startswith(name + "/") for p in expected):
                raise ValueError("UNOWNED_DIRECTORY")
            continue
        if not entry.is_file() or entry.stat().st_size > 5_000_000:
            raise ValueError("UNSAFE_ENTRY")
        data = entry.read_bytes()
        actual[name] = {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    owned = {k: v for k, v in actual.items() if k != RECEIPT}
    if owned != expected:
        raise ValueError("OWNED_BYTES_CHANGED_OR_UNOWNED_FILES")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--replacement", type=Path)
    parser.add_argument("--recover-activation", action="store_true",
                        help="Review recovery only when target is absent and archive/replacement are intact")
    parser.add_argument("--approve-plan")
    args = parser.parse_args()
    phase = "preflight"
    try:
        skills, target, archive = map(physical, (args.skills_root, args.target, args.archive))
        replacement = physical(args.replacement) if args.replacement else None
        if target.parent != skills or not skills.is_dir():
            raise ValueError("TARGET_MUST_BE_DIRECT_SKILL_CHILD")
        for external in (archive, replacement):
            if external is not None and (external == skills or skills in external.parents or external in skills.parents):
                raise ValueError("ARCHIVE_AND_REPLACEMENT_MUST_BE_OUTSIDE_DISCOVERY")
        if args.recover_activation:
            if target.exists() or replacement is None or not archive.is_dir():
                raise ValueError("RECOVERY_REQUIRES_ABSENT_TARGET_AND_INTACT_COPIES")
        elif archive.exists() or not archive.parent.is_dir():
            raise ValueError("ARCHIVE_NOT_NEW_OR_PARENT_MISSING")
        if replacement and (replacement == archive or replacement in archive.parents or archive in replacement.parents):
            raise ValueError("OVERLAPPING_PATHS")
        old = inventory(archive if args.recover_activation else target)
        new = inventory(replacement) if replacement else None
        if any(p.stat().st_dev != skills.stat().st_dev for p in (archive.parent, replacement or target)):
            raise ValueError("SAME_FILESYSTEM_REQUIRED")
        operation = "recover-activation" if args.recover_activation else ("update" if replacement else "uninstall-archive")
        plan = {"protocol": "cortex-supervisor-lifecycle.v1", "operation": operation,
                "target": str(target), "archive": str(archive), "replacement": str(replacement) if replacement else None,
                "old_files": old, "new_files": new, "deletes_files": False}
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if args.approve_plan is None:
            print(json.dumps({"state": "planned", "plan_hash": digest, "plan": plan}))
            return 0
        if args.approve_plan != digest:
            raise ValueError("PLAN_CHANGED_OR_NOT_APPROVED")
        # The caller must stop users/writers first. All errors preserve bytes.
        if not args.recover_activation:
            if archive.exists():
                raise ValueError("ARCHIVE_EXISTS")
            os.rename(target, archive)
        phase = "old_archived"
        if inventory(archive) != old:
            raise ValueError("ARCHIVE_VERIFICATION_FAILED")
        if replacement:
            if target.exists() or inventory(replacement) != new:
                raise ValueError("ACTIVATION_CHANGED")
            os.rename(replacement, target)
            phase = "replacement_activated"
            if inventory(target) != new:
                raise ValueError("ACTIVATION_VERIFICATION_FAILED")
        print(json.dumps({"state": "updated" if replacement else "archived", "plan": plan,
                          "plan_hash": digest, "discovery_reload_required": True}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"state": "failed", "phase": phase, "error": str(exc),
                          "recovery": "Inspect paths; all remaining bytes are retained. Do not retry blindly."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
