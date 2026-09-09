"""Managed installed-server handoff; storage authorization is supplied under lock."""
import asyncio
import fcntl
import json
import os
import pwd
from pathlib import Path
import socket
import signal
import stat
import subprocess
import sys
import threading
import time
from uuid import UUID

from generation_metadata import GenerationMetadata, verify_generation_metadata
from lifecycle_lock import open_lifecycle_lock, ensure_private_directory
from startup_lease import (
    StartupLeaseError, ManagedStartReceipt, _read_kernel_process_identity,
    _safe_boot_identity, _send_json, _recv_json, _duplicate_key_rejector,
    publish_startup_lease, parent_release_and_wait_ack, child_consume_startup_lease,
    write_runtime_lifespan_record, _require_managed_start_context,
)


def _read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid()
                or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1 or s.st_size > 16 * 1024 * 1024):
            raise StartupLeaseError("STARTUP_GENERATION_UNSAFE")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(16 * 1024 * 1024 + 1)
        if len(data) != s.st_size:
            raise StartupLeaseError("STARTUP_GENERATION_CHANGED")
        return data
    finally:
        os.close(fd)


def launch(home, *, lock_set, lifecycle, contract, timeout_seconds=5.0, child_owner=None):
    home = Path(home)
    if type(timeout_seconds) not in (float, int) or not 0 < timeout_seconds <= 30:
        raise StartupLeaseError("STARTUP_TIMEOUT_INVALID")
    lock_set.assert_active(home=home, required_install_mode="shared", required_storage_mode="shared")
    if lock_set.install_mode != "shared" or lock_set.storage_mode != "shared":
        raise StartupLeaseError("STARTUP_REQUIRES_SHARED_LOCKS")
    status = contract.probe_locked(lock_set)
    observed = lifecycle.status_locked(lock_set)
    if (status.verdict != "PASS" or status.runtime_allowed is not True
            or observed.verdict != "PASS" or observed.runtime_allowed is not True
            or observed.transaction_id != status.transaction_id):
        raise StartupLeaseError("STARTUP_STORAGE_NOT_READY")
    selector_bytes = _read_private(home / "current-generation.json")
    selector = json.loads(selector_bytes, object_pairs_hook=_duplicate_key_rejector)
    generation_id = UUID(selector["generation_id"])
    generation = home / "installed-generations" / str(generation_id)
    # Full native signatures, interpreter identity/hash and app-tree validation.
    metadata = GenerationMetadata(generation_id, _read_private(generation / "owned-manifest.json"),
                                  _read_private(generation / "generation-record.json"), selector_bytes)
    verify_generation_metadata(generation, metadata)
    app = generation / "app"
    pids = home / "pids"
    ensure_private_directory(pids)
    descriptors = []
    left, right = socket.socketpair()
    process = None
    try:
        # Independent open descriptions: closing the caller's lock set must not
        # unlock the child's lifetime locks. Admission stays with the caller.
        for name in (".install.lock", "storage-state.lock"):
            fd = open_lifecycle_lock(home / name, deadline=time.monotonic() + timeout_seconds)
            descriptors.append(fd)
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        pids_fd = os.open(pids, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(pids_fd)
        environment = {"PATH": os.defpath, "HOME": os.environ.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir,
                       "CORTEX_HOME": str(home),
                       "LANG": "C", "LC_ALL": "C", "PORT": os.environ.get("PORT", "8420")}
        for name in ("CORTEX_STORAGE_BOOTSTRAP", "CORTEX_STORAGE_REQUIRED_MARKER",
                     "CORTEX_STORAGE_HOST", "CORTEX_STORAGE_IMAGE", "CORTEX_STORAGE_MOUNT", "CORTEX_STORAGE_ROOT"):
            if name in os.environ:
                environment[name] = os.environ[name]
        program = "import sys; sys.path.insert(0,sys.argv[1]); from managed_runtime import child_main; child_main()"
        process = subprocess.Popen([str(app / "bin/python"), "-I", "-S", "-B", "-c", program,
                                    str(app / "python"), str(right.fileno()), str(pids_fd),
                                    status.transaction_id or "", selector["generation_record_sha256"],
                                    str(descriptors[0]), str(descriptors[1])],
                                   env=environment, cwd=home, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, pass_fds=(*descriptors, right.fileno()))
        right.close()
        identity = _read_kernel_process_identity(process.pid)
        if identity is None:
            raise StartupLeaseError("STARTUP_CHILD_IDENTITY_UNAVAILABLE")
        deadline = time.monotonic() + timeout_seconds
        lease = publish_startup_lease(pids_fd=pids_fd, identity=identity,
                                      storage_transaction_id=status.transaction_id, boot=_safe_boot_identity(),
                                      generation_record_sha256=selector["generation_record_sha256"],
                                      ttl_seconds=timeout_seconds)
        parent_release_and_wait_ack(left.fileno(), lease, timeout_seconds=timeout_seconds)
        ready = _recv_json(left, max(0.001, deadline - time.monotonic()))
        if ready != {"type": "READY", "lease_id": lease.lease_id}:
            raise StartupLeaseError("STARTUP_RUNTIME_NOT_READY")
        _require_managed_start_context(home, status)
        receipt = ManagedStartReceipt(lease.lease_id, process.pid, status.transaction_id, True)
        if child_owner is None:
            threading.Thread(target=process.wait, daemon=True).start()
        else:
            child_owner(process)
        process = None
        return receipt
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        left.close()
        right.close()
        for fd in reversed(descriptors):
            os.close(fd)  # No LOCK_UN: the child inherited these descriptions.


def child_main():
    _, _, control, pids, transaction, generation_digest, install_fd, storage_fd = sys.argv
    channel = socket.socket(fileno=int(control))
    context = child_consume_startup_lease(control_fd=channel.fileno(), pids_fd=int(pids),
                                         expected_transaction_id=transaction or None)
    if context.generation_record_sha256 != generation_digest:
        raise StartupLeaseError("STARTUP_GENERATION_MISMATCH")
    home = Path(os.environ["CORTEX_HOME"])
    current = write_runtime_lifespan_record(home, context=context, state="STARTING")
    import server
    import uvicorn

    class ManagedServer(uvicorn.Server):
        async def startup(self, sockets=None):
            nonlocal current
            await super().startup(sockets=sockets)
            if not self.started:
                raise StartupLeaseError("STARTUP_HTTP_NOT_READY")
            current = write_runtime_lifespan_record(home, context=context, state="READY",
                                                   previous_record_sha256=current.record_sha256)
            _send_json(channel, {"type": "READY", "lease_id": context.lease_id})

    try:
        # Uvicorn re-raises handled signals after shutdown. Retain control long
        # enough to durably close the lifespan record before this process exits.
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: None)
        asyncio.run(ManagedServer(uvicorn.Config(server.app, host="127.0.0.1",
                                                port=int(os.environ["PORT"]), log_level="warning")).serve())
    finally:
        if current.state == "READY":
            write_runtime_lifespan_record(home, context=context, state="CLOSED",
                                         previous_record_sha256=current.record_sha256)
        channel.close()
        for fd in (int(pids), int(install_fd), int(storage_fd)):
            os.close(fd)
