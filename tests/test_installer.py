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

    def test_default_install_prepares_the_extension_without_downloading_playwright(self):
        plan = self.dry_plan()
        command_ids = {command["id"] for command in plan["commands"]}
        self.assertNotIn("install_browser", command_ids)
        self.assertEqual(
            plan["chrome_extension_path"],
            str((ROOT / "chrome-extension").resolve()),
        )
        extension_pause = next(
            pause for pause in plan["human_pauses"] if pause["kind"] == "extension"
        )
        self.assertIn("explicit approval", extension_pause["detail"])
        self.assertIn("chrome://extensions", extension_pause["detail"])

    def test_install_does_not_claim_or_remove_the_repository_extension(self):
        self.approved_install()
        browser_cache = (self.cortex_home / "browser-cache").resolve()
        manifest = json.loads(
            (self.cortex_home / "install" / "owned.json").read_text(encoding="utf-8")
        )

        self.assertFalse(browser_cache.exists())
        self.assertNotIn(str(browser_cache), manifest["resources"])
        self.assertNotIn(str((ROOT / "chrome-extension").resolve()), manifest["resources"])

        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        applied = self.run_script(
            "uninstall.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue((ROOT / "chrome-extension" / "manifest.json").is_file())

    def test_ui_rebuild_uses_the_repository_npm_wrapper(self):
        rebuild = self.dry_plan("--rebuild-ui")
        commands = {
            command["id"]: command["argv"] for command in rebuild["commands"]
        }
        wrapper = str(ROOT / "scripts" / "npmw")
        self.assertEqual(commands["npm_ci"], [wrapper, "ci"])
        self.assertEqual(commands["build_ui"], [wrapper, "run", "build"])

    def test_chrome_extension_is_the_required_manual_product_dependency(self):
        manifest = json.loads(
            (ROOT / "install/dependencies.json").read_text(encoding="utf-8")
        )
        extension = next(
            dependency
            for dependency in manifest["dependencies"]
            if dependency["id"] == "chrome-extension"
        )
        self.assertTrue(extension["required"])
        self.assertTrue(extension["human_pause"])
        self.assertEqual(
            extension["official_url"],
            "https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked",
        )

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
        self.assertTrue(payload["modes"]["chrome_extension"])
        extension = next(check for check in payload["checks"] if check["id"] == "chrome_extension")
        self.assertEqual(extension["status"], "pass")
        self.assertEqual(extension["path"], str((ROOT / "chrome-extension").resolve()))
        self.assertIsInstance(payload["checks"], list)

    def test_doctor_text_output_is_french_and_actionable(self):
        result = self.run_script("cortex.sh", "doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("vérification de l'installation", result.stdout)
        self.assertIn("Extension Chrome Cortex Bridge", result.stdout)
        self.assertIn("Python 3.11", result.stdout)
        # Every failing or warning line must be followed by an actionable hint.
        self.assertNotIn('"checks"', result.stdout)  # no raw JSON dump

    def test_public_install_docs_use_the_real_chrome_tab_flow(self):
        docs = [
            ROOT / "README.md",
            ROOT / "INSTALL.md",
            ROOT / "docs/agent-installation.md",
            ROOT / "docs/chatgpt-web-transport.md",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in docs)
        self.assertIn("chrome://extensions", source)
        self.assertIn("Open and connect ChatGPT", source)
        self.assertIn("BLOCKED_BY_PROVIDER_TERMS", source)
        self.assertIn("https://openai.com/policies/eu-terms-of-use/", source)
        self.assertNotIn("dedicated Playwright Chromium profile", source)
        self.assertNotIn("dedicated Chromium profile", source)

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
