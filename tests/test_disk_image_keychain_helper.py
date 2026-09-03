#!/usr/bin/env python3
"""Pure contract tests for the macOS disk-image/Keychain helper.

The default runner compiles only the fake-adapter harness. Real Keychain and
DiskImages effects are unreachable unless both explicit integration gates are
present; the focused suite below never supplies the authorization environment.
"""

import ast
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
HELPER_OUTER_TIMEOUT_SECONDS = 55
HELPER_TIMEOUT_MARGIN_SECONDS = 2
HELPER_PRE_MONITOR_CAP_SECONDS = 1
HELPER_POST_MONITOR_CAP_SECONDS = 1
PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS = 6
SWIFT_FINAL_REQUEST_BUDGET_SECONDS = 40
PROCESS_TREE_SCAN_TIMEOUT_SECONDS = 2
PROCESS_TERMINATION_GRACE_SECONDS = 1


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


@dataclass(frozen=True)
class HelperDeadlinePlan:
    execution_deadline: float
    post_monitor_deadline: float
    cleanup_deadline: float
    hard_deadline: float


def _helper_deadline_plan(start):
    hard_deadline = start + HELPER_OUTER_TIMEOUT_SECONDS
    cleanup_deadline = hard_deadline - HELPER_TIMEOUT_MARGIN_SECONDS
    post_monitor_deadline = (
        cleanup_deadline - PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS
    )
    execution_deadline = post_monitor_deadline - HELPER_POST_MONITOR_CAP_SECONDS
    return HelperDeadlinePlan(
        execution_deadline=execution_deadline,
        post_monitor_deadline=post_monitor_deadline,
        cleanup_deadline=cleanup_deadline,
        hard_deadline=hard_deadline,
    )


def _process_deadline_plan(start, timeout):
    if timeout == HELPER_OUTER_TIMEOUT_SECONDS:
        return _helper_deadline_plan(start)
    hard_deadline = start + timeout
    margin = min(HELPER_TIMEOUT_MARGIN_SECONDS, max(0.01, timeout * 0.01))
    cleanup_budget = min(
        PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS,
        max(0.05, timeout * 0.08),
    )
    post_budget = min(
        HELPER_POST_MONITOR_CAP_SECONDS,
        max(0.01, timeout * 0.02),
    )
    cleanup_deadline = hard_deadline - margin
    post_monitor_deadline = cleanup_deadline - cleanup_budget
    execution_deadline = post_monitor_deadline - post_budget
    if execution_deadline <= start:
        raise IntegrationWorkflowFailure
    return HelperDeadlinePlan(
        execution_deadline=execution_deadline,
        post_monitor_deadline=post_monitor_deadline,
        cleanup_deadline=cleanup_deadline,
        hard_deadline=hard_deadline,
    )


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    ppid: int
    pgid: int
    start_seconds: int
    start_microseconds: int

    @property
    def stable_key(self):
        return self.pid, self.start_seconds, self.start_microseconds


class _ProcBSDInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32), ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32), ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32), ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32), ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32), ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32), ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32), ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


def _bounded_timeout(deadline, cap):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise IntegrationWorkflowFailure
    return min(cap, remaining)


def _process_table(timeout=PROCESS_TREE_SCAN_TIMEOUT_SECONDS):
    if timeout <= 0:
        raise IntegrationWorkflowFailure
    started = time.monotonic()
    libc = ctypes.CDLL(None, use_errno=True)
    list_all = libc.proc_listallpids
    list_all.argtypes = [ctypes.c_void_p, ctypes.c_int]
    list_all.restype = ctypes.c_int
    pid_info = libc.proc_pidinfo
    pid_info.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int,
    ]
    pid_info.restype = ctypes.c_int
    capacity = max(list_all(None, 0), 1) + 64
    storage = (ctypes.c_int * capacity)()
    count = list_all(storage, ctypes.sizeof(storage))
    if count <= 0 or count >= capacity:
        raise IntegrationWorkflowFailure
    rows = []
    for pid in storage[:count]:
        if pid <= 0:
            continue
        info = _ProcBSDInfo()
        copied = pid_info(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if copied != ctypes.sizeof(info):
            continue
        rows.append(ProcessIdentity(
            int(info.pbi_pid), int(info.pbi_ppid), int(info.pbi_pgid),
            int(info.pbi_start_tvsec), int(info.pbi_start_tvusec),
        ))
    if time.monotonic() - started > timeout:
        raise IntegrationWorkflowFailure
    return tuple(rows)


class ProcessTreeTracker:
    def __init__(self, root_identity):
        self.root_identity = root_identity
        self.owned_group = root_identity.pgid
        self.tracked = {root_identity.stable_key: root_identity}
        self.current = {root_identity.stable_key: root_identity}
        self.adoption_open = True
        self.scan_complete = True
        self.identity_reused = False

    @property
    def tracked_identities(self):
        return frozenset(self.tracked)

    def mark_scan_unavailable(self):
        self.scan_complete = False
        self.adoption_open = False

    def observe(self, rows):
        rows = tuple(rows)
        snapshot = {row.stable_key: row for row in rows}
        root_current = snapshot.get(self.root_identity.stable_key)
        if (
            root_current is None
            or root_current.pgid != self.root_identity.pgid
        ):
            self.adoption_open = False
        tracked_pids = {identity.pid for identity in self.tracked.values()}
        if any(
            row.pid in tracked_pids
            and (
                row.stable_key not in self.tracked
                or row.pgid != self.tracked[row.stable_key].pgid
            )
            for row in rows
        ):
            self.identity_reused = True

        active = {
            key: snapshot[key]
            for key, tracked in self.tracked.items()
            if key in snapshot and snapshot[key].pgid == tracked.pgid
        }
        if self.adoption_open:
            active_parent_pids = {identity.pid for identity in active.values()}
            changed = True
            while changed:
                changed = False
                for identity in rows:
                    if (
                        identity.ppid in active_parent_pids
                        and identity.stable_key not in self.tracked
                        and identity.pid not in tracked_pids
                    ):
                        self.tracked[identity.stable_key] = identity
                        active[identity.stable_key] = identity
                        active_parent_pids.add(identity.pid)
                        tracked_pids.add(identity.pid)
                        changed = True
        tracked_groups = {identity.pgid for identity in self.tracked.values()}
        active_groups = {identity.pgid for identity in active.values()}
        if any(
            row.pgid in tracked_groups and row.pgid not in active_groups
            for row in rows
        ):
            self.identity_reused = True
        self.current = active

    def signalable_descendant_groups(self):
        groups = set()
        for key, tracked in self.tracked.items():
            if key == self.root_identity.stable_key:
                continue
            current = self.current.get(key)
            if current is not None and current.pgid == tracked.pgid and current.pgid > 1:
                groups.add(current.pgid)
        return groups

    def signalable_groups(self):
        return {
            identity.pgid
            for identity in self.current.values()
            if identity.pgid > 1
        }

    def cleanup_verified(self):
        return (
            self.scan_complete
            and not self.current
            and not self.identity_reused
        )


@dataclass(frozen=True)
class ObservedProcessResult:
    completed: subprocess.CompletedProcess
    observation_error: Exception | None
    supervision_error: Exception | None = None


def _root_process_tracker(pid, deadline):
    rows = _process_table(_bounded_timeout(deadline, PROCESS_TREE_SCAN_TIMEOUT_SECONDS))
    roots = [row for row in rows if row.pid == pid]
    if len(roots) != 1:
        raise IntegrationWorkflowFailure
    tracker = ProcessTreeTracker(roots[0])
    tracker.observe(rows)
    return tracker


def _refresh_process_tracker(tracker, deadline):
    try:
        rows = _process_table(_bounded_timeout(deadline, PROCESS_TREE_SCAN_TIMEOUT_SECONDS))
        tracker.observe(rows)
    except IntegrationWorkflowFailure:
        tracker.mark_scan_unavailable()
        raise


def _descendant_process_groups(root_pid, *, deadline):
    rows = _process_table(
        _bounded_timeout(deadline, PROCESS_TREE_SCAN_TIMEOUT_SECONDS)
    )
    roots = [row for row in rows if row.pid == root_pid]
    if len(roots) != 1:
        return set()
    tracker = ProcessTreeTracker(roots[0])
    tracker.observe(rows)
    return tracker.signalable_descendant_groups() | {tracker.owned_group}


def _process_group_exists(pgid, *, deadline):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        try:
            return any(
                identity.pgid == pgid
                for identity in _process_table(
                    _bounded_timeout(deadline, PROCESS_TREE_SCAN_TIMEOUT_SECONDS)
                )
            )
        except IntegrationWorkflowFailure:
            return True
    return True


def _close_process_pipes(process):
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(process, stream_name, None)
        if stream is not None and not stream.closed:
            stream.close()


def _terminate_process_tree(process, tracker, *, deadline):
    if not isinstance(tracker, ProcessTreeTracker):
        return False

    def refresh():
        try:
            rows = _process_table(
                _bounded_timeout(deadline, PROCESS_TREE_SCAN_TIMEOUT_SECONDS)
            )
            tracker.observe(rows)
            return True
        except IntegrationWorkflowFailure:
            tracker.mark_scan_unavailable()
            return False

    def signal_current_groups(signal_number):
        signal_ok = True
        for pgid in sorted(tracker.signalable_groups(), reverse=True):
            if not refresh() or pgid not in tracker.signalable_groups():
                return False
            try:
                os.killpg(pgid, signal_number)
            except ProcessLookupError:
                continue
            except PermissionError:
                signal_ok = False
        return signal_ok

    def verified_absent():
        return process.poll() is not None and tracker.cleanup_verified()

    if not refresh():
        return False
    if verified_absent():
        return True
    if not tracker.signalable_groups():
        return False
    if not signal_current_groups(signal.SIGTERM):
        return False

    remaining = deadline - time.monotonic()
    term_deadline = min(
        deadline,
        time.monotonic()
        + min(PROCESS_TERMINATION_GRACE_SECONDS, max(0.0, remaining / 3)),
    )
    while time.monotonic() < term_deadline:
        if not refresh():
            return False
        if verified_absent():
            return True
        time.sleep(min(0.02, max(0.0, term_deadline - time.monotonic())))

    if not refresh():
        return False
    if verified_absent():
        return True
    if not signal_current_groups(signal.SIGKILL):
        return False
    if process.poll() is None:
        try:
            process.wait(
                timeout=_bounded_timeout(deadline, PROCESS_TERMINATION_GRACE_SECONDS)
            )
        except (subprocess.TimeoutExpired, IntegrationWorkflowFailure):
            return False

    while time.monotonic() < deadline:
        if not refresh():
            return False
        if verified_absent():
            return True
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
    return False


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
        baseline_processes, baseline_windows = observer.snapshot(
            timeout=HELPER_PRE_MONITOR_CAP_SECONDS
        )
    except Exception:
        return IntegrationOutcome("UNCLEAR", "observer_unavailable")
    if baseline_processes or baseline_windows:
        return IntegrationOutcome("UNCLEAR", "securityagent_baseline_nonempty")
    if hasattr(effects, "bind_observer"):
        effects.bind_observer(observer, (baseline_processes, baseline_windows))
    encryption_uuid = None

    def latch_observation(error):
        if hasattr(effects, "_latch_terminal_observation"):
            effects._latch_terminal_observation(error)

    def reject_new_securityagent():
        try:
            processes, windows = observer.snapshot(
                timeout=HELPER_POST_MONITOR_CAP_SECONDS
            )
        except Exception:
            error = ObservationUnavailable()
            latch_observation(error)
            raise error from None
        if processes - baseline_processes or windows - baseline_windows:
            error = SecurityAgentDetected()
            latch_observation(error)
            raise error

    def dispose(outcome):
        disposition_failed = False
        try:
            effects.dispose_after_failure(
                encryption_uuid=encryption_uuid,
                cleanup_approved=cleanup_approved,
            )
        except Exception:
            disposition_failed = True
        terminal_observation = getattr(
            effects, "terminal_observation_error", None
        )
        if (
            outcome.code == "securityagent_detected"
            or isinstance(terminal_observation, SecurityAgentDetected)
        ):
            return IntegrationOutcome("FAIL", "securityagent_detected")
        if (
            outcome.code == "observer_unavailable"
            or isinstance(terminal_observation, ObservationUnavailable)
        ):
            return IntegrationOutcome("UNCLEAR", "observer_unavailable")
        if disposition_failed:
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
    except ObservationUnavailable:
        return dispose(IntegrationOutcome("UNCLEAR", "observer_unavailable"))
    except Exception:
        terminal_observation = getattr(
            effects, "terminal_observation_error", None
        )
        if isinstance(terminal_observation, SecurityAgentDetected):
            return dispose(IntegrationOutcome("FAIL", "securityagent_detected"))
        if isinstance(terminal_observation, ObservationUnavailable):
            return dispose(IntegrationOutcome("UNCLEAR", "observer_unavailable"))
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

    def test_mount_rejects_invalid_keychain_secret_before_any_hdiutil_call(self):
        scenarios = (
            "secret-length-42",
            "secret-length-44",
            "secret-nul",
            "secret-plus",
            "secret-slash",
            "secret-padding",
            "secret-non-ascii",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                completed, observation = self.run_helper("mount", scenario=scenario)
                self.assertEqual(completed.returncode, 70)
                self.assertEqual(
                    observation["response"]["code"], "KEYCHAIN_SECRET_INVALID"
                )
                self.assertEqual(observation["hdiutil_calls"], [])
                self.assertTrue(observation["all_buffers_zeroed"])

        completed, observation = self.run_helper("mount", scenario="success")
        self.assertEqual(completed.returncode, 0)
        attach = [
            call for call in observation["hdiutil_calls"]
            if call["argv"][1] == "attach"
        ]
        self.assertEqual(len(attach), 1)
        self.assertEqual(attach[0]["secret_payload_count"], 43)

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

    def test_rejects_duplicate_top_level_keys_including_escaped_equivalents(self):
        valid = json.dumps(self.request("create", expected_encryption_uuid=None))
        for duplicate in ('"size":"64m"', '"si\\u007ae":"64m"'):
            with self.subTest(duplicate=duplicate):
                payload = valid[:-1] + "," + duplicate + "}\n"
                completed = subprocess.run(
                    [str(self.binary), "--test-scenario", "success"],
                    input=payload,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                )
                self.assertEqual(completed.returncode, 64)
                self.assertEqual(completed.stdout, "")

    def test_swift_internal_timeout_composes_below_live_helper_timeout(self):
        self.assertIn("HELPER_OUTER_TIMEOUT_SECONDS", globals())
        self.assertIn("HELPER_TIMEOUT_MARGIN_SECONDS", globals())
        completed = subprocess.run(
            [str(self.binary), "--process-policy"],
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        policy = json.loads(completed.stdout)
        self.assertEqual(
            policy["request_deadline_seconds"],
            SWIFT_FINAL_REQUEST_BUDGET_SECONDS,
        )
        internal_total = sum(
            policy[key]
            for key in (
                "request_deadline_seconds",
                "term_grace_seconds",
                "reap_grace_seconds",
                "group_grace_seconds",
            )
        )
        self.assertLess(
            internal_total + HELPER_TIMEOUT_MARGIN_SECONDS,
            HELPER_OUTER_TIMEOUT_SECONDS,
        )

    def test_sequential_hdiutil_calls_share_one_request_deadline(self):
        completed, observation = self.run_helper(
            "create", scenario="slow-series", expected_encryption_uuid=None
        )
        self.assertEqual(completed.returncode, 0)
        calls = observation["hdiutil_calls"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(len({call["absolute_deadline"] for call in calls}), 1)
        self.assertGreater(
            calls[0]["remaining_budget_before"],
            calls[1]["remaining_budget_before"],
        )

    def test_mount_reserves_final_deadline_window_for_exact_compensation(self):
        completed, observation = self.run_helper(
            "mount", scenario="deadline-compensation"
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "HDIUTIL_FAILED")
        calls = observation["hdiutil_calls"]
        normal_deadline = calls[0]["absolute_deadline"]
        compensation_calls = [
            call for call in calls if call.get("deadline_phase") == "compensation"
        ]
        self.assertTrue(compensation_calls)
        compensation_deadline = compensation_calls[0]["absolute_deadline"]
        self.assertGreater(compensation_deadline, normal_deadline)
        self.assertTrue(
            all(call["absolute_deadline"] == compensation_deadline for call in compensation_calls)
        )
        detach = [
            call for call in compensation_calls if call["argv"][1] == "detach"
        ]
        self.assertEqual(len(detach), 1)
        self.assertGreater(detach[0]["remaining_budget_before"], 0)

    def test_child_hard_deadline_contains_full_termination_budget(self):
        completed, observation = self.run_helper(
            "mount", scenario="hard-deadline-compensation"
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(observation["response"]["code"], "HDIUTIL_FAILED")
        timed_out = next(
            call
            for call in observation["hdiutil_calls"]
            if call["argv"][1] == "isencrypted"
        )
        self.assertTrue(timed_out["spawned"])
        self.assertEqual(
            timed_out["hard_deadline"] - timed_out["work_deadline"],
            timed_out["termination_budget"],
        )
        self.assertEqual(
            timed_out["termination_started_at"], timed_out["work_deadline"]
        )
        self.assertEqual(timed_out["finished_at"], timed_out["hard_deadline"])

    def test_late_normal_child_leaves_complete_compensation_window(self):
        completed, observation = self.run_helper(
            "mount", scenario="hard-deadline-compensation"
        )
        self.assertEqual(completed.returncode, 70)
        calls = observation["hdiutil_calls"]
        normal = [call for call in calls if call["deadline_phase"] == "normal"]
        compensation = [
            call for call in calls if call["deadline_phase"] == "compensation"
        ]
        self.assertTrue(normal)
        self.assertEqual(compensation[0]["argv"][1], "detach")
        normal_hard_deadline = normal[0]["hard_deadline"]
        final_deadline = compensation[0]["hard_deadline"]
        self.assertEqual(
            final_deadline - normal_hard_deadline,
            observation["mount_compensation_budget"],
        )
        self.assertEqual(compensation[0]["started_at"], normal_hard_deadline)
        self.assertTrue(all(call["hard_deadline"] == normal_hard_deadline for call in normal))
        self.assertTrue(all(call["hard_deadline"] == final_deadline for call in compensation))
        self.assertLessEqual(compensation[-1]["finished_at"], final_deadline)

    def test_required_compensation_child_is_not_spawned_without_cleanup_time(self):
        completed, observation = self.run_helper(
            "mount", scenario="compensation-window-exhausted"
        )
        self.assertEqual(completed.returncode, 70)
        self.assertEqual(
            observation["response"]["code"], "MOUNT_CLEANUP_UNCLEAR"
        )
        compensation = [
            call
            for call in observation["hdiutil_calls"]
            if call["deadline_phase"] == "compensation"
        ]
        self.assertEqual(
            [call["argv"][1] for call in compensation],
            ["detach", "info"],
        )
        self.assertTrue(compensation[0]["spawned"])
        self.assertFalse(compensation[1]["spawned"])
        self.assertEqual(
            compensation[1]["started_at"], compensation[1]["work_deadline"]
        )

    def test_python_outer_deadline_covers_both_monitors_swift_and_cleanup(self):
        required_names = (
            "HELPER_PRE_MONITOR_CAP_SECONDS",
            "HELPER_POST_MONITOR_CAP_SECONDS",
            "PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS",
            "SWIFT_FINAL_REQUEST_BUDGET_SECONDS",
        )
        for name in required_names:
            self.assertIn(name, globals())
        covered = (
            globals()["HELPER_PRE_MONITOR_CAP_SECONDS"]
            + globals()["SWIFT_FINAL_REQUEST_BUDGET_SECONDS"]
            + globals()["HELPER_POST_MONITOR_CAP_SECONDS"]
            + globals()["PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS"]
            + HELPER_TIMEOUT_MARGIN_SECONDS
        )
        self.assertLess(covered, HELPER_OUTER_TIMEOUT_SECONDS)
        plan = _helper_deadline_plan(100.0)
        self.assertEqual(plan.hard_deadline, 100.0 + HELPER_OUTER_TIMEOUT_SECONDS)
        self.assertGreaterEqual(
            plan.execution_deadline - 100.0,
            HELPER_PRE_MONITOR_CAP_SECONDS + SWIFT_FINAL_REQUEST_BUDGET_SECONDS,
        )
        self.assertEqual(
            plan.cleanup_deadline - plan.post_monitor_deadline,
            PYTHON_PROCESS_TERMINATION_BUDGET_SECONDS,
        )
        self.assertEqual(
            plan.hard_deadline - plan.cleanup_deadline,
            HELPER_TIMEOUT_MARGIN_SECONDS,
        )

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

    def snapshot(self, timeout=None):
        snapshot = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return snapshot


class DiskImageKeychainIntegrationOrchestrationTests(unittest.TestCase):
    @staticmethod
    def _harmless_process_tree_command(record_path, mode):
        child_source = (
            "import signal,time;"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "time.sleep(30)"
        )
        parent_source = """
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen(
    [sys.executable, "-c", sys.argv[3]],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
record = pathlib.Path(sys.argv[1])
receipt = {
    "pids": [os.getpid(), child.pid],
    "pgids": [os.getpgid(0), os.getpgid(child.pid)],
    "compensated": False,
}
record.write_text(json.dumps(receipt))
if sys.argv[2] == "exit":
    time.sleep(0.3)
elif sys.argv[2] == "nonzero":
    time.sleep(0.3)
    raise SystemExit(7)
elif sys.argv[2] == "stdout-cap":
    time.sleep(0.3)
    os.write(1, b"A" * 1_048_577)
    raise SystemExit(0)
elif sys.argv[2] == "stderr-cap":
    time.sleep(0.3)
    os.write(2, b"B" * 1_048_577)
    raise SystemExit(0)
elif sys.argv[2] == "compensate":
    time.sleep(0.6)
    os.killpg(child.pid, signal.SIGKILL)
    child.wait()
    receipt["compensated"] = True
    record.write_text(json.dumps(receipt))
else:
    time.sleep(30)
"""
        return [str(PYTHON), "-c", parent_source, str(record_path), mode, child_source]

    def _assert_tree_gone_and_cleanup_if_needed(self, record_path):
        deadline = time.monotonic() + 2
        while not record_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(record_path.is_file(), "process tree did not publish its receipt")
        receipt = json.loads(record_path.read_text())
        verification_deadline = time.monotonic() + 2
        survivors = []
        for pid in receipt["pids"]:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            survivors.append(("pid", pid))
        for pgid in receipt["pgids"]:
            if _process_group_exists(pgid, deadline=verification_deadline):
                survivors.append(("pgid", pgid))
        for pgid in receipt["pgids"]:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        self.assertEqual(survivors, [])
        return receipt

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
            lambda: uninitialized._observe_bound(1),
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

    def test_outer_timeout_and_observation_remove_separate_descendant_groups(self):
        class DelayedDetectionObserver:
            def __init__(self):
                self.calls = 0

            def snapshot(self, timeout=None):
                self.calls += 1
                if self.calls < 4:
                    return frozenset(), frozenset()
                return frozenset({"process:securityagent"}), frozenset()

        for trigger in ("timeout", "observation"):
            with self.subTest(trigger=trigger), tempfile.TemporaryDirectory() as root:
                record = Path(root) / "tree.json"
                effects = object.__new__(LiveIntegrationEffects)
                effects.capability = None
                if trigger == "observation":
                    effects.observer = DelayedDetectionObserver()
                    effects.observer_baseline = (frozenset(), frozenset())
                    expected_error = SecurityAgentDetected
                else:
                    effects.observer = None
                    effects.observer_baseline = None
                    expected_error = IntegrationWorkflowFailure
                with mock.patch(
                    f"{__name__}._require_live_capability", return_value=None
                ):
                    if trigger == "observation":
                        observed = effects._run(
                            self._harmless_process_tree_command(
                                record,
                                "compensate",
                            ),
                            timeout=0.8,
                        )
                        self.assertIsInstance(
                            observed.observation_error, SecurityAgentDetected
                        )
                    else:
                        with self.assertRaises(expected_error):
                            effects._run(
                                self._harmless_process_tree_command(record, "sleep"),
                                timeout=0.8,
                            )
                receipt = self._assert_tree_gone_and_cleanup_if_needed(record)
                if trigger == "observation":
                    self.assertTrue(receipt["compensated"])

    def test_process_tree_termination_fails_closed_when_descendant_scan_is_unavailable(self):
        root = ProcessIdentity(999_999, 1, 999_999, 10, 1)
        tracker = ProcessTreeTracker(root)
        process = mock.Mock(pid=root.pid)
        process.poll.return_value = 0
        process.wait.return_value = 0
        with mock.patch(
            f"{__name__}._process_table",
            side_effect=IntegrationWorkflowFailure,
        ) as scanner, mock.patch("os.killpg") as signal_group:
            self.assertFalse(
                _terminate_process_tree(
                    process,
                    tracker,
                    deadline=time.monotonic() + 0.1,
                )
            )
        scanner.assert_called()
        signal_group.assert_not_called()

    def test_descendant_scan_never_adopts_children_after_root_pid_disappears(self):
        with mock.patch(
            f"{__name__}._process_table",
            return_value=[
                ProcessIdentity(123, 999_999, 123, 1, 0),
                ProcessIdentity(456, 1, 456, 2, 0),
            ],
        ):
            self.assertEqual(
                _descendant_process_groups(
                    999_999, deadline=time.monotonic() + 0.1
                ),
                set(),
            )

    def test_process_tracker_revalidates_stable_identities_before_signaling_groups(self):
        self.assertIn("ProcessIdentity", globals())
        self.assertIn("ProcessTreeTracker", globals())
        root = ProcessIdentity(100, 1, 100, 10, 1)
        leader = ProcessIdentity(200, 100, 200, 20, 1)
        member = ProcessIdentity(201, 200, 200, 21, 1)
        tracker = ProcessTreeTracker(root)
        tracker.observe((root, leader, member))

        reparented_member = ProcessIdentity(201, 1, 200, 21, 1)
        tracker.observe((reparented_member,))
        self.assertEqual(tracker.signalable_descendant_groups(), {200})

        reused_group = ProcessIdentity(300, 1, 200, 30, 1)
        tracker.observe((reused_group,))
        self.assertEqual(tracker.signalable_descendant_groups(), set())

    def test_process_tracker_does_not_traverse_through_reused_historical_child_pid(self):
        root = ProcessIdentity(100, 1, 100, 10, 1)
        child = ProcessIdentity(200, 100, 200, 20, 1)
        tracker = ProcessTreeTracker(root)
        tracker.observe((root, child))

        reused_child = ProcessIdentity(200, 1, 900, 99, 9)
        foreign_grandchild = ProcessIdentity(300, 200, 300, 30, 1)
        tracker.observe((root, reused_child, foreign_grandchild))

        self.assertNotIn(foreign_grandchild.stable_key, tracker.tracked_identities)
        self.assertEqual(tracker.signalable_descendant_groups(), set())

    def test_reused_root_identity_and_pgid_are_never_signaled(self):
        root = ProcessIdentity(100, 1, 100, 10, 1)
        tracker = ProcessTreeTracker(root)
        tracker.observe((root,))
        reused_root = ProcessIdentity(100, 1, 100, 90, 9)
        foreign_member = ProcessIdentity(101, 100, 100, 91, 1)
        process = mock.Mock(pid=root.pid)
        process.poll.return_value = 0
        process.wait.return_value = 0

        with mock.patch(
            f"{__name__}._process_table",
            return_value=(reused_root, foreign_member),
        ), mock.patch("os.killpg") as signal_group:
            cleanup_ok = _terminate_process_tree(
                process,
                tracker,
                deadline=time.monotonic() + 0.1,
            )

        self.assertFalse(cleanup_ok)
        signal_group.assert_not_called()

    def test_group_leader_gone_still_signals_exact_surviving_member_group_only(self):
        root = ProcessIdentity(100, 1, 100, 10, 1)
        leader = ProcessIdentity(200, 100, 200, 20, 1)
        member = ProcessIdentity(201, 200, 200, 21, 1)
        tracker = ProcessTreeTracker(root)
        tracker.observe((root, leader, member))
        scans = iter(((member,), (member,), ()))

        def next_scan(*_args, **_kwargs):
            return next(scans, ())

        process = mock.Mock(pid=root.pid)
        process.poll.return_value = 0
        process.wait.return_value = 0
        with mock.patch(
            f"{__name__}._process_table", side_effect=next_scan
        ), mock.patch("os.killpg") as signal_group:
            cleanup_ok = _terminate_process_tree(
                process,
                tracker,
                deadline=time.monotonic() + 0.2,
            )

        self.assertTrue(cleanup_ok)
        self.assertIn(mock.call(200, signal.SIGTERM), signal_group.call_args_list)
        self.assertFalse(
            any(call.args[0] == 100 for call in signal_group.call_args_list)
        )

    def test_process_tracker_freezes_adoption_and_fails_closed_on_scan_loss(self):
        self.assertIn("ProcessIdentity", globals())
        self.assertIn("ProcessTreeTracker", globals())
        root = ProcessIdentity(100, 1, 100, 10, 1)
        first = ProcessIdentity(200, 100, 200, 20, 1)
        late = ProcessIdentity(300, 200, 300, 30, 1)
        tracker = ProcessTreeTracker(root)
        tracker.observe((root, first))
        tracker.observe((first, late))
        self.assertNotIn(late.stable_key, tracker.tracked_identities)
        self.assertEqual(tracker.signalable_descendant_groups(), {200})
        tracker.mark_scan_unavailable()
        self.assertFalse(tracker.scan_complete)

    def test_every_communicate_call_has_an_explicit_timeout(self):
        tree = ast.parse(Path(__file__).read_text())
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "communicate"
        ]
        self.assertTrue(calls)
        self.assertTrue(
            all(any(keyword.arg == "timeout" for keyword in call.keywords) for call in calls)
        )

    def test_observer_timeout_removes_descendant_group_after_direct_exit(self):
        with tempfile.TemporaryDirectory() as root:
            record = Path(root) / "tree.json"
            observer = object.__new__(LiveSecurityAgentObserver)
            observer.capability = None
            with mock.patch(
                f"{__name__}._require_live_capability", return_value=None
            ):
                with self.assertRaises(IntegrationWorkflowFailure):
                    observer._run(
                        self._harmless_process_tree_command(record, "exit"),
                        timeout=0.8,
                    )
            self._assert_tree_gone_and_cleanup_if_needed(record)

    def test_observer_failures_always_remove_and_verify_descendant_groups(self):
        for mode in ("sleep", "nonzero", "stdout-cap", "stderr-cap"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                record = Path(root) / "tree.json"
                observer = object.__new__(LiveSecurityAgentObserver)
                observer.capability = None
                with mock.patch(
                    f"{__name__}._require_live_capability", return_value=None
                ):
                    with self.assertRaises(IntegrationWorkflowFailure):
                        observer._run(
                            self._harmless_process_tree_command(record, mode),
                            timeout=0.8,
                        )
                self._assert_tree_gone_and_cleanup_if_needed(record)

    def test_observer_success_depends_on_the_same_terminal_cleanup_block(self):
        root = ProcessIdentity(4242, 1, 4242, 10, 1)
        for cleanup_ok in (True, False):
            with self.subTest(cleanup_ok=cleanup_ok):
                process = mock.Mock(pid=root.pid)
                process.communicate.return_value = (b'{"ok":true}\n', b"")
                process.returncode = 0
                process.poll.return_value = 0
                tracker = ProcessTreeTracker(root)
                tracker.observe(())
                observer = object.__new__(LiveSecurityAgentObserver)
                observer.capability = None
                with mock.patch(
                    f"{__name__}._require_live_capability", return_value=None
                ), mock.patch(
                    "subprocess.Popen", return_value=process
                ), mock.patch(
                    f"{__name__}._root_process_tracker", return_value=tracker
                ), mock.patch(
                    f"{__name__}._refresh_process_tracker", return_value=None
                ), mock.patch(
                    f"{__name__}._terminate_process_tree",
                    return_value=cleanup_ok,
                ) as cleanup:
                    if cleanup_ok:
                        self.assertEqual(
                            observer._run(["fake-observer"], timeout=1),
                            b'{"ok":true}\n',
                        )
                    else:
                        with self.assertRaises(IntegrationWorkflowFailure):
                            observer._run(["fake-observer"], timeout=1)
                cleanup.assert_called_once()

    def test_observer_process_scan_overrun_uses_bounded_terminal_cleanup(self):
        root = ProcessIdentity(4343, 1, 4343, 10, 1)
        tracker = ProcessTreeTracker(root)
        process = mock.Mock(pid=root.pid)
        process.poll.return_value = None
        observer = object.__new__(LiveSecurityAgentObserver)
        observer.capability = None
        with mock.patch(
            f"{__name__}._require_live_capability", return_value=None
        ), mock.patch(
            "subprocess.Popen", return_value=process
        ), mock.patch(
            f"{__name__}._root_process_tracker", return_value=tracker
        ), mock.patch(
            f"{__name__}._refresh_process_tracker",
            side_effect=IntegrationWorkflowFailure,
        ), mock.patch(
            f"{__name__}._terminate_process_tree", return_value=False
        ) as cleanup:
            with self.assertRaises(IntegrationWorkflowFailure):
                observer._run(["fake-observer"], timeout=1)
        cleanup.assert_called_once()
        self.assertIn("deadline", cleanup.call_args.kwargs)

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
        self.assertIn("PROC_PIDTBSDINFO", observer_source)
        self.assertIn("pbi_start_tvsec", observer_source)
        self.assertIn("pbi_start_tvusec", observer_source)
        self.assertIn("pbi_pgid", observer_source)
        self.assertIn("pbi_ppid", observer_source)
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

    def test_securityagent_failure_with_rejected_quarantine_preserves_without_deletion(self):
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
        self.assertEqual((outcome.status, outcome.code), ("FAIL", "securityagent_detected"))
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

    def test_securityagent_detected_inside_helper_remains_terminal_if_disposition_is_unclear(self):
        class DetectionDuringMountEffects(FakeLiveEffects):
            def invoke_helper(self, operation, request):
                if operation == "mount":
                    self.calls.append("mount-securityagent-detected")
                    raise SecurityAgentDetected
                return super().invoke_helper(operation, request)

            def dispose_after_failure(self, *, encryption_uuid, cleanup_approved):
                self.calls.append("preserve-after-detection")
                raise IntegrationWorkflowFailure

        effects = DetectionDuringMountEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=False,
        )
        self.assertEqual((outcome.status, outcome.code), ("FAIL", "securityagent_detected"))
        self.assertIn("preserve-after-detection", effects.calls)
        self.assertNotIn("delete-disposable-item", effects.calls)
        self.assertNotIn("delete-image", effects.calls)

    def test_invoke_helper_records_safe_mount_receipt_before_raising_observation(self):
        self.assertIn("ObservedProcessResult", globals())
        effects = object.__new__(LiveIntegrationEffects)
        effects.capability = None
        effects.invocation_counter = 0
        effects.helper = Path("/private/tmp/fake-helper")
        effects.image_path = Path("/private/tmp/CORTEX_TEST.sparsebundle")
        effects.mount_path = Path("/private/tmp/CORTEX_TEST_MOUNT")
        effects.preserve_image_and_item = False
        effects.mounted_device = None
        effects.encryption_uuid = None
        response = {
            "schema_version": 1,
            "operation": "mount",
            "code": "OK",
            "encryption_uuid": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
            "device": "/dev/disk99",
            "item_count": 1,
        }
        completed = subprocess.CompletedProcess(
            ["helper"], 0, json.dumps(response) + "\n", ""
        )
        effects._run = mock.Mock(
            return_value=ObservedProcessResult(completed, SecurityAgentDetected())
        )
        with mock.patch(
            f"{__name__}._require_live_capability", return_value=None
        ):
            with self.assertRaises(SecurityAgentDetected):
                effects.invoke_helper("mount", {})
        self.assertEqual(effects.mounted_device, "/dev/disk99")
        self.assertFalse(effects.preserve_image_and_item)

    def test_detected_mount_uses_real_disposition_to_detach_then_quarantine(self):
        encryption_uuid = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            image_path = root / "CORTEX_TEST.sparsebundle"
            mount_path = root / "CORTEX_TEST_MOUNT"
            quarantine_path = root / "CORTEX_TEST.sparsebundle.quarantine"
            image_path.mkdir()
            mount_path.mkdir()
            helper = root / "disk-image-keychain"
            helper.touch()

            effects = object.__new__(LiveIntegrationEffects)
            effects.capability = LiveCapability(_LIVE_CAPABILITY_SEAL, True)
            effects.observer = None
            effects.observer_baseline = None
            effects.private_root = root
            effects.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            effects.plan = LiveIntegrationPlan(
                image_path=image_path,
                mount_path=mount_path,
                quarantine_path=quarantine_path,
                transaction_id="12345678-1234-4234-8234-123456789abc",
                size="64m",
                filesystem="APFS",
                volume_name="CORTEX_BRIDGE_SPIKE",
            )
            effects.image_path = image_path
            effects.mount_path = mount_path
            effects.quarantine_path = quarantine_path
            effects.transaction_id = effects.plan.transaction_id
            effects.helper = helper
            effects.image_identity = None
            effects.image_fd = None
            effects.image_name = image_path.name
            effects.image_quarantined = False
            effects.preserve_image_and_item = False
            effects.encryption_uuid = None
            effects.mounted_device = None
            effects.invocation_counter = 0
            effects.terminal_observation_error = None
            effects.disposition_active = False
            events = []

            def helper_response(operation, *, device=None, item_count=None):
                return {
                    "schema_version": 1,
                    "operation": operation,
                    "code": "OK",
                    "encryption_uuid": encryption_uuid,
                    "device": device,
                    "item_count": item_count,
                }

            def fake_run(
                argv,
                *,
                input_text=None,
                timeout=COMMAND_TIMEOUT_SECONDS,
                accepted_returncodes=(0,),
            ):
                del timeout, accepted_returncodes
                if argv[:2] == ["/usr/bin/xcrun", "swiftc"]:
                    events.append("compile")
                    completed = subprocess.CompletedProcess(argv, 0, "", "")
                    return ObservedProcessResult(completed, None)
                if argv == [str(helper)]:
                    operation = json.loads(input_text)["operation"]
                    events.append(f"helper:{operation}")
                    if operation == "create":
                        response = helper_response(operation, item_count=1)
                        observation_error = None
                    elif operation == "mount":
                        response = helper_response(
                            operation, device="/dev/disk99", item_count=1
                        )
                        observation_error = SecurityAgentDetected()
                    elif operation == "detach":
                        response = helper_response(operation, device="/dev/disk99")
                        observation_error = SecurityAgentDetected()
                    else:
                        self.fail(f"unexpected Keychain helper operation: {operation}")
                    completed = subprocess.CompletedProcess(
                        argv, 0, json.dumps(response) + "\n", ""
                    )
                    return ObservedProcessResult(completed, observation_error)
                if argv == ["/usr/bin/hdiutil", "info", "-plist"]:
                    events.append("plist:info")
                    payload = plistlib.dumps({"images": []}).decode("utf-8")
                    completed = subprocess.CompletedProcess(argv, 0, payload, "")
                    return ObservedProcessResult(
                        completed, SecurityAgentDetected()
                    )
                self.fail(f"unexpected fake subprocess: {argv}")

            test_case = self

            class FakeRename:
                argtypes = None
                restype = None

                def __call__(self, source_fd, source, target_fd, target, flags):
                    test_case.assertEqual(flags, 0x00000004)
                    events.append("rename:quarantine")
                    os.rename(
                        os.fsdecode(source),
                        os.fsdecode(target),
                        src_dir_fd=source_fd,
                        dst_dir_fd=target_fd,
                    )
                    return 0

            class FakeLibC:
                renameatx_np = FakeRename()

            effects._run = fake_run
            try:
                with mock.patch("ctypes.CDLL", return_value=FakeLibC()):
                    outcome = run_live_integration_workflow(
                        effects=effects,
                        observer=FakeSecurityAgentObserver(),
                        cleanup_approved=True,
                    )
                self.assertEqual(
                    (outcome.status, outcome.code),
                    ("FAIL", "securityagent_detected"),
                )
                self.assertEqual(effects.mounted_device, None)
                self.assertIsInstance(
                    effects.terminal_observation_error, SecurityAgentDetected
                )
                self.assertTrue(quarantine_path.is_dir())
                self.assertFalse(image_path.exists())
                self.assertEqual(
                    events,
                    [
                        "compile",
                        "helper:create",
                        "helper:mount",
                        "helper:detach",
                        "plist:info",
                        "rename:quarantine",
                    ],
                )
                self.assertNotIn("helper:inspect-item", events)
                self.assertNotIn("helper:delete-disposable-item", events)
            finally:
                for descriptor_name in ("image_fd", "root_fd"):
                    descriptor = getattr(effects, descriptor_name, None)
                    if isinstance(descriptor, int) and descriptor >= 0:
                        os.close(descriptor)
                        setattr(effects, descriptor_name, -1)

    def test_nonzero_helper_response_latches_terminal_observation_before_error(self):
        for observation_error in (
            SecurityAgentDetected(),
            ObservationUnavailable(),
        ):
            with self.subTest(error=type(observation_error).__name__):
                effects = object.__new__(LiveIntegrationEffects)
                effects.capability = None
                effects.invocation_counter = 0
                effects.helper = Path("/private/tmp/fake-helper")
                effects.image_path = Path("/private/tmp/CORTEX_TEST.sparsebundle")
                effects.mount_path = Path("/private/tmp/CORTEX_TEST_MOUNT")
                effects.preserve_image_and_item = False
                effects.mounted_device = None
                effects.encryption_uuid = None
                effects.terminal_observation_error = None
                effects.disposition_active = False
                response = {
                    "schema_version": 1,
                    "operation": "mount",
                    "code": "HDIUTIL_FAILED",
                    "encryption_uuid": None,
                    "device": None,
                    "item_count": None,
                }
                completed = subprocess.CompletedProcess(
                    ["helper"], 70, json.dumps(response) + "\n", ""
                )
                effects._run = mock.Mock(
                    return_value=ObservedProcessResult(
                        completed, observation_error
                    )
                )
                with mock.patch(
                    f"{__name__}._require_live_capability", return_value=None
                ):
                    with self.assertRaises(type(observation_error)):
                        effects.invoke_helper("mount", {})
                self.assertIs(
                    effects.terminal_observation_error, observation_error
                )

    def test_observer_unavailable_during_workflow_is_terminal_unclear(self):
        class UnavailableDuringMountEffects(FakeLiveEffects):
            def invoke_helper(self, operation, request):
                if operation == "mount":
                    self.calls.append("mount-observer-unavailable")
                    raise ObservationUnavailable
                return super().invoke_helper(operation, request)

        effects = UnavailableDuringMountEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=False,
        )
        self.assertEqual(
            (outcome.status, outcome.code),
            ("UNCLEAR", "observer_unavailable"),
        )
        self.assertTrue(effects.item_present)
        self.assertNotIn("delete-disposable-item", effects.calls)

    def test_securityagent_latched_during_failed_disposition_keeps_priority(self):
        class DetectionDuringDispositionEffects(FakeLiveEffects):
            def __init__(self):
                super().__init__()
                self.terminal_observation_error = None

            def invoke_helper(self, operation, request):
                if operation == "mount":
                    self.calls.append("mount-failed")
                    raise IntegrationWorkflowFailure
                return super().invoke_helper(operation, request)

            def dispose_after_failure(self, *, encryption_uuid, cleanup_approved):
                self.calls.append("disposition-detected-then-failed")
                self.terminal_observation_error = SecurityAgentDetected()
                raise IntegrationWorkflowFailure

        effects = DetectionDuringDispositionEffects()
        outcome = run_live_integration_workflow(
            effects=effects,
            observer=FakeSecurityAgentObserver(),
            cleanup_approved=False,
        )
        self.assertEqual(
            (outcome.status, outcome.code),
            ("FAIL", "securityagent_detected"),
        )

    def test_disposition_never_deletes_item_after_inspect_latches_securityagent(self):
        encryption_uuid = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
        effects = object.__new__(LiveIntegrationEffects)
        effects.capability = LiveCapability(_LIVE_CAPABILITY_SEAL, True)
        effects.preserve_image_and_item = False
        effects.mounted_device = None
        effects.terminal_observation_error = None
        effects.disposition_active = False
        effects.root_fd = -1
        effects.image_fd = -1
        events = []

        effects._image_entry_present = mock.Mock(return_value=True)
        effects.request = mock.Mock(
            side_effect=lambda operation, *_args, **_kwargs: {
                "operation": operation
            }
        )
        effects.quarantine_exact_image = mock.Mock(
            side_effect=lambda: events.append("quarantine")
        )
        effects.delete_exact_image = mock.Mock(
            side_effect=lambda: events.append("delete-image")
        )

        def invoke_helper(operation, request):
            del request
            events.append(operation)
            if operation == "inspect-item":
                effects.terminal_observation_error = SecurityAgentDetected()
                return (
                    {
                        "schema_version": 1,
                        "operation": operation,
                        "code": "OK",
                        "encryption_uuid": encryption_uuid,
                        "device": None,
                        "item_count": 1,
                    },
                    "helper-inspect",
                )
            self.fail("Keychain delete ran after SecurityAgent was latched")

        effects.invoke_helper = invoke_helper
        effects.dispose_after_failure(
            encryption_uuid=encryption_uuid,
            cleanup_approved=True,
        )
        self.assertEqual(events, ["inspect-item", "quarantine"])


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
        var bsdInfo = proc_bsdinfo()
        let bsdInfoSize = Int32(MemoryLayout<proc_bsdinfo>.size)
        let copiedInfoSize = proc_pidinfo(
            processID, PROC_PIDTBSDINFO, 0, &bsdInfo, bsdInfoSize
        )
        var nameStorage = [CChar](repeating: 0, count: Int(MAXPATHLEN))
        var pathStorage = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
        let nameLength = proc_name(processID, &nameStorage, UInt32(nameStorage.count))
        let pathLength = proc_pidpath(processID, &pathStorage, UInt32(pathStorage.count))
        guard copiedInfoSize == bsdInfoSize, nameLength > 0 || pathLength > 0 else {
            processMetadataComplete = false
            continue
        }
        let name = nameLength > 0 ? String(cString: nameStorage) : ""
        let path = pathLength > 0 ? String(cString: pathStorage) : ""
        let executable = path.split(separator: "/").last.map(String.init) ?? ""
        if name == "SecurityAgent" || executable == "SecurityAgent" {
            processIDs.insert(processID)
            processes.append(
                "process:\(bsdInfo.pbi_pid):\(bsdInfo.pbi_ppid):" +
                "\(bsdInfo.pbi_pgid):\(bsdInfo.pbi_start_tvsec):" +
                "\(bsdInfo.pbi_start_tvusec):SecurityAgent"
            )
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
        plan = _process_deadline_plan(time.monotonic(), timeout)
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
            tracker = _root_process_tracker(process.pid, plan.execution_deadline)
        except IntegrationWorkflowFailure:
            tracker = ProcessTreeTracker(ProcessIdentity(process.pid, 0, process.pid, 0, 0))
            tracker.mark_scan_unavailable()
        stdout = stderr = b""
        failure = None
        try:
            if not tracker.scan_complete:
                raise IntegrationWorkflowFailure
            while True:
                _refresh_process_tracker(tracker, plan.execution_deadline)
                try:
                    stdout, stderr = process.communicate(
                        timeout=_bounded_timeout(plan.execution_deadline, 0.10)
                    )
                    break
                except subprocess.TimeoutExpired as timeout_error:
                    partial_stdout = timeout_error.output or b""
                    partial_stderr = timeout_error.stderr or b""
                    if len(partial_stdout) > 1_048_576 or len(partial_stderr) > 1_048_576:
                        raise IntegrationWorkflowFailure
            if process.returncode != 0 or len(stdout) > 1_048_576 or len(stderr) > 1_048_576:
                raise IntegrationWorkflowFailure
            _refresh_process_tracker(tracker, plan.post_monitor_deadline)
            if tracker.signalable_descendant_groups():
                raise IntegrationWorkflowFailure
        except Exception:
            failure = IntegrationWorkflowFailure()
        finally:
            cleanup_ok = _terminate_process_tree(
                process, tracker, deadline=plan.cleanup_deadline
            )
            if not cleanup_ok:
                failure = IntegrationWorkflowFailure()
            _close_process_pipes(process)
        if failure is not None:
            raise failure
        return stdout

    def snapshot(self, timeout=10):
        _require_live_capability(self.capability)
        payload = self._run([str(self.binary)], timeout=timeout)
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
        self.terminal_observation_error = None
        self.disposition_active = False

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

    def _observe_bound(self, timeout):
        self._require_capability()
        if self.observer is None or self.observer_baseline is None:
            return
        processes, windows = self.observer.snapshot(timeout=timeout)
        baseline_processes, baseline_windows = self.observer_baseline
        if processes - baseline_processes or windows - baseline_windows:
            raise SecurityAgentDetected

    def _latch_terminal_observation(self, error):
        if (
            isinstance(error, SecurityAgentDetected)
            or getattr(self, "terminal_observation_error", None) is None
        ):
            self.terminal_observation_error = error

    def _kill_process_group(self, process, tracker, *, deadline):
        self._require_capability()
        if not _terminate_process_tree(process, tracker, deadline=deadline):
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
        plan = _process_deadline_plan(time.monotonic(), timeout)
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
        try:
            tracker = _root_process_tracker(process.pid, plan.execution_deadline)
        except IntegrationWorkflowFailure:
            tracker = ProcessTreeTracker(ProcessIdentity(process.pid, 0, process.pid, 0, 0))
            tracker.mark_scan_unavailable()
        first_communication = True
        stdout = stderr = ""
        pending_observation_error = None
        failure = None
        supervision_error = None
        communication_completed = False
        try:
            if not tracker.scan_complete:
                raise IntegrationWorkflowFailure
            while True:
                _refresh_process_tracker(tracker, plan.execution_deadline)
                if pending_observation_error is None:
                    try:
                        self._observe_bound(
                            _bounded_timeout(
                                plan.execution_deadline,
                                HELPER_PRE_MONITOR_CAP_SECONDS,
                            )
                        )
                    except (SecurityAgentDetected, ObservationUnavailable) as error:
                        pending_observation_error = error
                        self._latch_terminal_observation(error)
                try:
                    stdout, stderr = process.communicate(
                        input=input_text if first_communication else None,
                        timeout=_bounded_timeout(plan.execution_deadline, 0.10),
                    )
                    communication_completed = True
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
            if len(stdout) > 1_048_576 or len(stderr) > 1_048_576:
                raise IntegrationWorkflowFailure
            if process.returncode not in accepted_returncodes:
                raise IntegrationWorkflowFailure
            try:
                _refresh_process_tracker(tracker, plan.post_monitor_deadline)
            except IntegrationWorkflowFailure:
                supervision_error = IntegrationWorkflowFailure()
            if pending_observation_error is None:
                try:
                    self._observe_bound(
                        _bounded_timeout(
                            plan.post_monitor_deadline,
                            HELPER_POST_MONITOR_CAP_SECONDS,
                        )
                    )
                except (SecurityAgentDetected, ObservationUnavailable) as error:
                    pending_observation_error = error
                    self._latch_terminal_observation(error)
                except IntegrationWorkflowFailure:
                    supervision_error = IntegrationWorkflowFailure()
            if tracker.signalable_descendant_groups():
                supervision_error = IntegrationWorkflowFailure()
        except Exception:
            failure = IntegrationWorkflowFailure()
        finally:
            try:
                self._kill_process_group(
                    process, tracker, deadline=plan.cleanup_deadline
                )
            except Exception:
                if communication_completed:
                    supervision_error = IntegrationWorkflowFailure()
                else:
                    failure = IntegrationWorkflowFailure()
            _close_process_pipes(process)
        if failure is not None:
            raise failure
        return ObservedProcessResult(
            subprocess.CompletedProcess(argv, process.returncode, stdout, stderr),
            pending_observation_error,
            supervision_error,
        )

    def compile_production_helper(self):
        self._require_capability()
        result = self._run(
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
        if result.observation_error is not None:
            self._latch_terminal_observation(result.observation_error)
            raise result.observation_error
        if result.supervision_error is not None:
            raise result.supervision_error
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
            observed = self._run(
                [str(self.helper)],
                input_text=json.dumps(request, separators=(",", ":")) + "\n",
                timeout=HELPER_OUTER_TIMEOUT_SECONDS,
                accepted_returncodes=(0, 64, 70),
            )
        except Exception:
            if operation == "create":
                self._capture_image_identity()
            if operation in {"create", "mount"}:
                self.preserve_image_and_item = True
            raise
        completed = observed.completed
        if completed.stderr or completed.stdout.count("\n") != 1:
            raise IntegrationWorkflowFailure
        try:
            response = json.loads(completed.stdout)
        except (TypeError, ValueError):
            raise IntegrationWorkflowFailure from None
        serialized = json.dumps(response, separators=(",", ":"))
        if str(self.image_path) in serialized or str(self.mount_path) in serialized:
            raise IntegrationWorkflowFailure
        if (
            set(response)
            != {
                "schema_version",
                "operation",
                "code",
                "encryption_uuid",
                "device",
                "item_count",
            }
            or response.get("schema_version") != 1
            or response.get("operation") != operation
            or not isinstance(response.get("code"), str)
        ):
            raise IntegrationWorkflowFailure
        if operation == "create" and isinstance(response.get("encryption_uuid"), str):
            self._capture_image_identity()
            self.encryption_uuid = response["encryption_uuid"]
        elif operation == "mount" and isinstance(response.get("device"), str):
            self.mounted_device = response["device"]
        elif operation == "detach" and response.get("code") == "OK":
            self.mounted_device = None
        if observed.observation_error is not None:
            self._latch_terminal_observation(observed.observation_error)
        if completed.returncode != 0 or response.get("code") != "OK":
            if response.get("code") == "MOUNT_CLEANUP_UNCLEAR" or operation in {"create", "mount"}:
                self.preserve_image_and_item = True
            if (
                observed.observation_error is not None
                and not getattr(self, "disposition_active", False)
            ):
                raise observed.observation_error
            if observed.supervision_error is not None:
                raise observed.supervision_error
            raise IntegrationWorkflowFailure
        if (
            observed.observation_error is not None
            and not getattr(self, "disposition_active", False)
        ):
            raise observed.observation_error
        if observed.supervision_error is not None:
            raise observed.supervision_error
        return response, f"fresh-helper-{self.invocation_counter}"

    def _plist_command(self, argv):
        self._require_capability()
        observed = self._run(argv)
        try:
            payload = plistlib.loads(observed.completed.stdout.encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            raise IntegrationWorkflowFailure from None
        if observed.observation_error is not None:
            self._latch_terminal_observation(observed.observation_error)
            if not getattr(self, "disposition_active", False):
                raise observed.observation_error
        if observed.supervision_error is not None:
            raise observed.supervision_error
        return payload

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
        previous_disposition_state = getattr(self, "disposition_active", False)
        self.disposition_active = True
        try:
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
            if getattr(self, "terminal_observation_error", None) is not None:
                self.quarantine_exact_image()
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
            if getattr(self, "terminal_observation_error", None) is not None:
                self.quarantine_exact_image()
                return
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
        finally:
            self.disposition_active = previous_disposition_state


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
