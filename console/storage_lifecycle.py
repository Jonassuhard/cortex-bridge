"""Lock-carrying storage façade.

This façade is the only product layer allowed to construct private broker
requests.  It deliberately keeps the implementation no-effect by default:
native work is supplied by the injected ``StorageBrokerClient`` and mount
verification is supplied by the injected verifier.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

from storage_broker import StorageBrokerError, StorageBrokerClient, StorageLocalResponse, _StorageBrokerRequest
from storage_result import CheckResult, OperationResult


@dataclass(frozen=True, slots=True)
class StoragePaths:
    home: Path
    host_volume: Path
    legacy_image: Path
    new_image: Path
    mount: Path
    root: Path
    bootstrap: Path
    marker: Path
    transition: Path
    quarantine: Path


@dataclass(slots=True)
class HostBinding:
    fd: int
    volume_uuid: str
    filesystem_type: str
    fsid_u32: tuple[int, int]
    mount_from: str
    flags: int

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


@dataclass(frozen=True, slots=True)
class LegacySnapshot:
    file_count: int
    allocated_bytes: int
    metadata_sha256: Mapping[str, str]


def _assert_lock(lock_set: Any, home: Path, *, exclusive: bool) -> None:
    if lock_set is None or not hasattr(lock_set, "assert_active"):
        raise RuntimeError("storage lock set is required")
    lock_set.assert_active(
        home=Path(home), required_install_mode="shared",
        required_storage_mode="exclusive" if exclusive else "shared",
    )
    if getattr(lock_set, "admission_mode", "exclusive") != "exclusive":
        raise RuntimeError("storage admission lock is required")


class StorageLifecycle:
    def __init__(
        self,
        paths: StoragePaths,
        *,
        broker: StorageBrokerClient,
        fd_probe: Callable[[Any], Any],
        mount_verifier: Callable[[Any], OperationResult],
        effect_budget_ns: int = 1_000_000_000,
        cleanup_budget_ns: int = 1_000_000_000,
    ) -> None:
        self.paths = paths
        self.broker = broker
        self.fd_probe = fd_probe
        self.mount_verifier = mount_verifier
        self.effect_budget_ns = effect_budget_ns
        self.cleanup_budget_ns = cleanup_budget_ns

    def _operation(self, name: str, lock_set: Any, *, exclusive: bool = True) -> None:
        _assert_lock(lock_set, self.paths.home, exclusive=exclusive)

    def _ok(self, operation: str, code: str, transaction_id: UUID | str | None = None) -> OperationResult:
        return OperationResult(operation, "PASS", str(transaction_id) if transaction_id else None, code, (CheckResult("storage", "PASS", "contract_passed"),))

    def _fail(self, operation: str, code: str, transaction_id: UUID | str | None = None) -> OperationResult:
        return OperationResult(operation, "FAIL", str(transaction_id) if transaction_id else None, code, (CheckResult("storage", "FAIL", "contract_rejected"),))

    def preflight_locked(self, lock_set: Any) -> OperationResult:
        self._operation("preflight", lock_set, exclusive=False)
        if not self.paths.host_volume.is_dir():
            return self._fail("preflight", "HOST_VOLUME_MISSING")
        try:
            self.fd_probe(self.paths.host_volume)
        except Exception:
            return self._fail("preflight", "HOST_PROBE_FAILED")
        return self._ok("preflight", "HOST_READY")

    def keychain_spike_locked(self, lock_set: Any, *, cleanup_approved: bool) -> OperationResult:
        self._operation("keychain_spike", lock_set)
        if cleanup_approved is not True:
            return self._fail("keychain_spike", "CLEANUP_NOT_AUTHORIZED")
        transaction_id = uuid4()
        image = self.paths.quarantine / f"spike-{transaction_id}.sparsebundle"
        encryption_uuid = None
        try:
            for operation, expected_count in (("create", 1), ("inspect-item", 1), ("delete-disposable-item", 0)):
                request = _StorageBrokerRequest(
                    1, operation, image, None,
                    "CORTEX_BRIDGE_SPIKE" if operation == "create" else None,
                    "64m" if operation == "create" else None,
                    transaction_id, encryption_uuid, True, True,
                )
                record = self.broker._run_locked(
                    lock_set, request, effect_budget_ns=self.effect_budget_ns,
                    cleanup_budget_ns=self.cleanup_budget_ns,
                )
                encryption_uuid = self._confirmed_spike_step(record, request, expected_count)
        except StorageBrokerError as exc:
            # Preserve the quarantine image and exact transaction on ambiguity;
            # never infer cleanup or issue a compensating delete to a guessed item.
            return self._fail("keychain_spike", exc.code, transaction_id)
        return self._ok("keychain_spike", "SPIKE_PASSED", transaction_id)

    @staticmethod
    def _confirmed_spike_step(record: Any, request: _StorageBrokerRequest, expected_count: int) -> str:
        def reject() -> None:
            raise StorageBrokerError("SPIKE_RESPONSE_UNCONFIRMED")
        if (getattr(record, "state", None) != "CLOSED_SUCCESS"
                or getattr(record, "transaction_id", None) != request.transaction_id
                or getattr(record, "terminal_outcome", None) != "success"
                or getattr(record, "terminal_code", None) != "OK"
                or any(getattr(record, field, None) is not True for field in
                       ("child_reaped", "group_absent", "native_cleanup_proven", "recovery_authority_consumed"))):
            reject()
        terminal = getattr(record, "terminal_response", None)
        if not isinstance(terminal, Mapping) or set(terminal) != {"response_kind", "response"} or terminal["response_kind"] != "local":
            reject()
        response = terminal["response"]
        if isinstance(response, StorageLocalResponse):
            response = asdict(response)
        if not isinstance(response, Mapping) or set(response) != {"schema_version", "operation", "code", "encryption_uuid", "device", "item_count"}:
            reject()
        if (type(response["schema_version"]) is not int or response["schema_version"] != 1
                or response["operation"] != request.operation or response["code"] != "OK"
                or response["device"] is not None or type(response["item_count"]) is not int
                or response["item_count"] != expected_count):
            reject()
        encryption_uuid = response["encryption_uuid"]
        try:
            if not isinstance(encryption_uuid, str) or str(UUID(encryption_uuid)) != encryption_uuid:
                reject()
        except (ValueError, AttributeError):
            reject()
        if request.expected_encryption_uuid is not None and encryption_uuid != request.expected_encryption_uuid:
            reject()
        return encryption_uuid

    def create_vault_locked(self, lock_set: Any) -> OperationResult:
        self._operation("create_vault", lock_set)
        request = _StorageBrokerRequest(
            1, "create", self.paths.new_image, None, "CORTEX_BRIDGE_2026_09", "256g",
            uuid4(), None, False, False,
        )
        try:
            record = self.broker._run_locked(
                lock_set, request, effect_budget_ns=self.effect_budget_ns,
                cleanup_budget_ns=self.cleanup_budget_ns,
            )
        except StorageBrokerError as exc:
            return self._fail("create_vault", exc.code)
        return self._ok("create_vault", "VAULT_CREATED", record.transaction_id)

    def initialize_layout_locked(self, lock_set: Any) -> OperationResult:
        self._operation("initialize_layout", lock_set)
        try:
            self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not stat.S_ISDIR(os.stat(self.paths.root, follow_symlinks=False).st_mode):
                return self._fail("initialize_layout", "STORAGE_ROOT_UNSAFE")
            os.chmod(self.paths.root, 0o700)
        except OSError:
            return self._fail("initialize_layout", "STORAGE_ROOT_UNSAFE")
        return self._ok("initialize_layout", "LAYOUT_READY")

    def mount_or_adopt_locked(self, lock_set: Any) -> OperationResult:
        self._operation("mount_or_adopt", lock_set)
        result = self.mount_verifier(lock_set)
        if not isinstance(result, OperationResult):
            raise RuntimeError("mount verifier returned an invalid result")
        if result.operation != "status":
            return result
        return OperationResult("mount_or_adopt", result.verdict, result.transaction_id, result.code, result.checks)

    def detach_locked(self, lock_set: Any) -> OperationResult:
        self._operation("detach", lock_set)
        request = _StorageBrokerRequest(
            1, "detach", self.paths.new_image, self.paths.mount,
            "CORTEX_BRIDGE_2026_09", None, uuid4(), None, False, False,
        )
        try:
            record = self.broker._run_locked(
                lock_set, request, effect_budget_ns=self.effect_budget_ns,
                cleanup_budget_ns=self.cleanup_budget_ns,
            )
        except StorageBrokerError as exc:
            return self._fail("detach", exc.code)
        return self._ok("detach", "DETACHED", record.transaction_id)

    def status_locked(self, lock_set: Any) -> OperationResult:
        self._operation("status", lock_set, exclusive=False)
        result = self.mount_verifier(lock_set)
        if isinstance(result, OperationResult) and result.operation == "status":
            return result
        return OperationResult("status", "UNCLEAR", None, "STORAGE_NOT_READY", (CheckResult("storage", "UNCLEAR", "contract_unclear"),), storage_state="UNKNOWN", mounted=False, runtime_allowed=False, recovery="UNCLEAR")


__all__ = ["StoragePaths", "HostBinding", "LegacySnapshot", "StorageLifecycle"]
