from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))


class ProcessOwnershipTest(unittest.TestCase):
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
        environment = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "BASH_ENV": str(bash_env),
            "CORTEX_HOME": str(root / "cortex-home"),
            "PYTHON_BIN": sys.executable,
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


if __name__ == "__main__":
    unittest.main()
