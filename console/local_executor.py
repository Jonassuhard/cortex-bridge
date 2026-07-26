"""Executor adapter for the Cortex Bridge console.

Two modes, selected automatically at task time:

- LIVE        — only if Ollama responds on 127.0.0.1:11434 AND the
                `orchestra-executor` model is installed/loaded AND the model
                storage volume is mounted. The console IS the executor
                harness: it drives Ollama /api/chat directly with one
                `run_process` tool and a strict JSON status schema, validates every tool
                request (workspace jail + denylist), executes the commands
                itself, and verifies evidence before accepting success.
- UNAVAILABLE — default fallback. Refuses the task with
                `EXECUTOR_UNAVAILABLE`; it never claims simulated success.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.request import Request, urlopen

from executor.tools import ToolDenied, ToolError, ToolExecutor
from executor.policy import PolicyEngine

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_ENDPOINT}/api/tags"
OLLAMA_CHAT_URL = f"{OLLAMA_ENDPOINT}/api/chat"
# Local model storage lives on the external DJO volume; override with
# CORTEX_STORAGE_PATH to test the disk-missing code path.
DEFAULT_STORAGE_PATH = "/Volumes/DJO/AI/Ollama/models"
VOLUME_ROOT = "/Volumes/DJO"
STORAGE_UNAVAILABLE = "LOCAL_MODEL_STORAGE_UNAVAILABLE"

PRIMARY_EXECUTOR = "orchestra-executor"
DEVELOPMENT_FIXTURE_ENV = "CORTEX_ALLOW_DEVELOPMENT_FIXTURES"

Emit = Callable[[str, str], Awaitable[None]]  # emit(text, kind)


def probe_ollama(timeout: float = 1.0) -> bool:
    """Return True if the local Ollama daemon answers /api/tags."""
    try:
        with urlopen(OLLAMA_TAGS_URL, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def detect_mode() -> str:
    """'live' when Ollama is up, storage is mounted and the primary executor
    model is installed or loaded; else 'unavailable'."""
    if (
        volume_mounted()
        and probe_ollama()
        and model_state(PRIMARY_EXECUTOR) in ("installed", "loaded")
    ):
        return "live"
    return "unavailable"


# ------------------------------------------------------ local runtime status

def storage_path() -> str:
    """Model storage path; CORTEX_STORAGE_PATH overrides the DJO default."""
    return os.environ.get("CORTEX_STORAGE_PATH", DEFAULT_STORAGE_PATH)


def volume_mounted() -> bool:
    """True only if the DJO volume exists AND the storage path is accessible."""
    try:
        return Path(VOLUME_ROOT).exists() and os.access(storage_path(), os.R_OK)
    except OSError:
        return False


def storage_status() -> str:
    return "OK" if volume_mounted() else STORAGE_UNAVAILABLE


def _ollama_names(args: list[str]) -> set[str]:
    """Run `ollama <args>` and return the model names in the NAME column."""
    try:
        out = subprocess.run(
            ["ollama", *args],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    names: set[str] = set()
    for line in out.stdout.splitlines()[1:]:  # skip header
        cols = line.split()
        if cols:
            names.add(cols[0])
    return names


def model_state(name: str) -> str:
    """'loaded' (in `ollama ps`), 'installed' (in `ollama list`), or 'missing'.

    Never errors: if the volume is gone or Ollama is down, the model is
    reported as 'missing'.
    """
    if not volume_mounted() or not probe_ollama():
        return "missing"
    if any(n == name or n.startswith(name + ":") for n in _ollama_names(["ps"])):
        return "loaded"
    if any(n == name or n.startswith(name + ":") for n in _ollama_names(["list"])):
        return "installed"
    return "missing"


def runtime_status() -> dict:
    """Availability snapshot for GET /api/status.

    A healthy daemon and an installed model are candidates, not evidence that
    an executor ran.  Runtime execution truth therefore starts unavailable.
    """
    up = probe_ollama(timeout=1.0)
    executor_available = detect_mode() == "live"
    return {
        "ollama_up": up,
        "ollama_status": "healthy" if up else "unhealthy",
        "endpoint": OLLAMA_ENDPOINT,
        "storage_path": storage_path(),
        "volume_mounted": volume_mounted(),
        "storage_status": storage_status(),
        "primary": {"name": PRIMARY_EXECUTOR, "state": model_state(PRIMARY_EXECUTOR)},
        "executor_available": executor_available,
        "executor_kind": "unavailable",
        "executor_model_used": None,
        "runtime_mode": "live",
        "release_eligible": False,
    }


async def run_task(task: dict, emit: Emit) -> dict:
    """Run only when the reviewed local executor is available."""
    if (
        task.get("development_fixture") is True
        and os.environ.get(DEVELOPMENT_FIXTURE_ENV) == "1"
    ):
        await emit("development fixture requested explicitly; no executor ran", "info")
        return _report(
            "blocked",
            "Development fixture only; no command was executed.",
            [],
            [],
            ["DEVELOPMENT_FIXTURE_NOT_RELEASE_ELIGIBLE"],
            "Run again against a live executor for release evidence.",
            executor_kind="unavailable",
            executor_model_used=None,
            runtime_mode="development_fixture",
        )
    if detect_mode() == "live":
        return await _run_live(task, emit)
    await emit("local executor unavailable; refusing simulated completion", "error")
    return _report(
        "failed",
        "Local executor is unavailable; no command was simulated or executed.",
        [],
        [],
        ["EXECUTOR_UNAVAILABLE"],
        "Start the reviewed local executor and retry.",
        executor_kind="unavailable",
        executor_model_used=None,
        runtime_mode="live",
    )


# ---------------------------------------------------------------- live mode
#
# The console IS the executor harness (see docs/routing-policy.md): the model
# is a subordinate worker that only *requests* actions; the bridge controls
# the tools, validates every request, executes commands itself, and verifies
# evidence before accepting success. No Codex CLI dependency.

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["READY_FOR_TOOL", "READY_FOR_VALIDATION", "BLOCKED", "FAILED"],
        },
        "tool": {"type": ["string", "null"]},
        "arguments": {"type": "object"},
        "summary": {"type": "string"},
    },
    "required": ["status", "tool", "arguments", "summary"],
}

PROCESS_TOOL = {
    "type": "function",
    "function": {
        "name": "run_process",
        "description": "Run one reviewed executable vector inside the authorized workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Executable followed by literal arguments; no shell syntax.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional subdirectory inside the workspace (relative)",
                },
            },
            "required": ["argv"],
            "additionalProperties": False,
        },
    },
}

MAX_TOOL_STEPS = 8          # hard cap on process executions per task
WALL_CLOCK_S = 300          # total task wall-clock guard
CMD_TIMEOUT_S = 60          # per-command timeout
CHAT_TIMEOUT_S = 180        # per /api/chat call (includes model load time)
OUTPUT_TAIL = 2000          # truncation for captured command output

def _chat_sync(messages: list[dict], model: str = PRIMARY_EXECUTOR) -> str:
    """Blocking /api/chat call; returns the raw message content."""
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": RESPONSE_SCHEMA,
        "tools": [PROCESS_TOOL],
        "options": {"temperature": 0},
    }
    req = Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=CHAT_TIMEOUT_S) as resp:
        out = json.load(resp)
    return out["message"].get("content", "")


def _parse_status(raw: str) -> dict | None:
    """Parse the model's JSON status object; None if invalid."""
    try:
        p = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if (
        isinstance(p, dict)
        and p.get("status") in RESPONSE_SCHEMA["properties"]["status"]["enum"]
        and isinstance(p.get("arguments"), dict)
        and isinstance(p.get("summary"), str)
        and (p.get("tool") is None or isinstance(p.get("tool"), str))
    ):
        return p
    return None


def _snapshot(workspace: Path) -> dict[str, tuple[float, int]]:
    """Map of relative file path → (mtime, size) for the workspace."""
    snap: dict[str, tuple[float, int]] = {}
    try:
        for p in workspace.rglob("*"):
            if p.is_file():
                try:
                    st = p.stat()
                    snap[str(p.relative_to(workspace))] = (st.st_mtime, st.st_size)
                except OSError:
                    continue
    except OSError:
        pass
    return snap


def _files_changed(before: dict, after: dict) -> list[str]:
    """Relative paths created or modified between two snapshots."""
    return sorted(p for p, sig in after.items() if before.get(p) != sig)


SYNTAX_CHECK_SNIPPET = (
    "import sys; "
    "src = open(sys.argv[1], encoding='utf-8').read(); "
    "compile(src, sys.argv[1], 'exec')"
)


async def _auto_validate(changed: list[str], workspace: Path) -> tuple[bool, str]:
    """Bridge-side proof check on produced files.

    Every changed .py file must pass a real syntax compile. Returns
    (ok, evidence) — evidence is the compiler error output on failure.
    Never trusts the model's own claim: this is the bridge verifying.
    """
    for rel in changed:
        if not rel.endswith(".py"):
            continue
        path = (workspace / rel).resolve()
        try:
            path.relative_to(workspace)
        except ValueError:
            return False, f"{rel}: resolved path escapes the workspace"
        if not path.is_file():
            return False, f"{rel}: file listed as changed but missing on disk"
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", SYNTAX_CHECK_SNIPPET, str(path),
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 15)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return False, f"{rel}: syntax check timed out (15s)"
        except OSError as exc:
            return False, f"{rel}: could not run syntax check: {exc}"
        if proc.returncode != 0:
            evidence = out.decode("utf-8", errors="replace").strip()
            return False, f"{rel}: Python syntax error — {evidence}"
    return True, ""


def _report(status: str, summary: str, commands_run: list[str],
            files_changed: list[str], blockers: list[str], next_step: str,
            *, executor_kind: str, executor_model_used: str | None,
            runtime_mode: str) -> dict:
    report = {
        "status": status,
        "summary": summary,
        "commands_run": commands_run,
        "files_changed": files_changed,
        "blockers": blockers,
        "suggested_next_step": next_step,
        "executor_kind": executor_kind,
        "executor_model_used": executor_model_used,
        "runtime_mode": runtime_mode,
    }
    report["release_eligible"] = release_runtime_eligible(report)
    return report


def release_runtime_eligible(report: dict) -> bool:
    """Return whether runtime evidence may enter a release-pass result."""
    return (
        report.get("runtime_mode") == "live"
        and report.get("executor_kind") in {"deterministic", "ollama"}
        and report.get("status") in {"done", "COMPLETED"}
    )


async def _run_live(task: dict, emit: Emit, process_approval=None) -> dict:
    goal: str = task["goal"]
    constraints: list[str] = task.get("constraints") or []
    workspace = Path(task.get("workspace") or "~").expanduser().resolve()
    executor_model_used: str | None = None

    def report(status: str, summary: str, commands_run: list[str],
               files_changed: list[str], blockers: list[str], next_step: str) -> dict:
        return _report(
            status,
            summary,
            commands_run,
            files_changed,
            blockers,
            next_step,
            executor_kind="ollama" if executor_model_used else "unavailable",
            executor_model_used=executor_model_used,
            runtime_mode="live",
        )

    await emit(f"executor mode: live (Ollama /api/chat → {PRIMARY_EXECUTOR})", "info")
    await emit(f"workspace jail: {workspace}", "info")

    before = _snapshot(workspace)
    policy = PolicyEngine(workspace, allow_processes=bool(task.get("allow_processes", False)))

    first = (
        f"Goal: {goal}\n\n"
        + (f"Constraints:\n" + "\n".join(f"- {c}" for c in constraints) + "\n\n" if constraints else "")
        + f"Authorized workspace: {workspace}\n"
        "The workspace above is the ONLY allowed root. Use relative paths in "
        "structured process requests — the bridge executes them with the workspace as the "
        "working directory. Do not reference absolute paths outside the "
        "workspace. One atomic action per step. When the action is complete "
        "and its output is visible in the conversation, report "
        "READY_FOR_VALIDATION."
    )
    messages: list[dict] = [{"role": "user", "content": first}]

    commands_run: list[str] = []
    steps = 0
    invalid_replies = 0
    false_success_warnings = 0
    validation_retries = 0
    process_failures: list[str] = []
    started = time.monotonic()

    while True:
        if time.monotonic() - started > WALL_CLOCK_S:
            await emit("wall-clock limit reached (5 min)", "error")
            return report("failed", "Task exceeded the 5-minute wall-clock guard.",
                          commands_run, [], ["wall-clock limit reached"],
                          "Split the goal into smaller atomic tasks and retry.")

        try:
            raw = await asyncio.to_thread(_chat_sync, messages, PRIMARY_EXECUTOR)
            executor_model_used = PRIMARY_EXECUTOR
        except Exception as exc:
            await emit(f"ollama /api/chat call failed: {exc}", "error")
            return report("failed", f"Ollama chat call failed: {exc}",
                          commands_run, [], [f"chat error: {exc}"],
                          "Check that Ollama is running and the model is loaded, then retry.")

        parsed = _parse_status(raw)
        if parsed is None:
            invalid_replies += 1
            await emit("model reply was not a valid status JSON object", "error")
            if invalid_replies >= 2:
                return report("failed", "Model repeatedly answered outside the status schema.",
                              commands_run, [], ["invalid schema reply"],
                              "Inspect the live log; the model profile may be broken.")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             "Your reply did not match the required JSON schema. "
                             "Reply with exactly one JSON status object."})
            continue

        status = parsed["status"]
        summary = parsed["summary"]
        tool = parsed.get("tool")
        args = parsed.get("arguments") or {}
        await emit(f"executor: {status} — {summary[:140]}", "info")

        if status == "READY_FOR_TOOL" and tool == "run_process":
            if steps >= MAX_TOOL_STEPS:
                await emit("step limit reached (8 tool executions)", "error")
                return report("failed", "Step limit reached: 8 tool executions.",
                              commands_run, [], ["step limit reached"],
                              "Split the goal into smaller atomic tasks and retry.")
            argv = args.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 "argv must be a non-empty list of literal strings, "
                                 "or reply BLOCKED."})
                continue
            messages.append({"role": "assistant", "content": raw})
            policy_decision = policy.evaluate("run_process", {"argv": argv})
            if not policy_decision.allowed:
                await emit(f"bridge refused command: {policy_decision.reason}", "error")
                return report(
                    "failed", "Process capability denied for this task.", commands_run, [],
                    [policy_decision.denial_code or "PROCESS_CAPABILITY_DENIED"],
                    "Enable the mission process capability and submit the command for review.",
                )
            if policy_decision.requires_approval:
                if process_approval is None:
                    await emit("process command requires human approval", "error")
                    return report(
                        "blocked", "Process command requires explicit human approval.", commands_run, [],
                        ["PROCESS_APPROVAL_REQUIRED"],
                        "Approve this exact command in a reviewed mission flow.",
                    )
                approved = process_approval(argv, policy_decision)
                if inspect.isawaitable(approved):
                    approved = await approved
                if not approved:
                    await emit("process command approval denied", "error")
                    return report(
                        "blocked", "Process command approval was denied.", commands_run, [],
                        ["PROCESS_APPROVAL_DENIED"],
                        "Approve this exact command or revise the task.",
                    )
            steps += 1
            rendered = shlex.join(argv)
            commands_run.append(rendered)
            await emit(f"$ {rendered}", "command")
            try:
                result = await ToolExecutor(workspace).run_process(
                    argv,
                    cwd=str(args.get("cwd") or "."),
                    timeoutSeconds=min(float(args.get("timeoutSeconds") or CMD_TIMEOUT_S), CMD_TIMEOUT_S),
                )
                rc = result["exitCode"]
                output = (result["stdout"] + result["stderr"]).strip()[:OUTPUT_TAIL]
                if result["timedOut"]:
                    process_failures.append("PROCESS_TIMEOUT")
                if result["truncated"]:
                    process_failures.append("PROCESS_OUTPUT_TRUNCATED")
            except (ToolDenied, ToolError, ValueError) as exc:
                rc = 1
                output = f"[bridge] command refused: {exc}"
                process_failures.append("PROCESS_EXECUTION_DENIED")
            if output:
                await emit(output[-OUTPUT_TAIL:], "info" if rc == 0 else "error")
            if rc != 0:
                await emit(f"exit code {rc}", "error")
                if "PROCESS_TIMEOUT" not in process_failures:
                    process_failures.append("PROCESS_EXIT_NONZERO")
            messages.append({"role": "user", "content":
                             f"Tool result (exit {rc}):\n{output or '(no output)'}"})
            continue

        if status == "READY_FOR_TOOL":  # asked for a tool that is not structured process execution
            await emit(f"model requested unavailable tool: {tool}", "error")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             f"The tool '{tool}' does not exist. The only tool is "
                             "'run_process'. Reply READY_FOR_TOOL with tool 'run_process', "
                             "or BLOCKED if the task cannot be done with it."})
            continue

        if status == "READY_FOR_VALIDATION":
            if not commands_run:
                false_success_warnings += 1
                await emit("false-success guard: model claims completion with no executed tool", "error")
                if false_success_warnings >= 2:
                    return report(
                        "failed",
                        "Model claimed completion without executing any tool (false success).",
                        commands_run, [],
                        ["false success: READY_FOR_VALIDATION with zero executed commands"],
                        "Rephrase the goal as one atomic verifiable action and retry.")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 "No tool was executed; return READY_FOR_TOOL or BLOCKED."})
                continue
            if process_failures:
                await emit("process failure blocks completion", "error")
                return report(
                    "failed", "One or more process commands did not complete cleanly.",
                    commands_run, [], sorted(set(process_failures)),
                    "Resolve every process failure before requesting validation.",
                )
            changed = _files_changed(before, _snapshot(workspace))
            await emit(f"validation: {len(changed)} file(s) created/modified", "info")
            ok_v, proof = await _auto_validate(changed, workspace)
            if not ok_v:
                validation_retries += 1
                await emit(f"bridge auto-validation FAILED: {proof[:200]}", "error")
                if validation_retries >= 2:
                    return report(
                        "failed",
                        "Bridge auto-validation failed twice on the produced files.",
                        commands_run, changed,
                        [f"auto-validation: {proof[:300]}"],
                        "Fix the file content (see validation error) and retry the task.")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 f"Bridge auto-validation of your produced files FAILED:\n"
                                 f"{proof}\n"
                                 "Fix the file with READY_FOR_TOOL (tool 'run_process'), "
                                 "or reply FAILED if you cannot."})
                continue
            await emit("bridge auto-validation passed", "info")
            return report("done", summary or "Executor finished successfully.",
                          commands_run, changed, [],
                          "Review the executor output and decide the next task.")

        if status == "BLOCKED":
            return report("blocked", summary or "Executor reports BLOCKED.",
                          commands_run, [],
                          [summary] if summary else ["blocked"],
                          "Resolve the blocker (or re-scope the goal) and retry.")

        # FAILED
        return report("failed", summary or "Executor reports FAILED.",
                      commands_run, [],
                      [summary] if summary else ["failed"],
                      "Inspect the log, adjust the goal or constraints, and retry.")
