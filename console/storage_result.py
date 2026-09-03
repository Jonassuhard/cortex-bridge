"""Redacted, strict result types for the storage runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


Verdict = Literal["PASS", "FAIL", "UNCLEAR"]
_VERDICTS = frozenset({"PASS", "FAIL", "UNCLEAR"})
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_CHECK_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_OPERATION = re.compile(r"^[a-z][a-z0-9_]*$")
_EVIDENCE_TOKENS = frozenset(
    {
        "committed_transaction_verified",
        "contract_passed",
        "contract_rejected",
        "contract_unclear",
    }
)


def _require_verdict(value: object) -> None:
    if type(value) is not str or value not in _VERDICTS:
        raise ValueError("storage verdict is invalid")


def _require_transaction_id(value: str | None) -> None:
    if value is not None and (type(value) is not str or _UUID.fullmatch(value) is None):
        raise ValueError("storage transaction id is invalid")


def _require_token(value: object, pattern: re.Pattern[str], name: str) -> None:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"storage {name} is invalid")


def _require_redacted_evidence(value: object) -> None:
    if type(value) is not str or value not in _EVIDENCE_TOKENS:
        raise ValueError("storage evidence is not redacted")


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: Verdict
    evidence: str

    def __post_init__(self) -> None:
        _require_token(self.id, _CHECK_ID, "check id")
        _require_verdict(self.status)
        _require_redacted_evidence(self.evidence)


@dataclass(frozen=True)
class StorageStatus:
    verdict: Verdict
    code: str
    transaction_id: str | None
    storage_state: str
    mounted: bool
    runtime_allowed: bool
    recovery: Literal["UNCLEAR"] = "UNCLEAR"

    def __post_init__(self) -> None:
        _require_verdict(self.verdict)
        _require_token(self.code, _CODE, "code")
        _require_transaction_id(self.transaction_id)
        _require_token(self.storage_state, _CODE, "state")
        if type(self.mounted) is not bool or type(self.runtime_allowed) is not bool:
            raise ValueError("storage status booleans are invalid")
        if self.recovery != "UNCLEAR":
            raise ValueError("storage recovery is invalid")


@dataclass(frozen=True)
class OperationResult:
    operation: str
    verdict: Verdict
    transaction_id: str | None
    code: str
    checks: tuple[CheckResult, ...]
    storage_state: str | None = None
    mounted: bool | None = None
    runtime_allowed: bool | None = None
    recovery: Literal["UNCLEAR"] | None = None

    def __post_init__(self) -> None:
        _require_token(self.operation, _OPERATION, "operation")
        _require_verdict(self.verdict)
        _require_transaction_id(self.transaction_id)
        _require_token(self.code, _CODE, "code")
        if type(self.checks) is not tuple or not all(
            isinstance(check, CheckResult) for check in self.checks
        ):
            raise ValueError("storage checks are invalid")
        status_fields = (
            self.storage_state,
            self.mounted,
            self.runtime_allowed,
            self.recovery,
        )
        if self.operation != "status":
            if any(value is not None for value in status_fields):
                raise ValueError("status fields are only valid for status")
            return
        if any(value is None for value in status_fields):
            raise ValueError("status results require all status fields")
        _require_token(self.storage_state, _CODE, "state")
        if type(self.mounted) is not bool or type(self.runtime_allowed) is not bool:
            raise ValueError("storage status booleans are invalid")
        if self.recovery != "UNCLEAR":
            raise ValueError("storage recovery is invalid")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": 1,
            "operation": self.operation,
            "verdict": self.verdict,
            "transaction_id": self.transaction_id,
            "code": self.code,
            "checks": [
                {
                    "id": check.id,
                    "status": check.status,
                    "evidence": check.evidence,
                }
                for check in self.checks
            ],
            "private_paths_redacted": True,
        }
        if self.operation == "status":
            result.update(
                {
                    "storage_state": self.storage_state,
                    "mounted": self.mounted,
                    "runtime_allowed": self.runtime_allowed,
                    "recovery": self.recovery,
                }
            )
        return result
