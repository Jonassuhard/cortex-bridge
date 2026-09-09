"""Install one immutable ABI-v1 native bootstrap under the caller's install lock.

Generation updates reuse a verified bootstrap. A changed bootstrap source/profile
requires a separate migration, never an unreviewed replacement of a live launcher.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess

from generation_publication import _private_directory, _write_all
from native_helpers import attest_file
from storage_reconciliation import digest

SOURCE = "native/macos/storage_bootstrap.swift"
PROFILE = "native/build-profiles/storage-bootstrap-v1.json"
FILES = {"cortex-launch", "bootstrap-v1.json", "storage_bootstrap.swift", "storage-bootstrap-v1.json"}
DOMAIN = "CORTEX-S3\x00BOOTSTRAP-MANIFEST\x00V1\x00"


def _cdhash(binary):
    verified = subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(binary)],
                              env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
                              capture_output=True, timeout=15)
    if verified.returncode != 0:
        raise ValueError("Bootstrap signature verification failed")
    result = subprocess.run(["/usr/bin/codesign", "-d", "--verbose=4", str(binary)],
                            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
                            check=True, capture_output=True, text=True, timeout=15)
    found = re.search(r"^CDHash=([0-9a-f]{40,64})$", result.stderr, re.M)
    if found is None:
        raise ValueError("Missing bootstrap signature identity")
    return found.group(1)


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or not 0 <= info.st_size <= 1024 * 1024):
            raise ValueError("Unsafe bootstrap metadata")
        data = os.read(fd, info.st_size + 1)
        if len(data) != info.st_size:
            raise ValueError("Bootstrap metadata changed")
        return data
    finally:
        os.close(fd)


def inspect(home, inputs):
    directory = Path(home) / "bootstrap"
    if not directory.exists() and not directory.is_symlink():
        return None
    _private_directory(directory)
    if set(os.listdir(directory)) != FILES:
        raise ValueError("Bootstrap file set is incomplete or unexpected")
    raw = _read(directory / "bootstrap-v1.json")
    from installed_storage_runtime import _reject_duplicate_keys
    record = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    if (type(record) is not dict or record.get("schema_version") != 1
            or record.get("target") != "bootstrap/cortex-launch" or record.get("source") != SOURCE):
        raise ValueError("Invalid bootstrap manifest")
    unsigned = {key: value for key, value in record.items() if key != "bootstrap_manifest_sha256"}
    if record.get("bootstrap_manifest_sha256") != digest(DOMAIN, unsigned):
        raise ValueError("Bootstrap manifest digest changed")
    for key, relative in (("source", SOURCE), ("profile", PROFILE)):
        expected = inputs[key]["sha256"]
        field = "source_sha256" if key == "source" else "build_profile_sha256"
        if record.get(field) != expected:
            raise RuntimeError("BOOTSTRAP_UPDATE_REQUIRES_MIGRATION")
        if hashlib.sha256(_read(directory / Path(relative).name)).hexdigest() != expected:
            raise ValueError("Bootstrap provenance changed")
    fd, details, sha = attest_file(directory / "cortex-launch")
    try:
        actual = dict(sha256=sha, dev_u32=details.st_dev & 0xffffffff, ino=details.st_ino,
                      uid=details.st_uid, mode=stat.S_IMODE(details.st_mode),
                      cdhash=_cdhash(directory / "cortex-launch"))
        if details.st_nlink != 1 or any(record.get(key) != value for key, value in actual.items()):
            raise ValueError("Bootstrap executable changed")
    finally:
        os.close(fd)
    return {"record": record, "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def stage(staging, inputs):
    from generation_install import _copy_checked
    staging = Path(staging)
    directory = staging / "bootstrap"
    directory.mkdir(mode=0o700)
    for key, relative in (("source", SOURCE), ("profile", PROFILE)):
        _copy_checked(inputs[key], directory / Path(relative).name)
    profile = json.loads(_read(directory / Path(PROFILE).name))
    flags = ["-O", "-target", f"{platform.machine()}-apple-macosx14.0"]
    if (profile.get("schema_version") != 1 or profile.get("target") != "bootstrap/cortex-launch"
            or profile.get("source") != SOURCE or profile.get("swiftc") != flags
            or profile.get("configuration") != "production" or profile.get("test_routes") is not False
            or profile.get("frameworks") != ["Foundation"]):
        raise ValueError("Unsupported stable bootstrap profile")
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C",
                   "CLANG_MODULE_CACHE_PATH": str(staging / "bootstrap-clang-cache"),
                   "SWIFT_MODULECACHE_PATH": str(staging / "bootstrap-swift-cache")}
    binary = directory / "cortex-launch"
    subprocess.run(["/usr/bin/xcrun", "swiftc", *flags, "-framework", "Foundation",
                    str(directory / Path(SOURCE).name), "-o", str(binary)],
                   env=environment, check=True, capture_output=True, timeout=180)
    binary.chmod(0o700)
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(binary)],
                   env=environment, check=True, capture_output=True, timeout=15)
    fd, details, sha = attest_file(binary)
    try:
        os.fsync(fd)
        record = dict(schema_version=1, target="bootstrap/cortex-launch", source=SOURCE,
                      source_sha256=inputs["source"]["sha256"],
                      build_profile_sha256=inputs["profile"]["sha256"], sha256=sha,
                      dev_u32=details.st_dev & 0xffffffff, ino=details.st_ino, uid=details.st_uid,
                      mode=stat.S_IMODE(details.st_mode), cdhash=_cdhash(binary))
        record["bootstrap_manifest_sha256"] = digest(DOMAIN, record)
    finally:
        os.close(fd)
    fd = os.open(directory / "bootstrap-v1.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, json.dumps(record, separators=(",", ":")).encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return inspect(staging, inputs)


def publish(home, staging, inputs, before):
    from installer import _rename_exclusive
    if inspect(home, inputs) != before:
        raise RuntimeError("BOOTSTRAP_CHANGED_AFTER_APPROVAL")
    if before is not None:
        return
    inspect(staging, inputs)
    _rename_exclusive(Path(staging) / "bootstrap", Path(home) / "bootstrap")
    for directory in (staging, home):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    inspect(home, inputs)
