from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home"
        self.cortex_home = self.root / "cortex"
        self.runner_log = self.root / "runner.jsonl"
        self.runner = self.root / "runner.py"
        self.runner.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys\n"
            "command=json.loads(sys.argv[1])\n"
            "with open(os.environ['RUNNER_LOG'], 'a', encoding='utf-8') as f: f.write(json.dumps(command, sort_keys=True)+'\\n')\n"
            "if os.environ.get('FAIL_STEP') == command['id']: raise SystemExit(9)\n"
            "if command['id'] == 'create_venv':\n"
            " p=pathlib.Path(command['argv'][-1]); (p/'bin').mkdir(parents=True, exist_ok=True); (p/'bin'/'python').write_text('fixture', encoding='utf-8')\n"
            "if command['id'] == 'install_browser':\n"
            " p=command.get('environment', {}).get('PLAYWRIGHT_BROWSERS_PATH')\n"
            " if p:\n"
            "  cache=pathlib.Path(p); cache.mkdir(parents=True, exist_ok=True); (cache/'browser-fixture').write_text('fixture', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.runner.chmod(0o755)
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "CORTEX_HOME": str(self.cortex_home),
            "PYTHON_BIN": sys.executable,
            "CORTEX_INSTALL_RUNNER": str(self.runner),
            "RUNNER_LOG": str(self.runner_log),
        }

    def run_script(self, name: str, *args: str, env: dict[str, str] | None = None):
        return subprocess.run(
            [str(ROOT / "scripts" / name), *args],
            cwd=ROOT,
            env=env or self.environment,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def dry_plan(self, *extra: str) -> dict:
        result = self.run_script("install.sh", "--dry-run", "--json", *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def approved_install(self) -> dict:
        plan = self.dry_plan()
        result = self.run_script("install.sh", "--approve-plan", plan["plan_hash"], "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_dry_run_is_immutable_and_plan_is_detailed(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        plan = self.dry_plan()
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(after, before)
        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(plan["version"], "0.5.0")
        self.assertEqual(len(plan["plan_hash"]), 64)
        self.assertTrue(plan["commands"])
        for command in plan["commands"]:
            self.assertTrue(command["argv"])
            self.assertTrue(command["official_url"].startswith("https://"))
            self.assertGreaterEqual(command["disk_bytes"], 0)
            self.assertTrue(command["rollback"])
            self.assertNotIn("sudo", command["argv"])
        pause_kinds = {pause["kind"] for pause in plan["human_pauses"]}
        self.assertTrue({"login", "terms", "extension", "secrets", "privilege"} <= pause_kinds)

    def test_plan_hash_changes_when_commands_change(self):
        normal = self.dry_plan()
        rebuild = self.dry_plan("--rebuild-ui")
        self.assertNotEqual(normal["plan_hash"], rebuild["plan_hash"])
        self.assertNotEqual(normal["commands"], rebuild["commands"])

    def test_browser_download_is_declared_inside_owned_staging(self):
        plan = self.dry_plan()
        browser = next(command for command in plan["commands"] if command["id"] == "install_browser")

        self.assertEqual(
            browser.get("environment"),
            {
                "PLAYWRIGHT_BROWSERS_PATH": str(
                    (self.cortex_home / ".install-staging" / "browser-cache").resolve()
                )
            },
        )

    def test_browser_runtime_is_moved_owned_and_removed(self):
        self.approved_install()
        browser_cache = (self.cortex_home / "browser-cache").resolve()
        manifest = json.loads(
            (self.cortex_home / "install" / "owned.json").read_text(encoding="utf-8")
        )

        self.assertTrue((browser_cache / "browser-fixture").is_file())
        self.assertIn(str(browser_cache), manifest["resources"])

        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        applied = self.run_script(
            "uninstall.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertFalse(browser_cache.exists())

    def test_ui_rebuild_uses_the_repository_npm_wrapper(self):
        rebuild = self.dry_plan("--rebuild-ui")
        commands = {
            command["id"]: command["argv"] for command in rebuild["commands"]
        }
        wrapper = str(ROOT / "scripts" / "npmw")
        self.assertEqual(commands["npm_ci"], [wrapper, "ci"])
        self.assertEqual(commands["build_ui"], [wrapper, "run", "build"])

    def test_webbridge_has_no_fake_official_distribution_link(self):
        manifest = json.loads(
            (ROOT / "install/dependencies.json").read_text(encoding="utf-8")
        )
        webbridge = next(
            dependency
            for dependency in manifest["dependencies"]
            if dependency["id"] == "webbridge"
        )
        self.assertIsNone(webbridge["official_url"])
        self.assertIn("no public official distribution", webbridge["reason"])

    def test_wrong_or_missing_approval_never_mutates_target(self):
        result = self.run_script("install.sh", "--approve-plan", "0" * 64, "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.cortex_home.exists())
        self.assertFalse(self.runner_log.exists())

    def test_approved_install_and_reinstall_are_idempotent(self):
        installed = self.approved_install()
        self.assertEqual(installed["status"], "installed")
        manifest = self.cortex_home / "install" / "owned.json"
        self.assertTrue(manifest.is_file())
        first_calls = self.runner_log.read_text(encoding="utf-8").splitlines()
        self.assertTrue(first_calls)

        second_plan = self.dry_plan()
        self.assertEqual(second_plan["commands"], [])
        second = self.run_script(
            "install.sh", "--approve-plan", second_plan["plan_hash"], "--json"
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            self.runner_log.read_text(encoding="utf-8").splitlines(),
            first_calls,
        )

    def test_interruption_rolls_back_only_staging(self):
        self.cortex_home.mkdir(parents=True)
        foreign = self.cortex_home / "keep-me.txt"
        foreign.write_text("foreign", encoding="utf-8")
        plan = self.dry_plan()
        environment = {**self.environment, "FAIL_STEP": "install_python"}
        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json", env=environment
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(foreign.is_file())
        self.assertFalse((self.cortex_home / ".install-staging").exists())
        self.assertFalse((self.cortex_home / "install" / "owned.json").exists())

    def test_doctor_json_is_stable_without_optional_services(self):
        result = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["version"], "0.5.0")
        self.assertIn("deterministic", payload["modes"])
        self.assertIsInstance(payload["checks"], list)

    def test_uninstall_removes_only_manifest_owned_resources(self):
        self.approved_install()
        foreign = self.cortex_home / "user-data.txt"
        foreign.write_text("keep", encoding="utf-8")
        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        self.assertNotIn(str(foreign), plan["resources"])
        applied = self.run_script(
            "uninstall.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(foreign.is_file())
        self.assertFalse((self.cortex_home / "venv").exists())


if __name__ == "__main__":
    unittest.main()
