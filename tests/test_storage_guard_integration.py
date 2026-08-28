"""Lifecycle integration tests for the optional external-storage guard."""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORTEX_SH = ROOT / "scripts" / "cortex.sh"


class StorageGuardIntegrationTest(unittest.TestCase):
    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    @staticmethod
    def _is_listening(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            return probe.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _environment(root: Path, cortex_home: Path) -> dict[str, str]:
        fake_python = root / "python"
        fake_python.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
            "case \"$1:$2\" in\n"
            f" */process_ownership.py:status) printf '%s\\n' {shlex.quote(json.dumps({'state': 'stopped', 'pid': None, 'listener_pids': []}))}; exit 0;;\n"
            "esac\n"
            f"exec {sys.executable!r} \"$@\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = {
            **os.environ,
            "CORTEX_HOME": str(cortex_home),
            "CORTEX_START_INSTALL_LOCK_HELD": "1",
            "PORT": "58423",
            "PYTHON_BIN": str(fake_python),
        }
        environment.pop("PYTHONPATH", None)
        return environment

    def test_start_fails_before_launch_when_configured_volume_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            cortex_home.mkdir()
            missing_mount = root / "missing-volume"
            (cortex_home / "storage-bootstrap.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "mount_path": str(missing_mount),
                        "volume_uuid": "12345678-1234-1234-1234-123456789ABC",
                        "encrypted_image_path": str(root / "vault.sparsebundle"),
                        "storage_root": str(missing_mount / "CORTEX_BRIDGE"),
                    }
                ),
                encoding="utf-8",
            )
            (cortex_home / "storage-bootstrap.json").chmod(0o600)

            environment = self._environment(root, cortex_home)
            result = subprocess.run(
                ["bash", str(CORTEX_SH), "start"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("STORAGE_VOLUME_MISSING", result.stderr)
            self.assertFalse((cortex_home / "pids" / "launch.pid").exists())
            self.assertFalse((cortex_home / "logs" / "console.log").exists())

    def test_required_storage_cannot_fail_open_when_bootstrap_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            cortex_home.mkdir()
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-required").chmod(0o600)
            environment = self._environment(root, cortex_home)

            result = subprocess.run(
                ["bash", str(CORTEX_SH), "start"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("STORAGE_BOOTSTRAP_MISSING", result.stderr)
            self.assertFalse((cortex_home / "pids" / "launch.pid").exists())
            self.assertFalse((cortex_home / "logs" / "console.log").exists())

    def test_uvicorn_module_entrypoint_refuses_required_storage_before_listening(self) -> None:
        """Catch a direct ``python -m uvicorn server:app`` fail-open."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            cortex_home.mkdir()
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-required").chmod(0o600)
            port = self._free_port()
            environment = {
                **os.environ,
                "CORTEX_HOME": str(cortex_home),
                "PORT": str(port),
            }
            environment["PYTHONPATH"] = str(ROOT)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "error",
                ],
                cwd=ROOT / "console",
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                stdout, stderr = process.communicate(timeout=5)
                self.fail(
                    "Uvicorn served despite missing required storage bootstrap: "
                    + stdout
                    + stderr
                )
            stdout, stderr = process.communicate(timeout=1)

            self.assertNotEqual(returncode, 0, stdout + stderr)
            self.assertIn("STORAGE_BOOTSTRAP_MISSING", stderr)
            self.assertFalse(self._is_listening(port), stdout + stderr)

    def test_rejected_asgi_startup_closes_an_open_mission_store(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            cortex_home.mkdir()
            (cortex_home / "storage-required").write_text("required\n", encoding="utf-8")
            (cortex_home / "storage-required").chmod(0o600)
            code = """
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

root = Path(sys.argv[1])
database = Path(sys.argv[2])
sys.path[:0] = [str(root / "console"), str(root)]

import missions
import server
from orchestration.store import Store

async def verify():
    os.umask(0o022)
    store = Store(database)
    missions._store = store
    with patch.object(server, "close_mission_store", wraps=missions.close_store) as close:
        try:
            async with server.app.router.lifespan_context(server.app):
                raise AssertionError("required storage should reject startup")
        except RuntimeError:
            pass
        close.assert_called_once_with()
    assert store.closed
    current = os.umask(0o022)
    os.umask(current)
    assert current == 0o022, oct(current)

asyncio.run(verify())
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(cortex_home),
                "PYTHONPATH": str(ROOT),
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT), str(cortex_home / "cortex.db")],
                cwd=ROOT / "console",
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_uvicorn_module_entrypoint_starts_when_external_storage_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            cortex_home.mkdir()
            port = self._free_port()
            environment = {
                **os.environ,
                "CORTEX_HOME": str(cortex_home),
                "PORT": str(port),
            }
            environment["PYTHONPATH"] = str(ROOT)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "error",
                ],
                cwd=ROOT / "console",
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not self._is_listening(port):
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                stdout, stderr = process.communicate(timeout=0) if process.poll() is not None else ("", "")
                self.assertIsNone(process.poll(), stdout + stderr)
                self.assertTrue(self._is_listening(port))
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

    def test_uvicorn_lifespan_saves_iterations_with_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cortex_home = root / "cortex-home"
            port = self._free_port()
            code = """
import os
import socket
import sys
import threading
import time
from pathlib import Path

os.umask(0o022)
root = Path(sys.argv[1])
port = int(sys.argv[2])
sys.path[:0] = [str(root / "console"), str(root)]

import server
import uvicorn

server._iterations[:] = [{"id": "lifespan-proof"}]
httpd = uvicorn.Server(
    uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error")
)
thread = threading.Thread(target=httpd.run, daemon=True)
thread.start()
try:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)
    else:
        raise AssertionError("Uvicorn did not start")

    server._save_store()
    store = server.STORE_FILE
    assert store.stat().st_mode & 0o777 == 0o600, oct(store.stat().st_mode & 0o777)
    assert store.parent.stat().st_mode & 0o777 == 0o700
finally:
    httpd.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive()
    current = os.umask(0o022)
    os.umask(current)
    assert current == 0o022, oct(current)
"""
            environment = {
                **os.environ,
                "CORTEX_HOME": str(cortex_home),
                "PYTHONPATH": str(ROOT),
            }
            result = subprocess.run(
                [sys.executable, "-c", code, str(ROOT), str(port)],
                cwd=ROOT / "console",
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
