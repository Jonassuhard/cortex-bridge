"""Content/identity binding for one exclusively held, unpublished generation.

This produces metadata, not readiness, consent or a running installation.
The caller must own staging, trust the build records, and publish transactionally.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from uuid import UUID

from executor import fd_ops
from install_resource_tree import _file, _inventory, _private
from native_helpers import attest_helper
from storage_reconciliation import digest

GENERATION_DOMAIN = "CORTEX-S3\x00INSTALLED-GENERATION\x00V1\x00"
TREE_DOMAIN = "CORTEX-S3\x00RESOURCE-TREE\x00V1\x00"


@dataclass(frozen=True)
class GenerationMetadata:
    generation_id: UUID
    manifest_bytes: bytes
    record_bytes: bytes
    selector_bytes: bytes


def _json(value):
    # Preserve declared helper order in the published representation.
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def build_generation_metadata(home, generation_id, native_helpers):
    from installer import NATIVE_HELPERS
    if not isinstance(generation_id, UUID):
        raise ValueError("Generation UUID required")
    names = [spec.name for spec in NATIVE_HELPERS]
    if type(native_helpers) is not dict or list(native_helpers) != names:
        raise ValueError("Complete ordered native helper records required")
    native = json.loads(_json(native_helpers))
    home = Path(home)
    if not home.is_absolute() or home != home.resolve(strict=True):
        raise ValueError("Canonical generation directory required")
    root = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    app = interpreter = None
    try:
        _private(root)
        app = fd_ops.open_directory_at(root, "app")
        tree = _inventory(app, private=True)
        entries = {entry["path"]: entry for entry in tree}
        required = {"bin", "python", "frontend", "scripts", "native-src", "build-profiles", "chrome-extension"}
        roots = {entry["path"] for entry in tree if "/" not in entry["path"]}
        if roots not in (required, required | {"native-helpers.json"}):
            raise ValueError("Generation application resource set is incomplete or unexpected")
        for relative in ("python/server.py", "frontend/out/index.html", "frontend/fallback/index.html",
                         "chrome-extension/manifest.json", "bin/python"):
            if entries.get(relative, {}).get("kind") != "file":
                raise ValueError("Required generation file is missing")
        for spec in NATIVE_HELPERS:
            record = native[spec.name]
            for relative, key in ((f"native-src/{spec.source.name}", "source_sha256"),
                                  (f"build-profiles/{spec.build_profile.name}", "build_profile_sha256")):
                if entries.get(relative, {}).get("sha256") != record[key]:
                    raise ValueError("Native build input digest mismatch")
            attested = attest_helper(spec.name, {"native_helpers": native}, home=home)
            attested.close()
        interpreter = fd_ops.open_regular_at(app, "bin/python")
        identity = os.fstat(interpreter)
        if identity.st_uid != os.getuid() or stat.S_IMODE(identity.st_mode) != 0o700:
            raise ValueError("Private interpreter required")
        _, interpreter_hash = _file(interpreter)
        if interpreter_hash != entries["bin/python"]["sha256"]:
            raise ValueError("Interpreter changed during manifest construction")
        interpreter_record = dict(target="app/bin/python", sha256=interpreter_hash,
                                  dev_u32=identity.st_dev & 0xffffffff, ino=identity.st_ino,
                                  uid=identity.st_uid, mode=0o700)
        manifest = dict(schema_version=1, native_helpers=native, interpreter=interpreter_record, app_tree=tree)
        manifest_bytes = _json(manifest)

        def tree_digest(prefix):
            selected = [entry for entry in tree if entry["path"] == prefix or entry["path"].startswith(prefix + "/")]
            return digest(TREE_DOMAIN, selected)

        record = dict(schema_version=1, generation_id=str(generation_id),
                      python_tree_sha256=tree_digest("python"), scripts_tree_sha256=tree_digest("scripts"),
                      native_sources_tree_sha256=tree_digest("native-src"),
                      build_profiles_tree_sha256=tree_digest("build-profiles"),
                      extension_tree_sha256=tree_digest("chrome-extension"),
                      interpreter_sha256=interpreter_hash, interpreter_dev_u32=identity.st_dev & 0xffffffff,
                      interpreter_ino=identity.st_ino, interpreter_uid=identity.st_uid, interpreter_mode=0o700,
                      native_helpers=native, owned_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
        record["generation_record_sha256"] = digest(GENERATION_DOMAIN, record)
        selector = dict(schema_version=1, generation_id=str(generation_id),
                        generation_record_sha256=record["generation_record_sha256"])
        if _inventory(app, private=True) != tree:
            raise ValueError("Generation changed during manifest construction")
        return GenerationMetadata(generation_id, manifest_bytes, _json(record), _json(selector))
    finally:
        for descriptor in (interpreter, app, root):
            if descriptor is not None:
                os.close(descriptor)


def verify_generation_metadata(home, metadata):
    """Recompute every binding; caller must separately trust the expected metadata."""
    if type(metadata) is not GenerationMetadata:
        raise ValueError("Generation metadata required")
    try:
        record = json.loads(metadata.record_bytes)
        manifest = json.loads(metadata.manifest_bytes)
        generation_id = UUID(record["generation_id"])
        native = manifest["native_helpers"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Invalid generation metadata") from error
    if build_generation_metadata(home, generation_id, native) != metadata:
        raise ValueError("Generation does not match its metadata")
