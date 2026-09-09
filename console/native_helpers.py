"""Descriptor-held attestation for installed native storage helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import selectors
import time
from uuid import UUID
from pathlib import Path
from typing import Any, Mapping

from storage_broker import AttestedBrokerExecutable, AttestedMountProbe, DarwinU32
from executor import fd_ops


PRIVATE_MODE = 0o700


class NativeHelperAttestationError(RuntimeError):
    pass


class NativeMountReader:
    """Read descriptor metadata; retain any unresolved child, never signal it.

    The caller owns the executable attestation and must keep this reader alive
    until close succeeds. A timeout is not cleanup or volume validity evidence.
    """
    def __init__(self, executable: AttestedMountProbe):
        self.executable = executable
        self._process = None

    def close(self):
        if self._process is not None:
            if self._process.poll() is None:
                raise NativeHelperAttestationError("mount probe remains unresolved")
            self._process.stdout.close()
            self._process.stderr.close()
            self._process = None

    def __call__(self, fd):
        from executor.workspace_handle import MountFacts
        self.close()
        verify_attested_fd(self.executable)
        try:
            before = os.fstat(fd)
            if not stat.S_ISDIR(before.st_mode):
                raise NativeHelperAttestationError("mount descriptor is not a directory")
            named = os.stat(self.executable.path, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode)
                    or (named.st_dev & 0xffffffff, named.st_ino, named.st_uid, stat.S_IMODE(named.st_mode))
                    != (self.executable.dev_u32, self.executable.ino, self.executable.uid, self.executable.mode)
                    or _read_hash(self.executable.fd) != self.executable.sha256):
                raise NativeHelperAttestationError("mount probe identity changed")
            deadline = time.monotonic() + 2.0
            self._process = subprocess.Popen(
                [str(self.executable.path), '--fd', str(fd)], pass_fds=(fd,),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C'},
                close_fds=True,
            )
            process = self._process
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                for pipe in (process.stdout, process.stderr):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
                while selector.get_map() or process.poll() is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise NativeHelperAttestationError("mount probe observation timed out")
                    for key, _ in selector.select(min(remaining, 0.02)):
                        chunk = os.read(key.fd, 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif key.fileobj is process.stderr:
                            raise NativeHelperAttestationError("mount probe reported an error")
                        else:
                            output.extend(chunk)
                            if len(output) > 16384:
                                raise NativeHelperAttestationError("mount probe output too large")
            if process.returncode != 0:
                raise NativeHelperAttestationError("mount probe failed")
            self.close()
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate field')
                    result[key] = value
                return result
            data = json.loads(output, object_pairs_hook=unique)
            fields = {'schema_version', 'st_dev_u32', 'fsid_u32', 'flags',
                      'filesystem_type', 'mount_from', 'mount_on', 'volume_uuid'}
            if type(data) is not dict or set(data) != fields:
                raise ValueError('invalid fields')
            if type(data['schema_version']) is not int or data['schema_version'] != 1:
                raise ValueError('invalid version')
            if any(type(data[k]) is not int or not 0 <= data[k] <= 0xffffffff for k in ('st_dev_u32', 'flags')):
                raise ValueError('invalid integer')
            fsid = data['fsid_u32']
            if type(fsid) is not list or len(fsid) != 2 or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in fsid):
                raise ValueError('invalid fsid')
            for key in ('filesystem_type', 'mount_from', 'mount_on', 'volume_uuid'):
                if type(data[key]) is not str or not data[key] or any(ord(c) < 32 or ord(c) == 127 for c in data[key]):
                    raise ValueError('invalid text')
            volume = UUID(data['volume_uuid'])
            if volume.int == 0 or str(volume) != data['volume_uuid']:
                raise ValueError('invalid uuid')
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or data['st_dev_u32'] != before.st_dev & 0xffffffff:
                raise ValueError('descriptor changed')
            return MountFacts(data['st_dev_u32'], tuple(fsid), data['flags'],
                              data['filesystem_type'], data['mount_from'], data['mount_on'], data['volume_uuid'])
        except (OSError, ValueError, TypeError) as exc:
            raise NativeHelperAttestationError("mount probe observation rejected") from exc


class AttestedHelper:
    """Retain the verified inode until immediately before path-based spawn."""
    def __init__(self, home, record, fd):
        self.home = home
        self._record = dict(record)
        self.path = home / record["target"]
        self.fd = fd
        self._closed = False

    def close(self):
        if not self._closed:
            self._closed = True
            os.close(self.fd)

    def revalidate_for_spawn(self):
        if self._closed:
            raise NativeHelperAttestationError("native helper attestation is closed")
        try:
            _check_helper_identity(self.fd, self._record)
            verified = _open_signed_helper(self.home, self._record)
            try:
                if os.fstat(verified).st_ino != os.fstat(self.fd).st_ino:
                    raise NativeHelperAttestationError("native helper identity changed")
            finally:
                os.close(verified)
            return self.path
        except OSError as exc:
            raise NativeHelperAttestationError("native helper is unavailable") from exc


def _check_helper_identity(fd, record):
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or (before.st_dev & 0xffffffff, before.st_ino, before.st_uid, stat.S_IMODE(before.st_mode))
            != (record["dev_u32"], record["ino"], record["uid"], record["mode"])
            or before.st_uid != os.getuid() or record["mode"] != 0o700):
        raise NativeHelperAttestationError("native helper identity mismatch")
    if _read_hash(fd) != record["sha256"]:
        raise NativeHelperAttestationError("native helper digest mismatch")
    after = os.fstat(fd)
    fields = ("st_dev", "st_ino", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise NativeHelperAttestationError("native helper changed during inspection")


def _open_signed_helper(home, record):
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    helper = None
    try:
        # Open each home component without following links, including on
        # external volumes. Same-device confinement begins within that home.
        for component in fd_ops.components(str(home)[1:]):
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=parent)
            os.close(parent)
            parent = child
        home_stat = os.fstat(parent)
        if home_stat.st_uid != os.getuid() or stat.S_IMODE(home_stat.st_mode) != 0o700:
            raise NativeHelperAttestationError("native home is not private")
        with fd_ops.open_parent(parent, record["target"]) as (native_parent, leaf):
            details = os.fstat(native_parent)
            if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
                raise NativeHelperAttestationError("native directory is not private")
            helper = fd_ops.open_regular_at(native_parent, leaf)
            _check_helper_identity(helper, record)
            path = home / record["target"]
            environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
            for options in (["--verify", "--strict"], ["-d", "--verbose=4"]):
                result = subprocess.run(["/usr/bin/codesign", *options, str(path)],
                                        capture_output=True, text=True, timeout=5, env=environment)
                if result.returncode != 0:
                    raise NativeHelperAttestationError("native signature verification failed")
            found = re.search(r"^CDHash=([0-9a-f]+)$", result.stderr, re.MULTILINE)
            if found is None or found.group(1) != record["cdhash"]:
                raise NativeHelperAttestationError("native signature identity mismatch")
            named = fd_ops.stat_at(native_parent, leaf)
            opened = os.fstat(helper)
            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                raise NativeHelperAttestationError("native helper replaced during verification")
            _check_helper_identity(helper, record)
            returned, helper = helper, None
            return returned
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise NativeHelperAttestationError("native helper verification failed") from exc
    finally:
        os.close(parent)
        if helper is not None:
            os.close(helper)


def attest_helper(name, manifest, *, home):
    """Verify one trusted manifest record at an explicitly admitted home.

    Manifest provenance and the install lock are caller responsibilities.
    This performs no install/repair and never changes file permissions.
    """
    try:
        home = Path(home)
        if not home.is_absolute() or home == Path("/"):
            raise ValueError()
        record = manifest["native_helpers"][name]
        fields = {"target", "source", "source_sha256", "build_profile_sha256", "sha256",
                  "cdhash", "dev_u32", "ino", "uid", "mode"}
        if type(record) is not dict or set(record) != fields:
            raise ValueError()
        for key in ("source_sha256", "build_profile_sha256", "sha256"):
            if type(record[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", record[key]) is None:
                raise ValueError()
        if type(record["cdhash"]) is not str or re.fullmatch(r"[0-9a-f]{40,64}", record["cdhash"]) is None:
            raise ValueError()
        if any(type(record[key]) is not int for key in ("dev_u32", "ino", "uid", "mode")):
            raise ValueError()
        if not fd_ops.components(record["source"]) or not fd_ops.components(record["target"]):
            raise ValueError()
        record = dict(record)
    except (KeyError, TypeError, ValueError) as exc:
        raise NativeHelperAttestationError("native manifest record is invalid") from exc
    return AttestedHelper(home, record, _open_signed_helper(home, record))


def _read_hash(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def attest_file(path: Path, *, expected_mode: int = PRIVATE_MODE, profile_sha256: str = "") -> tuple[int, os.stat_result, str]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise NativeHelperAttestationError("native helper is not a regular file")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise NativeHelperAttestationError("native helper cannot be opened") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid():
            raise NativeHelperAttestationError("native helper ownership is invalid")
        if stat.S_IMODE(details.st_mode) != expected_mode:
            raise NativeHelperAttestationError("native helper mode is invalid")
        before = (details.st_dev, details.st_ino, details.st_size, details.st_mtime_ns)
        sha = _read_hash(fd)
        after = os.fstat(fd)
        if before != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise NativeHelperAttestationError("native helper changed while hashing")
        return fd, after, sha
    except Exception:
        os.close(fd)
        raise


def attest_broker_executable(path: Path, *, build_profile_sha256: str = "") -> AttestedBrokerExecutable:
    fd, details, sha = attest_file(path, expected_mode=PRIVATE_MODE, profile_sha256=build_profile_sha256)
    return AttestedBrokerExecutable(
        Path(path), fd, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino,
        details.st_uid, stat.S_IMODE(details.st_mode), sha, build_profile_sha256,
    )


def attest_mount_probe(path: Path, *, build_profile_sha256: str = "") -> AttestedMountProbe:
    fd, details, sha = attest_file(path, expected_mode=PRIVATE_MODE, profile_sha256=build_profile_sha256)
    return AttestedMountProbe(
        Path(path), fd, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino,
        details.st_uid, 0o700, sha, build_profile_sha256,
    )


def verify_attested_fd(attested: Any) -> None:
    if getattr(attested, "_closed", False):
        raise NativeHelperAttestationError("attestation FD is closed")
    try:
        current = os.fstat(attested.fd)
    except OSError as exc:
        raise NativeHelperAttestationError("attestation FD is unavailable") from exc
    if (current.st_dev & 0xFFFFFFFF, current.st_ino, current.st_uid) != (
        int(attested.dev_u32), attested.ino, attested.uid
    ):
        raise NativeHelperAttestationError("attested vnode identity changed")
    if stat.S_IMODE(current.st_mode) != attested.mode:
        raise NativeHelperAttestationError("attested helper mode changed")


def native_helper_manifest_record(
    *, target: str, source: str, source_sha256: str, build_profile_sha256: str,
    attested: AttestedBrokerExecutable | AttestedMountProbe, cdhash: str = "",
) -> dict[str, Any]:
    verify_attested_fd(attested)
    return {
        "target": target, "source": source, "source_sha256": source_sha256,
        "build_profile_sha256": build_profile_sha256, "sha256": attested.sha256,
        "cdhash": cdhash, "dev_u32": int(attested.dev_u32), "ino": attested.ino,
        "uid": attested.uid, "mode": attested.mode,
    }


def write_native_helper_registry(path: Path, records: Mapping[str, Mapping[str, Any]]) -> str:
    """Write an owned, hash-addressed registry atomically and return its SHA."""
    # Helper order is part of the generation contract; sorting recursively
    # would silently reorder the installer's declared helper sequence.
    payload = json.dumps({"schema_version": 1, "native_helpers": records}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("native registry write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return hashlib.sha256(payload).hexdigest()


def load_verified_native_helper_registry(home: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Read a registry bound to a trusted installer manifest, never adopt one."""
    from executor import fd_ops
    root = descriptor = None
    try:
        record = manifest["native_helper_registry"]
        if (set(record) != {"target", "sha256", "dev_u32", "ino", "uid", "mode"}
                or record["target"] != "app/native-helpers.json"
                or type(record["sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
                or any(type(record[k]) is not int for k in ("dev_u32", "ino", "uid", "mode"))
                or record["uid"] != os.getuid() or record["mode"] != 0o600):
            raise ValueError()
        home = Path(home)
        if not home.is_absolute() or home != home.resolve(strict=True):
            raise ValueError()
        root = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        owner = os.fstat(root)
        if owner.st_uid != os.getuid() or stat.S_IMODE(owner.st_mode) != 0o700:
            raise ValueError()
        descriptor = fd_ops.open_regular_at(root, record["target"])
        before = os.fstat(descriptor)
        if ((before.st_dev & 0xffffffff, before.st_ino, before.st_uid, stat.S_IMODE(before.st_mode))
                != (record["dev_u32"], record["ino"], record["uid"], record["mode"])
                or not 0 < before.st_size <= 1048576):
            raise ValueError()
        content = bytearray()
        while len(content) <= before.st_size:
            block = os.read(descriptor, min(65536, before.st_size + 1 - len(content)))
            if not block:
                break
            content.extend(block)
        after = os.fstat(descriptor)
        if (len(content) != before.st_size or hashlib.sha256(content).hexdigest() != record["sha256"]
                or any(getattr(before, k) != getattr(after, k)
                       for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink"))):
            raise ValueError()
        payload = json.loads(content)
        if (type(payload) is not dict or payload.get("schema_version") != 1
                or type(payload.get("native_helpers")) is not dict):
            raise ValueError()
        return payload
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise NativeHelperAttestationError("Installer-bound native registry could not be verified") from error
    finally:
        for descriptor in (descriptor, root):
            if descriptor is not None:
                os.close(descriptor)


def load_native_helper_registry(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeHelperAttestationError("native helper registry is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("native_helpers"), dict):
        raise NativeHelperAttestationError("native helper registry schema is invalid")
    return payload


__all__ = [
    "AttestedHelper", "attest_helper",
    "NativeHelperAttestationError", "attest_file", "attest_broker_executable",
    "attest_mount_probe", "verify_attested_fd", "native_helper_manifest_record",
    "write_native_helper_registry", "load_native_helper_registry",
    "load_verified_native_helper_registry",
]
