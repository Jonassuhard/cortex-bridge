"""Tests for publishing the optional external-storage bootstrap safely."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "configure-external-storage.py"
EXPECTED_UUID = "12345678-1234-1234-1234-123456789ABC"


class StorageConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # macOS exposes its temporary directory through the /var -> /private/var
        # compatibility symlink. Use the canonical test root so that only the
        # symlinks created by each test are relevant to the contract.
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.home = self.root / "state" / "cortex-bridge"
        self.mount = self.root / "vault"
        self.mount.mkdir()
        self.storage = self.mount / "CORTEX_BRIDGE"
        self.storage.mkdir()
        self.image = self.root / "vault.sparsebundle"
        self.image.mkdir()

    def load_module(self):
        self.assertTrue(SCRIPT.is_file(), "configuration script is not implemented")
        spec = importlib.util.spec_from_file_location(
            "configure_external_storage",
            SCRIPT,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def arguments(self) -> list[str]:
        return [
            "--cortex-home",
            str(self.home),
            "--mount-path",
            str(self.mount),
            "--volume-uuid",
            EXPECTED_UUID,
            "--encrypted-image-path",
            str(self.image),
            "--storage-root",
            str(self.storage),
        ]

    def arguments_without_runtime_home(self) -> list[str]:
        arguments = self.arguments()
        home_index = arguments.index("--cortex-home")
        del arguments[home_index : home_index + 2]
        return arguments

    def patch_atomic_rename(self, module, before_rename) -> None:
        """Inject immediately before the configurator's atomic rename syscall."""
        if hasattr(module, "_rename_at"):
            original = module._rename_at

            def wrapped(directory_fd, source, target, flags):
                before_rename(Path(source), Path(target), flags)
                return original(directory_fd, source, target, flags)

            module._rename_at = wrapped
            self.addCleanup(setattr, module, "_rename_at", original)
            return

        original = module.os.replace

        def wrapped(source, target, **kwargs):
            before_rename(Path(source), Path(target), None)
            return original(source, target, **kwargs)

        module.os.replace = wrapped
        self.addCleanup(setattr, module.os, "replace", original)

    def test_verified_configuration_is_published_privately_and_idempotently(self) -> None:
        module = self.load_module()
        observed: list[dict[str, object]] = []

        def verify(path: Path) -> int:
            first_run = not observed
            observed.append(json.loads(path.read_text(encoding="utf-8")))
            self.assertNotEqual(path.name, "storage-bootstrap.json")
            if first_run:
                self.assertFalse((self.home / "storage-required").exists())
            return 0

        self.assertEqual(module.main(self.arguments(), guard_runner=verify), 0)
        self.assertEqual(module.main(self.arguments(), guard_runner=verify), 0)

        bootstrap = self.home / "storage-bootstrap.json"
        marker = self.home / "storage-required"
        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(json.loads(bootstrap.read_text(encoding="utf-8")), observed[0])
        self.assertEqual(marker.read_text(encoding="utf-8"), "required\n")
        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(bootstrap.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)
        self.assertEqual(list(self.home.glob(".storage-bootstrap.*")), [])
        self.assertEqual(list(self.home.glob(".storage-required.*")), [])

    def test_environment_runtime_home_is_used_when_cli_override_is_absent(self) -> None:
        module = self.load_module()
        custom_home = self.root / "custom-state" / "cortex-bridge"
        isolated_fallback_home = self.root / "fallback-user-home"
        isolated_fallback_home.mkdir()

        with patch.dict(
            os.environ,
            {"CORTEX_HOME": str(custom_home)},
            clear=False,
        ), patch("pathlib.Path.home", return_value=isolated_fallback_home):
            self.assertEqual(
                module.main(
                    self.arguments_without_runtime_home(),
                    guard_runner=lambda _path: 0,
                ),
                0,
            )

        self.assertTrue((custom_home / "storage-bootstrap.json").is_file())
        self.assertTrue((custom_home / "storage-required").is_file())
        self.assertFalse((self.home / "storage-bootstrap.json").exists())

    def test_guard_failure_leaves_no_partial_configuration(self) -> None:
        module = self.load_module()

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 6), 6)

        self.assertFalse((self.home / "storage-bootstrap.json").exists())
        self.assertFalse((self.home / "storage-required").exists())
        self.assertEqual(list(self.home.glob(".storage-bootstrap.*")), [])

    def test_guard_failure_preserves_existing_configuration(self) -> None:
        module = self.load_module()
        self.home.mkdir(parents=True)
        bootstrap = self.home / "storage-bootstrap.json"
        marker = self.home / "storage-required"
        bootstrap.write_text('{"existing":true}\n', encoding="utf-8")
        marker.write_text("required\n", encoding="utf-8")

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 4), 4)

        self.assertEqual(bootstrap.read_text(encoding="utf-8"), '{"existing":true}\n')
        self.assertEqual(marker.read_text(encoding="utf-8"), "required\n")

    def test_relative_or_external_runtime_home_is_rejected_before_verification(self) -> None:
        module = self.load_module()
        calls = 0

        def verify(_path: Path) -> int:
            nonlocal calls
            calls += 1
            return 0

        relative = self.arguments()
        relative[1] = "relative/state"
        external = self.arguments()
        external[1] = str(
            Path("/") / "Volumes" / "External" / "CORTEX_BRIDGE" / "runtime"
        )
        case_alias = self.arguments()
        case_alias[1] = str(
            Path("/") / "volumes" / "External" / "CORTEX_BRIDGE" / "runtime"
        )

        self.assertEqual(module.main(relative, guard_runner=verify), 2)
        self.assertEqual(module.main(external, guard_runner=verify), 2)
        self.assertEqual(module.main(case_alias, guard_runner=verify), 2)
        self.assertEqual(calls, 0)

    def test_broad_runtime_home_is_rejected_before_verification(self) -> None:
        module = self.load_module()
        arguments = self.arguments()
        arguments[1] = str(Path.home())

        self.assertEqual(
            module.main(
                arguments,
                guard_runner=lambda _path: self.fail("guard must not run"),
            ),
            2,
        )

    def test_symlinked_runtime_home_leaf_is_rejected_without_mutation(self) -> None:
        module = self.load_module()
        real_home = self.root / "real-home"
        real_home.mkdir()
        sentinel = real_home / "sentinel"
        sentinel.write_text("preserve", encoding="utf-8")
        self.home.parent.mkdir(parents=True)
        self.home.symlink_to(real_home, target_is_directory=True)

        self.assertEqual(
            module.main(
                self.arguments(),
                guard_runner=lambda _path: self.fail("guard must not run"),
            ),
            2,
        )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(list(real_home.iterdir()), [sentinel])

    def test_symlinked_control_file_is_rejected(self) -> None:
        module = self.load_module()
        self.home.mkdir(parents=True)

        victim = self.root / "victim"
        victim.write_text("preserve", encoding="utf-8")
        (self.home / "storage-bootstrap.json").symlink_to(victim)
        self.assertEqual(
            module.main(
                self.arguments(),
                guard_runner=lambda _path: self.fail("guard must not run"),
            ),
            2,
        )
        self.assertEqual(victim.read_text(encoding="utf-8"), "preserve")

    def test_symlinked_runtime_home_ancestor_is_rejected(self) -> None:
        module = self.load_module()
        external_target = self.root / "external-target"
        external_target.mkdir()
        sentinel = external_target / "sentinel"
        sentinel.write_text("preserve", encoding="utf-8")
        alias = self.root / "alias"
        alias.symlink_to(external_target, target_is_directory=True)
        arguments = self.arguments()
        arguments[1] = str(alias / "cortex-bridge")

        self.assertEqual(
            module.main(
                arguments,
                guard_runner=lambda _path: self.fail("guard must not run"),
            ),
            2,
        )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(list(external_target.iterdir()), [sentinel])

    def test_environment_runtime_home_symlink_is_rejected_without_mutation(self) -> None:
        module = self.load_module()
        real_home = self.root / "environment-real-home"
        real_home.mkdir()
        sentinel = real_home / "sentinel"
        sentinel.write_text("preserve", encoding="utf-8")
        alias = self.root / "environment-alias"
        alias.symlink_to(real_home, target_is_directory=True)
        fallback_home = self.root / "fallback-user-home"
        fallback_home.mkdir()

        with patch.dict(
            os.environ,
            {"CORTEX_HOME": str(alias)},
            clear=False,
        ), patch("pathlib.Path.home", return_value=fallback_home):
            self.assertEqual(
                module.main(
                    self.arguments_without_runtime_home(),
                    guard_runner=lambda _path: self.fail("guard must not run"),
                ),
                2,
            )

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(list(real_home.iterdir()), [sentinel])

    def test_runtime_home_replacement_before_publication_is_not_mutated(self) -> None:
        module = self.load_module()
        displaced = self.root / "displaced-cortex-home"
        replacement_sentinel = "foreign replacement"
        copied_temporary_names: list[str] = []

        def replace_runtime_home(_verification: Path) -> int:
            copied_temporary_names.extend(
                child.name
                for child in self.home.iterdir()
                if child.name.startswith((".storage-bootstrap.", ".storage-required."))
            )
            self.home.rename(displaced)
            self.home.mkdir()
            (self.home / "sentinel").write_text(
                replacement_sentinel,
                encoding="utf-8",
            )
            for name in copied_temporary_names:
                (self.home / name).write_text("foreign temporary", encoding="utf-8")
            return 0

        self.assertEqual(
            module.main(self.arguments(), guard_runner=replace_runtime_home),
            2,
        )
        self.assertEqual(
            (self.home / "sentinel").read_text(encoding="utf-8"),
            replacement_sentinel,
        )
        for name in copied_temporary_names:
            self.assertEqual(
                (self.home / name).read_text(encoding="utf-8"),
                "foreign temporary",
            )
        self.assertFalse((displaced / "storage-bootstrap.json").exists())
        self.assertFalse((displaced / "storage-required").exists())

    def test_runtime_home_appearing_after_preflight_is_not_adopted(self) -> None:
        module = self.load_module()
        original_ensure = module._ensure_private_home
        sentinel = self.home / "sentinel"

        def inject_foreign_home(home, expected_existing):
            self.home.mkdir(parents=True, mode=0o755)
            self.home.chmod(0o755)
            sentinel.write_text("foreign", encoding="utf-8")
            return original_ensure(home, expected_existing)

        module._ensure_private_home = inject_foreign_home
        self.addCleanup(setattr, module, "_ensure_private_home", original_ensure)

        self.assertEqual(
            module.main(self.arguments(), guard_runner=lambda _path: 0),
            2,
        )
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "foreign")
        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o755)
        self.assertEqual(list(self.home.iterdir()), [sentinel])

    def test_marker_appearing_at_exclusive_publication_is_preserved(self) -> None:
        module = self.load_module()
        marker = self.home / "storage-required"
        injected = False

        def create_foreign_marker(_source: Path, target: Path, _flags) -> None:
            nonlocal injected
            if target.name == marker.name and not injected:
                injected = True
                marker.write_text("foreign marker", encoding="utf-8")

        self.patch_atomic_rename(module, create_foreign_marker)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "foreign marker")
        self.assertFalse((self.home / "storage-bootstrap.json").exists())

    def test_bootstrap_appearing_at_exclusive_publication_is_preserved(self) -> None:
        module = self.load_module()
        bootstrap = self.home / "storage-bootstrap.json"
        injected = False

        def create_foreign_bootstrap(_source: Path, target: Path, _flags) -> None:
            nonlocal injected
            if target.name == bootstrap.name and not injected:
                injected = True
                bootstrap.write_text("foreign bootstrap", encoding="utf-8")

        self.patch_atomic_rename(module, create_foreign_bootstrap)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertEqual(
            bootstrap.read_text(encoding="utf-8"),
            "foreign bootstrap",
        )
        self.assertEqual(
            (self.home / "storage-required").read_text(encoding="utf-8"),
            "required\n",
        )

    def test_existing_marker_replaced_before_swap_is_rolled_back(self) -> None:
        module = self.load_module()
        self.home.mkdir(parents=True)
        marker = self.home / "storage-required"
        marker.write_text("previous marker", encoding="utf-8")
        displaced = self.root / "previous-marker"
        injected = False

        def replace_existing_marker(_source: Path, target: Path, flags) -> None:
            nonlocal injected
            if target.name == marker.name and flags == module.RENAME_SWAP and not injected:
                injected = True
                marker.rename(displaced)
                marker.write_text("foreign replacement", encoding="utf-8")

        self.patch_atomic_rename(module, replace_existing_marker)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "foreign replacement")
        self.assertEqual(displaced.read_text(encoding="utf-8"), "previous marker")
        self.assertFalse((self.home / "storage-bootstrap.json").exists())

    def test_existing_marker_symlink_race_is_rolled_back(self) -> None:
        module = self.load_module()
        self.home.mkdir(parents=True)
        marker = self.home / "storage-required"
        marker.write_text("previous marker", encoding="utf-8")
        displaced = self.root / "previous-marker"
        victim = self.root / "victim"
        victim.write_text("preserve", encoding="utf-8")
        injected = False

        def replace_marker_with_symlink(_source: Path, target: Path, flags) -> None:
            nonlocal injected
            if target.name == marker.name and flags == module.RENAME_SWAP and not injected:
                injected = True
                marker.rename(displaced)
                marker.symlink_to(victim)

        self.patch_atomic_rename(module, replace_marker_with_symlink)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertTrue(marker.is_symlink())
        self.assertEqual(marker.readlink(), victim)
        self.assertEqual(victim.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(displaced.read_text(encoding="utf-8"), "previous marker")
        self.assertFalse((self.home / "storage-bootstrap.json").exists())

    def test_verification_temporary_substitution_is_preserved_on_cleanup(self) -> None:
        module = self.load_module()
        escaped = self.root / "escaped-verification"
        substituted: Path | None = None

        def replace_verification(verification: Path) -> int:
            nonlocal substituted
            substituted = verification
            verification.rename(escaped)
            verification.write_text("foreign verification", encoding="utf-8")
            return 6

        self.assertEqual(
            module.main(self.arguments(), guard_runner=replace_verification),
            2,
        )
        self.assertIsNotNone(substituted)
        self.assertEqual(substituted.read_text(encoding="utf-8"), "foreign verification")
        self.assertTrue(escaped.is_file())

    def test_marker_temporary_substitution_is_preserved_on_cleanup(self) -> None:
        module = self.load_module()
        escaped = self.root / "escaped-marker"
        substituted: Path | None = None

        def replace_marker(_verification: Path) -> int:
            nonlocal substituted
            substituted = next(self.home.glob(".storage-required.write-*"))
            substituted.rename(escaped)
            substituted.write_text("foreign marker temporary", encoding="utf-8")
            return 6

        self.assertEqual(
            module.main(self.arguments(), guard_runner=replace_marker),
            2,
        )
        self.assertIsNotNone(substituted)
        self.assertEqual(
            substituted.read_text(encoding="utf-8"),
            "foreign marker temporary",
        )
        self.assertTrue(escaped.is_file())

    def test_bootstrap_temporary_substitution_is_preserved_on_cleanup(self) -> None:
        module = self.load_module()
        escaped = self.root / "escaped-bootstrap"
        substituted: Path | None = None

        def replace_bootstrap_temporary(
            source: Path,
            target: Path,
            _flags,
        ) -> None:
            nonlocal substituted
            if target.name != "storage-bootstrap.json":
                return
            substituted = self.home / source.name
            substituted.rename(escaped)
            substituted.write_text("foreign bootstrap temporary", encoding="utf-8")
            raise OSError("injected bootstrap publication failure")

        self.patch_atomic_rename(module, replace_bootstrap_temporary)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertIsNotNone(substituted)
        self.assertEqual(
            substituted.read_text(encoding="utf-8"),
            "foreign bootstrap temporary",
        )
        self.assertTrue(escaped.is_file())

    def test_marker_is_published_first_so_a_second_replace_failure_fails_closed(self) -> None:
        module = self.load_module()
        self.home.mkdir(parents=True)
        bootstrap = self.home / "storage-bootstrap.json"
        marker = self.home / "storage-required"
        bootstrap.write_text('{"existing":true}\n', encoding="utf-8")

        def fail_bootstrap_publication(
            _source: Path,
            destination: Path,
            _flags,
        ) -> None:
            if destination.name == "storage-bootstrap.json":
                raise OSError("injected bootstrap publication failure")

        self.patch_atomic_rename(module, fail_bootstrap_publication)

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "required\n")
        self.assertEqual(bootstrap.read_text(encoding="utf-8"), '{"existing":true}\n')
        self.assertEqual(list(self.home.glob(".storage-bootstrap.*")), [])
        self.assertEqual(list(self.home.glob(".storage-required.*")), [])

    def test_second_temporary_write_failure_cleans_the_first_temporary(self) -> None:
        module = self.load_module()
        original_write = module._write_private_temporary

        def fail_marker_temporary(
            home: Path,
            prefix: str,
            payload: bytes,
            *,
            directory_fd: int | None = None,
        ) -> object:
            if prefix.startswith(".storage-required"):
                raise OSError("injected marker temporary failure")
            return original_write(
                home,
                prefix,
                payload,
                directory_fd=directory_fd,
            )

        module._write_private_temporary = fail_marker_temporary
        self.addCleanup(
            setattr,
            module,
            "_write_private_temporary",
            original_write,
        )

        self.assertEqual(module.main(self.arguments(), guard_runner=lambda _path: 0), 2)
        self.assertFalse((self.home / "storage-bootstrap.json").exists())
        self.assertFalse((self.home / "storage-required").exists())
        self.assertEqual(list(self.home.glob(".storage-bootstrap.*")), [])
        self.assertEqual(list(self.home.glob(".storage-required.*")), [])

    def test_paths_and_uuid_are_validated_before_verification(self) -> None:
        module = self.load_module()
        bad_uuid = self.arguments()
        bad_uuid[bad_uuid.index("--volume-uuid") + 1] = "not-a-uuid"
        relative_storage = self.arguments()
        relative_storage[relative_storage.index("--storage-root") + 1] = "relative"
        wrong_image = self.arguments()
        wrong_image[wrong_image.index("--encrypted-image-path") + 1] = str(
            self.root / "plain-directory"
        )

        for arguments in (bad_uuid, relative_storage, wrong_image):
            with self.subTest(arguments=arguments):
                self.assertEqual(
                    module.main(
                        arguments,
                        guard_runner=lambda _path: self.fail("guard must not run"),
                    ),
                    2,
                )


if __name__ == "__main__":
    unittest.main()
