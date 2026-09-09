# Workspace volume identity propagation

WorkspaceHandle now rejects admission when descriptor observations omit the
expected APFS volume identity or disagree with it. Revalidation compares the
observed UUID as well as device, filesystem ID and workspace inode. Production
ToolExecutor operations already invoke this revalidation; a new read test
verifies rejection after a synthetic volume change rather than returning data.

## Evidence

RED: four workspace tests produced three failing subcases: missing UUID,
different UUID at admission, and changed UUID with unchanged device/fsid.
GREEN: 118 tests PASS in 44.595 seconds:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_workspace_handle test_storage_contract test_executor_handle_reads test_executor_fd_ops test_signed_native_helper -q
```

Asyncio emitted slow-task diagnostics during native supervision tests; the
suite exited 0. These diagnostics were not treated as latency acceptance.
After adding the production read-denial test, 66 tests PASS in 0.283 seconds:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_workspace_handle test_storage_contract test_executor_handle_reads test_executor_fd_ops -q
```

Existing synthetic mount fixtures now explicitly supply their matching fixture
identity. Filesystem operations and retained FDs are real; fixture UUIDs are not
evidence of an encrypted image. UUID syntax remains checked by the native
reader/StorageContract; WorkspaceHandle enforces equality at its verified-input
boundary. Native process tests do not prove a live ChatGPT mission.

## Open gates

Host and encryption identity still require journal/private broker proof;
committed transition status is not sufficient. Native effects, terminal ACK,
recovery, complete installation and 0.6 product acceptance remain incomplete.
No user installation, image or Keychain change; no commit or push.
