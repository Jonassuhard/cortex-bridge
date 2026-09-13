import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LifecycleTests(unittest.TestCase):
    def test_failure_after_archive_then_explicit_recovery(self):
        candidate = self.root / "candidate"
        self.install(candidate)
        plan = self.call("--replacement", str(candidate))
        self.assertEqual(plan.returncode, 0, plan.stdout)
        command = [str(ROOT / "scripts/supervisor-lifecycle.py"),
                   "--skills-root", str(self.skills), "--target", str(self.target),
                   "--archive", str(self.archive), "--replacement", str(candidate),
                   "--approve-plan", json.loads(plan.stdout)["plan_hash"]]
        inject = '''
import os, runpy, sys
original = os.rename
calls = 0
def rename(source, destination):
    global calls
    calls += 1
    if calls == 2:
        raise OSError("injected activation interruption")
    return original(source, destination)
os.rename = rename
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        failed = subprocess.run([sys.executable, "-c", inject, *command], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["phase"], "old_archived")
        self.assertFalse(self.target.exists())
        self.assertTrue((self.archive / "SKILL.md").is_file())
        self.assertTrue((candidate / "SKILL.md").is_file())
        recovery = self.call("--replacement", str(candidate), "--recover-activation")
        self.assertEqual(recovery.returncode, 0, recovery.stdout + recovery.stderr)
        done = self.call("--replacement", str(candidate), "--recover-activation", "--approve-plan",
                         json.loads(recovery.stdout)["plan_hash"])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((self.target / "SKILL.md").is_file())
        self.assertTrue((self.archive / "SKILL.md").is_file())
        self.assertFalse(candidate.exists())

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.skills = self.root / "skills"
        self.skills.mkdir()
        self.target = self.skills / "cortex-supervisor"
        self.archive = self.root / "archived"
        self.install(self.target)

    def install(self, target):
        cmd = [sys.executable, str(ROOT / "scripts/install-supervisor.py"), "--target", str(target)]
        plan = subprocess.run(cmd, capture_output=True, text=True, check=True)
        subprocess.run(cmd + ["--approve-plan", json.loads(plan.stdout)["plan_hash"]], capture_output=True, text=True, check=True)

    def call(self, *extra):
        return subprocess.run([sys.executable, str(ROOT / "scripts/supervisor-lifecycle.py"),
                               "--skills-root", str(self.skills), "--target", str(self.target),
                               "--archive", str(self.archive), *extra], capture_output=True, text=True)

    def test_uninstall_archives_owned_bytes_and_preserves_unrelated(self):
        unrelated = self.skills / "unrelated.txt"
        unrelated.write_text("keep")
        before = (self.target / "SKILL.md").read_bytes()
        plan = self.call()
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        self.assertTrue(self.target.exists())
        applied = self.call("--approve-plan", json.loads(plan.stdout)["plan_hash"])
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertFalse(self.target.exists())
        self.assertEqual((self.archive / "SKILL.md").read_bytes(), before)
        self.assertEqual(unrelated.read_text(), "keep")

    def test_update_and_subsequent_uninstall(self):
        candidate = self.root / "candidate"
        self.install(candidate)
        before = (self.target / "SKILL.md").read_bytes()
        plan = self.call("--replacement", str(candidate))
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        result = self.call("--replacement", str(candidate), "--approve-plan", json.loads(plan.stdout)["plan_hash"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(candidate.exists())
        self.assertEqual((self.archive / "SKILL.md").read_bytes(), before)
        self.archive = self.root / "archived-new"
        plan = self.call()
        self.assertEqual(plan.returncode, 0, plan.stdout)
        self.assertEqual(self.call("--approve-plan", json.loads(plan.stdout)["plan_hash"]).returncode, 0)

    def test_changed_or_unowned_files_refuse_without_moving(self):
        plan = self.call()
        self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
        (self.target / "user-note.txt").write_text("retain")
        result = self.call("--approve-plan", json.loads(plan.stdout)["plan_hash"])
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.target.exists())
        self.assertFalse(self.archive.exists())

    def test_owned_file_change_refused(self):
        (self.target / "SKILL.md").write_text("user edited skill")
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.target.exists())
        self.assertFalse(self.archive.exists())

    def test_hard_exit_after_first_move_and_occupied_target_refused(self):
        candidate = self.root / "candidate"
        self.install(candidate)
        plan = self.call("--replacement", str(candidate))
        command = [str(ROOT / "scripts/supervisor-lifecycle.py"),
                   "--skills-root", str(self.skills), "--target", str(self.target),
                   "--archive", str(self.archive), "--replacement", str(candidate),
                   "--approve-plan", json.loads(plan.stdout)["plan_hash"]]
        inject = '''
import os, runpy, sys
original = os.rename
def rename(source, destination):
    original(source, destination)
    os._exit(17)
os.rename = rename
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        failed = subprocess.run([sys.executable, "-c", inject, *command], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 17)
        recovery = self.call("--replacement", str(candidate), "--recover-activation")
        self.assertEqual(recovery.returncode, 0, recovery.stdout)
        # Another actor re-creates the active location after review.
        self.target.mkdir()
        (self.target / "user-file").write_text("never overwrite")
        refused = self.call("--replacement", str(candidate), "--recover-activation",
                            "--approve-plan", json.loads(recovery.stdout)["plan_hash"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual((self.target / "user-file").read_text(), "never overwrite")
        self.assertTrue(candidate.exists())
        self.assertTrue(self.archive.exists())

    def test_recovery_changed_candidate_refused(self):
        candidate = self.root / "candidate"
        self.install(candidate)
        self.target.rename(self.archive)
        recovery = self.call("--replacement", str(candidate), "--recover-activation")
        self.assertEqual(recovery.returncode, 0, recovery.stdout)
        (candidate / "SKILL.md").write_text("changed after review")
        refused = self.call("--replacement", str(candidate), "--recover-activation",
                            "--approve-plan", json.loads(recovery.stdout)["plan_hash"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.archive.exists())

    def test_wrong_approval_and_archive_in_discovery_refused(self):
        result = self.call("--approve-plan", "wrong")
        self.assertNotEqual(result.returncode, 0)
        self.archive = self.skills / "archived"
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.archive.exists())
        self.assertTrue(self.target.exists())

    def test_archive_never_overwrites_existing_destination(self):
        self.archive.mkdir()
        (self.archive / "keep").write_text("preserve")
        self.assertNotEqual(self.call().returncode, 0)
        self.assertEqual((self.archive / "keep").read_text(), "preserve")
        self.assertTrue(self.target.exists())
