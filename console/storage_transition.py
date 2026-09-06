"""Durable, lock-bound storage transition journal.

The transition journal is deliberately small and conservative.  It records a
single forward transition, snapshots the three private control files before
publication, and only reports a committed runtime after the journal itself has
been atomically replaced and fsynced.  All mutating entrypoints require the
same active install/storage/admission lock set; a missing or replaced set is a
hard failure rather than an implicit reacquisition.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, cast
from uuid import UUID, uuid4

from storage_result import CheckResult, OperationResult, StorageStatus
from storage_reconciliation import canonical_json, digest


TransitionPhase = Literal[
    "in_progress", "spike_create_started", "spike_keychain_bound",
    "spike_mount_one_verified", "spike_mount_two_verified",
    "spike_disposition_recorded", "spike_passed", "image_create_started",
    "keychain_bound", "bootstrap_published", "marker_published",
    "settings_published", "committed", "rolling_back", "rolled_back",
]

_PHASES: tuple[TransitionPhase, ...] = (
    "in_progress", "spike_create_started", "spike_keychain_bound",
    "spike_mount_one_verified", "spike_mount_two_verified",
    "spike_disposition_recorded", "spike_passed", "image_create_started",
    "keychain_bound", "bootstrap_published", "marker_published",
    "settings_published", "committed", "rolling_back", "rolled_back",
)
_SNAPSHOT_NAMES = ("settings.json", "storage-bootstrap.json", "storage-required")
_JOURNAL_NAME = "storage-transition.json"
_TARGET_IMAGE = "CORTEX_BRIDGE_2026_09.sparsebundle"
_SHA256 = set("0123456789abcdef")


def _as_json(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, PurePosixPath):
        return value.as_posix()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _as_json(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _as_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_as_json(item) for item in value]
    return value.value if hasattr(value, "value") and type(value).__name__.endswith("Enum") else value


@dataclass(frozen=True, slots=True)
class StorageProjection:
    default_workspace: str
    browser_profile_root: str
    browser_transport: Literal["chrome_extension"]

    def __post_init__(self) -> None:
        if self.browser_transport != "chrome_extension":
            raise ValueError("browser transport must be chrome_extension")
        for name, value in (("default_workspace", self.default_workspace), ("browser_profile_root", self.browser_profile_root)):
            if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
                raise ValueError(f"{name} must be an absolute path")


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    name: Literal["settings.json", "storage-bootstrap.json", "storage-required"]
    present: bool
    mode: int | None
    size: int | None
    sha256: str | None
    dev_u32: int | None
    ino: int | None

    def __post_init__(self) -> None:
        if self.name not in _SNAPSHOT_NAMES:
            raise ValueError("snapshot entry name is invalid")
        if type(self.present) is not bool:
            raise ValueError("snapshot entry presence is invalid")
        if not self.present:
            if any(value is not None for value in (self.mode, self.size, self.sha256, self.dev_u32, self.ino)):
                raise ValueError("absent snapshot entry has metadata")
            return
        if type(self.mode) is not int or not 0 <= self.mode <= 0o777:
            raise ValueError("snapshot entry mode is invalid")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("snapshot entry size is invalid")
        if type(self.sha256) is not str or len(self.sha256) != 64 or set(self.sha256) - _SHA256:
            raise ValueError("snapshot entry digest is invalid")
        if type(self.dev_u32) is not int or not 0 <= self.dev_u32 <= 0xFFFFFFFF:
            raise ValueError("snapshot entry device is invalid")
        if type(self.ino) is not int or self.ino <= 0:
            raise ValueError("snapshot entry inode is invalid")


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    schema_version: Literal[1]
    entries: tuple[SnapshotEntry, SnapshotEntry, SnapshotEntry]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or tuple(entry.name for entry in self.entries) != _SNAPSHOT_NAMES:
            raise ValueError("snapshot manifest is not canonical")
        if not all(isinstance(entry, SnapshotEntry) for entry in self.entries):
            raise ValueError("snapshot manifest entries are invalid")

    @property
    def sha256(self) -> str:
        return digest("CORTEX-S3\x00SNAPSHOT-MANIFEST\x00V1\x00", self)


@dataclass(frozen=True, slots=True)
class TransitionJournal:
    schema_version: Literal[1]
    transaction_id: str
    phase_number: int
    phase: TransitionPhase
    snapshot_relative: PurePosixPath
    snapshot_manifest_sha256: str
    originals: tuple[SnapshotEntry, SnapshotEntry, SnapshotEntry]
    target_bootstrap_sha256: str
    target_marker_sha256: str
    target_storage_projection_sha256: str
    target_image_basename: str
    spike_transaction_id: str | None
    spike_image_basename: str | None
    spike_encryption_uuid: str | None
    spike_disposition: Literal["deleted", "quarantined"] | None
    spike_receipt_sha256: str | None
    target_encryption_uuid: str | None
    reconciliation: Literal["not_started", "image_create_started", "keychain_bound"]
    s3_workflow_id: str | None
    s3_generation: int | None
    s3_operation: Literal["create", "mount", "detach", "delete-disposable-item"] | None
    s3_request_sha256: str | None
    s3_result_sha256: str | None
    effect_reconciled: bool
    reconciliation_record_sha256: str | None

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.phase not in _PHASES:
            raise ValueError("transition journal schema or phase is invalid")
        if self.phase_number != _PHASES.index(self.phase):
            raise ValueError("transition phase number is invalid")
        try:
            UUID(self.transaction_id)
        except ValueError as exc:
            raise ValueError("transition transaction id is invalid") from exc
        if self.target_image_basename != _TARGET_IMAGE:
            raise ValueError("transition target image basename is invalid")
        if self.reconciliation not in {"not_started", "image_create_started", "keychain_bound"}:
            raise ValueError("transition reconciliation state is invalid")


def _assert_locked(lock_set: Any, home: Path, *, exclusive: bool) -> None:
    if lock_set is None or not hasattr(lock_set, "assert_active"):
        raise RuntimeError("storage lock set is required")
    lock_set.assert_active(
        home=Path(home), required_install_mode="shared", required_storage_mode="exclusive" if exclusive else "shared"
    )
    if getattr(lock_set, "admission_mode", "exclusive") != "exclusive":
        raise RuntimeError("storage admission lock is required")


def _journal_path(home: Path) -> Path:
    return Path(home) / _JOURNAL_NAME


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short transition write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, path)
    parent_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _entry(path: Path, name: str) -> SnapshotEntry:
    if path.is_symlink():
        raise RuntimeError("transition control file is a symlink")
    try:
        details = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return SnapshotEntry(cast(Any, name), False, None, None, None, None, None)
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RuntimeError("transition control file is not a private regular file")
    if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) & 0o077:
        raise RuntimeError("transition control file is not owner-only")
    data = path.read_bytes()
    return SnapshotEntry(cast(Any, name), True, stat.S_IMODE(details.st_mode), len(data), hashlib.sha256(data).hexdigest(), details.st_dev & 0xFFFFFFFF, details.st_ino)


def _snapshot(home: Path, transaction_id: str) -> tuple[PurePosixPath, SnapshotManifest]:
    relative = PurePosixPath("private-quarantine") / f"storage-cutover-{transaction_id}"
    root = home / Path(relative)
    snapshot_dir = root / "snapshot"
    snapshot_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries: list[SnapshotEntry] = []
    for name in _SNAPSHOT_NAMES:
        path = home / name
        item = _entry(path, name)
        entries.append(item)
        if item.present:
            output = snapshot_dir / name
            output.write_bytes(path.read_bytes())
            output.chmod(item.mode or 0o600)
            fd = os.open(output, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    manifest = SnapshotManifest(1, cast(Any, tuple(entries)))
    _atomic_write(root / "manifest.json", canonical_json(manifest))
    directory_fd = os.open(snapshot_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    root_fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    return relative, manifest


def _journal_dict(journal: TransitionJournal) -> dict[str, Any]:
    return cast(dict[str, Any], _as_json(journal))


def _write_journal(home: Path, journal: TransitionJournal) -> None:
    _atomic_write(_journal_path(home), canonical_json(_journal_dict(journal)))


def _parse_entry(value: Mapping[str, Any]) -> SnapshotEntry:
    required = {"name", "present", "mode", "size", "sha256", "dev_u32", "ino"}
    if set(value) != required:
        raise ValueError("snapshot entry keys are not exact")
    return SnapshotEntry(cast(Any, value["name"]), value["present"], value["mode"], value["size"], value["sha256"], value["dev_u32"], value["ino"])


def _parse_manifest(raw: Mapping[str, Any]) -> SnapshotManifest:
    if set(raw) != {"schema_version", "entries"}:
        raise ValueError("snapshot manifest keys are not exact")
    entries = raw["entries"]
    if not isinstance(entries, list) or len(entries) != len(_SNAPSHOT_NAMES):
        raise ValueError("snapshot manifest entries are invalid")
    manifest = SnapshotManifest(1, cast(Any, tuple(_parse_entry(item) for item in entries)))
    if canonical_json(_as_json(manifest)) != canonical_json(raw):
        raise ValueError("snapshot manifest is not canonical")
    return manifest


def _validate_snapshot_binding(home: Path, journal: TransitionJournal) -> None:
    relative = journal.snapshot_relative
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("snapshot path is unsafe")
    expected_prefix = ("private-quarantine", f"storage-cutover-{journal.transaction_id}")
    if relative.parts[:2] != expected_prefix:
        raise ValueError("snapshot path is not transaction-bound")
    manifest_path = home / Path(relative) / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _parse_manifest(raw)
    if manifest.sha256 != journal.snapshot_manifest_sha256 or manifest.entries != journal.originals:
        raise ValueError("snapshot manifest digest mismatch")
    for entry in manifest.entries:
        path = home / Path(relative) / "snapshot" / entry.name
        if entry.present:
            details = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise ValueError("snapshot entry is not a private regular file")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != entry.sha256 or len(data) != entry.size:
                raise ValueError("snapshot entry digest mismatch")
        elif path.exists() or path.is_symlink():
            raise ValueError("absent snapshot entry exists")


def _parse_journal(raw: Mapping[str, Any]) -> TransitionJournal:
    required = set(TransitionJournal.__dataclass_fields__)
    if set(raw) != required:
        raise ValueError("transition journal keys are not exact")
    data = dict(raw)
    data["snapshot_relative"] = PurePosixPath(data["snapshot_relative"])
    if not isinstance(data["originals"], list) or len(data["originals"]) != len(_SNAPSHOT_NAMES):
        raise ValueError("transition originals are invalid")
    data["originals"] = tuple(_parse_entry(item) for item in data["originals"])
    return TransitionJournal(**data)


def begin_transition_locked(
    lock_set: Any, home: Path, target: StorageProjection, *,
    target_image_basename: Literal["CORTEX_BRIDGE_2026_09.sparsebundle"],
) -> TransitionJournal:
    home = Path(home).resolve(strict=True)
    _assert_locked(lock_set, home, exclusive=True)
    if target_image_basename != _TARGET_IMAGE:
        raise ValueError("target image basename is invalid")
    if load_transition_locked(lock_set, home) is not None:
        raise RuntimeError("transition already exists")
    transaction_id = str(uuid4())
    snapshot_relative, manifest = _snapshot(home, transaction_id)
    projection_sha = digest("CORTEX-S3\x00STORAGE-PROJECTION\x00V1\x00", target)
    journal = TransitionJournal(
        1, transaction_id, 0, "in_progress", snapshot_relative, manifest.sha256,
        manifest.entries,
        digest("CORTEX-S3\x00TARGET-BOOTSTRAP\x00V1\x00", target),
        digest("CORTEX-S3\x00TARGET-MARKER\x00V1\x00", target), projection_sha,
        _TARGET_IMAGE, None, None, None, None, None, None, "not_started", None,
        None, None, None, None, False, None,
    )
    _write_journal(home, journal)
    return journal


def advance_transition_locked(
    lock_set: Any, journal: TransitionJournal, *, phase: TransitionPhase,
    updates: Mapping[str, object],
) -> TransitionJournal:
    _assert_locked(lock_set, _journal_home(lock_set, journal), exclusive=True)
    if phase not in _PHASES or _PHASES.index(phase) != journal.phase_number + 1:
        raise ValueError("transition phase must advance")
    allowed = set(TransitionJournal.__dataclass_fields__) - {"schema_version", "transaction_id", "phase_number", "phase", "originals", "snapshot_relative", "snapshot_manifest_sha256", "target_bootstrap_sha256", "target_marker_sha256", "target_storage_projection_sha256", "target_image_basename"}
    if set(updates) - allowed:
        raise ValueError("transition update contains unknown field")
    values = {key: value for key, value in updates.items()}
    next_journal = replace(journal, phase_number=_PHASES.index(phase), phase=phase, **values)
    _write_journal(_journal_home(lock_set, journal), next_journal)
    return next_journal


def _journal_home(lock_set: Any, journal: TransitionJournal) -> Path:
    home = getattr(lock_set, "home", None)
    if home is None:
        raise RuntimeError("lock set has no home")
    return Path(home)


def _journal_home_from_path(lock_set: Any, home: Path) -> Path:
    _assert_locked(lock_set, home, exclusive=False)
    return Path(home)


def commit_transition_locked(lock_set: Any, journal: TransitionJournal) -> TransitionJournal:
    home = _journal_home(lock_set, journal)
    _assert_locked(lock_set, home, exclusive=True)
    if journal.phase in {"rolling_back", "rolled_back", "committed"}:
        raise ValueError("transition cannot be committed from this phase")
    committed = replace(journal, phase_number=_PHASES.index("committed"), phase="committed")
    _write_journal(home, committed)
    return committed


def load_transition_locked(lock_set: Any, home: Path) -> TransitionJournal | None:
    home = _journal_home_from_path(lock_set, Path(home).resolve(strict=True))
    try:
        raw = json.loads(_journal_path(home).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("transition journal is not an object")
    journal = _parse_journal(raw)
    _validate_snapshot_binding(home, journal)
    return journal


def runtime_transition_status_locked(lock_set: Any, home: Path) -> StorageStatus:
    try:
        journal = load_transition_locked(lock_set, home)
    except Exception:
        return StorageStatus("UNCLEAR", "STORAGE_NOT_READY", None, "UNKNOWN", False, False)
    if journal is None:
        return StorageStatus("PASS", "STORAGE_UNCONFIGURED", None, "UNCONFIGURED", False, True)
    if journal.phase == "committed":
        return StorageStatus("PASS", "STORAGE_READY", journal.transaction_id, "COMMITTED", True, True)
    if journal.phase == "rolled_back":
        return StorageStatus("PASS", "STORAGE_UNCONFIGURED", None, "UNCONFIGURED", False, True)
    return StorageStatus("UNCLEAR", "STORAGE_TRANSITIONING", journal.transaction_id, "TRANSITIONING", False, False)


def rollback_transition_locked(lock_set: Any, home: Path, *, process_status: Any) -> OperationResult:
    home = Path(home).resolve(strict=True)
    _assert_locked(lock_set, home, exclusive=True)
    journal = load_transition_locked(lock_set, home)
    if journal is None:
        return OperationResult("rollback", "PASS", None, "NO_TRANSITION", (CheckResult("journal", "PASS", "contract_passed"),))
    stopped = process_status.get("stopped") if isinstance(process_status, Mapping) else getattr(process_status, "stopped", False)
    if stopped is not True:
        return OperationResult("rollback", "FAIL", journal.transaction_id, "PROCESS_RUNNING", (CheckResult("process", "FAIL", "contract_rejected"),))
    rolling = replace(journal, phase_number=_PHASES.index("rolling_back"), phase="rolling_back")
    _write_journal(home, rolling)
    snapshot_dir = home / Path(journal.snapshot_relative) / "snapshot"
    for entry in journal.originals:
        target = home / entry.name
        if entry.present:
            data = (snapshot_dir / entry.name).read_bytes()
            _atomic_write(target, data)
            os.chmod(target, entry.mode or 0o600)
        else:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
    parent_fd = os.open(home, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    rolled = replace(rolling, phase_number=_PHASES.index("rolled_back"), phase="rolled_back")
    _write_journal(home, rolled)
    return OperationResult("rollback", "PASS", journal.transaction_id, "ROLLED_BACK", (CheckResult("journal", "PASS", "contract_passed"),))


__all__ = [
    "StorageProjection", "SnapshotEntry", "SnapshotManifest", "TransitionJournal",
    "TransitionPhase", "begin_transition_locked", "advance_transition_locked",
    "commit_transition_locked", "load_transition_locked", "runtime_transition_status_locked",
    "rollback_transition_locked",
]
