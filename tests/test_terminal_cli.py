"""Black-box contracts for the Cortex terminal launcher and package."""

from __future__ import annotations

import json
import os
import pty
import select
import signal
import subprocess
import sys
import threading
import time
import unittest
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class _LoopbackFixture:
    """Small HTTP fixture that records the terminal's actual API path."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, bytes]] = []
        self._follow_calls = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_GET(self):
                parent._respond(self)

            def do_POST(self):
                parent._respond(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def _respond(self, handler: BaseHTTPRequestHandler) -> None:
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length)
        self.requests.append((handler.command, handler.path, body))
        route = urlsplit(handler.path).path
        if route == "/api/status":
            payload = {"executor_available": True}
        elif route == "/api/pipeline/status":
            payload = {"components": [{"id": "transport", "state": "fixture"}]}
        elif route == "/api/conversations":
            payload = [{"title": "Fixture conversation", "url": "https://chatgpt.com/c/fixture"}]
        elif route == "/api/conversations/snapshot":
            payload = {"messages": [{"role": "user", "text": "Fixture question"}]}
        elif route == "/api/chat/send":
            payload = {"id": "run-1", "state": "QUEUED"}
        elif route == "/api/chat/runs/run-1":
            self._follow_calls += 1
            payload = {
                "id": "run-1", "state": "COMPLETED", "response_text": "Fixture answer",
                "delivered_at": "2026-09-10T01:00:00Z",
            }
        else:
            handler.send_response(404)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b'{"detail":"unexpected fixture route"}')
            return
        encoded = json.dumps(payload).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)


def _pty_run(arguments: list[str], input_bytes: bytes, *, columns: int = 80) -> tuple[int, str]:
    master, slave = pty.openpty()
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "COLUMNS": str(columns),
        "LINES": "24",
    }
    process = subprocess.Popen(
        [str(ROOT / "scripts" / "cortex"), "--plain", *arguments],
        cwd=ROOT,
        env=environment,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
    )
    os.close(slave)
    try:
        if input_bytes:
            os.write(master, input_bytes)
        chunks = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            if process.poll() is not None:
                break
            process.wait(timeout=5)
            return process.returncode, b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _pty_start(arguments: list[str], *, columns: int = 80) -> tuple[subprocess.Popen[bytes], int, str]:
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [str(ROOT / "scripts" / "cortex"), "--plain", *arguments],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": str(columns), "LINES": "24"},
        stdin=slave, stdout=slave, stderr=slave, close_fds=True,
    )
    os.close(slave)
    chunks = []
    # A full release run can have many short-lived subprocesses and PTYs
    # already active. Keep the assertion about signal handling, but allow the
    # child a bounded extra window to flush the prompt and marker under load.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        readable, _, _ = select.select([master], [], [], 0.1)
        if not readable:
            continue
        chunk = os.read(master, 4096)
        chunks.append(chunk)
        if b"cortex> " in b"".join(chunks):
            return process, master, b"".join(chunks).decode("utf-8", errors="replace")
    os.close(master)
    process.kill()
    process.wait(timeout=5)
    raise AssertionError("terminal prompt did not arrive")


def _pty_finish(process: subprocess.Popen[bytes], master: int, prefix: str) -> tuple[int, str]:
    chunks = [prefix.encode("utf-8")]
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], 0.1)
            if not readable:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        process.wait(timeout=5)
        return process.returncode, b"".join(chunks).decode("utf-8", errors="replace")
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _pty_wait_for(master: int, process: subprocess.Popen[bytes], prefix: str, marker: str) -> str:
    """Drain a PTY until an interactive state is observable before sending input."""
    chunks = [prefix.encode("utf-8")]
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            screen = b"".join(chunks).decode("utf-8", errors="replace")
            if marker in screen:
                return screen
            readable, _, _ = select.select([master], [], [], 0.1)
            if not readable:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        raise AssertionError(f"PTY marker did not arrive: {marker!r}")
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        raise


class TerminalCliUnitTests(unittest.TestCase):
    def test_help_and_version_are_offline(self):
        for argument, expected in (("--help", "usage:"), ("--version", "0.6.1")):
            with self.subTest(argument=argument):
                result = subprocess.run(
                    [str(ROOT / "scripts" / "cortex"), argument],
                    cwd=ROOT, text=True, capture_output=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

    def test_default_constructs_the_frozen_terminal_app_contract(self):
        import terminal_cli

        received = {}

        class App:
            def __init__(self, client, input_fn=input, output=None, open_ui=None, start_backend=None):
                received.update({
                    "client": client, "input_fn": input_fn, "output": output,
                    "open_ui": open_ui, "start_backend": start_backend,
                })

            def run(self):
                return 7

        self.assertEqual(7, terminal_cli.main(["--url", "http://127.0.0.1:18420"], app_factory=App))
        self.assertEqual("http://127.0.0.1:18420", received["client"].base_url)
        self.assertTrue(callable(received["open_ui"]))
        self.assertTrue(callable(received["start_backend"]))

    def test_plain_flag_keeps_legacy_text_client_explicit(self):
        import terminal_cli

        received = {}

        class App:
            def __init__(self, client, input_fn=input, output=None, open_ui=None, start_backend=None):
                received["client"] = client

            def run(self):
                return 0

        self.assertEqual(
            0,
            terminal_cli.main(["--plain", "--url", "http://127.0.0.1:18420"], app_factory=App),
        )
        self.assertEqual("http://127.0.0.1:18420", received["client"].base_url)

    def test_default_without_factory_dispatches_to_full_screen_tui(self):
        import terminal_cli
        import tui

        received = {}

        class FakeTui:
            def __init__(self, client, *, open_ui=None, start_backend=None, offline=False):
                received.update({
                    "client": client,
                    "open_ui": open_ui,
                    "start_backend": start_backend,
                    "offline": offline,
                })

            def run(self):
                return 13

        with mock.patch.object(tui, "CortexTui", FakeTui):
            self.assertEqual(13, terminal_cli.main(["--url", "http://127.0.0.1:18420"]))
        self.assertEqual("http://127.0.0.1:18420", received["client"].base_url)
        self.assertTrue(callable(received["open_ui"]))
        self.assertTrue(callable(received["start_backend"]))
        self.assertFalse(received["offline"])

    def test_ui_validates_loopback_before_fixed_macos_open_argv(self):
        import terminal_cli

        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        self.assertEqual(
            0,
            terminal_cli.main(
                ["--url", "http://127.0.0.1:18420", "ui"],
                platform="darwin", process_run=run,
            ),
        )
        run.assert_called_once_with(
            ["open", "-a", "Google Chrome", "http://127.0.0.1:18420/"],
            check=False,
        )
        with self.assertRaises(SystemExit) as rejected:
            terminal_cli.main(["--url", "http://example.com:18420", "ui"])
        self.assertEqual(2, rejected.exception.code)

    def test_ui_macos_os_error_becomes_clean_failure_exit(self):
        import terminal_cli

        def unavailable(*_args, **_kwargs):
            raise OSError("open unavailable")

        self.assertEqual(
            1,
            terminal_cli.main(
                ["--url", "http://127.0.0.1:18420", "ui"],
                platform="darwin", process_run=unavailable,
            ),
        )

    def test_ui_browser_fallback_error_becomes_clean_failure_exit(self):
        import terminal_cli

        def unavailable(_url):
            raise webbrowser.Error("browser unavailable")

        self.assertEqual(
            1,
            terminal_cli.main(
                ["--url", "http://127.0.0.1:18420", "ui"],
                platform="linux", browser_open=unavailable,
            ),
        )

    def test_managed_start_uses_trusted_checkout_launcher_and_selected_port(self):
        import terminal_cli

        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        root = ROOT
        with mock.patch.dict(os.environ, {}, clear=True):
            started = terminal_cli.managed_start(
                "http://127.0.0.1:18420", root=root, process_run=run,
            )
        self.assertTrue(started)
        command, = run.call_args.args
        self.assertEqual([str(root / "scripts" / "cortex.sh"), "start"], command)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        self.assertEqual("18420", run.call_args.kwargs["env"]["PORT"])
        self.assertEqual(sys.executable, run.call_args.kwargs["env"]["PYTHON_BIN"])

    def test_managed_start_preserves_explicit_python_interpreter_override(self):
        import terminal_cli

        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        with mock.patch.dict(os.environ, {"PYTHON_BIN": "/custom/cortex-python"}, clear=True):
            started = terminal_cli.managed_start(
                "http://127.0.0.1:18420", root=ROOT, process_run=run,
            )

        self.assertTrue(started)
        self.assertEqual("/custom/cortex-python", run.call_args.kwargs["env"]["PYTHON_BIN"])

    def test_installed_wheel_has_no_direct_daemon_start_fallback(self):
        import terminal_cli

        output = []
        self.assertFalse(terminal_cli.managed_start(
            "http://127.0.0.1:18420", root=Path("/missing-checkout"), output=output.append,
        ))
        self.assertIn("checkout Cortex", "\n".join(output))


class TerminalCliPtyAcceptanceTests(unittest.TestCase):
    def test_pty_human_path_reads_selected_messages_then_followed_response_and_delivery(self):
        with _LoopbackFixture() as fixture:
            process, master, opening = _pty_start(["--url", fixture.base_url])
            os.write(master, b"/conversations\n/ouvrir 1\n/historique\ntexte exact PTY\n/suivre\n/quitter\n")
            status, screen = _pty_finish(process, master, opening)

        self.assertEqual(0, status, screen)
        self.assertIn("████", screen)
        self.assertIn("Cortex terminal", screen)
        self.assertIn("Fixture conversation", screen)
        self.assertIn("user: Fixture question", screen)
        self.assertIn("Message en file", screen)
        self.assertIn("Run run-1", screen)
        self.assertIn("Fixture answer", screen)
        self.assertIn("Livraison confirmée", screen)
        observed = [(method, path) for method, path, _body in fixture.requests]
        self.assertIn(("GET", "/api/conversations"), observed)
        self.assertIn(("GET", "/api/conversations/snapshot?url=https%3A%2F%2Fchatgpt.com%2Fc%2Ffixture"), observed)
        self.assertIn(("POST", "/api/chat/send"), observed)
        self.assertIn(("GET", "/api/chat/runs/run-1"), observed)
        sent_body = next(body for method, path, body in fixture.requests if (method, path) == ("POST", "/api/chat/send"))
        self.assertEqual("texte exact PTY", json.loads(sent_body)["text"])

    def test_pty_narrow_width_uses_compact_title(self):
        with _LoopbackFixture() as fixture:
            process, master, opening = _pty_start(["--url", fixture.base_url], columns=20)
            os.write(master, b"/quitter\n")
            status, screen = _pty_finish(process, master, opening)

        self.assertEqual(0, status, screen)
        self.assertIn("Cortex terminal", screen)
        self.assertNotIn("████", screen)

    def test_pty_ctrl_c_leaves_the_interactive_prompt_usable(self):
        with _LoopbackFixture() as fixture:
            process, master, opening = _pty_start(["--url", fixture.base_url])
            process.send_signal(signal.SIGINT)
            opening = _pty_wait_for(master, process, opening, "Interrompu. Rien n’a été annulé.")
            os.write(master, b"/quitter\n")
            status, screen = _pty_finish(process, master, opening)

        self.assertEqual(0, status, screen)
        self.assertIn("Interrompu. Rien n’a été annulé.", screen)

    def test_pty_eof_exits_without_stopping_the_backend(self):
        with _LoopbackFixture() as fixture:
            process, master, opening = _pty_start(["--url", fixture.base_url])
            os.write(master, b"\x04")
            status, screen = _pty_finish(process, master, opening)

        self.assertEqual(0, status, screen)
        self.assertIn("Fin de l’entrée. Le serveur reste actif.", screen)


if __name__ == "__main__":
    unittest.main()
