#!/usr/bin/env python3
"""Pure contract tests for the macOS disk-image/Keychain helper.

The default runner compiles only the fake-adapter harness. Real Keychain and
DiskImages effects are unreachable unless both explicit integration gates are
present; the focused suite below never supplies the authorization environment.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/macos/disk_image_keychain.swift"
PYTHON = ROOT / ".venv/py311/bin/python"
AUTHORIZATION = "YES_DISPOSABLE_64_MIB_ONLY"


def _consume_integration_flags():
    integration = "--integration" in sys.argv
    allow_effects = "--allow-effects" in sys.argv
    if integration or allow_effects:
        authorized = os.environ.get("CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION")
        if not (integration and allow_effects and authorized == AUTHORIZATION):
            raise SystemExit(64)
        # This task's default suite is intentionally fake-only. A separately
        # approved live run may add its integration TestCase without weakening
        # either gate.
        sys.argv = [
            argument
            for argument in sys.argv
            if argument not in {"--integration", "--allow-effects"}
        ]


_consume_integration_flags()


class DiskImageKeychainHelperTests(unittest.TestCase):
    """The helper owns the secret and exposes only non-secret observations."""

    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary_directory.name) / "disk-image-keychain-test"
        cls.source_exists = SOURCE.is_file()
        if cls.source_exists:
            completed = subprocess.run(
                [
                    "xcrun",
                    "swiftc",
                    "-D",
                    "CORTEX_STORAGE_HELPER_TESTING",
                    str(SOURCE),
                    "-framework",
                    "Security",
                    "-o",
                    str(cls.binary),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise AssertionError(
                    "disk image Keychain helper did not compile:\n"
                    f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                )

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def setUp(self):
        self.assertTrue(
            self.source_exists,
            f"missing required native helper: {SOURCE}",
        )

    @staticmethod
    def request(operation, **overrides):
        request = {
            "schema_version": 1,
            "operation": operation,
            "image_path": "/private/tmp/CORTEX_TEST.sparsebundle",
            "mount_path": "/private/tmp/CORTEX_TEST_MOUNT",
            "volume_name": "CORTEX_BRIDGE_SPIKE",
            "size": "64m",
            "transaction_id": "12345678-1234-4234-8234-123456789abc",
            "expected_encryption_uuid": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
            "disposable": True,
            "cleanup_approved": True,
        }
        request.update(overrides)
        return request

    def run_helper(self, operation, scenario="success", **overrides):
        completed = subprocess.run(
            [str(self.binary), "--test-scenario", scenario],
            input=json.dumps(self.request(operation, **overrides)) + "\n",
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertIn(completed.returncode, {0, 64, 70}, completed.stderr)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.stdout.count("\n"), 1, completed.stdout)
        return completed, json.loads(completed.stdout)

    def test_create_generates_32_bytes_as_43_base64url_characters_and_one_pipe_nul(self):
        completed, observation = self.run_helper(
            "create", expected_encryption_uuid=None
        )
        self.assertEqual(completed.returncode, 0)
        create_call = observation["hdiutil_calls"][0]
        self.assertEqual(
            create_call["argv"],
            [
                "/usr/bin/hdiutil",
                "create",
                "-stdinpass",
                "-encryption",
                "AES-256",
                "-type",
                "SPARSEBUNDLE",
                "-size",
                "64m",
                "-fs",
                "APFS",
                "-volname",
                "CORTEX_BRIDGE_SPIKE",
                "/private/tmp/CORTEX_TEST.sparsebundle",
            ],
        )
        self.assertEqual(create_call["source_random_byte_count"], 32)
        self.assertEqual(create_call["secret_payload_count"], 43)
        self.assertTrue(create_call["secret_payload_is_base64url"])
        self.assertEqual(create_call["secret_wire_count"], 44)
        self.assertEqual(create_call["terminal_nul_count"], 1)
        self.assertFalse(create_call["secret_payload_contains_nul"])

    def test_child_policy_uses_cloexec_default_minimal_environment_and_no_foreign_fd(self):
        _, observation = self.run_helper("create", expected_encryption_uuid=None)
        for call in observation["hdiutil_calls"]:
            self.assertTrue(call["posix_spawn_cloexec_default"])
            self.assertEqual(call["unrelated_inherited_fd_count"], 0)
            self.assertEqual(
                call["environment"],
                [
                    "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                    "LANG=C",
                    "LC_ALL=C",
                ],
            )
            self.assertFalse(any(value.startswith("HOME=") for value in call["environment"]))

    def test_real_spawn_probe_closes_foreign_fd_and_delivers_exact_wire_format(self):
        completed = subprocess.run(
            [str(self.binary), "--spawn-probe"],
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.stdout.count("\n"), 1)
        observation = json.loads(completed.stdout)
        self.assertTrue(observation["foreign_fd_closed"])
        self.assertEqual(set(observation["open_fds"]), {0, 1, 2})
        self.assertEqual(observation["secret_wire_count"], 44)
        self.assertEqual(observation["secret_payload_count"], 43)
        self.assertEqual(observation["terminal_nul_count"], 1)
        self.assertTrue(observation["secret_payload_is_base64url"])
        self.assertTrue(observation["parent_buffer_zeroed"])
        self.assertEqual(
            observation.get("environment"),
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
        self.assertFalse(observation["home_present"])

    def test_create_adds_only_the_exact_keychain_schema(self):
        _, observation = self.run_helper("create", expected_encryption_uuid=None)
        add_call = next(
            call for call in observation["keychain_calls"] if call["action"] == "add"
        )
        self.assertEqual(
            add_call,
            {
                "action": "add",
                "class": "generic-password",
                "account": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
                "service": "com.cortexbridge.encrypted-storage",
                "label": "CORTEX_TEST.sparsebundle",
                "description": "disk image password",
                "generic_tag": "12345678-1234-4234-8234-123456789abc",
                "data_protection_keychain": True,
                "accessible": "when-unlocked-this-device-only",
                "synchronizable": False,
                "authentication_ui": "fail",
                "secret_length": 43,
            },
        )

    def test_create_rejects_uuid_service_collision_without_updating_item(self):
        completed, observation = self.run_helper(
            "create", scenario="collision", expected_encryption_uuid=None
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "KEYCHAIN_ITEM_COLLISION")
        self.assertFalse(any(call["action"] == "add" for call in observation["keychain_calls"]))
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_create_rejects_unverified_encryption_metadata_before_keychain_add(self):
        completed, observation = self.run_helper(
            "create", scenario="bad-encryption", expected_encryption_uuid=None
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "IMAGE_ENCRYPTION_INVALID")
        self.assertFalse(any(call["action"] == "add" for call in observation["keychain_calls"]))
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_mount_reads_exact_item_and_passes_secret_to_exact_attach_argv(self):
        completed, observation = self.run_helper("mount")
        self.assertEqual(completed.returncode, 0)
        attach_call = next(
            call for call in observation["hdiutil_calls"] if call["argv"][1] == "attach"
        )
        self.assertEqual(
            attach_call["argv"],
            [
                "/usr/bin/hdiutil",
                "attach",
                "-stdinpass",
                "-owners",
                "on",
                "-nobrowse",
                "-mountpoint",
                "/private/tmp/CORTEX_TEST_MOUNT",
                "/private/tmp/CORTEX_TEST.sparsebundle",
            ],
        )
        self.assertEqual(attach_call["secret_wire_count"], 44)
        self.assertEqual(attach_call["terminal_nul_count"], 1)
        read_call = next(
            call for call in observation["keychain_calls"] if call["action"] == "read"
        )
        self.assertEqual(
            read_call,
            {
                "action": "read",
                "class": "generic-password",
                "account": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
                "service": "com.cortexbridge.encrypted-storage",
                "generic_tag": "12345678-1234-4234-8234-123456789abc",
                "data_protection_keychain": True,
                "synchronizable": False,
                "authentication_ui": "fail",
            },
        )
        self.assertEqual(observation["response"]["device"], "/dev/disk99")
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_mount_rejects_zero_or_multiple_keychain_matches_before_hdiutil(self):
        for scenario, code in (
            ("zero-match", "KEYCHAIN_ITEM_NOT_FOUND"),
            ("multiple-match", "KEYCHAIN_ITEM_AMBIGUOUS"),
        ):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper("mount", scenario=scenario)
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(observation["response"]["code"], code)
                self.assertEqual(observation["hdiutil_calls"], [])

    def test_interaction_forbidden_is_terminal_with_zero_hdiutil_calls(self):
        completed, observation = self.run_helper("mount", scenario="interaction")
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(
            observation["response"]["code"], "KEYCHAIN_INTERACTION_FORBIDDEN"
        )
        self.assertEqual(observation["hdiutil_calls"], [])
        self.assertEqual(observation["security_agent_observations"], 0)

    def test_mount_hdiutil_error_still_zeroes_every_secret_buffer(self):
        completed, observation = self.run_helper("mount", scenario="hdiutil-error")
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "HDIUTIL_FAILED")
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_inspect_requires_exactly_one_strict_match(self):
        completed, observation = self.run_helper("inspect-item")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(observation["response"]["item_count"], 1)
        self.assertEqual(observation["keychain_calls"][0]["action"], "inspect")
        for scenario, code in (
            ("zero-match", "KEYCHAIN_ITEM_NOT_FOUND"),
            ("multiple-match", "KEYCHAIN_ITEM_AMBIGUOUS"),
        ):
            with self.subTest(scenario=scenario):
                failed, failed_observation = self.run_helper(
                    "inspect-item", scenario=scenario
                )
                self.assertEqual(failed.returncode, 70)
                self.assertEqual(failed_observation["response"]["code"], code)

    def test_delete_requires_both_disposable_and_cleanup_approval_before_query(self):
        for overrides in (
            {"disposable": False},
            {"cleanup_approved": False},
        ):
            with self.subTest(overrides=overrides):
                completed, observation = self.run_helper(
                    "delete-disposable-item", **overrides
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(
                    observation["response"]["code"], "CLEANUP_NOT_AUTHORIZED"
                )
                self.assertEqual(observation["keychain_calls"], [])
                self.assertEqual(observation["hdiutil_calls"], [])

    def test_delete_matches_once_then_deletes_with_the_same_strict_query(self):
        completed, observation = self.run_helper("delete-disposable-item")
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            [call["action"] for call in observation["keychain_calls"]],
            ["inspect", "delete"],
        )
        inspect_query = dict(observation["keychain_calls"][0])
        delete_query = dict(observation["keychain_calls"][1])
        inspect_query.pop("action")
        delete_query.pop("action")
        self.assertEqual(delete_query, inspect_query)
        self.assertEqual(delete_query["service"], "com.cortexbridge.encrypted-storage")
        self.assertEqual(delete_query["account"], "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE")
        self.assertEqual(
            delete_query["generic_tag"], "12345678-1234-4234-8234-123456789abc"
        )

    def test_delete_rejects_zero_or_multiple_matches_without_delete(self):
        for scenario, code in (
            ("zero-match", "KEYCHAIN_ITEM_NOT_FOUND"),
            ("multiple-match", "KEYCHAIN_ITEM_AMBIGUOUS"),
        ):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper(
                    "delete-disposable-item", scenario=scenario
                )
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(observation["response"]["code"], code)
                self.assertFalse(
                    any(call["action"] == "delete" for call in observation["keychain_calls"])
                )

    def test_detach_resolves_one_verified_mapping_and_never_forces(self):
        completed, observation = self.run_helper("detach")
        self.assertEqual(completed.returncode, 0)
        detach_call = observation["hdiutil_calls"][-1]
        self.assertEqual(
            detach_call["argv"],
            ["/usr/bin/hdiutil", "detach", "/dev/disk99"],
        )
        self.assertNotIn("-force", detach_call["argv"])

    def test_detach_rejects_zero_or_multiple_verified_mappings_before_detach(self):
        for scenario in ("mapping-zero", "mapping-multiple"):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper("detach", scenario=scenario)
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(
                    observation["response"]["code"], "MOUNT_MAPPING_INVALID"
                )
                self.assertFalse(
                    any(call["argv"][1] == "detach" for call in observation["hdiutil_calls"])
                )

    def test_response_is_one_nonsecret_json_line_with_only_contract_fields(self):
        _, observation = self.run_helper("mount")
        response = observation["response"]
        self.assertEqual(
            set(response),
            {
                "schema_version",
                "operation",
                "code",
                "encryption_uuid",
                "device",
                "item_count",
            },
        )
        serialized = json.dumps(response)
        self.assertNotIn("CORTEX_TEST.sparsebundle", serialized)
        self.assertNotIn("CORTEX_TEST_MOUNT", serialized)
        self.assertNotIn("secret", serialized.lower())

    def test_malformed_or_extra_cli_input_fails_before_any_effect(self):
        for stdin, arguments in (
            ("not-json\n", ("--test-scenario", "success")),
            (json.dumps(self.request("mount")) + "\n", ("--unknown",)),
        ):
            with self.subTest(stdin=stdin, arguments=arguments):
                completed = subprocess.run(
                    [str(self.binary), *arguments],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    check=False,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 64)

    def test_integration_runner_exits_64_when_either_effect_gate_is_missing(self):
        clean_environment = os.environ.copy()
        clean_environment.pop("CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION", None)
        for arguments in (
            ("--integration",),
            ("--allow-effects",),
            ("--integration", "--allow-effects"),
        ):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [str(PYTHON), str(Path(__file__).resolve()), *arguments],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=clean_environment,
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
