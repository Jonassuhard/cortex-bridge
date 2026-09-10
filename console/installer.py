"""Consent-bound install, doctor and uninstall plans."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from cortex_paths import build_paths
from process_ownership import classify, load_record
from version import current_version

ROOT = Path(__file__).resolve().parent.parent
STAGING_NAME = ".install-staging"
TRANSACTION_NAME = "transaction.json"
MACOS_AX_HELPER_NAME = "cortex-macos-ax-send"
MACOS_AX_HELPER_SOURCE = ROOT / "transport" / "macos_ax_send.swift"
RENAME_SWAP = 0x00000002
RENAME_EXCL = 0x00000004
AT_FDCWD = -2


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hashed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "plan_hash": hashlib.sha256(_canonical(payload)).hexdigest()}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while chunk := os.read(fd, 1024 * 1024):
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _opened_path_matches(fd: int, path: Path) -> bool:
    try:
        opened = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(current.st_mode)
        and opened.st_dev == current.st_dev
        and opened.st_ino == current.st_ino
    )


def _renameatx(source: Path, target: Path, flags: int) -> None:
    if sys.platform != "darwin":
        raise OSError("renameatx_np is available only on macOS")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameatx_np = libc.renameatx_np
    except AttributeError as exc:
        raise OSError("renameatx_np is unavailable on this macOS version") from exc
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(target),
        flags,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == getattr(os, "EEXIST", 17):
        raise FileExistsError(error, os.strerror(error), str(target))
    raise OSError(error, os.strerror(error), str(target))


def _rename_exclusive(source: Path, target: Path) -> None:
    _renameatx(source, target, RENAME_EXCL)


def _rename_swap(source: Path, target: Path) -> None:
    _renameatx(source, target, RENAME_SWAP)


def _native_helper_path() -> Path:
    return build_paths().home / "bin" / MACOS_AX_HELPER_NAME


def _staged_native_helper_path() -> Path:
    return build_paths().home / STAGING_NAME / f".{MACOS_AX_HELPER_NAME}.tmp"


def _staged_native_helper_source_path() -> Path:
    return build_paths().home / STAGING_NAME / "macos_ax_send.swift"


def _swiftc_path() -> Path | None:
    raw = os.environ.get("SWIFTC_BIN") or shutil.which("swiftc")
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return None
    resolved = candidate.resolve(strict=False)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    return resolved


def _native_helper_needs_build() -> bool:
    if sys.platform != "darwin":
        return False
    if MACOS_AX_HELPER_SOURCE.is_symlink() or not MACOS_AX_HELPER_SOURCE.is_file():
        raise RuntimeError("macOS native helper source is missing or unsafe")
    helper = _native_helper_path()
    if helper.parent.is_symlink():
        return True
    manifest = _load_owned_manifest() or {}
    metadata = manifest.get("native_helper")
    if not isinstance(metadata, dict):
        return True
    if metadata.get("path") != str(helper):
        return True
    if helper.is_symlink() or not helper.is_file() or not os.access(helper, os.X_OK):
        return True
    try:
        return (
            metadata.get("source_sha256") != _sha256_file(MACOS_AX_HELPER_SOURCE)
            or metadata.get("sha256") != _sha256_file(helper)
        )
    except OSError:
        return True


def _human_pauses() -> list[dict[str, str]]:
    return [
        {"kind": "login", "detail": "ChatGPT login is manual in the user's Chrome tab."},
        {"kind": "terms", "detail": "Only the user may accept third-party terms."},
        {
            "kind": "extension",
            "detail": (
                "Browser extensions require explicit approval and manual installation: "
                "open chrome://extensions and load the repository chrome-extension directory."
            ),
        },
        {"kind": "secrets", "detail": "Secrets are never requested or generated by this installer."},
        {"kind": "privilege", "detail": "sudo and privilege escalation are never executed."},
    ]


def _command(
    command_id: str,
    argv: list[str],
    official_url: str,
    disk_bytes: int,
    rollback: str,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not argv or "sudo" in argv:
        raise ValueError("unsafe installer command")
    command = {
        "id": command_id,
        "argv": argv,
        "official_url": official_url,
        "disk_bytes": disk_bytes,
        "rollback": rollback,
    }
    if environment:
        command["environment"] = environment
    return command


def _owned_manifest_path() -> Path:
    return build_paths().home / "install" / "owned.json"


def _installed() -> bool:
    paths = build_paths()
    return (paths.home / "venv").is_dir() and _owned_manifest_path().is_file()


def build_install_plan(*, rebuild_ui: bool = False, ollama_model: str | None = None) -> dict[str, Any]:
    paths = build_paths()
    staging = paths.home / STAGING_NAME
    python = os.environ.get("PYTHON_BIN") or sys.executable
    commands: list[dict[str, Any]] = []
    human_pauses = _human_pauses()
    if not _installed():
        staged_python = staging / "venv" / "bin" / "python"
        commands.extend([
            _command(
                "create_venv",
                [python, "-m", "venv", str(staging / "venv")],
                "https://docs.python.org/3/library/venv.html",
                50 * 1024 * 1024,
                f"remove owned staging directory {staging}",
            ),
            _command(
                "install_python",
                [str(staged_python), "-m", "pip", "install", "--require-hashes", "-r", str(ROOT / "requirements.lock")],
                "https://pypi.org/",
                250 * 1024 * 1024,
                f"remove owned staging directory {staging}",
            ),
        ])
    if _native_helper_needs_build():
        swiftc = _swiftc_path()
        if swiftc is None:
            human_pauses.append({
                "kind": "file_send_toolchain",
                "detail": (
                    "Text chat can be installed now. File sending remains unavailable until "
                    "the user installs Apple's Command Line Tools and reruns this installer."
                ),
            })
        else:
            source_sha256 = _sha256_file(MACOS_AX_HELPER_SOURCE)
            compile_command = _command(
                "compile_macos_ax_helper",
                [
                    str(swiftc),
                    str(_staged_native_helper_source_path()),
                    "-o",
                    str(_staged_native_helper_path()),
                ],
                "https://developer.apple.com/xcode/resources/",
                5 * 1024 * 1024,
                f"remove the staged helper and preserve the previous {_native_helper_path()}",
            )
            compile_command["source_sha256"] = source_sha256
            commands.append(compile_command)
    if rebuild_ui:
        npm_wrapper = str(ROOT / "scripts" / "npmw")
        commands.extend([
            _command(
                "npm_ci",
                [npm_wrapper, "ci"],
                "https://docs.npmjs.com/cli/v11/commands/npm-ci",
                400 * 1024 * 1024,
                "remove frontend/node_modules if it was created by this approved run",
            ),
            _command(
                "build_ui",
                [npm_wrapper, "run", "build"],
                "https://nextjs.org/docs/app/api-reference/cli/next",
                200 * 1024 * 1024,
                "restore the previous generated frontend artifact",
            ),
        ])
    if ollama_model:
        commands.append(_command(
            "ollama_pull",
            ["ollama", "pull", ollama_model],
            "https://docs.ollama.com/cli",
            12 * 1024 * 1024 * 1024,
            f"remove only the explicitly installed model {ollama_model}",
        ))
    payload = {
        "schema_version": 1,
        "action": "install",
        "version": current_version(),
        "target": str(paths.home),
        "chrome_extension_path": str((ROOT / "chrome-extension").resolve()),
        "commands": commands,
        "disk_bytes": sum(command["disk_bytes"] for command in commands),
        "human_pauses": human_pauses,
        "rollback": "Only the owned staging directory and manifest-listed resources may be removed.",
    }
    return _hashed(payload)


def _run_command(command: dict[str, Any]) -> None:
    runner = os.environ.get("CORTEX_INSTALL_RUNNER")
    if runner:
        argv = [runner, json.dumps(command, sort_keys=True)]
        cwd = ROOT
    else:
        argv = command["argv"]
        cwd = ROOT / "frontend" if command["id"] in {"npm_ci", "build_ui"} else ROOT
    environment = {**os.environ, **command.get("environment", {})}
    subprocess.run(argv, cwd=cwd, env=environment, check=True)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(temporary, flags, 0o600)
    try:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        view = memoryview(encoded)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _copy_approved_helper_source(destination: Path, expected_sha256: str) -> None:
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise RuntimeError("approved native helper source hash is invalid")
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(MACOS_AX_HELPER_SOURCE, source_flags)
    destination_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    destination_fd: int | None = None
    digest = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise RuntimeError("macOS native helper source is not a regular file")
        destination_fd = os.open(destination, destination_flags, 0o400)
        while chunk := os.read(source_fd, 1024 * 1024):
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        os.fsync(destination_fd)
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)
    if digest.hexdigest() != expected_sha256:
        destination.unlink(missing_ok=True)
        raise RuntimeError("native helper source changed after plan approval")
    _fsync_directory(destination.parent)


def _regular_file_hash(path: Path) -> str | None:
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        return None
    try:
        return _sha256_file(path)
    except OSError:
        return None


def _owned_helper_hash_for_replacement(helper: Path) -> str:
    manifest = _load_owned_manifest()
    metadata = (manifest or {}).get("native_helper")
    resources = (manifest or {}).get("resources")
    if (
        not isinstance(metadata, dict)
        or metadata.get("path") != str(helper)
        or not isinstance(resources, list)
        or str(helper) not in resources
        or not isinstance(metadata.get("sha256"), str)
    ):
        raise RuntimeError("existing native helper is not owned by Cortex Bridge")
    actual_hash = _regular_file_hash(helper)
    if actual_hash is None or actual_hash != metadata["sha256"]:
        raise RuntimeError("existing native helper ownership hash does not match")
    return actual_hash


@contextmanager
def _exclusive_install_lock(home: Path):
    home.mkdir(parents=True, exist_ok=True)
    lock_path = home / ".install.lock"
    if lock_path.is_symlink():
        raise RuntimeError(f"installer lock is unsafe: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError(f"installer lock is unsafe: {lock_path}")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def _shared_install_lock_if_present(home: Path):
    lock_path = home / ".install.lock"
    if not lock_path.exists() and not lock_path.is_symlink():
        yield
        return
    if lock_path.is_symlink():
        raise RuntimeError(f"installer lock is unsafe: {lock_path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError(f"installer lock is unsafe: {lock_path}")
        fcntl.flock(fd, fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _load_install_transaction(staging: Path, home: Path) -> dict[str, Any]:
    journal = staging / TRANSACTION_NAME
    if journal.is_symlink() or not journal.is_file():
        raise RuntimeError("installer recovery requires a valid transaction journal")
    try:
        payload = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("installer recovery journal is unreadable") from exc
    if (
        payload.get("schema_version") != 1
        or payload.get("owner") != "cortex-bridge"
        or payload.get("home") != str(home)
        or not isinstance(payload.get("plan_hash"), str)
        or not isinstance(payload.get("creates_venv"), bool)
    ):
        raise RuntimeError("installer recovery journal is invalid")
    return payload


def _cleanup_staging(staging: Path) -> None:
    journal = staging / TRANSACTION_NAME
    for child in list(staging.iterdir()):
        if child == journal:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            raise RuntimeError(f"installer staging contains an unknown artifact: {child}")
    journal.unlink(missing_ok=True)
    staging.rmdir()


def _transaction_committed(transaction: dict[str, Any], home: Path) -> bool:
    manifest = _load_owned_manifest()
    if not manifest or manifest.get("plan_hash") != transaction["plan_hash"]:
        return False
    resources = manifest.get("resources")
    if not isinstance(resources, list):
        return False
    if transaction["creates_venv"] and str(home / "venv") not in resources:
        return False
    helper_state = transaction.get("helper")
    if not isinstance(helper_state, dict):
        return True
    target = home / "bin" / MACOS_AX_HELPER_NAME
    metadata = manifest.get("native_helper")
    new_hash = helper_state.get("new_sha256")
    return (
        isinstance(new_hash, str)
        and isinstance(metadata, dict)
        and metadata.get("path") == str(target)
        and metadata.get("sha256") == new_hash
        and str(target) in resources
        and _regular_file_hash(target) == new_hash
    )


def _recover_interrupted_install(home: Path) -> None:
    staging = home / STAGING_NAME
    if not staging.exists() and not staging.is_symlink():
        return
    if staging.is_symlink() or not staging.is_dir():
        raise RuntimeError(f"owned staging path is unsafe: {staging}")
    entries = list(staging.iterdir())
    if not entries:
        staging.rmdir()
        return
    journal = staging / TRANSACTION_NAME
    prejournal_temporary = staging / f".{TRANSACTION_NAME}.tmp"
    if not journal.exists() and entries == [prejournal_temporary]:
        _cleanup_staging(staging)
        return
    transaction = _load_install_transaction(staging, home)
    if _transaction_committed(transaction, home):
        _cleanup_staging(staging)
        return

    helper_state = transaction.get("helper")
    if isinstance(helper_state, dict):
        target = home / "bin" / MACOS_AX_HELPER_NAME
        backup = Path(str(helper_state.get("backup", "")))
        allowed_backups = {
            staging / f".{MACOS_AX_HELPER_NAME}.previous",
            staging / f".{MACOS_AX_HELPER_NAME}.tmp",
        }
        if (
            helper_state.get("target") != str(target)
            or backup not in allowed_backups
            or not isinstance(helper_state.get("previous_exists"), bool)
        ):
            raise RuntimeError("installer recovery helper paths are invalid")
        previous_hash = helper_state.get("previous_sha256")
        new_hash = helper_state.get("new_sha256")
        current_hash = _regular_file_hash(target)
        if helper_state["previous_exists"]:
            if not isinstance(previous_hash, str):
                raise RuntimeError("installer recovery previous helper hash is invalid")
            if current_hash != previous_hash:
                if _regular_file_hash(backup) != previous_hash:
                    raise RuntimeError(
                        "installer recovery cannot identify the previous native helper"
                    )
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise RuntimeError("installer recovery target is unsafe")
                if target.exists():
                    if not isinstance(new_hash, str) or current_hash != new_hash:
                        raise RuntimeError("installer recovery found an unknown native helper")
                    _rename_swap(backup, target)
                    if _regular_file_hash(backup) != new_hash:
                        _rename_swap(backup, target)
                        raise RuntimeError("installer recovery swap displaced an unknown file")
                else:
                    _rename_exclusive(backup, target)
                _fsync_directory(target.parent)
        elif target.exists() or target.is_symlink():
            if not isinstance(new_hash, str) or current_hash != new_hash:
                raise RuntimeError("installer recovery found an unknown native helper")
            rollback_slot = staging / f".{MACOS_AX_HELPER_NAME}.rollback"
            _rename_exclusive(target, rollback_slot)
            if _regular_file_hash(rollback_slot) != new_hash:
                _rename_exclusive(rollback_slot, target)
                raise RuntimeError("installer recovery moved an unknown native helper")
            rollback_slot.unlink()
            _fsync_directory(target.parent)

    if transaction["creates_venv"]:
        staged_venv = staging / "venv"
        target_venv = home / "venv"
        if not staged_venv.exists() and target_venv.exists():
            if target_venv.is_symlink() or not target_venv.is_dir():
                raise RuntimeError("installer recovery venv target is unsafe")
            shutil.rmtree(target_venv)
    _cleanup_staging(staging)


def apply_install(plan: dict[str, Any], approved_hash: str) -> dict[str, Any]:
    if approved_hash != plan["plan_hash"]:
        raise PermissionError("approved plan hash does not match the current plan")
    paths = build_paths()
    with _exclusive_install_lock(paths.home):
        _recover_interrupted_install(paths.home)
        if not plan["commands"]:
            return {
                "schema_version": 1,
                "status": "already_installed",
                "plan_hash": approved_hash,
            }

        staging = paths.home / STAGING_NAME
        if staging.exists() or staging.is_symlink():
            raise RuntimeError(f"owned staging path already exists: {staging}")
        helper_target = _native_helper_path()
        helper_staged = _staged_native_helper_path()
        helper_source_staged = _staged_native_helper_source_path()
        helper_backup = helper_staged
        manifest_path = paths.home / "install" / "owned.json"
        manifest_temporary = staging / "owned.json"
        compile_commands = [
            command
            for command in plan["commands"]
            if command["id"] == "compile_macos_ax_helper"
        ]
        if len(compile_commands) > 1:
            raise RuntimeError("install plan contains duplicate native helper builds")
        compile_command = compile_commands[0] if compile_commands else None
        creates_venv = any(
            command["id"] == "create_venv" for command in plan["commands"]
        )
        staged_venv = staging / "venv"
        target_venv = paths.home / "venv"
        if creates_venv and (target_venv.exists() or target_venv.is_symlink()):
            raise RuntimeError("target venv already exists and is not owned by this plan")

        install_dir = paths.home / "install"
        if install_dir.is_symlink() or (install_dir.exists() and not install_dir.is_dir()):
            raise RuntimeError(f"install manifest directory is unsafe: {install_dir}")
        helper_dir = helper_target.parent
        if helper_dir.is_symlink() or (helper_dir.exists() and not helper_dir.is_dir()):
            raise RuntimeError(f"native helper directory is unsafe: {helper_dir}")

        previous_helper_exists = helper_target.exists() or helper_target.is_symlink()
        previous_helper_hash: str | None = None
        if compile_command is not None and previous_helper_exists:
            previous_helper_hash = _owned_helper_hash_for_replacement(helper_target)

        staging.mkdir(mode=0o700, parents=True)
        transaction: dict[str, Any] = {
            "schema_version": 1,
            "owner": "cortex-bridge",
            "home": str(paths.home),
            "plan_hash": approved_hash,
            "creates_venv": creates_venv,
            "helper": None,
        }
        if compile_command is not None:
            transaction["helper"] = {
                "target": str(helper_target),
                "backup": str(helper_backup),
                "previous_exists": previous_helper_exists,
                "previous_sha256": previous_helper_hash,
                "new_sha256": None,
            }
        _durable_json_write(staging / TRANSACTION_NAME, transaction)

        try:
            if compile_command is not None:
                if (
                    compile_command.get("argv", [None, None])[1]
                    != str(helper_source_staged)
                    or compile_command.get("argv", [None])[-1] != str(helper_staged)
                ):
                    raise RuntimeError("native helper build paths do not match staging")
                _copy_approved_helper_source(
                    helper_source_staged,
                    str(compile_command.get("source_sha256", "")),
                )

            for command in plan["commands"]:
                _run_command(command)

            if creates_venv:
                if staged_venv.is_symlink() or not staged_venv.is_dir():
                    raise RuntimeError("venv command did not produce the staged venv")
                if target_venv.exists() or target_venv.is_symlink():
                    raise RuntimeError("target venv appeared during installation")

            new_helper_hash: str | None = None
            source_hash: str | None = None
            if compile_command is not None:
                if helper_staged.is_symlink() or not helper_staged.is_file():
                    raise RuntimeError("swiftc did not produce the staged native helper")
                if helper_staged.stat().st_size <= 0:
                    raise RuntimeError("swiftc produced an empty native helper")
                source_hash = str(compile_command["source_sha256"])
                if _sha256_file(helper_source_staged) != source_hash:
                    raise RuntimeError("staged native helper source changed during compilation")
                helper_staged.chmod(0o700)
                new_helper_hash = _sha256_file(helper_staged)
                transaction["helper"]["new_sha256"] = new_helper_hash
                _durable_json_write(staging / TRANSACTION_NAME, transaction)

            if creates_venv:
                os.replace(staged_venv, target_venv)
                _fsync_directory(paths.home)

            if compile_command is not None:
                helper_target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if helper_target.parent.is_symlink():
                    raise RuntimeError("native helper directory changed during installation")
                if previous_helper_exists:
                    _rename_swap(helper_staged, helper_target)
                    _fsync_directory(helper_target.parent)
                    if _regular_file_hash(helper_staged) != previous_helper_hash:
                        _rename_swap(helper_staged, helper_target)
                        _fsync_directory(helper_target.parent)
                        raise RuntimeError(
                            "native helper swap displaced a file that is not owned"
                        )
                else:
                    try:
                        _rename_exclusive(helper_staged, helper_target)
                    except FileExistsError as exc:
                        raise RuntimeError(
                            "unowned native helper appeared during installation"
                        ) from exc
                    _fsync_directory(helper_target.parent)
                if _regular_file_hash(helper_target) != new_helper_hash:
                    raise RuntimeError("installed native helper hash does not match staging")

            install_dir.mkdir(parents=True, exist_ok=True)
            resources = [str(target_venv), str(manifest_path)]
            native_helper: dict[str, str] | None = None
            if sys.platform == "darwin" and helper_target.is_file() and not helper_target.is_symlink():
                if compile_command is not None:
                    binary_hash = str(new_helper_hash)
                    installed_source_hash = str(source_hash)
                else:
                    existing = (_load_owned_manifest() or {}).get("native_helper")
                    if not isinstance(existing, dict):
                        raise RuntimeError("installed native helper ownership metadata is missing")
                    binary_hash = str(existing.get("sha256", ""))
                    installed_source_hash = str(existing.get("source_sha256", ""))
                native_helper = {
                    "path": str(helper_target),
                    "sha256": binary_hash,
                    "source_sha256": installed_source_hash,
                }
                resources.append(str(helper_target))
            manifest = {
                "schema_version": 1,
                "owner": "cortex-bridge",
                "version": current_version(),
                "plan_hash": approved_hash,
                "resources": resources,
                "chrome_extension_path": str((ROOT / "chrome-extension").resolve()),
            }
            if native_helper is not None:
                manifest["native_helper"] = native_helper
            _durable_json_write(manifest_temporary, manifest)
            os.replace(manifest_temporary, manifest_path)
            _fsync_directory(install_dir)
        except BaseException:
            _recover_interrupted_install(paths.home)
            raise

        _recover_interrupted_install(paths.home)
    return {
        "schema_version": 1,
        "status": "installed",
        "plan_hash": approved_hash,
        "manifest": str(manifest_path),
        "chrome_extension_path": str((ROOT / "chrome-extension").resolve()),
        "next_human_action": "Open chrome://extensions and load the unpacked extension after explicit approval.",
    }


def _load_owned_manifest() -> dict[str, Any] | None:
    path = _owned_manifest_path()
    if path.parent.is_symlink() or path.is_symlink():
        return None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if payload.get("owner") != "cortex-bridge" or not isinstance(payload.get("resources"), list):
        return None
    return payload


def build_uninstall_plan() -> dict[str, Any]:
    paths = build_paths()
    manifest = _load_owned_manifest()
    resources: list[str] = []
    for raw in (manifest or {}).get("resources", []):
        candidate = Path(str(raw)).resolve(strict=False)
        try:
            candidate.relative_to(paths.home)
        except ValueError:
            continue
        if candidate.exists() or candidate.is_symlink():
            resources.append(str(candidate))
    payload = {
        "schema_version": 1,
        "action": "uninstall",
        "version": current_version(),
        "target": str(paths.home),
        "resources": sorted(set(resources)),
        "preserved": ["settings", "database", "runs", "attachments", "browser profile", "logs"],
    }
    return _hashed(payload)


def apply_uninstall(plan: dict[str, Any], approved_hash: str) -> dict[str, Any]:
    if approved_hash != plan["plan_hash"]:
        raise PermissionError("approved uninstall plan hash does not match")
    home = build_paths().home
    removed: list[str] = []
    with _exclusive_install_lock(home):
        port = int(os.environ.get("PORT", "8420"))
        process = classify(load_record(build_paths().pids / "console.json"), port)
        if process.state == "owned":
            raise RuntimeError(
                "Cortex Bridge is still running; stop it with ./scripts/cortex.sh stop "
                "before uninstalling"
            )
        if process.state == "unknown":
            raise RuntimeError(
                "Cortex Bridge runtime state could not be verified; run "
                "./scripts/cortex.sh status before uninstalling"
            )
        if process.state != "stopped":
            listeners = getattr(process, "listener_pids", None) or []
            if listeners:
                raise RuntimeError(
                    "A listener is still active on the Cortex Bridge port; run "
                    "./scripts/cortex.sh status and stop it before uninstalling"
                )
            raise RuntimeError(
                f"Cortex Bridge runtime state is {process.state}, not verified stopped; "
                "run ./scripts/cortex.sh status before uninstalling"
            )
        _recover_interrupted_install(home)
        current_plan = build_uninstall_plan()
        if current_plan["plan_hash"] != approved_hash:
            raise PermissionError("approved uninstall plan is stale after recovery")
        for raw in sorted(
            current_plan["resources"],
            key=lambda value: len(Path(value).parts),
            reverse=True,
        ):
            candidate = Path(raw).resolve(strict=False)
            candidate.relative_to(home)
            if candidate.is_symlink() or candidate.is_file():
                candidate.unlink(missing_ok=True)
                removed.append(str(candidate))
            elif candidate.is_dir():
                shutil.rmtree(candidate)
                removed.append(str(candidate))
    return {"schema_version": 1, "status": "uninstalled", "plan_hash": approved_hash, "removed": removed}


def _swift_toolchain_doctor_check() -> dict[str, Any]:
    check: dict[str, Any] = {
        "id": "swift_toolchain",
        "label": "Compilateur Swift macOS",
        "status": "warning",
        "required": False,
        "detail": "not available",
        "hint": (
            "Installe les outils de ligne de commande Xcode depuis "
            "https://developer.apple.com/xcode/resources/ puis relance le diagnostic."
        ),
    }
    if sys.platform != "darwin":
        check["detail"] = "available on macOS only"
        return check
    swiftc = _swiftc_path()
    if swiftc is not None:
        check["status"] = "pass"
        check["detail"] = "available"
        check["path"] = str(swiftc)
        check["hint"] = ""
    return check


def _native_helper_doctor_checks() -> tuple[list[dict[str, Any]], bool]:
    binary_check: dict[str, Any] = {
        "id": "macos_ax_helper",
        "label": "Helper macOS d’envoi ChatGPT",
        "status": "warning",
        "required": False,
        "detail": "not installed",
        "path": str(_native_helper_path()),
        "hint": "Relance le plan approuvé de scripts/install.sh pour compiler le helper.",
    }
    permission_check: dict[str, Any] = {
        "id": "macos_accessibility",
        "label": "Autorisation Accessibilité macOS",
        "status": "warning",
        "required": False,
        "detail": "not checked",
        "hint": (
            f"Ajoute exactement {_native_helper_path()} dans Réglages Système → "
            "Confidentialité et sécurité → Accessibilité, puis relance le diagnostic. "
            "Cortex ne demande jamais cette autorisation automatiquement."
        ),
    }
    if sys.platform != "darwin":
        binary_check["detail"] = "available on macOS only"
        permission_check["detail"] = "not applicable"
        return [binary_check, permission_check], False

    helper = _native_helper_path()
    metadata = (_load_owned_manifest() or {}).get("native_helper")
    verified = False
    helper_fd: int | None = None
    if not isinstance(metadata, dict) or metadata.get("path") != str(helper):
        binary_check["detail"] = "ownership metadata missing"
    elif helper.parent.is_symlink() or helper.is_symlink() or not helper.is_file():
        binary_check["status"] = "fail"
        binary_check["detail"] = "owned binary missing or unsafe"
    else:
        expected_hash = metadata.get("sha256")
        expected_source_hash = metadata.get("source_sha256")
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            helper_fd = os.open(helper, flags)
            opened = os.fstat(helper_fd)
            if not stat.S_ISREG(opened.st_mode) or opened.st_mode & 0o111 == 0:
                raise PermissionError("owned binary is not executable")
            actual_hash = _sha256_fd(helper_fd)
            actual_source_hash = _sha256_file(MACOS_AX_HELPER_SOURCE)
        except PermissionError:
            binary_check["status"] = "fail"
            binary_check["detail"] = "owned binary is not executable"
        except OSError:
            binary_check["status"] = "fail"
            binary_check["detail"] = "owned binary could not be read"
        else:
            if not isinstance(expected_hash, str) or actual_hash != expected_hash:
                binary_check["status"] = "fail"
                binary_check["detail"] = "owned binary hash mismatch"
            elif (
                not isinstance(expected_source_hash, str)
                or actual_source_hash != expected_source_hash
            ):
                binary_check["status"] = "fail"
                binary_check["detail"] = "native helper source hash mismatch"
            else:
                binary_check["status"] = "pass"
                binary_check["detail"] = f"executable; SHA-256 verified ({actual_hash[:12]}…)"
                binary_check["hint"] = ""
                verified = True

    if verified and helper_fd is not None:
        try:
            if not _opened_path_matches(helper_fd, helper):
                permission_check["status"] = "fail"
                permission_check["detail"] = "owned binary changed before permission check"
                verified = False
                result = None
            else:
                result = subprocess.run(
                    [str(helper), "--check-permissions"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if not _opened_path_matches(helper_fd, helper):
                    permission_check["status"] = "fail"
                    permission_check["detail"] = "owned binary changed during permission check"
                    verified = False
                    result = None
        except (OSError, subprocess.SubprocessError):
            permission_check["status"] = "fail"
            permission_check["detail"] = "permission check failed"
        else:
            output = result.stdout.strip() if result is not None else ""
            if result is not None and result.returncode == 0 and output == "READY":
                permission_check["status"] = "pass"
                permission_check["detail"] = "READY"
                permission_check["hint"] = ""
            elif result is not None and result.returncode == 3:
                permission_check["detail"] = "permission not granted"
            elif result is not None:
                permission_check["status"] = "fail"
                permission_check["detail"] = "permission check returned an invalid result"
    if helper_fd is not None:
        os.close(helper_fd)
    return [binary_check, permission_check], verified


def _runtime_dependencies_doctor_check() -> dict[str, Any]:
    dependencies = ("fastapi", "uvicorn", "playwright", "websockets", "textual")
    python = os.environ.get("PYTHON_BIN") or sys.executable
    probe = (
        "import importlib,json\n"
        f"names={dependencies!r}\n"
        "failed=[]\n"
        "for name in names:\n"
        " try: importlib.import_module(name)\n"
        " except Exception: failed.append(name)\n"
        "print(json.dumps(failed))\n"
        "raise SystemExit(1 if failed else 0)\n"
    )
    check: dict[str, Any] = {
        "id": "runtime_dependencies",
        "label": "Dépendances Python du moteur",
        "status": "fail",
        "required": True,
        "detail": f"probe failed via {python}",
        "interpreter": python,
        "hint": (
            "Lance ./scripts/install.sh --dry-run --json, relis le plan, puis "
            "./scripts/install.sh --approve-plan HASH --json."
        ),
    }
    try:
        result = subprocess.run(
            [python, "-c", probe],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return check
    try:
        failed = json.loads(result.stdout.strip())
    except (TypeError, json.JSONDecodeError):
        return check
    if not isinstance(failed, list) or not all(
        isinstance(name, str) and name in dependencies for name in failed
    ):
        return check
    if result.returncode == 0 and not failed:
        check["status"] = "pass"
        check["detail"] = f"available via {python}"
        check["hint"] = ""
    elif failed:
        check["detail"] = f"missing or unusable: {', '.join(failed)}"
    return check


def doctor() -> dict[str, Any]:
    paths = build_paths()
    record = paths.pids / "console.json"
    port = int(os.environ.get("PORT", "8420"))
    local_url = f"http://127.0.0.1:{port}"
    process = classify(load_record(record), port)
    extension_path = (ROOT / "chrome-extension").resolve()
    extension_manifest = extension_path / "manifest.json"
    extension_ok = False
    extension_detail = "manifest missing"
    try:
        extension = json.loads(extension_manifest.read_text(encoding="utf-8"))
        extension_ok = (
            extension.get("manifest_version") == 3
            and int(extension.get("minimum_chrome_version", "0")) >= 116
            and extension.get("background", {}).get("service_worker") == "service-worker.js"
        )
        extension_detail = "unpacked extension ready" if extension_ok else "manifest invalid"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    with _shared_install_lock_if_present(paths.home):
        native_checks, native_helper_ready = _native_helper_doctor_checks()
    checks = [
        {
            "id": "python",
            "label": "Python 3.11 ou plus récent",
            "status": "pass" if sys.version_info >= (3, 11) else "fail",
            "required": True,
            "detail": sys.version.split()[0],
            "hint": "Installe Python 3.11+ depuis https://www.python.org/downloads/macos/",
        },
        {
            "id": "cortex_home",
            "label": "Dossier de données CORTEX_HOME",
            "status": "pass" if paths.home.is_absolute() else "fail",
            "required": True,
            "detail": str(paths.home),
            "hint": "Définis CORTEX_HOME avec un chemin absolu, ou laisse la valeur par défaut.",
        },
        {
            "id": "deterministic",
            "label": "Exécuteur déterministe local",
            "status": "pass",
            "required": True,
            "detail": "available without Ollama",
            "hint": "",
        },
        _runtime_dependencies_doctor_check(),
        _swift_toolchain_doctor_check(),
        {
            "id": "chrome_extension",
            "label": "Extension Chrome Cortex Bridge",
            "status": "pass" if extension_ok else "fail",
            "required": True,
            "detail": extension_detail,
            "path": str(extension_path),
            "hint": "Lance scripts/install-extension.sh : il ouvre chrome://extensions et copie le chemin à charger.",
        },
        {
            "id": "installation",
            "label": "Installation du moteur (venv + dépendances)",
            "status": "pass" if _installed() else "warning",
            "required": False,
            "detail": "installed" if _installed() else "not installed",
            "hint": "Lance ./scripts/install.sh --dry-run --json, relis le plan, puis ./scripts/install.sh --approve-plan HASH --json",
        },
        *native_checks,
        {
            "id": "console_process",
            "label": "Console locale en cours d'exécution",
            "status": process.state,
            "required": False,
            "detail": process.reason or process.state,
            "hint": f"Lance scripts/cortex.sh start puis ouvre {local_url}",
        },
    ]
    return {
        "schema_version": 1,
        "version": current_version(),
        "ok": all(check["status"] == "pass" for check in checks if check["required"]),
        "cortex_home": str(paths.home),
        "local_url": local_url,
        "modes": {
            "deterministic": True,
            "chrome_extension": extension_ok,
            "macos_native_send": native_helper_ready,
            "ollama": False,
            "playwright_development": False,
            "webbridge": False,
        },
        "checks": checks,
    }


_CONSOLE_STATE_LABELS = {
    "owned": "pass",
    "stopped": "warning",
    "stale": "warning",
    "foreign": "warning",
    "unknown": "warning",
}

_CONSOLE_STATE_HINTS = {
    "foreign": "Un autre processus utilise le port. Vois le détail avec : scripts/cortex.sh status",
    "stale": "Fiche processus périmée : scripts/cortex.sh status la nettoie, puis scripts/cortex.sh start",
    "unknown": "Vérification du port impossible — réessaie dans quelques secondes.",
}


def _print_doctor_text(payload: dict[str, Any]) -> None:
    print(f"Cortex Bridge {payload.get('version', '')} — vérification de l'installation")
    print()
    icons = {"pass": "✅", "warning": "⚠️ ", "fail": "❌"}
    missing = 0
    for check in payload.get("checks", []):
        status = str(check.get("status"))
        mapped = _CONSOLE_STATE_LABELS.get(status, status) if check.get("id") == "console_process" else status
        icon = icons.get(mapped, "❓")
        print(f"{icon} {check.get('label', check.get('id'))} : {check.get('detail', '')}")
        hint = check.get("hint") or ""
        if check.get("id") == "console_process":
            hint = _CONSOLE_STATE_HINTS.get(status, hint)
        if mapped != "pass":
            missing += 1
            if hint:
                print(f"   → {hint}")
    print()
    if payload.get("ok") and missing == 0:
        local_url = payload.get("local_url") or "http://127.0.0.1:8420"
        print(f"Tout est prêt ✅  Ouvre {local_url} pour utiliser Cortex.")
    elif payload.get("ok"):
        print("Cortex peut fonctionner, mais regarde les points ⚠️  ci-dessus.")
    else:
        print("Il manque des éléments ❌  Suis les flèches → ci-dessus, puis relance scripts/cortex.sh doctor")


def _print(payload: dict[str, Any], as_json: bool, *, kind: str = "generic") -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    elif kind == "doctor":
        _print_doctor_text(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.add_argument("--approve-plan")
    install_parser.add_argument("--json", action="store_true")
    install_parser.add_argument("--rebuild-ui", action="store_true")
    install_parser.add_argument("--with-ollama-model")
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser.add_argument("--approve-plan")
    uninstall_parser.add_argument("--json", action="store_true")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            _print(doctor(), args.json, kind="doctor")
            return 0
        if args.action == "install":
            plan = build_install_plan(rebuild_ui=args.rebuild_ui, ollama_model=args.with_ollama_model)
            if args.dry_run:
                _print(plan, args.json)
                return 0
            if not args.approve_plan:
                raise PermissionError("install requires --dry-run or --approve-plan HASH")
            _print(apply_install(plan, args.approve_plan), args.json)
            return 0
        plan = build_uninstall_plan()
        if args.dry_run:
            _print(plan, args.json)
            return 0
        if not args.approve_plan:
            raise PermissionError("uninstall requires --dry-run or --approve-plan HASH")
        _print(apply_uninstall(plan, args.approve_plan), args.json)
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError, subprocess.SubprocessError) as exc:
        payload = {"schema_version": 1, "status": "error", "error": str(exc)}
        _print(payload, getattr(args, "json", False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
