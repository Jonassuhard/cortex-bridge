#!/usr/bin/env python3
"""Pure contract tests for the macOS disk-image/Keychain helper.

The default runner compiles only the fake-adapter harness. Real Keychain and
DiskImages effects are unreachable unless both explicit integration gates are
present; the focused suite below never supplies the authorization environment.
"""

import json
import inspect
import os
import plistlib
import ctypes
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from dataclasses import dataclass
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/macos/disk_image_keychain.swift"
PYTHON = ROOT / ".venv/py311/bin/python"
AUTHORIZATION = "YES_DISPOSABLE_64_MIB_ONLY"
COMMAND_TIMEOUT_SECONDS = 60


class EffectGateRejected(Exception):
    pass


class LiveCapabilityRequired(Exception):
    pass


class ObservationUnavailable(Exception):
    pass


_LIVE_CAPABILITY_SEAL = object()


@dataclass(frozen=True)
class LiveCapability:
    _seal: object
    cleanup_approved: bool


def _require_live_capability(capability):
    if not isinstance(capability, LiveCapability) or capability._seal is not _LIVE_CAPABILITY_SEAL:
        raise LiveCapabilityRequired


@dataclass(frozen=True)
class ExecutionMode:
    mode: str
    cleanup_approved: bool


@dataclass(frozen=True)
class IntegrationOutcome:
    status: str
    code: str


@dataclass(frozen=True)
class LiveIntegrationPlan:
    image_path: Path
    mount_path: Path
    quarantine_path: Path
    transaction_id: str
    size: str
    filesystem: str
    volume_name: str


def build_live_plan(private_root, *, unique, transaction_id):
    private_root = Path(private_root)
    if not private_root.is_absolute():
        raise ValueError("private root must be absolute")
    if len(unique) != 32 or any(character not in "0123456789abcdef" for character in unique):
        raise ValueError("invalid unique identifier")
    if str(uuid.UUID(transaction_id)) != transaction_id.lower():
        raise ValueError("invalid transaction identifier")
    image_path = private_root / f"CORTEX_BRIDGE_SPIKE_{unique}.sparsebundle"
    return LiveIntegrationPlan(
        image_path=image_path,
        mount_path=private_root / f"mount-{unique}",
        quarantine_path=private_root / f"{image_path.name}.quarantine",
        transaction_id=transaction_id,
        size="64m",
        filesystem="APFS",
        volume_name="CORTEX_BRIDGE_SPIKE",
    )


class SecurityAgentDetected(Exception):
    pass


class IntegrationWorkflowFailure(Exception):
    pass


def select_execution_mode(arguments, environment):
    arguments = list(arguments)
    authorization = environment.get("CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION")
    if not arguments and authorization is None:
        return ExecutionMode("fake", False)

    allowed = {"--integration", "--allow-effects", "--cleanup-approved"}
    if any(argument not in allowed for argument in arguments):
        raise EffectGateRejected
    if len(arguments) != len(set(arguments)):
        raise EffectGateRejected
    required = {"--integration", "--allow-effects"}
    if not required.issubset(arguments) or authorization != AUTHORIZATION:
        raise EffectGateRejected
    if set(arguments) not in (required, required | {"--cleanup-approved"}):
        raise EffectGateRejected
    return ExecutionMode("live", "--cleanup-approved" in arguments)


def dispatch_execution_mode(
    arguments,
    environment,
    *,
    fake_runner,
    live_runner,
):
    selection = select_execution_mode(arguments, environment)
    if selection.mode == "live":
        return live_runner(selection.cleanup_approved)
    return fake_runner()


def _consume_execution_mode():
    try:
        selection = select_execution_mode(sys.argv[1:], os.environ)
    except EffectGateRejected:
        raise SystemExit(64)
    sys.argv = [sys.argv[0]]
    return selection


def _main_execution_state():
    selection = _consume_execution_mode()
    capability = None
    if selection.mode == "live":
        capability = LiveCapability(_LIVE_CAPABILITY_SEAL, selection.cleanup_approved)
    return selection, capability


def _require_response(response, operation, *, uuid_value=None, device=None, item_count=None):
    if set(response) != {
        "schema_version",
        "operation",
        "code",
        "encryption_uuid",
        "device",
        "item_count",
    }:
        raise IntegrationWorkflowFailure
    if response["schema_version"] != 1 or response["operation"] != operation:
        raise IntegrationWorkflowFailure
    if response["code"] != "OK":
        raise IntegrationWorkflowFailure
    if uuid_value is not None and response["encryption_uuid"] != uuid_value:
        raise IntegrationWorkflowFailure
    if device is not None and response["device"] != device:
        raise IntegrationWorkflowFailure
    if item_count is not None and response["item_count"] != item_count:
        raise IntegrationWorkflowFailure


def run_live_integration_workflow(*, effects, observer, cleanup_approved):
    try:
        baseline_processes, baseline_windows = observer.snapshot()
    except Exception:
        return IntegrationOutcome("UNCLEAR", "securityagent_observer_unavailable")
    if baseline_processes or baseline_windows:
        return IntegrationOutcome("UNCLEAR", "securityagent_baseline_nonempty")
    if hasattr(effects, "bind_observer"):
        effects.bind_observer(observer, (baseline_processes, baseline_windows))
    encryption_uuid = None

    def reject_new_securityagent():
        processes, windows = observer.snapshot()
        if processes - baseline_processes or windows - baseline_windows:
            raise SecurityAgentDetected

    def dispose(outcome):
        try:
            effects.dispose_after_failure(
                encryption_uuid=encryption_uuid,
                cleanup_approved=cleanup_approved,
            )
        except Exception:
            return IntegrationOutcome("UNCLEAR", "disposition_failed")
        return outcome

    try:
        effects.compile_production_helper()
        reject_new_securityagent()

        create_response, _ = effects.invoke_helper("create", effects.create_request())
        _require_response(create_response, "create", item_count=1)
        encryption_uuid = create_response["encryption_uuid"]
        if not isinstance(encryption_uuid, str) or not encryption_uuid:
            raise IntegrationWorkflowFailure
        reject_new_securityagent()

        mount_processes = []
        for _ in range(2):
            mount_response, process_token = effects.invoke_helper(
                "mount", effects.request("mount", encryption_uuid)
            )
            _require_response(mount_response, "mount", uuid_value=encryption_uuid)
            device = mount_response["device"]
            if not isinstance(device, str) or not device.startswith("/dev/disk"):
                raise IntegrationWorkflowFailure
            mount_processes.append(process_token)
            reject_new_securityagent()

            effects.verify_mounted(encryption_uuid, device)
            reject_new_securityagent()

            detach_response, _ = effects.invoke_helper(
                "detach", effects.request("detach", encryption_uuid)
            )
            _require_response(
                detach_response,
                "detach",
                uuid_value=encryption_uuid,
                device=device,
            )
            reject_new_securityagent()

            effects.verify_detached(device)
            reject_new_securityagent()

        if len(set(mount_processes)) != 2:
            raise IntegrationWorkflowFailure

        inspect_response, _ = effects.invoke_helper(
            "inspect-item", effects.request("inspect-item", encryption_uuid)
        )
        _require_response(
            inspect_response,
            "inspect-item",
            uuid_value=encryption_uuid,
            item_count=1,
        )
        reject_new_securityagent()

        if not cleanup_approved:
            effects.quarantine_exact_image()
            reject_new_securityagent()
            return IntegrationOutcome("UNCLEAR", "cleanup_not_authorized")

        delete_response, _ = effects.invoke_helper(
            "delete-disposable-item",
            effects.request(
                "delete-disposable-item",
                encryption_uuid,
                cleanup_approved=True,
            ),
        )
        _require_response(
            delete_response,
            "delete-disposable-item",
            uuid_value=encryption_uuid,
            item_count=0,
        )
        reject_new_securityagent()
        effects.delete_exact_image()
        reject_new_securityagent()
        return IntegrationOutcome("PASS", "integration_verified")
    except SecurityAgentDetected:
        return dispose(IntegrationOutcome("FAIL", "securityagent_detected"))
    except Exception:
        return dispose(IntegrationOutcome("FAIL", "integration_failed"))


if __name__ == "__main__":
    EXECUTION_MODE, LIVE_CAPABILITY = _main_execution_state()
else:
    EXECUTION_MODE, LIVE_CAPABILITY = ExecutionMode("fake", False), None


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
                timeout=COMMAND_TIMEOUT_SECONDS,
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
            timeout=COMMAND_TIMEOUT_SECONDS,
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
            timeout=COMMAND_TIMEOUT_SECONDS,
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
        self.assertTrue(observation["all_keychain_staging_zeroed"])
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_create_rejects_uuid_service_collision_without_updating_item(self):
        completed, observation = self.run_helper(
            "create", scenario="collision", expected_encryption_uuid=None
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "KEYCHAIN_ITEM_COLLISION")
        self.assertFalse(any(call["action"] == "add" for call in observation["keychain_calls"]))
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_add_collision_and_interaction_zeroize_staging_and_secret(self):
        for scenario, code in (
            ("add-collision", "KEYCHAIN_ITEM_COLLISION"),
            ("add-interaction", "KEYCHAIN_INTERACTION_FORBIDDEN"),
        ):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper(
                    "create", scenario=scenario, expected_encryption_uuid=None
                )
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(observation["response"]["code"], code)
                self.assertTrue(observation["all_buffers_zeroed"])
                self.assertTrue(observation["all_keychain_staging_zeroed"])

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
        self.assertEqual(
            [call["action"] for call in observation["keychain_calls"]],
            ["read-count", "read-one"],
        )
        read_call = observation["keychain_calls"][1]
        self.assertEqual(
            read_call,
            {
                "action": "read-one",
                "class": "generic-password",
                "account": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
                "service": "com.cortexbridge.encrypted-storage",
                "generic_tag": "12345678-1234-4234-8234-123456789abc",
                "data_protection_keychain": True,
                "synchronizable": False,
                "authentication_ui": "fail",
                "match_limit": "one",
                "return_data": True,
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
                self.assertEqual(
                    [call["action"] for call in observation["keychain_calls"]],
                    ["read-count"],
                )
                self.assertEqual(observation["secret_materializations"], 0)

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
        self.assertEqual(observation["response"]["code"], "MOUNT_CLEANUP_UNCLEAR")
        self.assertTrue(observation["all_buffers_zeroed"])

    def test_pipe_writes_secret_and_nul_separately_without_combined_buffer(self):
        completed = subprocess.run(
            [str(self.binary), "--spawn-probe"],
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertEqual(completed.returncode, 0)
        observation = json.loads(completed.stdout)
        self.assertEqual(observation["stdin_write_lengths"], [43, 1])
        self.assertFalse(observation["combined_wire_buffer_created"])

    def test_bounded_process_runner_handles_timeout_caps_epipe_exit_and_signal(self):
        expected = {
            "sleep": "PROCESS_TIMEOUT",
            "ignore-term-grandchild": "PROCESS_TIMEOUT",
            "stdout-cap": "PROCESS_OUTPUT_LIMIT",
            "stderr-cap": "PROCESS_OUTPUT_LIMIT",
            "epipe": "PROCESS_STDIN_FAILED",
            "nonzero": "PROCESS_EXIT_NONZERO",
            "signal": "PROCESS_SIGNALED",
        }
        for scenario, code in expected.items():
            with self.subTest(scenario=scenario):
                completed = subprocess.run(
                    [str(self.binary), "--process-scenario", scenario],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                observation = json.loads(completed.stdout)
                self.assertEqual(observation["code"], code)
                self.assertTrue(observation["direct_child_reaped"])
                self.assertTrue(observation["process_group_gone"])

    def test_mount_captures_baseline_and_compensates_each_safe_partial_attach(self):
        for scenario in (
            "post-encryption-failure",
            "post-mapping-failure",
            "postcheck-timeout",
            "attach-timeout-with-receipt",
        ):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper("mount", scenario=scenario)
                self.assertEqual(completed.returncode, 70)
                commands = [call["argv"][1] for call in observation["hdiutil_calls"]]
                self.assertEqual(commands[0], "info")
                detach = [
                    call for call in observation["hdiutil_calls"]
                    if call["argv"][1] == "detach"
                ]
                self.assertEqual(len(detach), 1)
                self.assertEqual(
                    detach[0]["argv"],
                    ["/usr/bin/hdiutil", "detach", "/dev/disk99"],
                )
                self.assertNotIn("-force", detach[0]["argv"])

    def test_mount_cleanup_unclear_never_detaches_blindly(self):
        for scenario in (
            "attach-timeout-no-receipt",
            "post-mapping-ambiguous",
            "compensation-detach-failure",
        ):
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper("mount", scenario=scenario)
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(
                    observation["response"]["code"], "MOUNT_CLEANUP_UNCLEAR"
                )
                detach = [
                    call for call in observation["hdiutil_calls"]
                    if call["argv"][1] == "detach"
                ]
                if scenario != "compensation-detach-failure":
                    self.assertEqual(detach, [])
                else:
                    self.assertEqual(len(detach), 1)

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
        invalid_plan = self.request("delete-disposable-item", disposable=False)
        completed = subprocess.run(
            [str(self.binary), "--test-scenario", "success"],
            input=json.dumps(invalid_plan) + "\n",
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stdout, "")

        completed, observation = self.run_helper(
            "delete-disposable-item", cleanup_approved=False
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
        detach_call = next(
            call for call in observation["hdiutil_calls"] if call["argv"][1] == "detach"
        )
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
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 64)

    def test_rejects_nonexact_json_shape_controls_unsafe_paths_and_unapproved_plan(self):
        valid = self.request("create", expected_encryption_uuid=None)
        invalid_payloads = []
        extra = dict(valid, passphrase="forbidden")
        invalid_payloads.append(extra)
        missing = dict(valid)
        missing.pop("size")
        invalid_payloads.append(missing)
        for field in ("image_path", "mount_path", "volume_name", "size"):
            controlled = dict(valid)
            controlled[field] = f"safe\nunsafe"
            invalid_payloads.append(controlled)
        invalid_payloads.extend(
            [
                dict(valid, image_path="relative.sparsebundle"),
                dict(valid, mount_path="/private/tmp/../escape"),
                dict(valid, size="65m"),
                dict(valid, volume_name="UNAPPROVED"),
                self.request("mount", disposable=False),
                self.request(
                    "mount",
                    size="256g",
                    volume_name="CORTEX_BRIDGE_2026_09",
                    disposable=True,
                ),
            ]
        )
        for payload in invalid_payloads:
            with self.subTest(payload_keys=sorted(payload)):
                completed = subprocess.run(
                    [str(self.binary), "--test-scenario", "success"],
                    input=json.dumps(payload) + "\n",
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")

        for codepoint in (*range(0x20), *range(0x7F, 0xA0)):
            control = chr(codepoint)
            controlled = dict(valid)
            for field in ("image_path", "mount_path", "volume_name", "size"):
                controlled[field] = f"safe{control}unsafe"
            with self.subTest(control=codepoint):
                completed = subprocess.run(
                    [str(self.binary), "--test-scenario", "success"],
                    input=json.dumps(controlled) + "\n",
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")

        truncated = json.dumps(valid)[:-1]
        completed = subprocess.run(
            [str(self.binary), "--test-scenario", "success"],
            input=truncated,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertEqual(completed.returncode, 64)
        self.assertEqual(completed.stdout, "")

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
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env=clean_environment,
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")


class FakeLiveEffects:
    """No-effect adapter used to test the gated integration orchestrator."""

    encryption_uuid = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"

    def __init__(self):
        self.calls = []
        self.process_tokens = []
        self.item_present = True

    def compile_production_helper(self):
        self.calls.append("compile-helper")

    def create_request(self):
        return {"operation": "create"}

    def request(self, operation, encryption_uuid, cleanup_approved=False):
        return {
            "operation": operation,
            "expected_encryption_uuid": encryption_uuid,
            "cleanup_approved": cleanup_approved,
        }

    def invoke_helper(self, operation, request):
        token = f"helper-process-{len(self.process_tokens) + 1}"
        self.process_tokens.append(token)
        self.calls.append(operation)
        response = {
            "schema_version": 1,
            "operation": operation,
            "code": "OK",
            "encryption_uuid": self.encryption_uuid,
            "device": "/dev/disk99" if operation in {"mount", "detach"} else None,
            "item_count": 1 if operation in {"create", "inspect-item"} else None,
        }
        if operation == "delete-disposable-item":
            self.item_present = False
            response["item_count"] = 0
        return response, token

    def verify_mounted(self, expected_uuid, expected_device):
        self.calls.append("verify-mounted")

    def verify_detached(self, expected_device):
        self.calls.append("verify-detached")

    def delete_exact_image(self):
        self.calls.append("delete-image")

    def quarantine_exact_image(self):
        self.calls.append("quarantine-image")

    def dispose_after_failure(self, *, encryption_uuid, cleanup_approved):
        if cleanup_approved:
            self.calls.append("cleanup-after-failure")
        else:
            self.quarantine_exact_image()


class FakeSecurityAgentObserver:
    def __init__(self, snapshots=None):
        self.snapshots = list(snapshots or [(frozenset(), frozenset())])
        self.index = 0

    def snapshot(self):
        snapshot = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return snapshot


class DiskImageKeychainIntegrationOrchestrationTests(unittest.TestCase):
    def test_imported_live_suite_without_capability_has_zero_effects(self):
        self.assertIn("LiveCapabilityRequired", globals(), "missing live capability gate")
        counters = {"observer": 0, "effects": 0}

        def observer_init(instance):
            counters["observer"] += 1

        def effects_init(instance, *args, **kwargs):
            counters["effects"] += 1

        suite = build_selected_suite(unittest.TestLoader(), ExecutionMode("live", False))
        result = unittest.TestResult()
        with mock.patch.object(LiveSecurityAgentObserver, "__init__", observer_init), mock.patch.object(
            LiveIntegrationEffects, "__init__", effects_init
        ):
            suite.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(counters, {"observer": 0, "effects": 0})
        with mock.patch("tempfile.mkdtemp") as make_root:
            with self.assertRaises(LiveCapabilityRequired):
                LiveIntegrationEffects(None)
            make_root.assert_not_called()

        uninitialized = object.__new__(LiveIntegrationEffects)
        uninitialized.capability = None
        guarded_calls = (
            lambda: uninitialized.compile_production_helper(),
            lambda: uninitialized._observe_bound(),
            lambda: uninitialized.invoke_helper("mount", {}),
            lambda: uninitialized.verify_mounted("uuid", "/dev/disk99"),
            lambda: uninitialized.verify_detached("/dev/disk99"),
            lambda: uninitialized.delete_exact_image(),
            lambda: uninitialized.quarantine_exact_image(),
            lambda: uninitialized.dispose_after_failure(
                encryption_uuid=None, cleanup_approved=False
            ),
        )
        for guarded_call in guarded_calls:
            with self.assertRaises(LiveCapabilityRequired):
                guarded_call()

    def test_fd_identity_substitution_and_concurrent_quarantine_target_fail_closed(self):
        effects = object.__new__(LiveIntegrationEffects)
        effects.root_fd = 9
        effects.image_fd = 10
        effects.image_name = "image.sparsebundle"
        effects.image_identity = (1, 2)
        descriptor_facts = mock.Mock(st_dev=1, st_ino=2, st_mode=stat.S_IFDIR)
        substituted_facts = mock.Mock(st_dev=1, st_ino=3, st_mode=stat.S_IFDIR)
        effects.capability = None
        with mock.patch(
            f"{__name__}._require_live_capability", return_value=None
        ), mock.patch("os.fstat", return_value=descriptor_facts), mock.patch(
            "os.stat", return_value=substituted_facts
        ):
            with self.assertRaises(IntegrationWorkflowFailure):
                effects._require_exact_image()

        effects.quarantine_path = Path("/private/tmp/image.sparsebundle.quarantine")
        effects._require_reconciled_unmounted = mock.Mock()
        effects._require_exact_image = mock.Mock()
        with mock.patch(
            f"{__name__}._require_live_capability", return_value=None
        ), mock.patch("os.stat", return_value=substituted_facts), mock.patch(
            "ctypes.CDLL"
        ) as load_libc:
            with self.assertRaises(IntegrationWorkflowFailure):
                effects.quarantine_exact_image()
            load_libc.assert_not_called()
        effects.root_fd = -1
        effects.image_fd = -1

    def test_observer_parser_fails_closed_when_windows_are_unavailable(self):
        self.assertIn(
            "parse_securityagent_snapshot", globals(), "missing observer fail-closed parser"
        )
        with self.assertRaises(ObservationUnavailable):
            parse_securityagent_snapshot(
                {
                    "processes": [],
                    "processes_available": True,
                    "windows": [],
                    "windows_available": False,
                }
            )
        with self.assertRaises(ObservationUnavailable):
            parse_securityagent_snapshot(
                {"processes": [], "windows": [], "windows_available": True}
            )
        processes, windows = parse_securityagent_snapshot(
            {
                "processes": [],
                "processes_available": True,
                "windows": [],
                "windows_available": True,
            }
        )
        self.assertEqual((processes, windows), (frozenset(), frozenset()))

    def test_observer_enumerates_all_system_processes_without_spawning_ps(self):
        observer_source = inspect.getsource(LiveSecurityAgentObserver)
        self.assertIn("proc_listallpids", observer_source)
        self.assertNotIn('"/bin/ps"', observer_source)

    def test_nonempty_securityagent_baseline_is_unclear_before_any_effect(self):
        effects = FakeLiveEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(
                [(frozenset({"process:baseline"}), frozenset())]
            ),
            cleanup_approved=False,
        )
        self.assertEqual(
            (outcome.status, outcome.code),
            ("UNCLEAR", "securityagent_baseline_nonempty"),
        )
        self.assertEqual(effects.calls, [])

    def test_unknown_failure_disposition_preserves_item_and_image_as_unclear(self):
        class SubstitutedEffects(FakeLiveEffects):
            def quarantine_exact_image(self):
                self.calls.append("quarantine-rejected-substitution")
                raise IntegrationWorkflowFailure

        effects = SubstitutedEffects()
        observer = FakeSecurityAgentObserver(
            [
                (frozenset(), frozenset()),
                (frozenset(), frozenset()),
                (frozenset({"process:99"}), frozenset()),
            ]
        )
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=observer,
            cleanup_approved=False,
        )
        self.assertEqual((outcome.status, outcome.code), ("UNCLEAR", "disposition_failed"))
        self.assertTrue(effects.item_present)
        self.assertNotIn("delete-disposable-item", effects.calls)
        self.assertNotIn("delete-image", effects.calls)

    def test_lost_helper_after_mount_effect_never_quarantines_or_deletes(self):
        class LostHelperEffects(FakeLiveEffects):
            def invoke_helper(self, operation, request):
                if operation == "mount":
                    self.calls.append("mount-helper-lost")
                    raise IntegrationWorkflowFailure
                return super().invoke_helper(operation, request)

            def dispose_after_failure(self, *, encryption_uuid, cleanup_approved):
                self.calls.append("preserve-unknown-mapping")
                raise IntegrationWorkflowFailure

        effects = LostHelperEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=True,
        )
        self.assertEqual((outcome.status, outcome.code), ("UNCLEAR", "disposition_failed"))
        self.assertIn("preserve-unknown-mapping", effects.calls)
        self.assertNotIn("quarantine-image", effects.calls)
        self.assertNotIn("delete-disposable-item", effects.calls)
        self.assertNotIn("delete-image", effects.calls)

    def test_pure_live_plan_is_unique_private_and_fixed_to_disposable_contract(self):
        self.assertIn("build_live_plan", globals(), "missing pure live plan builder")
        private_root = Path("/private/tmp/cortex-owned-test-root")
        first = build_live_plan(
            private_root,
            unique="11111111111111111111111111111111",
            transaction_id="12345678-1234-4234-8234-123456789abc",
        )
        second = build_live_plan(
            private_root,
            unique="22222222222222222222222222222222",
            transaction_id="87654321-4321-4321-8321-cba987654321",
        )
        self.assertEqual(first.image_path.parent, private_root)
        self.assertEqual(first.mount_path.parent, private_root)
        self.assertNotEqual(first.image_path, second.image_path)
        self.assertNotEqual(first.mount_path, second.mount_path)
        self.assertEqual(first.size, "64m")
        self.assertEqual(first.volume_name, "CORTEX_BRIDGE_SPIKE")
        self.assertEqual(first.filesystem, "APFS")
        self.assertEqual(first.transaction_id, "12345678-1234-4234-8234-123456789abc")

    def test_pure_hdiutil_parser_requires_one_exact_image_mount_device_mapping(self):
        self.assertIn(
            "parse_hdiutil_mappings", globals(), "missing pure hdiutil plist parser"
        )
        payload = {
            "images": [
                {
                    "image-path": "/private/tmp/expected.sparsebundle",
                    "system-entities": [
                        {
                            "mount-point": "/private/tmp/expected-mount",
                            "dev-entry": "/dev/disk99",
                        }
                    ],
                },
                {
                    "image-path": "/private/tmp/foreign.sparsebundle",
                    "system-entities": [],
                },
            ]
        }
        self.assertEqual(
            parse_hdiutil_mappings(
                payload,
                image_path="/private/tmp/expected.sparsebundle",
                mount_path="/private/tmp/expected-mount",
            ),
            (1, ["/dev/disk99"]),
        )
        self.assertEqual(
            parse_hdiutil_mappings(
                {"images": []},
                image_path="/private/tmp/expected.sparsebundle",
                mount_path="/private/tmp/expected-mount",
            ),
            (0, []),
        )

    def test_exact_triple_gate_selects_live_and_cleanup_remains_separate(self):
        self.assertIn(
            "select_execution_mode", globals(), "missing gated runner selector"
        )
        authorized = {
            "CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION": AUTHORIZATION,
        }
        live = select_execution_mode(
            ["--integration", "--allow-effects"], authorized
        )
        self.assertEqual((live.mode, live.cleanup_approved), ("live", False))
        cleanup = select_execution_mode(
            ["--integration", "--allow-effects", "--cleanup-approved"],
            authorized,
        )
        self.assertEqual((cleanup.mode, cleanup.cleanup_approved), ("live", True))
        default = select_execution_mode([], {})
        self.assertEqual((default.mode, default.cleanup_approved), ("fake", False))

    def test_selected_suite_routes_live_mode_to_real_integration_testcase_only(self):
        self.assertIn(
            "build_selected_suite", globals(), "missing selected-suite router"
        )
        suite = build_selected_suite(unittest.TestLoader(), ExecutionMode("live", False))

        def test_ids(node):
            for child in node:
                if isinstance(child, unittest.TestSuite):
                    yield from test_ids(child)
                else:
                    yield child.id()

        selected = list(test_ids(suite))
        self.assertEqual(len(selected), 1)
        self.assertIn("DiskImageKeychainLiveIntegrationTests", selected[0])

    def test_every_incomplete_gate_combination_is_rejected_before_dispatch(self):
        self.assertIn(
            "dispatch_execution_mode", globals(), "missing pre-effect gate dispatcher"
        )
        invocations = []
        incomplete = (
            (["--integration"], {}),
            (["--allow-effects"], {}),
            (["--integration", "--allow-effects"], {}),
            (["--integration", "--allow-effects", "--cleanup-approved"], {}),
            ([], {"CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION": AUTHORIZATION}),
            (["--cleanup-approved"], {}),
        )
        for arguments, environment in incomplete:
            with self.subTest(arguments=arguments, environment=environment):
                with self.assertRaises(EffectGateRejected):
                    dispatch_execution_mode(
                        arguments,
                        environment,
                        fake_runner=lambda: invocations.append("fake"),
                        live_runner=lambda cleanup: invocations.append("live"),
                    )
        self.assertEqual(invocations, [])

    def test_live_workflow_uses_two_fresh_mount_processes_in_exact_order(self):
        self.assertIn(
            "run_live_integration_workflow", globals(), "missing live orchestrator"
        )
        effects = FakeLiveEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=True,
        )
        self.assertEqual((outcome.status, outcome.code), ("PASS", "integration_verified"))
        self.assertEqual(
            effects.calls,
            [
                "compile-helper",
                "create",
                "mount",
                "verify-mounted",
                "detach",
                "verify-detached",
                "mount",
                "verify-mounted",
                "detach",
                "verify-detached",
                "inspect-item",
                "delete-disposable-item",
                "delete-image",
            ],
        )
        mount_tokens = [
            token
            for operation, token in zip(
                [
                    "create",
                    "mount",
                    "detach",
                    "mount",
                    "detach",
                    "inspect-item",
                    "delete-disposable-item",
                ],
                effects.process_tokens,
            )
            if operation == "mount"
        ]
        self.assertEqual(len(mount_tokens), 2)
        self.assertEqual(len(set(mount_tokens)), 2)

    def test_missing_cleanup_authorization_quarantines_image_and_keeps_item(self):
        self.assertIn(
            "run_live_integration_workflow", globals(), "missing live orchestrator"
        )
        effects = FakeLiveEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=False,
        )
        self.assertEqual((outcome.status, outcome.code), ("UNCLEAR", "cleanup_not_authorized"))
        self.assertTrue(effects.item_present)
        self.assertIn("quarantine-image", effects.calls)
        self.assertNotIn("delete-disposable-item", effects.calls)
        self.assertNotIn("delete-image", effects.calls)
        self.assertEqual(set(outcome.__dict__), {"status", "code"})

    def test_new_securityagent_snapshot_is_terminal_before_mount_and_quarantines(self):
        self.assertIn(
            "run_live_integration_workflow", globals(), "missing live orchestrator"
        )
        effects = FakeLiveEffects()
        observer = FakeSecurityAgentObserver(
            [
                (frozenset(), frozenset()),
                (frozenset(), frozenset()),
                (frozenset({"process:99"}), frozenset({"window:7"})),
            ]
        )
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=observer,
            cleanup_approved=False,
        )
        self.assertEqual((outcome.status, outcome.code), ("FAIL", "securityagent_detected"))
        self.assertEqual(
            effects.calls,
            ["compile-helper", "create", "quarantine-image"],
        )


def parse_securityagent_snapshot(decoded):
    if (
        not isinstance(decoded, dict)
        or decoded.get("processes_available") is not True
        or decoded.get("windows_available") is not True
    ):
        raise ObservationUnavailable
    processes = decoded.get("processes")
    windows = decoded.get("windows")
    if not isinstance(processes, list) or not isinstance(windows, list):
        raise ObservationUnavailable
    if not all(isinstance(value, str) for value in processes + windows):
        raise ObservationUnavailable
    return frozenset(processes), frozenset(windows)


class LiveSecurityAgentObserver:
    """Snapshots SecurityAgent processes/windows without Accessibility APIs."""

    def __init__(self, capability):
        _require_live_capability(capability)
        self.capability = capability
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        source = root / "security_agent_snapshot.swift"
        self.binary = root / "security-agent-snapshot"
        source.write_text(
            r"""
import CoreGraphics
import Darwin
import Foundation

let initialProcessCount = Int(proc_listallpids(nil, 0))
var processIdentifiers = [pid_t](
    repeating: 0,
    count: max(initialProcessCount, 1) + 64
)
let listedProcessCount = processIdentifiers.withUnsafeMutableBytes { storage -> Int32 in
    proc_listallpids(storage.baseAddress, Int32(storage.count))
}
var processIDs = Set<pid_t>()
var processes = [String]()
var processMetadataComplete = true
if listedProcessCount > 0 {
    for processID in processIdentifiers.prefix(Int(listedProcessCount)) where processID > 0 {
        var nameStorage = [CChar](repeating: 0, count: Int(MAXPATHLEN))
        var pathStorage = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
        let nameLength = proc_name(processID, &nameStorage, UInt32(nameStorage.count))
        let pathLength = proc_pidpath(processID, &pathStorage, UInt32(pathStorage.count))
        guard nameLength > 0 || pathLength > 0 else {
            processMetadataComplete = false
            continue
        }
        let name = nameLength > 0 ? String(cString: nameStorage) : ""
        let path = pathLength > 0 ? String(cString: pathStorage) : ""
        let executable = path.split(separator: "/").last.map(String.init) ?? ""
        if name == "SecurityAgent" || executable == "SecurityAgent" {
            processIDs.insert(processID)
            processes.append("process:\(processID):SecurityAgent")
        }
    }
}
processes.sort()
let processesAvailable = initialProcessCount > 0 && listedProcessCount > 0 &&
    Int(listedProcessCount) < processIdentifiers.count && processMetadataComplete

let rawWindows = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID)
let allWindows = rawWindows as? [[String: Any]] ?? []
let windowsAvailable = rawWindows != nil && allWindows.allSatisfy { window in
    window[kCGWindowOwnerName as String] != nil &&
        window[kCGWindowOwnerPID as String] != nil &&
        window[kCGWindowNumber as String] != nil
}
let windows = allWindows.compactMap { window -> String? in
    let ownerName = window[kCGWindowOwnerName as String] as? String ?? ""
    let ownerPID = window[kCGWindowOwnerPID as String] as? pid_t ?? -1
    guard ownerName == "SecurityAgent" || processIDs.contains(ownerPID) else {
        return nil
    }
    let number = window[kCGWindowNumber as String] as? Int ?? -1
    return "window:\(ownerPID):\(number)"
}.sorted()

let output: [String: Any] = [
    "processes": processes,
    "processes_available": processesAvailable,
    "windows": windows,
    "windows_available": windowsAvailable,
]
var data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
data.append(0x0A)
FileHandle.standardOutput.write(data)
""".strip()
            + "\n",
            encoding="utf-8",
        )
        self._run(
            [
                "/usr/bin/xcrun",
                "swiftc",
                str(source),
                "-framework",
                "CoreGraphics",
                "-o",
                str(self.binary),
            ],
            timeout=COMMAND_TIMEOUT_SECONDS,
        )

    def _run(self, argv, *, timeout):
        _require_live_capability(self.capability)
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "LANG": "C",
                    "LC_ALL": "C",
                },
                start_new_session=True,
            )
        except OSError:
            raise IntegrationWorkflowFailure from None
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=1)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=1)
            raise IntegrationWorkflowFailure from None
        if process.returncode != 0 or len(stdout) > 1_048_576 or len(stderr) > 1_048_576:
            raise IntegrationWorkflowFailure
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return stdout
        try:
            os.killpg(process.pid, signal.SIGTERM)
            time.sleep(0.1)
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise IntegrationWorkflowFailure

    def snapshot(self):
        _require_live_capability(self.capability)
        payload = self._run([str(self.binary)], timeout=10)
        try:
            return parse_securityagent_snapshot(json.loads(payload))
        except (KeyError, TypeError, ValueError):
            raise ObservationUnavailable from None


def _recursive_plist_value(value, accepted_keys):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("_", "-")
            if normalized in accepted_keys:
                return child
        for child in value.values():
            found = _recursive_plist_value(child, accepted_keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _recursive_plist_value(child, accepted_keys)
            if found is not None:
                return found
    return None


def parse_hdiutil_mappings(payload, *, image_path, mount_path):
    images = payload.get("images")
    if not isinstance(images, list):
        raise IntegrationWorkflowFailure
    matching_images = []
    devices = []
    for image in images:
        if not isinstance(image, dict):
            raise IntegrationWorkflowFailure
        candidate = image.get("image-path", image.get("image_path"))
        if candidate != image_path:
            continue
        matching_images.append(image)
        entities = image.get("system-entities", image.get("system_entities", []))
        if not isinstance(entities, list):
            raise IntegrationWorkflowFailure
        for entity in entities:
            if not isinstance(entity, dict):
                raise IntegrationWorkflowFailure
            mount = entity.get("mount-point", entity.get("mount_point"))
            device = entity.get("dev-entry", entity.get("dev_entry"))
            if mount == mount_path and isinstance(device, str):
                devices.append(device)
    return len(matching_images), devices


class LiveIntegrationEffects:
    """Effectful adapter reachable only through the exact action-time gates."""

    def __init__(self, capability):
        _require_live_capability(capability)
        self.capability = capability
        self.observer = None
        self.observer_baseline = None
        self.private_root = Path(tempfile.mkdtemp(prefix="cortex-keychain-integration-"))
        os.chmod(self.private_root, 0o700)
        root_facts = os.stat(self.private_root, follow_symlinks=False)
        if root_facts.st_uid != os.getuid() or stat.S_IMODE(root_facts.st_mode) != 0o700:
            raise IntegrationWorkflowFailure
        self.root_fd = os.open(
            self.private_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        self.plan = build_live_plan(
            self.private_root,
            unique=uuid.uuid4().hex,
            transaction_id=str(uuid.uuid4()),
        )
        self.image_path = self.plan.image_path
        self.mount_path = self.plan.mount_path
        self.mount_path.mkdir(mode=0o700)
        os.chmod(self.mount_path, 0o700)
        self.quarantine_path = self.plan.quarantine_path
        self.transaction_id = self.plan.transaction_id
        self.helper = self.private_root / "disk-image-keychain"
        self.image_identity = None
        self.image_fd = None
        self.image_name = self.image_path.name
        self.image_quarantined = False
        self.preserve_image_and_item = False
        self.encryption_uuid = None
        self.mounted_device = None
        self.invocation_counter = 0

    def __del__(self):
        for descriptor_name in ("image_fd", "root_fd"):
            descriptor = getattr(self, descriptor_name, None)
            if isinstance(descriptor, int) and descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, descriptor_name, -1)

    def _require_capability(self):
        _require_live_capability(self.capability)

    def bind_observer(self, observer, baseline):
        self._require_capability()
        self.observer = observer
        self.observer_baseline = baseline

    @staticmethod
    def _environment():
        return {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        }

    def _observe_bound(self):
        self._require_capability()
        if self.observer is None or self.observer_baseline is None:
            return
        processes, windows = self.observer.snapshot()
        baseline_processes, baseline_windows = self.observer_baseline
        if processes - baseline_processes or windows - baseline_windows:
            raise SecurityAgentDetected

    def _kill_process_group(self, process):
        self._require_capability()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                raise IntegrationWorkflowFailure from None
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        raise IntegrationWorkflowFailure

    def _run(
        self,
        argv,
        *,
        input_text=None,
        timeout=COMMAND_TIMEOUT_SECONDS,
        accepted_returncodes=(0,),
    ):
        self._require_capability()
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._environment(),
                start_new_session=True,
            )
        except OSError:
            raise IntegrationWorkflowFailure from None
        deadline = time.monotonic() + timeout
        first_communication = True
        stdout = stderr = ""
        try:
            while True:
                self._observe_bound()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    stdout, stderr = process.communicate(
                        input=input_text if first_communication else None,
                        timeout=min(0.10, remaining),
                    )
                    break
                except subprocess.TimeoutExpired as timeout_error:
                    first_communication = False
                    partial_stdout = timeout_error.output or ""
                    partial_stderr = timeout_error.stderr or ""
                    if isinstance(partial_stdout, bytes):
                        partial_stdout = partial_stdout.decode("utf-8", "replace")
                    if isinstance(partial_stderr, bytes):
                        partial_stderr = partial_stderr.decode("utf-8", "replace")
                    if len(partial_stdout) > 1_048_576 or len(partial_stderr) > 1_048_576:
                        raise IntegrationWorkflowFailure
            self._observe_bound()
        except (SecurityAgentDetected, ObservationUnavailable):
            self._kill_process_group(process)
            raise
        except Exception:
            self._kill_process_group(process)
            raise IntegrationWorkflowFailure from None
        if len(stdout) > 1_048_576 or len(stderr) > 1_048_576:
            raise IntegrationWorkflowFailure
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            self._kill_process_group(process)
            raise IntegrationWorkflowFailure
        if process.returncode not in accepted_returncodes:
            raise IntegrationWorkflowFailure
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)

    def compile_production_helper(self):
        self._require_capability()
        self._run(
            [
                "/usr/bin/xcrun",
                "swiftc",
                str(SOURCE),
                "-framework",
                "Security",
                "-o",
                str(self.helper),
            ]
        )
        os.chmod(self.helper, 0o700)

    def create_request(self):
        self._require_capability()
        return {
            "schema_version": 1,
            "operation": "create",
            "image_path": str(self.image_path),
            "mount_path": str(self.mount_path),
            "volume_name": self.plan.volume_name,
            "size": self.plan.size,
            "transaction_id": self.transaction_id,
            "expected_encryption_uuid": None,
            "disposable": True,
            "cleanup_approved": False,
        }

    def request(self, operation, encryption_uuid, cleanup_approved=False):
        self._require_capability()
        if cleanup_approved and not self.capability.cleanup_approved:
            raise LiveCapabilityRequired
        return {
            "schema_version": 1,
            "operation": operation,
            "image_path": str(self.image_path),
            "mount_path": str(self.mount_path),
            "volume_name": self.plan.volume_name,
            "size": self.plan.size,
            "transaction_id": self.transaction_id,
            "expected_encryption_uuid": encryption_uuid,
            "disposable": True,
            "cleanup_approved": cleanup_approved,
        }

    def _capture_image_identity(self):
        self._require_capability()
        try:
            descriptor = os.open(
                self.image_name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=self.root_fd,
            )
        except FileNotFoundError:
            return
        facts = os.fstat(descriptor)
        if stat.S_ISLNK(facts.st_mode) or not stat.S_ISDIR(facts.st_mode):
            os.close(descriptor)
            raise IntegrationWorkflowFailure
        if self.image_fd is not None and self.image_fd >= 0:
            os.close(self.image_fd)
        self.image_fd = descriptor
        self.image_identity = (facts.st_dev, facts.st_ino)

    def _require_exact_image(self):
        self._require_capability()
        if self.image_identity is None or self.image_fd is None or self.image_fd < 0:
            raise IntegrationWorkflowFailure
        descriptor_facts = os.fstat(self.image_fd)
        entry_facts = os.stat(
            self.image_name,
            dir_fd=self.root_fd,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(entry_facts.st_mode) or not stat.S_ISDIR(entry_facts.st_mode):
            raise IntegrationWorkflowFailure
        identity = (descriptor_facts.st_dev, descriptor_facts.st_ino)
        entry_identity = (entry_facts.st_dev, entry_facts.st_ino)
        if identity != self.image_identity or entry_identity != self.image_identity:
            raise IntegrationWorkflowFailure

    def _image_entry_present(self):
        self._require_capability()
        try:
            os.stat(self.image_name, dir_fd=self.root_fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def _require_reconciled_unmounted(self):
        self._require_capability()
        if self.preserve_image_and_item or self.mounted_device is not None:
            raise IntegrationWorkflowFailure
        info = self._plist_command(["/usr/bin/hdiutil", "info", "-plist"])
        image_count, devices = parse_hdiutil_mappings(
            info,
            image_path=str(self.image_path),
            mount_path=str(self.mount_path),
        )
        if image_count != 0 or devices:
            raise IntegrationWorkflowFailure

    def invoke_helper(self, operation, request):
        self._require_capability()
        if operation == "delete-disposable-item" and not self.capability.cleanup_approved:
            raise LiveCapabilityRequired
        self.invocation_counter += 1
        try:
            completed = self._run(
                [str(self.helper)],
                input_text=json.dumps(request, separators=(",", ":")) + "\n",
                accepted_returncodes=(0, 64, 70),
            )
        except Exception:
            if operation == "create":
                self._capture_image_identity()
            if operation in {"create", "mount"}:
                self.preserve_image_and_item = True
            raise
        if completed.stderr or completed.stdout.count("\n") != 1:
            raise IntegrationWorkflowFailure
        try:
            response = json.loads(completed.stdout)
        except (TypeError, ValueError):
            raise IntegrationWorkflowFailure from None
        serialized = json.dumps(response, separators=(",", ":"))
        if str(self.image_path) in serialized or str(self.mount_path) in serialized:
            raise IntegrationWorkflowFailure
        if completed.returncode != 0 or response.get("code") != "OK":
            if response.get("code") == "MOUNT_CLEANUP_UNCLEAR" or operation in {"create", "mount"}:
                self.preserve_image_and_item = True
            raise IntegrationWorkflowFailure
        if operation == "create":
            self._capture_image_identity()
            self.encryption_uuid = response.get("encryption_uuid")
        elif operation == "mount":
            self.mounted_device = response.get("device")
        elif operation == "detach":
            self.mounted_device = None
        return response, f"fresh-helper-{self.invocation_counter}"

    def _plist_command(self, argv):
        self._require_capability()
        completed = self._run(argv)
        try:
            return plistlib.loads(completed.stdout.encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            raise IntegrationWorkflowFailure from None

    def _verify_encryption_uuid(self, expected_uuid):
        self._require_capability()
        encrypted = self._plist_command(
            ["/usr/bin/hdiutil", "isencrypted", "-plist", str(self.image_path)]
        )
        actual = _recursive_plist_value(
            encrypted,
            {"encryption-uuid", "image-encryption-uuid"},
        )
        if actual != expected_uuid:
            raise IntegrationWorkflowFailure

    def verify_mounted(self, expected_uuid, expected_device):
        self._require_capability()
        self._verify_encryption_uuid(expected_uuid)
        disk = self._plist_command(
            ["/usr/sbin/diskutil", "info", "-plist", expected_device]
        )
        mount = disk.get("MountPoint")
        filesystem = str(disk.get("FilesystemType", "")).lower()
        device_node = disk.get("DeviceNode")
        if mount != str(self.mount_path) or filesystem != "apfs":
            raise IntegrationWorkflowFailure
        if device_node is not None and device_node != expected_device:
            raise IntegrationWorkflowFailure
        info = self._plist_command(["/usr/bin/hdiutil", "info", "-plist"])
        image_count, devices = parse_hdiutil_mappings(
            info,
            image_path=str(self.image_path),
            mount_path=str(self.mount_path),
        )
        if image_count != 1 or devices != [expected_device]:
            raise IntegrationWorkflowFailure

    def verify_detached(self, expected_device):
        self._require_capability()
        info = self._plist_command(["/usr/bin/hdiutil", "info", "-plist"])
        image_count, devices = parse_hdiutil_mappings(
            info,
            image_path=str(self.image_path),
            mount_path=str(self.mount_path),
        )
        if image_count != 0 or devices:
            raise IntegrationWorkflowFailure
        if any(self.mount_path.iterdir()):
            raise IntegrationWorkflowFailure

    def delete_exact_image(self):
        self._require_capability()
        if not self.capability.cleanup_approved:
            raise LiveCapabilityRequired
        self._require_reconciled_unmounted()
        if not self.image_quarantined:
            self.quarantine_exact_image()
        if not shutil.rmtree.avoids_symlink_attacks:
            raise IntegrationWorkflowFailure
        self._require_exact_image()
        shutil.rmtree(self.image_name, dir_fd=self.root_fd)
        if self._image_entry_present():
            raise IntegrationWorkflowFailure

    def quarantine_exact_image(self):
        self._require_capability()
        self._require_reconciled_unmounted()
        self._require_exact_image()
        try:
            os.stat(
                self.quarantine_path.name,
                dir_fd=self.root_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise IntegrationWorkflowFailure
        libc = ctypes.CDLL(None, use_errno=True)
        rename_exclusive = libc.renameatx_np
        rename_exclusive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_exclusive.restype = ctypes.c_int
        result = rename_exclusive(
            self.root_fd,
            os.fsencode(self.image_name),
            self.root_fd,
            os.fsencode(self.quarantine_path.name),
            0x00000004,
        )
        if result != 0:
            raise IntegrationWorkflowFailure
        moved = os.stat(
            self.quarantine_path.name,
            dir_fd=self.root_fd,
            follow_symlinks=False,
        )
        if (moved.st_dev, moved.st_ino) != self.image_identity:
            raise IntegrationWorkflowFailure
        try:
            os.stat(self.image_name, dir_fd=self.root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise IntegrationWorkflowFailure
        self.image_name = self.quarantine_path.name
        self.image_quarantined = True

    def dispose_after_failure(self, *, encryption_uuid, cleanup_approved):
        self._require_capability()
        if cleanup_approved and not self.capability.cleanup_approved:
            raise LiveCapabilityRequired
        if self.preserve_image_and_item:
            raise IntegrationWorkflowFailure
        if self.mounted_device is not None and encryption_uuid:
            mounted_device = self.mounted_device
            response, _ = self.invoke_helper(
                "detach", self.request("detach", encryption_uuid)
            )
            _require_response(
                response,
                "detach",
                uuid_value=encryption_uuid,
                device=mounted_device,
            )
        if not self._image_entry_present():
            return
        if not cleanup_approved:
            self.quarantine_exact_image()
            return
        if not encryption_uuid:
            self.quarantine_exact_image()
            raise IntegrationWorkflowFailure
        inspected, _ = self.invoke_helper(
            "inspect-item", self.request("inspect-item", encryption_uuid)
        )
        _require_response(
            inspected,
            "inspect-item",
            uuid_value=encryption_uuid,
            item_count=1,
        )
        deleted, _ = self.invoke_helper(
            "delete-disposable-item",
            self.request(
                "delete-disposable-item",
                encryption_uuid,
                cleanup_approved=True,
            ),
        )
        _require_response(
            deleted,
            "delete-disposable-item",
            uuid_value=encryption_uuid,
            item_count=0,
        )
        self.delete_exact_image()


class DiskImageKeychainLiveIntegrationTests(unittest.TestCase):
    def test_disposable_keychain_image_lifecycle(self):
        try:
            _require_live_capability(LIVE_CAPABILITY)
        except LiveCapabilityRequired:
            self.fail("FAIL live_capability_required")
            return
        try:
            observer = LiveSecurityAgentObserver(LIVE_CAPABILITY)
            effects = LiveIntegrationEffects(LIVE_CAPABILITY)
            outcome = run_live_integration_workflow(
                effects=effects,
                observer=observer,
                cleanup_approved=LIVE_CAPABILITY.cleanup_approved,
            )
        except Exception:
            self.fail("FAIL integration_harness_unavailable")
        if outcome.status == "UNCLEAR":
            self.fail(f"UNCLEAR {outcome.code}")
        self.assertEqual(
            (outcome.status, outcome.code),
            ("PASS", "integration_verified"),
        )


def build_selected_suite(loader, selection):
    if selection.mode == "live":
        return loader.loadTestsFromTestCase(DiskImageKeychainLiveIntegrationTests)
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(DiskImageKeychainHelperTests))
    suite.addTests(
        loader.loadTestsFromTestCase(DiskImageKeychainIntegrationOrchestrationTests)
    )
    return suite


def load_tests(loader, tests, pattern):
    return build_selected_suite(loader, EXECUTION_MODE)


if __name__ == "__main__":
    unittest.main()
