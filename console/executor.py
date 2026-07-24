"""Executor adapter for the Cortex Bridge console.

Two modes, selected automatically at task time:

- LIVE        — only if ~/.codex-cortex-bridge/config.toml exists AND Ollama
                responds on 127.0.0.1:11434 AND the `codex` binary is on PATH.
                Runs `codex exec` with CODEX_HOME pointed at the Cortex Bridge
                profile, cwd = task workspace, captures stdout, status done if
                exit code 0.
- SIMULATION  — default fallback. Emits a realistic fake execution (6-10 log
                lines with small delays) and a complete structured report
                tagged with "mode": "simulation".
"""

from __future__ import annotations

import asyncio
import random
import re
import shutil
import shlex
from pathlib import Path
from typing import Awaitable, Callable
from urllib.request import urlopen

OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
CODEX_HOME = Path.home() / ".codex-cortex-bridge"
CONFIG_TOML = CODEX_HOME / "config.toml"

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
    """'live' only when the full executor stack is present, else 'simulation'."""
    if CONFIG_TOML.is_file() and probe_ollama() and shutil.which("codex"):
        return "live"
    return "simulation"


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

async def _run_live(task: dict, emit: Emit) -> dict:
    goal = task["goal"]
    constraints = task.get("constraints") or []
    workspace = str(Path(task.get("workspace") or "~").expanduser())

    prompt = goal
    if constraints:
        prompt += "\n\nConstraints:\n" + "\n".join(f"- {c}" for c in constraints)

    await emit(f"executor mode: live (codex CLI → Ollama)", "info")
    await emit(f"$ codex exec {shlex.quote(goal[:80])}", "command")

    env = dict(**__import__("os").environ, CODEX_HOME=str(CODEX_HOME))
    try:
        proc = await asyncio.create_subprocess_exec(
            "codex", "exec", prompt,
            cwd=workspace,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        await emit("codex binary not found on PATH", "error")
        return {
            "status": "failed",
            "summary": "codex CLI was not found on PATH at execution time.",
            "commands_run": [],
            "files_changed": [],
            "blockers": ["codex binary missing"],
            "suggested_next_step": "Install the Codex CLI or fix PATH, then retry.",
            "mode": "live",
        }

    output_lines: list[str] = []
    commands_run: list[str] = [f"codex exec {shlex.quote(prompt[:120])}"]
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").rstrip()
        if not line:
            continue
        output_lines.append(line)
        kind = "command" if line.lstrip().startswith(("$", ">")) else "info"
        await emit(line, kind)

    rc = await proc.wait()
    tail = "\n".join(output_lines[-30:])
    if rc == 0:
        await emit("codex exited 0 — marking task done", "info")
        return {
            "status": "done",
            "summary": tail[-800:] or "Executor finished successfully.",
            "commands_run": commands_run,
            "files_changed": [],
            "blockers": [],
            "suggested_next_step": "Review the executor output and decide the next task.",
            "mode": "live",
        }
    await emit(f"codex exited with code {rc}", "error")
    return {
        "status": "failed",
        "summary": f"codex exited with code {rc}. Tail of output:\n{tail[-800:]}",
        "commands_run": commands_run,
        "files_changed": [],
        "blockers": [f"exit code {rc}"],
        "suggested_next_step": "Inspect the log, adjust the goal or constraints, and retry.",
        "mode": "live",
    }


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
