"""Structured local tools for the Cortex Bridge executor (mission spec §15).

Implements the 11 cortex.v1 tools directly in Python. No free-form shell:

* relative paths only, resolved under an authorized workspace;
* symlink escapes rejected;
* bounded outputs;
* write_file atomic, with backup + sha256 report + exact-content verification;
* apply_patch with before-hash, expected-text verification and unified diff;
* run_process ONLY via asyncio.create_subprocess_exec (never shell=True);
* §15 default-deny command list;
* run_tests only from user-configured or manifest-detected commands;
* rollback checkpoints (create / restore workspace snapshots).
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import re
import signal
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MAX_READ_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16 * 1024
MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_FILE_BYTES = 1024 * 1024
DEFAULT_PROCESS_TIMEOUT = 30
MAX_PROCESS_TIMEOUT = 300

SKIP_DIRS = {".git", ".cortex", "__pycache__", "node_modules"}

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

SHELL_INTERPRETERS = frozenset({"sh", "bash", "zsh", "dash", "fish", "ksh"})
DELETION_PROGRAMS = frozenset({"rm", "rmdir", "unlink", "find"})
NETWORK_CLIENTS = frozenset({"curl", "wget", "ssh", "scp", "sftp", "nc", "ncat"})
APPROVED_EXECUTABLES = frozenset({"python", "python3", "node", "npm", "pytest", "git", "curl"})
SAFE_GIT_SUBCOMMANDS = frozenset({"status", "diff", "log", "show", "rev-parse", "branch", "ls-files"})

SHELL_METACHARS = ("&&", "||", ";", "|", "`", "$(", ">", "<")


@dataclass(frozen=True)
class ProcessCapabilities:
    """Capabilities granted to a reviewed structured process invocation."""

    allowed: bool = False
    allow_network: bool = False
    allow_deletions: bool = False


class ToolError(Exception):
    """Tool execution failed. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ToolDenied(ToolError):
    """Policy/safety denial — the action must not be attempted."""


# ---------------------------------------------------------------------------
# Path confinement
# ---------------------------------------------------------------------------

def resolve_in_workspace(workspace: Path, rel: str, *, must_exist: bool = False) -> Path:
    """Resolve a workspace-relative path, rejecting escapes and symlink escapes."""
    if not isinstance(rel, str) or not rel.strip():
        raise ToolDenied("MALFORMED_PATH", "path must be a non-empty string")
    if rel.startswith("~") or os.path.isabs(rel) or re.match(r"^[A-Za-z]:[\\/]", rel):
        raise ToolDenied("ABSOLUTE_PATH", f"absolute paths are not allowed: {rel!r}")
    parts = re.split(r"[\\/]+", rel)
    if any(p == ".." for p in parts):
        raise ToolDenied("PATH_TRAVERSAL", f"parent traversal is not allowed: {rel!r}")
    if "\x00" in rel:
        raise ToolDenied("MALFORMED_PATH", "path contains NUL")

    root = workspace.resolve()
    candidate = root / rel
    # Resolve as much of the chain as exists; non-existent tails are safe
    # as long as every existing ancestor resolves inside the workspace.
    resolved = Path(os.path.realpath(candidate))
    if resolved != root and root not in resolved.parents:
        raise ToolDenied(
            "SYMLINK_ESCAPE" if candidate.exists() or candidate.is_symlink() else "PATH_ESCAPE",
            f"path resolves outside the workspace: {rel!r}",
        )
    if must_exist and not resolved.exists():
        raise ToolError("NOT_FOUND", f"no such file or directory: {rel!r}")
    return resolved


def _bounded(text: str, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…[truncated at {limit} chars]", True


# ---------------------------------------------------------------------------
# §15 reviewed structured process policy
# ---------------------------------------------------------------------------

def sanitized_process_environment(workspace: Path) -> dict[str, str]:
    """Return a non-secret environment for child processes."""
    return {
        "PATH": os.defpath,
        "HOME": str(workspace.resolve()),
        "TMPDIR": "/tmp",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def check_command_allowed(argv: list[str], workspace: Path) -> None:
    """Allow only reviewed executable and subcommand vectors."""
    if not argv or not all(isinstance(a, str) and a for a in argv):
        raise ToolDenied("MALFORMED_COMMAND", "argv must be a non-empty list of strings")
    program = Path(argv[0]).name
    args = argv[1:]

    if program in SHELL_INTERPRETERS:
        raise ToolDenied("DENIED_COMMAND", f"shell interpreter {program} is denied")
    if program in DELETION_PROGRAMS:
        raise ToolDenied("DENIED_COMMAND", f"deletion-capable program {program} is denied")
    if program not in APPROVED_EXECUTABLES:
        raise ToolDenied("DENIED_COMMAND", f"executable {program} is not approved")

    for a in args:
        for meta in SHELL_METACHARS:
            if meta in a:
                raise ToolDenied(
                    "SHELL_OPERATORS",
                    f"shell operator {meta!r} is not allowed inside arguments",
                )

    if program == "git":
        if not args or args[0] not in SAFE_GIT_SUBCOMMANDS:
            raise ToolDenied("DENIED_COMMAND", "git subcommand is not approved")
        return
    if program in {"python", "python3"}:
        if args[:1] == ["-m"] and args[1:2] == ["unittest"]:
            return
        if not args or args[0].startswith("-"):
            raise ToolDenied("DENIED_COMMAND", "inline or option-based Python execution is denied")
        resolve_in_workspace(workspace, args[0], must_exist=True)
        return
    if program == "node":
        if not args or args[0].startswith("-"):
            raise ToolDenied("DENIED_COMMAND", "inline or option-based Node execution is denied")
        resolve_in_workspace(workspace, args[0], must_exist=True)
        return
    if program == "npm":
        if args not in (["test"], ["run", "test"]):
            raise ToolDenied("DENIED_COMMAND", "only npm test is approved")
        return
    if program == "pytest":
        return
    if program in NETWORK_CLIENTS:
        if any(a in {"-X", "--request", "--data", "-d", "--form", "-F"} for a in args):
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", "only loopback health-check GET requests are approved")
        urls = [a for a in args if a.startswith(("http://", "https://"))]
        if len(urls) != 1:
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", "a single loopback health-check URL is required")
        host = (urlparse(urls[0]).hostname or "").lower()
        if host not in LOOPBACK_HOSTS:
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", f"network destination is not loopback: {host}")


# ---------------------------------------------------------------------------
# Test-command detection for run_tests (§15: configured or manifest-detected)
# ---------------------------------------------------------------------------

def detect_test_command(workspace: Path) -> list[str] | None:
    """Detect a test command from trusted manifests. None if undetectable."""
    package_json = workspace / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            test = (data.get("scripts") or {}).get("test")
            if isinstance(test, str) and test.strip():
                return ["npm", "test"]
        except (json.JSONDecodeError, OSError):
            pass
    if (workspace / "tests").is_dir() or any(workspace.glob("test_*.py")):
        return ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
    return None


# ---------------------------------------------------------------------------
# Checkpoints (§21 tests 19-20): workspace snapshot + restore
# ---------------------------------------------------------------------------

class CheckpointManager:
    """Rollback checkpoints: snapshot and restore workspace files."""

    def __init__(self, workspace: Path, root: Path | None = None):
        self.workspace = workspace.resolve()
        self.root = (root or self.workspace / ".cortex" / "checkpoints").resolve()

    def _iter_files(self):
        for dirpath, dirnames, filenames in os.walk(self.workspace):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                full = Path(dirpath) / name
                if full.is_symlink():
                    continue
                yield full.relative_to(self.workspace)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def create_checkpoint(self, label: str | None = None) -> dict:
        """Snapshot every workspace file (content + sha256 manifest)."""
        label = label or time.strftime("checkpoint-%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        if not re.match(r"^[A-Za-z0-9._-]+$", label):
            raise ToolError("MALFORMED_ARGUMENTS", f"invalid checkpoint label {label!r}")
        dest = self.root / label
        if dest.exists():
            raise ToolError("CHECKPOINT_EXISTS", f"checkpoint {label!r} already exists")
        manifest: dict[str, str] = {}
        dest.mkdir(parents=True)
        try:
            for rel in self._iter_files():
                src = self.workspace / rel
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                manifest[str(rel)] = self._sha256(src)
            (dest / ".manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
        return {"label": label, "files": len(manifest), "manifest": manifest}

    def restore_checkpoint(self, label: str) -> dict:
        """Restore a checkpoint: overwrite changed files, delete files added
        after the checkpoint, recreate files deleted since."""
        src = self.root / label
        manifest_path = src / ".manifest.json"
        if not manifest_path.is_file():
            raise ToolError("CHECKPOINT_NOT_FOUND", f"no checkpoint {label!r}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        restored, deleted = [], []
        for rel in self._iter_files():
            if str(rel) not in manifest:
                (self.workspace / rel).unlink()
                deleted.append(str(rel))
        for rel_str in manifest:
            rel = Path(rel_str)
            source = src / rel
            target = self.workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or self._sha256(target) != manifest[rel_str]:
                shutil.copy2(source, target)
                restored.append(rel_str)
        return {"label": label, "restored": sorted(restored), "deleted": sorted(deleted)}


# ---------------------------------------------------------------------------
# The 11 tools
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes cortex.v1 tools against one authorized workspace."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        test_commands: list[list[str]] | None = None,
        checkpoint_root: str | Path | None = None,
    ):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ToolError("NO_WORKSPACE", f"workspace does not exist: {workspace}")
        self.test_commands = list(test_commands or [])
        self.checkpoints = CheckpointManager(
            self.workspace, Path(checkpoint_root) if checkpoint_root else None
        )

    def _resolve(self, rel: str, *, must_exist: bool = False) -> Path:
        return resolve_in_workspace(self.workspace, rel, must_exist=must_exist)

    # -- read-only tools --------------------------------------------------------

    async def list_directory(self, path: str = ".", maxEntries: int = MAX_LIST_ENTRIES) -> dict:
        target = self._resolve(path, must_exist=True)
        if not target.is_dir():
            raise ToolError("NOT_A_DIRECTORY", f"not a directory: {path}")
        entries = []
        truncated = False
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            if len(entries) >= maxEntries:
                truncated = True
                break
            try:
                st = child.lstat()
                kind = "symlink" if child.is_symlink() else ("directory" if child.is_dir() else "file")
                entries.append({"name": child.name, "type": kind, "size": st.st_size})
            except OSError:
                continue
        return {"path": path, "entries": entries, "truncated": truncated}

    async def read_file(self, path: str, maxBytes: int = MAX_READ_BYTES) -> dict:
        target = self._resolve(path, must_exist=True)
        if not target.is_file():
            raise ToolError("NOT_A_FILE", f"not a file: {path}")
        size = target.stat().st_size
        with open(target, "rb") as fh:
            raw = fh.read(min(maxBytes, MAX_READ_BYTES) + 1)
        if b"\x00" in raw[:8192]:
            raise ToolDenied("BINARY_FILE", f"binary files are rejected by default: {path}")
        truncated = len(raw) > maxBytes
        raw = raw[:maxBytes]
        content = raw.decode("utf-8", errors="replace")
        return {
            "path": path,
            "content": content,
            "size": size,
            "truncated": truncated,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    async def file_exists(self, path: str) -> dict:
        try:
            target = self._resolve(path)
        except ToolDenied:
            raise
        return {"path": path, "exists": target.exists()}

    async def search_text(
        self,
        pattern: str,
        path: str = ".",
        isRegex: bool = False,
        maxResults: int = MAX_SEARCH_RESULTS,
    ) -> dict:
        if not pattern:
            raise ToolError("MALFORMED_ARGUMENTS", "pattern must be non-empty")
        if isRegex:
            try:
                rx = re.compile(pattern)
            except re.error as exc:
                raise ToolError("MALFORMED_ARGUMENTS", f"invalid regex: {exc}") from exc
            match = lambda line: bool(rx.search(line))  # noqa: E731
        else:
            match = lambda line: pattern in line  # noqa: E731
        root = self._resolve(path, must_exist=True)
        results = []
        truncated = False
        if root.is_file():
            files = [root]
        elif root == self.workspace:
            files = [self.workspace / rel for rel in self.checkpoints._iter_files()]
        else:
            files = sorted(
                p
                for p in root.rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
            )
        for file_path in files:
            try:
                if file_path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if match(line):
                    results.append(
                        {
                            "path": str(file_path.relative_to(self.workspace)),
                            "line": lineno,
                            "text": line[:500],
                        }
                    )
                    if len(results) >= maxResults:
                        truncated = True
                        break
            if truncated:
                break
        return {"pattern": pattern, "matches": results, "truncated": truncated}

    async def git_status(self) -> dict:
        return await self._run_git(["status", "--porcelain"])

    async def git_diff(self, path: str | None = None) -> dict:
        argv = ["diff"]
        if path is not None:
            self._resolve(path)
            argv += ["--", path]
        return await self._run_git(argv)

    async def _run_git(self, git_args: list[str]) -> dict:
        argv = ["git", *git_args]
        check_command_allowed(argv, self.workspace)
        if not (self.workspace / ".git").exists():
            raise ToolError("NOT_A_GIT_REPO", "workspace is not a git repository")
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.workspace),
            env=sanitized_process_environment(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ToolError("TIMEOUT", "git command timed out")
        stdout, _ = _bounded(out.decode("utf-8", errors="replace"))
        stderr, _ = _bounded(err.decode("utf-8", errors="replace"))
        return {"exitCode": proc.returncode, "stdout": stdout, "stderr": stderr}

    # -- write tools --------------------------------------------------------------

    def _backup_existing(self, rel: str, target: Path) -> str | None:
        """Back up an existing file before mutation; returns backup path."""
        if not target.exists():
            return None
        backup_dir = self.workspace / ".cortex" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 100000:05d}"
        backup = backup_dir / f"{stamp}_{rel.replace('/', '__')}"
        shutil.copy2(target, backup)
        return str(backup.relative_to(self.workspace))

    async def write_file(self, path: str, content: str) -> dict:
        if not isinstance(content, str):
            raise ToolError("MALFORMED_ARGUMENTS", "content must be text")
        target = self._resolve(path)
        if target.exists() and target.is_symlink():
            raise ToolDenied("SYMLINK_ESCAPE", f"refusing to write through symlink: {path}")
        if target.exists() and not target.is_file():
            raise ToolError("NOT_A_FILE", f"cannot overwrite non-file: {path}")
        if not target.parent.exists():
            raise ToolError(
                "MISSING_DIRECTORY",
                f"parent directory does not exist; use create_directory first: {path}",
            )
        backup = self._backup_existing(path, target)
        data = content.encode("utf-8")
        tmp = target.parent / f".{target.name}.cortex-tmp-{os.getpid()}"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)  # atomic
        finally:
            tmp.unlink(missing_ok=True)
        # Verify exact contents after the write.
        actual = target.read_bytes()
        if actual != data:
            raise ToolError("VERIFY_FAILED", f"written content mismatch for {path}")
        return {
            "path": path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "backup": backup,
            "filesChanged": [path],
        }

    async def apply_patch(self, path: str, replacements: list[dict]) -> dict:
        target = self._resolve(path, must_exist=True)
        if target.is_symlink():
            raise ToolDenied("SYMLINK_ESCAPE", f"refusing to patch through symlink: {path}")
        if not target.is_file():
            raise ToolError("NOT_A_FILE", f"not a file: {path}")
        raw = target.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ToolDenied("BINARY_FILE", f"binary files are rejected by default: {path}")
        before = raw.decode("utf-8")
        before_hash = hashlib.sha256(raw).hexdigest()

        after = before
        applied = []
        for rep in replacements:
            old, new = rep["old"], rep["new"]
            count = after.count(old)
            if count == 0:
                raise ToolError(
                    "EXPECTED_TEXT_MISMATCH",
                    f"expected text not found in {path}: {old[:80]!r}",
                )
            after = after.replace(old, new)
            applied.append({"old": old, "new": new, "occurrences": count})

        backup = self._backup_existing(path, target)
        data = after.encode("utf-8")
        tmp = target.parent / f".{target.name}.cortex-tmp-{os.getpid()}"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        if target.read_bytes() != data:
            raise ToolError("VERIFY_FAILED", f"patched content mismatch for {path}")

        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        diff, _ = _bounded(diff)
        return {
            "path": path,
            "beforeHash": before_hash,
            "afterHash": hashlib.sha256(data).hexdigest(),
            "replacements": applied,
            "diff": diff,
            "backup": backup,
            "filesChanged": [path],
        }

    async def create_directory(self, path: str) -> dict:
        target = self._resolve(path)
        if target.exists() and not target.is_dir():
            raise ToolError("NOT_A_DIRECTORY", f"a non-directory exists at {path}")
        # Reject creating through a symlinked ancestor that escaped resolution.
        target.mkdir(parents=True, exist_ok=True)
        return {"path": path, "created": True, "filesChanged": [path]}

    # -- process tools ---------------------------------------------------------------

    async def run_process(
        self,
        argv: list[str],
        cwd: str = ".",
        timeoutSeconds: float = DEFAULT_PROCESS_TIMEOUT,
    ) -> dict:
        check_command_allowed(argv, self.workspace)
        timeout = min(max(float(timeoutSeconds), 1.0), MAX_PROCESS_TIMEOUT)
        workdir = self._resolve(cwd, must_exist=True)
        if not workdir.is_dir():
            raise ToolError("NOT_A_DIRECTORY", f"cwd is not a directory: {cwd}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(workdir),
                env=sanitized_process_environment(self.workspace),
                start_new_session=True,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise ToolError("COMMAND_NOT_FOUND", f"no such program: {argv[0]}") from exc
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            timed_out = False
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
            out, err = await proc.communicate()
            timed_out = True
        stdout, out_trunc = _bounded(out.decode("utf-8", errors="replace"))
        stderr, err_trunc = _bounded(err.decode("utf-8", errors="replace"))
        return {
            "argv": argv,
            "exitCode": -1 if timed_out else proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timedOut": timed_out,
            "truncated": out_trunc or err_trunc,
        }

    async def run_tests(self, command: str | None = None, cwd: str = ".", timeoutSeconds: float = 120) -> dict:
        """Run only a user-configured or manifest-detected test command."""
        allowed = list(self.test_commands)
        detected = detect_test_command(self.workspace)
        if detected is not None:
            allowed.append(detected)
        if not allowed:
            raise ToolDenied(
                "NO_TEST_COMMAND",
                "no configured test command and none detectable from manifests",
            )
        if command is None:
            argv = allowed[0]
        else:
            import shlex

            try:
                requested = shlex.split(command)
            except ValueError as exc:
                raise ToolError("MALFORMED_ARGUMENTS", f"cannot parse command: {exc}") from exc
            if requested not in allowed:
                raise ToolDenied(
                    "UNCONFIGURED_TEST_COMMAND",
                    f"test command is not configured or manifest-detected: {command!r}",
                )
            argv = requested
        return await self.run_process(argv, cwd=cwd, timeoutSeconds=timeoutSeconds)


# ---------------------------------------------------------------------------
# Result validation helper (§7.5 core: reject false success)
# ---------------------------------------------------------------------------

def validate_write_result(
    workspace: str | Path, path: str, expected_content: str
) -> dict:
    """Deterministic check that a file on disk has exactly the expected content.

    Used to reject model-declared success when the real result differs.
    """
    target = resolve_in_workspace(Path(workspace), path, must_exist=True)
    actual = target.read_text(encoding="utf-8")
    passed = actual == expected_content
    return {
        "name": "exact_content",
        "passed": passed,
        "evidence": (
            f"{path} content matches exactly"
            if passed
            else f"{path} content differs from expected (actual {len(actual)} chars,"
            f" expected {len(expected_content)} chars)"
        ),
    }
