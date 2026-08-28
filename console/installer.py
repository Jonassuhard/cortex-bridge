"""Consent-bound install, doctor and uninstall plans."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from cortex_paths import build_paths
from lifecycle_lock import LIFECYCLE_LOCK_MARKER, ensure_private_directory, open_lifecycle_lock
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


def _renameatx_relative(
    source_dir_fd: int,
    source: str,
    target_dir_fd: int,
    target: str,
    flags: int,
) -> None:
    if sys.platform != "darwin":
        raise OSError("renameatx_np is available only on macOS")
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = libc.renameatx_np
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        source_dir_fd,
        os.fsencode(source),
        target_dir_fd,
        os.fsencode(target),
        flags,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == getattr(os, "EEXIST", 17):
        raise FileExistsError(error, os.strerror(error), target)
    raise OSError(error, os.strerror(error), target)


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
    venv = paths.home / "venv"
    return not venv.is_symlink() and venv.is_dir() and _owned_manifest_path().is_file()


def _owned_manifest_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    path = _owned_manifest_path()
    if path.parent.is_symlink():
        raise RuntimeError("installed manifest path is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("installed manifest is missing or unsafe") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise RuntimeError("installed manifest is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not _opened_path_matches(fd, path):
            raise RuntimeError("installed manifest identity changed while reading")
    finally:
        os.close(fd)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("installed manifest is unreadable") from exc
    if payload.get("owner") != "cortex-bridge" or not isinstance(
        payload.get("resources"), list
    ):
        raise RuntimeError("installed manifest ownership is invalid")
    return payload, {
        "path": str(path),
        "dev": details.st_dev,
        "ino": details.st_ino,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _manifest_venv_identity(
    manifest: dict[str, Any] | None,
    venv: Path,
) -> tuple[int, int] | None:
    if not manifest or "venv" not in manifest:
        return None
    metadata = manifest.get("venv")
    if (
        not isinstance(metadata, dict)
        or metadata.get("path") != str(venv)
        or type(metadata.get("dev")) is not int
        or type(metadata.get("ino")) is not int
    ):
        raise RuntimeError("venv ownership metadata is invalid")
    return metadata["dev"], metadata["ino"]


def _legacy_preservation_path(kind: str, identity: tuple[int, int]) -> Path:
    return build_paths().home / (
        f".legacy-preserved-{kind}-{identity[0]:x}-{identity[1]:x}"
    )


def _build_metadata_migration() -> dict[str, Any] | None:
    if _load_owned_manifest() is None:
        return None
    manifest, manifest_snapshot = _owned_manifest_snapshot()
    resources = manifest["resources"]
    venv = build_paths().home / "venv"
    if str(venv) not in resources:
        raise RuntimeError("installed manifest does not own the existing venv")
    recorded_venv = _manifest_venv_identity(manifest, venv)
    venv_missing = recorded_venv is None

    helper = _native_helper_path()
    helper_metadata = manifest.get("native_helper")
    unowned_helper_metadata = manifest.get("preserved_unowned_helper")
    helper_missing = False
    if helper_metadata is not None:
        if not isinstance(helper_metadata, dict):
            raise RuntimeError("native helper ownership metadata is invalid")
        has_dev = "dev" in helper_metadata
        has_ino = "ino" in helper_metadata
        if has_dev != has_ino:
            raise RuntimeError("native helper ownership metadata is incomplete")
        if has_dev:
            recorded_helper = _manifest_native_helper_identity(manifest, helper)
            try:
                actual_helper_identity = _file_identity(helper)
            except RuntimeError:
                actual_helper_identity = None
            if recorded_helper is None or actual_helper_identity != recorded_helper[:2]:
                staging = build_paths().home / STAGING_NAME
                if not staging.is_dir() or staging.is_symlink():
                    raise RuntimeError(
                        "native helper ownership identity does not match the installed manifest"
                    )
        else:
            helper_missing = True
    elif unowned_helper_metadata is not None:
        if (
            not isinstance(unowned_helper_metadata, dict)
            or set(unowned_helper_metadata) != {"path", "dev", "ino", "sha256"}
            or unowned_helper_metadata.get("path") != str(helper)
            or type(unowned_helper_metadata.get("dev")) is not int
            or type(unowned_helper_metadata.get("ino")) is not int
            or not isinstance(unowned_helper_metadata.get("sha256"), str)
            or _file_identity(helper)
            != (
                unowned_helper_metadata["dev"],
                unowned_helper_metadata["ino"],
            )
            or _regular_file_hash(helper) != unowned_helper_metadata["sha256"]
        ):
            raise RuntimeError("preserved unowned helper metadata is invalid")
        helper_missing = _swiftc_path() is not None

    venv_identity = _directory_identity(venv)
    if recorded_venv is not None and recorded_venv != venv_identity:
        raise RuntimeError("venv ownership identity does not match the installed manifest")
    if not venv_missing and not helper_missing:
        return None

    venv_snapshot: dict[str, Any] = {
        "action": "rebuild_preserve" if venv_missing else "retain",
        "path": str(venv),
        "dev": venv_identity[0],
        "ino": venv_identity[1],
    }
    if venv_missing:
        preserved_venv = _legacy_preservation_path("venv", venv_identity)
        if preserved_venv.exists() or preserved_venv.is_symlink():
            raise RuntimeError(
                f"legacy venv preservation path already exists: {preserved_venv}"
            )
        venv_snapshot["preserve_path"] = str(preserved_venv)

    helper_snapshot: dict[str, Any] | None = None
    helper_source_metadata = helper_metadata or unowned_helper_metadata
    if helper_source_metadata is not None and (helper_metadata is not None or helper_missing):
        if (
            helper_source_metadata.get("path") != str(helper)
            or (
                helper_metadata is not None
                and str(helper) not in resources
            )
            or (
                unowned_helper_metadata is not None
                and str(helper) in resources
            )
            or not isinstance(helper_source_metadata.get("sha256"), str)
            or len(helper_source_metadata["sha256"]) != 64
            or (
                helper_metadata is not None
                and (
                    not isinstance(helper_source_metadata.get("source_sha256"), str)
                    or len(helper_source_metadata["source_sha256"]) != 64
                )
            )
        ):
            raise RuntimeError("native helper ownership metadata is invalid")
        helper_identity = _file_identity(helper)
        helper_hash = _regular_file_hash(helper)
        if helper_hash != helper_source_metadata["sha256"]:
            raise RuntimeError("native helper ownership hash does not match")
        helper_action = (
            "rebuild_preserve"
            if helper_missing and _swiftc_path() is not None
            else "preserve_unowned" if helper_missing else "retain"
        )
        helper_snapshot = {
            "action": helper_action,
            "path": str(helper),
            "dev": helper_identity[0],
            "ino": helper_identity[1],
            "sha256": helper_hash,
        }
        if helper_action == "rebuild_preserve":
            preserved_helper = _legacy_preservation_path(
                MACOS_AX_HELPER_NAME,
                helper_identity,
            )
            if preserved_helper.exists() or preserved_helper.is_symlink():
                raise RuntimeError(
                    "legacy helper preservation path already exists: "
                    f"{preserved_helper}"
                )
            helper_snapshot["preserve_path"] = str(preserved_helper)

    return {
        "manifest": manifest_snapshot,
        "venv": venv_snapshot,
        "native_helper": helper_snapshot,
    }


def _venv_needs_repair() -> bool:
    paths = build_paths()
    venv = paths.home / "venv"
    staged_prefix = os.fsencode(paths.home / STAGING_NAME)
    manifest = _load_owned_manifest()
    recorded_identity = _manifest_venv_identity(manifest, venv)
    if recorded_identity is not None and _directory_identity(venv) != recorded_identity:
        raise RuntimeError("venv ownership identity does not match the installed manifest")
    staging_signatures: list[bool] = []
    for name in ("pip", "uvicorn", "playwright"):
        entrypoint = venv / "bin" / name
        if entrypoint.is_symlink() or not entrypoint.is_file():
            raise RuntimeError(
                "unsafe automatic venv repair refused: required entrypoint is missing"
            )
        try:
            mode = entrypoint.stat(follow_symlinks=False).st_mode
            content = entrypoint.read_bytes()
        except OSError:
            raise RuntimeError(
                "unsafe automatic venv repair refused: required entrypoint is unreadable"
            )
        if mode & 0o111 == 0:
            raise RuntimeError(
                "unsafe automatic venv repair refused: required entrypoint is not executable"
            )
        staging_signatures.append(
            staged_prefix in content or STAGING_NAME.encode("utf-8") in content
        )
    if any(staging_signatures):
        if not all(staging_signatures) or manifest is None:
            raise RuntimeError(
                "unsafe automatic venv repair refused: legacy staging signature is incomplete"
            )
        return True
    return False


def build_install_plan(*, rebuild_ui: bool = False, ollama_model: str | None = None) -> dict[str, Any]:
    paths = build_paths()
    staging = paths.home / STAGING_NAME
    python = os.environ.get("PYTHON_BIN") or sys.executable
    commands: list[dict[str, Any]] = []
    human_pauses = _human_pauses()
    installed = _installed()
    metadata_migration = _build_metadata_migration() if installed else None
    manifest_snapshot: dict[str, Any] | None = None
    if metadata_migration is not None:
        manifest_snapshot = metadata_migration["manifest"]
    elif installed and _load_owned_manifest() is not None:
        _, manifest_snapshot = _owned_manifest_snapshot()
    legacy_venv = (metadata_migration or {}).get("venv")
    if isinstance(legacy_venv, dict) and legacy_venv.get("action") == "rebuild_preserve":
        venv_action = "rebuild_legacy"
    else:
        venv_action = "repair" if installed and _venv_needs_repair() else (
            "none" if installed else "create"
        )
    if venv_action in {"create", "repair", "rebuild_legacy"}:
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
    legacy_helper = (metadata_migration or {}).get("native_helper")
    helper_action = (
        legacy_helper.get("action") if isinstance(legacy_helper, dict) else None
    )
    helper_needs_build = (
        helper_action == "rebuild_preserve" or _native_helper_needs_build()
    )
    if helper_action == "preserve_unowned":
        human_pauses.append({
            "kind": "file_send_toolchain",
            "detail": (
                "The legacy native helper was preserved but is no longer owned. "
                "Install Apple's Command Line Tools and rerun this installer to rebuild it."
            ),
        })
    if helper_needs_build:
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
        "venv_action": venv_action,
        "metadata_migration": metadata_migration,
        "manifest_snapshot": manifest_snapshot,
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


def _durable_json_write(
    path: Path,
    payload: dict[str, Any],
    *,
    must_create: bool = False,
) -> None:
    expected_existing: dict[str, Any] | None = None
    if path.exists() or path.is_symlink():
        if must_create:
            raise RuntimeError(
                f"durable JSON destination appeared before publication: {path}"
            )
        expected_existing = _regular_file_fingerprint(path)
    fd, temporary_raw = tempfile.mkstemp(
        prefix=f".{path.name}.write-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_raw)
    published = False
    try:
        os.fchmod(fd, 0o600)
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        view = memoryview(encoded)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        temporary_details = os.fstat(fd)
        temporary_fingerprint = {
            "path": str(temporary),
            "dev": temporary_details.st_dev,
            "ino": temporary_details.st_ino,
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        if not _opened_path_matches(fd, temporary):
            raise RuntimeError("durable JSON temporary changed before publication")
        if expected_existing is None:
            try:
                _rename_exclusive(temporary, path)
            except FileExistsError as exc:
                raise RuntimeError(
                    f"durable JSON destination appeared during publication: {path}"
                ) from exc
        else:
            if sys.platform != "darwin":
                raise RuntimeError(
                    "safe durable JSON replacement requires atomic exchange"
                )
            if _regular_file_fingerprint(path) != expected_existing:
                raise RuntimeError(
                    f"durable JSON destination changed before publication: {path}"
                )
            _rename_swap(temporary, path)
            displaced = _regular_file_fingerprint(temporary)
            if (
                displaced != {**expected_existing, "path": str(temporary)}
                or not _opened_path_matches(fd, path)
            ):
                if _opened_path_matches(fd, path):
                    _rename_swap(temporary, path)
                    _fsync_directory(path.parent)
                raise RuntimeError(
                    f"durable JSON destination changed during publication: {path}"
                )
        published = True
        _fsync_directory(path.parent)
        os.lseek(fd, 0, os.SEEK_SET)
        if (
            _sha256_fd(fd) != temporary_fingerprint["sha256"]
            or not _opened_path_matches(fd, path)
            or _regular_file_fingerprint(path)
            != {**temporary_fingerprint, "path": str(path)}
        ):
            raise RuntimeError(
                f"durable JSON destination changed after publication: {path}"
            )
    finally:
        os.close(fd)
    if not published:
        raise RuntimeError(f"durable JSON publication failed: {path}")


def _validated_metadata_migration(
    migration: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(migration) != {"manifest", "venv", "native_helper"}:
        raise RuntimeError("install plan metadata migration is invalid")
    expected_manifest = migration.get("manifest")
    expected_venv = migration.get("venv")
    expected_helper = migration.get("native_helper")
    expected_venv_keys = {"action", "path", "dev", "ino"}
    if isinstance(expected_venv, dict) and expected_venv.get("action") == "rebuild_preserve":
        expected_venv_keys.add("preserve_path")
    if (
        not isinstance(expected_manifest, dict)
        or set(expected_manifest) != {"path", "dev", "ino", "sha256"}
        or expected_manifest.get("path") != str(_owned_manifest_path())
        or type(expected_manifest.get("dev")) is not int
        or type(expected_manifest.get("ino")) is not int
        or not isinstance(expected_manifest.get("sha256"), str)
        or len(expected_manifest["sha256"]) != 64
        or not isinstance(expected_venv, dict)
        or set(expected_venv) != expected_venv_keys
        or expected_venv.get("action") not in {"retain", "rebuild_preserve"}
        or expected_venv.get("path") != str(build_paths().home / "venv")
        or type(expected_venv.get("dev")) is not int
        or type(expected_venv.get("ino")) is not int
    ):
        raise RuntimeError("install plan metadata migration is invalid")
    if expected_venv["action"] == "rebuild_preserve":
        expected_preserved_venv = _legacy_preservation_path(
            "venv",
            (expected_venv["dev"], expected_venv["ino"]),
        )
        if (
            expected_venv.get("preserve_path") != str(expected_preserved_venv)
            or expected_preserved_venv.exists()
            or expected_preserved_venv.is_symlink()
        ):
            raise RuntimeError("install plan legacy venv preservation is invalid")
    if expected_helper is not None:
        helper_keys = {"action", "path", "dev", "ino", "sha256"}
        if (
            isinstance(expected_helper, dict)
            and expected_helper.get("action") == "rebuild_preserve"
        ):
            helper_keys.add("preserve_path")
        if (
            not isinstance(expected_helper, dict)
            or set(expected_helper) != helper_keys
            or expected_helper.get("action")
            not in {"retain", "rebuild_preserve", "preserve_unowned"}
            or expected_helper.get("path") != str(_native_helper_path())
            or type(expected_helper.get("dev")) is not int
            or type(expected_helper.get("ino")) is not int
            or not isinstance(expected_helper.get("sha256"), str)
            or len(expected_helper["sha256"]) != 64
        ):
            raise RuntimeError("install plan metadata migration is invalid")
        if expected_helper["action"] == "rebuild_preserve":
            expected_preserved_helper = _legacy_preservation_path(
                MACOS_AX_HELPER_NAME,
                (expected_helper["dev"], expected_helper["ino"]),
            )
            if (
                expected_helper.get("preserve_path")
                != str(expected_preserved_helper)
                or expected_preserved_helper.exists()
                or expected_preserved_helper.is_symlink()
            ):
                raise RuntimeError("install plan legacy helper preservation is invalid")

    try:
        manifest, actual_manifest = _owned_manifest_snapshot()
    except RuntimeError as exc:
        raise RuntimeError(
            "installed manifest identity or hash changed after plan approval"
        ) from exc
    if actual_manifest != expected_manifest:
        raise RuntimeError("installed manifest identity or hash changed after plan approval")
    resources = manifest["resources"]
    venv = build_paths().home / "venv"
    if str(venv) not in resources or _directory_identity(venv) != (
        expected_venv["dev"],
        expected_venv["ino"],
    ):
        raise RuntimeError("venv ownership identity changed after plan approval")
    recorded_venv = _manifest_venv_identity(manifest, venv)
    if recorded_venv is not None and recorded_venv != (
        expected_venv["dev"],
        expected_venv["ino"],
    ):
        raise RuntimeError("venv ownership identity does not match the installed manifest")

    migrated = dict(manifest)
    migrated["resources"] = list(resources)
    if expected_venv["action"] == "retain":
        migrated["venv"] = {
            key: expected_venv[key] for key in ("path", "dev", "ino")
        }
    else:
        migrated.pop("venv", None)
    helper_metadata = manifest.get("native_helper")
    unowned_helper_metadata = manifest.get("preserved_unowned_helper")
    if expected_helper is not None:
        helper = _native_helper_path()
        helper_record = (
            helper_metadata
            if isinstance(helper_metadata, dict)
            else unowned_helper_metadata
        )
        if (
            not isinstance(helper_record, dict)
            or helper_record.get("path") != str(helper)
            or helper_record.get("sha256") != expected_helper["sha256"]
            or (
                isinstance(helper_metadata, dict)
                and str(helper) not in resources
            )
            or (
                not isinstance(helper_metadata, dict)
                and str(helper) in resources
            )
            or _file_identity(helper)
            != (expected_helper["dev"], expected_helper["ino"])
            or _regular_file_hash(helper) != expected_helper["sha256"]
        ):
            raise RuntimeError("native helper ownership identity or hash changed")
        has_dev = "dev" in helper_record
        has_ino = "ino" in helper_record
        if has_dev != has_ino:
            raise RuntimeError("native helper ownership metadata is incomplete")
        if has_dev and (
            helper_record.get("dev"),
            helper_record.get("ino"),
        ) != (expected_helper["dev"], expected_helper["ino"]):
            raise RuntimeError("native helper ownership identity does not match")
        if expected_helper["action"] == "retain":
            if not has_dev or not isinstance(helper_metadata, dict):
                raise RuntimeError("native helper ownership identity is missing")
            migrated["native_helper"] = dict(helper_metadata)
        elif expected_helper["action"] == "preserve_unowned":
            migrated.pop("native_helper", None)
            migrated["resources"] = [
                raw for raw in migrated["resources"] if raw != str(helper)
            ]
            migrated["preserved_unowned_helper"] = {
                key: expected_helper[key] for key in ("path", "dev", "ino", "sha256")
            }
        else:
            migrated.pop("native_helper", None)
    elif helper_metadata is not None:
        raise RuntimeError("native helper ownership metadata is inconsistent")
    return migrated, expected_manifest


def _write_migrated_manifest(
    payload: dict[str, Any],
    expected_manifest: dict[str, Any],
) -> None:
    path = _owned_manifest_path()
    temporary = path.with_name(f".{path.name}.migration.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("manifest migration temporary path already exists")
    try:
        _durable_json_write(temporary, payload, must_create=True)
        _publish_manifest_replacement(temporary, path, expected_manifest)
    except BaseException:
        raise


def _regular_file_fingerprint(path: Path) -> dict[str, Any]:
    if path.parent.is_symlink():
        raise RuntimeError(f"owned file path is unsafe: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"owned file is missing or unsafe: {path}") from exc
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise RuntimeError(f"owned file is not regular: {path}")
        digest = _sha256_fd(fd)
        if not _opened_path_matches(fd, path):
            raise RuntimeError(f"owned file identity changed while reading: {path}")
    finally:
        os.close(fd)
    return {
        "path": str(path),
        "dev": details.st_dev,
        "ino": details.st_ino,
        "sha256": digest,
    }


def _publish_manifest_replacement(
    replacement: Path,
    target: Path,
    expected_manifest: dict[str, Any],
) -> None:
    replacement_fingerprint = _regular_file_fingerprint(replacement)
    previous_backup = target.parent / (
        ".previous-owned-manifest-"
        f"{expected_manifest['dev']:x}-{expected_manifest['ino']:x}.json"
    )
    if previous_backup.exists() or previous_backup.is_symlink():
        raise RuntimeError(f"previous manifest backup already exists: {previous_backup}")
    _, current_manifest = _owned_manifest_snapshot()
    if current_manifest != expected_manifest:
        raise RuntimeError("installed manifest identity or hash changed before publication")
    if sys.platform != "darwin":
        os.replace(replacement, target)
        _fsync_directory(target.parent)
        return

    _rename_swap(replacement, target)
    _fsync_directory(replacement.parent)
    if target.parent != replacement.parent:
        _fsync_directory(target.parent)
    try:
        displaced = _regular_file_fingerprint(replacement)
    except RuntimeError:
        displaced = None
    expected_displaced = {**expected_manifest, "path": str(replacement)}
    if displaced != expected_displaced:
        try:
            published = _regular_file_fingerprint(target)
            expected_published = {**replacement_fingerprint, "path": str(target)}
            if published != expected_published:
                raise RuntimeError(
                    "manifest publication target changed; displaced file was preserved"
                )
            _rename_swap(replacement, target)
            _fsync_directory(replacement.parent)
            if target.parent != replacement.parent:
                _fsync_directory(target.parent)
            _remove_owned_file(
                replacement,
                (
                    replacement_fingerprint["dev"],
                    replacement_fingerprint["ino"],
                ),
                replacement_fingerprint["sha256"],
            )
        except BaseException as exc:
            raise RuntimeError(
                "installed manifest changed during atomic publication; files were preserved"
            ) from exc
        raise RuntimeError(
            "installed manifest identity or hash changed during atomic publication"
        )
    try:
        published = _regular_file_fingerprint(target)
    except RuntimeError:
        published = None
    expected_published = {**replacement_fingerprint, "path": str(target)}
    if published != expected_published:
        _rename_exclusive(replacement, previous_backup)
        _fsync_directory(target.parent)
        raise RuntimeError(
            "installed manifest changed after atomic publication; previous manifest preserved"
        )
    _rename_exclusive(replacement, previous_backup)
    _fsync_directory(target.parent)
    preserved = _regular_file_fingerprint(previous_backup)
    if preserved != {**expected_manifest, "path": str(previous_backup)}:
        raise RuntimeError("previous manifest backup identity changed during publication")
    final_published = _regular_file_fingerprint(target)
    if final_published != expected_published:
        raise RuntimeError(
            "installed manifest target changed after previous backup publication"
        )


def _relocate_staged_venv(staged_venv: Path, target_venv: Path) -> None:
    """Rewrite venv-generated absolute paths before the atomic directory rename."""
    staged_prefix = os.fsencode(staged_venv)
    target_prefix = os.fsencode(target_venv)
    candidates = [staged_venv / "pyvenv.cfg"]
    bin_dir = staged_venv / "bin"
    if bin_dir.is_symlink() or not bin_dir.is_dir():
        raise RuntimeError("staged venv bin directory is missing or unsafe")
    candidates.extend(sorted(bin_dir.iterdir()))
    for candidate in candidates:
        if candidate.is_symlink() or not candidate.is_file():
            continue
        content = candidate.read_bytes()
        if staged_prefix not in content:
            continue
        mode = stat.S_IMODE(candidate.stat(follow_symlinks=False).st_mode)
        fd, temporary_raw = tempfile.mkstemp(
            prefix=f".{candidate.name}.relocate-",
            dir=candidate.parent,
        )
        temporary = Path(temporary_raw)
        temporary_details = os.fstat(fd)
        temporary_identity = (temporary_details.st_dev, temporary_details.st_ino)
        try:
            os.fchmod(fd, mode)
            view = memoryview(content.replace(staged_prefix, target_prefix))
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, candidate)
        except BaseException:
            if temporary.exists() or temporary.is_symlink():
                _remove_owned_file(temporary, temporary_identity)
            raise
    for candidate in candidates:
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if staged_prefix in candidate.read_bytes():
            raise RuntimeError(f"staged venv path remains in {candidate.name}")
    _fsync_directory(bin_dir)
    _fsync_directory(staged_venv)


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
    destination_identity: tuple[int, int] | None = None
    digest = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise RuntimeError("macOS native helper source is not a regular file")
        destination_fd = os.open(destination, destination_flags, 0o400)
        destination_details = os.fstat(destination_fd)
        destination_identity = (
            destination_details.st_dev,
            destination_details.st_ino,
        )
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
        if destination.exists() or destination.is_symlink():
            if destination_identity is None:
                raise RuntimeError("native helper source staging identity is missing")
            _remove_owned_file(
                destination,
                destination_identity,
                digest.hexdigest(),
            )
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
    if "dev" in metadata or "ino" in metadata:
        recorded_identity = _manifest_native_helper_identity(manifest, helper)
        if recorded_identity is None or _file_identity(helper) != recorded_identity[:2]:
            raise RuntimeError("existing native helper ownership identity does not match")
    return actual_hash


def _directory_identity(path: Path) -> tuple[int, int]:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"owned directory is missing or unsafe: {path}")
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(details.st_mode):
        raise RuntimeError(f"owned directory is missing or unsafe: {path}")
    return details.st_dev, details.st_ino


def _file_identity(path: Path) -> tuple[int, int]:
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"owned file is missing or unsafe: {path}")
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise RuntimeError(f"owned file is missing or unsafe: {path}")
    return details.st_dev, details.st_ino


def _identity_record(path: Path) -> dict[str, Any]:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"owned resource is missing or unsafe: {path}") from exc
    if stat.S_ISDIR(details.st_mode):
        kind = "directory"
    elif stat.S_ISREG(details.st_mode):
        kind = "file"
    elif stat.S_ISLNK(details.st_mode):
        kind = "symlink"
    else:
        raise RuntimeError(f"owned resource has an unsupported type: {path}")
    return {"kind": kind, "dev": details.st_dev, "ino": details.st_ino}


def _same_identity(details: os.stat_result, expected: tuple[int, int]) -> bool:
    return (details.st_dev, details.st_ino) == expected


def _open_parent_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path.parent, flags)
    except OSError as exc:
        raise RuntimeError(f"owned resource parent is missing or unsafe: {path}") from exc


def _deletion_quarantine_name(name: str, identity: tuple[int, int]) -> str:
    return (
        f".{name}.delete-{identity[0]:x}-{identity[1]:x}-"
        f"{secrets.token_hex(16)}"
    )


def _restore_relative_quarantine(
    directory_fd: int,
    quarantine: str,
    original: str,
    label: str,
) -> None:
    try:
        _renameatx_relative(
            directory_fd,
            quarantine,
            directory_fd,
            original,
            RENAME_EXCL,
        )
    except FileExistsError as exc:
        raise RuntimeError(
            f"{label} changed during deletion; preserved as {quarantine}"
        ) from exc


def _remove_directory_contents_fd(directory_fd: int, root_dev: int) -> None:
    with os.scandir(directory_fd) as entries:
        entry_list = list(entries)
    for entry in entry_list:
        name = entry.name
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(f"owned directory entry changed before deletion: {name}") from exc
        identity = (before.st_dev, before.st_ino)
        if before.st_dev != root_dev:
            raise RuntimeError(
                f"owned directory entry crosses a device boundary: {name}"
            )
        quarantine = _deletion_quarantine_name(name, identity)
        try:
            os.stat(quarantine, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError(
                f"owned directory deletion quarantine already exists: {quarantine}"
            )
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_IFMT(current.st_mode) != stat.S_IFMT(before.st_mode) or not _same_identity(
            current, identity
        ):
            raise RuntimeError(
                f"owned directory entry identity changed before deletion: {name}"
            )
        _renameatx_relative(
            directory_fd,
            name,
            directory_fd,
            quarantine,
            RENAME_EXCL,
        )
        moved = os.stat(quarantine, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_IFMT(moved.st_mode) != stat.S_IFMT(before.st_mode) or not _same_identity(
            moved, identity
        ):
            _restore_relative_quarantine(
                directory_fd,
                quarantine,
                name,
                "owned directory entry",
            )
            raise RuntimeError(
                f"owned directory entry identity changed during deletion: {name}"
            )
        if stat.S_ISDIR(before.st_mode):
            flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                child_fd = os.open(quarantine, flags, dir_fd=directory_fd)
            except OSError as exc:
                _restore_relative_quarantine(
                    directory_fd,
                    quarantine,
                    name,
                    "owned directory entry",
                )
                raise RuntimeError(
                    f"owned directory entry changed before deletion: {name}"
                ) from exc
            try:
                opened = os.fstat(child_fd)
                if not stat.S_ISDIR(opened.st_mode) or not _same_identity(opened, identity):
                    raise RuntimeError(
                        f"owned directory entry identity changed before deletion: {name}"
                    )
                _remove_directory_contents_fd(child_fd, root_dev)
                current = os.stat(
                    quarantine,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not stat.S_ISDIR(current.st_mode) or not _same_identity(
                    current, identity
                ):
                    raise RuntimeError(
                        f"owned directory entry identity changed before deletion: {name}"
                    )
                os.rmdir(quarantine, dir_fd=directory_fd)
            except BaseException:
                try:
                    _restore_relative_quarantine(
                        directory_fd,
                        quarantine,
                        name,
                        "owned directory entry",
                    )
                except BaseException:
                    pass
                raise
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            if stat.S_ISLNK(before.st_mode):
                flags = os.O_RDONLY | getattr(os, "O_SYMLINK", 0)
            entry_fd = os.open(quarantine, flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(entry_fd)
                if (
                    stat.S_IFMT(opened.st_mode) != stat.S_IFMT(before.st_mode)
                    or not _same_identity(opened, identity)
                ):
                    raise RuntimeError(
                        f"owned directory entry identity changed before cleanup: {name}"
                    )
                os.unlink(quarantine, dir_fd=directory_fd)
            finally:
                os.close(entry_fd)
        else:
            raise RuntimeError(
                f"owned directory entry has an unsupported type: {name}"
            )


def _remove_owned_directory(path: Path, expected_identity: tuple[int, int]) -> None:
    parent_fd = _open_parent_directory(path)
    directory_fd: int | None = None
    quarantine = _deletion_quarantine_name(path.name, expected_identity)
    quarantined = False
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            directory_fd = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise RuntimeError(
                f"owned directory identity changed before deletion: {path}"
            ) from exc
        opened = os.fstat(directory_fd)
        if not stat.S_ISDIR(opened.st_mode) or not _same_identity(
            opened, expected_identity
        ):
            raise RuntimeError(f"owned directory identity changed before deletion: {path}")
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or not _same_identity(
            current, expected_identity
        ):
            raise RuntimeError(f"owned directory identity changed before deletion: {path}")
        os.close(directory_fd)
        directory_fd = None
        _renameatx_relative(
            parent_fd,
            path.name,
            parent_fd,
            quarantine,
            RENAME_EXCL,
        )
        quarantined = True
        moved = os.stat(quarantine, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(moved.st_mode) or not _same_identity(
            moved, expected_identity
        ):
            _restore_relative_quarantine(
                parent_fd,
                quarantine,
                path.name,
                "owned directory",
            )
            quarantined = False
            raise RuntimeError(f"owned directory identity changed during deletion: {path}")
        directory_fd = os.open(quarantine, flags, dir_fd=parent_fd)
        reopened = os.fstat(directory_fd)
        if not stat.S_ISDIR(reopened.st_mode) or not _same_identity(
            reopened,
            expected_identity,
        ):
            raise RuntimeError(
                f"owned directory identity changed after quarantine reopen: {path}"
            )
        _remove_directory_contents_fd(directory_fd, expected_identity[0])
        os.rmdir(quarantine, dir_fd=parent_fd)
        os.close(directory_fd)
        directory_fd = None
        quarantined = False
    except BaseException:
        if quarantined:
            try:
                _restore_relative_quarantine(
                    parent_fd,
                    quarantine,
                    path.name,
                    "owned directory",
                )
            except BaseException:
                pass
        raise
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)


def _remove_owned_file(
    path: Path,
    expected_identity: tuple[int, int],
    expected_hash: str | None = None,
) -> None:
    parent_fd = _open_parent_directory(path)
    file_fd: int | None = None
    quarantine = _deletion_quarantine_name(path.name, expected_identity)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            file_fd = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise RuntimeError(f"owned file identity changed before deletion: {path}") from exc
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode) or not _same_identity(opened, expected_identity):
            raise RuntimeError(f"owned file identity changed before deletion: {path}")
        if expected_hash is not None and _sha256_fd(file_fd) != expected_hash:
            raise RuntimeError(f"owned file hash changed before deletion: {path}")
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or not _same_identity(
            current, expected_identity
        ):
            raise RuntimeError(f"owned file identity changed before deletion: {path}")
        os.close(file_fd)
        file_fd = None
        _renameatx_relative(
            parent_fd,
            path.name,
            parent_fd,
            quarantine,
            RENAME_EXCL,
        )
        moved_fd = os.open(
            quarantine,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            moved = os.fstat(moved_fd)
            moved_hash = _sha256_fd(moved_fd) if expected_hash is not None else None
            if (
                not stat.S_ISREG(moved.st_mode)
                or not _same_identity(moved, expected_identity)
                or (expected_hash is not None and moved_hash != expected_hash)
            ):
                _restore_relative_quarantine(
                    parent_fd,
                    quarantine,
                    path.name,
                    "owned file",
                )
                raise RuntimeError(f"owned file identity changed during deletion: {path}")
            os.unlink(quarantine, dir_fd=parent_fd)
        finally:
            os.close(moved_fd)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def _remove_owned_entry(path: Path, identity: dict[str, Any]) -> None:
    if (
        not isinstance(identity, dict)
        or type(identity.get("dev")) is not int
        or type(identity.get("ino")) is not int
        or identity.get("kind") not in {"directory", "file", "symlink"}
    ):
        raise RuntimeError(f"owned resource identity is missing: {path}")
    expected = (identity["dev"], identity["ino"])
    if identity["kind"] == "directory":
        _remove_owned_directory(path, expected)
        return
    if identity["kind"] == "file":
        _remove_owned_file(path, expected)
        return
    parent_fd = _open_parent_directory(path)
    try:
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISLNK(current.st_mode) or not _same_identity(current, expected):
            raise RuntimeError(f"owned symlink identity changed before deletion: {path}")
        quarantine = _deletion_quarantine_name(path.name, expected)
        _renameatx_relative(
            parent_fd,
            path.name,
            parent_fd,
            quarantine,
            RENAME_EXCL,
        )
        moved = os.stat(quarantine, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISLNK(moved.st_mode) or not _same_identity(moved, expected):
            _restore_relative_quarantine(
                parent_fd,
                quarantine,
                path.name,
                "owned symlink",
            )
            raise RuntimeError(f"owned symlink identity changed during deletion: {path}")
        symlink_fd = os.open(
            quarantine,
            os.O_RDONLY | getattr(os, "O_SYMLINK", 0),
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(symlink_fd)
            if not stat.S_ISLNK(opened.st_mode) or not _same_identity(opened, expected):
                raise RuntimeError(
                    f"owned symlink identity changed before cleanup: {path}"
                )
            os.unlink(quarantine, dir_fd=parent_fd)
        finally:
            os.close(symlink_fd)
    finally:
        os.close(parent_fd)


def _manifest_native_helper_identity(
    manifest: dict[str, Any] | None,
    helper: Path,
) -> tuple[int, int, str] | None:
    if not manifest or "native_helper" not in manifest:
        return None
    metadata = manifest.get("native_helper")
    if not isinstance(metadata, dict) or metadata.get("path") != str(helper):
        raise RuntimeError("native helper ownership metadata is invalid")
    if type(metadata.get("dev")) is not int or type(metadata.get("ino")) is not int:
        raise RuntimeError("native helper ownership metadata is missing or invalid")
    expected_hash = metadata.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise RuntimeError("native helper ownership metadata is invalid")
    return metadata["dev"], metadata["ino"], expected_hash


def _owned_venv_identity_for_replacement(venv: Path) -> tuple[int, int]:
    manifest = _load_owned_manifest()
    resources = (manifest or {}).get("resources")
    if not isinstance(resources, list) or str(venv) not in resources:
        raise RuntimeError("existing venv is not owned by Cortex Bridge")
    actual_identity = _directory_identity(venv)
    recorded_identity = _manifest_venv_identity(manifest, venv)
    if recorded_identity is not None and actual_identity != recorded_identity:
        raise RuntimeError("venv ownership identity does not match the installed manifest")
    return actual_identity


def _ensure_private_directory(path: Path) -> bool:
    return ensure_private_directory(path)


@contextmanager
def _exclusive_install_lock(home: Path):
    fd = _open_lifecycle_lock(home)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _open_lifecycle_lock(home: Path) -> int:
    return open_lifecycle_lock(home / ".install.lock")


@contextmanager
def _shared_install_lock_if_present(home: Path):
    fd = _open_lifecycle_lock(home)
    try:
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
    payload.setdefault("replaces_venv", False)
    payload.setdefault("venv", None)
    if (
        payload.get("schema_version") != 1
        or payload.get("owner") != "cortex-bridge"
        or payload.get("home") != str(home)
        or not isinstance(payload.get("plan_hash"), str)
        or not isinstance(payload.get("creates_venv"), bool)
        or not isinstance(payload.get("replaces_venv"), bool)
        or (payload["creates_venv"] and payload["replaces_venv"])
    ):
        raise RuntimeError("installer recovery journal is invalid")
    if payload["replaces_venv"]:
        venv_state = payload.get("venv")
        if isinstance(venv_state, dict):
            venv_state.setdefault("preserves_previous", False)
            venv_state.setdefault("preserved", None)
        if (
            not isinstance(venv_state, dict)
            or venv_state.get("target") != str(home / "venv")
            or type(venv_state.get("previous_dev")) is not int
            or type(venv_state.get("previous_ino")) is not int
            or (
                venv_state.get("new_dev") is not None
                and type(venv_state.get("new_dev")) is not int
            )
            or (
                venv_state.get("new_ino") is not None
                and type(venv_state.get("new_ino")) is not int
            )
            or not isinstance(venv_state.get("preserves_previous"), bool)
        ):
            raise RuntimeError("installer recovery venv metadata is invalid")
        if venv_state["preserves_previous"]:
            expected_preserved = _legacy_preservation_path(
                "venv",
                (venv_state["previous_dev"], venv_state["previous_ino"]),
            )
            if venv_state.get("preserved") != str(expected_preserved):
                raise RuntimeError("installer recovery venv preservation is invalid")
        elif venv_state.get("preserved") is not None:
            raise RuntimeError("installer recovery venv preservation is invalid")
    elif payload["creates_venv"] and payload.get("venv") is not None:
        venv_state = payload["venv"]
        if (
            not isinstance(venv_state, dict)
            or venv_state.get("target") != str(home / "venv")
            or type(venv_state.get("new_dev")) is not int
            or type(venv_state.get("new_ino")) is not int
        ):
            raise RuntimeError("installer recovery fresh venv metadata is invalid")
    helper_state = payload.get("helper")
    if isinstance(helper_state, dict):
        helper_state.setdefault("preserves_previous", False)
        helper_state.setdefault("preserved", None)
        helper_state.setdefault("previous_dev", None)
        helper_state.setdefault("previous_ino", None)
        helper_state.setdefault("new_dev", None)
        helper_state.setdefault("new_ino", None)
        if not isinstance(helper_state["preserves_previous"], bool):
            raise RuntimeError("installer recovery helper preservation is invalid")
        if helper_state["preserves_previous"]:
            if (
                type(helper_state.get("previous_dev")) is not int
                or type(helper_state.get("previous_ino")) is not int
            ):
                raise RuntimeError("installer recovery helper preservation is invalid")
            expected_preserved = _legacy_preservation_path(
                MACOS_AX_HELPER_NAME,
                (helper_state["previous_dev"], helper_state["previous_ino"]),
            )
            if helper_state.get("preserved") != str(expected_preserved):
                raise RuntimeError("installer recovery helper preservation is invalid")
        elif helper_state.get("preserved") is not None:
            raise RuntimeError("installer recovery helper preservation is invalid")
    return payload


def _cleanup_staging(staging: Path) -> None:
    staging_identity = _directory_identity(staging)
    journal = staging / TRANSACTION_NAME
    for child in list(staging.iterdir()):
        if child == journal:
            continue
        child_identity = _identity_record(child)
        if child_identity["dev"] != staging_identity[0]:
            raise RuntimeError(
                f"installer staging entry crosses a device boundary: {child}"
            )
        _remove_owned_entry(child, child_identity)
    if journal.exists() or journal.is_symlink():
        journal_identity = _file_identity(journal)
        if journal_identity[0] != staging_identity[0]:
            raise RuntimeError(
                f"installer staging journal crosses a device boundary: {journal}"
            )
        _remove_owned_file(
            journal,
            journal_identity,
            _regular_file_hash(journal),
        )
    _remove_owned_directory(staging, staging_identity)


def _transaction_committed(transaction: dict[str, Any], home: Path) -> bool:
    manifest = _load_owned_manifest()
    if not manifest or manifest.get("plan_hash") != transaction["plan_hash"]:
        return False
    resources = manifest.get("resources")
    if not isinstance(resources, list):
        return False
    if (
        transaction["creates_venv"] or transaction.get("replaces_venv", False)
    ) and str(home / "venv") not in resources:
        return False
    if transaction.get("replaces_venv", False):
        venv_state = transaction.get("venv")
        if not isinstance(venv_state, dict):
            return False
        try:
            target_identity = _directory_identity(home / "venv")
        except RuntimeError:
            return False
        if target_identity != (
            venv_state.get("new_dev"),
            venv_state.get("new_ino"),
        ):
            return False
    elif transaction["creates_venv"] and isinstance(transaction.get("venv"), dict):
        venv_state = transaction["venv"]
        try:
            target_identity = _directory_identity(home / "venv")
        except RuntimeError:
            return False
        if target_identity != (venv_state.get("new_dev"), venv_state.get("new_ino")):
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
        and type(metadata.get("dev")) is int
        and type(metadata.get("ino")) is int
        and str(target) in resources
        and _regular_file_hash(target) == new_hash
        and _file_identity(target) == (metadata["dev"], metadata["ino"])
        and (
            helper_state.get("new_dev") is None
            or _file_identity(target)
            == (helper_state.get("new_dev"), helper_state.get("new_ino"))
        )
    )


def _recover_interrupted_install(home: Path) -> None:
    staging = home / STAGING_NAME
    if not staging.exists() and not staging.is_symlink():
        return
    if staging.is_symlink() or not staging.is_dir():
        raise RuntimeError(f"owned staging path is unsafe: {staging}")
    entries = list(staging.iterdir())
    if not entries:
        _cleanup_staging(staging)
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
        preserves_previous = helper_state.get("preserves_previous", False)
        preserved_helper = (
            Path(str(helper_state.get("preserved"))) if preserves_previous else None
        )
        if preserves_previous:
            previous_identity = (
                helper_state.get("previous_dev"),
                helper_state.get("previous_ino"),
            )
            new_identity = (
                helper_state.get("new_dev"),
                helper_state.get("new_ino"),
            )
            expected_preserved = _legacy_preservation_path(
                MACOS_AX_HELPER_NAME,
                previous_identity,
            )
            if (
                not helper_state["previous_exists"]
                or type(previous_identity[0]) is not int
                or type(previous_identity[1]) is not int
                or not isinstance(previous_hash, str)
                or preserved_helper != expected_preserved
            ):
                raise RuntimeError("installer recovery helper preservation is invalid")
            try:
                target_identity = _file_identity(target)
            except RuntimeError:
                target_identity = None
            try:
                backup_identity = _file_identity(backup)
            except RuntimeError:
                backup_identity = None
            try:
                preserved_identity = _file_identity(preserved_helper)
            except RuntimeError:
                preserved_identity = None
            if new_identity[0] is None or new_identity[1] is None:
                if target_identity != previous_identity or preserved_identity is not None:
                    raise RuntimeError(
                        "installer recovery cannot identify the previous legacy helper"
                    )
            elif target_identity == previous_identity and backup_identity == new_identity:
                if preserved_identity is not None:
                    raise RuntimeError(
                        "installer recovery found an unexpected preserved helper"
                    )
            elif target_identity == new_identity and backup_identity == previous_identity:
                _rename_swap(backup, target)
                _fsync_directory(target.parent)
                if (
                    _file_identity(target) != previous_identity
                    or _file_identity(backup) != new_identity
                ):
                    raise RuntimeError(
                        "installer recovery helper rollback identity mismatch"
                    )
            elif (
                target_identity == new_identity
                and backup_identity is None
                and preserved_identity == previous_identity
            ):
                _rename_swap(preserved_helper, target)
                _fsync_directory(target.parent)
                if (
                    _file_identity(target) != previous_identity
                    or _file_identity(preserved_helper) != new_identity
                ):
                    raise RuntimeError(
                        "installer recovery preserved helper rollback identity mismatch"
                    )
                _rename_exclusive(preserved_helper, backup)
                _fsync_directory(staging)
                _fsync_directory(target.parent)
            else:
                raise RuntimeError("installer recovery found unknown legacy helper files")
        elif helper_state["previous_exists"]:
            if not isinstance(previous_hash, str):
                raise RuntimeError("installer recovery previous helper hash is invalid")
            previous_identity = (
                helper_state.get("previous_dev"),
                helper_state.get("previous_ino"),
            )
            new_identity = (
                helper_state.get("new_dev"),
                helper_state.get("new_ino"),
            )
            has_previous_identity = all(type(value) is int for value in previous_identity)
            has_new_identity = all(type(value) is int for value in new_identity)
            if current_hash != previous_hash:
                if _regular_file_hash(backup) != previous_hash:
                    raise RuntimeError(
                        "installer recovery cannot identify the previous native helper"
                    )
                if has_previous_identity and _file_identity(backup) != previous_identity:
                    raise RuntimeError(
                        "installer recovery previous helper identity does not match"
                    )
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise RuntimeError("installer recovery target is unsafe")
                if target.exists():
                    if not isinstance(new_hash, str) or current_hash != new_hash:
                        raise RuntimeError("installer recovery found an unknown native helper")
                    if has_new_identity and _file_identity(target) != new_identity:
                        raise RuntimeError(
                            "installer recovery new helper identity does not match"
                        )
                    _rename_swap(backup, target)
                    if (
                        _regular_file_hash(backup) != new_hash
                        or (has_new_identity and _file_identity(backup) != new_identity)
                    ):
                        _rename_swap(backup, target)
                        raise RuntimeError("installer recovery swap displaced an unknown file")
                else:
                    _rename_exclusive(backup, target)
                _fsync_directory(target.parent)
        elif target.exists() or target.is_symlink():
            if not isinstance(new_hash, str) or current_hash != new_hash:
                raise RuntimeError("installer recovery found an unknown native helper")
            new_identity = (
                helper_state.get("new_dev"),
                helper_state.get("new_ino"),
            )
            has_new_identity = all(type(value) is int for value in new_identity)
            if has_new_identity and _file_identity(target) != new_identity:
                raise RuntimeError("installer recovery new helper identity does not match")
            rollback_slot = staging / f".{MACOS_AX_HELPER_NAME}.rollback"
            _rename_exclusive(target, rollback_slot)
            if (
                _regular_file_hash(rollback_slot) != new_hash
                or (has_new_identity and _file_identity(rollback_slot) != new_identity)
            ):
                _rename_exclusive(rollback_slot, target)
                raise RuntimeError("installer recovery moved an unknown native helper")
            _remove_owned_file(
                rollback_slot,
                _file_identity(rollback_slot),
                new_hash,
            )
            _fsync_directory(target.parent)

    if transaction.get("replaces_venv", False):
        staged_venv = staging / "venv"
        target_venv = home / "venv"
        venv_state = transaction["venv"]
        previous_identity = (
            venv_state["previous_dev"],
            venv_state["previous_ino"],
        )
        new_identity = (venv_state.get("new_dev"), venv_state.get("new_ino"))
        preserves_previous = venv_state.get("preserves_previous", False)
        preserved_venv = (
            Path(venv_state["preserved"]) if preserves_previous else None
        )
        if new_identity[0] is None or new_identity[1] is None:
            if _directory_identity(target_venv) != previous_identity:
                raise RuntimeError("installer recovery cannot identify the previous venv")
        else:
            target_identity = _directory_identity(target_venv)
            try:
                staged_identity = _directory_identity(staged_venv)
            except RuntimeError:
                staged_identity = None
            try:
                preserved_identity = (
                    _directory_identity(preserved_venv)
                    if preserved_venv is not None
                    else None
                )
            except RuntimeError:
                preserved_identity = None
            if target_identity == previous_identity and staged_identity == new_identity:
                pass
            elif target_identity == new_identity and staged_identity == previous_identity:
                _rename_swap(staged_venv, target_venv)
                _fsync_directory(staging)
                _fsync_directory(home)
                if (
                    _directory_identity(target_venv) != previous_identity
                    or _directory_identity(staged_venv) != new_identity
                ):
                    raise RuntimeError("installer recovery venv rollback identity mismatch")
            elif (
                preserves_previous
                and preserved_venv is not None
                and target_identity == new_identity
                and staged_identity is None
                and preserved_identity == previous_identity
            ):
                _rename_swap(preserved_venv, target_venv)
                _fsync_directory(home)
                if (
                    _directory_identity(target_venv) != previous_identity
                    or _directory_identity(preserved_venv) != new_identity
                ):
                    raise RuntimeError(
                        "installer recovery preserved venv rollback identity mismatch"
                    )
                _rename_exclusive(preserved_venv, staged_venv)
                _fsync_directory(staging)
                _fsync_directory(home)
            else:
                raise RuntimeError("installer recovery found unknown venv directories")
    elif transaction["creates_venv"]:
        staged_venv = staging / "venv"
        target_venv = home / "venv"
        if not staged_venv.exists() and target_venv.exists():
            venv_state = transaction.get("venv")
            if not isinstance(venv_state, dict):
                raise RuntimeError(
                    "installer recovery cannot identify the published fresh venv"
                )
            expected_identity = (venv_state.get("new_dev"), venv_state.get("new_ino"))
            try:
                actual_identity = _directory_identity(target_venv)
            except RuntimeError as exc:
                raise RuntimeError(
                    "installer recovery fresh venv identity is unsafe"
                ) from exc
            if actual_identity != expected_identity:
                raise RuntimeError(
                    "installer recovery fresh venv identity does not match"
                )
            _remove_owned_directory(target_venv, expected_identity)
    _cleanup_staging(staging)


def apply_install(plan: dict[str, Any], approved_hash: str) -> dict[str, Any]:
    if approved_hash != plan["plan_hash"]:
        raise PermissionError("approved plan hash does not match the current plan")
    paths = build_paths()
    with _exclusive_install_lock(paths.home):
        _recover_interrupted_install(paths.home)
        metadata_migration = plan.get("metadata_migration")
        approved_manifest_snapshot = plan.get("manifest_snapshot")
        migrated_manifest: dict[str, Any] | None = None
        expected_manifest_snapshot: dict[str, Any] | None = None
        if metadata_migration is not None:
            if not isinstance(metadata_migration, dict):
                raise RuntimeError("install plan metadata migration is invalid")
            migrated_manifest, expected_manifest_snapshot = _validated_metadata_migration(
                metadata_migration
            )
            if approved_manifest_snapshot != expected_manifest_snapshot:
                raise RuntimeError("install plan manifest snapshot is inconsistent")
        elif approved_manifest_snapshot is not None:
            if (
                not isinstance(approved_manifest_snapshot, dict)
                or set(approved_manifest_snapshot) != {"path", "dev", "ino", "sha256"}
            ):
                raise RuntimeError("install plan manifest snapshot is invalid")
            try:
                _, actual_manifest_snapshot = _owned_manifest_snapshot()
            except RuntimeError as exc:
                raise RuntimeError(
                    "installed manifest identity or hash changed after plan approval"
                ) from exc
            if actual_manifest_snapshot != approved_manifest_snapshot:
                raise RuntimeError(
                    "installed manifest identity or hash changed after plan approval"
                )
            expected_manifest_snapshot = approved_manifest_snapshot
        if not plan["commands"]:
            if migrated_manifest is not None and expected_manifest_snapshot is not None:
                _write_migrated_manifest(
                    migrated_manifest,
                    expected_manifest_snapshot,
                )
                return {
                    "schema_version": 1,
                    "status": "metadata_migrated",
                    "plan_hash": approved_hash,
                    "manifest": str(_owned_manifest_path()),
                }
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
        has_venv_commands = any(
            command["id"] == "create_venv" for command in plan["commands"]
        )
        venv_action = plan.get("venv_action")
        if venv_action not in {"create", "repair", "rebuild_legacy", "none"}:
            raise RuntimeError("install plan has an invalid venv action")
        if has_venv_commands != (
            venv_action in {"create", "repair", "rebuild_legacy"}
        ):
            raise RuntimeError("install plan venv commands do not match its action")
        creates_venv = venv_action == "create"
        replaces_venv = venv_action in {"repair", "rebuild_legacy"}
        preserves_legacy_venv = venv_action == "rebuild_legacy"
        staged_venv = staging / "venv"
        target_venv = paths.home / "venv"
        if creates_venv and (target_venv.exists() or target_venv.is_symlink()):
            raise RuntimeError("target venv already exists and is not owned by this plan")
        previous_venv_identity: tuple[int, int] | None = None
        if replaces_venv:
            if preserves_legacy_venv:
                migration_venv = (metadata_migration or {}).get("venv")
                if (
                    not isinstance(migration_venv, dict)
                    or migration_venv.get("action") != "rebuild_preserve"
                ):
                    raise RuntimeError("legacy venv reconstruction metadata is missing")
                previous_venv_identity = (
                    migration_venv["dev"],
                    migration_venv["ino"],
                )
            else:
                previous_venv_identity = _owned_venv_identity_for_replacement(target_venv)

        install_dir = paths.home / "install"
        if install_dir.is_symlink() or (install_dir.exists() and not install_dir.is_dir()):
            raise RuntimeError(f"install manifest directory is unsafe: {install_dir}")
        helper_dir = helper_target.parent
        if helper_dir.is_symlink() or (helper_dir.exists() and not helper_dir.is_dir()):
            raise RuntimeError(f"native helper directory is unsafe: {helper_dir}")

        previous_helper_exists = helper_target.exists() or helper_target.is_symlink()
        previous_helper_hash: str | None = None
        previous_helper_identity: tuple[int, int] | None = None
        migration_helper = (metadata_migration or {}).get("native_helper")
        preserves_legacy_helper = (
            isinstance(migration_helper, dict)
            and migration_helper.get("action") == "rebuild_preserve"
        )
        helper_preserved_unowned = (
            isinstance(migration_helper, dict)
            and migration_helper.get("action") == "preserve_unowned"
        )
        if preserves_legacy_helper and compile_command is None:
            raise RuntimeError("legacy helper reconstruction command is missing")
        if compile_command is not None and previous_helper_exists:
            if preserves_legacy_helper:
                previous_helper_hash = migration_helper["sha256"]
                previous_helper_identity = (
                    migration_helper["dev"],
                    migration_helper["ino"],
                )
                if (
                    _file_identity(helper_target) != previous_helper_identity
                    or _regular_file_hash(helper_target) != previous_helper_hash
                ):
                    raise RuntimeError("legacy helper changed before reconstruction")
            else:
                previous_helper_hash = _owned_helper_hash_for_replacement(helper_target)
                previous_helper_identity = _file_identity(helper_target)

        staging.mkdir(mode=0o700, parents=True)
        transaction: dict[str, Any] = {
            "schema_version": 1,
            "owner": "cortex-bridge",
            "home": str(paths.home),
            "plan_hash": approved_hash,
            "creates_venv": creates_venv,
            "replaces_venv": replaces_venv,
            "venv": None,
            "helper": None,
        }
        if replaces_venv:
            transaction["venv"] = {
                "target": str(target_venv),
                "previous_dev": previous_venv_identity[0],
                "previous_ino": previous_venv_identity[1],
                "new_dev": None,
                "new_ino": None,
                "preserves_previous": preserves_legacy_venv,
                "preserved": (
                    migration_venv.get("preserve_path")
                    if preserves_legacy_venv
                    else None
                ),
            }
        if compile_command is not None:
            transaction["helper"] = {
                "target": str(helper_target),
                "backup": str(helper_backup),
                "previous_exists": previous_helper_exists,
                "previous_sha256": previous_helper_hash,
                "previous_dev": (
                    previous_helper_identity[0]
                    if previous_helper_identity is not None
                    else None
                ),
                "previous_ino": (
                    previous_helper_identity[1]
                    if previous_helper_identity is not None
                    else None
                ),
                "new_sha256": None,
                "new_dev": None,
                "new_ino": None,
                "preserves_previous": preserves_legacy_helper,
                "preserved": (
                    migration_helper.get("preserve_path")
                    if preserves_legacy_helper
                    else None
                ),
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

            if creates_venv or replaces_venv:
                if staged_venv.is_symlink() or not staged_venv.is_dir():
                    raise RuntimeError("venv command did not produce the staged venv")
                if creates_venv and (target_venv.exists() or target_venv.is_symlink()):
                    raise RuntimeError("target venv appeared during installation")
                if replaces_venv and (
                    _directory_identity(target_venv) != previous_venv_identity
                ):
                    raise RuntimeError("owned venv changed during repair")
                _relocate_staged_venv(staged_venv, target_venv)
                new_venv_identity = _directory_identity(staged_venv)
                if creates_venv:
                    transaction["venv"] = {
                        "target": str(target_venv),
                        "new_dev": new_venv_identity[0],
                        "new_ino": new_venv_identity[1],
                    }
                    _durable_json_write(staging / TRANSACTION_NAME, transaction)
                elif replaces_venv:
                    transaction["venv"]["new_dev"] = new_venv_identity[0]
                    transaction["venv"]["new_ino"] = new_venv_identity[1]
                    _durable_json_write(staging / TRANSACTION_NAME, transaction)

            new_helper_hash: str | None = None
            new_helper_identity: tuple[int, int] | None = None
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
                new_helper_identity = _file_identity(helper_staged)
                transaction["helper"]["new_sha256"] = new_helper_hash
                transaction["helper"]["new_dev"] = new_helper_identity[0]
                transaction["helper"]["new_ino"] = new_helper_identity[1]
                _durable_json_write(staging / TRANSACTION_NAME, transaction)

            if creates_venv:
                _rename_exclusive(staged_venv, target_venv)
                _fsync_directory(paths.home)
            elif replaces_venv:
                if _directory_identity(target_venv) != previous_venv_identity:
                    raise RuntimeError("owned venv changed before atomic repair publication")
                new_venv_identity = (
                    transaction["venv"]["new_dev"],
                    transaction["venv"]["new_ino"],
                )
                if _directory_identity(staged_venv) != new_venv_identity:
                    raise RuntimeError("staged repair venv changed before publication")
                _rename_swap(staged_venv, target_venv)
                _fsync_directory(staging)
                _fsync_directory(paths.home)
                if (
                    _directory_identity(target_venv) != new_venv_identity
                    or _directory_identity(staged_venv) != previous_venv_identity
                ):
                    raise RuntimeError("atomic venv repair identity mismatch")
                if preserves_legacy_venv:
                    preserved_venv = Path(migration_venv["preserve_path"])
                    _rename_exclusive(staged_venv, preserved_venv)
                    _fsync_directory(paths.home)

            if compile_command is not None:
                _ensure_private_directory(helper_target.parent)
                if helper_target.parent.is_symlink():
                    raise RuntimeError("native helper directory changed during installation")
                if previous_helper_exists:
                    _rename_swap(helper_staged, helper_target)
                    _fsync_directory(helper_target.parent)
                    if preserves_legacy_helper and (
                        _file_identity(helper_staged) != previous_helper_identity
                        or _regular_file_hash(helper_staged) != previous_helper_hash
                    ):
                        _rename_swap(helper_staged, helper_target)
                        _fsync_directory(helper_target.parent)
                        raise RuntimeError(
                            "legacy helper swap displaced an unexpected file"
                        )
                    if not preserves_legacy_helper and (
                        _file_identity(helper_staged) != previous_helper_identity
                        or _regular_file_hash(helper_staged) != previous_helper_hash
                    ):
                        _rename_swap(helper_staged, helper_target)
                        _fsync_directory(helper_target.parent)
                        raise RuntimeError(
                            "native helper swap displaced a file that is not owned"
                        )
                    if preserves_legacy_helper:
                        preserved_helper = Path(migration_helper["preserve_path"])
                        _rename_exclusive(helper_staged, preserved_helper)
                        _fsync_directory(preserved_helper.parent)
                else:
                    try:
                        _rename_exclusive(helper_staged, helper_target)
                    except FileExistsError as exc:
                        raise RuntimeError(
                            "unowned native helper appeared during installation"
                        ) from exc
                    _fsync_directory(helper_target.parent)
                if (
                    new_helper_identity is None
                    or _file_identity(helper_target) != new_helper_identity
                    or _regular_file_hash(helper_target) != new_helper_hash
                ):
                    raise RuntimeError(
                        "installed native helper identity or hash does not match staging"
                    )

            _ensure_private_directory(install_dir)
            resources = [str(target_venv), str(manifest_path)]
            native_helper: dict[str, str] | None = None
            if (
                sys.platform == "darwin"
                and not helper_preserved_unowned
                and helper_target.is_file()
                and not helper_target.is_symlink()
            ):
                if compile_command is not None:
                    binary_hash = str(new_helper_hash)
                    installed_source_hash = str(source_hash)
                else:
                    existing = (_load_owned_manifest() or {}).get("native_helper")
                    if not isinstance(existing, dict):
                        raise RuntimeError("installed native helper ownership metadata is missing")
                    binary_hash = str(existing.get("sha256", ""))
                    installed_source_hash = str(existing.get("source_sha256", ""))
                installed_helper_identity = _file_identity(helper_target)
                native_helper = {
                    "path": str(helper_target),
                    "sha256": binary_hash,
                    "source_sha256": installed_source_hash,
                    "dev": installed_helper_identity[0],
                    "ino": installed_helper_identity[1],
                }
                resources.append(str(helper_target))
            installed_venv_identity = _directory_identity(target_venv)
            manifest = dict(migrated_manifest or {})
            manifest.update({
                "schema_version": 1,
                "owner": "cortex-bridge",
                "version": current_version(),
                "plan_hash": approved_hash,
                "resources": resources,
                "venv": {
                    "path": str(target_venv),
                    "dev": installed_venv_identity[0],
                    "ino": installed_venv_identity[1],
                },
                "chrome_extension_path": str((ROOT / "chrome-extension").resolve()),
            })
            if native_helper is not None:
                manifest["native_helper"] = native_helper
                manifest.pop("preserved_unowned_helper", None)
            _durable_json_write(manifest_temporary, manifest)
            if expected_manifest_snapshot is not None:
                _publish_manifest_replacement(
                    manifest_temporary,
                    manifest_path,
                    expected_manifest_snapshot,
                )
            else:
                _rename_exclusive(manifest_temporary, manifest_path)
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
    manifest_resources = (manifest or {}).get("resources", [])
    venv = paths.home / "venv"
    venv_identity: dict[str, Any] | None = None
    helper = paths.home / "bin" / MACOS_AX_HELPER_NAME
    native_helper_identity: dict[str, Any] | None = None
    if (
        isinstance(manifest_resources, list)
        and str(venv) in manifest_resources
        and (venv.exists() or venv.is_symlink())
    ):
        recorded_identity = _manifest_venv_identity(manifest, venv)
        if recorded_identity is None:
            raise RuntimeError("venv ownership metadata is missing; refusing uninstall")
        actual_identity = _directory_identity(venv)
        if actual_identity != recorded_identity:
            raise RuntimeError("venv ownership identity does not match; refusing uninstall")
        venv_identity = {
            "path": str(venv),
            "dev": recorded_identity[0],
            "ino": recorded_identity[1],
        }
    if (
        isinstance(manifest_resources, list)
        and str(helper) in manifest_resources
        and (helper.exists() or helper.is_symlink())
    ):
        recorded_helper = _manifest_native_helper_identity(manifest, helper)
        if recorded_helper is None:
            raise RuntimeError(
                "native helper ownership metadata is missing; refusing uninstall"
            )
        try:
            actual_helper_identity = _file_identity(helper)
            actual_helper_hash = _sha256_file(helper)
        except (OSError, RuntimeError) as exc:
            raise RuntimeError(
                "native helper ownership identity is unsafe; refusing uninstall"
            ) from exc
        if (
            actual_helper_identity != recorded_helper[:2]
            or actual_helper_hash != recorded_helper[2]
        ):
            raise RuntimeError(
                "native helper ownership identity does not match; refusing uninstall"
            )
        native_helper_identity = {
            "path": str(helper),
            "dev": recorded_helper[0],
            "ino": recorded_helper[1],
            "sha256": recorded_helper[2],
        }
    resources: list[str] = []
    resource_identities: dict[str, dict[str, Any]] = {}
    for raw in manifest_resources:
        candidate = Path(os.path.abspath(os.path.expanduser(str(raw))))
        try:
            candidate.relative_to(paths.home)
        except ValueError:
            continue
        if candidate == paths.home:
            continue
        if candidate.exists() or candidate.is_symlink():
            resources.append(str(candidate))
            resource_identities[str(candidate)] = _identity_record(candidate)
    payload = {
        "schema_version": 1,
        "action": "uninstall",
        "version": current_version(),
        "target": str(paths.home),
        "resources": sorted(set(resources)),
        "resource_identities": resource_identities,
        "venv_identity": venv_identity,
        "native_helper_identity": native_helper_identity,
        "preserved": ["settings", "database", "runs", "attachments", "browser profile", "logs"],
    }
    return _hashed(payload)


def _restore_uninstall_quarantine(quarantine: Path, target: Path, label: str) -> None:
    try:
        _rename_exclusive(quarantine, target)
    except FileExistsError as exc:
        raise RuntimeError(
            f"{label} changed during uninstall; preserved at {quarantine}"
        ) from exc
    _fsync_directory(target.parent)


def _quarantine_owned_venv(
    target: Path,
    expected_identity: tuple[int, int],
) -> Path:
    quarantine = target.parent / ".venv.uninstall-quarantine"
    if quarantine.exists() or quarantine.is_symlink():
        raise RuntimeError(f"venv uninstall quarantine already exists: {quarantine}")
    _rename_exclusive(target, quarantine)
    _fsync_directory(target.parent)
    try:
        if _directory_identity(quarantine) != expected_identity:
            raise RuntimeError("venv ownership identity does not match; refusing uninstall")
    except BaseException as exc:
        try:
            _restore_uninstall_quarantine(quarantine, target, "venv")
        except BaseException as restore_error:
            raise RuntimeError(
                f"venv ownership identity is unsafe; preserved at {quarantine}"
            ) from restore_error
        raise RuntimeError("venv ownership identity does not match; refusing uninstall") from exc
    return quarantine


def _quarantine_owned_helper(
    target: Path,
    expected_identity: tuple[int, int],
    expected_hash: str,
) -> Path:
    quarantine = target.parent / f".{target.name}.uninstall-quarantine"
    if quarantine.exists() or quarantine.is_symlink():
        raise RuntimeError(
            f"native helper uninstall quarantine already exists: {quarantine}"
        )
    _rename_exclusive(target, quarantine)
    _fsync_directory(target.parent)
    try:
        if (
            _file_identity(quarantine) != expected_identity
            or _sha256_file(quarantine) != expected_hash
        ):
            raise RuntimeError(
                "native helper ownership identity does not match; refusing uninstall"
            )
    except BaseException as exc:
        try:
            _restore_uninstall_quarantine(quarantine, target, "native helper")
        except BaseException as restore_error:
            raise RuntimeError(
                "native helper ownership identity is unsafe; "
                f"preserved at {quarantine}"
            ) from restore_error
        raise RuntimeError(
            "native helper ownership identity does not match; refusing uninstall"
        ) from exc
    return quarantine


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
        expected_venv_identity = current_plan.get("venv_identity")
        expected_helper_identity = current_plan.get("native_helper_identity")
        resource_identities = current_plan.get("resource_identities")
        if not isinstance(resource_identities, dict):
            raise RuntimeError("uninstall resource identities are missing")
        resource_paths = {
            Path(os.path.abspath(os.path.expanduser(str(raw))))
            for raw in current_plan["resources"]
        }
        venv = home / "venv"
        helper = home / "bin" / MACOS_AX_HELPER_NAME
        venv_quarantine: Path | None = None
        helper_quarantine: Path | None = None
        try:
            if venv in resource_paths:
                if (
                    not isinstance(expected_venv_identity, dict)
                    or expected_venv_identity.get("path") != str(venv)
                ):
                    raise RuntimeError(
                        "venv ownership metadata is missing; refusing uninstall"
                    )
                venv_quarantine = _quarantine_owned_venv(
                    venv,
                    (
                        expected_venv_identity.get("dev"),
                        expected_venv_identity.get("ino"),
                    ),
                )
            if helper in resource_paths:
                if (
                    not isinstance(expected_helper_identity, dict)
                    or expected_helper_identity.get("path") != str(helper)
                    or not isinstance(expected_helper_identity.get("sha256"), str)
                ):
                    raise RuntimeError(
                        "native helper ownership metadata is missing; refusing uninstall"
                    )
                helper_quarantine = _quarantine_owned_helper(
                    helper,
                    (
                        expected_helper_identity.get("dev"),
                        expected_helper_identity.get("ino"),
                    ),
                    expected_helper_identity["sha256"],
                )
        except BaseException:
            if helper_quarantine is not None and helper_quarantine.exists():
                _restore_uninstall_quarantine(
                    helper_quarantine,
                    helper,
                    "native helper",
                )
            if venv_quarantine is not None and venv_quarantine.exists():
                _restore_uninstall_quarantine(venv_quarantine, venv, "venv")
            raise

        if helper_quarantine is not None:
            _remove_owned_file(
                helper_quarantine,
                (
                    expected_helper_identity["dev"],
                    expected_helper_identity["ino"],
                ),
                expected_helper_identity["sha256"],
            )
            _fsync_directory(helper.parent)
            removed.append(str(helper))
            resource_paths.remove(helper)
        if venv_quarantine is not None:
            _remove_owned_directory(
                venv_quarantine,
                (
                    expected_venv_identity["dev"],
                    expected_venv_identity["ino"],
                ),
            )
            _fsync_directory(venv.parent)
            removed.append(str(venv))
            resource_paths.remove(venv)

        for candidate in sorted(
            resource_paths,
            key=lambda value: len(Path(value).parts),
            reverse=True,
        ):
            candidate.relative_to(home)
            identity = resource_identities.get(str(candidate))
            _remove_owned_entry(candidate, identity)
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
            if (
                type(metadata.get("dev")) is not int
                or type(metadata.get("ino")) is not int
                or (opened.st_dev, opened.st_ino)
                != (metadata.get("dev"), metadata.get("ino"))
            ):
                raise RuntimeError("owned binary identity mismatch")
            actual_hash = _sha256_fd(helper_fd)
            actual_source_hash = _sha256_file(MACOS_AX_HELPER_SOURCE)
        except PermissionError:
            binary_check["status"] = "fail"
            binary_check["detail"] = "owned binary is not executable"
        except OSError:
            binary_check["status"] = "fail"
            binary_check["detail"] = "owned binary could not be read"
        except RuntimeError:
            binary_check["status"] = "fail"
            binary_check["detail"] = "owned binary identity mismatch"
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
    dependencies = ("fastapi", "uvicorn", "playwright", "websockets")
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
