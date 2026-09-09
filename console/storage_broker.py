"""Python side of the Cortex Bridge S3 storage-broker contract.

This module contains the canonical wire codec, the durable five-state ledger,
and a lock-bound client.  Native effects are intentionally delegated to the
Swift broker (or an injected test transport); Python never constructs an
``hdiutil``/``diskutil`` command and never receives a native child identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import select
import socket
import stat
import struct
import subprocess
import ctypes
import sys
import time
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal, Mapping, NewType, Protocol, TypedDict, cast
from uuid import UUID, uuid4

from storage_reconciliation import canonical_json, digest


FRAME_LIMIT = 16 * 1024
MAX_UINT64 = 2**64 - 1
EFFECT_BUDGET_MAX_NS = 40_000_000_000
CLEANUP_BUDGET_MAX_NS = 12_000_000_000
TOTAL_BUDGET_MAX_NS = 52_000_000_000
RECOVERY_BUDGET_MAX_NS = 12_000_000_000
PROTOCOL_IO_MAX_NS = 2_000_000_000


class LedgerState(StrEnum):
    OPEN_PREPARED = "OPEN_PREPARED"
    OPEN_RUNNING = "OPEN_RUNNING"
    OPEN_UNRESOLVED = "OPEN_UNRESOLVED"
    CLOSED_SUCCESS = "CLOSED_SUCCESS"
    CLOSED_FAILURE = "CLOSED_FAILURE"


PublicStorageOperation = Literal[
    "create", "mount", "detach", "inspect-item", "delete-disposable-item"
]


class UnresolvedReason(StrEnum):
    CHANNEL_LOST = "CHANNEL_LOST"
    BROKER_LOST = "BROKER_LOST"
    BOOT_MISMATCH = "BOOT_MISMATCH"
    ECHILD = "ECHILD"
    IDENTITY_UNCERTAIN = "IDENTITY_UNCERTAIN"
    WAITABILITY_LOST = "WAITABILITY_LOST"
    TERMINAL_AMBIGUOUS = "TERMINAL_AMBIGUOUS"
    GROUP_PRESENT = "GROUP_PRESENT"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"


DarwinU32 = NewType("DarwinU32", int)


@dataclass(frozen=True, slots=True)
class BootIdentity:
    seconds: int
    microseconds: int

    def __post_init__(self) -> None:
        if not 0 <= self.seconds <= MAX_UINT64 or not 0 <= self.microseconds <= MAX_UINT64:
            raise ValueError("boot identity outside UInt64")


@dataclass(slots=True)
class AttestedBrokerExecutable:
    path: Path
    fd: int
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: int
    sha256: str
    build_profile_sha256: str
    _closed: bool = False

    def close(self) -> None:
        if not self._closed:
            os.close(self.fd)
            self._closed = True


@dataclass(slots=True)
class AttestedMountProbe:
    path: Path
    fd: int
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[448]
    sha256: str
    build_profile_sha256: str
    _closed: bool = False

    def close(self) -> None:
        if not self._closed:
            os.close(self.fd)
            self._closed = True


@dataclass(frozen=True, slots=True)
class BrokerSocketIdentity:
    path: Path
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: int


class NativeHelperManifestRecord(TypedDict):
    target: str
    source: str
    source_sha256: str
    build_profile_sha256: str
    sha256: str
    cdhash: str
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[448]


class InstalledStorageRuntimeGeneration(TypedDict):
    schema_version: Literal[1]
    generation_id: UUID
    python_tree_sha256: str
    scripts_tree_sha256: str
    native_sources_tree_sha256: str
    build_profiles_tree_sha256: str
    extension_tree_sha256: str
    interpreter_sha256: str
    interpreter_dev_u32: DarwinU32
    interpreter_ino: int
    interpreter_uid: int
    interpreter_mode: int
    native_helpers: Mapping[str, NativeHelperManifestRecord]
    owned_manifest_sha256: str
    generation_record_sha256: str


class InstalledGenerationSelector(TypedDict):
    schema_version: Literal[1]
    generation_id: UUID
    generation_record_sha256: str


class StableBootstrapManifest(TypedDict):
    schema_version: Literal[1]
    target: Literal["bootstrap/cortex-launch"]
    source: Literal["native/macos/storage_bootstrap.swift"]
    source_sha256: str
    build_profile_sha256: str
    sha256: str
    cdhash: str
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[448]
    bootstrap_manifest_sha256: str


@dataclass(slots=True)
class AttestedBootstrapHandle:
    home: Path
    install_lock_fd: int
    install_lock_dev_u32: int
    install_lock_ino: int
    install_lock_uid: int
    install_lock_mode: Literal[384]
    selector_fd: int
    generation_dir_fd: int
    generation_record_fd: int
    owned_manifest_fd: int
    interpreter_fd: int
    generation_id: UUID
    selector_sha256: str
    generation_record_sha256: str
    owned_manifest_sha256: str
    active: bool = True

    def assert_locked(self, home: Path, lock_set: Any) -> None:
        if not self.active or Path(home) != self.home:
            raise RuntimeError("bootstrap handle is inactive or bound to another home")
        _assert_lock(lock_set, home, "shared", "shared")

    def close(self) -> None:
        if not self.active:
            return
        for fd in (
            self.selector_fd, self.generation_dir_fd, self.generation_record_fd,
            self.owned_manifest_fd, self.interpreter_fd, self.install_lock_fd,
        ):
            try:
                os.close(fd)
            except OSError:
                pass
        self.active = False


RecoveryPhase = Literal["running", "closed_ready", "committed", "reconciliation", "finalized"]


@dataclass(slots=True)
class _RecoveryAuthority:
    relative_path: PurePosixPath
    fd: int
    root: bytearray
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[384]
    sha256: str
    consumed: bool = False

    def close(self) -> None:
        try:
            os.close(self.fd)
        finally:
            for i in range(len(self.root)):
                self.root[i] = 0


@dataclass(frozen=True, slots=True)
class _StorageBrokerRequest:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    image_path: Path
    mount_path: Path | None
    volume_name: str | None
    size: str | None
    transaction_id: UUID
    expected_encryption_uuid: str | None
    disposable: bool
    cleanup_approved: bool

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.operation not in {
            "create", "mount", "detach", "inspect-item", "delete-disposable-item"
        }:
            raise ValueError("invalid storage request")
        _validate_path(self.image_path)
        if self.mount_path is not None:
            _validate_path(self.mount_path)
        if self.expected_encryption_uuid is not None:
            UUID(self.expected_encryption_uuid)
        if self.size is not None and self.size not in {"256g", "64m"}:
            raise ValueError("unsupported image size")
        if self.operation == "delete-disposable-item" and not (self.disposable and self.cleanup_approved):
            raise ValueError("disposable deletion requires explicit cleanup approval")
        if self.operation == "create":
            expected_size = "64m" if self.disposable else "256g"
            expected_volume = "CORTEX_BRIDGE_SPIKE" if self.disposable else "CORTEX_BRIDGE_2026_09"
            if self.size != expected_size or self.volume_name != expected_volume:
                raise ValueError("create request does not match managed image contract")
        elif self.operation in {"mount", "detach"}:
            if not self.mount_path or not self.volume_name:
                raise ValueError("mount and detach require a managed mount and volume")
            if self.size is not None:
                raise ValueError("size is only valid for create")
        else:
            if self.size is not None or self.volume_name is not None or self.mount_path is not None:
                raise ValueError("inspect/delete request contains create or mount fields")


@dataclass(frozen=True, slots=True)
class _BrokerProbeRequest:
    schema_version: Literal[1]
    operation: Literal["probe-mounted-image"]
    transaction_id: UUID
    image_path: Path
    mount_path: Path
    expected_volume_name: str
    expected_volume_uuid: UUID
    expected_encryption_uuid: UUID
    image_identity: tuple[DarwinU32, int]
    mount_identity: tuple[DarwinU32, int, DarwinU32, DarwinU32]
    expected_mapping_count: Literal[1]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.operation != "probe-mounted-image":
            raise ValueError("invalid mounted-image probe")
        _validate_path(self.image_path)
        _validate_path(self.mount_path)
        if self.expected_mapping_count != 1:
            raise ValueError("mounted probe requires one mapping")
        if len(self.image_identity) != 2 or len(self.mount_identity) != 4:
            raise ValueError("invalid Darwin identity")


StorageLocalCode = Literal[
    "OK", "INVALID_REQUEST", "CLEANUP_NOT_AUTHORIZED", "RANDOM_GENERATION_FAILED",
    "HDIUTIL_FAILED", "IMAGE_ENCRYPTION_INVALID", "KEYCHAIN_ITEM_COLLISION",
    "KEYCHAIN_ITEM_NOT_FOUND", "KEYCHAIN_ITEM_AMBIGUOUS", "KEYCHAIN_INTERACTION_FORBIDDEN",
    "KEYCHAIN_SECRET_INVALID", "KEYCHAIN_FAILED", "MOUNT_MAPPING_INVALID",
    "MOUNT_CLEANUP_UNCLEAR", "SUPERVISION_UNRESOLVED", "CANCELLED", "INTERNAL_ERROR",
]


@dataclass(frozen=True, slots=True)
class StorageLocalResponse:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    code: StorageLocalCode
    encryption_uuid: str | None
    device: str | None
    item_count: int | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported response schema")
        if self.device is not None and self.device.startswith("/dev/"):
            raise ValueError("native device identity is private")
        if self.item_count is not None and self.item_count not in (0, 1):
            raise ValueError("item count must be zero or one")


@dataclass(frozen=True, slots=True)
class StorageEvidenceResponse:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    code: StorageLocalCode
    item_count: int | None


def to_storage_evidence_response(response: StorageLocalResponse) -> StorageEvidenceResponse:
    if response.device is not None and response.device.startswith("/dev/disk"):
        raise ValueError("native device identity cannot enter evidence")
    return StorageEvidenceResponse(1, response.operation, response.code, response.item_count)


@dataclass(frozen=True, slots=True)
class MountedImageProof:
    mount_path: Path
    image_dev_u32: DarwinU32
    image_ino: int
    mount_dev_u32: DarwinU32
    mount_ino: int
    mount_fsid0_u32: DarwinU32
    mount_fsid1_u32: DarwinU32
    volume_name: str
    volume_uuid: UUID
    encryption_uuid: UUID
    mapping_count: Literal[1]
    filesystem_type: Literal["apfs"]
    writable: Literal[True]
    encrypted: Literal[True]
    request_sha256: str


class LocalBrokerTerminalResponse(TypedDict):
    response_kind: Literal["local"]
    response: StorageLocalResponse


class MountedProofBrokerTerminalResponse(TypedDict):
    response_kind: Literal["mounted_image_proof"]
    response: MountedImageProof


BrokerTerminalResponse = LocalBrokerTerminalResponse | MountedProofBrokerTerminalResponse


@dataclass(frozen=True, slots=True)
class ClosedReadyResult:
    workflow_id: UUID
    generation: int
    outcome: Literal["success", "failure", "unresolved"]
    code: StorageLocalCode
    response: BrokerTerminalResponse | None
    command_sha256: str
    result_sha256: str
    closed_ready_sha256: str
    child_reaped: bool
    group_absent: bool
    native_cleanup_proven: bool
    reconciliation_required: bool

    def result_payload(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "generation": self.generation,
            "outcome": self.outcome,
            "code": self.code,
            "response": self.response,
            "command_sha256": self.command_sha256,
            "child_reaped": self.child_reaped,
            "group_absent": self.group_absent,
            "native_cleanup_proven": self.native_cleanup_proven,
            "reconciliation_required": self.reconciliation_required,
        }

    def verify_hashes(self) -> None:
        expected_result = digest("CORTEX-S3\x00RESULT\x00V1\x00", self.result_payload())
        if expected_result != self.result_sha256:
            raise ValueError("result digest mismatch")
        closed_payload = {
            "workflow_id": self.workflow_id,
            "generation": self.generation,
            "outcome": self.outcome,
            "code": self.code,
            "response": self.response,
            "command_sha256": self.command_sha256,
            "result_sha256": self.result_sha256,
            "child_reaped": self.child_reaped,
            "group_absent": self.group_absent,
            "native_cleanup_proven": self.native_cleanup_proven,
            "reconciliation_required": self.reconciliation_required,
        }
        expected_closed = digest("CORTEX-S3\x00CLOSED-READY\x00V1\x00", closed_payload)
        if expected_closed != self.closed_ready_sha256:
            raise ValueError("closed-ready digest mismatch")


@dataclass(frozen=True, slots=True)
class StorageWorkflowRecord:
    schema_version: Literal[1]
    state: LedgerState
    workflow_id: UUID
    generation: int
    operation: PublicStorageOperation | Literal["probe-mounted-image"]
    transaction_id: UUID
    canonical_request: Mapping[str, object]
    request_sha256: str
    broker_sha256: str
    broker_dev_u32: DarwinU32
    broker_ino: int
    broker_uid: int
    broker_mode: int
    owner_connection_nonce: str | None
    owner_peer_audit_sha256: str | None
    broker_pid: int | None
    broker_sid: int | None
    broker_pgid: int | None
    socket: BrokerSocketIdentity
    boot: BootIdentity
    effect_budget_ns: int
    cleanup_budget_ns: int
    recovery_authority_relative: PurePosixPath
    recovery_authority_dev_u32: DarwinU32
    recovery_authority_ino: int
    recovery_authority_sha256: str
    recovery_authority_consumed: bool
    started_monotonic_ns: int | None
    command_sha256: str | None
    unresolved_reason: UnresolvedReason | None
    result_sha256: str | None
    closed_ready_sha256: str | None
    child_reaped: bool
    group_absent: bool
    native_cleanup_proven: bool
    terminal_outcome: Literal["success", "failure", "unresolved"] | None
    terminal_code: StorageLocalCode | None
    terminal_response: BrokerTerminalResponse | None
    reconciliation_required: bool
    record_sha256: str


class StorageLockSetLike(Protocol):
    def assert_active(self, *, home: Path, required_install_mode: str, required_storage_mode: str) -> None: ...


def _assert_lock(lock_set: Any, home: Path, install_mode: str, storage_mode: str) -> None:
    if lock_set is None:
        raise RuntimeError("storage lock set is required")
    method = getattr(lock_set, "assert_active", None)
    if method is None:
        raise RuntimeError("invalid storage lock set")
    try:
        method(home=Path(home), required_install_mode=install_mode, required_storage_mode=storage_mode)
    except TypeError:
        method(Path(home), install_mode, storage_mode)


def _validate_path(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("storage path must be absolute")
    text = str(path)
    if "\x00" in text or any(ord(c) < 32 for c in text):
        raise ValueError("storage path contains control bytes")
    if any(part in {"", ".", ".."} for part in text.split("/")[1:]):
        raise ValueError("storage path contains invalid component")
    if text.startswith("/dev/disk"):
        raise ValueError("device paths are never accepted")


def _as_json(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (Path, PurePosixPath)):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: _as_json(item) for key, item in asdict(value).items() if key != "_closed"}
    if isinstance(value, Mapping):
        return {str(k): _as_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_json(v) for v in value]
    return value


def _request_projection(request: _StorageBrokerRequest | _BrokerProbeRequest) -> dict[str, Any]:
    return cast(dict[str, Any], _as_json(request))


def request_sha256(request: _StorageBrokerRequest | _BrokerProbeRequest) -> str:
    return digest("CORTEX-S3\x00REQUEST\x00V1\x00", _request_projection(request))


def command_sha256(
    *, workflow_id: UUID, generation: int, operation: str, request_sha: str,
    broker_sha: str, boot: BootIdentity, effect_budget_ns: int,
    cleanup_budget_ns: int, connection_nonce: str, peer_audit_sha256: str,
) -> str:
    return digest(
        "CORTEX-S3\x00COMMAND\x00V1\x00",
        {
            "workflow_id": workflow_id, "generation": generation, "operation": operation,
            "request_sha256": request_sha, "broker_sha256": broker_sha,
            "boot_seconds": boot.seconds, "boot_microseconds": boot.microseconds,
            "effect_budget_ns": effect_budget_ns, "cleanup_budget_ns": cleanup_budget_ns,
            "connection_nonce": connection_nonce, "peer_audit_sha256": peer_audit_sha256,
        },
    )


def encode_frame(envelope: Mapping[str, Any]) -> bytes:
    encoded = canonical_json(envelope)
    if len(encoded) > FRAME_LIMIT:
        raise ValueError("protocol frame exceeds 16 KiB")
    return struct.pack(">I", len(encoded)) + encoded


def decode_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < 4:
        raise ValueError("truncated frame prefix")
    length = struct.unpack(">I", frame[:4])[0]
    if length > FRAME_LIMIT or len(frame) != 4 + length:
        raise ValueError("invalid frame length")
    payload = frame[4:]
    return _decode_strict_json(payload)


def _decode_strict_json(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8", "strict")
        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            pairs_seen: set[str] = set()
            for key, value in items:
                if key in pairs_seen:
                    raise ValueError("duplicate object key")
                pairs_seen.add(key)
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(ValueError("float forbidden")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid canonical JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("frame envelope must be an object")
    if canonical_json(value) != payload:
        raise ValueError("JSON is not canonical")
    return value


def _safe_boot_identity() -> BootIdentity:
    # Managed macOS handoffs require the exact kernel value, never a rounded
    # wall-clock-minus-uptime estimate or an optional third-party sysctl module.
    if sys.platform == "darwin":
        return _current_boot_identity_exact()
    try:
        import sysctl  # type: ignore[import-not-found]
        value = sysctl.sysctlbyname("kern.boottime")
        return BootIdentity(int(value.tv_sec), int(value.tv_usec))
    except Exception:
        now = time.time_ns() // 1_000_000_000
        uptime = int(time.monotonic())
        return BootIdentity(max(0, now - uptime), 0)


class StorageBrokerError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class _AuthenticatedHello:
    connection_nonce: str
    peer_audit_sha256: str
    boot: BootIdentity


def _deadline_timeout(deadline_ns: int) -> float:
    if type(deadline_ns) is not int:
        raise StorageBrokerError("DEADLINE_EXPIRED")
    remaining = deadline_ns - time.monotonic_ns()
    if remaining <= 0:
        raise StorageBrokerError("DEADLINE_EXPIRED")
    if remaining > PROTOCOL_IO_MAX_NS:
        raise StorageBrokerError("BUDGET_EXCEEDED")
    return remaining / 1_000_000_000


def _read_exact_before_deadline(channel: socket.socket, count: int, deadline_ns: int) -> bytes:
    output = bytearray()
    while len(output) < count:
        readable, _, _ = select.select([channel], [], [], _deadline_timeout(deadline_ns))
        if not readable:
            raise StorageBrokerError("DEADLINE_EXPIRED")
        try:
            chunk = channel.recv(count - len(output))
        except InterruptedError:
            continue
        if not chunk:
            raise StorageBrokerError("INVALID_FRAME")
        output.extend(chunk)
    return bytes(output)


def _read_frame_before_deadline(channel: socket.socket, *, deadline_ns: int) -> dict[str, Any]:
    prefix = _read_exact_before_deadline(channel, 4, deadline_ns)
    length = struct.unpack(">I", prefix)[0]
    if length > FRAME_LIMIT:
        raise StorageBrokerError("INVALID_FRAME")
    payload = _read_exact_before_deadline(channel, length, deadline_ns)
    try:
        return decode_frame(prefix + payload)
    except ValueError as exc:
        raise StorageBrokerError("INVALID_FRAME") from exc


def _write_frame_before_deadline(
    channel: socket.socket, envelope: Mapping[str, Any], *, deadline_ns: int,
) -> None:
    frame = encode_frame(envelope)
    offset = 0
    while offset < len(frame):
        _, writable, _ = select.select([], [channel], [], _deadline_timeout(deadline_ns))
        if not writable:
            raise StorageBrokerError("DEADLINE_EXPIRED")
        try:
            written = channel.send(frame[offset:])
        except InterruptedError:
            continue
        except BrokenPipeError as exc:
            raise StorageBrokerError("CHANNEL_LOST") from exc
        if written <= 0:
            raise StorageBrokerError("CHANNEL_LOST")
        offset += written


def _fd_sha256(fd: int) -> str:
    digest_value = hashlib.sha256()
    offset = 0
    while True:
        chunk = os.pread(fd, 1024 * 1024, offset)
        if not chunk:
            return digest_value.hexdigest()
        digest_value.update(chunk)
        offset += len(chunk)


def _reattest_executable(executable: AttestedBrokerExecutable) -> os.stat_result:
    if executable._closed:
        raise StorageBrokerError("AUTH_FAILED")
    try:
        retained = os.fstat(executable.fd)
    except OSError as exc:
        raise StorageBrokerError("AUTH_FAILED") from exc
    expected = (
        int(executable.dev_u32), executable.ino, executable.uid, executable.mode,
        executable.sha256,
    )
    retained_observed = (
        retained.st_dev & 0xFFFFFFFF, retained.st_ino, retained.st_uid,
        stat.S_IMODE(retained.st_mode), _fd_sha256(executable.fd),
    )
    if not stat.S_ISREG(retained.st_mode) or retained_observed != expected:
        raise StorageBrokerError("AUTH_FAILED")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        path_fd = os.open(executable.path, flags)
    except OSError as exc:
        raise StorageBrokerError("AUTH_FAILED") from exc
    try:
        path_details = os.fstat(path_fd)
        path_observed = (
            path_details.st_dev & 0xFFFFFFFF, path_details.st_ino, path_details.st_uid,
            stat.S_IMODE(path_details.st_mode), _fd_sha256(path_fd),
        )
        if not stat.S_ISREG(path_details.st_mode) or path_observed != expected:
            raise StorageBrokerError("AUTH_FAILED")
    finally:
        os.close(path_fd)
    return retained


def _is_uint64(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_UINT64


def _is_lower_hex(value: Any, byte_count: int) -> bool:
    if not isinstance(value, str) or len(value) != byte_count * 2:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _current_boot_identity_exact() -> BootIdentity:
    if sys.platform != "darwin":
        raise StorageBrokerError("AUTH_FAILED", "kern.boottime is unavailable")

    class Timeval(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_int)]

    value = Timeval()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    libc = ctypes.CDLL(None, use_errno=True)
    sysctlbyname = libc.sysctlbyname
    sysctlbyname.argtypes = [
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    sysctlbyname.restype = ctypes.c_int
    if (
        sysctlbyname(b"kern.boottime", ctypes.byref(value), ctypes.byref(size), None, 0) != 0
        or size.value != ctypes.sizeof(value)
        or value.tv_sec <= 0
        or not 0 <= value.tv_usec < 1_000_000
    ):
        raise StorageBrokerError("AUTH_FAILED", "kern.boottime is unavailable")
    return BootIdentity(value.tv_sec, value.tv_usec)


def _validate_pre_effect_hello(
    envelope: Mapping[str, Any], *, lock_set: Any, home: Path,
    executable: AttestedBrokerExecutable, workflow_id: UUID, generation: int,
) -> _AuthenticatedHello:
    _assert_lock(lock_set, Path(home), "shared", "shared")
    _reattest_executable(executable)
    if set(envelope) != {
        "version", "type", "workflow_id", "generation", "connection_nonce", "cursor", "payload",
    }:
        raise StorageBrokerError("AUTH_FAILED")
    if (
        not _is_uint64(envelope.get("version"))
        or envelope.get("version") != 1
        or envelope.get("type") != "HELLO"
        or envelope.get("workflow_id") != str(workflow_id)
        or not _is_uint64(envelope.get("generation"))
        or envelope.get("generation") != generation
        or not _is_uint64(envelope.get("cursor"))
        or envelope.get("cursor") != 0
        or not _is_uint64(generation)
        or not _is_lower_hex(envelope.get("connection_nonce"), 32)
        or set(cast(str, envelope.get("connection_nonce"))) == {"0"}
    ):
        raise StorageBrokerError("AUTH_FAILED")
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping) or set(payload) != {
        "broker_dev_u32", "broker_ino", "broker_uid", "broker_mode", "broker_sha256",
        "boot_seconds", "boot_microseconds", "peer_audit_sha256",
    }:
        raise StorageBrokerError("AUTH_FAILED")
    for field in (
        "broker_dev_u32", "broker_ino", "broker_uid", "broker_mode",
        "boot_seconds", "boot_microseconds",
    ):
        if not _is_uint64(payload.get(field)):
            raise StorageBrokerError("AUTH_FAILED")
    if not _is_lower_hex(payload.get("broker_sha256"), 32) or not _is_lower_hex(
        payload.get("peer_audit_sha256"), 32
    ):
        raise StorageBrokerError("AUTH_FAILED")
    identity = (
        payload["broker_dev_u32"], payload["broker_ino"], payload["broker_uid"],
        payload["broker_mode"], payload["broker_sha256"],
    )
    expected_identity = (
        int(executable.dev_u32), executable.ino, executable.uid, executable.mode,
        executable.sha256,
    )
    if identity != expected_identity:
        raise StorageBrokerError("AUTH_FAILED")
    boot = BootIdentity(payload["boot_seconds"], payload["boot_microseconds"])
    if boot.microseconds >= 1_000_000:
        raise StorageBrokerError("AUTH_FAILED")
    current_boot = _current_boot_identity_exact()
    if boot != current_boot:
        raise StorageBrokerError("AUTH_FAILED")
    return _AuthenticatedHello(
        connection_nonce=cast(str, envelope["connection_nonce"]),
        peer_audit_sha256=cast(str, payload["peer_audit_sha256"]),
        boot=boot,
    )


class _StartGrantChannel:
    """Own the launcher's anonymous capability socket; emit at most one grant.

    This only authorizes a matching START. The production session owner must
    separately prove exec/HELLO and must never retry an uncertain grant write.
    """
    def __init__(self, channel: socket.socket):
        if (channel.family != socket.AF_UNIX or channel.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
                or channel.getsockname() not in ("", b"") or channel.getpeername() not in ("", b"")):
            raise StorageBrokerError("INVALID_START_CAPABILITY")
        self.channel = channel
        self.consumed = False
        channel.setblocking(False)

    def send_locked(self, lock_set: Any, *, ledger: StorageWorkflowLedger,
                    record: StorageWorkflowRecord, executable: AttestedBrokerExecutable,
                    hello: Mapping[str, Any]) -> None:
        if self.consumed:
            raise StorageBrokerError("REPLAY")
        _assert_lock(lock_set, ledger.home, "shared",
                     "shared" if record.operation == "probe-mounted-image" else "exclusive")
        persisted = _find_record(ledger.load_all_locked(lock_set), record.workflow_id, record.generation)
        if persisted != record or persisted.state != LedgerState.OPEN_RUNNING:
            raise StorageBrokerError("INVALID_STATE")
        accepted = _validate_pre_effect_hello(hello, lock_set=lock_set, home=ledger.home,
            executable=executable, workflow_id=record.workflow_id, generation=record.generation)
        if (record.owner_connection_nonce != accepted.connection_nonce
                or record.owner_peer_audit_sha256 != accepted.peer_audit_sha256
                or record.boot != accepted.boot
                or (record.broker_sha256, int(record.broker_dev_u32), record.broker_ino, record.broker_uid, record.broker_mode)
                   != (executable.sha256, int(executable.dev_u32), executable.ino, executable.uid, executable.mode)):
            raise StorageBrokerError("AUTH_FAILED")
        _validate_budgets(record.effect_budget_ns, record.cleanup_budget_ns)
        grant = dict(version=1, type="START_GRANT", workflow_id=str(record.workflow_id),
            generation=record.generation, record_sha256=record.record_sha256,
            request_sha256=record.request_sha256, operation=record.operation,
            effect_budget_ns=record.effect_budget_ns, cleanup_budget_ns=record.cleanup_budget_ns,
            boot_seconds=record.boot.seconds, boot_microseconds=record.boot.microseconds,
            connection_nonce=accepted.connection_nonce, peer_audit_sha256=accepted.peer_audit_sha256)
        self.consumed = True
        try:
            _write_frame_before_deadline(self.channel, grant,
                                        deadline_ns=time.monotonic_ns() + PROTOCOL_IO_MAX_NS)
        except OSError as error:
            raise StorageBrokerError("CHANNEL_LOST") from error
        finally:
            # Closing the owned endpoint prevents constructing a second sender
            # on the same capability after a partial or uncertain write.
            self.channel.close()


class StorageWorkflowLedger:
    """Atomic JSON ledger with immutable closed records."""

    def __init__(self, home: Path, *, path: Path | None = None):
        self.home = Path(home)
        self.path = path or self.home / "storage" / "storage-workflows.jsonl"

    def _load_raw(self) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        records: list[dict[str, Any]] = []
        for line in lines:
            if not line:
                continue
            value = _decode_strict_json(line.encode("utf-8"))
            records.append(value)
        return records

    def _write_raw(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}")
        data = b"".join(canonical_json(record) + b"\n" for record in records)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short ledger write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, self.path)
        parent_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    def _save(self, records: list[StorageWorkflowRecord]) -> None:
        self._write_raw([_as_json(record) for record in records])

    def load_all_locked(self, lock_set: Any) -> tuple[StorageWorkflowRecord, ...]:
        _assert_lock(lock_set, self.home, "shared", "shared")
        return tuple(_record_from_dict(raw) for raw in self._load_raw())

    def prepare_locked(
        self, lock_set: Any, request: _StorageBrokerRequest | _BrokerProbeRequest,
        executable: AttestedBrokerExecutable, socket_identity: BrokerSocketIdentity,
        boot: BootIdentity, recovery: _RecoveryAuthority, *,
        effect_budget_ns: int, cleanup_budget_ns: int,
    ) -> StorageWorkflowRecord:
        required_storage_mode = "shared" if isinstance(request, _BrokerProbeRequest) else "exclusive"
        _assert_lock(lock_set, self.home, "shared", required_storage_mode)
        _validate_budgets(effect_budget_ns, cleanup_budget_ns)
        records = list(self.load_all_locked(lock_set))
        generation = max((r.generation for r in records), default=0) + 1
        if generation > MAX_UINT64:
            raise StorageBrokerError("RANDOM_GENERATION_FAILED")
        projection = _request_projection(request)
        request_hash = request_sha256(request)
        workflow_id = uuid4()
        transaction_id = request.transaction_id
        record_data: dict[str, Any] = {
            "schema_version": 1, "state": LedgerState.OPEN_PREPARED,
            "workflow_id": workflow_id, "generation": generation,
            "operation": projection["operation"], "transaction_id": transaction_id,
            "canonical_request": projection, "request_sha256": request_hash,
            "broker_sha256": executable.sha256, "broker_dev_u32": int(executable.dev_u32),
            "broker_ino": executable.ino, "broker_uid": executable.uid,
            "broker_mode": executable.mode, "owner_connection_nonce": None,
            "owner_peer_audit_sha256": None, "broker_pid": None, "broker_sid": None,
            "broker_pgid": None, "socket": socket_identity, "boot": boot,
            "effect_budget_ns": effect_budget_ns, "cleanup_budget_ns": cleanup_budget_ns,
            "recovery_authority_relative": recovery.relative_path,
            "recovery_authority_dev_u32": int(recovery.dev_u32),
            "recovery_authority_ino": recovery.ino, "recovery_authority_sha256": recovery.sha256,
            "recovery_authority_consumed": False, "started_monotonic_ns": None,
            "command_sha256": None, "unresolved_reason": None, "result_sha256": None,
            "closed_ready_sha256": None, "child_reaped": False, "group_absent": False,
            "native_cleanup_proven": False, "terminal_outcome": None, "terminal_code": None,
            "terminal_response": None, "reconciliation_required": False,
        }
        record_data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", record_data)
        record = _record_from_dict(record_data)
        self._save(records + [record])
        return record

    def _replace(self, lock_set: Any, updated: StorageWorkflowRecord) -> StorageWorkflowRecord:
        records = list(self.load_all_locked(lock_set))
        for index, record in enumerate(records):
            if record.workflow_id == updated.workflow_id and record.generation == updated.generation:
                records[index] = updated
                self._save(records)
                return updated
        raise StorageBrokerError("LEDGER_RECORD_NOT_FOUND")

    def mark_running_before_start_locked(
        self, lock_set: Any, workflow_id: UUID, generation: int, *, broker_pid: int,
        broker_sid: int, broker_pgid: int, owner_connection_nonce: str,
        owner_peer_audit_sha256: str,
    ) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "shared")
        record = _find_record(self.load_all_locked(lock_set), workflow_id, generation)
        if record.operation != "probe-mounted-image":
            _assert_lock(lock_set, self.home, "shared", "exclusive")
        if record.state != LedgerState.OPEN_PREPARED:
            raise StorageBrokerError("INVALID_STATE")
        command = command_sha256(
            workflow_id=record.workflow_id, generation=record.generation,
            operation=record.operation, request_sha=record.request_sha256,
            broker_sha=record.broker_sha256, boot=record.boot,
            effect_budget_ns=record.effect_budget_ns, cleanup_budget_ns=record.cleanup_budget_ns,
            connection_nonce=owner_connection_nonce, peer_audit_sha256=owner_peer_audit_sha256,
        )
        data = _as_json(record)
        data.update({
            "state": LedgerState.OPEN_RUNNING, "broker_pid": broker_pid,
            "broker_sid": broker_sid, "broker_pgid": broker_pgid,
            "owner_connection_nonce": owner_connection_nonce,
            "owner_peer_audit_sha256": owner_peer_audit_sha256,
            "started_monotonic_ns": time.monotonic_ns(), "command_sha256": command,
        })
        data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", {k: v for k, v in data.items() if k != "record_sha256"})
        return self._replace(lock_set, _record_from_dict(data))

    def close_preexec_failure_locked(self, lock_set: Any, workflow_id: UUID, generation: int) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        record = _find_record(self.load_all_locked(lock_set), workflow_id, generation)
        if record.state != LedgerState.OPEN_PREPARED:
            raise StorageBrokerError("INVALID_STATE")
        data = _as_json(record)
        data.update({"state": LedgerState.CLOSED_FAILURE, "terminal_outcome": "failure", "terminal_code": "SUPERVISION_UNRESOLVED"})
        data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", {k: v for k, v in data.items() if k != "record_sha256"})
        return self._replace(lock_set, _record_from_dict(data))

    def mark_unresolved_locked(self, lock_set: Any, workflow_id: UUID, generation: int, reason: UnresolvedReason) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        record = _find_record(self.load_all_locked(lock_set), workflow_id, generation)
        if record.state in {LedgerState.CLOSED_SUCCESS, LedgerState.CLOSED_FAILURE}:
            raise StorageBrokerError("INVALID_STATE")
        data = _as_json(record)
        data.update({"state": LedgerState.OPEN_UNRESOLVED, "unresolved_reason": reason})
        data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", {k: v for k, v in data.items() if k != "record_sha256"})
        return self._replace(lock_set, _record_from_dict(data))

    def close_from_ready_locked(self, lock_set: Any, result: ClosedReadyResult) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "shared")
        result.verify_hashes()
        record = _find_record(self.load_all_locked(lock_set), result.workflow_id, result.generation)
        if record.operation != "probe-mounted-image":
            _assert_lock(lock_set, self.home, "shared", "exclusive")
        if record.state != LedgerState.OPEN_RUNNING:
            raise StorageBrokerError("INVALID_STATE")
        if result.command_sha256 != record.command_sha256:
            raise StorageBrokerError("PROTOCOL_ERROR")
        expected_reconciliation = record.operation in {
            "create", "mount", "detach", "delete-disposable-item"
        }
        if result.reconciliation_required != expected_reconciliation:
            raise StorageBrokerError("PROTOCOL_ERROR")
        if result.outcome == "success" and result.code != "OK":
            raise StorageBrokerError("PROTOCOL_ERROR")
        if result.outcome == "unresolved":
            raise StorageBrokerError("PROTOCOL_ERROR")
        state = LedgerState.CLOSED_SUCCESS if result.outcome == "success" else LedgerState.CLOSED_FAILURE
        data = _as_json(record)
        data.update({
            "state": state, "result_sha256": result.result_sha256,
            "closed_ready_sha256": result.closed_ready_sha256,
            "child_reaped": result.child_reaped, "group_absent": result.group_absent,
            "native_cleanup_proven": result.native_cleanup_proven,
            "terminal_outcome": result.outcome, "terminal_code": result.code,
            "terminal_response": result.response,
            "reconciliation_required": result.reconciliation_required,
        })
        data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", {k: v for k, v in data.items() if k != "record_sha256"})
        return self._replace(lock_set, _record_from_dict(data))

    def consume_recovery_authority_after_finalized_locked(
        self, lock_set: Any, workflow_id: UUID, generation: int, *, finalized_record_sha256: str,
    ) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        record = _find_record(self.load_all_locked(lock_set), workflow_id, generation)
        if record.record_sha256 != finalized_record_sha256 or record.state not in {LedgerState.CLOSED_SUCCESS, LedgerState.CLOSED_FAILURE}:
            raise StorageBrokerError("INVALID_STATE")
        data = _as_json(record)
        data["recovery_authority_consumed"] = True
        data["record_sha256"] = digest("CORTEX-S3\x00LEDGER\x00V1\x00", {k: v for k, v in data.items() if k != "record_sha256"})
        return self._replace(lock_set, _record_from_dict(data))


class StorageBrokerTransport(Protocol):
    def __call__(self, request: _StorageBrokerRequest | _BrokerProbeRequest, record: StorageWorkflowRecord) -> ClosedReadyResult | BrokerTerminalResponse: ...


class _BrokerLaunchOwner:
    """Own a real broker process/channel; never signal native children.

    Closing the owner link delegates cleanup to the broker. Callers retain this
    object while its process is alive; a closed link is not proof of cleanup.
    """

    def __init__(self, *, home: Path, executable: AttestedBrokerExecutable,
                 ledger: StorageWorkflowLedger):
        self.home, self.executable, self.ledger = Path(home), executable, ledger
        self.process: subprocess.Popen | None = None
        self.channel: socket.socket | None = None
        self.record: StorageWorkflowRecord | None = None
        self.recovery: _RecoveryAuthority | None = None
        self.attempted = False
        self.receive_cursor = 1
        self.socket_directory: Path | None = None

    def close_channel(self) -> None:
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        if self.recovery is not None:
            self.recovery.close()
            self.recovery = None

    def start_locked(self, lock_set: Any, request: _StorageBrokerRequest, *,
                     effect_budget_ns: int, cleanup_budget_ns: int) -> StorageWorkflowRecord:
        if self.attempted:
            raise StorageBrokerError("REPLAY")
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        _validate_budgets(effect_budget_ns, cleanup_budget_ns)
        _reattest_executable(self.executable)
        self.attempted = True
        listener = capability_parent = capability_child = None
        recovery_read = recovery_write = None
        try:
            self.recovery = _new_recovery_authority(self.home)
            # Darwin sockaddr_un cannot hold long external-volume/home paths.
            # Only this private ephemeral IPC directory is outside storage;
            # retain it for original-broker recovery until finalization.
            self.socket_directory = Path(tempfile.mkdtemp(prefix="cx-b-", dir="/private/tmp"))
            path = self.socket_directory / "s"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            os.chmod(path, 0o600, follow_symlinks=False)
            listener.listen(1)
            details = path.lstat()
            identity = BrokerSocketIdentity(path, DarwinU32(details.st_dev & 0xffffffff),
                details.st_ino, details.st_uid, stat.S_IMODE(details.st_mode))
            self.record = self.ledger.prepare_locked(lock_set, request, self.executable,
                identity, _current_boot_identity_exact(), self.recovery,
                effect_budget_ns=effect_budget_ns, cleanup_budget_ns=cleanup_budget_ns)
            capability_parent, capability_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            recovery_read, recovery_write = os.pipe()
            if os.write(recovery_write, self.recovery.root) != 32:
                raise StorageBrokerError("BROKER_UNAVAILABLE")
            os.close(recovery_write)
            recovery_write = None
            # Reattest immediately before path-based exec under the install lock.
            _assert_lock(lock_set, self.home, "shared", "exclusive")
            _reattest_executable(self.executable)
            # CPython's fork_exec/Popen path observes its close-on-exec error
            # pipe before returning; pass_fds + start_new_session select it.
            # No Python preexec_fn or inherited environment is used.
            self.process = subprocess.Popen([
                str(self.executable.path), "--broker-fd", str(listener.fileno()),
                "--start-capability-fd", str(capability_child.fileno()),
                "--recovery-authority-fd", str(recovery_read),
                "--workflow-id", str(self.record.workflow_id),
                "--generation", str(self.record.generation)],
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(listener.fileno(), capability_child.fileno(), recovery_read),
                close_fds=True, start_new_session=True)
            capability_child.close()
            capability_child = None
            os.close(recovery_read)
            recovery_read = None
            listener.close()
            listener = None
            self.channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.channel.settimeout(PROTOCOL_IO_MAX_NS / 1_000_000_000)
            self.channel.connect(str(path))
            self.channel.setblocking(False)
            hello = _read_frame_before_deadline(self.channel,
                deadline_ns=time.monotonic_ns() + PROTOCOL_IO_MAX_NS)
            # Darwin sys/un.h: SOL_LOCAL=0, LOCAL_PEERPID=2. Check the
            # accepted process after HELLO: before accept, an inherited listener
            # can still expose its creator's PID. Never weaken the expected PID.
            if self.channel.getsockopt(0, 2) != self.process.pid:
                raise StorageBrokerError("AUTH_FAILED")
            uid, gid = ctypes.c_uint(), ctypes.c_uint()
            getpeereid = ctypes.CDLL(None, use_errno=True).getpeereid
            getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
            getpeereid.restype = ctypes.c_int
            if getpeereid(self.channel.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0 or uid.value != os.getuid():
                raise StorageBrokerError("AUTH_FAILED")
            accepted = _validate_pre_effect_hello(hello, lock_set=lock_set, home=self.home,
                executable=self.executable, workflow_id=self.record.workflow_id,
                generation=self.record.generation)
            pid = self.process.pid
            sid, pgid = os.getsid(pid), os.getpgid(pid)
            if sid != pid or pgid != pid:
                raise StorageBrokerError("AUTH_FAILED")
            self.record = self.ledger.mark_running_before_start_locked(lock_set,
                self.record.workflow_id, self.record.generation, broker_pid=pid,
                broker_sid=sid, broker_pgid=pgid, owner_connection_nonce=accepted.connection_nonce,
                owner_peer_audit_sha256=accepted.peer_audit_sha256)
            _StartGrantChannel(capability_parent).send_locked(lock_set, ledger=self.ledger,
                record=self.record, executable=self.executable, hello=hello)
            _write_frame_before_deadline(self.channel, dict(version=1, type="START",
                workflow_id=str(self.record.workflow_id), generation=self.record.generation,
                connection_nonce=accepted.connection_nonce, cursor=0,
                payload=dict(request=_request_projection(request), request_sha256=self.record.request_sha256,
                    effect_budget_ns=effect_budget_ns, cleanup_budget_ns=cleanup_budget_ns)),
                deadline_ns=time.monotonic_ns() + PROTOCOL_IO_MAX_NS)
            return self.record
        except Exception as error:
            self.close_channel()
            if self.record is not None:
                # Reload: a durable replacement may have succeeded even when a
                # later fsync/return failed. Never infer PREPARED from stale RAM.
                current = _find_record(self.ledger.load_all_locked(lock_set),
                    self.record.workflow_id, self.record.generation)
                if current.state == LedgerState.OPEN_PREPARED:
                    self.record = self.ledger.close_preexec_failure_locked(lock_set,
                        current.workflow_id, current.generation)
                elif current.state in {LedgerState.OPEN_RUNNING, LedgerState.OPEN_UNRESOLVED}:
                    self.record = self.ledger.mark_unresolved_locked(lock_set,
                        current.workflow_id, current.generation, UnresolvedReason.CHANNEL_LOST)
            if isinstance(error, StorageBrokerError):
                raise
            raise StorageBrokerError("BROKER_UNAVAILABLE") from error
        finally:
            for channel in (listener, capability_parent, capability_child):
                if channel is not None:
                    channel.close()
            for descriptor in (recovery_read, recovery_write):
                if descriptor is not None:
                    os.close(descriptor)

    def receive_frame(self) -> dict[str, Any]:
        if self.channel is None or self.record is None:
            raise StorageBrokerError("CHANNEL_LOST")
        frame = _read_frame_before_deadline(self.channel,
            deadline_ns=time.monotonic_ns() + PROTOCOL_IO_MAX_NS)
        if (set(frame) != {"version", "type", "workflow_id", "generation", "connection_nonce", "cursor", "payload"}
                or type(frame["version"]) is not int or frame["version"] != 1
                or frame["workflow_id"] != str(self.record.workflow_id)
                or type(frame["generation"]) is not int or frame["generation"] != self.record.generation
                or frame["connection_nonce"] != self.record.owner_connection_nonce
                or type(frame["cursor"]) is not int or frame["cursor"] != self.receive_cursor
                or not isinstance(frame["payload"], dict)):
            raise StorageBrokerError("PROTOCOL_ERROR")
        self.receive_cursor += 1
        return frame


class StorageBrokerClient:
    def __init__(self, *, home: Path, executable: AttestedBrokerExecutable, ledger: StorageWorkflowLedger, transport: StorageBrokerTransport | None = None) -> None:
        self.home = Path(home)
        self.executable = executable
        self.ledger = ledger
        self.transport = transport
        self._native_sessions: list[_BrokerLaunchOwner] = []

    def _run_locked(self, lock_set: Any, request: _StorageBrokerRequest, *, effect_budget_ns: int, cleanup_budget_ns: int) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        if request.operation not in {"create", "mount", "detach", "inspect-item", "delete-disposable-item"}:
            raise StorageBrokerError("INVALID_REQUEST")
        _validate_budgets(effect_budget_ns, cleanup_budget_ns)
        if self.transport is None:
            return self._run_native_locked(lock_set, request,
                effect_budget_ns=effect_budget_ns, cleanup_budget_ns=cleanup_budget_ns)
        socket_identity = _socket_identity(self.home)
        recovery = _new_recovery_authority(self.home)
        record = self.ledger.prepare_locked(
            lock_set, request, self.executable, socket_identity, _safe_boot_identity(), recovery,
            effect_budget_ns=effect_budget_ns, cleanup_budget_ns=cleanup_budget_ns,
        )
        nonce = secrets.token_hex(16)
        audit = hashlib.sha256(canonical_json({"pid": os.getpid(), "uid": os.getuid()})).hexdigest()
        running = self.ledger.mark_running_before_start_locked(
            lock_set, record.workflow_id, record.generation, broker_pid=os.getpid(),
            broker_sid=os.getsid(0), broker_pgid=os.getpgrp(), owner_connection_nonce=nonce,
            owner_peer_audit_sha256=audit,
        )
        try:
            response = self.transport(request, running)
            if isinstance(response, ClosedReadyResult):
                ready = response
            else:
                ready = _success_result(running, response)
            return self.ledger.close_from_ready_locked(lock_set, ready)
        except StorageBrokerError as exc:
            if exc.code in {"PROTOCOL_ERROR", "BROKER_LOST"}:
                self.ledger.mark_unresolved_locked(
                    lock_set, running.workflow_id, running.generation,
                    UnresolvedReason.PROTOCOL_ERROR if exc.code == "PROTOCOL_ERROR" else UnresolvedReason.BROKER_LOST,
                )
            raise
        except ValueError as exc:
            self.ledger.mark_unresolved_locked(
                lock_set, running.workflow_id, running.generation, UnresolvedReason.PROTOCOL_ERROR
            )
            raise StorageBrokerError("PROTOCOL_ERROR") from exc
        except Exception as exc:
            self.ledger.mark_unresolved_locked(lock_set, running.workflow_id, running.generation, UnresolvedReason.BROKER_LOST)
            raise StorageBrokerError("BROKER_LOST") from exc
        finally:
            recovery.close()

    def _run_native_locked(self, lock_set: Any, request: _StorageBrokerRequest, *,
                           effect_budget_ns: int, cleanup_budget_ns: int) -> StorageWorkflowRecord:
        owner = _BrokerLaunchOwner(home=self.home, executable=self.executable, ledger=self.ledger)
        self._native_sessions.append(owner)
        try:
            owner.start_locked(lock_set, request, effect_budget_ns=effect_budget_ns,
                               cleanup_budget_ns=cleanup_budget_ns)
            frame = owner.receive_frame()
            if frame["type"] == "PROTOCOL_ERROR" and set(frame["payload"]) == {"code"}:
                code = frame["payload"]["code"]
                if code in {"INVALID_FRAME", "STALE_GENERATION", "AUTH_FAILED", "REPLAY", "INVALID_STATE"}:
                    raise StorageBrokerError("PROTOCOL_ERROR", f"Native broker rejected START: {code}")
            # Terminal RESULT/CLOSED_READY/COMMIT handling must be implemented
            # before this path can return success. Never use _success_result on
            # raw native frames or infer completion from process exit.
            raise StorageBrokerError("PROTOCOL_ERROR")
        except Exception:
            if owner.record is not None:
                current = _find_record(self.ledger.load_all_locked(lock_set),
                    owner.record.workflow_id, owner.record.generation)
                if current.state in {LedgerState.OPEN_RUNNING, LedgerState.OPEN_UNRESOLVED}:
                    owner.record = self.ledger.mark_unresolved_locked(lock_set,
                        current.workflow_id, current.generation, UnresolvedReason.PROTOCOL_ERROR)
            raise
        finally:
            owner.close_channel()
            if owner.process is not None:
                try:
                    owner.process.wait(timeout=PROTOCOL_IO_MAX_NS / 1_000_000_000)
                except subprocess.TimeoutExpired:
                    # Retain original ownership for recovery. No TERM/KILL and
                    # no success/cleanup inference on observation timeout.
                    pass
            if owner.process is None or owner.process.returncode is not None:
                self._native_sessions.remove(owner)

    def _probe_mounted_image_locked(self, lock_set: Any, *, image_path: Path, mount_path: Path, expected_volume_name: str, expected_volume_uuid: UUID, expected_encryption_uuid: UUID, image_identity: tuple[DarwinU32, int], mount_identity: tuple[DarwinU32, int, DarwinU32, DarwinU32], expected_mapping_count: Literal[1], effect_budget_ns: int) -> MountedImageProof:
        _assert_lock(lock_set, self.home, "shared", "shared")
        request = _BrokerProbeRequest(1, "probe-mounted-image", uuid4(), image_path, mount_path, expected_volume_name, expected_volume_uuid, expected_encryption_uuid, image_identity, mount_identity, expected_mapping_count)
        if self.transport is None:
            raise StorageBrokerError("BROKER_UNAVAILABLE")
        # The private probe is deliberately not routed through the public
        # operation constructor.  A test transport may return a proof arm.
        record = self._run_probe_record(lock_set, request, effect_budget_ns)
        running = self.ledger.mark_running_before_start_locked(
            lock_set, record.workflow_id, record.generation, broker_pid=os.getpid(),
            broker_sid=os.getsid(0), broker_pgid=os.getpgrp(),
            owner_connection_nonce=secrets.token_hex(16),
            owner_peer_audit_sha256=hashlib.sha256(
                canonical_json({"pid": os.getpid(), "uid": os.getuid()})
            ).hexdigest(),
        )
        try:
            response = self.transport(request, running)
            if isinstance(response, dict) and response.get("response_kind") == "mounted_image_proof":
                proof = response.get("response")
            elif isinstance(response, MountedImageProof):
                proof = response
            else:
                raise StorageBrokerError("PROTOCOL_ERROR")
            if not isinstance(proof, MountedImageProof):
                raise StorageBrokerError("PROTOCOL_ERROR")
            _validate_mounted_image_proof(request, proof)
            ready = _success_result(
                running,
                {"response_kind": "mounted_image_proof", "response": proof},
            )
            self.ledger.close_from_ready_locked(lock_set, ready)
            return proof
        except StorageBrokerError as exc:
            self.ledger.mark_unresolved_locked(
                lock_set, running.workflow_id, running.generation,
                UnresolvedReason.PROTOCOL_ERROR if exc.code == "PROTOCOL_ERROR" else UnresolvedReason.BROKER_LOST,
            )
            raise
        except ValueError as exc:
            self.ledger.mark_unresolved_locked(
                lock_set, running.workflow_id, running.generation, UnresolvedReason.PROTOCOL_ERROR
            )
            raise StorageBrokerError("PROTOCOL_ERROR") from exc
        except Exception as exc:
            self.ledger.mark_unresolved_locked(
                lock_set, running.workflow_id, running.generation, UnresolvedReason.BROKER_LOST
            )
            raise StorageBrokerError("BROKER_LOST") from exc

    def _run_probe_record(self, lock_set: Any, request: _BrokerProbeRequest, effect_budget_ns: int) -> StorageWorkflowRecord:
        _validate_budgets(effect_budget_ns, CLEANUP_BUDGET_MAX_NS)
        recovery = _new_recovery_authority(self.home)
        try:
            return self.ledger.prepare_locked(lock_set, request, self.executable, _socket_identity(self.home), _safe_boot_identity(), recovery, effect_budget_ns=effect_budget_ns, cleanup_budget_ns=CLEANUP_BUDGET_MAX_NS)
        finally:
            recovery.close()

    def _recover_open_workflows_locked(self, lock_set: Any, *, recovery_budget_ns: int) -> tuple[StorageWorkflowRecord, ...]:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        if recovery_budget_ns <= 0 or recovery_budget_ns > RECOVERY_BUDGET_MAX_NS:
            raise StorageBrokerError("DEADLINE_EXPIRED")
        records = self.ledger.load_all_locked(lock_set)
        recovered: list[StorageWorkflowRecord] = []
        for record in records:
            if record.state == LedgerState.OPEN_PREPARED:
                recovered.append(self.ledger.close_preexec_failure_locked(lock_set, record.workflow_id, record.generation))
            elif record.state in {LedgerState.OPEN_RUNNING, LedgerState.OPEN_UNRESOLVED}:
                recovered.append(self.ledger.mark_unresolved_locked(lock_set, record.workflow_id, record.generation, UnresolvedReason.BROKER_LOST))
        return tuple(recovered)

    def _late_close_locked(self, lock_set: Any, workflow_id: UUID, generation: int, *, recovery_budget_ns: int) -> StorageWorkflowRecord:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        records = self.ledger.load_all_locked(lock_set)
        record = _find_record(records, workflow_id, generation)
        if record.state == LedgerState.OPEN_PREPARED:
            return self.ledger.close_preexec_failure_locked(lock_set, workflow_id, generation)
        if record.state == LedgerState.OPEN_RUNNING:
            return self.ledger.mark_unresolved_locked(lock_set, workflow_id, generation, UnresolvedReason.CHANNEL_LOST)
        return record

    def _reconcile_locked(self, lock_set: Any, request: Any, *, capability: Any) -> Mapping[str, Any]:
        _assert_lock(lock_set, self.home, "shared", "exclusive")
        if getattr(capability, "consumed", False):
            raise StorageBrokerError("REPLAY")
        if not getattr(capability, "capability_sha256", None):
            raise StorageBrokerError("AUTH_FAILED")
        capability.consumed = True
        if self.transport is None:
            raise StorageBrokerError("BROKER_UNAVAILABLE")
        record = _find_record(self.ledger.load_all_locked(lock_set), request.workflow_id, request.generation)
        response = self.transport(request, record)
        if isinstance(response, dict):
            postcondition = response.get("postcondition", response)
            if not isinstance(postcondition, Mapping):
                raise StorageBrokerError("PROTOCOL_ERROR")
            return postcondition
        raise StorageBrokerError("PROTOCOL_ERROR")


def _validate_budgets(effect: int, cleanup: int) -> None:
    if type(effect) is not int or type(cleanup) is not int or effect <= 0 or cleanup <= 0:
        raise StorageBrokerError("DEADLINE_EXPIRED")
    if effect > EFFECT_BUDGET_MAX_NS or cleanup > CLEANUP_BUDGET_MAX_NS or effect + cleanup > TOTAL_BUDGET_MAX_NS:
        raise StorageBrokerError("BUDGET_EXCEEDED")


def _new_recovery_authority(home: Path) -> _RecoveryAuthority:
    from lifecycle_lock import ensure_private_directory
    root = bytearray(os.urandom(32))
    path = home / "storage" / "recovery" / f"{uuid4()}.root"
    for directory in (home / "storage", path.parent):
        ensure_private_directory(directory)
        details = directory.lstat()
        if (not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o700):
            raise StorageBrokerError("RECOVERY_DIRECTORY_UNSAFE")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(root)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short recovery-authority write")
            view = view[written:]
        os.fsync(fd)
        details = os.fstat(fd)
    except Exception:
        os.close(fd)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return _RecoveryAuthority(PurePosixPath(path.relative_to(home)), fd, root, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino, details.st_uid, 0o600, hashlib.sha256(root).hexdigest())


def _socket_identity(home: Path) -> BrokerSocketIdentity:
    path = home / "storage" / "broker.sock"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        path.touch(mode=0o600)
    details = path.stat(follow_symlinks=False)
    return BrokerSocketIdentity(path, DarwinU32(details.st_dev & 0xFFFFFFFF), details.st_ino, details.st_uid, stat.S_IMODE(details.st_mode))


def _find_record(records: tuple[StorageWorkflowRecord, ...], workflow_id: UUID, generation: int) -> StorageWorkflowRecord:
    for record in records:
        if record.workflow_id == workflow_id and record.generation == generation:
            return record
    raise StorageBrokerError("LEDGER_RECORD_NOT_FOUND")


def _record_from_dict(raw: Mapping[str, Any]) -> StorageWorkflowRecord:
    required = {
        "schema_version", "state", "workflow_id", "generation", "operation", "transaction_id",
        "canonical_request", "request_sha256", "broker_sha256", "broker_dev_u32", "broker_ino",
        "broker_uid", "broker_mode", "owner_connection_nonce", "owner_peer_audit_sha256", "broker_pid",
        "broker_sid", "broker_pgid", "socket", "boot", "effect_budget_ns", "cleanup_budget_ns",
        "recovery_authority_relative", "recovery_authority_dev_u32", "recovery_authority_ino",
        "recovery_authority_sha256", "recovery_authority_consumed", "started_monotonic_ns",
        "command_sha256", "unresolved_reason", "result_sha256", "closed_ready_sha256", "child_reaped",
        "group_absent", "native_cleanup_proven", "terminal_outcome", "terminal_code", "terminal_response",
        "reconciliation_required", "record_sha256",
    }
    if set(raw) != required:
        raise ValueError("ledger record keys are not exact")
    data = _as_json(raw)
    data["state"] = LedgerState(str(data["state"]))
    data["workflow_id"] = UUID(str(data["workflow_id"]))
    data["transaction_id"] = UUID(str(data["transaction_id"]))
    data["socket"] = BrokerSocketIdentity(Path(data["socket"]["path"]), DarwinU32(int(data["socket"]["dev_u32"])), int(data["socket"]["ino"]), int(data["socket"]["uid"]), int(data["socket"]["mode"]))
    data["boot"] = BootIdentity(int(data["boot"]["seconds"]), int(data["boot"]["microseconds"]))
    data["recovery_authority_relative"] = PurePosixPath(data["recovery_authority_relative"])
    if data["unresolved_reason"] is not None:
        data["unresolved_reason"] = UnresolvedReason(str(data["unresolved_reason"]))
    data["broker_dev_u32"] = DarwinU32(int(data["broker_dev_u32"]))
    data["recovery_authority_dev_u32"] = DarwinU32(int(data["recovery_authority_dev_u32"]))
    record_sha = data.pop("record_sha256")
    computed = digest("CORTEX-S3\x00LEDGER\x00V1\x00", data)
    if computed != record_sha:
        raise ValueError("ledger record digest mismatch")
    data["record_sha256"] = str(record_sha)
    return StorageWorkflowRecord(**data)


def _success_result(record: StorageWorkflowRecord, response: BrokerTerminalResponse) -> ClosedReadyResult:
    payload = {
        "workflow_id": record.workflow_id, "generation": record.generation,
        "outcome": "success", "code": "OK", "response": response,
        "command_sha256": record.command_sha256, "child_reaped": True,
        "group_absent": True, "native_cleanup_proven": True,
        "reconciliation_required": record.operation in {"create", "mount", "detach", "delete-disposable-item"},
    }
    result_sha = digest("CORTEX-S3\x00RESULT\x00V1\x00", payload)
    closed_payload = dict(payload)
    closed_payload["result_sha256"] = result_sha
    closed_sha = digest("CORTEX-S3\x00CLOSED-READY\x00V1\x00", closed_payload)
    return ClosedReadyResult(record.workflow_id, record.generation, "success", "OK", response, record.command_sha256 or "", result_sha, closed_sha, True, True, True, bool(payload["reconciliation_required"]))


def _validate_mounted_image_proof(request: _BrokerProbeRequest, proof: MountedImageProof) -> None:
    if proof.mount_path != request.mount_path:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if (proof.image_dev_u32, proof.image_ino) != request.image_identity:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if (
        proof.mount_dev_u32,
        proof.mount_ino,
        proof.mount_fsid0_u32,
        proof.mount_fsid1_u32,
    ) != request.mount_identity:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if proof.volume_name != request.expected_volume_name:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if proof.volume_uuid != request.expected_volume_uuid or proof.encryption_uuid != request.expected_encryption_uuid:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if proof.mapping_count != 1 or proof.filesystem_type != "apfs" or not proof.writable or not proof.encrypted:
        raise StorageBrokerError("PROTOCOL_ERROR")
    if proof.request_sha256 != request_sha256(request):
        raise StorageBrokerError("PROTOCOL_ERROR")


__all__ = [
    "LedgerState", "PublicStorageOperation", "UnresolvedReason", "BootIdentity", "DarwinU32",
    "AttestedBrokerExecutable", "AttestedMountProbe", "BrokerSocketIdentity",
    "NativeHelperManifestRecord", "InstalledStorageRuntimeGeneration", "InstalledGenerationSelector",
    "StableBootstrapManifest", "AttestedBootstrapHandle", "StorageLocalResponse",
    "StorageEvidenceResponse", "to_storage_evidence_response", "ClosedReadyResult", "MountedImageProof",
    "StorageWorkflowRecord", "StorageWorkflowLedger", "StorageBrokerClient", "StorageBrokerError",
    "encode_frame", "decode_frame", "canonical_json", "request_sha256", "command_sha256",
    "_StorageBrokerRequest", "_BrokerProbeRequest", "_RecoveryAuthority",
]
