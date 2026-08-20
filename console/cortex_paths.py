"""One location for every mutable Cortex Bridge runtime artifact."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CortexPaths:
    home: Path
    settings: Path
    database: Path
    iterations: Path
    chat_runs: Path
    attachments: Path
    browser_profiles: Path
    runs: Path
    pids: Path
    logs: Path
    onboarding: Path
    transport_optin: Path

    def mutable_paths(self) -> tuple[Path, ...]:
        return (
            self.home,
            self.settings,
            self.database,
            self.iterations,
            self.chat_runs,
            self.attachments,
            self.browser_profiles,
            self.runs,
            self.pids,
            self.logs,
            self.onboarding,
            self.transport_optin,
        )


def _absolute_env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path.resolve(strict=False)


def build_paths() -> CortexPaths:
    home = _absolute_env_path(
        "CORTEX_HOME",
        Path.home() / ".local" / "share" / "cortex-bridge",
    )
    return CortexPaths(
        home=home,
        settings=home / "settings.json",
        database=home / "cortex.db",
        iterations=home / "iterations.json",
        chat_runs=home / "chat-runs.json",
        attachments=home / "attachments",
        browser_profiles=home / "browser-profiles",
        runs=home / "runs",
        pids=home / "pids",
        logs=home / "logs",
        onboarding=home / "onboarding-done.json",
        transport_optin=home / "transport-optin.json",
    )


def ensure_layout(paths: CortexPaths | None = None) -> CortexPaths:
    paths = paths or build_paths()
    for directory in (
        paths.home,
        paths.attachments,
        paths.browser_profiles,
        paths.runs,
        paths.pids,
        paths.logs,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _copy_directory_without_symlinks(source: Path, destination: Path) -> bool:
    copied = False
    for child in sorted(source.rglob("*")):
        if child.is_symlink():
            continue
        relative = child.relative_to(source)
        target = destination / relative
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif child.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
            copied = True
    return copied


def migrate_legacy_state(legacy_data: Path, paths: CortexPaths | None = None) -> list[Path]:
    """Copy missing legacy state into CORTEX_HOME; never delete or overwrite."""
    paths = paths or build_paths()
    mapping = {
        "settings.json": paths.settings,
        "cortex.db": paths.database,
        "iterations.json": paths.iterations,
        "chat-runs.json": paths.chat_runs,
        "onboarding-done.json": paths.onboarding,
        "transport-optin.json": paths.transport_optin,
        "attachments": paths.attachments,
        "browser-profiles": paths.browser_profiles,
        "runs": paths.runs,
    }
    migrated: list[Path] = []
    if not legacy_data.is_dir() or legacy_data.is_symlink():
        return migrated
    paths.home.mkdir(parents=True, exist_ok=True)
    for name, destination in mapping.items():
        source = legacy_data / name
        if source.is_symlink() or not source.exists() or destination.exists():
            continue
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            if _copy_directory_without_symlinks(source, destination):
                migrated.append(destination)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            migrated.append(destination)
    return migrated


def model_directory() -> Path:
    if "CORTEX_MODEL_DIR" in os.environ:
        return _absolute_env_path("CORTEX_MODEL_DIR", Path.home() / ".ollama" / "models")
    if "CORTEX_STORAGE_PATH" in os.environ:
        return _absolute_env_path("CORTEX_STORAGE_PATH", Path.home() / ".ollama" / "models")
    return (Path.home() / ".ollama" / "models").resolve(strict=False)
