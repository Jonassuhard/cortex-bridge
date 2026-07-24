"""cortex.v1 decision protocol (mission spec §10) and report protocol (§11).

Strict validation of orchestrator decisions and construction of execution
reports. No network, no external deps — stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Iterable

PROTOCOL_VERSION = "cortex.v1"

DECISION_STATES = ("EXECUTE", "REQUEST_CONTEXT", "COMPLETE", "BLOCKED")

ALLOWED_TOOLS = (
    "list_directory",
    "read_file",
    "file_exists",
    "search_text",
    "write_file",
    "apply_patch",
    "create_directory",
    "run_process",
    "run_tests",
    "git_status",
    "git_diff",
)

READ_ONLY_TOOLS = frozenset(
    {"list_directory", "read_file", "file_exists", "search_text", "git_status", "git_diff"}
)
WRITE_TOOLS = frozenset({"write_file", "apply_patch", "create_directory", "run_process", "run_tests"})

REPORT_STATUSES = ("SUCCEEDED", "FAILED", "BLOCKED", "DENIED", "CANCELLED")

DECISION_FIELDS = frozenset(
    {
        "protocol",
        "missionId",
        "actionId",
        "iteration",
        "state",
        "summary",
        "action",
        "acceptanceCriteria",
        "requiresApproval",
        "terminal",
    }
)

# Per-tool argument contract: required keys and allowed key → type.
TOOL_ARGUMENTS: dict[str, dict[str, Any]] = {
    "list_directory": {"required": [], "types": {"path": str, "maxEntries": int}},
    "read_file": {"required": ["path"], "types": {"path": str, "maxBytes": int}},
    "file_exists": {"required": ["path"], "types": {"path": str}},
    "search_text": {
        "required": ["pattern"],
        "types": {"pattern": str, "path": str, "isRegex": bool, "maxResults": int},
    },
    "write_file": {"required": ["path", "content"], "types": {"path": str, "content": str}},
    "apply_patch": {"required": ["path", "replacements"], "types": {"path": str, "replacements": list}},
    "create_directory": {"required": ["path"], "types": {"path": str}},
    "run_process": {
        "required": ["argv"],
        "types": {"argv": list, "cwd": str, "timeoutSeconds": (int, float)},
    },
    "run_tests": {"required": [], "types": {"command": str, "cwd": str, "timeoutSeconds": (int, float)}},
    "git_status": {"required": [], "types": {}},
    "git_diff": {"required": [], "types": {"path": str}},
}

# Argument keys that must be workspace-relative paths.
_PATH_KEYS = ("path", "cwd", "directory", "dir", "target")


class DecisionError(Exception):
    """A cortex.v1 decision failed validation. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Extraction (§9): exactly one ```cortex-decision fenced block.
# ---------------------------------------------------------------------------

_DECISION_BLOCK_RE = re.compile(r"```cortex-decision[ \t]*\r?\n(.*?)```", re.DOTALL)
_REPORT_FENCE = "```cortex-report"


def extract_decision_block(message: str) -> dict:
    """Pull exactly one ```cortex-decision fenced block from an assistant message.

    Rejects 0 or 2+ blocks. Any other JSON or code in the message is ignored.
    Returns the parsed JSON object.
    """
    if not isinstance(message, str):
        raise DecisionError("INVALID_MESSAGE", "assistant message must be text")
    blocks = _DECISION_BLOCK_RE.findall(message)
    if len(blocks) == 0:
        raise DecisionError("NO_DECISION_BLOCK", "no ```cortex-decision block found")
    if len(blocks) > 1:
        raise DecisionError(
            "MULTIPLE_DECISION_BLOCKS",
            f"expected exactly one ```cortex-decision block, found {len(blocks)}",
        )
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        raise DecisionError("INVALID_JSON", f"decision block is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DecisionError("NOT_AN_OBJECT", "decision block must contain a JSON object")
    return data


# ---------------------------------------------------------------------------
# Path safety (§10/§15): relative only, no absolute, no parent traversal.
# ---------------------------------------------------------------------------

def check_relative_path(value: Any, field: str = "path") -> str:
    """Validate a workspace-relative path argument. Returns the path string."""
    if not isinstance(value, str) or not value.strip():
        raise DecisionError("MALFORMED_ARGUMENTS", f"{field} must be a non-empty string")
    if value.startswith("~") or os.path.isabs(value) or re.match(r"^[A-Za-z]:[\\/]", value):
        raise DecisionError("ABSOLUTE_PATH", f"{field} must be relative, got {value!r}")
    parts = re.split(r"[\\/]+", value)
    if any(part == ".." for part in parts):
        raise DecisionError("PATH_TRAVERSAL", f"{field} must not contain '..': {value!r}")
    if "\x00" in value:
        raise DecisionError("MALFORMED_ARGUMENTS", f"{field} contains NUL")
    return value


def _validate_arguments(tool: str, arguments: Any) -> dict:
    if not isinstance(arguments, dict):
        raise DecisionError("MALFORMED_ARGUMENTS", f"arguments for {tool} must be an object")
    schema = TOOL_ARGUMENTS[tool]
    allowed = schema["types"]
    for key in arguments:
        if key not in allowed:
            raise DecisionError(
                "MALFORMED_ARGUMENTS", f"unknown argument {key!r} for tool {tool}"
            )
    for key in schema["required"]:
        if key not in arguments:
            raise DecisionError(
                "MALFORMED_ARGUMENTS", f"missing required argument {key!r} for tool {tool}"
            )
    for key, value in arguments.items():
        expected = allowed[key]
        # bool is a subclass of int; do not accept bools where numbers are wanted.
        if expected in (int, (int, float)) and isinstance(value, bool):
            raise DecisionError(
                "MALFORMED_ARGUMENTS", f"argument {key!r} for {tool} must be a number"
            )
        if not isinstance(value, expected):
            name = getattr(expected, "__name__", str(expected))
            raise DecisionError(
                "MALFORMED_ARGUMENTS",
                f"argument {key!r} for {tool} must be {name}",
            )
    # Structured constraints per tool.
    if tool == "run_process":
        argv = arguments.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(a, str) or not a for a in argv)
        ):
            raise DecisionError(
                "MALFORMED_ARGUMENTS", "run_process argv must be a non-empty list of strings"
            )
        timeout = arguments.get("timeoutSeconds")
        if timeout is not None and not (0 < timeout <= 600):
            raise DecisionError(
                "MALFORMED_ARGUMENTS", "timeoutSeconds must be within (0, 600]"
            )
    if tool == "apply_patch":
        replacements = arguments.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            raise DecisionError(
                "MALFORMED_ARGUMENTS", "apply_patch replacements must be a non-empty list"
            )
        for i, rep in enumerate(replacements):
            if not isinstance(rep, dict) or set(rep) != {"old", "new"}:
                raise DecisionError(
                    "MALFORMED_ARGUMENTS",
                    f"replacement #{i} must be an object with exactly 'old' and 'new'",
                )
            if not isinstance(rep["old"], str) or not rep["old"]:
                raise DecisionError(
                    "MALFORMED_ARGUMENTS", f"replacement #{i} 'old' must be non-empty text"
                )
            if not isinstance(rep["new"], str):
                raise DecisionError(
                    "MALFORMED_ARGUMENTS", f"replacement #{i} 'new' must be text"
                )
    # Path confinement for every path-typed key.
    for key in _PATH_KEYS:
        if key in arguments:
            check_relative_path(arguments[key], key)
    return arguments


# ---------------------------------------------------------------------------
# Decision validation (§10).
# ---------------------------------------------------------------------------

def validate_decision(
    data: Any,
    *,
    expected_mission_id: str,
    expected_iteration: int,
    seen_action_ids: Iterable[str] = (),
) -> dict:
    """Validate a parsed cortex.v1 decision. Returns it unchanged on success.

    Raises DecisionError with a stable machine-readable code otherwise.
    """
    if not isinstance(data, dict):
        raise DecisionError("NOT_AN_OBJECT", "decision must be a JSON object")

    unknown = set(data) - DECISION_FIELDS
    if unknown:
        raise DecisionError("UNKNOWN_FIELD", f"unknown fields: {sorted(unknown)}")

    if data.get("protocol") != PROTOCOL_VERSION:
        raise DecisionError(
            "INVALID_PROTOCOL", f"protocol must be {PROTOCOL_VERSION!r}"
        )

    mission_id = data.get("missionId")
    if not isinstance(mission_id, str) or mission_id != expected_mission_id:
        raise DecisionError(
            "WRONG_MISSION_ID",
            f"missionId {mission_id!r} does not match expected {expected_mission_id!r}",
        )

    action_id = data.get("actionId")
    if not isinstance(action_id, str):
        raise DecisionError("MALFORMED_ARGUMENTS", "actionId must be a string")
    try:
        uuid.UUID(action_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise DecisionError("MALFORMED_ARGUMENTS", "actionId must be a UUID") from exc
    if action_id in set(seen_action_ids):
        raise DecisionError("REPEATED_ACTION_ID", f"actionId {action_id} was already used")

    iteration = data.get("iteration")
    if isinstance(iteration, bool) or not isinstance(iteration, int):
        raise DecisionError("WRONG_ITERATION", "iteration must be an integer")
    if iteration != expected_iteration:
        raise DecisionError(
            "WRONG_ITERATION",
            f"iteration {iteration} does not match expected {expected_iteration}",
        )

    state = data.get("state")
    if state not in DECISION_STATES:
        raise DecisionError("UNKNOWN_STATE", f"state must be one of {DECISION_STATES}")

    if not isinstance(data.get("summary"), str):
        raise DecisionError("MALFORMED_ARGUMENTS", "summary must be a string")
    for flag in ("requiresApproval", "terminal"):
        if not isinstance(data.get(flag), bool):
            raise DecisionError("MALFORMED_ARGUMENTS", f"{flag} must be a boolean")

    criteria = data.get("acceptanceCriteria")
    if criteria is None or not isinstance(criteria, list) or any(
        not isinstance(c, str) for c in criteria
    ):
        raise DecisionError(
            "MISSING_ACCEPTANCE_CRITERIA",
            "acceptanceCriteria must be present as a list of strings",
        )

    action = data.get("action")
    if state == "EXECUTE":
        if not criteria:
            raise DecisionError(
                "MISSING_ACCEPTANCE_CRITERIA",
                "EXECUTE decisions require non-empty acceptanceCriteria",
            )
        if not isinstance(action, dict):
            raise DecisionError("MISSING_ACTION", "EXECUTE requires an action object")
        tool = action.get("tool")
        if tool not in ALLOWED_TOOLS:
            raise DecisionError("UNKNOWN_TOOL", f"unknown tool {tool!r}")
        if set(action) - {"tool", "arguments"}:
            raise DecisionError(
                "UNKNOWN_FIELD", "action may only contain 'tool' and 'arguments'"
            )
        _validate_arguments(tool, action.get("arguments", {}))
    elif state == "REQUEST_CONTEXT":
        if action is not None:
            if not isinstance(action, dict):
                raise DecisionError(
                    "MISSING_ACTION", "REQUEST_CONTEXT action must be an object or null"
                )
            tool = action.get("tool")
            if tool not in ALLOWED_TOOLS:
                raise DecisionError("UNKNOWN_TOOL", f"unknown tool {tool!r}")
            if tool not in READ_ONLY_TOOLS:
                raise DecisionError(
                    "UNKNOWN_TOOL",
                    f"REQUEST_CONTEXT may only use read-only tools, not {tool!r}",
                )
            if set(action) - {"tool", "arguments"}:
                raise DecisionError(
                    "UNKNOWN_FIELD", "action may only contain 'tool' and 'arguments'"
                )
            _validate_arguments(tool, action.get("arguments", {}))
    elif state == "COMPLETE":
        # Terminal COMPLETE without validation instructions is rejected (§10).
        if not criteria:
            raise DecisionError(
                "COMPLETE_WITHOUT_VALIDATION",
                "COMPLETE requires acceptanceCriteria as validation instructions",
            )
    # BLOCKED: action may be null; empty criteria allowed.

    return data


def decision_action_key(decision: dict) -> str:
    """Canonical identity of the action a decision asks for (loop detection)."""
    action = decision.get("action") or {}
    tool = action.get("tool") or ""
    arguments = action.get("arguments") or {}
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return f"{decision.get('state')}|{tool}|{canonical}"


# ---------------------------------------------------------------------------
# Report builder (§11).
# ---------------------------------------------------------------------------

REPORT_FIELDS = frozenset(
    {
        "protocol",
        "missionId",
        "actionId",
        "iteration",
        "status",
        "summary",
        "tool",
        "toolResult",
        "filesChanged",
        "validation",
        "blockers",
        "artifacts",
    }
)


def build_report(
    *,
    mission_id: str,
    action_id: str,
    iteration: int,
    status: str,
    summary: str,
    tool: str | None,
    tool_result: dict | None = None,
    files_changed: list[str] | None = None,
    validation: dict | None = None,
    blockers: list[str] | None = None,
    artifacts: list[str] | None = None,
) -> dict:
    """Build a §11 execution report. Raises ValueError on invalid input."""
    if status not in REPORT_STATUSES:
        raise ValueError(f"status must be one of {REPORT_STATUSES}")
    result = {
        "exitCode": 0,
        "stdout": "",
        "stderr": "",
    }
    if tool_result:
        result.update(tool_result)
    if validation is None:
        validation = {"passed": status == "SUCCEEDED", "checks": []}
    return {
        "protocol": PROTOCOL_VERSION,
        "missionId": mission_id,
        "actionId": action_id,
        "iteration": iteration,
        "status": status,
        "summary": summary,
        "tool": tool,
        "toolResult": result,
        "filesChanged": list(files_changed or []),
        "validation": validation,
        "blockers": list(blockers or []),
        "artifacts": list(artifacts or []),
    }


def render_report_message(report: dict) -> str:
    """Render the transport payload: one ```cortex-report fence, nothing else."""
    if set(report) - REPORT_FIELDS:
        raise ValueError("report contains unknown fields")
    body = json.dumps(report, indent=2, sort_keys=False)
    return f"{_REPORT_FENCE}\n{body}\n```"
