"""Durable, closed reconciliation records for the S3 storage broker.

The module deliberately owns the reconciliation schema.  It is independent of
the native broker so it can be exercised under both supported Python versions
without touching Keychain, DiskImages, or a real Chrome profile.
"""

from __future__ import annotations

import hashlib
import json
import os
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
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    return value


def canonical_json(value: Any) -> bytes:
    """Encode restricted canonical JSON used by reconciliation hashes."""
    value = _json_value(value)

    def reject_float(obj: Any) -> Any:
        if isinstance(obj, float):
            raise ValueError("floating point values are forbidden")
        if isinstance(obj, int) and (obj < 0 or obj > 2**64 - 1):
            raise ValueError("integer outside UInt64")
        if isinstance(obj, str):
            obj.encode("utf-8", "strict")
            if any(0xD800 <= ord(c) <= 0xDFFF for c in obj):
                raise ValueError("lone surrogate")
        if isinstance(obj, Mapping):
            seen: set[str] = set()
            for key in obj:
                if not isinstance(key, str):
                    raise ValueError("object keys must be strings")
                if key in seen:
                    raise ValueError("duplicate key")
                seen.add(key)
                reject_float(key)
            for item in obj.values():
                reject_float(item)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                reject_float(item)
        return obj

    reject_float(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


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

    def without_digest(self) -> dict[str, Any]:
        data = _json_value(self)
        data.pop("record_sha256", None)
        return data

    def verify(self) -> bool:
        return self.record_sha256 == digest(
            "CORTEX-S3\x00RECONCILIATION-RECORD\x00V1\x00", self.without_digest()
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
    if kind == "create" and postcondition["keychain_item_count"] not in (0, 1):
        raise ValueError("invalid keychain count")
    if kind == "mount" and postcondition["mapping_count"] not in (0, 1):
        raise ValueError("invalid mapping count")
    if kind in {"detach", "delete_disposable_item"}:
        if postcondition.get("mapping_count", 0) != 0 and kind == "detach":
            raise ValueError("detach must have zero mappings")
        if postcondition.get("item_count", 1) != 0 and kind == "delete_disposable_item":
            raise ValueError("delete must have zero items")
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
            os.write(fd, payload)
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
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(raw, dict):
            raise ValueError("reconciliation record is not an object")
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
        data["record_sha256"] = digest("CORTEX-S3\x00RECONCILIATION-RECORD\x00V1\x00", data)
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
            "postcondition_sha256": digest("CORTEX-S3\x00POSTCONDITION\x00V1\x00", postcondition),
            "previous_record_sha256": current.record_sha256,
        }
        data["record_sha256"] = digest("CORTEX-S3\x00RECONCILIATION-RECORD\x00V1\x00", data)
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
            generation=int(raw["generation"]),
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
