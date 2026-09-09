"""One-shot managed-runtime startup lease primitives.

The lease is a local socketpair handshake.  It is intentionally independent of
the web server so it can be tested without binding a port.  A lease is written
to the caller-owned pids directory, consumed exactly once by the child, and
acknowledged by the parent.  The module never treats a missing or replayed
receipt as readiness.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import secrets
import socket
import stat
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import UUID, uuid4

from storage_broker import BootIdentity, _safe_boot_identity
from storage_result import StorageStatus


class StartupLeaseError(RuntimeError):
    pass


_SHA256 = set("0123456789abcdef")
_RENAME_EXCL = 0x00000004
_PROC_PIDTBSDINFO = 3


class _ProcBSDInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32), ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32), ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32), ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32), ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32), ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32), ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32), ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not (set(value) - _SHA256)


@dataclass(frozen=True, slots=True)
class ManagedProcessIdentity:
    pid: int
    pgid: int
    start_time: str

    def __post_init__(self) -> None:
        if type(self.pid) is not int or self.pid <= 0:
            raise ValueError("managed process pid is invalid")
        if type(self.pgid) is not int or self.pgid <= 0:
            raise ValueError("managed process pgid is invalid")
        if type(self.start_time) is not str or not self.start_time or any(ord(ch) < 0x20 for ch in self.start_time):
            raise ValueError("managed process start identity is invalid")


def _read_kernel_process_identity(pid: int) -> ManagedProcessIdentity | None:
    """Read one exact Darwin PID/PGID/creation tuple without a text fallback.

    ``start_time`` is the kernel ``proc_bsdinfo`` timeval encoded as
    ``darwin-proc-bsdinfo-v1:<seconds>:<microseconds-six-digits>``.  Failure to
    obtain the complete owner process snapshot is deliberately not recoverable
    through ``ps lstart`` because that representation loses sub-second identity.
    """
    if sys.platform != "darwin" or type(pid) is not int or pid <= 0:
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        proc_pidinfo = libc.proc_pidinfo
        proc_pidinfo.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
            ctypes.c_void_p, ctypes.c_int,
        ]
        proc_pidinfo.restype = ctypes.c_int
        info = _ProcBSDInfo()
        copied = proc_pidinfo(
            pid, _PROC_PIDTBSDINFO, 0, ctypes.byref(info), ctypes.sizeof(info)
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return None
    seconds = int(info.pbi_start_tvsec)
    microseconds = int(info.pbi_start_tvusec)
    observed_pid = int(info.pbi_pid)
    observed_pgid = int(info.pbi_pgid)
    if (
        copied != ctypes.sizeof(info)
        or observed_pid != pid
        or observed_pgid <= 0
        or int(info.pbi_uid) != os.getuid()
        or seconds <= 0
        or not 0 <= microseconds < 1_000_000
    ):
        return None
    return ManagedProcessIdentity(
        observed_pid,
        observed_pgid,
        f"darwin-proc-bsdinfo-v1:{seconds}:{microseconds:06d}",
    )


@dataclass(frozen=True, slots=True)
class StartupLease:
    schema_version: Literal[1]
    lease_id: str
    nonce: str
    identity: ManagedProcessIdentity
    launcher_pid: int
    launcher_start_time: str
    pids_dev_u32: int
    pids_ino: int
    pids_uid: int
    pids_mode: Literal[448]
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    expires_at_monotonic_ns: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("startup lease schema is invalid")
        try:
            UUID(self.lease_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("startup lease id is invalid") from exc
        if type(self.nonce) is not str or len(self.nonce) != 32 or set(self.nonce) - _SHA256:
            raise ValueError("startup lease nonce is invalid")
        if type(self.launcher_pid) is not int or self.launcher_pid <= 0:
            raise ValueError("startup launcher pid is invalid")
        if type(self.launcher_start_time) is not str or not self.launcher_start_time:
            raise ValueError("startup launcher identity is invalid")
        if type(self.pids_dev_u32) is not int or not 0 <= self.pids_dev_u32 <= 0xFFFFFFFF:
            raise ValueError("startup pids device is invalid")
        if type(self.pids_ino) is not int or self.pids_ino <= 0:
            raise ValueError("startup pids inode is invalid")
        if type(self.pids_uid) is not int or self.pids_uid < 0:
            raise ValueError("startup pids uid is invalid")
        if self.pids_mode != 0o700:
            raise ValueError("startup pids mode is invalid")
        if self.storage_transaction_id is not None:
            try:
                UUID(self.storage_transaction_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError("startup transaction id is invalid") from exc
        if not _is_sha256(self.generation_record_sha256):
            raise ValueError("startup generation digest is invalid")
        if type(self.expires_at_monotonic_ns) is not int or self.expires_at_monotonic_ns <= 0:
            raise ValueError("startup lease expiry is invalid")


@dataclass(frozen=True, slots=True)
class ManagedStartContext:
    lease_id: str
    identity: ManagedProcessIdentity
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        try:
            UUID(self.lease_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("managed start lease id is invalid") from exc
        if not _is_sha256(self.generation_record_sha256) or not _is_sha256(self.receipt_sha256):
            raise ValueError("managed start digest is invalid")


@dataclass(frozen=True, slots=True)
class ManagedStartReceipt:
    lease_id: str
    child_pid: int
    storage_transaction_id: str | None
    acknowledged: Literal[True]

    def __post_init__(self) -> None:
        try:
            UUID(self.lease_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("managed receipt lease id is invalid") from exc
        if type(self.child_pid) is not int or self.child_pid <= 0 or self.acknowledged is not True:
            raise ValueError("managed receipt is invalid")
        if self.storage_transaction_id is not None:
            try:
                UUID(self.storage_transaction_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError("managed receipt transaction id is invalid") from exc


RuntimeLifespanState = Literal["STARTING", "READY", "CLOSED"]


@dataclass(frozen=True, slots=True)
class RuntimeLifespanRecord:
    schema_version: Literal[1]
    state: RuntimeLifespanState
    lease_id: str
    lease_receipt_sha256: str
    identity: ManagedProcessIdentity
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    previous_record_sha256: str | None
    record_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.state not in {"STARTING", "READY", "CLOSED"}:
            raise ValueError("runtime lifespan record is invalid")
        try:
            UUID(self.lease_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("runtime lifespan lease id is invalid") from exc
        if self.storage_transaction_id is not None:
            try:
                UUID(self.storage_transaction_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError("runtime lifespan transaction id is invalid") from exc
        for name, value in (
            ("lease receipt", self.lease_receipt_sha256),
            ("generation", self.generation_record_sha256),
            ("record", self.record_sha256),
        ):
            if not _is_sha256(value):
                raise ValueError(f"runtime lifespan {name} digest is invalid")
        if self.previous_record_sha256 is not None and not _is_sha256(self.previous_record_sha256):
            raise ValueError("runtime lifespan previous digest is invalid")


def _json(value: Any) -> Any:
    if isinstance(value, BootIdentity):
        return {"seconds": value.seconds, "microseconds": value.microseconds}
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _send_json(sock: socket.socket, value: Mapping[str, Any]) -> None:
    payload = json.dumps(_json(value), separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    if len(payload) > 4096:
        raise StartupLeaseError("STARTUP_LEASE_FRAME_TOO_LARGE")
    sock.sendall(payload)


def _recv_json(sock: socket.socket, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while len(data) <= 4096:
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        if time.monotonic() >= deadline:
            raise StartupLeaseError("STARTUP_LEASE_TIMEOUT")
        chunk = sock.recv(1)  # Leave the next frame queued for the next reader.
        if not chunk:
            raise StartupLeaseError("STARTUP_LEASE_EOF")
        data.extend(chunk)
        if b"\n" in chunk:
            break
    else:
        raise StartupLeaseError("STARTUP_LEASE_FRAME_TOO_LARGE")
    line = bytes(data).split(b"\n", 1)[0]
    try:
        pairs_seen: set[str] = set()
        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in items:
                if key in pairs_seen:
                    raise ValueError("duplicate object key")
                pairs_seen.add(key)
                value[key] = item
            return value
        value = json.loads(line.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise StartupLeaseError("STARTUP_LEASE_MALFORMED") from exc
    if not isinstance(value, dict):
        raise StartupLeaseError("STARTUP_LEASE_MALFORMED")
    return value


def _lease_filename(lease_id: str, *, consumed: bool = False) -> str:
    try:
        if str(UUID(lease_id)) != lease_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise StartupLeaseError("STARTUP_LEASE_ID_INVALID") from exc
    suffix = ".consumed" if consumed else ""
    return f"startup-lease-{lease_id}{suffix}.json"


def _rename_exclusive_at(directory_fd: int, source: str, target: str) -> None:
    """Atomically consume one lease without replacing an existing receipt."""
    if sys.platform != "darwin":
        # The product route is macOS.  Keep non-macOS fixture execution
        # no-clobber without pretending that it proves renameatx_np.
        os.link(
            source, target, src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd, follow_symlinks=False,
        )
        os.unlink(source, dir_fd=directory_fd)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = libc.renameatx_np
    renameatx_np.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        directory_fd, os.fsencode(source), directory_fd, os.fsencode(target),
        _RENAME_EXCL,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), target)
    raise OSError(error, os.strerror(error), target)


def _receipt_sha(lease: StartupLease) -> str:
    return hashlib.sha256(json.dumps(_json(lease), separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _runtime_record_sha(record: RuntimeLifespanRecord) -> str:
    raw = _json(record)
    raw.pop("record_sha256", None)
    return hashlib.sha256(json.dumps(raw, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _duplicate_key_rejector(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _owner_only_home(home: Path) -> None:
    home = Path(home)
    try:
        details = home.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise StartupLeaseError("LIFESPAN_HOME_INVALID") from exc
    if home.is_symlink() or not stat.S_ISDIR(details.st_mode):
        raise StartupLeaseError("LIFESPAN_HOME_INVALID")
    if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise StartupLeaseError("LIFESPAN_HOME_INVALID")


def _read_runtime_lifespan_record(home: Path) -> RuntimeLifespanRecord | None:
    _owner_only_home(home)
    path = Path(home) / "runtime-lifespan.json"
    try:
        details = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(details.st_mode):
            raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
        if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o600:
            raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicate_key_rejector)
    except StartupLeaseError:
        raise
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, FileNotFoundError):
            return None
        raise StartupLeaseError("LIFESPAN_RECORD_INVALID") from exc
    if not isinstance(raw, dict) or set(raw) != set(RuntimeLifespanRecord.__dataclass_fields__):
        raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
    try:
        record_data = dict(raw)
        identity = record_data.get("identity")
        boot = record_data.get("boot")
        if not isinstance(identity, dict) or not isinstance(boot, dict):
            raise ValueError("nested record data is invalid")
        record_data["identity"] = ManagedProcessIdentity(**identity)
        record_data["boot"] = BootIdentity(**boot)
        record = RuntimeLifespanRecord(**record_data)
    except (KeyError, TypeError, ValueError) as exc:
        raise StartupLeaseError("LIFESPAN_RECORD_INVALID") from exc
    if _runtime_record_sha(record) != record.record_sha256:
        raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
    return record


def _read_selected_generation_digest(home: Path) -> str:
    path = Path(home) / "current-generation.json"
    try:
        details = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
        ):
            raise StartupLeaseError("MANAGED_START_GENERATION_INVALID")
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_key_rejector,
        )
    except StartupLeaseError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise StartupLeaseError("MANAGED_START_GENERATION_INVALID") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version", "generation_id", "generation_record_sha256"
    }:
        raise StartupLeaseError("MANAGED_START_GENERATION_INVALID")
    try:
        UUID(str(raw["generation_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise StartupLeaseError("MANAGED_START_GENERATION_INVALID") from exc
    digest_value = raw.get("generation_record_sha256")
    if raw.get("schema_version") != 1 or not _is_sha256(digest_value):
        raise StartupLeaseError("MANAGED_START_GENERATION_INVALID")
    return str(digest_value)


def _read_consumed_lease(home: Path, record: RuntimeLifespanRecord) -> StartupLease:
    pids = Path(home) / "pids"
    path = pids / _lease_filename(record.lease_id, consumed=True)
    try:
        pids_details = pids.lstat()
        details = path.lstat()
        if (
            pids.is_symlink()
            or not stat.S_ISDIR(pids_details.st_mode)
            or pids_details.st_uid != os.getuid()
            or stat.S_IMODE(pids_details.st_mode) != 0o700
            or path.is_symlink()
            or not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
            or details.st_dev != pids_details.st_dev
            or details.st_size > 64 * 1024
        ):
            raise StartupLeaseError("MANAGED_START_RECEIPT_INVALID")
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_duplicate_key_rejector,
        )
    except StartupLeaseError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise StartupLeaseError("MANAGED_START_RECEIPT_INVALID") from exc
    if not isinstance(raw, dict) or set(raw) != set(StartupLease.__dataclass_fields__):
        raise StartupLeaseError("MANAGED_START_RECEIPT_INVALID")
    try:
        raw = dict(raw)
        raw["identity"] = ManagedProcessIdentity(**raw["identity"])
        raw["boot"] = BootIdentity(**raw["boot"])
        lease = StartupLease(**raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise StartupLeaseError("MANAGED_START_RECEIPT_INVALID") from exc
    if (
        lease.lease_id != record.lease_id
        or lease.identity != record.identity
        or lease.storage_transaction_id != record.storage_transaction_id
        or lease.boot != record.boot
        or lease.generation_record_sha256 != record.generation_record_sha256
        or _receipt_sha(lease) != record.lease_receipt_sha256
        or (lease.pids_dev_u32, lease.pids_ino, lease.pids_uid, lease.pids_mode)
        != (
            pids_details.st_dev & 0xFFFFFFFF,
            pids_details.st_ino,
            pids_details.st_uid,
            0o700,
        )
    ):
        raise StartupLeaseError("MANAGED_START_RECEIPT_INVALID")
    return lease


def _live_identity_matches(identity: ManagedProcessIdentity, *, reader: Any = None) -> bool:
    if reader is None:
        reader = _read_kernel_process_identity
    try:
        observed = reader(identity.pid)
    except Exception:
        return False
    return observed == identity


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_runtime_lifespan(home: Path, record: RuntimeLifespanRecord) -> None:
    _owner_only_home(home)
    path = Path(home) / "runtime-lifespan.json"
    if path.is_symlink():
        raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
    payload = json.dumps(_json(record), separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".runtime-lifespan.", dir=home)
    temporary_path = Path(temporary)
    try:
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise StartupLeaseError("LIFESPAN_WRITE_FAILED")
                view = view[written:]
            os.fsync(fd)
        except OSError as exc:
            raise StartupLeaseError("LIFESPAN_WRITE_FAILED") from exc
        finally:
            os.close(fd)
        if path.is_symlink():
            raise StartupLeaseError("LIFESPAN_RECORD_INVALID")
        os.replace(temporary_path, path)
        _fsync_directory(Path(home))
    except OSError as exc:
        raise StartupLeaseError("LIFESPAN_WRITE_FAILED") from exc
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def write_runtime_lifespan_record(
    home: Path,
    *,
    context: ManagedStartContext,
    state: RuntimeLifespanState,
    previous_record_sha256: str | None = None,
) -> RuntimeLifespanRecord:
    if not isinstance(context, ManagedStartContext) or not isinstance(state, str) or state not in {"STARTING", "READY", "CLOSED"}:
        raise StartupLeaseError("LIFESPAN_TRANSITION_INVALID")
    current = _read_runtime_lifespan_record(Path(home))
    if current is None:
        if state != "STARTING" or previous_record_sha256 is not None:
            raise StartupLeaseError("LIFESPAN_TRANSITION_INVALID")
        previous = None
    elif state == "STARTING":
        if current.state != "CLOSED":
            raise StartupLeaseError("LIFESPAN_TRANSITION_INVALID")
        if previous_record_sha256 is None:
            previous = current.record_sha256
        elif previous_record_sha256 != current.record_sha256:
            raise StartupLeaseError("LIFESPAN_PREVIOUS_MISMATCH")
        else:
            previous = previous_record_sha256
    elif state == "READY":
        if current.state != "STARTING":
            raise StartupLeaseError("LIFESPAN_TRANSITION_INVALID")
        if previous_record_sha256 != current.record_sha256:
            raise StartupLeaseError("LIFESPAN_PREVIOUS_MISMATCH")
        previous = previous_record_sha256
    else:
        if current.state != "READY":
            raise StartupLeaseError("LIFESPAN_TRANSITION_INVALID")
        if previous_record_sha256 != current.record_sha256:
            raise StartupLeaseError("LIFESPAN_PREVIOUS_MISMATCH")
        previous = previous_record_sha256
    record = RuntimeLifespanRecord(
        schema_version=1,
        state=state,
        lease_id=context.lease_id,
        lease_receipt_sha256=context.receipt_sha256,
        identity=context.identity,
        storage_transaction_id=context.storage_transaction_id,
        boot=context.boot,
        generation_record_sha256=context.generation_record_sha256,
        previous_record_sha256=previous,
        record_sha256="0" * 64,
    )
    record = RuntimeLifespanRecord(
        schema_version=record.schema_version,
        state=record.state,
        lease_id=record.lease_id,
        lease_receipt_sha256=record.lease_receipt_sha256,
        identity=record.identity,
        storage_transaction_id=record.storage_transaction_id,
        boot=record.boot,
        generation_record_sha256=record.generation_record_sha256,
        previous_record_sha256=record.previous_record_sha256,
        record_sha256=_runtime_record_sha(record),
    )
    _atomic_write_runtime_lifespan(Path(home), record)
    return record


def publish_startup_lease(
    *,
    pids_fd: int,
    identity: ManagedProcessIdentity,
    storage_transaction_id: str | None,
    boot: BootIdentity,
    generation_record_sha256: str,
    ttl_seconds: float = 5.0,
) -> StartupLease:
    if ttl_seconds <= 0 or ttl_seconds > 30:
        raise StartupLeaseError("STARTUP_LEASE_TTL_INVALID")
    details = os.fstat(pids_fd)
    if not stat.S_ISDIR(details.st_mode) or details.st_nlink < 2 or details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise StartupLeaseError("STARTUP_LEASE_PIDS_UNSAFE")
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise StartupLeaseError("STARTUP_LEASE_PIDS_UNSAFE")
    lease = StartupLease(
        1, str(uuid4()), secrets.token_hex(16), identity, os.getpid(), _launcher_identity(),
        details.st_dev & 0xFFFFFFFF, details.st_ino, details.st_uid, 0o700,
        storage_transaction_id, boot, generation_record_sha256,
        time.monotonic_ns() + int(ttl_seconds * 1_000_000_000),
    )
    filename = _lease_filename(lease.lease_id)
    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=pids_fd)
    try:
        payload = json.dumps(_json(lease), separators=(",", ":"), sort_keys=True).encode("utf-8")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short startup-lease write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(pids_fd)
    return lease


def parent_release_and_wait_ack(control_fd: int, lease: StartupLease, *, timeout_seconds: float = 5.0) -> None:
    sock = socket.socket(fileno=control_fd)
    try:
        _send_json(sock, {"type": "START", "lease_id": lease.lease_id, "nonce": lease.nonce})
        ack = _recv_json(sock, timeout_seconds)
        if ack.get("type") != "ACK" or ack.get("lease_id") != lease.lease_id or ack.get("receipt_sha256") != _receipt_sha(lease):
            raise StartupLeaseError("STARTUP_LEASE_ACK_INVALID")
    finally:
        sock.detach()


def child_consume_startup_lease(*, control_fd: int, pids_fd: int, expected_transaction_id: str | None) -> ManagedStartContext:
    sock = socket.socket(fileno=control_fd)
    try:
        grant = _recv_json(sock, 5.0)
        lease_id = grant.get("lease_id")
        nonce = grant.get("nonce")
        if grant.get("type") != "START" or not isinstance(lease_id, str) or not isinstance(nonce, str):
            raise StartupLeaseError("STARTUP_LEASE_MALFORMED")
        filename = _lease_filename(lease_id)
        consumed_filename = _lease_filename(lease_id, consumed=True)
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=pids_fd)
            try:
                details = os.fstat(fd)
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_uid != os.getuid()
                    or stat.S_IMODE(details.st_mode) != 0o600
                    or details.st_nlink != 1
                ):
                    raise StartupLeaseError("STARTUP_LEASE_UNSAFE")
                data = os.read(fd, 64 * 1024 + 1)
                if len(data) > 64 * 1024:
                    raise StartupLeaseError("STARTUP_LEASE_FRAME_TOO_LARGE")
            finally:
                os.close(fd)
        except (FileNotFoundError, OSError) as exc:
            raise StartupLeaseError("STARTUP_LEASE_REPLAYED") from exc
        try:
            raw = json.loads(
                data.decode("utf-8"), object_pairs_hook=_duplicate_key_rejector
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise StartupLeaseError("STARTUP_LEASE_MALFORMED") from exc
        if set(raw) != set(StartupLease.__dataclass_fields__):
            raise StartupLeaseError("STARTUP_LEASE_MALFORMED")
        if raw.get("nonce") != nonce:
            raise StartupLeaseError("STARTUP_LEASE_GRANT_INVALID")
        if raw.get("expires_at_monotonic_ns", 0) < time.monotonic_ns():
            raise StartupLeaseError("STARTUP_LEASE_EXPIRED")
        details = os.fstat(pids_fd)
        if (details.st_dev & 0xFFFFFFFF, details.st_ino, details.st_uid) != (raw.get("pids_dev_u32"), raw.get("pids_ino"), raw.get("pids_uid")):
            raise StartupLeaseError("STARTUP_LEASE_PIDS_CHANGED")
        if raw.get("storage_transaction_id") != expected_transaction_id:
            raise StartupLeaseError("STARTUP_LEASE_TRANSACTION_MISMATCH")
        identity = ManagedProcessIdentity(**raw["identity"])
        boot = BootIdentity(**raw["boot"])
        lease = StartupLease(**{**raw, "identity": identity, "boot": boot})
        if identity != _read_kernel_process_identity(os.getpid()):
            raise StartupLeaseError("STARTUP_LEASE_PROCESS_MISMATCH")
        if boot != _safe_boot_identity():
            raise StartupLeaseError("STARTUP_LEASE_BOOT_MISMATCH")
        launcher = _read_kernel_process_identity(lease.launcher_pid)
        if launcher is None or launcher.start_time != lease.launcher_start_time:
            raise StartupLeaseError("STARTUP_LEASE_LAUNCHER_MISMATCH")
        receipt = _receipt_sha(lease)
        context = ManagedStartContext(lease.lease_id, identity, lease.storage_transaction_id, boot, lease.generation_record_sha256, receipt)
        try:
            _rename_exclusive_at(pids_fd, filename, consumed_filename)
            os.fsync(pids_fd)
        except FileExistsError as exc:
            raise StartupLeaseError("STARTUP_LEASE_REPLAYED") from exc
        except OSError as exc:
            raise StartupLeaseError("STARTUP_LEASE_CONSUME_FAILED") from exc
        _send_json(sock, {"type": "ACK", "lease_id": lease.lease_id, "receipt_sha256": receipt})
        return context
    finally:
        sock.detach()


def _require_managed_start_context(home: Path, storage_status: StorageStatus) -> ManagedStartContext:
    if storage_status.runtime_allowed is not True:
        raise StartupLeaseError("MANAGED_START_REQUIRED")
    try:
        record = _read_runtime_lifespan_record(Path(home))
    except StartupLeaseError as exc:
        if str(exc) == "LIFESPAN_RECORD_INVALID":
            raise StartupLeaseError("MANAGED_START_RECORD_INVALID") from exc
        raise StartupLeaseError("MANAGED_START_REQUIRED") from exc
    if record is None:
        raise StartupLeaseError("MANAGED_START_REQUIRED")
    if record.state != "READY":
        raise StartupLeaseError("MANAGED_START_NOT_READY")
    if record.storage_transaction_id != storage_status.transaction_id:
        raise StartupLeaseError("MANAGED_START_TRANSACTION_MISMATCH")
    if record.boot != _safe_boot_identity():
        raise StartupLeaseError("MANAGED_START_BOOT_MISMATCH")
    if _read_selected_generation_digest(Path(home)) != record.generation_record_sha256:
        raise StartupLeaseError("MANAGED_START_GENERATION_MISMATCH")
    _read_consumed_lease(Path(home), record)
    if not _live_identity_matches(record.identity):
        raise StartupLeaseError("MANAGED_START_IDENTITY_MISMATCH")
    return ManagedStartContext(
        record.lease_id, record.identity, record.storage_transaction_id, record.boot,
        record.generation_record_sha256, record.lease_receipt_sha256,
    )


def managed_runtime_is_ready_locked(lock_set: Any, *, home: Path, expected_storage_transaction_id: str | None) -> bool:
    try:
        lock_set.assert_active(home=Path(home), required_install_mode="shared", required_storage_mode="shared")
        context = _require_managed_start_context(Path(home), StorageStatus("PASS", "RUNTIME_READY", expected_storage_transaction_id, "COMMITTED", True, True))
        return context.storage_transaction_id == expected_storage_transaction_id
    except Exception:
        return False


def launch_managed_runtime(home: Path, *, lock_set: Any, lifecycle: Any, contract: Any, timeout_seconds: float = 5.0, child_owner: Any = None) -> ManagedStartReceipt:
    from managed_runtime import launch
    return launch(home, lock_set=lock_set, lifecycle=lifecycle, contract=contract,
                  timeout_seconds=timeout_seconds, child_owner=child_owner)


def _launcher_identity() -> str:
    identity = _read_kernel_process_identity(os.getpid())
    if identity is None:
        raise StartupLeaseError("STARTUP_LAUNCHER_IDENTITY_UNAVAILABLE")
    return identity.start_time


__all__ = [
    "ManagedProcessIdentity", "StartupLease", "ManagedStartContext", "ManagedStartReceipt",
    "RuntimeLifespanRecord", "StartupLeaseError", "publish_startup_lease",
    "parent_release_and_wait_ack", "child_consume_startup_lease", "_require_managed_start_context",
    "write_runtime_lifespan_record", "managed_runtime_is_ready_locked", "launch_managed_runtime",
]
