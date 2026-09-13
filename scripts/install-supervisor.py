#!/usr/bin/env python3
"""Install supervisor instructions and stdlib helpers. Dry run unless hash approved.

No dependencies, accounts, permissions, models or global runtime are modified.
Existing destinations are never overwritten. Incomplete output is retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--approve-plan")
    args = parser.parse_args()
    target = args.target.expanduser().absolute()
    try:
        for part in (target, *target.parents):
            if part.is_symlink():
                raise ValueError("SYMLINK_TARGET: supply an explicit physical path")
        if target.exists():
            raise ValueError("TARGET_EXISTS: no files overwritten")
        if not target.parent.is_dir():
            raise ValueError("PARENT_MISSING: select an existing authorized directory")
        root = Path(__file__).resolve().parents[1]
        mapping = {"SKILL.md": root / "cortex-supervisor/SKILL.md",
                   "references/HARNESS_V065.md": root / "HARNESS_V065.md",
                   "scripts/supervisor-journal.py": root / "scripts/supervisor-journal.py",
                   "scripts/supervisor-artifacts.py": root / "scripts/supervisor-artifacts.py",
                   "scripts/supervisor-lifecycle.py": root / "scripts/supervisor-lifecycle.py"}
        for name in ("__init__.py", "protocol.py", "state.py", "store.py", "native_journal.py", "artifacts.py", "context.py"):
            mapping["scripts/lib/orchestration/" + name] = root / "orchestration" / name
        frozen = {}
        for name, source in mapping.items():
            if source.is_symlink() or not source.is_file():
                raise ValueError("INVALID_SOURCE")
            frozen[name] = source.read_bytes()
        plan = {"protocol": "cortex-supervisor-install.v1", "target": str(target),
                "scope": "instructions-local-helpers-and-lifecycle", "receipt_file": ".cortex-install.json", "files": [
                    {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                    for name, data in sorted(frozen.items())]}
        plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if args.approve_plan is None:
            print(json.dumps({"state": "planned", "plan_hash": plan_hash, "plan": plan}))
            return 0
        if args.approve_plan != plan_hash:
            raise ValueError("PLAN_CHANGED_OR_NOT_APPROVED")
        target.mkdir(exist_ok=False)
        for name, data in frozen.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            with (target / name).open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if (target / name).read_bytes() != data:
                raise ValueError("VERIFY_FAILED: partial installation retained")
        with (target / ".cortex-install.json").open("x") as handle:
            json.dump({"plan_hash": plan_hash, "plan": plan}, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps({"state": "installed", "plan_hash": plan_hash, "plan": plan,
                          "capabilities_verified": False,
                          "next": "Reload skill discovery, then probe actual host tools"}))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"state": "failed", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
