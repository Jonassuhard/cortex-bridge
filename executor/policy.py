"""Policy engine for Cortex Bridge (mission spec §7.3 / §16 — data model only).

* workspace allowlist;
* per-tool approval requirements (reads free, writes/process need approval
  by default — "Workspace-write with approvals" is the default mode);
* command restrictions (delegates to tools.check_command_allowed);
* model selection hook (primary / single fallback attempt per action);
* denial of external side effects.

No UI here: approval *decisions* are recorded through ``approve()`` and the
UI layer (Phase 6) will drive them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .tools import ProcessCapabilities, ToolDenied, check_command_allowed, detect_test_command

# §16 approval modes.
READ_ONLY_AUTOMATIC = "read-only-automatic"
WRITE_WITH_APPROVALS = "workspace-write-with-approvals"  # default
WRITE_AUTOMATIC = "workspace-write-automatic"

READ_TOOLS = frozenset(
    {"list_directory", "read_file", "file_exists", "search_text", "git_status", "git_diff"}
)
WRITE_TOOLS = frozenset({"write_file", "apply_patch", "create_directory", "run_process", "run_tests"})
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS

# §16 approval scopes.
SCOPE_ONCE = "once"
SCOPE_TOOL_FOR_MISSION = "tool-for-mission"
SCOPE_ALL_WRITES_FOR_MISSION = "all-writes-for-mission"

# Categories never supported in the first release (§16).
NEVER_SUPPORTED = (
    "deployment",
    "push",
    "publishing",
    "payment",
    "email sending",
    "account modification",
    "credential access",
)

DEFAULT_PRIMARY_MODEL = "orchestra-executor"
DEFAULT_FALLBACK_MODEL = "orchestra-executor-fallback"


@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    tool: str
    reason: str
    denial_code: str | None = None


@dataclass
class ModelSelection:
    model: str
    is_fallback: bool
    allowed: bool
    reason: str = ""


@dataclass
class PolicyEngine:
    """Deterministic policy for one mission."""

    workspace: Path | str
    allowed_workspaces: list[Path | str] | None = None
    mode: str = WRITE_WITH_APPROVALS
    test_commands: list[list[str]] | None = None
    allow_processes: bool = False
    primary_model: str = DEFAULT_PRIMARY_MODEL
    fallback_model: str = DEFAULT_FALLBACK_MODEL
    _approvals: set[tuple[str, str | None]] = field(default_factory=set)
    _fallback_used: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.workspace = Path(self.workspace).resolve()
        if self.allowed_workspaces is None:
            self.allowed_workspaces = [self.workspace]
        else:
            self.allowed_workspaces = [Path(w).resolve() for w in self.allowed_workspaces]
        if self.mode not in (READ_ONLY_AUTOMATIC, WRITE_WITH_APPROVALS, WRITE_AUTOMATIC):
            raise ValueError(f"unknown approval mode {self.mode!r}")

    # -- workspace allowlist ------------------------------------------------------

    def workspace_allowed(self) -> bool:
        return any(
            self.workspace == w or self.workspace in w.parents or w in self.workspace.parents
            for w in self.allowed_workspaces
        )

    @property
    def process_capabilities(self) -> ProcessCapabilities:
        """The exact process privileges granted to this mission."""
        return ProcessCapabilities(allowed=self.allow_processes)

    # -- action evaluation ------------------------------------------------------------

    def evaluate(self, tool: str, arguments: dict | None = None) -> PolicyDecision:
        """Evaluate one structured action. Never raises for policy denials."""
        arguments = arguments or {}
        if not self.workspace_allowed():
            return PolicyDecision(
                False, False, tool, "workspace is not on the allowlist", "WORKSPACE_DENIED"
            )
        if tool not in ALL_TOOLS:
            return PolicyDecision(False, False, tool, f"unknown tool {tool!r}", "UNKNOWN_TOOL")
        if tool in WRITE_TOOLS and self.mode == READ_ONLY_AUTOMATIC:
            return PolicyDecision(
                False,
                False,
                tool,
                f"{tool} is a write/process tool and the mission is read-only",
                "READ_ONLY_MODE",
            )
        if tool in {"run_process", "run_tests"} and not self.process_capabilities.allowed:
            return PolicyDecision(
                False,
                False,
                tool,
                "process execution was not enabled for this mission",
                "PROCESS_CAPABILITY_DENIED",
            )
        # Deterministic command restrictions for process tools (§15).
        if tool == "run_process":
            try:
                check_command_allowed(list(arguments.get("argv") or []), self.workspace)
            except ToolDenied as exc:
                return PolicyDecision(False, False, tool, exc.message, exc.code)
        if tool == "run_tests":
            requested = arguments.get("argv")
            allowed = list(self.test_commands or [])
            detected = detect_test_command(self.workspace)
            if detected is not None:
                allowed.append(detected)
            if not allowed:
                return PolicyDecision(
                    False,
                    False,
                    tool,
                    "no configured or manifest-detected test command",
                    "NO_TEST_COMMAND",
                )
            if requested is not None:
                if (
                    not isinstance(requested, list)
                    or not requested
                    or not all(isinstance(arg, str) and arg for arg in requested)
                ):
                    return PolicyDecision(
                        False, False, tool, "test argv must be a non-empty list of strings", "MALFORMED_ARGUMENTS"
                    )
                if requested not in allowed:
                    return PolicyDecision(
                        False,
                        False,
                        tool,
                        f"unconfigured test command: {requested!r}",
                        "UNCONFIGURED_TEST_COMMAND",
                    )
        if tool in {"run_process", "run_tests"}:
            return PolicyDecision(True, True, tool, "allowed pending per-command approval")
        requires_approval = tool in WRITE_TOOLS and self.mode == WRITE_WITH_APPROVALS
        if requires_approval and self._approval_satisfied(tool):
            requires_approval = False
        return PolicyDecision(True, requires_approval, tool, "allowed")

    # -- approvals (§16 scopes) ------------------------------------------------------------

    def approve(self, scope: str, *, tool: str | None = None) -> None:
        """Record a user approval: once / this tool for this mission / all writes."""
        if scope == SCOPE_ONCE:
            if tool is None:
                raise ValueError("SCOPE_ONCE requires a tool")
            self._approvals.add((SCOPE_ONCE, tool))
        elif scope == SCOPE_TOOL_FOR_MISSION:
            if tool is None:
                raise ValueError("SCOPE_TOOL_FOR_MISSION requires a tool")
            self._approvals.add((SCOPE_TOOL_FOR_MISSION, tool))
        elif scope == SCOPE_ALL_WRITES_FOR_MISSION:
            self._approvals.add((SCOPE_ALL_WRITES_FOR_MISSION, None))
        else:
            raise ValueError(f"unknown approval scope {scope!r}")

    def _approval_satisfied(self, tool: str) -> bool:
        if (SCOPE_ALL_WRITES_FOR_MISSION, None) in self._approvals:
            return True
        if (SCOPE_TOOL_FOR_MISSION, tool) in self._approvals:
            return True
        if (SCOPE_ONCE, tool) in self._approvals:
            self._approvals.discard((SCOPE_ONCE, tool))  # consumed
            return True
        return False

    def approval_satisfied(self, tool: str) -> bool:
        """Peek without consuming a one-shot approval."""
        if (SCOPE_ALL_WRITES_FOR_MISSION, None) in self._approvals:
            return True
        if (SCOPE_TOOL_FOR_MISSION, tool) in self._approvals:
            return True
        return (SCOPE_ONCE, tool) in self._approvals

    # -- model selection hook (§7.4: one fallback attempt per action) -----------------------

    def select_model(self, action_key: str, *, failure_count: int = 0) -> ModelSelection:
        """Primary model first; exactly one fallback attempt per action."""
        if failure_count <= 0:
            return ModelSelection(self.primary_model, False, True)
        if action_key in self._fallback_used:
            return ModelSelection(
                self.primary_model,
                False,
                False,
                "fallback already used for this action (max 1 attempt)",
            )
        self._fallback_used.add(action_key)
        return ModelSelection(self.fallback_model, True, True)
