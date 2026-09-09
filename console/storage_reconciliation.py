"""Durable, closed reconciliation records for the S3 storage broker.

The module deliberately owns the reconciliation schema.  It is independent of
the native broker so it can be exercised under both supported Python versions
without touching Keychain, DiskImages, or a real Chrome profile.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, TypedDict, cast
from uuid import UUID


class ReconciliationState(StrEnum):
    PENDING = "pending"
    RECONCILED = "reconciled"
    UNCLEAR = "unclear"


class CreatePostcondition(TypedDict):
    kind: Literal["create"]
    disposition: Literal["absent", "present_consistent"]
    image_present: bool
    image_identity_sha256: str | None
    keychain_item_count: Literal[0, 1]
    encryption_uuid: str | None


class MountPostcondition(TypedDict):
    kind: Literal["mount"]
    disposition: Literal["absent", "exact_mapping"]
    mapping_count: Literal[0, 1]
    mount_empty: bool
    mounted_image_proof_sha256: str | None


class DetachPostcondition(TypedDict):
    kind: Literal["detach"]
    mapping_count: Literal[0]
    mount_empty: Literal[True]


class InspectItemPostcondition(TypedDict):
    kind: Literal["inspect_item"]
    item_count: Literal[0, 1]


class DeleteItemPostcondition(TypedDict):
    kind: Literal["delete_disposable_item"]
    item_count: Literal[0]
    transaction_match: Literal[True]


class MountedImageProbePostcondition(TypedDict):
    kind: Literal["mounted_image_probe"]
    proof_sha256: str
    mapping_count: Literal[1]


ReconciliationPostcondition = (
    CreatePostcondition
    | MountPostcondition
    | DetachPostcondition
    | InspectItemPostcondition
    | DeleteItemPostcondition
    | MountedImageProbePostcondition
)


class CreateReconciliationProbe(TypedDict):
    probe_kind: Literal["create_absent_or_consistent"]
    image_path: str
    expected_image_identity_sha256: str | None
    keychain_query_sha256: str
    expected_encryption_uuid: str | None


class MountReconciliationProbe(TypedDict):
    probe_kind: Literal["mount_mapping_zero_or_one"]
    image_path: str
    mount_path: str
    expected_volume_name: str
    expected_volume_uuid: str
    expected_encryption_uuid: str


class DetachReconciliationProbe(TypedDict):
    probe_kind: Literal["detach_mapping_zero"]
    image_path: str
    mount_path: str


class ItemReconciliationProbe(TypedDict):
    probe_kind: Literal["item_count_zero_or_one"]
    keychain_query_sha256: str


class DeleteReconciliationProbe(TypedDict):
    probe_kind: Literal["deleted_item_count_zero"]
    keychain_query_sha256: str
    transaction_match: Literal[True]


class MountedImageReconciliationProbe(TypedDict):
    probe_kind: Literal["mounted_image_exact_one"]
    image_path: str
    mount_path: str
    expected_volume_name: str
    expected_volume_uuid: str
    expected_encryption_uuid: str


ReconciliationProbePayload = (
    CreateReconciliationProbe
    | MountReconciliationProbe
    | DetachReconciliationProbe
    | ItemReconciliationProbe
    | DeleteReconciliationProbe
    | MountedImageReconciliationProbe
)
ReconciliationOperation = Literal["create", "mount", "detach", "delete-disposable-item"]


def _json_value(value: Any) -> Any:
    """Convert dataclass/enum/UUID values without leaking implementation types."""
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, PurePosixPath):
        return value.as_posix()
    if hasattr(value, "__dataclass_fields__"):
        return {k: _json_value(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    return value


def canonical_json(value: Any) -> bytes:
    """Encode restricted canonical JSON used by reconciliation hashes."""
    value = _json_value(value)

    def canonicalize(obj: Any) -> Any:
        if isinstance(obj, float):
            raise ValueError("floating point values are forbidden")
        if isinstance(obj, int) and (obj < 0 or obj > 2**64 - 1):
            raise ValueError("integer outside UInt64")
        if isinstance(obj, str):
            obj.encode("utf-8", "strict")
            if any(0xD800 <= ord(c) <= 0xDFFF for c in obj):
                raise ValueError("lone surrogate")
            return obj
        if isinstance(obj, Mapping):
            keys: list[str] = []
            for key in obj:
                if not isinstance(key, str):
                    raise ValueError("object keys must be strings")
                if key in keys:
                    raise ValueError("duplicate key")
                canonicalize(key)
                keys.append(key)
            # RFC 8785-compatible member order for the S3 contract is the
            # lexicographic order of the UTF-8 byte sequences, not Python's
            # Unicode code-point order.
            return {key: canonicalize(obj[key]) for key in sorted(keys, key=lambda item: item.encode("utf-8"))}
        elif isinstance(obj, (list, tuple)):
            return [canonicalize(item) for item in obj]
        return obj

    value = canonicalize(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
        allow_nan=False,
    )
    # S3 uses long lowercase escapes for every control scalar. Match escape
    # pairs, so a literal backslash followed by n is not rewritten as a newline.
    short_controls = {r"\b": r"\u0008", r"\t": r"\u0009", r"\n": r"\u000a",
                      r"\f": r"\u000c", r"\r": r"\u000d"}
    return re.sub(r"\\.", lambda match: short_controls.get(match[0], match[0]), encoded).encode("utf-8")


def digest(domain: str, value: Any) -> str:
    if "\x00" not in domain:
        raise ValueError("digest domain must contain an explicit NUL separator")
    return hashlib.sha256(domain.encode("ascii") + canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class ReconciliationProbeRequest:
    schema_version: Literal[1]
    workflow_id: UUID
    generation: int
    transaction_id: UUID
    operation: ReconciliationOperation
    request_sha256: str
    result_sha256: str
    payload: ReconciliationProbePayload

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reconciliation schema")
        if self.generation < 0 or self.generation > 2**64 - 1:
            raise ValueError("generation outside UInt64")
        if len(self.request_sha256) != 64 or len(self.result_sha256) != 64:
            raise ValueError("invalid digest")
        _validate_probe(self.operation, self.payload)

    @property
    def probe_sha256(self) -> str:
        return digest("CORTEX-S3\x00RECONCILIATION-PROBE\x00V1\x00", self)


@dataclass(frozen=True, slots=True)
class ReconciliationRecord:
    schema_version: Literal[1]
    workflow_id: UUID
    generation: int
    transaction_id: UUID
    operation: ReconciliationOperation
    request_sha256: str
    result_sha256: str
    state: ReconciliationState
    postcondition: ReconciliationPostcondition | None
    reconciliation_probe_sha256: str | None
    postcondition_sha256: str | None
    previous_record_sha256: str | None
    record_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported reconciliation record schema")
        if type(self.generation) is not int or not 0 <= self.generation <= 2**64 - 1:
            raise ValueError("invalid reconciliation generation")
        if self.operation not in {"create", "mount", "detach", "delete-disposable-item"}:
            raise ValueError("invalid reconciliation operation")
        for value in (self.request_sha256, self.result_sha256, self.reconciliation_probe_sha256,
                      self.record_sha256):
            if not _is_sha256(value):
                raise ValueError("invalid reconciliation digest")
        for value in (self.previous_record_sha256, self.postcondition_sha256):
            if value is not None and not _is_sha256(value):
                raise ValueError("invalid optional reconciliation digest")
        if self.state == ReconciliationState.PENDING:
            if self.postcondition is not None or self.postcondition_sha256 is not None:
                raise ValueError("pending reconciliation cannot contain a result")
        elif self.state == ReconciliationState.RECONCILED:
            if self.postcondition is None or self.previous_record_sha256 is None:
                raise ValueError("reconciled result requires postcondition and predecessor")
        if self.postcondition is not None:
            validate_postcondition(self.operation, self.postcondition)
            expected = digest("CORTEX-S3\x00RECONCILIATION-POSTCONDITION\x00V1\x00", self.postcondition)
            if self.postcondition_sha256 != expected:
                raise ValueError("reconciliation postcondition digest mismatch")
        elif self.postcondition_sha256 is not None:
            raise ValueError("postcondition digest without a postcondition")

    def without_digest(self) -> dict[str, Any]:
        data = _json_value(self)
        data.pop("record_sha256", None)
        return data

    def verify(self) -> bool:
        return self.record_sha256 == digest(
            "CORTEX-S3\x00RECONCILIATION\x00V1\x00", self.without_digest()
        )


def _validate_probe(operation: str, payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError("probe payload must be an object")
    kind = payload.get("probe_kind")
    expected = {
        "create": "create_absent_or_consistent",
        "mount": "mount_mapping_zero_or_one",
        "detach": "detach_mapping_zero",
        "delete-disposable-item": "deleted_item_count_zero",
    }.get(operation)
    if expected is None or kind != expected:
        raise ValueError("operation/probe mismatch")
    allowed = {
        "create_absent_or_consistent": {
            "probe_kind", "image_path", "expected_image_identity_sha256",
            "keychain_query_sha256", "expected_encryption_uuid",
        },
        "mount_mapping_zero_or_one": {
            "probe_kind", "image_path", "mount_path", "expected_volume_name",
            "expected_volume_uuid", "expected_encryption_uuid",
        },
        "detach_mapping_zero": {"probe_kind", "image_path", "mount_path"},
        "deleted_item_count_zero": {
            "probe_kind", "keychain_query_sha256", "transaction_match",
        },
    }[kind]
    if set(payload) != allowed:
        raise ValueError("probe payload keys are not exact")
    for key in ("image_path", "mount_path"):
        if key in payload:
            _validate_private_path(payload[key])
    for key in ("expected_volume_uuid", "expected_encryption_uuid"):
        if key in payload and payload[key] is not None:
            try:
                UUID(str(payload[key]))
            except (ValueError, AttributeError, TypeError) as exc:
                raise ValueError("invalid UUID") from exc
    if "transaction_match" in payload and payload["transaction_match"] is not True:
        raise ValueError("transaction_match must be true")


def _validate_private_path(value: Any) -> None:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("path must be absolute")
    if "\x00" in value or any(ord(c) < 32 for c in value):
        raise ValueError("path contains control character")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts[1:]):
        raise ValueError("path contains invalid component")


def _is_sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_postcondition(operation: str, postcondition: Mapping[str, Any]) -> None:
    if not isinstance(postcondition, Mapping):
        raise ValueError("postcondition must be an object")
    kind = postcondition.get("kind")
    allowed_by_kind: dict[str, set[str]] = {
        "create": {
            "kind", "disposition", "image_present", "image_identity_sha256",
            "keychain_item_count", "encryption_uuid",
        },
        "mount": {
            "kind", "disposition", "mapping_count", "mount_empty",
            "mounted_image_proof_sha256",
        },
        "detach": {"kind", "mapping_count", "mount_empty"},
        "inspect_item": {"kind", "item_count"},
        "delete_disposable_item": {"kind", "item_count", "transaction_match"},
        "mounted_image_probe": {"kind", "proof_sha256", "mapping_count"},
    }
    if kind not in allowed_by_kind or set(postcondition) != allowed_by_kind[kind]:
        raise ValueError("postcondition keys are not exact")
    if operation != "delete-disposable-item" and kind not in {operation, "mounted_image_probe"}:
        raise ValueError("postcondition operation mismatch")
    if operation == "delete-disposable-item" and kind != "delete_disposable_item":
        raise ValueError("delete requires its own item observation")
    if kind == "create" and postcondition["keychain_item_count"] not in (0, 1):
        raise ValueError("invalid keychain count")
    if kind == "mount":
        count = postcondition["mapping_count"]
        empty = postcondition["mount_empty"]
        proof = postcondition["mounted_image_proof_sha256"]
        if type(count) is not int or count not in (0, 1) or type(empty) is not bool:
            raise ValueError("invalid mount observation types")
        if postcondition["disposition"] == "absent":
            if count != 0 or empty is not True or proof is not None:
                raise ValueError("contradictory absent mount observation")
        elif postcondition["disposition"] == "exact_mapping":
            if (count != 1 or type(proof) is not str or len(proof) != 64
                    or any(c not in "0123456789abcdef" for c in proof)):
                raise ValueError("exact mount mapping requires its proof digest")
        else:
            raise ValueError("invalid mount disposition")
    if kind in {"detach", "delete_disposable_item"}:
        if kind == "detach" and (type(postcondition["mapping_count"]) is not int
                                 or postcondition["mapping_count"] != 0
                                 or postcondition["mount_empty"] is not True):
            raise ValueError("detach requires zero mappings and an empty mount point")
        if kind == "delete_disposable_item" and (
                type(postcondition["item_count"]) is not int or postcondition["item_count"] != 0
                or postcondition["transaction_match"] is not True):
            raise ValueError("delete requires zero items and an exact transaction match")
    if kind == "mounted_image_probe" and postcondition["mapping_count"] != 1:
        raise ValueError("mounted probe must have one mapping")


class ReconciliationStore:
    """Hash-chained, atomic reconciliation file with compare-and-swap updates."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _fsync_parent(self) -> None:
        fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write(self, record: ReconciliationRecord) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            payload = canonical_json(_json_value(record))
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short reconciliation write")
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temp_name, self.path)
            self._fsync_parent()
        finally:
            if fd != -1:
                os.close(fd)
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def load(self) -> ReconciliationRecord | None:
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(fd)
            parent = self.path.parent.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                    or not 0 < before.st_size <= 65536
                    or not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                    or stat.S_IMODE(parent.st_mode) != 0o700):
                raise ValueError("unsafe reconciliation record")
            chunks = []
            total = 0
            while total <= 65536:
                chunk = os.read(fd, 65537 - total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            data = b"".join(chunks)
            after = os.fstat(fd)
            if (len(data) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("reconciliation record changed during read")
        finally:
            os.close(fd)
        raw = json.loads(data)
        if not isinstance(raw, dict):
            raise ValueError("reconciliation record is not an object")
        if canonical_json(raw) != data:
            raise ValueError("reconciliation record is not canonical")
        record = _record_from_dict(raw)
        if not record.verify():
            raise ValueError("reconciliation record digest mismatch")
        return record

    def create_pending(self, request: ReconciliationProbeRequest, *, previous_record_sha256: str | None = None) -> ReconciliationRecord:
        if self.load() is not None:
            raise ValueError("reconciliation record already exists")
        data = {
            "schema_version": 1,
            "workflow_id": request.workflow_id,
            "generation": request.generation,
            "transaction_id": request.transaction_id,
            "operation": request.operation,
            "request_sha256": request.request_sha256,
            "result_sha256": request.result_sha256,
            "state": ReconciliationState.PENDING,
            "postcondition": None,
            "reconciliation_probe_sha256": request.probe_sha256,
            "postcondition_sha256": None,
            "previous_record_sha256": previous_record_sha256,
        }
        data["record_sha256"] = digest("CORTEX-S3\x00RECONCILIATION\x00V1\x00", data)
        record = _record_from_dict(data)
        self._write(record)
        return record

    def cas_reconciled(
        self,
        pending_record_sha256: str,
        postcondition: ReconciliationPostcondition,
    ) -> ReconciliationRecord:
        current = self.load()
        if current is None or current.record_sha256 != pending_record_sha256:
            raise ValueError("stale reconciliation record")
        if current.state != ReconciliationState.PENDING:
            raise ValueError("reconciliation record is not pending")
        validate_postcondition(current.operation, postcondition)
        data = {
            "schema_version": 1,
            "workflow_id": current.workflow_id,
            "generation": current.generation,
            "transaction_id": current.transaction_id,
            "operation": current.operation,
            "request_sha256": current.request_sha256,
            "result_sha256": current.result_sha256,
            "state": ReconciliationState.RECONCILED,
            "postcondition": postcondition,
            "reconciliation_probe_sha256": current.reconciliation_probe_sha256,
            "postcondition_sha256": digest("CORTEX-S3\x00RECONCILIATION-POSTCONDITION\x00V1\x00", postcondition),
            "previous_record_sha256": current.record_sha256,
        }
        data["record_sha256"] = digest("CORTEX-S3\x00RECONCILIATION\x00V1\x00", data)
        record = _record_from_dict(data)
        self._write(record)
        return record


def _record_from_dict(raw: Mapping[str, Any]) -> ReconciliationRecord:
    required = {
        "schema_version", "workflow_id", "generation", "transaction_id", "operation",
        "request_sha256", "result_sha256", "state", "postcondition",
        "reconciliation_probe_sha256", "postcondition_sha256", "previous_record_sha256",
        "record_sha256",
    }
    if set(raw) != required:
        raise ValueError("record keys are not exact")
    try:
        return ReconciliationRecord(
            schema_version=cast(Literal[1], raw["schema_version"]),
            workflow_id=UUID(str(raw["workflow_id"])),
            generation=raw["generation"],
            transaction_id=UUID(str(raw["transaction_id"])),
            operation=cast(ReconciliationOperation, raw["operation"]),
            request_sha256=str(raw["request_sha256"]),
            result_sha256=str(raw["result_sha256"]),
            state=ReconciliationState(str(raw["state"])),
            postcondition=cast(ReconciliationPostcondition | None, raw["postcondition"]),
            reconciliation_probe_sha256=raw["reconciliation_probe_sha256"],
            postcondition_sha256=raw["postcondition_sha256"],
            previous_record_sha256=raw["previous_record_sha256"],
            record_sha256=str(raw["record_sha256"]),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid reconciliation record") from exc


__all__ = [
    "ReconciliationState", "ReconciliationProbeRequest", "ReconciliationRecord",
    "ReconciliationPostcondition", "ReconciliationStore", "CreatePostcondition",
    "MountPostcondition", "DetachPostcondition", "InspectItemPostcondition",
    "DeleteItemPostcondition", "MountedImageProbePostcondition",
    "CreateReconciliationProbe", "MountReconciliationProbe", "DetachReconciliationProbe",
    "ItemReconciliationProbe", "DeleteReconciliationProbe",
    "MountedImageReconciliationProbe", "canonical_json", "digest", "validate_postcondition",
]
