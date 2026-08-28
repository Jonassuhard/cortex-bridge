from __future__ import annotations

import fcntl
import json
import os
import signal
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
    LIFECYCLE_LOCK_MARKER = (
        b'{"owner":"cortex-bridge","schema_version":1,'
        b'"type":"lifecycle_lock"}\n'
    )

    def _run_with_shared_lock(self, lock_path: Path, command: list[str]):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "console" / "process_ownership.py"),
                "with-shared-lock",
                "--lock",
                str(lock_path),
                "--",
                *command,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_shared_lock_command_created_from_absence_publishes_canonical_marker(self):
        with tempfile.TemporaryDirectory() as root:
            lock_path = Path(root).resolve() / "cortex-home" / ".install.lock"

            result = self._run_with_shared_lock(
                lock_path,
                [sys.executable, "-c", "raise SystemExit(0)"],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lock_path.read_bytes(), self.LIFECYCLE_LOCK_MARKER)
            details = lock_path.stat(follow_symlinks=False)
            self.assertEqual(details.st_uid, os.getuid())
            self.assertEqual(details.st_nlink, 1)
            self.assertEqual(stat.S_IMODE(details.st_mode), 0o600)

    def test_concurrent_shared_lock_creators_publish_one_complete_marker_inode(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            home = root_path / "cortex-home"
            lock_path = home / ".install.lock"
            start = root_path / "lock-create-start"
            launcher = (
                "import os,sys,time\n"
                "from pathlib import Path\n"
                "while not Path(os.environ['LOCK_CREATE_START']).exists(): time.sleep(0.005)\n"
                "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
            )
            report = (
                "import json,os,sys\n"
                "from pathlib import Path\n"
                "lock,result=map(Path,sys.argv[1:])\n"
                "details=lock.stat(follow_symlinks=False)\n"
                "result.write_text(json.dumps({'dev':details.st_dev,'ino':details.st_ino,'hex':lock.read_bytes().hex()}), encoding='utf-8')\n"
            )
            processes: list[subprocess.Popen[str]] = []
            results: list[Path] = []
            try:
                for index in range(4):
                    result_path = root_path / f"lock-result-{index}.json"
                    results.append(result_path)
                    environment = {
                        **os.environ,
                        "LOCK_CREATE_START": str(start),
                    }
                    processes.append(
                        subprocess.Popen(
                            [
                                sys.executable,
                                "-c",
                                launcher,
                                str(ROOT / "console" / "process_ownership.py"),
                                "with-shared-lock",
                                "--lock",
                                str(lock_path),
                                "--",
                                sys.executable,
                                "-c",
                                report,
                                str(lock_path),
                                str(result_path),
                            ],
                            cwd=ROOT,
                            env=environment,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                    )
                start.touch()
                for process in processes:
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr or stdout)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

            payloads = [json.loads(path.read_text(encoding="utf-8")) for path in results]
            expected_identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            self.assertEqual(
                {(payload["dev"], payload["ino"]) for payload in payloads},
                {expected_identity},
            )
            self.assertEqual(
                {bytes.fromhex(payload["hex"]) for payload in payloads},
                {self.LIFECYCLE_LOCK_MARKER},
            )
            self.assertEqual(list(home.glob(".install.lock.init-*")), [])

    def test_shared_lock_command_rejects_foreign_marker_without_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            lock_path = root_path / ".install.lock"
            command_marker = root_path / "command-ran"
            foreign_bytes = b"foreign-private-lock"
            lock_path.write_bytes(foreign_bytes)
            lock_path.chmod(0o600)
            before = lock_path.stat(follow_symlinks=False)

            result = self._run_with_shared_lock(
                lock_path,
                [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).touch()", str(command_marker)],
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(command_marker.exists())
            self.assertEqual(lock_path.read_bytes(), foreign_bytes)
            after = lock_path.stat(follow_symlinks=False)
            self.assertEqual((after.st_dev, after.st_ino), (before.st_dev, before.st_ino))

    def test_shared_lock_command_rejects_hardlinked_marker_without_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            lock_path = root_path / ".install.lock"
            external = root_path / "external-lock"
            lock_path.write_bytes(self.LIFECYCLE_LOCK_MARKER)
            lock_path.chmod(0o600)
            os.link(lock_path, external)
            command_marker = root_path / "command-ran"
            before = lock_path.stat(follow_symlinks=False)

            result = self._run_with_shared_lock(
                lock_path,
                [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).touch()", str(command_marker)],
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(command_marker.exists())
            after = lock_path.stat(follow_symlinks=False)
            self.assertEqual((after.st_dev, after.st_ino, after.st_nlink), (before.st_dev, before.st_ino, 2))
            self.assertEqual(external.read_bytes(), self.LIFECYCLE_LOCK_MARKER)

    def test_shared_lock_command_rejects_world_readable_marker_without_chmod(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            lock_path = root_path / ".install.lock"
            command_marker = root_path / "command-ran"
            lock_path.write_bytes(self.LIFECYCLE_LOCK_MARKER)
            lock_path.chmod(0o644)

            result = self._run_with_shared_lock(
                lock_path,
                [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).touch()", str(command_marker)],
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(command_marker.exists())
            self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o644)
            self.assertEqual(lock_path.read_bytes(), self.LIFECYCLE_LOCK_MARKER)

    def test_shared_lock_command_accepts_an_existing_canonical_marker(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            lock_path = root_path / ".install.lock"
            command_marker = root_path / "command-ran"
            lock_path.write_bytes(self.LIFECYCLE_LOCK_MARKER)
            lock_path.chmod(0o600)

            result = self._run_with_shared_lock(
                lock_path,
                [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).touch()", str(command_marker)],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(command_marker.is_file())

    def test_shared_lock_command_blocks_an_exclusive_installer_lock_until_exit(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
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

    def test_shared_lock_command_privatizes_public_parent_before_creating_marker(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            home = root_path / "cortex-home"
            home.mkdir(mode=0o700)
            home.chmod(0o777)
            lock_path = home / ".install.lock"
            observed_mode = root_path / "observed-mode"

            result = self._run_with_shared_lock(
                lock_path,
                [
                    sys.executable,
                    "-c",
                    (
                        "import stat,sys\n"
                        "from pathlib import Path\n"
                        "home,result=map(Path,sys.argv[1:])\n"
                        "result.write_text(oct(stat.S_IMODE(home.stat().st_mode)), encoding='utf-8')\n"
                    ),
                    str(home),
                    str(observed_mode),
                ],
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(observed_mode.read_text(encoding="utf-8"), "0o700")
            self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
            self.assertEqual(lock_path.read_bytes(), self.LIFECYCLE_LOCK_MARKER)

    def test_shared_lock_command_rejects_symlinked_parent_component(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            actual = root_path / "actual"
            actual.mkdir()
            alias = root_path / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            lock_path = alias / "cortex-home" / ".install.lock"
            command_marker = root_path / "command-ran"

            result = self._run_with_shared_lock(
                lock_path,
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path(__import__('sys').argv[1]).touch()",
                    str(command_marker),
                ],
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(command_marker.exists())
            self.assertFalse((actual / "cortex-home" / ".install.lock").exists())

    def test_lifecycle_lock_rejects_foreign_owned_final_parent_without_marker(self):
        from lifecycle_lock import open_lifecycle_lock

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            home = root_path / "cortex-home"
            home.mkdir(mode=0o700)
            actual_uid = os.getuid()

            with mock.patch("lifecycle_lock.os.getuid", return_value=actual_uid + 1):
                with self.assertRaisesRegex(RuntimeError, "unsafe|directory|parent"):
                    open_lifecycle_lock(home / ".install.lock")

            self.assertFalse((home / ".install.lock").exists())

    def test_lifecycle_lock_rejects_parent_substitution_before_publication(self):
        import lifecycle_lock

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root).resolve()
            home = root_path / "cortex-home"
            home.mkdir(mode=0o700)
            displaced = root_path / "displaced-home"
            real_create = lifecycle_lock._create_temporary_lock

            def create_then_substitute(directory_fd: int, prefix: str):
                result = real_create(directory_fd, prefix)
                home.rename(displaced)
                home.mkdir(mode=0o700)
                return result

            with mock.patch.object(
                lifecycle_lock,
                "_create_temporary_lock",
                side_effect=create_then_substitute,
            ):
                with self.assertRaisesRegex(RuntimeError, "directory|parent"):
                    lifecycle_lock.open_lifecycle_lock(home / ".install.lock")

            self.assertFalse((home / ".install.lock").exists())
            self.assertFalse((displaced / ".install.lock").exists())
            self.assertEqual(list(displaced.glob(".install.lock.init-*")), [])

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
    @staticmethod
    def _is_listening(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.1)
            return probe.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def _wait_for_process_exit(self, pid: int, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while self._pid_exists(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        return not self._pid_exists(pid)

    def _capture_failure_environment(
        self,
        root_path: Path,
        port: int,
        *,
        substitute_record: Path | None = None,
    ) -> tuple[dict[str, str], Path, Path]:
        server_pid = root_path / "server.pid"
        capture_marker = root_path / "capture-reached"
        fake_server = root_path / "fake_server.py"
        fake_server.write_text(
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "import os\n"
            "from pathlib import Path\n"
            f"Path({str(server_pid)!r}).write_text(str(os.getpid()), encoding='utf-8')\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            " def do_GET(self):\n"
            "  self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b'{}')\n"
            " def log_message(self, *_args): pass\n"
            "HTTPServer(('127.0.0.1', int(os.environ['PORT'])), Handler).serve_forever()\n",
            encoding="utf-8",
        )
        python_wrapper = root_path / "python"
        python_wrapper.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
            f"if [ \"$1\" = server.py ]; then exec {sys.executable!r} {str(fake_server)!r}; fi\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import secrets; print(secrets.token_urlsafe(32))\" ]; then\n"
            " printf '%s\\n' '-leading-dash-token'; exit 0\n"
            "fi\n"
            "if [ \"$1\" = -c ]; then\n"
            " case \"$2\" in\n"
            "  *\".console.json.\"*)\n"
            f"   {sys.executable!r} -c \"import socket,sys; from pathlib import Path; connection=socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=2); connection.close(); Path(sys.argv[1]).write_text('listener-confirmed', encoding='utf-8')\" {str(capture_marker)!r} \"$PORT\" || exit 91\n"
            "   if [ -n \"${CORTEX_TEST_SUBSTITUTE_LAUNCH_RECORD:-}\" ]; then\n"
            f"    {sys.executable!r} -c \"import os,sys; os.replace(sys.argv[1], sys.argv[2])\" \"$CORTEX_TEST_SUBSTITUTE_LAUNCH_RECORD\" \"$CORTEX_HOME/pids/launch.pid\" || exit 92\n"
            "   fi\n"
            "   exit 23\n"
            "   ;;\n"
            " esac\n"
            "fi\n"
            f"exec {sys.executable!r} \"$@\"\n",
            encoding="utf-8",
        )
        python_wrapper.chmod(0o755)
        environment = {
            **os.environ,
            "CORTEX_HOME": str(root_path / "cortex-home"),
            "PYTHON_BIN": str(python_wrapper),
            "PORT": str(port),
        }
        if substitute_record is not None:
            environment["CORTEX_TEST_SUBSTITUTE_LAUNCH_RECORD"] = str(substitute_record)
        environment.pop("PYTHONPATH", None)
        return environment, server_pid, capture_marker

    def _never_ready_environment(
        self, root_path: Path, port: int
    ) -> tuple[dict[str, str], Path, Path]:
        server_pid = root_path / "server.pid"
        fake_server = root_path / "fake_server.py"
        fake_server.write_text(
            "import os\n"
            "import time\n"
            "from pathlib import Path\n"
            f"Path({str(server_pid)!r}).write_text(str(os.getpid()), encoding='utf-8')\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        python_wrapper = root_path / "python"
        python_wrapper.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
            f"if [ \"$1\" = server.py ]; then exec {sys.executable!r} {str(fake_server)!r}; fi\n"
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import secrets; print(secrets.token_urlsafe(32))\" ]; then\n"
            " printf '%s\\n' 'never-ready-token'; exit 0\n"
            "fi\n"
            f"exec {sys.executable!r} \"$@\"\n",
            encoding="utf-8",
        )
        python_wrapper.chmod(0o755)
        bin_dir = root_path / "bin"
        bin_dir.mkdir()
        sleep_wrapper = bin_dir / "sleep"
        sleep_wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        sleep_wrapper.chmod(0o755)
        environment = {
            **os.environ,
            "CORTEX_HOME": str(root_path / "cortex-home"),
            "PYTHON_BIN": str(python_wrapper),
            "PORT": str(port),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        environment.pop("PYTHONPATH", None)
        return environment, server_pid, bin_dir

    def _cleanup_test_process(self, pid_path: Path) -> None:
        if not pid_path.exists():
            return
        pid = int(pid_path.read_text(encoding="utf-8"))
        if self._pid_exists(pid):
            os.kill(pid, 9)
            self._wait_for_process_exit(pid)

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
                "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
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
                " pid=\"$(sed -E 's/.*\"pid\": ([0-9]+).*/\\1/' \"$CORTEX_HOME/pids/launch.pid\")\"\n"
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
                " pid=\"$(sed -E 's/.*\"pid\": ([0-9]+).*/\\1/' \"$CORTEX_HOME/pids/launch.pid\")\"\n"
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
                    "import fastapi,uvicorn,playwright,websockets",
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

    def test_start_cleans_up_when_ownership_capture_fails(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()

            environment, server_pid_path, capture_marker = self._capture_failure_environment(
                root_path, port
            )
            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=35,
                )

                self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
                self.assertEqual(capture_marker.read_text(encoding="utf-8"), "listener-confirmed")
                self.assertFalse((root_path / "cortex-home" / "pids" / "launch.pid").exists())
                server_pid = int(server_pid_path.read_text(encoding="utf-8"))
                self.assertTrue(
                    self._wait_for_process_exit(server_pid),
                    "launched server was left alive after ownership publication failed",
                )
                self.assertFalse(self._is_listening(port), "listener was left running after start failed")
            finally:
                self._cleanup_test_process(server_pid_path)

    def test_start_preserves_a_substituted_launch_record_and_foreign_process(self):
        from process_ownership import capture_identity

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            foreign_process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"]
            )
            self.addCleanup(
                lambda: (
                    foreign_process.kill(),
                    foreign_process.wait(timeout=5),
                )
                if foreign_process.poll() is None
                else None
            )
            foreign_payload = json.dumps(
                capture_identity(foreign_process.pid, port, "foreign-token"), sort_keys=True
            )
            substitute = root_path / "foreign-launch-record"
            substitute.write_text(foreign_payload, encoding="utf-8")
            expected_stat = substitute.stat()
            environment, server_pid_path, capture_marker = self._capture_failure_environment(
                root_path, port, substitute_record=substitute
            )
            launch_record = root_path / "cortex-home" / "pids" / "launch.pid"
            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=35,
                )

                self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
                self.assertEqual(capture_marker.read_text(encoding="utf-8"), "listener-confirmed")
                self.assertIsNone(foreign_process.poll(), "foreign process was signalled")
                self.assertEqual(launch_record.read_text(encoding="utf-8"), foreign_payload)
                actual_stat = launch_record.stat()
                self.assertEqual(
                    (actual_stat.st_dev, actual_stat.st_ino),
                    (expected_stat.st_dev, expected_stat.st_ino),
                    "substituted launch record was deleted or replaced",
                )
                server_pid = int(server_pid_path.read_text(encoding="utf-8"))
                self.assertTrue(
                    self._wait_for_process_exit(server_pid),
                    "exact launched server was left alive after record substitution",
                )
                self.assertFalse(self._is_listening(port), "launched listener was left running")
            finally:
                self._cleanup_test_process(server_pid_path)

    def test_start_cleans_up_when_readiness_expires(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            environment, server_pid_path, _bin_dir = self._never_ready_environment(
                root_path, port
            )
            launch_record = root_path / "cortex-home" / "pids" / "launch.pid"
            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(server_pid_path.exists(), "server launch marker was never written")
                server_pid = int(server_pid_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    (self._wait_for_process_exit(server_pid, timeout=2), launch_record.exists()),
                    (True, False),
                    "readiness timeout left the launched process or its exact launch record",
                )
                self.assertFalse(self._is_listening(port))
            finally:
                self._cleanup_test_process(server_pid_path)

    def test_slow_identity_probe_is_bounded_without_orphaning_launched_child(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            environment, server_pid_path, bin_dir = self._never_ready_environment(
                root_path, port
            )
            ps_wrapper = bin_dir / "ps"
            ps_wrapper.write_text("#!/bin/sh\nexec /bin/sleep 10\n", encoding="utf-8")
            ps_wrapper.chmod(0o755)
            command = ["bash", str(ROOT / "scripts" / "cortex.sh"), "start"]
            started_at = time.monotonic()
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            timed_out = False
            try:
                try:
                    stdout, stderr = process.communicate(timeout=6)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    stdout, stderr = process.communicate(timeout=5)
                elapsed = time.monotonic() - started_at

                self.assertFalse(
                    timed_out,
                    f"identity stabilization exceeded six seconds: {stdout}{stderr}",
                )
                self.assertEqual(process.returncode, 2, stdout + stderr)
                self.assertLess(elapsed, 3.0, f"identity stabilization took {elapsed:.3f}s")
                self.assertTrue(server_pid_path.exists(), "server child was never launched")
                server_pid = int(server_pid_path.read_text(encoding="utf-8"))
                self.assertTrue(
                    self._wait_for_process_exit(server_pid, timeout=2),
                    "slow identity probe left the launched child alive",
                )
                self.assertFalse(
                    (root_path / "cortex-home" / "pids" / "launch.pid").exists()
                )
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                self._cleanup_test_process(server_pid_path)

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
            "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
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
                "if [ \"$1\" = -c ] && [ \"$2\" = \"import fastapi,uvicorn,playwright,websockets\" ]; then exit 0; fi\n"
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
