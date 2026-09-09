"""Read-only recovery observations; no replay, cleanup or receipt persistence.

Callers must supply a freshly admitted handle for the recorded mission and
exclude live writers before using an observation to terminalize an effect.
"""
import hashlib
import json
import os
import re

from effect_gate import ReconcileResult
from executor import fd_ops
from executor.workspace_handle import WorkspaceHandle


def _identity(value):
    return (type(value) is dict and set(value) == {"device", "inode", "size", "sha256"}
            and all(type(value[k]) is int for k in ("device", "inode", "size"))
            and value["device"] >= 0 and value["inode"] > 0 and value["size"] >= 0
            and type(value["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None)


def _matches(parent, name, expected):
    descriptor = fd_ops.open_regular_at(parent, name)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (
                expected["device"], expected["inode"], expected["size"]):
            return False
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                return False
            digest.update(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            return False
        after = os.fstat(stream.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        named = fd_ops.stat_at(parent, name)
        return (all(getattr(before, key) == getattr(after, key) for key in fields)
                and all(getattr(after, key) == getattr(named, key) for key in fields)
                and digest.hexdigest() == expected["sha256"])


def reconcile_write_effect(handle, effect):
    """Observe only exact mission/filesystem/write_file effects.

    A failed result means the intended final file is currently absent or the
    original remains, not proof that publication never occurred historically.
    Terminal receipts are never overwritten by this function.
    """
    unclear = ReconcileResult("outcome_unclear", "WRITE_RECOVERY_UNCLEAR", {})
    root = None
    try:
        if not isinstance(handle, WorkspaceHandle):
            return unclear
        if (effect["owner_kind"], effect["category"], effect["operation"], effect["state"]) != (
                "mission", "filesystem", "write_file", "active"):
            return unclear
        ownership = json.loads(effect["ownership_json"])
        required = {"path", "temporary", "previous", "prior", "prepared", "expectedSha256",
                    "parentDevice", "parentInode"}
        if type(ownership) is not dict or set(ownership) != required:
            return unclear
        prepared, prior = ownership["prepared"], ownership["prior"]
        temporary = f".cortex-{effect['id']}.tmp"
        previous = f".cortex-{effect['id']}.previous"
        if (not _identity(prepared) or (prior is not None and not _identity(prior))
                or ownership["temporary"] != temporary
                or ownership["previous"] != (previous if prior is not None else None)
                or ownership["expectedSha256"] != prepared["sha256"]
                or type(ownership["parentDevice"]) is not int
                or type(ownership["parentInode"]) is not int
                or prepared["device"] != ownership["parentDevice"]):
            return unclear
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        with fd_ops.open_parent(root, ownership["path"]) as (parent, leaf):
            observed = os.fstat(parent)
            if (observed.st_dev, observed.st_ino) != (ownership["parentDevice"], ownership["parentInode"]):
                return unclear
            def exists(name):
                try:
                    fd_ops.stat_at(parent, name)
                    return True
                except FileNotFoundError:
                    return False
            def matches(name, identity):
                return exists(name) and _matches(parent, name, identity)
            if matches(leaf, prepared):
                if prior is None:
                    retained = None
                    if exists(temporary) or exists(previous):
                        return unclear
                elif matches(previous, prior) and not exists(temporary):
                    retained = previous
                elif matches(temporary, prior) and not exists(previous):
                    retained = temporary
                else:
                    return unclear
                handle.revalidate()
                return ReconcileResult("succeeded", None, {"path": ownership["path"],
                    "identity": prepared, "retainedPrevious": retained, "recovered": True})
            if (matches(temporary, prepared) and not exists(previous)
                    and ((prior is None and not exists(leaf))
                         or (prior is not None and matches(leaf, prior)))):
                handle.revalidate()
                return ReconcileResult("failed", "WRITE_NOT_PUBLISHED_AT_RECOVERY",
                                       {"path": ownership["path"], "retainedTemporary": temporary})
            return unclear
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return unclear
    finally:
        if root is not None:
            os.close(root)
