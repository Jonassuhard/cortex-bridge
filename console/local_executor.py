"""Executor adapter for the Cortex Bridge console.

Two modes, selected automatically at task time:

- LIVE        — only if Ollama responds on 127.0.0.1:11434 AND the
                `orchestra-executor` model is installed/loaded AND the model
                storage volume is mounted. The console IS the executor
                harness: it drives Ollama /api/chat directly with one `shell`
                tool and a strict JSON status schema, validates every tool
                request (workspace jail + denylist), executes the commands
                itself, and verifies evidence before accepting success.
- SIMULATION  — default fallback. Emits a realistic fake execution (6-10 log
                lines with small delays) and a complete structured report
                tagged with "mode": "simulation".
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable
from urllib.request import Request, urlopen

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_ENDPOINT}/api/tags"
OLLAMA_CHAT_URL = f"{OLLAMA_ENDPOINT}/api/chat"
CODEX_HOME = Path.home() / ".codex-cortex-bridge"
CONFIG_TOML = CODEX_HOME / "config.toml"

# Local model storage lives on the external DJO volume; override with
# CORTEX_STORAGE_PATH to test the disk-missing code path.
DEFAULT_STORAGE_PATH = "/Volumes/DJO/AI/Ollama/models"
VOLUME_ROOT = "/Volumes/DJO"
STORAGE_UNAVAILABLE = "LOCAL_MODEL_STORAGE_UNAVAILABLE"

PRIMARY_EXECUTOR = "orchestra-executor"
FALLBACK_EXECUTOR = "orchestra-executor-fallback"

Emit = Callable[[str, str], Awaitable[None]]  # emit(text, kind)


def probe_ollama(timeout: float = 1.0) -> bool:
    """Return True if the local Ollama daemon answers /api/tags."""
    try:
        with urlopen(OLLAMA_TAGS_URL, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def active_model() -> str:
    """Read the model name from the Cortex Bridge Codex profile, if present."""
    if not CONFIG_TOML.is_file():
        return "not configured"
    try:
        for line in CONFIG_TOML.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\s*model\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return "not configured"


def detect_mode() -> str:
    """'live' when Ollama is up, storage is mounted and the primary executor
    model is installed or loaded; else 'simulation'."""
    if (
        volume_mounted()
        and probe_ollama()
        and model_state(PRIMARY_EXECUTOR) in ("installed", "loaded")
    ):
        return "live"
    return "simulation"


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
    """Full local-runtime snapshot for GET /api/status."""
    up = probe_ollama(timeout=1.0)
    mode = detect_mode()
    return {
        "ollama_up": up,
        "ollama_status": "healthy" if up else "unhealthy",
        "endpoint": OLLAMA_ENDPOINT,
        "storage_path": storage_path(),
        "volume_mounted": volume_mounted(),
        "storage_status": storage_status(),
        "primary": {"name": PRIMARY_EXECUTOR, "state": model_state(PRIMARY_EXECUTOR)},
        "fallback": {"name": FALLBACK_EXECUTOR, "state": model_state(FALLBACK_EXECUTOR)},
        "mode": mode,
        "model": PRIMARY_EXECUTOR if mode == "live" else active_model(),
    }


def _slugify(text: str, max_words: int = 4) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with",
            "me", "my", "this", "that", "it", "is", "are", "be", "please"}
    words = [w for w in words if w not in stop]
    return "-".join(words[:max_words]) or "task"


async def run_task(task: dict, emit: Emit) -> dict:
    """Dispatch to live or simulation; returns the structured report."""
    if detect_mode() == "live":
        return await _run_live(task, emit)
    return await _run_simulation(task, emit)


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

SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Run a shell command inside the authorized workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": "Shell command to run; use relative paths, it "
                                   "executes with the workspace as working directory",
                },
                "workdir": {
                    "type": "string",
                    "description": "Optional subdirectory inside the workspace (relative)",
                },
            },
            "required": ["cmd"],
            "additionalProperties": False,
        },
    },
}

MAX_TOOL_STEPS = 8          # hard cap on shell executions per task
WALL_CLOCK_S = 300          # total task wall-clock guard
CMD_TIMEOUT_S = 60          # per-command timeout
CHAT_TIMEOUT_S = 180        # per /api/chat call (includes model load time)
OUTPUT_TAIL = 2000          # truncation for captured command output

# Commands matching this pattern are refused before execution.
DENY_RE = re.compile(
    r"\bsudo\b"
    r"|\brm\s+-[rf]+\s+/"
    r"|\bcurl\b.*\b(post|upload)\b"
    r"|\bgit\s+push\b"
    r"|\b(brew|npm|pip)\s+install\b"
    r"|>\s*/etc"
    r"|\bssh\b"
    r"|\b(kill|pkill)\b",
    re.IGNORECASE,
)

# Absolute-path tokens inside a command (pragmatic jail check).
_ABS_TOKEN_RE = re.compile(r"(?:^|[\s;|&'\"(])((?:/[\w.\-]|~/)[^\s;|&>'\")]*)")


def _chat_sync(messages: list[dict]) -> str:
    """Blocking /api/chat call; returns the raw message content."""
    body = {
        "model": PRIMARY_EXECUTOR,
        "messages": messages,
        "stream": False,
        "format": RESPONSE_SCHEMA,
        "tools": [SHELL_TOOL],
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


def _jail_check(cmd: str, workdir: str | None, workspace: Path) -> tuple[bool, Path, str]:
    """Validate a shell request. Returns (ok, resolved_cwd, refusal_reason)."""
    if DENY_RE.search(cmd):
        return False, workspace, f"command matches the bridge denylist: {cmd[:120]}"

    # workdir must resolve inside the workspace
    try:
        if workdir:
            wd = Path(workdir).expanduser()
            cwd = wd.resolve() if wd.is_absolute() else (workspace / wd).resolve()
        else:
            cwd = workspace
        cwd.relative_to(workspace)
    except (OSError, ValueError):
        return False, workspace, f"workdir escapes the authorized workspace: {workdir}"

    # absolute path tokens must stay inside the workspace
    for token in _ABS_TOKEN_RE.findall(cmd):
        if token.startswith("~"):
            return False, workspace, f"home-relative path not allowed in command: {token}"
        try:
            Path(token).resolve().relative_to(workspace)
        except (OSError, ValueError):
            return False, workspace, f"absolute path outside the workspace: {token}"
    return True, cwd, ""


def _report(status: str, summary: str, commands_run: list[str],
            files_changed: list[str], blockers: list[str], next_step: str) -> dict:
    return {
        "status": status,
        "summary": summary,
        "commands_run": commands_run,
        "files_changed": files_changed,
        "blockers": blockers,
        "suggested_next_step": next_step,
        "mode": "live",
    }


async def _run_live(task: dict, emit: Emit) -> dict:
    goal: str = task["goal"]
    constraints: list[str] = task.get("constraints") or []
    workspace = Path(task.get("workspace") or "~").expanduser().resolve()

    await emit(f"executor mode: live (Ollama /api/chat → {PRIMARY_EXECUTOR})", "info")
    await emit(f"workspace jail: {workspace}", "info")

    before = _snapshot(workspace)

    first = (
        f"Goal: {goal}\n\n"
        + (f"Constraints:\n" + "\n".join(f"- {c}" for c in constraints) + "\n\n" if constraints else "")
        + f"Authorized workspace: {workspace}\n"
        "The workspace above is the ONLY allowed root. Use relative paths in "
        "shell commands — the bridge executes them with the workspace as the "
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
    started = time.monotonic()

    while True:
        if time.monotonic() - started > WALL_CLOCK_S:
            await emit("wall-clock limit reached (5 min)", "error")
            return _report("failed", "Task exceeded the 5-minute wall-clock guard.",
                           commands_run, [], ["wall-clock limit reached"],
                           "Split the goal into smaller atomic tasks and retry.")

        try:
            raw = await asyncio.to_thread(_chat_sync, messages)
        except Exception as exc:
            await emit(f"ollama /api/chat call failed: {exc}", "error")
            return _report("failed", f"Ollama chat call failed: {exc}",
                           commands_run, [], [f"chat error: {exc}"],
                           "Check that Ollama is running and the model is loaded, then retry.")

        parsed = _parse_status(raw)
        if parsed is None:
            invalid_replies += 1
            await emit("model reply was not a valid status JSON object", "error")
            if invalid_replies >= 2:
                return _report("failed", "Model repeatedly answered outside the status schema.",
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

        if status == "READY_FOR_TOOL" and tool == "shell":
            if steps >= MAX_TOOL_STEPS:
                await emit("step limit reached (8 tool executions)", "error")
                return _report("failed", "Step limit reached: 8 tool executions.",
                               commands_run, [], ["step limit reached"],
                               "Split the goal into smaller atomic tasks and retry.")
            cmd = str(args.get("cmd") or "").strip()
            if not cmd:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 "Empty cmd. Provide a non-empty shell command, "
                                 "or reply BLOCKED."})
                continue
            ok, cwd, reason = _jail_check(cmd, args.get("workdir"), workspace)
            messages.append({"role": "assistant", "content": raw})
            if not ok:
                await emit(f"bridge refused command: {reason}", "error")
                messages.append({"role": "user", "content":
                                 f"Tool request refused by the bridge: {reason}. "
                                 "Respond BLOCKED or propose a compliant action "
                                 "inside the workspace."})
                continue
            steps += 1
            commands_run.append(cmd)
            await emit(f"$ {cmd}", "command")
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=str(cwd),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    out_bytes, _ = await asyncio.wait_for(proc.communicate(), CMD_TIMEOUT_S)
                    rc = proc.returncode or 0
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    out_bytes, rc = b"[bridge] command killed after 60s timeout", 124
            except OSError as exc:
                out_bytes, rc = f"[bridge] failed to start command: {exc}".encode(), 126
            output = out_bytes.decode("utf-8", errors="replace").strip()[:OUTPUT_TAIL]
            if output:
                await emit(output[-OUTPUT_TAIL:], "info" if rc == 0 else "error")
            if rc != 0:
                await emit(f"exit code {rc}", "error")
            messages.append({"role": "user", "content":
                             f"Tool result (exit {rc}):\n{output or '(no output)'}"})
            continue

        if status == "READY_FOR_TOOL":  # asked for a tool that is not `shell`
            await emit(f"model requested unavailable tool: {tool}", "error")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                             f"The tool '{tool}' does not exist. The only tool is "
                             "'shell'. Reply READY_FOR_TOOL with tool 'shell', "
                             "or BLOCKED if the task cannot be done with it."})
            continue

        if status == "READY_FOR_VALIDATION":
            if not commands_run:
                false_success_warnings += 1
                await emit("false-success guard: model claims completion with no executed tool", "error")
                if false_success_warnings >= 2:
                    return _report(
                        "failed",
                        "Model claimed completion without executing any tool (false success).",
                        commands_run, [],
                        ["false success: READY_FOR_VALIDATION with zero executed commands"],
                        "Rephrase the goal as one atomic verifiable action and retry.")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 "No tool was executed; return READY_FOR_TOOL or BLOCKED."})
                continue
            changed = _files_changed(before, _snapshot(workspace))
            await emit(f"validation: {len(changed)} file(s) created/modified", "info")
            ok_v, proof = await _auto_validate(changed, workspace)
            if not ok_v:
                validation_retries += 1
                await emit(f"bridge auto-validation FAILED: {proof[:200]}", "error")
                if validation_retries >= 2:
                    return _report(
                        "failed",
                        "Bridge auto-validation failed twice on the produced files.",
                        commands_run, changed,
                        [f"auto-validation: {proof[:300]}"],
                        "Fix the file content (see validation error) and retry the task.")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                                 f"Bridge auto-validation of your produced files FAILED:\n"
                                 f"{proof}\n"
                                 "Fix the file with READY_FOR_TOOL (tool 'shell'), "
                                 "or reply FAILED if you cannot."})
                continue
            await emit("bridge auto-validation passed", "info")
            return _report("done", summary or "Executor finished successfully.",
                           commands_run, changed, [],
                           "Review the executor output and decide the next task.")

        if status == "BLOCKED":
            return _report("blocked", summary or "Executor reports BLOCKED.",
                           commands_run, [],
                           [summary] if summary else ["blocked"],
                           "Resolve the blocker (or re-scope the goal) and retry.")

        # FAILED
        return _report("failed", summary or "Executor reports FAILED.",
                       commands_run, [],
                       [summary] if summary else ["failed"],
                       "Inspect the log, adjust the goal or constraints, and retry.")


# ---------------------------------------------------------- simulation mode

async def _run_simulation(task: dict, emit: Emit) -> dict:
    goal: str = task["goal"]
    constraints: list[str] = task.get("constraints") or []
    workspace: str = task.get("workspace") or "~/"
    slug = _slugify(goal)

    files = [
        f"{slug}/README.md",
        f"{slug}/main.py",
        f"{slug}/tests/test_main.py",
    ]
    commands = [
        f"mkdir -p {workspace.rstrip('/')}/{slug}",
        f"cd {slug} && git init -q",
        "python -m py_compile main.py",
        "python -m pytest -q",
    ]

    await emit("executor mode: SIMULATION — local model not installed yet", "info")
    await asyncio.sleep(random.uniform(0.4, 0.8))
    await emit(f"goal: {goal[:96]}", "info")
    if constraints:
        await asyncio.sleep(random.uniform(0.4, 0.8))
        await emit(f"constraints: {'; '.join(constraints)[:96]}", "info")

    for cmd in commands:
        await asyncio.sleep(random.uniform(0.4, 0.8))
        await emit(f"$ {cmd}", "command")

    for f in files:
        await asyncio.sleep(random.uniform(0.4, 0.8))
        await emit(f"wrote {f}", "file")

    await asyncio.sleep(random.uniform(0.4, 0.8))
    await emit("all checks passed — building report", "info")

    return {
        "status": "done",
        "summary": (
            f"[SIMULATED] Scaffolded '{slug}' in {workspace}: created a README, "
            f"a main.py implementing the requested goal, and a passing pytest "
            f"suite (3 tests). No real commands were executed — this is a dry-run "
            f"preview of what the live executor will do once the local model is "
            f"installed."
        ),
        "commands_run": commands,
        "files_changed": files,
        "blockers": [],
        "suggested_next_step": (
            "Install the executor model (see executor/scripts/setup-executor.sh) "
            "and re-run this task in live mode to verify the simulated plan."
        ),
        "mode": "simulation",
    }
