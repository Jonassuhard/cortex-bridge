"""Build only into caller-owned, exclusively held staging.

This does not install, replace a live helper, update a registry, or notarize.
The installer remains responsible for its lock and publication transaction.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import tempfile

from executor import fd_ops
from native_helpers import attest_file, attest_helper

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "native/build-profiles/process-release-v1.json"


def _private_directory(fd):
    details = os.fstat(fd)
    if (not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o700):
        raise ValueError("Private owned staging directory required")


def build_process_helper(home):
    from installer import NATIVE_HELPERS
    return _build_helper(home, NATIVE_HELPERS[-1])


def build_native_helper_bundle(home):
    """Prepare all helpers; caller must discard/retain incomplete staging on failure."""
    from installer import NATIVE_HELPERS
    return {spec.name: _build_helper(home, spec) for spec in NATIVE_HELPERS}


def _stage_build_inputs(root, spec, source, raw_profile):
    """Retain the exact input bytes, never adopt an existing provenance file."""
    app = fd_ops.open_directory_at(root, "app")
    directories = []
    try:
        _private_directory(app)
        inputs = (("native-src", spec.source.name, source),
                  ("build-profiles", spec.build_profile.name, raw_profile))
        for folder, name, content in inputs:
            try:
                os.mkdir(folder, 0o700, dir_fd=app)
            except FileExistsError:
                pass
            directory = fd_ops.open_directory_at(app, folder)
            directories.append((directory, name, content))
            _private_directory(directory)
            try:
                fd_ops.stat_at(directory, name)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("Native build provenance already exists")
        for directory, name, content in directories:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
            try:
                os.fchmod(descriptor, 0o600)
                remaining = memoryview(content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("Native build input write made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)
                fd_ops.fsync_directory(directory)
            finally:
                os.close(descriptor)
        fd_ops.fsync_directory(app)
    finally:
        for directory, _, _ in directories:
            os.close(directory)
        os.close(app)


def _build_helper(home, spec):
    home = Path(home)
    if sys.platform != "darwin":
        raise RuntimeError("PROCESS_HELPER_PLATFORM_UNSUPPORTED")
    if not home.is_absolute() or home != home.resolve(strict=True):
        raise ValueError("Canonical staging directory required")
    raw_profile = spec.build_profile.read_bytes()
    profile = json.loads(raw_profile)
    target_name = spec.target_name
    architecture = platform.machine()
    flags = profile.get("swiftc")
    target = f"{architecture}-apple-macosx14.0"
    if (profile.get("schema_version") != 1 or profile.get("configuration") != "production"
            or profile.get("target") != f"app/bin/{target_name}"
            or profile.get("source") != str(spec.source.relative_to(ROOT))
            or profile.get("test_routes", False) is not False
            or architecture not in ("arm64", "x86_64")
            or flags not in (["-O"], ["-O", "-target", target])):
        raise ValueError("Unsupported native build profile")
    flags = ["-O", "-target", target]
    source = spec.source.read_bytes()
    root = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    parent = None
    try:
        _private_directory(root)
        current = os.dup(root)
        try:
            for leaf in ("app", "bin"):
                try:
                    os.mkdir(leaf, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = fd_ops.open_directory_at(current, leaf)
                os.close(current)
                current = child
                _private_directory(current)
            parent, current = current, None
        finally:
            if current is not None:
                os.close(current)
        try:
            os.stat(target_name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Process helper target already exists")
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
        with tempfile.TemporaryDirectory(prefix=".process-build-", dir=home / "app/bin") as temporary:
            directory = Path(temporary)
            snapshot = directory / spec.source.name
            snapshot.write_bytes(source)
            binary = directory / target_name
            frameworks = [arg for framework in spec.frameworks for arg in ("-framework", framework)]
            subprocess.run(["/usr/bin/xcrun", "swiftc", *flags, *frameworks,
                str(snapshot), "-o", str(binary)], env=env, check=True, capture_output=True, timeout=120)
            binary.chmod(0o700)
            subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(binary)],
                           env=env, check=True, capture_output=True, timeout=15)
            subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(binary)],
                           env=env, check=True, capture_output=True, timeout=15)
            signature = subprocess.run(["/usr/bin/codesign", "-d", "--verbose=4", str(binary)],
                           env=env, check=True, capture_output=True, text=True, timeout=15)
            match = re.search(r"^CDHash=([0-9a-f]{40,64})$", signature.stderr, re.M)
            if not match:
                raise RuntimeError("PROCESS_HELPER_SIGNATURE_MISSING")
            descriptor, details, digest = attest_file(binary)
            try:
                os.fsync(descriptor)
                record = dict(target=profile["target"], source=profile["source"],
                    source_sha256=hashlib.sha256(source).hexdigest(),
                    build_profile_sha256=hashlib.sha256(raw_profile).hexdigest(),
                    sha256=digest, cdhash=match.group(1), dev_u32=details.st_dev & 0xffffffff,
                    ino=details.st_ino, uid=details.st_uid, mode=0o700)
                _stage_build_inputs(root, spec, source, raw_profile)
                build_fd = fd_ops.open_directory_at(parent, directory.name)
                try:
                    fd_ops.rename_exclusive_at(build_fd, target_name, parent, target_name)
                    fd_ops.fsync_directory(parent)
                finally:
                    os.close(build_fd)
            finally:
                os.close(descriptor)
        helper = attest_helper(spec.name, {"native_helpers": {spec.name: record}}, home=home)
        helper.close()
        return record
    finally:
        if parent is not None:
            os.close(parent)
        os.close(root)
