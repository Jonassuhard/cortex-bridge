"""Safe command-line entry point for the local Cortex terminal."""

from __future__ import annotations

import argparse
import os
import platform as platform_module
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Callable


_DEFAULT_URL = "http://127.0.0.1:8420"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Terminal Cortex pour le backend local loopback.",
    )
    parser.add_argument("--url", default=_DEFAULT_URL, metavar="URL", help="URL loopback du backend Cortex")
    parser.add_argument("--version", action="version", version=_version())
    parser.add_argument("command", nargs="?", choices=("ui",), help="ui : ouvrir l'interface Cortex")
    return parser


def _version() -> str:
    from version import current_version

    return current_version()


def _validated_url(raw_url: str, client_factory: Callable[..., Any]) -> tuple[Any, str]:
    try:
        client = client_factory(raw_url)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return client, client.base_url + "/"


def open_loopback_ui(
    url: str,
    *,
    platform: str | None = None,
    process_run: Callable[..., Any] = subprocess.run,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> bool:
    """Open an already validated loopback URL without a shell command."""
    try:
        if (platform or platform_module.system()).lower() == "darwin":
            result = process_run(["open", "-a", "Google Chrome", url], check=False)
            return result.returncode == 0
        return bool(browser_open(url))
    except (OSError, webbrowser.Error):
        return False


def managed_start(
    base_url: str,
    *,
    root: Path | None = None,
    output: Callable[[str], None] = print,
    process_run: Callable[..., Any] = subprocess.run,
) -> bool:
    """Delegate startup only to the checked-out lifecycle launcher."""
    from urllib.parse import urlsplit

    parsed = urlsplit(base_url)
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    launcher = root / "scripts" / "cortex.sh"
    if not launcher.is_file():
        output("Démarrage indisponible : un checkout Cortex géré avec scripts/cortex.sh est requis.")
        return False
    environment = dict(os.environ)
    # ``scripts/cortex`` may have selected the repository virtualenv for this
    # terminal process, while ``scripts/cortex.sh`` normally prefers the
    # runtime venv under ``CORTEX_HOME``.  Carry the interpreter that is
    # already running the terminal into the lifecycle launcher so its
    # dependency check and daemon use the same environment.  An explicit
    # override remains authoritative for callers that intentionally select a
    # different interpreter.
    if not environment.get("PYTHON_BIN"):
        environment["PYTHON_BIN"] = sys.executable
    environment["PORT"] = str(parsed.port or 80)
    try:
        result = process_run(
            [str(launcher), "start"], cwd=str(root), env=environment, check=False, shell=False,
        )
    except OSError as exc:
        output(f"Démarrage Cortex impossible : {exc}")
        return False
    if result.returncode != 0:
        output("Démarrage Cortex refusé ou incomplet. Consulte scripts/cortex.sh status.")
        return False
    return True


def main(
    argv: list[str] | None = None,
    *,
    app_factory: Callable[..., Any] | None = None,
    client_factory: Callable[..., Any] | None = None,
    platform: str | None = None,
    process_run: Callable[..., Any] = subprocess.run,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if client_factory is None:
        from terminal_client import ApiClient

        client_factory = ApiClient
    try:
        client, ui_url = _validated_url(arguments.url, client_factory)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if arguments.command == "ui":
        return 0 if open_loopback_ui(
            ui_url, platform=platform, process_run=process_run, browser_open=browser_open,
        ) else 1
    if app_factory is None:
        from terminal_app import TerminalApp

        app_factory = TerminalApp
    return int(app_factory(
        client,
        open_ui=lambda: open_loopback_ui(
            ui_url, platform=platform, process_run=process_run, browser_open=browser_open,
        ),
        start_backend=lambda: managed_start(client.base_url, process_run=process_run),
    ).run())


if __name__ == "__main__":
    sys.exit(main())
