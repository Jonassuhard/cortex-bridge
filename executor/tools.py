"""Structured local tools for the Cortex Bridge executor (mission spec §15).

Implements the 11 cortex.v1 tools directly in Python. No free-form shell:

* relative paths only, resolved under an authorized workspace;
* symlink escapes rejected;
* bounded outputs;
* write_file atomic, with backup + sha256 report + exact-content verification;
* apply_patch with before-hash, expected-text verification and unified diff;
* run_process via native owned-process supervision for descriptor workspaces;
  legacy path workspaces retain asyncio.create_subprocess_exec (never shell=True);
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
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from .workspace_handle import WorkspaceHandle
from . import fd_ops

MAX_READ_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16 * 1024
MAX_LIST_ENTRIES = 500
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_FILE_BYTES = 1024 * 1024
DEFAULT_PROCESS_TIMEOUT = 30
MAX_PROCESS_TIMEOUT = 300
_OMITTED = object()

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


def _check_command_path(workspace, relative, *, must_exist=False, cwd="."):
    if not isinstance(workspace, WorkspaceHandle):
        base = resolve_in_workspace(workspace, cwd, must_exist=True)
        resolve_in_workspace(base, relative, must_exist=must_exist)
        return
    workspace.revalidate()
    root = workspace.duplicate_workspace_fd()
    try:
        try:
            relative = "/".join(fd_ops.components(cwd) + fd_ops.components(relative)) or "."
            if must_exist:
                descriptor = fd_ops.open_regular_at(root, relative)
                os.close(descriptor)
            else:
                fd_ops.components(relative)
                try:
                    with fd_ops.open_parent(root, relative) as (parent, leaf):
                        details = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                        if stat.S_ISLNK(details.st_mode) or details.st_dev != os.fstat(root).st_dev:
                            raise ToolDenied("UNSAFE_COMMAND_PATH", "Command path is not admitted")
                except FileNotFoundError:
                    pass  # git diff may refer to a deleted file
        except (OSError, ValueError, TypeError) as error:
            raise ToolDenied("UNSAFE_COMMAND_PATH", "Command path is not admitted") from error
        workspace.revalidate()
    finally:
        os.close(root)


def check_command_allowed(argv: list[str], workspace: Path | WorkspaceHandle, *, cwd=".") -> None:
    """Allow only reviewed executable and subcommand vectors."""
    if not argv or not all(isinstance(a, str) and a for a in argv):
        raise ToolDenied("MALFORMED_COMMAND", "argv must be a non-empty list of strings")
    executable = argv[0]
    if os.path.isabs(executable) or "/" in executable or "\\" in executable:
        raise ToolDenied("DENIED_COMMAND", "executable must be resolved through the fixed PATH")
    program = executable
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
        subcommand, options = args[0], args[1:]
        if subcommand == "status" and any(option != "--porcelain" for option in options):
            raise ToolDenied("DENIED_COMMAND", "git status option is not approved")
        if subcommand == "diff":
            try:
                separator = options.index("--")
                flags, paths = options[:separator], options[separator + 1:]
            except ValueError:
                flags, paths = options, []
            if flags:
                raise ToolDenied("DENIED_COMMAND", "git diff option is not approved")
            for path in paths:
                _check_command_path(workspace, path, cwd=cwd)
        if subcommand in {"log", "show", "rev-parse", "branch", "ls-files"} and options:
            raise ToolDenied("DENIED_COMMAND", f"git {subcommand} option is not approved")
        return
    if program in {"python", "python3"}:
        if args[:1] == ["-m"] and args[1:2] == ["unittest"]:
            return
        if not args or args[0].startswith("-"):
            raise ToolDenied("DENIED_COMMAND", "inline or option-based Python execution is denied")
        _check_command_path(workspace, args[0], must_exist=True, cwd=cwd)
        return
    if program == "node":
        if not args or args[0].startswith("-"):
            raise ToolDenied("DENIED_COMMAND", "inline or option-based Node execution is denied")
        _check_command_path(workspace, args[0], must_exist=True, cwd=cwd)
        return
    if program == "npm":
        if args not in (["test"], ["run", "test"]):
            raise ToolDenied("DENIED_COMMAND", "only npm test is approved")
        return
    if program == "pytest":
        return
    if program in NETWORK_CLIENTS:
        safe_flags = {"--fail", "--silent", "--show-error", "-f", "-s", "-S"}
        value_flags = {"--max-time", "--connect-timeout"}
        urls = []
        index = 0
        while index < len(args):
            argument = args[index]
            if argument in safe_flags:
                index += 1
                continue
            if argument in value_flags:
                if index + 1 >= len(args) or not args[index + 1].isdigit():
                    raise ToolDenied("EXTERNAL_SIDE_EFFECT", "curl timeout option requires an integer")
                index += 2
                continue
            if argument.startswith(("http://", "https://")):
                urls.append(argument)
                index += 1
                continue
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", "curl option is not approved for health checks")
        if len(urls) != 1:
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", "a single loopback health-check URL is required")
        host = (urlparse(urls[0]).hostname or "").lower()
        if host not in LOOPBACK_HOSTS:
            raise ToolDenied("EXTERNAL_SIDE_EFFECT", f"network destination is not loopback: {host}")


# ---------------------------------------------------------------------------
# Test-command detection for run_tests (§15: configured or manifest-detected)
# ---------------------------------------------------------------------------

def detect_test_command(workspace: Path, *, cwd=".") -> list[str] | None:
    """Detect a test command from trusted manifests. None if undetectable."""
    if isinstance(workspace, WorkspaceHandle):
        try:
            prefix = "/".join(fd_ops.components(cwd))
        except (ValueError, TypeError) as error:
            raise ToolDenied("UNSAFE_COMMAND_PATH", "Test directory is not admitted") from error
        package_path = f"{prefix}/package.json" if prefix else "package.json"
        executor = ToolExecutor(workspace)
        if executor._file_exists_at_handle(package_path)["exists"]:
            manifest = executor._read_file_at_handle(package_path, MAX_READ_BYTES)
            if manifest["truncated"]:
                raise ToolDenied("TEST_MANIFEST_TOO_LARGE", "Test manifest exceeds the inspection limit")
            try:
                data = json.loads(manifest["content"])
            except json.JSONDecodeError:
                data = None
            scripts = data.get("scripts") if isinstance(data, dict) else None
            test = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(test, str) and test.strip():
                return ["npm", "test"]
        listing = executor._list_directory_at_handle(cwd, MAX_LIST_ENTRIES)
        if listing["truncated"]:
            raise ToolDenied("TEST_DISCOVERY_INCOMPLETE", "Root listing exceeds the inspection limit")
        for entry in listing["entries"]:
            if entry["name"] == "tests" and entry["type"] == "directory":
                return ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
        for entry in listing["entries"]:
            if entry["type"] == "file" and entry["name"].startswith("test_") and entry["name"].endswith(".py"):
                _check_command_path(workspace, entry["name"], must_exist=True, cwd=cwd)
                return ["python3", "-m", "unittest", "discover", "-s", ".", "-v"]
        return None
    workspace = resolve_in_workspace(workspace, cwd, must_exist=True)
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
        workspace: str | Path | WorkspaceHandle,
        *,
        test_commands: list[list[str]] | None = None,
        checkpoint_root: str | Path | None = None,
        effect_gate=None,
        process_helper=None,
    ):
        self.effect_gate = effect_gate
        self.process_helper = process_helper
        self._owned_processes = {}
        self._workspace_handle = workspace if isinstance(workspace, WorkspaceHandle) else None
        if self._workspace_handle is not None:
            if checkpoint_root is not None:
                raise ToolDenied("PATH_CHECKPOINT_FORBIDDEN", "Descriptor workspaces cannot use a path-based checkpoint root")
            workspace.revalidate()
            self.workspace = workspace
            self.test_commands = list(test_commands or [])
            self.checkpoints = None  # Descriptor checkpoint implementation pending.
            return
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ToolError("NO_WORKSPACE", f"workspace does not exist: {workspace}")
        self.test_commands = list(test_commands or [])
        self.checkpoints = CheckpointManager(
            self.workspace, Path(checkpoint_root) if checkpoint_root else None
        )

    def _resolve(self, rel: str, *, must_exist: bool = False) -> Path:
        if self._workspace_handle is not None:
            raise ToolDenied("DESCRIPTOR_TOOL_REQUIRED", "This tool has not been converted to descriptor access")
        return resolve_in_workspace(self.workspace, rel, must_exist=must_exist)

    @property
    def supports_durable_effects(self) -> bool:
        return self._workspace_handle is not None and self.effect_gate is not None

    # -- read-only tools --------------------------------------------------------

    async def list_directory(self, path: str = ".", maxEntries: int = MAX_LIST_ENTRIES) -> dict:
        if self._workspace_handle is not None:
            return self._list_directory_at_handle(path, maxEntries)
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

    def _list_directory_at_handle(self, path: str, max_entries: int) -> dict:
        if type(max_entries) is not int or max_entries < 1:
            raise ToolDenied("INVALID_LIST_LIMIT", "Listing limit must be a positive integer")
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        try:
            try:
                directory = fd_ops.open_directory_at(root, path)
                try:
                    names = sorted(os.listdir(directory))
                    limit = min(max_entries, MAX_LIST_ENTRIES)
                    entries = []
                    for name in names[:limit]:
                        details = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        kind = "symlink" if stat.S_ISLNK(details.st_mode) else ("directory" if stat.S_ISDIR(details.st_mode) else "file")
                        entries.append({"name": name, "type": kind, "size": details.st_size})
                finally:
                    os.close(directory)
            except (OSError, ValueError, TypeError) as error:
                raise ToolDenied("UNSAFE_LIST_TARGET", "Cannot list requested directory") from error
            handle.revalidate()
            return {"path": path, "entries": entries, "truncated": len(names) > limit}
        finally:
            os.close(root)

    async def read_file(self, path: str, maxBytes: int = MAX_READ_BYTES) -> dict:
        if self._workspace_handle is not None:
            return self._read_file_at_handle(path, maxBytes)
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

    def _read_file_at_handle(self, path: str, max_bytes: int) -> dict:
        if type(max_bytes) is not int or max_bytes < 1:
            raise ToolDenied("INVALID_READ_LIMIT", "Read limit must be a positive integer")
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        try:
            try:
                descriptor = fd_ops.open_regular_at(root, path)
            except (OSError, ValueError, TypeError) as error:
                raise ToolDenied("UNSAFE_READ_TARGET", "Cannot admit requested regular file") from error
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                limit = min(max_bytes, MAX_READ_BYTES)
                raw = stream.read(limit + 1)
                after = os.fstat(stream.fileno())
                fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
                if any(getattr(before, key) != getattr(after, key) for key in fields):
                    raise ToolDenied("READ_TARGET_CHANGED", "File changed while reading")
            handle.revalidate()
            if b"\x00" in raw[:8192]:
                raise ToolDenied("BINARY_FILE", "Binary files are rejected by default")
            truncated = len(raw) > limit
            raw = raw[:limit]
            return {"path": path, "content": raw.decode("utf-8", errors="replace"),
                    "size": before.st_size, "truncated": truncated,
                    "sha256": hashlib.sha256(raw).hexdigest()}
        finally:
            os.close(root)

    async def file_exists(self, path: str) -> dict:
        if self._workspace_handle is not None:
            return self._file_exists_at_handle(path)
        try:
            target = self._resolve(path)
        except ToolDenied:
            raise
        return {"path": path, "exists": target.exists()}

    def _file_exists_at_handle(self, path: str) -> dict:
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        try:
            try:
                if path == ".":
                    details = os.fstat(root)
                else:
                    with fd_ops.open_parent(root, path) as (parent, leaf):
                        details = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                if stat.S_ISLNK(details.st_mode) or details.st_dev != os.fstat(root).st_dev:
                    raise ToolDenied("UNSAFE_EXISTENCE_TARGET", "Target is a link or on another device")
                exists = True
            except FileNotFoundError:
                exists = False
            except (OSError, ValueError, TypeError) as error:
                raise ToolDenied("UNSAFE_EXISTENCE_TARGET", "Cannot inspect requested target") from error
            handle.revalidate()
            return {"path": path, "exists": exists}
        finally:
            os.close(root)

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
        if self._workspace_handle is not None:
            return self._search_at_handle(pattern, path, match, maxResults)
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

    def _search_at_handle(self, pattern, path, match, max_results):
        if type(max_results) is not int or max_results < 1:
            raise ToolDenied("INVALID_SEARCH_LIMIT", "Search limit must be a positive integer")
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        stack = []
        seen = set()
        results = []
        limit = min(max_results, MAX_SEARCH_RESULTS)
        truncated = False

        def scan_file(descriptor, relative):
            nonlocal truncated
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if before.st_size > MAX_SEARCH_FILE_BYTES:
                    truncated = True
                    return
                raw = stream.read(MAX_SEARCH_FILE_BYTES + 1)
                after = os.fstat(stream.fileno())
                if any(getattr(before, key) != getattr(after, key) for key in
                       ("st_dev", "st_ino", "st_size", "st_mode", "st_nlink", "st_mtime_ns", "st_ctime_ns")):
                    raise ToolDenied("SEARCH_TARGET_CHANGED", "File changed during search")
            if len(raw) > MAX_SEARCH_FILE_BYTES:
                truncated = True
                return
            if b"\x00" in raw[:8192]:
                return
            for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
                if match(line):
                    results.append({"path": relative, "line": number, "text": line[:500]})
                    if len(results) >= limit:
                        truncated = True
                        return

        def push(descriptor, relative):
            try:
                details = os.fstat(descriptor)
                identity = (details.st_dev, details.st_ino)
                if identity in seen or len(stack) >= 64:
                    raise ToolDenied("SEARCH_TRAVERSAL_LIMIT", "Repeated directory or excessive search depth")
                names = iter(sorted(os.listdir(descriptor)))
                seen.add(identity)
                stack.append((descriptor, relative, names))
            except BaseException:
                os.close(descriptor)
                raise

        try:
            try:
                try:
                    directory = fd_ops.open_directory_at(root, path)
                except NotADirectoryError:
                    scan_file(fd_ops.open_regular_at(root, path), path)
                else:
                    push(directory, "" if path == "." else path)
                while stack and len(results) < limit:
                    parent, relative, names = stack[-1]
                    name = next(names, None)
                    if name is None:
                        stack.pop()
                        os.close(parent)
                        continue
                    details = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    child_relative = f"{relative}/{name}" if relative else name
                    if stat.S_ISDIR(details.st_mode):
                        if name not in SKIP_DIRS:
                            push(fd_ops.open_directory_at(parent, name), child_relative)
                    elif stat.S_ISREG(details.st_mode) and details.st_nlink == 1:
                        scan_file(fd_ops.open_regular_at(parent, name), child_relative)
            except (OSError, ValueError, TypeError) as error:
                raise ToolDenied("UNSAFE_SEARCH_TARGET", "Search target could not be verified") from error
            handle.revalidate()
            return {"pattern": pattern, "matches": results, "truncated": truncated}
        finally:
            for descriptor, _, _ in reversed(stack):
                os.close(descriptor)
            os.close(root)

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

    async def write_file(self, path: str, content: str, *, activation=None) -> dict:
        if self._workspace_handle is not None:
            return self._write_file_at_handle(path, content, activation)
        if activation is not None:
            raise ToolDenied("WORKSPACE_HANDLE_REQUIRED", "Activated mutations require a retained workspace")
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

    async def create_directory(self, path: str, *, activation=None) -> dict:
        if self._workspace_handle is not None:
            return self._create_directory_at_handle(path, activation)
        if activation is not None:
            raise ToolDenied("WORKSPACE_HANDLE_REQUIRED", "Activated mutations require a retained workspace")
        target = self._resolve(path)
        if target.exists() and not target.is_dir():
            raise ToolError("NOT_A_DIRECTORY", f"a non-directory exists at {path}")
        # Reject creating through a symlinked ancestor that escaped resolution.
        target.mkdir(parents=True, exist_ok=True)
        return {"path": path, "created": True, "filesChanged": [path]}

    def _write_file_at_handle(self, path, content, activation):
        from effect_gate import canonical_digest
        if type(content) is not str:
            raise ToolDenied("MALFORMED_ARGUMENTS", "Content must be text")
        try:
            if not fd_ops.components(path):
                raise ValueError()
        except (ValueError, TypeError) as error:
            raise ToolDenied("MALFORMED_PATH", "Expected relative file path") from error
        gate = self.effect_gate
        if gate is None or activation is None:
            raise ToolDenied("EFFECT_CAPABILITY_REQUIRED", "File writes require durable activation")
        expected = canonical_digest("write_file", {"path": path, "content": content})
        gate.assert_activation(activation, owner_kind="mission", category="filesystem", operation="write_file")
        if activation.payload_digest != expected:
            raise ToolDenied("EFFECT_PAYLOAD_MISMATCH", "Write arguments differ from authorized action")
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        temporary = f".cortex-{activation.effect_id}.tmp"
        backup = f".cortex-{activation.effect_id}.previous"
        touched = False
        data = content.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()

        def snapshot(parent, name):
            descriptor = fd_ops.open_regular_at(parent, name)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                hasher = hashlib.sha256()
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
                after = os.fstat(stream.fileno())
                fields = ("st_dev", "st_ino", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
                if any(getattr(before, key) != getattr(after, key) for key in fields):
                    raise ToolDenied("WRITE_TARGET_CHANGED", "File changed during inspection")
                return {"device": before.st_dev, "inode": before.st_ino, "size": before.st_size, "sha256": hasher.hexdigest()}
        try:
            with fd_ops.open_parent(root, path) as (parent, leaf):
                try:
                    prior = snapshot(parent, leaf)
                except FileNotFoundError:
                    prior = None
                parent_stat = os.fstat(parent)
                gate.record_ownership(activation, {"path": path, "temporary": temporary,
                    "previous": backup if prior else None, "prior": prior, "expectedSha256": digest,
                    "parentDevice": parent_stat.st_dev, "parentInode": parent_stat.st_ino})
                handle.revalidate()
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o600, dir_fd=parent)
                touched = True
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                    prepared_inode = os.fstat(stream.fileno()).st_ino
                fd_ops.fsync_directory(parent)
                prepared = snapshot(parent, temporary)
                if (prepared["inode"] != prepared_inode or prepared["size"] != len(data)
                        or prepared["sha256"] != digest):
                    raise ToolDenied("WRITE_PREPARED_CHANGED", "Prepared file changed before publication")
                gate.record_prepared_file(activation, prepared)
                handle.revalidate()
                if prior is not None:
                    if snapshot(parent, leaf) != prior:
                        raise ToolDenied("WRITE_TARGET_CHANGED", "Original file changed before publication")
                    fd_ops.rename_exchange_at(parent, temporary, parent, leaf)
                    fd_ops.fsync_directory(parent)
                    if snapshot(parent, temporary) != prior:
                        raise ToolDenied("WRITE_TARGET_CHANGED", "Previous file identity could not be confirmed")
                    fd_ops.rename_exclusive_at(parent, temporary, parent, backup)
                else:
                    fd_ops.rename_exclusive_at(parent, temporary, parent, leaf)
                fd_ops.fsync_directory(parent)
                actual = snapshot(parent, leaf)
                if actual != prepared:
                    raise ToolError("WRITE_VERIFICATION_FAILED", "Published file differs from prepared content")
                handle.revalidate()
                result = {"path": path, "bytesWritten": len(data), "sha256": digest, "filesChanged": [path]}
                gate.succeed(activation, {**result, "identity": actual, "previous": backup if prior else None})
                return result
        except BaseException as error:
            if touched:
                gate.outcome_unclear(activation, code="WRITE_OUTCOME_UNCLEAR", receipt={"path": path, "temporary": temporary})
            else:
                gate.fail(activation, code="WRITE_FAILED_SAFE", receipt={"path": path})
            if isinstance(error, OSError):
                raise ToolDenied("WRITE_FAILED", "Write could not be completed safely") from error
            raise
        finally:
            os.close(root)

    def _create_directory_at_handle(self, path, activation):
        from effect_gate import canonical_digest
        try:
            if not fd_ops.components(path):
                raise ValueError("Root is not a creation target")
        except (TypeError, ValueError) as error:
            raise ToolDenied("MALFORMED_PATH", "Expected a relative directory path") from error
        gate = self.effect_gate
        if gate is None or activation is None:
            raise ToolDenied("EFFECT_CAPABILITY_REQUIRED", "Directory creation requires durable activation")
        digest = canonical_digest("create_directory", {"path": path})
        gate.assert_activation(activation, owner_kind="mission", category="filesystem", operation="create_directory")
        if activation.payload_digest != digest:
            raise ToolDenied("EFFECT_PAYLOAD_MISMATCH", "Creation arguments differ from the authorized action")
        handle = self._workspace_handle
        handle.revalidate()
        root = handle.duplicate_workspace_fd()
        mutation_attempted = False
        try:
            with fd_ops.open_parent(root, path) as (parent, leaf):
                parent_identity = os.fstat(parent)
                gate.record_ownership(activation, {"path": path, "parentDevice": parent_identity.st_dev,
                                                   "parentInode": parent_identity.st_ino})
                handle.revalidate()
                mutation_attempted = True
                created = fd_ops.create_directory_at(parent, leaf)
                observed = fd_ops.stat_at(parent, leaf)
                if not stat.S_ISDIR(observed.st_mode) or (observed.st_dev, observed.st_ino) != (created.st_dev, created.st_ino):
                    raise ToolError("DIRECTORY_IDENTITY_CHANGED", "Created directory identity could not be confirmed")
                handle.revalidate()
                result = {"path": path, "created": True, "filesChanged": [path]}
                gate.succeed(activation, {**result, "device": created.st_dev, "inode": created.st_ino})
                return result
        except BaseException as error:
            if mutation_attempted and not isinstance(error, FileExistsError):
                gate.outcome_unclear(activation, code="DIRECTORY_OUTCOME_UNCLEAR", receipt={"path": path})
            else:
                gate.fail(activation, code="DIRECTORY_CREATE_FAILED", receipt={"path": path})
            if isinstance(error, OSError):
                raise ToolDenied("DIRECTORY_CREATE_FAILED", "Directory could not be created safely") from error
            raise
        finally:
            os.close(root)

    # -- process tools ---------------------------------------------------------------

    async def run_process(
        self,
        argv: list[str],
        cwd: str = _OMITTED,
        timeoutSeconds: float = _OMITTED,
        *, activation=None,
    ) -> dict:
        arguments = {"argv": argv}
        if cwd is not _OMITTED:
            arguments["cwd"] = cwd
        if timeoutSeconds is not _OMITTED:
            arguments["timeoutSeconds"] = timeoutSeconds
        cwd = "." if cwd is _OMITTED else cwd
        timeoutSeconds = DEFAULT_PROCESS_TIMEOUT if timeoutSeconds is _OMITTED else timeoutSeconds
        if self._workspace_handle is not None:
            return await self._run_process_at_handle(arguments, cwd, timeoutSeconds, activation)
        if activation is not None:
            raise ToolDenied("DESCRIPTOR_TOOL_REQUIRED", "Activated processes require a descriptor workspace")
        check_command_allowed(argv, self.workspace, cwd=cwd)
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

    async def _run_process_at_handle(self, arguments, cwd, timeout, activation, *, operation="run_process", selected_argv=None):
        import math
        from effect_gate import canonical_digest
        from .process_spawn import spawn_owned_process, ProcessReleaseStopped
        gate = self.effect_gate
        if gate is None or activation is None:
            raise ToolDenied("EFFECT_CAPABILITY_REQUIRED", "Processes require durable activation")
        gate.assert_activation(activation, owner_kind="mission", category="process", operation=operation)
        if canonical_digest(operation, arguments) != activation.payload_digest:
            raise ToolDenied("EFFECT_PAYLOAD_MISMATCH", "Process arguments differ from the approved action")
        # Freeze exact input before any await; defaults are used for execution
        # only and are not silently inserted into the authorization payload.
        arguments = json.loads(json.dumps(arguments, ensure_ascii=False, allow_nan=False))
        command = list(selected_argv) if selected_argv is not None else arguments["argv"]
        root = directory = None
        process = None
        spawn_entered = False
        try:
            if not gate.status().accepting_effects:
                raise ProcessReleaseStopped("PROCESS_STOPPED_BEFORE_RELEASE")
            if self.process_helper is None:
                raise ToolDenied("PROCESS_HELPER_REQUIRED", "An attested native helper is required")
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= MAX_PROCESS_TIMEOUT:
                raise ToolDenied("INVALID_PROCESS_TIMEOUT", "Process deadline is outside the supported range")
            check_command_allowed(command, self.workspace, cwd=cwd)
            self._workspace_handle.revalidate()
            root = self._workspace_handle.duplicate_workspace_fd()
            directory = fd_ops.open_directory_at(root, cwd)
            self._workspace_handle.revalidate()
            spawn_entered = True
            process = spawn_owned_process(self.process_helper, gate=gate, activation=activation,
                arguments=arguments, cwd_fd=directory,
                selected_argv=command,
                env={"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
            self._owned_processes[activation.effect_id] = process
            self._workspace_handle.revalidate()
            process.release()
        except Exception as error:
            if process is not None:
                try:
                    process.close()
                except Exception:
                    pass  # Keep the owned handle; never invent successful cleanup.
            if isinstance(error, ProcessReleaseStopped):
                absent = process is None and not spawn_entered
                if process is not None and process._closed and process.returncode == 125:
                    absent = True
                    for probe in (lambda: os.killpg(process.pid, 0), lambda: os.kill(process.pid, 0)):
                        try:
                            probe()
                        except ProcessLookupError:
                            continue
                        except OSError:
                            absent = False
                            break
                        else:
                            absent = False
                            break
                if absent:
                    gate.fail(activation, code="PROCESS_CANCELLED",
                              receipt={"released": False, "quiescenceVerified": True})
                    self._owned_processes.pop(activation.effect_id, None)
                    raise ToolDenied("PROCESS_CANCELLED", "STOP prevented command release") from error
            if spawn_entered:
                gate.outcome_unclear(activation, code="PROCESS_START_UNCLEAR",
                                     receipt={"quiescenceVerified": False})
            else:
                gate.fail(activation, code="PROCESS_PREPARATION_FAILED", receipt={})
            raise
        finally:
            for fd in (directory, root):
                if fd is not None:
                    os.close(fd)
        try:
            receipt = await process.supervise(timeout=timeout, max_bytes=MAX_OUTPUT_CHARS)
            if receipt.state == "outcome_unclear":
                raise ToolError(receipt.error_code, "Process outcome requires reconciliation")
            return {**receipt.result, "argv": command,
                    "timedOut": receipt.error_code == "PROCESS_TIMEOUT",
                    "errorCode": receipt.error_code}
        finally:
            if process._closed:
                self._owned_processes.pop(activation.effect_id, None)

    async def run_tests(self, argv: list[str] | None = _OMITTED, cwd: str = _OMITTED,
                        timeoutSeconds: float = _OMITTED, *, activation=None) -> dict:
        """Run only a user-configured or manifest-detected test command."""
        arguments = {}
        for key, value in (("argv", argv), ("cwd", cwd), ("timeoutSeconds", timeoutSeconds)):
            if value is not _OMITTED:
                arguments[key] = value
        argv = None if argv is _OMITTED else argv
        cwd = "." if cwd is _OMITTED else cwd
        timeoutSeconds = 120 if timeoutSeconds is _OMITTED else timeoutSeconds
        if self._workspace_handle is not None:
            if self.effect_gate is None or activation is None:
                raise ToolDenied("EFFECT_CAPABILITY_REQUIRED", "Tests require durable activation")
            self.effect_gate.assert_activation(activation, owner_kind="mission",
                                              category="process", operation="run_tests")
            from effect_gate import canonical_digest
            if canonical_digest("run_tests", arguments) != activation.payload_digest:
                raise ToolDenied("EFFECT_PAYLOAD_MISMATCH", "Test arguments differ from the approved action")
        elif activation is not None:
            raise ToolDenied("DESCRIPTOR_TOOL_REQUIRED", "Activated tests require a descriptor workspace")
        try:
            selected = self._select_test_command(argv, cwd=cwd)
        except Exception as error:
            if self._workspace_handle is not None:
                self.effect_gate.fail(activation,
                    code=error.code if isinstance(error, ToolError) else "TEST_SELECTION_FAILED",
                    receipt={"processStarted": False})
            raise
        if self._workspace_handle is not None:
            return await self._run_process_at_handle(arguments, cwd, timeoutSeconds, activation,
                                                    operation="run_tests", selected_argv=selected)
        return await self.run_process(selected, cwd=cwd, timeoutSeconds=timeoutSeconds)

    def _select_test_command(self, argv, *, cwd="."):
        allowed = list(self.test_commands)
        detected = detect_test_command(self.workspace, cwd=cwd)
        if detected is not None:
            allowed.append(detected)
        if not allowed:
            raise ToolDenied(
                "NO_TEST_COMMAND",
                "no configured test command and none detectable from manifests",
            )
        if argv is None:
            selected = allowed[0]
        else:
            if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
                raise ToolError("MALFORMED_ARGUMENTS", "argv must be a non-empty list of strings")
            if argv not in allowed:
                raise ToolDenied(
                    "UNCONFIGURED_TEST_COMMAND",
                    f"test command is not configured or manifest-detected: {argv!r}",
                )
            selected = argv
        return selected


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
