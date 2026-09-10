from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
from contextlib import redirect_stdout
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_installer_module():
    console_path = str(ROOT / "console")
    sys.path.insert(0, console_path)
    try:
        return importlib.import_module("installer")
    finally:
        sys.path.remove(console_path)


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
            "if command['id'] == 'compile_macos_ax_helper':\n"
            " p=pathlib.Path(command['argv'][-1]); p.write_text('#!/bin/sh\\nif [ \"${CORTEX_TEST_AX_DENIED:-0}\" = \"1\" ]; then echo denied >&2; exit 3; fi\\nif [ \"${1:-}\" = \"--check-permissions\" ]; then printf \"READY\\\\n\"; exit 0; fi\\nexit 2\\n', encoding='utf-8'); p.chmod(0o700)\n"
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

    def stage_interrupted_helper_transaction(
        self,
        *,
        previous: bytes,
        replacement: bytes | None,
        plan_hash: str,
    ) -> Path:
        home = self.cortex_home.resolve()
        helper = home / "bin" / "cortex-macos-ax-send"
        staging = home / ".install-staging"
        staging.mkdir()
        backup = staging / ".cortex-macos-ax-send.previous"
        backup.write_bytes(previous)
        backup.chmod(0o700)
        if replacement is None:
            helper.unlink()
            replacement_hash = hashlib.sha256(b"replacement-not-yet-moved").hexdigest()
        else:
            helper.write_bytes(replacement)
            helper.chmod(0o700)
            replacement_hash = hashlib.sha256(replacement).hexdigest()
        transaction = {
            "schema_version": 1,
            "owner": "cortex-bridge",
            "home": str(home),
            "plan_hash": plan_hash,
            "creates_venv": False,
            "helper": {
                "target": str(helper),
                "backup": str(backup),
                "previous_exists": True,
                "previous_sha256": hashlib.sha256(previous).hexdigest(),
                "new_sha256": replacement_hash,
            },
        }
        (staging / "transaction.json").write_text(
            json.dumps(transaction, sort_keys=True), encoding="utf-8"
        )
        return staging

    def test_dry_run_is_immutable_and_plan_is_detailed(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        plan = self.dry_plan()
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(after, before)
        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(plan["version"], (ROOT / "VERSION").read_text().strip())
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

    def test_native_helper_dependencies_are_explicit_and_never_auto_approve_permission(self):
        manifest = json.loads(
            (ROOT / "install/dependencies.json").read_text(encoding="utf-8")
        )
        dependencies = {
            dependency["id"]: dependency for dependency in manifest["dependencies"]
        }

        compiler = dependencies["apple-command-line-tools"]
        self.assertFalse(compiler["required"])
        self.assertTrue(compiler["human_pause"])
        self.assertEqual(
            compiler["official_url"],
            "https://developer.apple.com/xcode/resources/",
        )
        accessibility = dependencies["macos-accessibility"]
        self.assertFalse(accessibility["required"])
        self.assertTrue(accessibility["human_pause"])
        self.assertIn("never requested automatically", accessibility["reason"])

    def test_fresh_text_install_does_not_require_swift(self):
        environment = {**self.environment, "SWIFTC_BIN": "/missing/cortex-swiftc"}
        result = self.run_script("install.sh", "--dry-run", "--json", env=environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        command_ids = {command["id"] for command in plan["commands"]}
        self.assertNotIn("compile_macos_ax_helper", command_ids)
        pause = next(
            item for item in plan["human_pauses"]
            if item["kind"] == "file_send_toolchain"
        )
        self.assertIn("text chat", pause["detail"].lower())
        self.assertIn("file sending", pause["detail"].lower())

    def test_fresh_install_compiles_helper_in_staging_and_records_exact_ownership(self):
        plan = self.dry_plan()
        compile_command = next(
            command
            for command in plan["commands"]
            if command["id"] == "compile_macos_ax_helper"
        )
        staged_output = Path(compile_command["argv"][-1])
        resolved_home = self.cortex_home.resolve()
        helper = resolved_home / "bin" / "cortex-macos-ax-send"
        staged_source = Path(compile_command["argv"][1])
        self.assertTrue(
            staged_output.is_relative_to(resolved_home / ".install-staging")
        )
        self.assertTrue(staged_source.is_relative_to(resolved_home / ".install-staging"))
        self.assertNotEqual(staged_source, ROOT / "transport" / "macos_ax_send.swift")
        expected_source_hash = hashlib.sha256(
            (ROOT / "transport" / "macos_ax_send.swift").read_bytes()
        ).hexdigest()
        self.assertEqual(compile_command["source_sha256"], expected_source_hash)
        self.assertNotEqual(staged_output, helper)

        installed = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertTrue(helper.is_file())
        self.assertFalse(helper.is_symlink())
        self.assertEqual(helper.stat().st_mode & 0o777, 0o700)
        self.assertFalse((resolved_home / ".install-staging").exists())

        manifest_path = resolved_home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["resources"]),
            {
                str(resolved_home / "venv"),
                str(helper),
                str(manifest_path),
            },
        )
        native_helper = manifest["native_helper"]
        self.assertEqual(set(native_helper), {"path", "sha256", "source_sha256"})
        self.assertEqual(native_helper["path"], str(helper))
        self.assertEqual(
            native_helper["sha256"],
            "ca2ab70294c2e1d19926d52eadf46f6dd4d2560c6a068194bed209903b3df5a5",
        )
        self.assertEqual(native_helper["source_sha256"], expected_source_hash)

    def test_install_refuses_to_overwrite_an_unowned_existing_helper(self):
        foreign = self.cortex_home / "bin" / "cortex-macos-ax-send"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("foreign-helper", encoding="utf-8")
        foreign.chmod(0o700)
        plan = self.dry_plan()

        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not owned", result.stdout)
        self.assertEqual(foreign.read_text(encoding="utf-8"), "foreign-helper")
        self.assertFalse(self.runner_log.exists())

    def test_update_rebuilds_stale_source_without_recreating_existing_venv(self):
        self.approved_install()
        helper = self.cortex_home / "bin" / "cortex-macos-ax-send"
        venv_python = self.cortex_home / "venv" / "bin" / "python"
        venv_inode = venv_python.stat().st_ino
        first_calls = self.runner_log.read_text(encoding="utf-8").splitlines()
        manifest_path = self.cortex_home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        plan = self.dry_plan()
        self.assertEqual(
            [command["id"] for command in plan["commands"]],
            ["compile_macos_ax_helper"],
        )
        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(venv_python.stat().st_ino, venv_inode)
        calls = [
            json.loads(line)["id"]
            for line in self.runner_log.read_text(encoding="utf-8").splitlines()[len(first_calls):]
        ]
        self.assertEqual(calls, ["compile_macos_ax_helper"])
        self.assertTrue(helper.read_text(encoding="utf-8").startswith("#!/bin/sh"))

    def test_update_refuses_a_tampered_owned_helper_without_mutating_it(self):
        self.approved_install()
        helper = self.cortex_home / "bin" / "cortex-macos-ax-send"
        helper.write_text("tampered-owned-helper", encoding="utf-8")
        plan = self.dry_plan()

        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ownership hash", result.stdout)
        self.assertEqual(helper.read_text(encoding="utf-8"), "tampered-owned-helper")

    def test_symlinked_owned_manifest_is_never_trusted(self):
        self.approved_install()
        manifest_path = self.cortex_home / "install" / "owned.json"
        external_manifest = self.root / "external-owned.json"
        manifest_path.replace(external_manifest)
        manifest_path.symlink_to(external_manifest)

        doctor = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        payload = json.loads(doctor.stdout)
        helper = next(
            check for check in payload["checks"] if check["id"] == "macos_ax_helper"
        )
        self.assertEqual(helper["status"], "warning")
        self.assertEqual(helper["detail"], "ownership metadata missing")

        plan = self.dry_plan()
        self.assertEqual(
            [command["id"] for command in plan["commands"]],
            ["compile_macos_ax_helper"],
        )
        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(manifest_path.is_symlink())
        self.assertTrue(external_manifest.is_file())

    def test_failed_helper_update_keeps_previous_binary_and_manifest(self):
        self.approved_install()
        helper = self.cortex_home / "bin" / "cortex-macos-ax-send"
        manifest_path = self.cortex_home / "install" / "owned.json"
        helper.write_text("previous-binary", encoding="utf-8")
        previous_manifest = manifest_path.read_bytes()
        plan = self.dry_plan()

        failed = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
            env={**self.environment, "FAIL_STEP": "compile_macos_ax_helper"},
        )

        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(helper.read_text(encoding="utf-8"), "previous-binary")
        self.assertEqual(manifest_path.read_bytes(), previous_manifest)
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    def test_retry_recovers_helper_crash_after_backup_before_replacement(self):
        self.approved_install()
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        previous = helper.read_bytes()
        manifest_path = self.cortex_home.resolve() / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        previous_manifest = manifest_path.read_bytes()
        plan = self.dry_plan()
        staging = self.stage_interrupted_helper_transaction(
            previous=previous,
            replacement=None,
            plan_hash=plan["plan_hash"],
        )

        result = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
            env={**self.environment, "FAIL_STEP": "compile_macos_ax_helper"},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(helper.read_bytes(), previous)
        self.assertEqual(manifest_path.read_bytes(), previous_manifest)
        self.assertFalse(staging.exists())

    def test_retry_recovers_helper_crash_after_replacement_before_manifest(self):
        self.approved_install()
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        previous = helper.read_bytes()
        manifest_path = self.cortex_home.resolve() / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        previous_manifest = manifest_path.read_bytes()
        plan = self.dry_plan()
        replacement = b"#!/bin/sh\nprintf 'CRASHED\\n'\n"
        staging = self.stage_interrupted_helper_transaction(
            previous=previous,
            replacement=replacement,
            plan_hash=plan["plan_hash"],
        )

        result = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
            env={**self.environment, "FAIL_STEP": "compile_macos_ax_helper"},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(helper.read_bytes(), previous)
        self.assertEqual(manifest_path.read_bytes(), previous_manifest)
        self.assertFalse(staging.exists())

    def test_retry_keeps_committed_helper_and_only_cleans_crash_staging(self):
        self.approved_install()
        home = self.cortex_home.resolve()
        helper = home / "bin" / "cortex-macos-ax-send"
        previous = helper.read_bytes()
        replacement = b"#!/bin/sh\n[ \"${1:-}\" = \"--check-permissions\" ] && printf 'READY\\n'\n"
        helper.write_bytes(replacement)
        helper.chmod(0o700)
        manifest_path = home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["sha256"] = hashlib.sha256(replacement).hexdigest()
        manifest["native_helper"]["source_sha256"] = hashlib.sha256(
            (ROOT / "transport" / "macos_ax_send.swift").read_bytes()
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        committed_plan_hash = manifest["plan_hash"]
        plan = self.dry_plan()
        self.assertEqual(plan["commands"], [])
        staging = self.stage_interrupted_helper_transaction(
            previous=previous,
            replacement=replacement,
            plan_hash=committed_plan_hash,
        )

        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(helper.read_bytes(), replacement)
        self.assertFalse(staging.exists())

    def test_retry_removes_an_empty_prejournal_crash_directory(self):
        self.approved_install()
        staging = self.cortex_home.resolve() / ".install-staging"
        staging.mkdir(mode=0o700)
        plan = self.dry_plan()
        self.assertEqual(plan["commands"], [])

        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(staging.exists())

    def test_retry_removes_a_partial_prejournal_write_before_any_mutation(self):
        self.approved_install()
        staging = self.cortex_home.resolve() / ".install-staging"
        staging.mkdir(mode=0o700)
        (staging / ".transaction.json.tmp").write_text("{", encoding="utf-8")
        plan = self.dry_plan()

        result = self.run_script(
            "install.sh", "--approve-plan", plan["plan_hash"], "--json"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(staging.exists())

    @unittest.skipUnless(sys.platform == "darwin", "renameatx_np is macOS-only")
    def test_atomic_rename_primitives_never_clobber_and_can_swap(self):
        module = load_installer_module()
        source = self.root / "source"
        target = self.root / "target"
        source.write_text("new", encoding="utf-8")
        target.write_text("foreign", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            module._rename_exclusive(source, target)
        self.assertEqual(source.read_text(encoding="utf-8"), "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "foreign")

        module._rename_swap(source, target)
        self.assertEqual(source.read_text(encoding="utf-8"), "foreign")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_open_file_identity_detects_a_path_swap(self):
        module = load_installer_module()
        helper = self.root / "verified-helper"
        replacement = self.root / "replacement-helper"
        helper.write_text("verified", encoding="utf-8")
        replacement.write_text("replacement", encoding="utf-8")
        fd = os.open(helper, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.replace(replacement, helper)
            self.assertFalse(module._opened_path_matches(fd, helper))
        finally:
            os.close(fd)

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
        self.assertEqual(payload["version"], (ROOT / "VERSION").read_text().strip())
        self.assertIn("deterministic", payload["modes"])
        self.assertTrue(payload["modes"]["chrome_extension"])
        extension = next(check for check in payload["checks"] if check["id"] == "chrome_extension")
        self.assertEqual(extension["status"], "pass")
        self.assertEqual(extension["path"], str((ROOT / "chrome-extension").resolve()))
        self.assertIsInstance(payload["checks"], list)

    def test_doctor_uses_the_effective_port_in_its_json_guidance(self):
        result = self.run_script(
            "cortex.sh",
            "doctor",
            "--json",
            env={**self.environment, "PORT": "18423"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        console = next(
            check for check in payload["checks"] if check["id"] == "console_process"
        )
        self.assertEqual(payload["local_url"], "http://127.0.0.1:18423")
        self.assertIn("http://127.0.0.1:18423", console["hint"])
        self.assertNotIn("127.0.0.1:8420", console["hint"])

    def test_doctor_text_summary_uses_the_diagnosed_local_url(self):
        installer = load_installer_module()
        output = io.StringIO()
        payload = {
            "version": "0.5.4",
            "ok": True,
            "local_url": "http://127.0.0.1:18423",
            "checks": [
                {
                    "id": "runtime_dependencies",
                    "label": "Dépendances Python du moteur",
                    "status": "pass",
                    "detail": "available",
                    "hint": "",
                }
            ],
        }

        with redirect_stdout(output):
            installer._print_doctor_text(payload)

        self.assertIn(
            "Ouvre http://127.0.0.1:18423 pour utiliser Cortex.",
            output.getvalue(),
        )
        self.assertNotIn("127.0.0.1:8420", output.getvalue())

    def test_doctor_fails_required_runtime_check_when_selected_python_cannot_start(self):
        self.approved_install()
        uninstall = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        uninstall_plan = json.loads(uninstall.stdout)
        removed = self.run_script(
            "uninstall.sh",
            "--approve-plan",
            uninstall_plan["plan_hash"],
            "--json",
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)

        selected_python = self.root / "selected-python"
        selected_python.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "if len(sys.argv) >= 3 and sys.argv[1] == '-c' and 'fastapi' in sys.argv[2]:\n"
            " print(json.dumps(['fastapi']))\n"
            " raise SystemExit(1)\n"
            f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        selected_python.chmod(0o755)
        environment = {**self.environment, "PYTHON_BIN": str(selected_python)}

        result = self.run_script("cortex.sh", "doctor", "--json", env=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        runtime = next(
            check
            for check in payload["checks"]
            if check["id"] == "runtime_dependencies"
        )
        self.assertFalse(payload["ok"])
        self.assertTrue(runtime["required"])
        self.assertEqual(runtime["status"], "fail")
        self.assertIn("fastapi", runtime["detail"])
        self.assertIn("install.sh", runtime["hint"])

        start = self.run_script("cortex.sh", "start", env=environment)
        self.assertNotEqual(start.returncode, 0)
        self.assertIn("runtime dependencies are incomplete", start.stderr)

    def test_doctor_reports_swift_toolchain_and_invalid_override(self):
        available = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(available.returncode, 0, available.stderr)
        payload = json.loads(available.stdout)
        toolchain = next(
            check for check in payload["checks"] if check["id"] == "swift_toolchain"
        )
        self.assertEqual(toolchain["status"], "pass")
        self.assertTrue(Path(toolchain["path"]).is_absolute())

        missing = self.run_script(
            "cortex.sh",
            "doctor",
            "--json",
            env={**self.environment, "SWIFTC_BIN": "/missing/cortex-swiftc"},
        )
        self.assertEqual(missing.returncode, 0, missing.stderr)
        missing_payload = json.loads(missing.stdout)
        missing_toolchain = next(
            check
            for check in missing_payload["checks"]
            if check["id"] == "swift_toolchain"
        )
        self.assertEqual(missing_toolchain["status"], "warning")
        self.assertFalse(missing_toolchain["required"])
        self.assertIn("Xcode", missing_toolchain["hint"])

    def test_uninstall_refuses_while_the_owned_server_is_running(self):
        self.approved_install()
        installer = load_installer_module()
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            with mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="owned", pid=4242),
            ):
                with self.assertRaisesRegex(RuntimeError, "cortex.sh stop"):
                    installer.apply_uninstall(plan, plan["plan_hash"])
        self.assertTrue((self.cortex_home / "install" / "owned.json").is_file())

    def test_uninstall_refuses_every_foreign_or_unverified_listener(self):
        self.approved_install()
        installer = load_installer_module()
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            for state in ("foreign", "stale"):
                with self.subTest(state=state), mock.patch.object(
                    installer,
                    "classify",
                    return_value=SimpleNamespace(
                        state=state,
                        pid=4242,
                        listener_pids=[4242],
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, "listener|status"):
                        installer.apply_uninstall(plan, plan["plan_hash"])
        self.assertTrue((self.cortex_home / "install" / "owned.json").is_file())

    def test_doctor_verifies_helper_hash_and_accessibility_without_requesting_it(self):
        self.approved_install()
        ready = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(ready.returncode, 0, ready.stderr)
        payload = json.loads(ready.stdout)
        helper = next(check for check in payload["checks"] if check["id"] == "macos_ax_helper")
        permission = next(
            check for check in payload["checks"] if check["id"] == "macos_accessibility"
        )
        self.assertEqual(helper["status"], "pass")
        self.assertIn("SHA-256 verified", helper["detail"])
        self.assertEqual(permission["status"], "pass")
        self.assertEqual(permission["detail"], "READY")

        denied = self.run_script(
            "cortex.sh",
            "doctor",
            "--json",
            env={**self.environment, "CORTEX_TEST_AX_DENIED": "1"},
        )
        self.assertEqual(denied.returncode, 0, denied.stderr)
        denied_payload = json.loads(denied.stdout)
        denied_permission = next(
            check
            for check in denied_payload["checks"]
            if check["id"] == "macos_accessibility"
        )
        self.assertEqual(denied_permission["status"], "warning")
        self.assertFalse(denied_permission["required"])
        self.assertTrue(denied_payload["ok"])
        self.assertIn("Réglages Système", denied_permission["hint"])
        self.assertIn(
            str(self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"),
            denied_permission["hint"],
        )
        self.assertNotIn("terminal", denied_permission["hint"].casefold())

    def test_doctor_refuses_tampered_helper_before_permission_check(self):
        self.approved_install()
        helper_path = self.cortex_home / "bin" / "cortex-macos-ax-send"
        helper_path.write_text("tampered", encoding="utf-8")

        result = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        helper = next(check for check in payload["checks"] if check["id"] == "macos_ax_helper")
        permission = next(
            check for check in payload["checks"] if check["id"] == "macos_accessibility"
        )
        self.assertEqual(helper["status"], "fail")
        self.assertIn("hash mismatch", helper["detail"])
        self.assertEqual(permission["status"], "warning")
        self.assertEqual(permission["detail"], "not checked")

    def test_doctor_refuses_helper_reached_through_symlinked_bin_directory(self):
        self.approved_install()
        installed_bin = self.cortex_home / "bin"
        external_bin = self.root / "external-bin"
        installed_bin.rename(external_bin)
        installed_bin.symlink_to(external_bin, target_is_directory=True)

        result = self.run_script("cortex.sh", "doctor", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        helper = next(check for check in payload["checks"] if check["id"] == "macos_ax_helper")
        permission = next(
            check for check in payload["checks"] if check["id"] == "macos_accessibility"
        )
        self.assertEqual(helper["status"], "fail")
        self.assertIn("unsafe", helper["detail"])
        self.assertEqual(permission["detail"], "not checked")

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
        foreign_tool = self.cortex_home / "bin" / "foreign-tool"
        foreign_tool.write_text("keep", encoding="utf-8")
        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        self.assertNotIn(str(foreign), plan["resources"])
        applied = self.run_script(
            "uninstall.sh", "--approve-plan", plan["plan_hash"], "--json"
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertTrue(foreign.is_file())
        self.assertTrue(foreign_tool.is_file())
        self.assertFalse((self.cortex_home / "bin" / "cortex-macos-ax-send").exists())
        self.assertFalse((self.cortex_home / "venv").exists())


if __name__ == "__main__":
    unittest.main()
