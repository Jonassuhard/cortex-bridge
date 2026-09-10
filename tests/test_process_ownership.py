from __future__ import annotations

import fcntl
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class ProcessOwnershipTest(unittest.TestCase):
    def test_shared_lock_command_blocks_an_exclusive_installer_lock_until_exit(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            lock_path = root_path / "cortex-home" / ".install.lock"
            ready_path = root_path / "ready"
            release_path = root_path / "release"
            command = (
                "import sys,time\n"
                "from pathlib import Path\n"
                "ready,release=map(Path,sys.argv[1:])\n"
                "ready.write_text('ready', encoding='utf-8')\n"
                "while not release.exists(): time.sleep(0.01)\n"
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "console" / "process_ownership.py"),
                    "with-shared-lock",
                    "--lock",
                    str(lock_path),
                    "--",
                    sys.executable,
                    "-c",
                    command,
                    str(ready_path),
                    str(release_path),
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.addCleanup(lambda: process.kill() if process.poll() is None else None)

            deadline = time.monotonic() + 5
            while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready_path.exists(), f"lock command exited early: {process.poll()}")

            fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            try:
                self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                release_path.touch()
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def test_shared_lock_command_rejects_a_symlink_without_running_the_command(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            target = root_path / "unrelated"
            target.write_text("keep", encoding="utf-8")
            lock_path = root_path / ".install.lock"
            lock_path.symlink_to(target)
            command_marker = root_path / "command-ran"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "console" / "process_ownership.py"),
                    "with-shared-lock",
                    "--lock",
                    str(lock_path),
                    "--",
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path(__import__('sys').argv[1]).touch()",
                    str(command_marker),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(command_marker.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_listener_probe_timeout_is_structured_unknown_state(self):
        from process_ownership import classify

        with mock.patch(
            "process_ownership.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["lsof"], 10),
        ):
            result = classify(None, 8420)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.listener_pids, [])
        self.assertIn("timed out", result.reason or "")

    def test_missing_listener_probe_is_structured_unknown_state(self):
        from process_ownership import classify

        with mock.patch(
            "process_ownership.subprocess.run",
            side_effect=FileNotFoundError("lsof"),
        ):
            result = classify(None, 8420)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.listener_pids, [])
        self.assertIn("failed", result.reason or "")

    def test_abnormal_listener_probe_exit_is_structured_unknown_state(self):
        from process_ownership import classify

        failed = subprocess.CompletedProcess(["lsof"], 2, stdout="", stderr="failure")
        with mock.patch("process_ownership.subprocess.run", return_value=failed):
            result = classify(None, 8420)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.listener_pids, [])
        self.assertIn("failed", result.reason or "")

    def test_identity_contains_every_required_field_and_exact_owner_is_owned(self):
        from process_ownership import capture_identity, classify

        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        record = capture_identity(os.getpid(), port, "instance-test")
        self.assertEqual(
            set(record),
            {"pid", "start_time", "executable", "argv_hash", "instance_token", "port"},
        )
        result = classify(record, port)
        self.assertEqual(result.state, "owned")
        self.assertEqual(result.pid, os.getpid())

    def test_pid_reuse_or_changed_command_is_stale(self):
        from process_ownership import capture_identity, classify

        record = capture_identity(os.getpid(), 65530, "instance-test")
        record["start_time"] = "not-the-same-start"
        self.assertEqual(classify(record, 65530).state, "stale")

    def test_foreign_listener_is_never_owned(self):
        from process_ownership import capture_identity, classify

        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait(timeout=5)) if sleeper.poll() is None else None)
        time.sleep(0.2)
        record = capture_identity(sleeper.pid, port, "instance-test")
        deadline = time.monotonic() + 2
        result = classify(record, port)
        while result.state != "foreign" and time.monotonic() < deadline:
            time.sleep(0.05)
            result = classify(record, port)
        self.assertEqual(result.state, "foreign")
        self.assertEqual(result.listener_pids, [os.getpid()])

    def test_missing_record_or_dead_process_is_stopped_or_stale(self):
        from process_ownership import capture_identity, classify

        self.assertEqual(classify(None, 65529).state, "stopped")
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        record = capture_identity(process.pid, 65529, "instance-test")
        process.wait(timeout=5)
        self.assertEqual(classify(record, 65529).state, "stale")

    def test_record_round_trip_is_atomic_and_rejects_malformed_json(self):
        from process_ownership import load_record, write_record

        record = {
            "pid": 1,
            "start_time": "start",
            "executable": "python",
            "argv_hash": "a" * 64,
            "instance_token": "token",
            "port": 8420,
        }
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "runtime" / "cortex.json"
            write_record(target, record)
            self.assertEqual(load_record(target), record)
            target.write_text("{broken", encoding="utf-8")
            self.assertIsNone(load_record(target))


class CortexScriptOwnershipTest(unittest.TestCase):
    def test_clean_environment_propagates_pythonpath_through_lifecycle(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            server_environment = root_path / "server-pythonpath.txt"
            start_lock_observation = root_path / "start-install-lock.txt"
            fake_server = root_path / "fake_server.py"
            fake_server.write_text(
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "import fcntl\n"
                "import os\n"
                "from pathlib import Path\n"
                f"Path({str(server_environment)!r}).write_text("
                "os.environ.get('PYTHONPATH', ''), encoding='utf-8')\n"
                "lock_path = Path(os.environ['CORTEX_HOME']) / '.install.lock'\n"
                "lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)\n"
                "try:\n"
                " try:\n"
                "  fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                f"  Path({str(start_lock_observation)!r}).write_text('exclusive-acquired', encoding='utf-8')\n"
                "  fcntl.flock(lock_fd, fcntl.LOCK_UN)\n"
                " except BlockingIOError:\n"
                f"  Path({str(start_lock_observation)!r}).write_text('shared-blocked', encoding='utf-8')\n"
                "finally:\n"
                " os.close(lock_fd)\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                " def do_GET(self):\n"
                "  self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b'{}')\n"
                " def log_message(self, *_args): pass\n"
                "HTTPServer(('127.0.0.1', int(os.environ['PORT'])), Handler).serve_forever()\n",
                encoding="utf-8",
            )
            python_wrapper = root_path / "python"
            python_calls = root_path / "python-calls.log"
            python_wrapper.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {str(python_calls)!r}\n"
                "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets,textual\" ]; then exit 0; fi\n"
                f"if [ \"$1\" = server.py ]; then exec {sys.executable!r} "
                f"{str(fake_server)!r}; fi\n"
                "if [ \"$1\" = -c ] && [ \"$2\" = \"import secrets; print(secrets.token_urlsafe(32))\" ]; then\n"
                " printf '%s\\n' '-leading-dash-token'; exit 0\n"
                "fi\n"
                f"exec {sys.executable!r} \"$@\"\n",
                encoding="utf-8",
            )
            python_wrapper.chmod(0o755)
            bin_dir = root_path / "bin"
            bin_dir.mkdir()
            lsof_wrapper = bin_dir / "lsof"
            lsof_wrapper.write_text(
                "#!/bin/sh\n"
                "pid=''\n"
                "if [ -f \"$CORTEX_HOME/pids/launch.pid\" ]; then\n"
                " pid=\"$(tr -cd '0-9' < \"$CORTEX_HOME/pids/launch.pid\")\"\n"
                "elif [ -f \"$CORTEX_HOME/pids/console.json\" ]; then\n"
                " pid=\"$(sed -E 's/.*\"pid\": ([0-9]+).*/\\1/' \"$CORTEX_HOME/pids/console.json\")\"\n"
                "fi\n"
                "if [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null; then printf '%s\\n' \"$pid\"; fi\n",
                encoding="utf-8",
            )
            lsof_wrapper.chmod(0o755)
            curl_wrapper = bin_dir / "curl"
            curl_wrapper.write_text(
                "#!/bin/sh\n"
                "pid=''\n"
                "if [ -f \"$CORTEX_HOME/pids/launch.pid\" ]; then\n"
                " pid=\"$(tr -cd '0-9' < \"$CORTEX_HOME/pids/launch.pid\")\"\n"
                "fi\n"
                f"if [ -s {str(server_environment)!r} ] && [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null; then exit 0; fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            curl_wrapper.chmod(0o755)
            environment = {
                **os.environ,
                "CORTEX_HOME": str(root_path / "cortex-home"),
                "PYTHON_BIN": str(python_wrapper),
                "PORT": str(port),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            }
            environment.pop("PYTHONPATH", None)

            # The lifecycle command owns smaller internal deadlines (including
            # three 3 s identity probes). This is only the outer test harness
            # bound and must leave scheduling margin on a cold macOS runner.
            lifecycle_timeout = 35
            started = subprocess.run(
                ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=lifecycle_timeout,
            )
            try:
                self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                self.assertEqual(
                    server_environment.read_text(encoding="utf-8"),
                    f"{ROOT / 'console'}:{ROOT}",
                )
                self.assertEqual(
                    start_lock_observation.read_text(encoding="utf-8"),
                    "shared-blocked",
                )
                self.assertIn(
                    "import fastapi,uvicorn,playwright,websockets,textual",
                    python_calls.read_text(encoding="utf-8"),
                )
            finally:
                subprocess.run(
                    ["bash", str(ROOT / "scripts" / "cortex.sh"), "stop"],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=lifecycle_timeout,
                )

    def _foreign_environment(self, root: Path) -> tuple[dict[str, str], Path]:
        bin_dir = root / "bin"
        bin_dir.mkdir()
        kill_log = root / "kill.log"
        foreign_pid = os.getpid()
        commands = {
            "lsof": f"#!/bin/sh\necho {foreign_pid}\n",
            "kill": f"#!/bin/sh\necho \"$*\" >> {kill_log}\n",
            "seq": "#!/bin/sh\necho 1\n",
            "sleep": "#!/bin/sh\nexit 0\n",
            "curl": "#!/bin/sh\nexit 1\n",
        }
        for name, body in commands.items():
            target = bin_dir / name
            target.write_text(body, encoding="utf-8")
            target.chmod(0o755)
        bash_env = root / "bash-env"
        bash_env.write_text("enable -n kill\n", encoding="utf-8")
        python_wrapper = root / "python"
        python_wrapper.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets,textual\" ]; then exit 0; fi\n"
            f"exec {sys.executable!r} \"$@\"\n",
            encoding="utf-8",
        )
        python_wrapper.chmod(0o755)
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "BASH_ENV": str(bash_env),
            "CORTEX_HOME": str(root / "cortex-home"),
            "PYTHON_BIN": str(python_wrapper),
            "PORT": "58420",
        }
        return environment, kill_log

    def test_start_refuses_a_foreign_listener(self):
        with tempfile.TemporaryDirectory() as root:
            environment, kill_log = self._foreign_environment(Path(root))
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("foreign", (result.stdout + result.stderr).lower())
            self.assertFalse(kill_log.exists())

    def test_stop_never_signals_a_foreign_listener(self):
        with tempfile.TemporaryDirectory() as root:
            environment, kill_log = self._foreign_environment(Path(root))
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "cortex.sh"), "stop"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("foreign", (result.stdout + result.stderr).lower())
            self.assertFalse(kill_log.exists(), "stop attempted to signal a foreign pid")

    def test_start_refuses_an_unknown_ownership_probe(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            bin_dir = root_path / "bin"
            bin_dir.mkdir()
            for name, body in {
                "lsof": "#!/bin/sh\nexit 0\n",
                "curl": "#!/bin/sh\nexit 1\n",
                "seq": "#!/bin/sh\necho 1\n",
                "sleep": "#!/bin/sh\nexit 0\n",
            }.items():
                target = bin_dir / name
                target.write_text(body, encoding="utf-8")
                target.chmod(0o755)
            python_wrapper = root_path / "python"
            python_wrapper.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets,textual\" ]; then exit 0; fi\n"
                "case \"$1:$2\" in\n"
                f" */process_ownership.py:with-shared-lock) exec {sys.executable!r} \"$@\";;\n"
                " */process_ownership.py:status) printf '%s\\n' '{\"state\":\"unknown\",\"pid\":null,\"listener_pids\":[],\"reason\":\"listener probe timed out\"}'; exit 0;;\n"
                " server.py:*) exit 1;;\n"
                "esac\n"
                f"exec {sys.executable!r} \"$@\"\n",
                encoding="utf-8",
            )
            python_wrapper.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "CORTEX_HOME": str(root_path / "cortex-home"),
                "PYTHON_BIN": str(python_wrapper),
                "PORT": "58421",
            }

            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
