from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import fcntl
import socket
import stat
from contextlib import redirect_stdout
import subprocess
import sys
import tempfile
import time
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
            " p=pathlib.Path(command['argv'][-1]); (p/'bin').mkdir(parents=True, exist_ok=True); python_path=p/'bin'/'python'; python_path.symlink_to(sys.executable)\n"
            " for name in ('pip', 'uvicorn', 'playwright'):\n"
            "  entry=p/'bin'/name; entry.write_text(f'#!{python_path}\\nimport pathlib\\nprint(pathlib.Path(__file__).name)\\n', encoding='utf-8'); entry.chmod(0o755)\n"
            "if command['id'] == 'compile_macos_ax_helper':\n"
            " p=pathlib.Path(command['argv'][-1]); p.write_text('#!/bin/sh\\nif [ \"${CORTEX_TEST_AX_DENIED:-0}\" = \"1\" ]; then echo denied >&2; exit 3; fi\\nif [ \"${1:-}\" = \"--check-permissions\" ]; then printf \"READY\\\\n\"; exit 0; fi\\nexit 2\\n', encoding='utf-8'); p.chmod(0o700)\n"
            "if command['id'] == 'install_browser':\n"
            " p=command.get('environment', {}).get('PLAYWRIGHT_BROWSERS_PATH')\n"
            " if p:\n"
            "  cache=pathlib.Path(p); cache.mkdir(parents=True, exist_ok=True); (cache/'browser-fixture').write_text('fixture', encoding='utf-8')\n",
            encoding="utf-8",
        )
        self.runner.chmod(0o755)
        with socket.socket() as available_port:
            available_port.bind(("127.0.0.1", 0))
            isolated_port = str(available_port.getsockname()[1])
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "CORTEX_HOME": str(self.cortex_home),
            "PORT": isolated_port,
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

    def break_installed_entrypoints_with_staging_shebangs(self) -> None:
        installed_bin = self.cortex_home.resolve() / "venv" / "bin"
        staged_bin = self.cortex_home.resolve() / ".install-staging" / "venv" / "bin"
        for name in ("pip", "uvicorn", "playwright"):
            entrypoint = installed_bin / name
            content = entrypoint.read_text(encoding="utf-8")
            entrypoint.write_text(
                content.replace(str(installed_bin), str(staged_bin)),
                encoding="utf-8",
            )
            entrypoint.chmod(0o755)

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
        manifest = json.loads(
            (home / "install" / "owned.json").read_text(encoding="utf-8")
        )
        committed = manifest.get("plan_hash") == plan_hash
        if committed:
            if replacement is None:
                raise ValueError("committed helper fixture requires a replacement")
            backup.write_bytes(previous)
            backup.chmod(0o700)
            previous_identity = (backup.stat().st_dev, backup.stat().st_ino)
            replacement_hash = hashlib.sha256(replacement).hexdigest()
            replacement_identity = (helper.stat().st_dev, helper.stat().st_ino)
        else:
            previous_identity = (helper.stat().st_dev, helper.stat().st_ino)
            helper.rename(backup)
            if replacement is None:
                replacement_hash = hashlib.sha256(
                    b"replacement-not-yet-moved"
                ).hexdigest()
                replacement_identity = (None, None)
            else:
                helper.write_bytes(replacement)
                helper.chmod(0o700)
                replacement_hash = hashlib.sha256(replacement).hexdigest()
                replacement_identity = (helper.stat().st_dev, helper.stat().st_ino)
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
                "previous_dev": previous_identity[0],
                "previous_ino": previous_identity[1],
                "new_sha256": replacement_hash,
                "new_dev": replacement_identity[0],
                "new_ino": replacement_identity[1],
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
        self.assertEqual(plan["version"], "0.5.4")
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
        self.assertEqual(
            set(native_helper),
            {"path", "sha256", "source_sha256", "dev", "ino"},
        )
        self.assertEqual(native_helper["path"], str(helper))
        self.assertEqual(
            native_helper["sha256"],
            "ca2ab70294c2e1d19926d52eadf46f6dd4d2560c6a068194bed209903b3df5a5",
        )
        self.assertEqual(native_helper["source_sha256"], expected_source_hash)

    def test_fresh_install_rehomes_python_entrypoints_before_atomic_rename(self):
        self.approved_install()
        installed_bin = self.cortex_home.resolve() / "venv" / "bin"
        expected_shebang = f"#!{installed_bin / 'python'}"

        for name in ("pip", "uvicorn", "playwright"):
            with self.subTest(name=name):
                entrypoint = installed_bin / name
                first_line = entrypoint.read_text(encoding="utf-8").splitlines()[0]
                self.assertEqual(first_line, expected_shebang)
                self.assertNotIn(".install-staging", first_line)
                executed = subprocess.run(
                    [str(entrypoint)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(executed.returncode, 0, executed.stderr)
                self.assertEqual(executed.stdout.strip(), name)

    def test_existing_staging_shebangs_trigger_atomic_repair_then_become_idempotent(self):
        self.approved_install()
        old_venv = self.cortex_home.resolve() / "venv"
        old_inode = old_venv.stat().st_ino
        manifest_path = self.cortex_home / "install" / "owned.json"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest.pop("venv", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        self.break_installed_entrypoints_with_staging_shebangs()

        repair_plan = self.dry_plan()
        self.assertEqual(repair_plan["venv_action"], "rebuild_legacy")
        self.assertEqual(
            [command["id"] for command in repair_plan["commands"]],
            ["create_venv", "install_python"],
        )
        preserved_venv = Path(
            repair_plan["metadata_migration"]["venv"]["preserve_path"]
        )
        repaired = self.run_script(
            "install.sh",
            "--approve-plan",
            repair_plan["plan_hash"],
            "--json",
        )

        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertNotEqual(old_venv.stat().st_ino, old_inode)
        self.assertEqual(preserved_venv.stat().st_ino, old_inode)
        installed_bin = old_venv / "bin"
        for name in ("pip", "uvicorn", "playwright"):
            with self.subTest(name=name):
                entrypoint = installed_bin / name
                first_line = entrypoint.read_text(encoding="utf-8").splitlines()[0]
                self.assertNotIn(".install-staging", first_line)
                executed = subprocess.run(
                    [str(entrypoint)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertFalse((self.cortex_home / ".install-staging").exists())

        second_plan = self.dry_plan()
        self.assertEqual(second_plan["venv_action"], "none")
        self.assertEqual(second_plan["commands"], [])

    @unittest.skipUnless(sys.platform == "darwin", "installer ownership is macOS-only")
    def test_healthy_legacy_install_migrates_exact_ownership_then_uninstalls(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        venv = home / "venv"
        helper = home / "bin" / "cortex-macos-ax-send"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest["legacy_marker"] = "preserve"
        legacy_manifest.pop("venv", None)
        legacy_manifest["native_helper"].pop("dev", None)
        legacy_manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        expected_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            migration = plan["metadata_migration"]
            self.assertEqual(plan["venv_action"], "rebuild_legacy")
            self.assertEqual(
                [command["id"] for command in plan["commands"]],
                ["create_venv", "install_python", "compile_macos_ax_helper"],
            )
            self.assertEqual(
                migration["manifest"],
                {
                    "path": str(manifest_path),
                    "dev": manifest_path.stat().st_dev,
                    "ino": manifest_path.stat().st_ino,
                    "sha256": expected_manifest_hash,
                },
            )
            self.assertEqual(
                {
                    key: migration["venv"][key]
                    for key in ("action", "path", "dev", "ino")
                },
                {
                    "action": "rebuild_preserve",
                    "path": str(venv),
                    "dev": venv.stat().st_dev,
                    "ino": venv.stat().st_ino,
                },
            )
            preserved_venv = Path(migration["venv"]["preserve_path"])
            preserved_helper = Path(migration["native_helper"]["preserve_path"])
            self.assertEqual(migration["native_helper"]["path"], str(helper))
            self.assertEqual(
                migration["native_helper"]["action"],
                "rebuild_preserve",
            )
            self.assertEqual(migration["native_helper"]["dev"], helper.stat().st_dev)
            self.assertEqual(migration["native_helper"]["ino"], helper.stat().st_ino)
            self.assertEqual(
                migration["native_helper"]["sha256"],
                hashlib.sha256(helper.read_bytes()).hexdigest(),
            )

            migrated = installer.apply_install(plan, plan["plan_hash"])
            self.assertEqual(migrated["status"], "installed")
            upgraded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(upgraded_manifest["legacy_marker"], "preserve")
            self.assertEqual(
                upgraded_manifest["venv"],
                {
                    "path": str(venv),
                    "dev": venv.stat().st_dev,
                    "ino": venv.stat().st_ino,
                },
            )
            self.assertNotEqual(venv.stat().st_ino, migration["venv"]["ino"])
            self.assertNotEqual(helper.stat().st_ino, migration["native_helper"]["ino"])
            self.assertEqual(preserved_venv.stat().st_ino, migration["venv"]["ino"])
            self.assertEqual(
                preserved_helper.stat().st_ino,
                migration["native_helper"]["ino"],
            )

            uninstall_plan = installer.build_uninstall_plan()
            with mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="stopped", listener_pids=[]),
            ):
                result = installer.apply_uninstall(
                    uninstall_plan,
                    uninstall_plan["plan_hash"],
                )

        self.assertEqual(result["status"], "uninstalled")
        self.assertFalse(venv.exists())
        self.assertFalse(helper.exists())
        self.assertFalse(manifest_path.exists())
        self.assertTrue(preserved_venv.is_dir())
        self.assertTrue(preserved_helper.is_file())

    @unittest.skipUnless(sys.platform == "darwin", "legacy reconstruction is macOS-only")
    def test_legacy_upgrade_never_adopts_valid_looking_foreign_resources_before_plan(self):
        self.approved_install()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        venv = home / "venv"
        helper = home / "bin" / "cortex-macos-ax-send"
        displaced_venv = self.root / "pre-plan-owned-venv"
        displaced_helper = self.root / "pre-plan-owned-helper"
        venv.rename(displaced_venv)
        helper.rename(displaced_helper)

        (venv / "bin").mkdir(parents=True)
        for name in ("pip", "uvicorn", "playwright"):
            entrypoint = venv / "bin" / name
            entrypoint.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            entrypoint.chmod(0o755)
        sentinel = venv / "foreign-sentinel.txt"
        sentinel.write_text("never delete or adopt", encoding="utf-8")
        helper.write_bytes(displaced_helper.read_bytes())
        helper.chmod(0o700)
        foreign_helper_identity = (helper.stat().st_dev, helper.stat().st_ino)

        manifest.pop("venv", None)
        manifest["native_helper"].pop("dev", None)
        manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        plan = self.dry_plan()
        installed = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
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

        preserved_sentinels = list(home.rglob("foreign-sentinel.txt"))
        self.assertEqual(len(preserved_sentinels), 1)
        self.assertEqual(
            preserved_sentinels[0].read_text(encoding="utf-8"),
            "never delete or adopt",
        )
        preserved_helpers = [
            path
            for path in home.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and (path.stat().st_dev, path.stat().st_ino) == foreign_helper_identity
        ]
        self.assertEqual(len(preserved_helpers), 1)
        self.assertNotIn(str(preserved_sentinels[0].parent), uninstall_plan["resources"])
        self.assertNotIn(str(preserved_helpers[0]), uninstall_plan["resources"])

    @unittest.skipUnless(sys.platform == "darwin", "legacy recovery is macOS-only")
    def test_legacy_reconstruction_crash_restores_untrusted_resources_without_deleting_them(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        venv = home / "venv"
        helper = home / "bin" / "cortex-macos-ax-send"
        sentinel = venv / "legacy-sentinel.txt"
        sentinel.write_text("survive rollback", encoding="utf-8")
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_manifest.pop("venv", None)
        old_manifest["native_helper"].pop("dev", None)
        old_manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(old_manifest), encoding="utf-8")
        old_manifest_bytes = manifest_path.read_bytes()
        old_venv_identity = (venv.stat().st_dev, venv.stat().st_ino)
        old_helper_identity = (helper.stat().st_dev, helper.stat().st_ino)

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            preserved_venv = Path(
                plan["metadata_migration"]["venv"]["preserve_path"]
            )
            preserved_helper = Path(
                plan["metadata_migration"]["native_helper"]["preserve_path"]
            )
            with mock.patch.object(
                installer,
                "_publish_manifest_replacement",
                side_effect=RuntimeError("simulated crash before manifest publication"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual((venv.stat().st_dev, venv.stat().st_ino), old_venv_identity)
        self.assertEqual((helper.stat().st_dev, helper.stat().st_ino), old_helper_identity)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "survive rollback")
        self.assertEqual(manifest_path.read_bytes(), old_manifest_bytes)
        self.assertFalse(preserved_venv.exists())
        self.assertFalse(preserved_helper.exists())
        self.assertFalse((home / ".install-staging").exists())

    @unittest.skipUnless(sys.platform == "darwin", "native helper is macOS-only")
    def test_legacy_helper_without_toolchain_is_preserved_but_no_longer_owned(self):
        self.approved_install()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        helper = home / "bin" / "cortex-macos-ax-send"
        helper_identity = (helper.stat().st_dev, helper.stat().st_ino)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"].pop("dev", None)
        manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        no_swift = {**self.environment, "SWIFTC_BIN": "/missing/cortex-swiftc"}

        dry = self.run_script("install.sh", "--dry-run", "--json", env=no_swift)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        self.assertEqual(plan["commands"], [])
        self.assertEqual(
            plan["metadata_migration"]["native_helper"]["action"],
            "preserve_unowned",
        )
        migrated = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
            env=no_swift,
        )
        self.assertEqual(migrated.returncode, 0, migrated.stderr)
        upgraded = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("native_helper", upgraded)
        self.assertNotIn(str(helper), upgraded["resources"])
        self.assertEqual((helper.stat().st_dev, helper.stat().st_ino), helper_identity)

        uninstall = self.run_script("uninstall.sh", "--dry-run", "--json", env=no_swift)
        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        uninstall_plan = json.loads(uninstall.stdout)
        self.assertNotIn(str(helper), uninstall_plan["resources"])
        removed = self.run_script(
            "uninstall.sh",
            "--approve-plan",
            uninstall_plan["plan_hash"],
            "--json",
            env=no_swift,
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual((helper.stat().st_dev, helper.stat().st_ino), helper_identity)

    @unittest.skipUnless(sys.platform == "darwin", "native helper is macOS-only")
    def test_preserved_unowned_helper_is_rebuilt_later_without_becoming_adopted(self):
        self.approved_install()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        helper = home / "bin" / "cortex-macos-ax-send"
        unowned_identity = (helper.stat().st_dev, helper.stat().st_ino)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"].pop("dev", None)
        manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        no_swift = {**self.environment, "SWIFTC_BIN": "/missing/cortex-swiftc"}

        no_toolchain_plan = self.run_script(
            "install.sh",
            "--dry-run",
            "--json",
            env=no_swift,
        )
        self.assertEqual(no_toolchain_plan.returncode, 0, no_toolchain_plan.stderr)
        no_toolchain_payload = json.loads(no_toolchain_plan.stdout)
        migrated = self.run_script(
            "install.sh",
            "--approve-plan",
            no_toolchain_payload["plan_hash"],
            "--json",
            env=no_swift,
        )
        self.assertEqual(migrated.returncode, 0, migrated.stderr)

        rebuild_plan = self.dry_plan()
        helper_migration = rebuild_plan["metadata_migration"]["native_helper"]
        self.assertEqual(helper_migration["action"], "rebuild_preserve")
        self.assertEqual(
            (helper_migration["dev"], helper_migration["ino"]),
            unowned_identity,
        )
        preserved_helper = Path(helper_migration["preserve_path"])
        rebuilt = self.run_script(
            "install.sh",
            "--approve-plan",
            rebuild_plan["plan_hash"],
            "--json",
        )
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)

        upgraded = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn("preserved_unowned_helper", upgraded)
        self.assertIn(str(helper), upgraded["resources"])
        self.assertNotEqual((helper.stat().st_dev, helper.stat().st_ino), unowned_identity)
        self.assertEqual(
            (preserved_helper.stat().st_dev, preserved_helper.stat().st_ino),
            unowned_identity,
        )

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
        self.assertFalse(helper.exists())
        self.assertEqual(
            (preserved_helper.stat().st_dev, preserved_helper.stat().st_ino),
            unowned_identity,
        )

    def test_legacy_metadata_migration_refuses_a_concurrent_manifest_replacement(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest.pop("venv", None)
        if "native_helper" in legacy_manifest:
            legacy_manifest["native_helper"].pop("dev", None)
            legacy_manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        displaced_manifest = self.root / "displaced-owned-manifest.json"
        foreign_manifest = b'{"foreign_sentinel":"preserve"}'

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            manifest_path.rename(displaced_manifest)
            manifest_path.write_bytes(foreign_manifest)

            with self.assertRaisesRegex(RuntimeError, "manifest.*(changed|identity|hash)"):
                installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual(manifest_path.read_bytes(), foreign_manifest)
        self.assertTrue(displaced_manifest.is_file())

    @unittest.skipUnless(sys.platform == "darwin", "atomic manifest swap is macOS-only")
    def test_metadata_migration_never_clobbers_predictable_temp_created_after_plan(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"].pop("dev", None)
        manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        no_swift = {**self.environment, "SWIFTC_BIN": "/missing/cortex-swiftc"}
        foreign_temp = manifest_path.parent / ".owned.json.migration.tmp"
        foreign_bytes = b"foreign outer temp sentinel"
        real_durable_write = installer._durable_json_write
        injected = False

        def inject_outer_temp_before_durable_write(path, payload, *args, **kwargs):
            nonlocal injected
            if path == foreign_temp and not injected:
                injected = True
                foreign_temp.write_bytes(foreign_bytes)
            return real_durable_write(path, payload, *args, **kwargs)

        with mock.patch.dict(os.environ, no_swift, clear=True):
            plan = installer.build_install_plan()
            self.assertEqual(plan["commands"], [])
            with mock.patch.object(
                installer,
                "_durable_json_write",
                side_effect=inject_outer_temp_before_durable_write,
            ):
                with self.assertRaisesRegex(RuntimeError, "temporary|destination|appeared"):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertTrue(injected)
        self.assertTrue(foreign_temp.is_file(), "foreign outer temp was displaced")
        self.assertEqual(foreign_temp.read_bytes(), foreign_bytes)
        self.assertNotIn("preserved_unowned_helper", json.loads(manifest_path.read_text()))

    @unittest.skipUnless(sys.platform == "darwin", "atomic manifest swap is macOS-only")
    def test_manifest_publication_preserves_late_foreign_target_and_previous_manifest(self):
        installer = load_installer_module()
        target = self.cortex_home.resolve() / "install" / "owned.json"
        target.parent.mkdir(parents=True)
        replacement = target.with_name(".owned.json.migration.tmp")
        displaced_new = self.root / "displaced-new-manifest.json"
        previous_bytes = b'{"owner":"cortex-bridge","resources":[],"legacy":true}'
        replacement_bytes = b'{"owner":"cortex-bridge","resources":[],"migrated":true}'
        foreign_bytes = b'{"foreign_sentinel":"preserve"}'
        target.write_bytes(previous_bytes)
        replacement.write_bytes(replacement_bytes)
        expected_manifest = installer._regular_file_fingerprint(target)
        previous_backup = target.parent / (
            ".previous-owned-manifest-"
            f"{expected_manifest['dev']:x}-{expected_manifest['ino']:x}.json"
        )
        real_swap = installer._rename_swap
        swapped = False

        def swap_then_replace_published_target(source, destination):
            nonlocal swapped
            real_swap(source, destination)
            if not swapped:
                swapped = True
                destination.rename(displaced_new)
                destination.write_bytes(foreign_bytes)

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with mock.patch.object(
                installer,
                "_rename_swap",
                side_effect=swap_then_replace_published_target,
            ):
                with self.assertRaisesRegex(RuntimeError, "changed after atomic publication"):
                    installer._publish_manifest_replacement(
                        replacement,
                        target,
                        expected_manifest,
                    )

        self.assertEqual(target.read_bytes(), foreign_bytes)
        self.assertEqual(displaced_new.read_bytes(), replacement_bytes)
        self.assertEqual(previous_backup.read_bytes(), previous_bytes)

    @unittest.skipUnless(sys.platform == "darwin", "atomic manifest swap is macOS-only")
    def test_manifest_publication_rejects_replacement_after_previous_backup_check(self):
        installer = load_installer_module()
        target = self.cortex_home.resolve() / "install" / "owned.json"
        target.parent.mkdir(parents=True)
        replacement = target.with_name(".owned.json.migration.tmp")
        displaced_new = self.root / "last-window-published-manifest"
        previous_bytes = b'{"owner":"cortex-bridge","resources":[],"legacy":true}'
        replacement_bytes = b'{"owner":"cortex-bridge","resources":[],"migrated":true}'
        foreign_bytes = b'{"foreign_sentinel":"last publication window"}'
        target.write_bytes(previous_bytes)
        replacement.write_bytes(replacement_bytes)
        expected_manifest = installer._regular_file_fingerprint(target)
        previous_backup = target.parent / (
            ".previous-owned-manifest-"
            f"{expected_manifest['dev']:x}-{expected_manifest['ino']:x}.json"
        )
        real_fingerprint = installer._regular_file_fingerprint
        replaced = False

        def fingerprint_then_replace_target(path):
            nonlocal replaced
            fingerprint = real_fingerprint(path)
            if path == previous_backup and not replaced:
                replaced = True
                target.rename(displaced_new)
                target.write_bytes(foreign_bytes)
            return fingerprint

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with mock.patch.object(
                installer,
                "_regular_file_fingerprint",
                side_effect=fingerprint_then_replace_target,
            ):
                with self.assertRaisesRegex(RuntimeError, "manifest.*changed"):
                    installer._publish_manifest_replacement(
                        replacement,
                        target,
                        expected_manifest,
                    )

        self.assertEqual(target.read_bytes(), foreign_bytes)
        self.assertEqual(displaced_new.read_bytes(), replacement_bytes)
        self.assertEqual(previous_backup.read_bytes(), previous_bytes)

    @unittest.skipUnless(sys.platform == "darwin", "atomic manifest exchange is macOS-only")
    def test_legacy_metadata_migration_detects_replacement_after_locked_revalidation(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest.pop("venv", None)
        legacy_manifest["native_helper"].pop("dev", None)
        legacy_manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        displaced_manifest = self.root / "late-displaced-owned-manifest.json"
        foreign_manifest = b'{"foreign_sentinel":"preserve after revalidation"}'
        real_snapshot = installer._owned_manifest_snapshot
        snapshot_calls = 0

        def replace_after_locked_revalidation():
            nonlocal snapshot_calls
            result = real_snapshot()
            snapshot_calls += 1
            if snapshot_calls == 2:
                manifest_path.rename(displaced_manifest)
                manifest_path.write_bytes(foreign_manifest)
            return result

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            snapshot_calls = 0
            with mock.patch.object(
                installer,
                "_owned_manifest_snapshot",
                side_effect=replace_after_locked_revalidation,
            ):
                with self.assertRaisesRegex(RuntimeError, "manifest.*(changed|identity|hash)"):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual(manifest_path.read_bytes(), foreign_manifest)
        self.assertTrue(displaced_manifest.is_file())

    def test_legacy_metadata_migration_refuses_a_concurrent_venv_replacement(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest.pop("venv", None)
        if "native_helper" in legacy_manifest:
            legacy_manifest["native_helper"].pop("dev", None)
            legacy_manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        venv = home / "venv"
        displaced_venv = self.root / "displaced-owned-venv-for-migration"
        sentinel = venv / "foreign-sentinel.txt"

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            venv.rename(displaced_venv)
            venv.mkdir()
            sentinel.write_text("preserve", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "venv.*identity"):
                installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertTrue(displaced_venv.is_dir())

    def test_foreign_venv_replacement_is_never_repaired_or_removed(self):
        self.approved_install()
        target_venv = self.cortex_home.resolve() / "venv"
        displaced_owned_venv = self.root / "displaced-owned-venv"
        target_venv.rename(displaced_owned_venv)
        target_venv.mkdir()
        sentinel = target_venv / "foreign-sentinel.txt"
        sentinel.write_text("keep foreign venv", encoding="utf-8")

        dry_run = self.run_script("install.sh", "--dry-run", "--json")

        self.assertNotEqual(dry_run.returncode, 0)
        self.assertIn("venv ownership", dry_run.stdout.lower())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep foreign venv")
        self.assertTrue(displaced_owned_venv.is_dir())
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    def test_legacy_incomplete_venv_requires_an_explicit_preserving_rebuild(self):
        self.approved_install()
        manifest_path = self.cortex_home / "install" / "owned.json"
        legacy_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy_manifest.pop("venv", None)
        manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
        target_venv = self.cortex_home.resolve() / "venv"
        missing_entrypoint = target_venv / "bin" / "playwright"
        missing_entrypoint.unlink()
        sentinel = target_venv / "keep.txt"
        sentinel.write_text("legacy-owned", encoding="utf-8")

        dry_run = self.run_script("install.sh", "--dry-run", "--json")

        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        plan = json.loads(dry_run.stdout)
        self.assertEqual(plan["venv_action"], "rebuild_legacy")
        self.assertEqual(
            plan["metadata_migration"]["venv"]["action"],
            "rebuild_preserve",
        )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "legacy-owned")
        self.assertFalse(missing_entrypoint.exists())
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    @unittest.skipUnless(sys.platform == "darwin", "atomic venv rollback is macOS-only")
    def test_failed_existing_venv_publication_restores_the_owned_broken_venv(self):
        self.approved_install()
        self.break_installed_entrypoints_with_staging_shebangs()
        installer = load_installer_module()
        target_venv = self.cortex_home.resolve() / "venv"
        staged_venv = self.cortex_home.resolve() / ".install-staging" / "venv"
        old_inode = target_venv.stat().st_ino
        old_manifest = (self.cortex_home / "install" / "owned.json").read_bytes()
        real_swap = installer._rename_swap
        swap_calls = 0

        def fail_after_first_swap(source, target):
            nonlocal swap_calls
            real_swap(source, target)
            if source == staged_venv and target == target_venv:
                swap_calls += 1
            if source == staged_venv and target == target_venv and swap_calls == 1:
                raise RuntimeError("simulated crash after venv swap")

        with mock.patch.dict(os.environ, self.environment, clear=True):
            repair_plan = installer.build_install_plan()
            self.assertEqual(repair_plan["venv_action"], "repair")
            with mock.patch.object(
                installer,
                "_rename_swap",
                side_effect=fail_after_first_swap,
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                    installer.apply_install(repair_plan, repair_plan["plan_hash"])

        self.assertEqual(swap_calls, 2)
        self.assertEqual(target_venv.stat().st_ino, old_inode)
        self.assertIn(
            ".install-staging",
            (target_venv / "bin" / "pip").read_text(encoding="utf-8").splitlines()[0],
        )
        self.assertEqual(
            (self.cortex_home / "install" / "owned.json").read_bytes(),
            old_manifest,
        )
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    @unittest.skipUnless(sys.platform == "darwin", "installer target is macOS")
    def test_relocation_runs_pip_from_a_real_stdlib_venv_after_publish(self):
        installer = load_installer_module()
        staged_venv = self.root / ".install-staging" / "venv"
        target_venv = self.root / "venv"
        created = subprocess.run(
            [sys.executable, "-m", "venv", str(staged_venv)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(created.returncode, 0, created.stderr)

        installer._relocate_staged_venv(staged_venv, target_venv)
        installer._rename_exclusive(staged_venv, target_venv)
        pip = target_venv / "bin" / "pip"
        first_line = pip.read_text(encoding="utf-8").splitlines()[0]
        executed = subprocess.run(
            [str(pip), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertIn(str(target_venv), first_line)
        self.assertNotIn(".install-staging", first_line)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertIn(str(target_venv), executed.stdout)

    def test_install_keeps_runtime_home_and_owned_metadata_private(self):
        self.approved_install()
        resolved_home = self.cortex_home.resolve()
        private_directories = (resolved_home, resolved_home / "install")
        private_files = (
            resolved_home / ".install.lock",
            resolved_home / "install" / "owned.json",
        )

        for directory in private_directories:
            with self.subTest(directory=directory):
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for private_file in private_files:
            with self.subTest(private_file=private_file):
                self.assertEqual(private_file.stat().st_mode & 0o777, 0o600)

    def test_install_privatizes_home_without_chmodding_preexisting_unowned_children(self):
        resolved_home = self.cortex_home.resolve()
        preexisting = (
            resolved_home,
            resolved_home / "bin",
            resolved_home / "install",
        )
        for directory in preexisting:
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o755)
            (directory / "foreign-sentinel.txt").write_text(
                f"preserve {directory.name}",
                encoding="utf-8",
            )

        self.approved_install()

        expected_modes = {
            resolved_home: 0o700,
            resolved_home / "bin": 0o755,
            resolved_home / "install": 0o755,
        }
        for directory, expected_mode in expected_modes.items():
            with self.subTest(directory=directory):
                self.assertEqual(directory.stat().st_mode & 0o777, expected_mode)
                self.assertEqual(
                    (directory / "foreign-sentinel.txt").read_text(encoding="utf-8"),
                    f"preserve {directory.name}",
                )

    def test_public_home_is_privatized_before_exclusive_lock_and_keeps_one_inode(self):
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        home.mkdir(parents=True, mode=0o700)
        home.chmod(0o777)
        lock = home / ".install.lock"

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with installer._exclusive_install_lock(home):
                locked_identity = (lock.stat().st_dev, lock.stat().st_ino)
                self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
                probe_fd = os.open(
                    lock,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    self.assertEqual(
                        (os.fstat(probe_fd).st_dev, os.fstat(probe_fd).st_ino),
                        locked_identity,
                    )
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe_fd)
            with installer._exclusive_install_lock(home):
                second_identity = (lock.stat().st_dev, lock.stat().st_ino)

        self.assertEqual(second_identity, locked_identity)

    def test_install_refuses_preexisting_hardlinked_lock_without_chmod(self):
        home = self.cortex_home.resolve()
        home.mkdir(parents=True)
        lock = home / ".install.lock"
        external = self.root / "external-lock-hardlink"
        lock.write_text("foreign lock sentinel", encoding="utf-8")
        lock.chmod(0o644)
        os.link(lock, external)
        before_identity = (lock.stat().st_dev, lock.stat().st_ino)

        plan = self.dry_plan()
        applied = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )

        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("lock", applied.stdout.lower())
        self.assertEqual(lock.read_text(encoding="utf-8"), "foreign lock sentinel")
        self.assertEqual(external.read_text(encoding="utf-8"), "foreign lock sentinel")
        self.assertEqual(lock.stat().st_mode & 0o777, 0o644)
        self.assertEqual(external.stat().st_mode & 0o777, 0o644)
        self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), before_identity)
        self.assertEqual((external.stat().st_dev, external.stat().st_ino), before_identity)

    def test_doctor_and_install_refuse_foreign_private_lock_without_mutation(self):
        home = self.cortex_home.resolve()
        home.mkdir(parents=True)
        lock = home / ".install.lock"
        foreign_bytes = b"foreign-private-lock"
        lock.write_bytes(foreign_bytes)
        lock.chmod(0o600)
        before = (
            lock.stat().st_dev,
            lock.stat().st_ino,
            lock.stat().st_mode & 0o777,
        )

        doctor = self.run_script("cortex.sh", "doctor", "--json")
        plan = self.dry_plan()
        applied = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )

        self.assertNotEqual(doctor.returncode, 0)
        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("lock", doctor.stdout.lower())
        self.assertIn("lock", applied.stdout.lower())
        self.assertEqual(lock.read_bytes(), foreign_bytes)
        self.assertEqual(
            (
                lock.stat().st_dev,
                lock.stat().st_ino,
                lock.stat().st_mode & 0o777,
            ),
            before,
        )

    def test_lifecycle_lock_rejects_partial_or_invalid_marker(self):
        home = self.cortex_home.resolve()
        home.mkdir(parents=True)
        lock = home / ".install.lock"
        invalid_payloads = (
            b"",
            b'{"owner":"cortex-bridge"',
            b'{"owner":"cortex-bridge","schema_version":2,"type":"lifecycle_lock"}\n',
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                lock.write_bytes(payload)
                lock.chmod(0o600)
                identity = (lock.stat().st_dev, lock.stat().st_ino)
                result = self.run_script("cortex.sh", "doctor", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("lock", result.stdout.lower())
                self.assertEqual(lock.read_bytes(), payload)
                self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)

    def test_failed_start_on_fresh_runtime_keeps_doctor_and_install_plan_usable(self):
        selected_python = self.root / "selected-python"
        selected_python.write_text(
            "#!/usr/bin/env python3\n"
            "import os,sys\n"
            "if len(sys.argv) >= 3 and sys.argv[1] == '-c' and sys.argv[2] == 'import fastapi,uvicorn,playwright,websockets':\n"
            " raise SystemExit(1)\n"
            f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        selected_python.chmod(0o755)
        environment = {**self.environment, "PYTHON_BIN": str(selected_python)}

        start = self.run_script("cortex.sh", "start", env=environment)
        doctor = self.run_script("cortex.sh", "doctor", "--json", env=environment)
        planned = self.run_script("install.sh", "--dry-run", "--json", env=environment)

        self.assertNotEqual(start.returncode, 0)
        self.assertIn("runtime dependencies are incomplete", start.stderr)
        self.assertEqual(doctor.returncode, 0, doctor.stderr or doctor.stdout)
        self.assertEqual(json.loads(doctor.stdout)["schema_version"], 1)
        self.assertEqual(planned.returncode, 0, planned.stderr or planned.stdout)
        plan = json.loads(planned.stdout)
        applied = self.run_script(
            "install.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
            env=environment,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr or applied.stdout)

    def test_concurrent_lock_creation_publishes_one_complete_marker_inode(self):
        home = self.cortex_home.resolve()
        start = self.root / "lock-create-start"
        expected_marker = (
            b'{"owner":"cortex-bridge","schema_version":1,'
            b'"type":"lifecycle_lock"}\n'
        )
        process_code = (
            "import json,os,time\n"
            "from pathlib import Path\n"
            "import installer\n"
            "while not Path(os.environ['LOCK_CREATE_START']).exists(): time.sleep(0.005)\n"
            "fd=installer._open_lifecycle_lock(Path(os.environ['CORTEX_HOME']).resolve())\n"
            "os.lseek(fd,0,os.SEEK_SET)\n"
            "data=b''\n"
            "while True:\n"
            " chunk=os.read(fd,4096)\n"
            " if not chunk: break\n"
            " data+=chunk\n"
            "details=os.fstat(fd)\n"
            "Path(os.environ['LOCK_RESULT']).write_text(json.dumps({'dev':details.st_dev,'ino':details.st_ino,'hex':data.hex()}))\n"
            "os.close(fd)\n"
        )
        processes: list[subprocess.Popen[str]] = []
        results: list[Path] = []
        try:
            for index in range(4):
                result_path = self.root / f"lock-create-result-{index}.json"
                results.append(result_path)
                environment = {
                    **self.environment,
                    "PYTHONPATH": f"{ROOT / 'console'}:{ROOT}",
                    "LOCK_CREATE_START": str(start),
                    "LOCK_RESULT": str(result_path),
                }
                processes.append(
                    subprocess.Popen(
                        [sys.executable, "-c", process_code],
                        cwd=ROOT,
                        env=environment,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )
            start.write_text("start", encoding="utf-8")
            for process in processes:
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr or stdout)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                if process.stdout and not process.stdout.closed:
                    process.communicate()

        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in results]
        self.assertEqual(
            {(payload["dev"], payload["ino"]) for payload in payloads},
            {(home.joinpath(".install.lock").stat().st_dev, home.joinpath(".install.lock").stat().st_ino)},
        )
        self.assertEqual({bytes.fromhex(payload["hex"]) for payload in payloads}, {expected_marker})
        self.assertEqual(list(home.glob(".install.lock.init-*")), [])

    def test_shared_lock_created_from_absence_blocks_nonblocking_exclusive_probe(self):
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        lock = home / ".install.lock"

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with installer._shared_install_lock_if_present(home):
                self.assertTrue(lock.is_file())
                probe_fd = os.open(
                    lock,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe_fd)

    def test_lifecycle_lock_inode_is_stable_across_exclusive_and_shared_users(self):
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        lock = home / ".install.lock"

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with installer._exclusive_install_lock(home):
                first_identity = (lock.stat().st_dev, lock.stat().st_ino)
            self.assertTrue(lock.is_file())
            with installer._shared_install_lock_if_present(home):
                shared_identity = (lock.stat().st_dev, lock.stat().st_ino)
            with installer._exclusive_install_lock(home):
                second_identity = (lock.stat().st_dev, lock.stat().st_ino)

        self.assertEqual(first_identity, shared_identity)
        self.assertEqual(first_identity, second_identity)
        details = lock.stat(follow_symlinks=False)
        self.assertEqual(details.st_uid, os.getuid())
        self.assertEqual(details.st_nlink, 1)
        self.assertEqual(details.st_mode & 0o077, 0)

    def test_real_process_shared_lock_excludes_exclusive_until_release(self):
        home = self.cortex_home.resolve()
        ready = self.root / "shared-lock-ready"
        release = self.root / "shared-lock-release"
        entered = self.root / "exclusive-lock-entered"
        environment = {
            **self.environment,
            "PYTHONPATH": f"{ROOT / 'console'}:{ROOT}",
            "LOCK_READY": str(ready),
            "LOCK_RELEASE": str(release),
            "LOCK_ENTERED": str(entered),
        }
        shared_code = (
            "import os,time\n"
            "from pathlib import Path\n"
            "import installer\n"
            "home=Path(os.environ['CORTEX_HOME']).resolve()\n"
            "with installer._shared_install_lock_if_present(home):\n"
            " Path(os.environ['LOCK_READY']).write_text('ready')\n"
            " while not Path(os.environ['LOCK_RELEASE']).exists(): time.sleep(0.01)\n"
        )
        exclusive_code = (
            "import os\n"
            "from pathlib import Path\n"
            "import installer\n"
            "home=Path(os.environ['CORTEX_HOME']).resolve()\n"
            "with installer._exclusive_install_lock(home):\n"
            " Path(os.environ['LOCK_ENTERED']).write_text('entered')\n"
        )
        shared = subprocess.Popen(
            [sys.executable, "-c", shared_code],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        exclusive = None
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and shared.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.is_file())
            exclusive = subprocess.Popen(
                [sys.executable, "-c", exclusive_code],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.25)
            self.assertFalse(entered.exists())
            release.write_text("release", encoding="utf-8")
            shared_stdout, shared_stderr = shared.communicate(timeout=5)
            exclusive_stdout, exclusive_stderr = exclusive.communicate(timeout=5)
            self.assertEqual(shared.returncode, 0, shared_stderr or shared_stdout)
            self.assertEqual(exclusive.returncode, 0, exclusive_stderr or exclusive_stdout)
            self.assertTrue(entered.is_file())
        finally:
            for process in (shared, exclusive):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    @unittest.skipUnless(sys.platform == "darwin", "exclusive directory rename is macOS-only")
    def test_install_never_replaces_a_venv_target_that_appears_during_relocation(self):
        installer = load_installer_module()
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            original_relocate = installer._relocate_staged_venv
            target_venv = self.cortex_home.resolve() / "venv"

            def create_competing_target(staged_venv, target):
                original_relocate(staged_venv, target)
                target_venv.mkdir()

            with mock.patch.object(
                installer,
                "_relocate_staged_venv",
                side_effect=create_competing_target,
            ):
                with self.assertRaises(FileExistsError):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertTrue(target_venv.is_dir())
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    @unittest.skipUnless(sys.platform == "darwin", "exclusive directory rename is macOS-only")
    def test_install_never_follows_a_venv_symlink_that_appears_during_relocation(self):
        installer = load_installer_module()
        external = self.root / "external-venv"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_text("foreign", encoding="utf-8")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            original_relocate = installer._relocate_staged_venv
            target_venv = self.cortex_home.resolve() / "venv"

            def create_competing_symlink(staged_venv, target):
                original_relocate(staged_venv, target)
                target_venv.symlink_to(external, target_is_directory=True)

            with mock.patch.object(
                installer,
                "_relocate_staged_venv",
                side_effect=create_competing_symlink,
            ):
                with self.assertRaises(FileExistsError):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertTrue(target_venv.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign")
        self.assertFalse((self.cortex_home / ".install-staging").exists())

    @unittest.skipUnless(sys.platform == "darwin", "exclusive manifest rename is macOS-only")
    def test_fresh_install_never_overwrites_a_manifest_that_appears_during_commands(self):
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        manifest_path = home / "install" / "owned.json"
        foreign_manifest = b'{"foreign_sentinel":"preserve appeared manifest"}'
        real_run = installer._run_command

        def run_then_create_manifest(command):
            real_run(command)
            if command["id"] == "compile_macos_ax_helper":
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_bytes(foreign_manifest)

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            with mock.patch.object(
                installer,
                "_run_command",
                side_effect=run_then_create_manifest,
            ):
                with self.assertRaises(FileExistsError):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual(manifest_path.read_bytes(), foreign_manifest)

    @unittest.skipUnless(sys.platform == "darwin", "fresh venv recovery is macOS-only")
    def test_fresh_recovery_never_deletes_a_foreign_replacement_venv(self):
        installer = load_installer_module()
        target_venv = self.cortex_home.resolve() / "venv"
        displaced_owned = self.root / "displaced-published-venv"
        sentinel = target_venv / "foreign-sentinel.txt"
        real_rename_exclusive = installer._rename_exclusive
        publication_interrupted = False

        def replace_after_fresh_publication(source, target):
            nonlocal publication_interrupted
            real_rename_exclusive(source, target)
            if target == target_venv and not publication_interrupted:
                publication_interrupted = True
                target.rename(displaced_owned)
                target.mkdir()
                sentinel.write_text("foreign replacement", encoding="utf-8")
                raise RuntimeError("simulated crash after fresh venv publication")

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            self.assertEqual(plan["venv_action"], "create")
            with mock.patch.object(
                installer,
                "_rename_exclusive",
                side_effect=replace_after_fresh_publication,
            ):
                with self.assertRaises(RuntimeError):
                    installer.apply_install(plan, plan["plan_hash"])

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign replacement")
            self.assertTrue(displaced_owned.is_dir())
            with self.assertRaisesRegex(RuntimeError, "identity|identify"):
                installer.apply_install(plan, plan["plan_hash"])

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign replacement")
        self.assertTrue((self.cortex_home / ".install-staging").is_dir())

    def test_fresh_recovery_rechecks_identity_after_the_existing_verification(self):
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        home.mkdir(parents=True)
        target_venv = home / "venv"
        target_venv.mkdir()
        (target_venv / "owned.txt").write_text("owned", encoding="utf-8")
        expected_identity = (target_venv.stat().st_dev, target_venv.stat().st_ino)
        staging = home / ".install-staging"
        staging.mkdir()
        (staging / "transaction.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "owner": "cortex-bridge",
                    "home": str(home),
                    "plan_hash": "f" * 64,
                    "creates_venv": True,
                    "replaces_venv": False,
                    "venv": {
                        "target": str(target_venv),
                        "new_dev": expected_identity[0],
                        "new_ino": expected_identity[1],
                    },
                    "helper": None,
                }
            ),
            encoding="utf-8",
        )
        displaced_owned = self.root / "late-displaced-recovery-venv"
        sentinel = target_venv / "foreign-sentinel.txt"
        real_identity = installer._directory_identity
        replaced = False

        def replace_after_verified(path):
            nonlocal replaced
            identity = real_identity(path)
            if path == target_venv and not replaced:
                replaced = True
                target_venv.rename(displaced_owned)
                target_venv.mkdir()
                sentinel.write_text("preserve late replacement", encoding="utf-8")
            return identity

        with mock.patch.dict(os.environ, self.environment, clear=True), mock.patch.object(
            installer,
            "_directory_identity",
            side_effect=replace_after_verified,
        ):
            with self.assertRaisesRegex(RuntimeError, "identity"):
                installer._recover_interrupted_install(home)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve late replacement")
        self.assertTrue(displaced_owned.is_dir())

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

    @unittest.skipUnless(sys.platform == "darwin", "atomic helper exchange is macOS-only")
    def test_helper_update_rejects_a_same_bytes_replacement_after_validation(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        helper = home / "bin" / "cortex-macos-ax-send"
        manifest_path = home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        foreign_helper = self.root / "same-bytes-foreign-helper"
        real_copy = installer._copy_approved_helper_source

        def copy_then_replace(destination, expected_sha256):
            real_copy(destination, expected_sha256)
            content = helper.read_bytes()
            helper.replace(foreign_helper)
            helper.write_bytes(content)
            helper.chmod(0o700)

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            with mock.patch.object(
                installer,
                "_copy_approved_helper_source",
                side_effect=copy_then_replace,
            ):
                with self.assertRaisesRegex(RuntimeError, "identity|displaced"):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertTrue(helper.is_file())
        self.assertNotEqual(helper.stat().st_ino, foreign_helper.stat().st_ino)
        self.assertEqual(helper.read_bytes(), foreign_helper.read_bytes())

    @unittest.skipUnless(sys.platform == "darwin", "atomic helper exchange is macOS-only")
    def test_helper_update_preserves_same_bytes_replacement_after_atomic_swap(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        helper = home / "bin" / "cortex-macos-ax-send"
        manifest_path = home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"]["source_sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        displaced_new = self.root / "displaced-new-helper"
        real_swap = installer._rename_swap
        replaced = False

        def swap_then_replace_new_helper(source, destination):
            nonlocal replaced
            real_swap(source, destination)
            if destination == helper and not replaced:
                replaced = True
                content = helper.read_bytes()
                helper.rename(displaced_new)
                helper.write_bytes(content)
                helper.chmod(0o700)

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_install_plan()
            with mock.patch.object(
                installer,
                "_rename_swap",
                side_effect=swap_then_replace_new_helper,
            ):
                with self.assertRaisesRegex(RuntimeError, "identity|unknown"):
                    installer.apply_install(plan, plan["plan_hash"])

        self.assertTrue(helper.is_file())
        self.assertTrue(displaced_new.is_file())
        self.assertNotEqual(helper.stat().st_ino, displaced_new.stat().st_ino)

    def test_install_plan_rejects_a_same_bytes_helper_replacement_before_plan(self):
        self.approved_install()
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        displaced_owned = self.root / "pre-plan-owned-helper-with-identity"
        content = helper.read_bytes()
        helper.rename(displaced_owned)
        helper.write_bytes(content)
        helper.chmod(0o700)

        plan = self.run_script("install.sh", "--dry-run", "--json")

        self.assertNotEqual(plan.returncode, 0)
        self.assertIn("identity", plan.stdout.lower())
        self.assertTrue(helper.is_file())
        self.assertTrue(displaced_owned.is_file())

    @unittest.skipUnless(sys.platform == "darwin", "helper recovery is macOS-only")
    def test_helper_recovery_never_deletes_a_same_bytes_foreign_replacement(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        helper = home / "bin" / "cortex-macos-ax-send"
        previous = helper.read_bytes()
        previous_identity = (helper.stat().st_dev, helper.stat().st_ino)
        staging = home / ".install-staging"
        staging.mkdir()
        backup = staging / ".cortex-macos-ax-send.previous"
        helper.rename(backup)
        replacement = b"owned replacement before crash"
        helper.write_bytes(replacement)
        helper.chmod(0o700)
        replacement_identity = (helper.stat().st_dev, helper.stat().st_ino)
        displaced_replacement = self.root / "displaced-owned-replacement"
        helper.rename(displaced_replacement)
        helper.write_bytes(replacement)
        helper.chmod(0o700)
        foreign_identity = (helper.stat().st_dev, helper.stat().st_ino)
        transaction = {
            "schema_version": 1,
            "owner": "cortex-bridge",
            "home": str(home),
            "plan_hash": "e" * 64,
            "creates_venv": False,
            "replaces_venv": False,
            "venv": None,
            "helper": {
                "target": str(helper),
                "backup": str(backup),
                "previous_exists": True,
                "previous_sha256": hashlib.sha256(previous).hexdigest(),
                "previous_dev": previous_identity[0],
                "previous_ino": previous_identity[1],
                "new_sha256": hashlib.sha256(replacement).hexdigest(),
                "new_dev": replacement_identity[0],
                "new_ino": replacement_identity[1],
                "preserves_previous": False,
                "preserved": None,
            },
        }
        (staging / "transaction.json").write_text(
            json.dumps(transaction),
            encoding="utf-8",
        )

        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "identity|unknown"):
                installer._recover_interrupted_install(home)

        self.assertEqual((helper.stat().st_dev, helper.stat().st_ino), foreign_identity)
        self.assertEqual(helper.read_bytes(), replacement)
        self.assertTrue(backup.is_file())

    def test_owned_file_deletion_preserves_a_replacement_after_final_stat(self):
        installer = load_installer_module()
        owned = self.root / "owned-delete-target"
        displaced = self.root / "displaced-owned-delete-target"
        owned.write_bytes(b"owned")
        expected_identity = (owned.stat().st_dev, owned.stat().st_ino)
        expected_hash = hashlib.sha256(b"owned").hexdigest()
        real_stat = installer.os.stat
        replaced = False

        def stat_then_replace(path, *args, **kwargs):
            nonlocal replaced
            result = real_stat(path, *args, **kwargs)
            if path == owned.name and kwargs.get("dir_fd") is not None and not replaced:
                replaced = True
                owned.rename(displaced)
                owned.write_bytes(b"foreign sentinel")
            return result

        with mock.patch.object(installer.os, "stat", side_effect=stat_then_replace):
            with self.assertRaisesRegex(RuntimeError, "identity|changed"):
                installer._remove_owned_file(owned, expected_identity, expected_hash)

        self.assertEqual(owned.read_bytes(), b"foreign sentinel")
        self.assertEqual(displaced.read_bytes(), b"owned")

    @unittest.skipUnless(sys.platform == "darwin", "fd-relative quarantine is macOS-only")
    def test_owned_file_cleanup_unlinks_before_verified_quarantine_fd_closes(self):
        installer = load_installer_module()
        owned = self.root / "owned-post-fstat-delete-target"
        displaced_owned = self.root / "post-fstat-displaced-owned"
        owned_bytes = b"owned deletion payload"
        foreign_bytes = b"foreign post-fstat sentinel"
        owned.write_bytes(owned_bytes)
        expected_identity = (owned.stat().st_dev, owned.stat().st_ino)
        expected_hash = hashlib.sha256(owned_bytes).hexdigest()
        real_close = installer.os.close
        replaced = False

        def close_then_replace_quarantine(fd):
            nonlocal replaced
            real_close(fd)
            candidates = list(
                owned.parent.glob(".owned-post-fstat-delete-target.delete-*")
            )
            if candidates and not replaced:
                replaced = True
                quarantine = candidates[0]
                quarantine.rename(displaced_owned)
                quarantine.write_bytes(foreign_bytes)

        with mock.patch.object(
            installer.os,
            "close",
            side_effect=close_then_replace_quarantine,
        ):
            installer._remove_owned_file(
                owned,
                expected_identity,
                expected_hash,
            )

        self.assertFalse(owned.exists())
        self.assertFalse(replaced, "quarantine fd closed before physical cleanup")
        self.assertFalse(displaced_owned.exists())
        self.assertEqual(
            list(owned.parent.glob(".owned-post-fstat-delete-target.delete-*")),
            [],
        )

    def test_recursive_deletion_preserves_an_entry_replaced_after_final_stat(self):
        installer = load_installer_module()
        owned_dir = self.root / "owned-delete-directory"
        owned_dir.mkdir()
        victim = owned_dir / "victim.txt"
        victim.write_bytes(b"owned child")
        displaced = self.root / "displaced-owned-child"
        expected_identity = (owned_dir.stat().st_dev, owned_dir.stat().st_ino)
        real_stat = installer.os.stat
        victim_stats = 0

        def stat_then_replace(path, *args, **kwargs):
            nonlocal victim_stats
            result = real_stat(path, *args, **kwargs)
            if path == victim.name and kwargs.get("dir_fd") is not None:
                victim_stats += 1
                if victim_stats == 2:
                    quarantined_root = next(
                        owned_dir.parent.glob(".owned-delete-directory.delete-*")
                    )
                    quarantined_victim = quarantined_root / victim.name
                    quarantined_victim.rename(displaced)
                    quarantined_victim.write_bytes(b"foreign child sentinel")
            return result

        with mock.patch.object(installer.os, "stat", side_effect=stat_then_replace):
            with self.assertRaisesRegex(RuntimeError, "identity|changed"):
                installer._remove_owned_directory(owned_dir, expected_identity)

        self.assertEqual(victim.read_bytes(), b"foreign child sentinel")
        self.assertEqual(displaced.read_bytes(), b"owned child")

    @unittest.skipUnless(sys.platform == "darwin", "fd-relative quarantine is macOS-only")
    def test_directory_deletion_revalidates_root_after_quarantine_reopen(self):
        installer = load_installer_module()
        owned_dir = self.root / "owned-reopen-directory"
        owned_dir.mkdir()
        (owned_dir / "owned.txt").write_text("owned", encoding="utf-8")
        expected_identity = (owned_dir.stat().st_dev, owned_dir.stat().st_ino)
        displaced_owned = self.root / "reopen-displaced-owned"
        real_open = installer.os.open
        replaced = False

        def replace_quarantine_before_reopen(path, flags, *args, **kwargs):
            nonlocal replaced
            if (
                isinstance(path, str)
                and path.startswith(".owned-reopen-directory.delete-")
                and kwargs.get("dir_fd") is not None
                and not replaced
            ):
                replaced = True
                quarantine = owned_dir.parent / path
                quarantine.rename(displaced_owned)
                quarantine.mkdir()
                (quarantine / "foreign-sentinel.txt").write_text(
                    "never traverse foreign root",
                    encoding="utf-8",
                )
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            installer.os,
            "open",
            side_effect=replace_quarantine_before_reopen,
        ):
            with self.assertRaisesRegex(RuntimeError, "identity|changed"):
                installer._remove_owned_directory(owned_dir, expected_identity)

        self.assertTrue(replaced)
        sentinels = list(self.root.rglob("foreign-sentinel.txt"))
        self.assertEqual(len(sentinels), 1)
        self.assertEqual(
            sentinels[0].read_text(encoding="utf-8"),
            "never traverse foreign root",
        )
        self.assertTrue((displaced_owned / "owned.txt").is_file())

    def test_recursive_deletion_refuses_cross_device_child_and_preserves_sentinel(self):
        installer = load_installer_module()
        owned_dir = self.root / "owned-cross-device-directory"
        mounted = owned_dir / "mounted"
        mounted.mkdir(parents=True)
        sentinel = mounted / "foreign-sentinel.txt"
        sentinel.write_text("preserve mounted data", encoding="utf-8")
        expected_identity = (owned_dir.stat().st_dev, owned_dir.stat().st_ino)
        real_stat = installer.os.stat

        def report_mounted_child_on_another_device(path, *args, **kwargs):
            details = real_stat(path, *args, **kwargs)
            if path == mounted.name and kwargs.get("dir_fd") is not None:
                return SimpleNamespace(
                    st_mode=details.st_mode,
                    st_dev=expected_identity[0] + 1,
                    st_ino=details.st_ino,
                )
            return details

        with mock.patch.object(
            installer.os,
            "stat",
            side_effect=report_mounted_child_on_another_device,
        ):
            with self.assertRaisesRegex(RuntimeError, "device boundary"):
                installer._remove_owned_directory(owned_dir, expected_identity)

        self.assertEqual(
            sentinel.read_text(encoding="utf-8"),
            "preserve mounted data",
        )

    def test_cleanup_staging_refuses_cross_device_child_and_preserves_sentinel(self):
        installer = load_installer_module()
        staging = self.cortex_home.resolve() / ".install-staging"
        mounted = staging / "mounted"
        mounted.mkdir(parents=True)
        sentinel = mounted / "foreign-sentinel.txt"
        sentinel.write_text("preserve staged mount", encoding="utf-8")
        staging_dev = staging.stat().st_dev
        real_stat = installer.os.stat

        def report_staging_child_on_another_device(path, *args, **kwargs):
            details = real_stat(path, *args, **kwargs)
            if Path(path) == mounted and kwargs.get("dir_fd") is None:
                return SimpleNamespace(
                    st_mode=details.st_mode,
                    st_dev=staging_dev + 1,
                    st_ino=details.st_ino,
                )
            return details

        with mock.patch.object(
            installer.os,
            "stat",
            side_effect=report_staging_child_on_another_device,
        ):
            with self.assertRaisesRegex(RuntimeError, "device boundary"):
                installer._cleanup_staging(staging)

        self.assertEqual(
            sentinel.read_text(encoding="utf-8"),
            "preserve staged mount",
        )

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
        self.assertEqual(payload["version"], "0.5.4")
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

    @unittest.skipUnless(sys.platform == "darwin", "physical quarantine cleanup is macOS-only")
    def test_two_install_uninstall_cycles_do_not_accumulate_quarantined_resources(self):
        home = self.cortex_home.resolve()
        foreign = home / "foreign-sentinel.txt"
        foreign.parent.mkdir(parents=True)
        foreign.write_text("preserve across cycles", encoding="utf-8")
        quarantine_totals: list[tuple[int, int]] = []

        for _ in range(2):
            self.approved_install()
            dry = self.run_script("uninstall.sh", "--dry-run", "--json")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            plan = json.loads(dry.stdout)
            applied = self.run_script(
                "uninstall.sh",
                "--approve-plan",
                plan["plan_hash"],
                "--json",
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["status"], "uninstalled")
            quarantined = [
                path for path in home.rglob("*") if ".delete-" in path.name
            ]
            quarantined_bytes = sum(
                path.stat().st_size
                for path in home.rglob("*")
                if path.is_file()
                and any(".delete-" in part for part in path.relative_to(home).parts)
            )
            quarantine_totals.append((len(quarantined), quarantined_bytes))
            self.assertFalse((home / "venv").exists())
            self.assertFalse((home / "bin" / "cortex-macos-ax-send").exists())
            self.assertFalse((home / "install" / "owned.json").exists())
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve across cycles")

        self.assertEqual(quarantine_totals, [(0, 0), (0, 0)])

    def test_uninstall_plan_never_deletes_a_replaced_foreign_venv(self):
        self.approved_install()
        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        self.assertEqual(plan["venv_identity"]["path"], str(self.cortex_home.resolve() / "venv"))

        owned_venv = self.cortex_home.resolve() / "venv"
        displaced_owned = self.root / "uninstall-owned-venv"
        owned_venv.rename(displaced_owned)
        owned_venv.mkdir()
        sentinel = owned_venv / "foreign-sentinel.txt"
        sentinel.write_text("preserve foreign", encoding="utf-8")
        applied = self.run_script(
            "uninstall.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )

        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("venv ownership identity", applied.stdout.lower())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve foreign")
        self.assertTrue(displaced_owned.is_dir())
        self.assertTrue((self.cortex_home / "install" / "owned.json").is_file())

    def test_uninstall_refuses_a_legacy_manifest_without_venv_identity(self):
        self.approved_install()
        manifest_path = self.cortex_home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("venv", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        dry = self.run_script("uninstall.sh", "--dry-run", "--json")

        self.assertNotEqual(dry.returncode, 0)
        self.assertIn("venv ownership metadata", dry.stdout.lower())
        self.assertTrue((self.cortex_home / "venv").is_dir())
        self.assertTrue(manifest_path.is_file())

    @unittest.skipUnless(sys.platform == "darwin", "atomic uninstall quarantine is macOS-only")
    def test_uninstall_quarantines_venv_lexically_before_identity_check(self):
        self.approved_install()
        installer = load_installer_module()
        target_venv = self.cortex_home.resolve() / "venv"
        displaced_owned = self.root / "late-owned-venv"
        foreign = self.cortex_home.resolve() / "foreign-data"
        foreign.mkdir()
        sentinel = foreign / "sentinel.txt"
        sentinel.write_text("preserve late foreign", encoding="utf-8")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            real_build = installer.build_uninstall_plan

            def rebuild_then_replace_with_symlink():
                current = real_build()
                target_venv.rename(displaced_owned)
                target_venv.symlink_to(foreign, target_is_directory=True)
                return current

            with mock.patch.object(
                installer,
                "build_uninstall_plan",
                side_effect=rebuild_then_replace_with_symlink,
            ), mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="stopped", listener_pids=[]),
            ):
                with self.assertRaisesRegex(RuntimeError, "venv ownership identity"):
                    installer.apply_uninstall(plan, plan["plan_hash"])

        self.assertTrue(target_venv.is_symlink())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve late foreign")
        self.assertTrue(displaced_owned.is_dir())

    @unittest.skipUnless(sys.platform == "darwin", "atomic uninstall quarantine is macOS-only")
    def test_uninstall_rechecks_quarantined_venv_before_recursive_deletion(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        quarantine = home / ".venv.uninstall-quarantine"
        displaced_owned = self.root / "late-displaced-quarantined-venv"
        sentinel = quarantine / "foreign-sentinel.txt"
        real_identity = installer._directory_identity
        replaced = False

        def replace_after_verified(path):
            nonlocal replaced
            identity = real_identity(path)
            if path == quarantine and not replaced:
                replaced = True
                quarantine.rename(displaced_owned)
                quarantine.mkdir()
                sentinel.write_text("preserve late quarantine", encoding="utf-8")
            return identity

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            with mock.patch.object(
                installer,
                "_directory_identity",
                side_effect=replace_after_verified,
            ), mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="stopped", listener_pids=[]),
            ):
                with self.assertRaisesRegex(RuntimeError, "identity"):
                    installer.apply_uninstall(plan, plan["plan_hash"])

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve late quarantine")
        self.assertTrue(displaced_owned.is_dir())

    @unittest.skipUnless(sys.platform == "darwin", "native helper is macOS-only")
    def test_uninstall_plan_never_deletes_a_replaced_foreign_native_helper(self):
        self.approved_install()
        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        self.assertEqual(plan["native_helper_identity"]["path"], str(helper))
        self.assertEqual(len(plan["native_helper_identity"]["sha256"]), 64)

        displaced_owned = self.root / "uninstall-owned-helper"
        helper.rename(displaced_owned)
        helper.write_text("foreign helper sentinel", encoding="utf-8")
        applied = self.run_script(
            "uninstall.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )

        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("native helper ownership", applied.stdout.lower())
        self.assertEqual(helper.read_text(encoding="utf-8"), "foreign helper sentinel")
        self.assertTrue(displaced_owned.is_file())
        self.assertTrue((self.cortex_home / "install" / "owned.json").is_file())

    @unittest.skipUnless(sys.platform == "darwin", "native helper is macOS-only")
    def test_uninstall_never_follows_a_replacement_native_helper_symlink(self):
        self.approved_install()
        dry = self.run_script("uninstall.sh", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        plan = json.loads(dry.stdout)
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        displaced_owned = self.root / "symlink-owned-helper"
        external = self.root / "external-helper-sentinel"
        helper.rename(displaced_owned)
        external.write_text("preserve external", encoding="utf-8")
        helper.symlink_to(external)

        applied = self.run_script(
            "uninstall.sh",
            "--approve-plan",
            plan["plan_hash"],
            "--json",
        )

        self.assertNotEqual(applied.returncode, 0)
        self.assertIn("native helper ownership", applied.stdout.lower())
        self.assertTrue(helper.is_symlink())
        self.assertEqual(external.read_text(encoding="utf-8"), "preserve external")

    @unittest.skipUnless(sys.platform == "darwin", "native helper is macOS-only")
    def test_uninstall_refuses_legacy_helper_metadata_without_identity(self):
        self.approved_install()
        manifest_path = self.cortex_home / "install" / "owned.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["native_helper"].pop("dev", None)
        manifest["native_helper"].pop("ino", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        dry = self.run_script("uninstall.sh", "--dry-run", "--json")

        self.assertNotEqual(dry.returncode, 0)
        self.assertIn("native helper ownership metadata", dry.stdout.lower())
        self.assertTrue((self.cortex_home / "bin" / "cortex-macos-ax-send").is_file())

    @unittest.skipUnless(sys.platform == "darwin", "atomic uninstall quarantine is macOS-only")
    def test_uninstall_quarantines_helper_lexically_before_identity_check(self):
        self.approved_install()
        installer = load_installer_module()
        helper = self.cortex_home.resolve() / "bin" / "cortex-macos-ax-send"
        displaced_owned = self.root / "late-owned-helper"
        external = self.cortex_home.resolve() / "foreign-helper-data"
        external.write_text("preserve helper target", encoding="utf-8")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            real_build = installer.build_uninstall_plan

            def rebuild_then_replace_with_symlink():
                current = real_build()
                helper.rename(displaced_owned)
                helper.symlink_to(external)
                return current

            with mock.patch.object(
                installer,
                "build_uninstall_plan",
                side_effect=rebuild_then_replace_with_symlink,
            ), mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="stopped", listener_pids=[]),
            ):
                with self.assertRaisesRegex(RuntimeError, "native helper ownership"):
                    installer.apply_uninstall(plan, plan["plan_hash"])

        self.assertTrue(helper.is_symlink())
        self.assertEqual(external.read_text(encoding="utf-8"), "preserve helper target")
        self.assertTrue(displaced_owned.is_file())

    @unittest.skipUnless(sys.platform == "darwin", "atomic uninstall quarantine is macOS-only")
    def test_uninstall_rechecks_quarantined_helper_before_file_deletion(self):
        self.approved_install()
        installer = load_installer_module()
        home = self.cortex_home.resolve()
        quarantine = home / "bin" / ".cortex-macos-ax-send.uninstall-quarantine"
        displaced_owned = self.root / "late-displaced-quarantined-helper"
        foreign_content = b"preserve late helper quarantine"
        real_hash = installer._sha256_file
        replaced = False

        def replace_after_verified(path):
            nonlocal replaced
            digest = real_hash(path)
            if path == quarantine and not replaced:
                replaced = True
                quarantine.rename(displaced_owned)
                quarantine.write_bytes(foreign_content)
                quarantine.chmod(0o700)
            return digest

        with mock.patch.dict(os.environ, self.environment, clear=True):
            plan = installer.build_uninstall_plan()
            with mock.patch.object(
                installer,
                "_sha256_file",
                side_effect=replace_after_verified,
            ), mock.patch.object(
                installer,
                "classify",
                return_value=SimpleNamespace(state="stopped", listener_pids=[]),
            ):
                with self.assertRaisesRegex(RuntimeError, "identity|hash"):
                    installer.apply_uninstall(plan, plan["plan_hash"])

        self.assertEqual(quarantine.read_bytes(), foreign_content)
        self.assertTrue(displaced_owned.is_file())


if __name__ == "__main__":
    unittest.main()
