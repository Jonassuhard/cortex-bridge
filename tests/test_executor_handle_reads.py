import os
import tempfile
import unittest
import uuid
import dataclasses
import json
import hashlib
import importlib.util
from unittest.mock import patch
from executor import fd_ops
from effect_gate import EffectGate, MissionApprovalResponse
from orchestration.effect_schema import upgrade_effect_schema
from pathlib import Path, PurePosixPath
from executor.tools import ToolExecutor, ToolDenied, MAX_SEARCH_FILE_BYTES, check_command_allowed, detect_test_command
from executor.workspace_handle import WorkspaceHandle, MountFacts, WorkspaceHandleClosed, WorkspaceIdentityChanged
from executor.policy import PolicyEngine
from orchestration.store import Store
from orchestration.loop import default_trace_validator, MissionLoop, MockOrchestrator


class HandleReadTests(unittest.IsolatedAsyncioTestCase):
    def recover_write(self, row):
        self.assertIsNotNone(importlib.util.find_spec("executor.effect_recovery"),
                             "Descriptor write recovery is not implemented")
        from executor.effect_recovery import reconcile_write_effect
        # Simulate a missing terminal receipt from the real persisted write evidence.
        interrupted = {**dict(row), "state": "active", "receipt_json": None, "finished_at": None}
        return reconcile_write_effect(self.handle, interrupted)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "20_WORKSPACES" / "qa"
        self.workspace.mkdir(parents=True)
        mount = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        workspace = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY)
        # Synthetic mount observation; actual filesystem operations use real FDs.
        facts = MountFacts(os.fstat(mount).st_dev & 0xffffffff, (1,2), 0, "fixture", "fixture", str(self.root), "fixture")
        try:
            self.handle = WorkspaceHandle.from_verified_fds(mount_fd=mount, workspace_fd=workspace,
                storage_transaction_id="fixture", apfs_volume_uuid="fixture",
                relative_path=PurePosixPath("20_WORKSPACES/qa"), fd_probe=lambda fd: facts)
        finally:
            os.close(mount)
            os.close(workspace)
        self.addCleanup(self.handle.close)

    async def test_production_read_uses_retained_handle_after_path_replacement(self):
        (self.workspace / "a.txt").write_text("original")
        executor = ToolExecutor(self.handle)
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        (self.workspace / "a.txt").write_text("replacement")
        result = await executor.read_file("a.txt")
        self.assertEqual(result["content"], "original")
        self.assertFalse(result["truncated"])

    async def test_closed_handle_is_not_replaced_with_path_access(self):
        (self.workspace / "a.txt").write_text("A")
        executor = ToolExecutor(self.handle)
        self.handle.close()
        with self.assertRaises(WorkspaceHandleClosed):
            await executor.read_file("a.txt")

    async def test_volume_identity_change_denies_production_read(self):
        (self.workspace / 'a.txt').write_text('must not be returned')
        executor = ToolExecutor(self.handle)
        original = self.handle._fd_probe(self.handle.mount_fd)
        self.handle._fd_probe = lambda fd: dataclasses.replace(original, volume_uuid='different')
        with self.assertRaises(WorkspaceIdentityChanged):
            await executor.read_file('a.txt')

    async def test_symlink_and_escape_are_rejected_by_production_read(self):
        (self.root / "outside.txt").write_text("private")
        (self.workspace / "link").symlink_to(self.root / "outside.txt")
        executor = ToolExecutor(self.handle)
        for relative in ("../../outside.txt", "link"):
            with self.assertRaises(ToolDenied):
                await executor.read_file(relative)

    async def test_bounded_read_reports_truncation(self):
        (self.workspace / "a.txt").write_text("abcdef")
        result = await ToolExecutor(self.handle).read_file("a.txt", maxBytes=3)
        self.assertEqual((result["content"], result["size"], result["truncated"]), ("abc", 6, True))

    async def test_listing_and_existence_use_original_directory(self):
        (self.workspace / "a.txt").write_text("A")
        executor = ToolExecutor(self.handle)
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        (self.workspace / "replacement.txt").write_text("wrong root")
        result = await executor.list_directory()
        self.assertEqual([e["name"] for e in result["entries"]], ["a.txt"])
        self.assertTrue((await executor.file_exists("a.txt"))["exists"])
        self.assertFalse((await executor.file_exists("replacement.txt"))["exists"])

    async def test_listing_labels_link_without_reading_its_target(self):
        (self.root / "outside").mkdir()
        (self.workspace / "link").symlink_to(self.root / "outside", target_is_directory=True)
        executor = ToolExecutor(self.handle)
        self.assertEqual((await executor.list_directory())["entries"][0]["type"], "symlink")
        with self.assertRaises(ToolDenied):
            await executor.list_directory("link")
        with self.assertRaises(ToolDenied):
            await executor.file_exists("link")

    async def test_listing_limit_and_existence_missing_parent(self):
        for name in ("a", "b", "c"):
            (self.workspace / name).write_text(name)
        executor = ToolExecutor(self.handle)
        result = await executor.list_directory(maxEntries=2)
        self.assertEqual([e["name"] for e in result["entries"]], ["a", "b"])
        self.assertTrue(result["truncated"])
        self.assertFalse((await executor.file_exists("missing/leaf"))["exists"])
        for limit in (0, -1, True):
            with self.assertRaises(ToolDenied):
                await executor.list_directory(maxEntries=limit)

    async def test_search_retains_root_and_ignores_links_and_exclusions(self):
        (self.workspace / "sub").mkdir()
        (self.workspace / "sub/a.txt").write_text("first\nneedle\n")
        (self.workspace / "node_modules").mkdir()
        (self.workspace / "node_modules/hidden.txt").write_text("needle")
        (self.root / "outside.txt").write_text("needle outside")
        (self.workspace / "link.txt").symlink_to(self.root / "outside.txt")
        executor = ToolExecutor(self.handle)
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        (self.workspace / "wrong.txt").write_text("needle wrong")
        result = await executor.search_text("needle")
        self.assertEqual(result["matches"], [{"path":"sub/a.txt", "line":2, "text":"needle"}])
        self.assertFalse(result["truncated"])

    async def test_search_supports_file_regex_and_limits(self):
        (self.workspace / "a.txt").write_text("item1\nitem2\nitem3")
        result = await ToolExecutor(self.handle).search_text(r"item[0-9]", path="a.txt", isRegex=True, maxResults=2)
        self.assertEqual([r["line"] for r in result["matches"]], [1, 2])
        self.assertTrue(result["truncated"])

    async def test_search_does_not_read_hardlinks_or_binary_files(self):
        (self.root / "outside.txt").write_text("needle")
        os.link(self.root / "outside.txt", self.workspace / "hardlink")
        (self.workspace / "binary").write_bytes(b"needle\x00binary")
        self.assertEqual((await ToolExecutor(self.handle).search_text("needle"))["matches"], [])

    async def test_search_marks_oversized_content_as_incomplete(self):
        (self.workspace / "large").write_bytes(b"x" * (MAX_SEARCH_FILE_BYTES + 1))
        result = await ToolExecutor(self.handle).search_text("needle")
        self.assertEqual(result["matches"], [])
        self.assertTrue(result["truncated"])

    async def test_search_rejects_escaping_start_and_invalid_limit(self):
        executor = ToolExecutor(self.handle)
        with self.assertRaises(ToolDenied):
            await executor.search_text("needle", path="..")
        with self.assertRaises(ToolDenied):
            await executor.search_text("needle", maxResults=True)

    def test_policy_accepts_verified_handle_and_refuses_closed_handle(self):
        policy = PolicyEngine(self.handle)
        self.assertTrue(policy.evaluate("read_file", {"path":"a.txt"}).allowed)
        self.assertTrue(policy.evaluate("write_file", {"path":"a.txt", "content":"A"}).requires_approval)
        self.handle.close()
        self.assertFalse(policy.evaluate("read_file", {"path":"a.txt"}).allowed)

    def test_handle_policy_cannot_be_granted_by_a_path_allowlist(self):
        with self.assertRaisesRegex(ValueError, "HANDLE_ALLOWLIST_REQUIRED"):
            PolicyEngine(self.handle, allowed_workspaces=[self.root])

    def test_final_validator_checks_changed_file_through_handle(self):
        (self.workspace / "a.txt").write_text("A")
        executor = ToolExecutor(self.handle)
        store = Store(":memory:")
        self.addCleanup(store.close)
        store.create_mission("m", "fixture", "20_WORKSPACES/qa")
        store.record_tool_execution("t", "m", "a", "write_file", {}, {"filesChanged":["a.txt"]}, 0, 1, 2)
        store.record_validation("v", "m", "a", True, [{"name":"fixture", "passed":True}])
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        self.assertTrue(default_trace_validator({}, executor, store, "m")["passed"])
        (self.root / "displaced/a.txt").unlink()
        (self.workspace / "a.txt").write_text("replacement must not validate")
        self.assertFalse(default_trace_validator({}, executor, store, "m")["passed"])

    async def test_read_mission_completes_with_production_handle_executor(self):
        (self.workspace / "a.txt").write_text("A")
        store = Store(":memory:")
        self.addCleanup(store.close)
        mission = str(uuid.uuid4())
        store.create_mission(mission, "Read the fixture", "20_WORKSPACES/qa")
        orchestrator = MockOrchestrator(mission, [
            {"state":"EXECUTE", "action":{"tool":"read_file", "arguments":{"path":"a.txt"}}},
            {"state":"COMPLETE", "action":None, "terminal":True, "acceptanceCriteria":["File read"]},
        ])
        result = await MissionLoop(store=store, mission_id=mission, orchestrator=orchestrator,
                                   tools=ToolExecutor(self.handle)).run()
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(store.count("tool_executions", mission), 1)

    def test_script_checks_use_retained_root_and_reject_links(self):
        (self.workspace / "script.py").write_text("pass")
        (self.root / "outside.py").write_text("pass")
        (self.workspace / "link.py").symlink_to(self.root / "outside.py")
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        check_command_allowed(["python3", "script.py"], self.handle)
        for path in ("link.py", "missing.py", "../outside.py"):
            with self.assertRaises(ToolDenied):
                check_command_allowed(["python3", path], self.handle)

    def test_test_discovery_reads_retained_manifest(self):
        (self.workspace / "package.json").write_text('{"scripts":{"test":"fixture"}}')
        self.workspace.rename(self.root / "displaced")
        self.workspace.mkdir()
        self.assertEqual(detect_test_command(self.handle), ["npm", "test"])
        policy = PolicyEngine(self.handle, allow_processes=True)
        decision = policy.evaluate("run_tests", {})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_root_test_discovery_uses_correct_start_directory(self):
        (self.workspace / "test_sample.py").write_text("pass")
        self.assertEqual(detect_test_command(self.handle), ["python3", "-m", "unittest", "discover", "-s", ".", "-v"])

    def test_discovery_rejects_linked_manifest(self):
        (self.root / "external.json").write_text('{"scripts":{"test":"fixture"}}')
        (self.workspace / "package.json").symlink_to(self.root / "external.json")
        with self.assertRaises(ToolDenied):
            detect_test_command(self.handle)
        decision = PolicyEngine(self.handle, allow_processes=True).evaluate("run_tests", {})
        self.assertFalse(decision.allowed)

    async def directory_mission(self, complete=True, operation="create_directory", arguments=None):
        store = Store(":memory:")
        self.addCleanup(store.close)
        mission = str(uuid.uuid4())
        store.create_mission(mission, "Create a directory", self.handle.display_path)
        upgrade_effect_schema(store._conn)
        gate = EffectGate(store)
        def approve(challenge, policy):
            values = dataclasses.asdict(challenge)
            values.pop("tool")
            gate.decide_approval(MissionApprovalResponse(**values, approve=True))
        orchestrator = MockOrchestrator(mission, [
            {"state":"EXECUTE", "action":{"tool":operation, "arguments":arguments or {"path":"created"}}, "requiresApproval":True},
            {"state":"COMPLETE" if complete else "BLOCKED", "action":None, "terminal":True,
             "acceptanceCriteria":["Directory created"] if complete else []},
        ])
        executor = ToolExecutor(self.handle, effect_gate=gate)
        result = await MissionLoop(store=store, mission_id=mission, orchestrator=orchestrator,
                                   tools=executor, effect_gate=gate, approval_callback=approve).run()
        return result, store, mission

    async def test_v3_directory_mission_uses_real_executor_and_receipt(self):
        result, store, mission = await self.directory_mission()
        self.assertEqual(result["state"], "COMPLETED")
        self.assertTrue((self.workspace / "created").is_dir())
        self.assertEqual([row["state"] for row in store.effect_rows()], ["succeeded"])
        self.assertIsNotNone(store.rows("approvals", mission)[0]["effect_consumed_at"])

    async def test_existing_directory_is_preserved_and_not_claimed_created(self):
        target = self.workspace / "created"
        target.mkdir()
        (target / "sentinel").write_text("keep")
        identity = target.stat().st_ino
        _, store, _ = await self.directory_mission(complete=False)
        self.assertEqual(target.stat().st_ino, identity)
        self.assertEqual((target / "sentinel").read_text(), "keep")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["failed"])

    async def test_post_creation_sync_failure_is_durably_unclear(self):
        with patch.object(fd_ops, "fsync_directory", side_effect=OSError("fixture fsync failure")):
            _, store, _ = await self.directory_mission(complete=False)
        self.assertTrue((self.workspace / "created").is_dir())
        self.assertEqual([r["state"] for r in store.effect_rows()], ["outcome_unclear"])

    async def test_handle_mkdir_requires_activation_without_touching_disk(self):
        executor = ToolExecutor(self.handle)
        with self.assertRaises(ToolDenied):
            await executor.create_directory("not-authorized")
        self.assertFalse((self.workspace / "not-authorized").exists())

    async def test_v3_write_mission_uses_real_executor(self):
        result, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"écrit"})
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual((self.workspace / "a.txt").read_text(), "écrit")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["succeeded"])

    async def test_v3_write_preserves_previous_file(self):
        (self.workspace / "a.txt").write_text("previous")
        result, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual((self.workspace / "a.txt").read_text(), "new")
        previous = list(self.workspace.glob(".cortex-*.previous"))
        self.assertEqual(len(previous), 1)
        self.assertEqual(previous[0].read_text(), "previous")

    async def test_prepared_identity_is_durable_before_first_rename(self):
        captured = []
        record = EffectGate.record_prepared_file
        rename = fd_ops.rename_exclusive_at
        def record_and_capture(gate, activation, identity):
            record(gate, activation, identity)
            captured.append((gate, activation))
        def inspect_then_rename(parent, source, destination_parent, destination):
            self.assertEqual(len(captured), 1)
            gate, activation = captured[0]
            row = gate.store.effect_rows()[0]
            ownership = json.loads(row["ownership_json"])
            observed = os.stat(source, dir_fd=parent, follow_symlinks=False)
            self.assertEqual(row["state"], "active")
            self.assertEqual(ownership["prepared"], dict(device=observed.st_dev,
                inode=observed.st_ino, size=observed.st_size, sha256=hashlib.sha256(b"new").hexdigest()))
            return rename(parent, source, destination_parent, destination)
        with patch.object(EffectGate, "record_prepared_file", record_and_capture), patch.object(fd_ops, "rename_exclusive_at", inspect_then_rename):
            result, _, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(len(captured), 1)

    async def test_prepared_journal_failure_prevents_publication(self):
        (self.workspace / "a.txt").write_text("previous")
        with patch.object(EffectGate, "record_prepared_file", side_effect=OSError("fixture journal failure")), patch.object(fd_ops, "rename_exchange_at") as exchange:
            _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"new"})
        exchange.assert_not_called()
        self.assertEqual((self.workspace / "a.txt").read_text(), "previous")
        self.assertEqual(store.effect_rows()[0]["state"], "outcome_unclear")
        self.assertEqual(len(list(self.workspace.glob(".cortex-*.tmp"))), 1)

    async def test_v3_write_refuses_symlink_without_external_mutation(self):
        outside = self.root / "outside.txt"
        outside.write_text("keep")
        (self.workspace / "a.txt").symlink_to(outside)
        _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"new"})
        self.assertEqual(outside.read_text(), "keep")
        self.assertTrue((self.workspace / "a.txt").is_symlink())
        self.assertEqual([r["state"] for r in store.effect_rows()], ["failed"])

    async def test_v3_write_does_not_overwrite_concurrent_destination(self):
        rename = fd_ops.rename_exclusive_at
        def raced_rename(source_fd, source, target_fd, target):
            if source.endswith(".tmp"):
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=target_fd)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(b"concurrent")
            return rename(source_fd, source, target_fd, target)
        with patch.object(fd_ops, "rename_exclusive_at", side_effect=raced_rename):
            _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"ours"})
        self.assertEqual((self.workspace / "a.txt").read_text(), "concurrent")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["outcome_unclear"])

    async def test_v3_write_post_publication_sync_failure_is_unclear(self):
        fsync = fd_ops.fsync_directory
        calls = 0
        def fail_second(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture publication sync failure")
            return fsync(descriptor)
        with patch.object(fd_ops, "fsync_directory", side_effect=fail_second):
            _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"ours"})
        self.assertEqual((self.workspace / "a.txt").read_text(), "ours")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["outcome_unclear"])

    async def test_replacement_keeps_destination_present_between_syscalls(self):
        target = self.workspace / "a.txt"
        target.write_text("previous")
        rename = fd_ops.rename_exclusive_at
        observations = []
        def observe(*args):
            observations.append(target.exists())
            result = rename(*args)
            observations.append(target.exists())
            return result
        with patch.object(fd_ops, "rename_exclusive_at", side_effect=observe):
            result, _, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        self.assertEqual(result["state"], "COMPLETED")
        self.assertTrue(observations)
        self.assertTrue(all(observations), observations)

    async def test_interrupted_exchange_retains_previous_bytes(self):
        (self.workspace / "a.txt").write_text("previous")
        fsync = fd_ops.fsync_directory
        calls = 0
        def fail_after_exchange(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture interrupted exchange")
            return fsync(descriptor)
        with patch.object(fd_ops, "fsync_directory", side_effect=fail_after_exchange):
            _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"new"})
        self.assertEqual((self.workspace / "a.txt").read_text(), "new")
        staged = list(self.workspace.glob(".cortex-*.tmp"))
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0].read_text(), "previous")
        self.assertEqual([r["state"] for r in store.effect_rows()], ["outcome_unclear"])
        recovered = self.recover_write(store.effect_rows()[0])
        self.assertEqual(recovered.state, "succeeded")
        self.assertEqual((self.workspace / "a.txt").read_text(), "new")
        self.assertEqual(staged[0].read_text(), "previous")

    async def test_write_recovery_requires_inode_not_just_matching_bytes(self):
        _, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        target = self.workspace / "a.txt"
        target.rename(self.workspace / "original-inode")
        target.write_text("new")
        recovered = self.recover_write(store.effect_rows()[0])
        self.assertEqual(recovered.state, "outcome_unclear")
        self.assertEqual(target.read_text(), "new")
        self.assertEqual((self.workspace / "original-inode").read_text(), "new")

    async def test_write_recovery_of_unpublished_create_never_publishes_it(self):
        with patch.object(fd_ops, "rename_exclusive_at", side_effect=OSError("fixture before publish")):
            _, store, _ = await self.directory_mission(complete=False, operation="write_file", arguments={"path":"a.txt", "content":"new"})
        recovered = self.recover_write(store.effect_rows()[0])
        self.assertEqual(recovered.state, "failed")
        self.assertFalse((self.workspace / "a.txt").exists())
        self.assertEqual(len(list(self.workspace.glob(".cortex-*.tmp"))), 1)

    async def test_write_recovery_refuses_replaced_parent_and_missing_evidence(self):
        _, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        row = dict(store.effect_rows()[0])
        ownership = json.loads(row["ownership_json"])
        for altered in ({**ownership, "parentInode": ownership["parentInode"] + 1},
                        {key: value for key, value in ownership.items() if key != "prepared"}):
            recovered = self.recover_write({**row, "ownership_json": json.dumps(altered)})
            self.assertEqual(recovered.state, "outcome_unclear")
        self.assertEqual((self.workspace / "a.txt").read_text(), "new")

    async def test_write_recovery_refuses_symlink_and_does_not_modify_external_file(self):
        _, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        target = self.workspace / "a.txt"
        outside = self.root / "outside"
        target.rename(outside)
        target.symlink_to(outside)
        recovered = self.recover_write(store.effect_rows()[0])
        self.assertEqual(recovered.state, "outcome_unclear")
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_text(), "new")

    async def test_write_recovery_requires_retained_original_for_replacement(self):
        (self.workspace / "a.txt").write_text("previous")
        _, store, _ = await self.directory_mission(operation="write_file", arguments={"path":"a.txt", "content":"new"})
        row = store.effect_rows()[0]
        self.assertEqual(self.recover_write(row).state, "succeeded")
        previous = next(self.workspace.glob(".cortex-*.previous"))
        previous.rename(self.workspace / "old-inode")
        previous.write_text("previous")
        self.assertEqual(self.recover_write(row).state, "outcome_unclear")
        self.assertEqual((self.workspace / "a.txt").read_text(), "new")
        self.assertEqual((self.workspace / "old-inode").read_text(), "previous")
