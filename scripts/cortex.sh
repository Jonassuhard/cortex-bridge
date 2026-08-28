#!/usr/bin/env bash
# Ownership-safe lifecycle for the local Cortex Bridge console.
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8420}"
RAW_CORTEX_HOME="${CORTEX_HOME:-$HOME/.local/share/cortex-bridge}"
case "$RAW_CORTEX_HOME" in
  /*) ;;
  *) echo "CORTEX_HOME must be absolute" >&2; exit 2 ;;
esac
case "${PYTHONPATH:-}" in
  "$ROOT/console:$ROOT"|"$ROOT/console:$ROOT:"*) ;;
  *) export PYTHONPATH="$ROOT/console:$ROOT${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

if [ -n "${PYTHON_BIN:-}" ]; then
  VALIDATION_PYTHON="$PYTHON_BIN"
elif [ -x /usr/bin/python3 ]; then
  VALIDATION_PYTHON=/usr/bin/python3
else
  VALIDATION_PYTHON=python3
fi

_prepare_private_runtime_tree() {
  exec "$VALIDATION_PYTHON" -c '
import fcntl
import os
import stat
import sys
from pathlib import Path

from lifecycle_lock import open_lifecycle_lock

raw_home = Path(sys.argv[1])
canonical_home = Path(sys.argv[2])
launcher = sys.argv[3]
launcher_args = sys.argv[4:]
if (
    not raw_home.is_absolute()
    or not canonical_home.is_absolute()
    or ".." in raw_home.parts
    or ".." in canonical_home.parts
):
    print("CORTEX_RUNTIME_TREE_UNSAFE: invalid runtime path", file=sys.stderr)
    raise SystemExit(2)

try:
    raw_details = os.lstat(raw_home)
except FileNotFoundError:
    raw_details = None
except OSError as error:
    print(f"CORTEX_RUNTIME_TREE_UNSAFE: {error}", file=sys.stderr)
    raise SystemExit(2)
if raw_details is not None and stat.S_ISLNK(raw_details.st_mode):
    print("CORTEX_RUNTIME_TREE_UNSAFE: CORTEX_HOME must not be a symlink", file=sys.stderr)
    raise SystemExit(2)

directory_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
descriptor = None
runtime_descriptors = []
try:
    descriptor = os.open(canonical_home.anchor, directory_flags)
    parts = canonical_home.parts[1:]
    if not parts:
        raise RuntimeError("CORTEX_HOME must be a dedicated directory")
    for position, part in enumerate(parts):
        try:
            child = os.open(part, directory_flags, dir_fd=descriptor)
        except FileNotFoundError:
            os.mkdir(part, 0o700, dir_fd=descriptor)
            child = os.open(part, directory_flags, dir_fd=descriptor)
        os.close(descriptor)
        descriptor = child
        if position == len(parts) - 1:
            details = os.fstat(descriptor)
            if not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid():
                raise RuntimeError("CORTEX_HOME is not an owned real directory")
            os.fchmod(descriptor, 0o700)

    home_details = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(home_details.st_mode)
        or home_details.st_uid != os.getuid()
    ):
        raise RuntimeError("CORTEX_HOME is not an owned real directory")
    runtime_descriptors.append(descriptor)
    for name in ("logs", "pids"):
        try:
            child = os.open(name, directory_flags, dir_fd=descriptor)
        except FileNotFoundError:
            os.mkdir(name, 0o700, dir_fd=descriptor)
            child = os.open(name, directory_flags, dir_fd=descriptor)
        try:
            details = os.fstat(child)
            if (
                not stat.S_ISDIR(details.st_mode)
                or details.st_uid != os.getuid()
                or details.st_dev != home_details.st_dev
            ):
                raise RuntimeError(f"{name} is not an owned real directory")
            os.fchmod(child, 0o700)
            runtime_descriptors.append(child)
        except Exception:
            os.close(child)
            raise

    lock_fd = None
    environment = os.environ.copy()
    if environment.get("CORTEX_START_INSTALL_LOCK_HELD") != "1":
        lock_fd = open_lifecycle_lock(canonical_home / ".install.lock")
        fcntl.flock(lock_fd, fcntl.LOCK_SH)
        runtime_descriptors.append(lock_fd)
        environment["CORTEX_START_INSTALL_LOCK_HELD"] = "1"

    for item in runtime_descriptors:
        os.set_inheritable(item, True)
    environment["CORTEX_RUNTIME_TREE_READY"] = "1"
    environment["CORTEX_HOME_FD"] = str(descriptor)
    environment["CORTEX_LOGS_FD"] = str(runtime_descriptors[1])
    environment["CORTEX_PIDS_FD"] = str(runtime_descriptors[2])
    os.execvpe("bash", ["bash", launcher, *launcher_args], environment)
except (OSError, RuntimeError) as error:
    print(f"CORTEX_RUNTIME_TREE_UNSAFE: {error}", file=sys.stderr)
    raise SystemExit(2)
finally:
    for item in reversed(runtime_descriptors):
        try:
            os.close(item)
        except OSError:
            pass
' "$@"
}

if ! CORTEX_HOME="$(
  CORTEX_HOME="$RAW_CORTEX_HOME" "$VALIDATION_PYTHON" -c '
import sys
from cortex_paths import build_paths

try:
    print(build_paths().home)
except (OSError, ValueError) as error:
    print(f"CORTEX_HOME_INVALID: {error}", file=sys.stderr)
    raise SystemExit(2)
'
)"; then
  exit 2
fi
if [ -z "$CORTEX_HOME" ]; then
  echo "CORTEX_HOME_INVALID: canonical path is empty" >&2
  exit 2
fi
if [ "${1:-help}" = "start" ] && [ "${CORTEX_RUNTIME_TREE_READY:-}" != "1" ]; then
  _prepare_private_runtime_tree \
    "$RAW_CORTEX_HOME" "$CORTEX_HOME" "$ROOT/scripts/cortex.sh" "$@"
fi
export CORTEX_HOME
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$CORTEX_HOME/browser-cache}"

if [ -n "${PYTHON_BIN:-}" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -x "$CORTEX_HOME/venv/bin/python" ]; then
  PYTHON="$CORTEX_HOME/venv/bin/python"
else
  PYTHON="python3"
fi

PIDS_DIR="$CORTEX_HOME/pids"
LOGS_DIR="$CORTEX_HOME/logs"
PID_RECORD="$PIDS_DIR/console.json"
LOG_FILE="${CORTEX_LOG:-$LOGS_DIR/console.log}"
LOG_ARCHIVE_DIR="${CORTEX_LOG_ARCHIVE_DIR:-}"
VALIDATED_STORAGE_ROOT=""
OWNERSHIP="$ROOT/console/process_ownership.py"
STORAGE_GUARD="$ROOT/scripts/check-cortex-storage.py"
STORAGE_BOOTSTRAP="${CORTEX_STORAGE_BOOTSTRAP:-$CORTEX_HOME/storage-bootstrap.json}"
STORAGE_REQUIRED_MARKER="${CORTEX_STORAGE_REQUIRED_MARKER:-$CORTEX_HOME/storage-required}"
COMMAND="${1:-help}"
OUTPUT_MODE="${2:-}"

_start_lock_acquire() {
  "$PYTHON" -c '
import os
import stat
import sys

parent_fd = int(sys.argv[1])
name = "start.lock"
parent = os.fstat(parent_fd)
try:
    os.mkdir(name, 0o700, dir_fd=parent_fd)
except FileExistsError:
    raise SystemExit(1)
descriptor = None
try:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    details = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_dev != parent.st_dev
    ):
        raise RuntimeError("start lock is unsafe")
    os.fchmod(descriptor, 0o700)
except (OSError, RuntimeError):
    try:
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        pass
    raise SystemExit(2)
finally:
    if descriptor is not None:
        os.close(descriptor)
' "${CORTEX_PIDS_FD:?}"
}

_start_lock_release() {
  "$PYTHON" -c '
import os
import sys

try:
    os.rmdir("start.lock", dir_fd=int(sys.argv[1]))
except OSError:
    pass
' "${CORTEX_PIDS_FD:?}" >/dev/null 2>&1 || true
}

_launch_private_server() {
  local instance_token="$1"
  "$PYTHON" -c '
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path

(
    raw_logs_fd,
    raw_pids_fd,
    raw_logs,
    raw_log,
    python,
    console,
    home,
    port,
    token,
) = sys.argv[1:]
logs_fd = int(raw_logs_fd)
pids_fd = int(raw_pids_fd)
directory_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
logs_details = os.fstat(logs_fd)
pids_details = os.fstat(pids_fd)
if any(
    not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
    for details in (logs_details, pids_details)
):
    raise SystemExit(2)


def ps_value_until(pid, field_name, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(["ps"], 0)
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", f"{field_name}="],
        capture_output=True,
        text=True,
        check=False,
        timeout=remaining,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ProcessLookupError(pid)
    return result.stdout.strip()


def capture_identity_until(pid, raw_port, instance_token, deadline):
    command = ps_value_until(pid, "command", deadline)
    return {
        "pid": int(pid),
        "start_time": ps_value_until(pid, "lstart", deadline),
        "executable": ps_value_until(pid, "comm", deadline),
        "argv_hash": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "instance_token": instance_token,
        "port": int(raw_port),
    }


def terminate_and_reap(child):
    if child is None or child.poll() is not None:
        return
    # poll() is waitpid() on this direct child. While it is None, the Popen
    # still owns the unreaped PID, so it cannot have been recycled.
    try:
        child.terminate()
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)


path = Path(raw_log)
root = Path(raw_logs)
try:
    relative = path.relative_to(root)
except ValueError:
    raise SystemExit(2)
if not relative.parts or ".." in path.parts:
    raise SystemExit(2)
parent_fd = os.dup(logs_fd)
process = None
published_launch = None
try:
    for component in relative.parts[:-1]:
        child = os.open(component, directory_flags, dir_fd=parent_fd)
        details = os.fstat(child)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_dev != logs_details.st_dev
        ):
            os.close(child)
            raise RuntimeError("log parent is unsafe")
        os.fchmod(child, 0o700)
        os.close(parent_fd)
        parent_fd = child
    log_fd = os.open(
        relative.parts[-1],
        os.O_WRONLY
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=parent_fd,
    )
    details = os.fstat(log_fd)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_dev != logs_details.st_dev
    ):
        raise RuntimeError("log file is unsafe")
    os.fchmod(log_fd, 0o600)
    environment = os.environ.copy()
    environment.update(
        CORTEX_HOME=home,
        PORT=port,
        CORTEX_INSTANCE_TOKEN=token,
    )
    process = subprocess.Popen(
        [python, "server.py"],
        cwd=console,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    previous = None
    record = None
    identity_deadline = time.monotonic() + 1.0
    while time.monotonic() < identity_deadline:
        if process.poll() is not None:
            raise RuntimeError("launched process exited before identity capture")
        try:
            current = capture_identity_until(process.pid, port, token, identity_deadline)
        except (OSError, ProcessLookupError, subprocess.SubprocessError):
            current = None
        if current is not None and current == previous:
            record = current
            break
        previous = current
        remaining = identity_deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.02, remaining))
    if record is None:
        raise RuntimeError("launched process identity did not stabilize")
    payload = json.dumps(record, sort_keys=True).encode("utf-8")
    temporary = f".launch.pid.{os.getpid()}.{secrets.token_hex(8)}"
    launch_fd = None
    try:
        launch_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=pids_fd,
        )
        launch_details = os.fstat(launch_fd)
        if (
            not stat.S_ISREG(launch_details.st_mode)
            or launch_details.st_uid != os.getuid()
            or launch_details.st_dev != pids_details.st_dev
        ):
            raise RuntimeError("launch pid record is unsafe")
        os.write(launch_fd, payload)
        os.fchmod(launch_fd, 0o600)
        os.fsync(launch_fd)
        os.replace(temporary, "launch.pid", src_dir_fd=pids_fd, dst_dir_fd=pids_fd)
        temporary = ""
        published_launch = (launch_details.st_dev, launch_details.st_ino)
        installed = os.stat("launch.pid", dir_fd=pids_fd, follow_symlinks=False)
        if (installed.st_dev, installed.st_ino) != published_launch:
            raise RuntimeError("launch identity record changed during publication")
        os.fsync(pids_fd)
    finally:
        if launch_fd is not None:
            os.close(launch_fd)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=pids_fd)
            except OSError:
                pass
    print(json.dumps({
        **record,
        "launch_record_dev": launch_details.st_dev,
        "launch_record_ino": launch_details.st_ino,
        "launch_record_sha256": hashlib.sha256(payload).hexdigest(),
    }, sort_keys=True))
except BaseException as error:
    terminate_and_reap(process)
    if published_launch is not None:
        try:
            installed = os.stat("launch.pid", dir_fd=pids_fd, follow_symlinks=False)
            if (installed.st_dev, installed.st_ino) == published_launch:
                os.unlink("launch.pid", dir_fd=pids_fd)
                os.fsync(pids_fd)
        except OSError:
            pass
    if isinstance(error, (OSError, RuntimeError, subprocess.SubprocessError)):
        raise SystemExit(2)
    raise
finally:
    try:
        os.close(log_fd)
    except (NameError, OSError):
        pass
    os.close(parent_fd)
' \
    "${CORTEX_LOGS_FD:?}" "${CORTEX_PIDS_FD:?}" "$LOGS_DIR" "$LOG_FILE" \
    "$PYTHON" "$ROOT/console" "$CORTEX_HOME" "$PORT" "$instance_token"
}

_capture_private_ownership_record() {
  local launch_state="$1"
  "$PYTHON" -c '
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys

from process_ownership import capture_identity

parent_fd = int(sys.argv[1])
try:
    expected = json.loads(sys.argv[2])
except (json.JSONDecodeError, TypeError):
    raise SystemExit(2)
identity_fields = {
    "pid",
    "start_time",
    "executable",
    "argv_hash",
    "instance_token",
    "port",
}
metadata_fields = {
    "launch_record_dev",
    "launch_record_ino",
    "launch_record_sha256",
}
if (
    not isinstance(expected, dict)
    or set(expected) != identity_fields | metadata_fields
    or not isinstance(expected.get("pid"), int)
    or expected["pid"] <= 0
    or not isinstance(expected.get("port"), int)
    or not 0 < expected["port"] < 65536
    or not all(isinstance(expected.get(name), str) and expected[name] for name in identity_fields - {"pid", "port"})
    or not isinstance(expected.get("launch_record_dev"), int)
    or not isinstance(expected.get("launch_record_ino"), int)
    or not isinstance(expected.get("launch_record_sha256"), str)
):
    raise SystemExit(2)
parent = os.fstat(parent_fd)
if (
    not stat.S_ISDIR(parent.st_mode)
    or parent.st_uid != os.getuid()
    or parent.st_dev != expected["launch_record_dev"]
):
    raise SystemExit(2)
record = {name: expected[name] for name in identity_fields}
payload = json.dumps(record, sort_keys=True).encode("utf-8")
if hashlib.sha256(payload).hexdigest() != expected["launch_record_sha256"]:
    raise SystemExit(2)
launch_fd = None
descriptor = None
temporary = ""
try:
    launch_fd = os.open(
        "launch.pid",
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
        dir_fd=parent_fd,
    )
    launch_details = os.fstat(launch_fd)
    if (
        not stat.S_ISREG(launch_details.st_mode)
        or launch_details.st_uid != os.getuid()
        or launch_details.st_dev != parent.st_dev
        or launch_details.st_dev != expected["launch_record_dev"]
        or launch_details.st_ino != expected["launch_record_ino"]
        or os.read(launch_fd, len(payload) + 1) != payload
    ):
        raise RuntimeError("launch identity record is unsafe")
    current = capture_identity(expected["pid"], expected["port"], expected["instance_token"])
    for name in ("pid", "start_time", "executable", "argv_hash", "port"):
        if current[name] != expected[name]:
            raise RuntimeError("launched process identity changed")
    temporary = f".console.json.{os.getpid()}.{secrets.token_hex(8)}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
        dir_fd=parent_fd,
    )
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_dev != parent.st_dev
    ):
        raise RuntimeError("ownership record is unsafe")
    os.write(descriptor, payload)
    os.fchmod(descriptor, 0o600)
    os.fsync(descriptor)
    os.replace(temporary, "console.json", src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    temporary = ""
    os.lseek(launch_fd, 0, os.SEEK_SET)
    launch_details = os.fstat(launch_fd)
    if (
        not stat.S_ISREG(launch_details.st_mode)
        or launch_details.st_uid != os.getuid()
        or launch_details.st_dev != expected["launch_record_dev"]
        or launch_details.st_ino != expected["launch_record_ino"]
        or os.read(launch_fd, len(payload) + 1) != payload
    ):
        raise RuntimeError("launch identity record changed before deletion")
    installed = os.stat("launch.pid", dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(installed.st_mode)
        or installed.st_uid != os.getuid()
        or installed.st_dev != launch_details.st_dev
        or installed.st_ino != launch_details.st_ino
    ):
        raise RuntimeError("launch identity record changed before deletion")
    os.unlink("launch.pid", dir_fd=parent_fd)
    os.fsync(parent_fd)
except (OSError, RuntimeError, subprocess.SubprocessError):
    raise SystemExit(2)
finally:
    if descriptor is not None:
        os.close(descriptor)
    if launch_fd is not None:
        os.close(launch_fd)
    if temporary:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except OSError:
            pass
' "${CORTEX_PIDS_FD:?}" "$launch_state"
}

_abort_unverified_start() {
  local launch_state="$1"
  "$PYTHON" -c '
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time

from process_ownership import capture_identity

parent_fd = int(sys.argv[1])
try:
    expected = json.loads(sys.argv[2])
except (json.JSONDecodeError, TypeError):
    raise SystemExit(2)
identity_fields = {
    "pid",
    "start_time",
    "executable",
    "argv_hash",
    "instance_token",
    "port",
}
metadata_fields = {
    "launch_record_dev",
    "launch_record_ino",
    "launch_record_sha256",
}
if (
    not isinstance(expected, dict)
    or set(expected) != identity_fields | metadata_fields
    or not isinstance(expected.get("pid"), int)
    or expected["pid"] <= 0
    or not isinstance(expected.get("port"), int)
    or not 0 < expected["port"] < 65536
    or not all(isinstance(expected.get(name), str) and expected[name] for name in identity_fields - {"pid", "port"})
    or not isinstance(expected.get("launch_record_dev"), int)
    or not isinstance(expected.get("launch_record_ino"), int)
    or not isinstance(expected.get("launch_record_sha256"), str)
):
    raise SystemExit(2)
parent = os.fstat(parent_fd)
if (
    not stat.S_ISDIR(parent.st_mode)
    or parent.st_uid != os.getuid()
    or parent.st_dev != expected["launch_record_dev"]
):
    raise SystemExit(2)
record = {name: expected[name] for name in identity_fields}
payload = json.dumps(record, sort_keys=True).encode("utf-8")
if hashlib.sha256(payload).hexdigest() != expected["launch_record_sha256"]:
    raise SystemExit(2)


def process_state():
    try:
        current = capture_identity(
            expected["pid"], expected["port"], expected["instance_token"]
        )
    except ProcessLookupError:
        return "gone"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    for name in ("pid", "start_time", "executable", "argv_hash", "port"):
        if current[name] != expected[name]:
            return "mismatch"
    return "match"


def signal_exact(sig):
    if process_state() != "match":
        return False
    try:
        os.kill(expected["pid"], sig)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return True


def wait_until_gone(timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = process_state()
        if state == "gone":
            return True
        if state != "match":
            return False
        time.sleep(0.05)
    return process_state() == "gone"


state = process_state()
gone = state == "gone"
if state == "match" and signal_exact(signal.SIGTERM):
    gone = wait_until_gone(5)
    if not gone and signal_exact(signal.SIGKILL):
        gone = wait_until_gone(5)

if gone:
    descriptor = None
    try:
        descriptor = os.open(
            "launch.pid",
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_dev != parent.st_dev
            or details.st_dev != expected["launch_record_dev"]
            or details.st_ino != expected["launch_record_ino"]
            or os.read(descriptor, len(payload) + 1) != payload
        ):
            raise RuntimeError("launch identity record is unsafe")
        installed = os.stat("launch.pid", dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(installed.st_mode)
            or installed.st_uid != os.getuid()
            or installed.st_dev != details.st_dev
            or installed.st_ino != details.st_ino
        ):
            raise RuntimeError("launch identity record changed before deletion")
        os.unlink("launch.pid", dir_fd=parent_fd)
        os.fsync(parent_fd)
    except (OSError, RuntimeError):
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
' "${CORTEX_PIDS_FD:?}" "$launch_state"
}

_ownership_status() {
  "$PYTHON" "$OWNERSHIP" status \
    --record "$PID_RECORD" --port "$PORT"
}

_json_field() {
  local payload="$1" field="$2"
  "$PYTHON" -c 'import json,sys; value=json.loads(sys.argv[1]).get(sys.argv[2]); print("" if value is None else value)' "$payload" "$field"
}

_port_pid() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true
}

_external_storage_configured() {
  [ -n "${CORTEX_STORAGE_BOOTSTRAP:-}" ] \
    || [ -n "${CORTEX_STORAGE_REQUIRED_MARKER:-}" ] \
    || [ -e "$STORAGE_REQUIRED_MARKER" ] \
    || [ -L "$STORAGE_REQUIRED_MARKER" ] \
    || [ -e "$STORAGE_BOOTSTRAP" ] \
    || [ -L "$STORAGE_BOOTSTRAP" ]
}

_check_external_storage() {
  local verified storage_root status

  if ! _external_storage_configured; then
    return 0
  fi
  if verified="$(
    "$PYTHON" "$STORAGE_GUARD" --bootstrap "$STORAGE_BOOTSTRAP" --json
  )"; then
    :
  else
    status=$?
    return "$status"
  fi
  if storage_root="$("$PYTHON" -c '
import json
import sys

try:
    document = json.loads(sys.argv[1])
    storage_root = document["storage_root"]
except (KeyError, json.JSONDecodeError, TypeError) as error:
    print(f"STORAGE_GUARD_OUTPUT_INVALID: {error}", file=sys.stderr)
    raise SystemExit(2)
if (
    document.get("status") != "ready"
    or not isinstance(storage_root, str)
    or not storage_root
):
    print("STORAGE_GUARD_OUTPUT_INVALID: verified storage_root is missing", file=sys.stderr)
    raise SystemExit(2)
print(storage_root)
' "$verified")"; then
    :
  else
    status=$?
    return "$status"
  fi
  printf '%s\n' "$storage_root"
}

_rotate_log_before_start() {
  local max_bytes="${CORTEX_LOG_MAX_BYTES:-10485760}"
  local backup_count="${CORTEX_LOG_BACKUPS:-3}"
  local allowed_archive_root archive_prefix external_archive

  if [ -n "$VALIDATED_STORAGE_ROOT" ]; then
    allowed_archive_root="$VALIDATED_STORAGE_ROOT"
    archive_prefix="99_QUARANTINE/logs"
    external_archive=1
  else
    allowed_archive_root="$LOGS_DIR"
    archive_prefix="archive"
    external_archive=0
  fi
  case "$max_bytes" in
    ''|*[!0-9]*)
      echo "CORTEX_LOG_MAX_BYTES must be an integer between 1048576 and 1073741824." >&2
      return 2
      ;;
  esac
  if [ "${#max_bytes}" -gt 10 ] \
    || [ "$max_bytes" -lt 1048576 ] \
    || [ "$max_bytes" -gt 1073741824 ]; then
    echo "CORTEX_LOG_MAX_BYTES must be an integer between 1048576 and 1073741824." >&2
    return 2
  fi
  case "$backup_count" in
    [1-9]|10) ;;
    *)
      echo "CORTEX_LOG_BACKUPS must be an integer between 1 and 10." >&2
      return 2
      ;;
  esac
  "$PYTHON" -c '
# CORTEX_SAFE_ARCHIVE_COPY: every mutation is relative to a pinned directory FD.
import datetime
import os
import secrets
import stat
import sys
from pathlib import Path

(
    raw_logs_fd,
    raw_logs,
    raw_log,
    raw_allowed,
    raw_prefix,
    raw_archive,
    raw_max_bytes,
    raw_backup_count,
    raw_external,
) = sys.argv[1:]
logs_fd = int(raw_logs_fd)
max_bytes = int(raw_max_bytes)
backup_count = int(raw_backup_count)
external = raw_external == "1"
directory_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


class UnsafeSymlink(RuntimeError):
    pass


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(2)


def relative_parts(path_text, root_text, label):
    def normalize(value):
        candidate = Path(value)
        for alias, canonical in (
            (Path("/var"), Path("/private/var")),
            (Path("/tmp"), Path("/private/tmp")),
        ):
            try:
                return canonical / candidate.relative_to(alias)
            except ValueError:
                pass
        return candidate

    path = normalize(path_text)
    root = normalize(root_text)
    if not path.is_absolute() or ".." in path.parts:
        fail(label)
    try:
        relative = path.relative_to(root)
    except ValueError:
        fail(label)
    if not relative.parts:
        fail(label)
    return relative.parts


def open_child_directory(parent_fd, name, expected_device, *, create=False, final=False):
    created = False
    observed = None
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    if observed is not None and stat.S_ISLNK(observed.st_mode):
        raise UnsafeSymlink(name)
    try:
        child = os.open(name, directory_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created = True
        child = os.open(name, directory_flags, dir_fd=parent_fd)
    details = os.fstat(child)
    unsafe_mode = details.st_mode & (0o077 if final else 0o022)
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_dev != expected_device
        or (
            observed is not None
            and (details.st_dev, details.st_ino) != (observed.st_dev, observed.st_ino)
        )
        or (not created and unsafe_mode)
    ):
        os.close(child)
        raise RuntimeError("directory is unsafe")
    if created:
        os.fchmod(child, 0o700)
    return child, details


def open_regular(parent_fd, name, expected_device):
    descriptor = os.open(name, file_flags, dir_fd=parent_fd)
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or details.st_uid != os.getuid()
        or details.st_dev != expected_device
    ):
        os.close(descriptor)
        raise RuntimeError("unsafe log backup")
    return descriptor, details


logs_details = os.fstat(logs_fd)
if (
    not stat.S_ISDIR(logs_details.st_mode)
    or logs_details.st_uid != os.getuid()
):
    fail("CORTEX_RUNTIME_TREE_UNSAFE: logs changed")
log_parts = relative_parts(
    raw_log,
    raw_logs,
    f"CORTEX_LOG must stay inside {raw_logs} without traversal or symlinks.",
)
log_parent_fd = os.dup(logs_fd)
try:
    for component in log_parts[:-1]:
        child, _details = open_child_directory(
            log_parent_fd,
            component,
            logs_details.st_dev,
        )
        os.close(log_parent_fd)
        log_parent_fd = child
except UnsafeSymlink:
    os.close(log_parent_fd)
    fail(f"CORTEX_LOG must stay inside {raw_logs} without traversal or symlinks.")
except (OSError, RuntimeError):
    os.close(log_parent_fd)
    fail(f"CORTEX_LOG must stay inside {raw_logs} without traversal or symlinks.")
log_name = log_parts[-1]

allowed, target = Path(raw_allowed), Path(raw_archive)
archive_parts = relative_parts(
    raw_archive,
    raw_allowed,
    "CORTEX_LOG_ARCHIVE_DIR must stay under its dedicated archive root without traversal or symlinks.",
)
required_prefix = Path(raw_prefix).parts
if archive_parts[:len(required_prefix)] != required_prefix:
    os.close(log_parent_fd)
    fail("CORTEX_LOG_ARCHIVE_DIR must stay under its dedicated archive root without traversal or symlinks.")
try:
    if external:
        allowed_fd = os.open(allowed, directory_flags)
        allowed_details = os.fstat(allowed_fd)
        if (
            not stat.S_ISDIR(allowed_details.st_mode)
            or allowed_details.st_uid != os.getuid()
        ):
            raise RuntimeError("archive root is unsafe")
    else:
        allowed_fd = os.dup(logs_fd)
        allowed_details = logs_details
    archive_fd = allowed_fd
    for position, component in enumerate(archive_parts):
        child, _details = open_child_directory(
            archive_fd,
            component,
            allowed_details.st_dev,
            create=True,
            final=position == len(archive_parts) - 1,
        )
        os.close(archive_fd)
        archive_fd = child
except UnsafeSymlink:
    os.close(log_parent_fd)
    fail("CORTEX_LOG_ARCHIVE_DIR must stay under its dedicated archive root without traversal or symlinks.")
except (OSError, RuntimeError):
    os.close(log_parent_fd)
    fail("CORTEX_LOG_ARCHIVE_DIR is not a private owned directory.")
archive_details = os.fstat(archive_fd)


def identity(details):
    return (
        details.st_dev,
        details.st_ino,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def checked_names():
    numeric = []
    try:
        with os.scandir(log_parent_fd) as scanner:
            names = sorted(entry.name for entry in scanner)
        for name in names:
            prefix = f"{log_name}."
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            if not suffix.isdigit():
                continue
            descriptor, _details = open_regular(log_parent_fd, name, logs_details.st_dev)
            os.close(descriptor)
            numeric.append((int(suffix), name))
        try:
            descriptor, _details = open_regular(log_parent_fd, log_name, logs_details.st_dev)
        except FileNotFoundError:
            pass
        else:
            os.close(descriptor)
        return numeric
    except (OSError, RuntimeError):
        fail(f"Refusing unsafe log backup; preserved in place: {raw_log}")


def archive(source_name, suffix):
    source_fd = target_fd = None
    target_name = None
    target_entry = None
    expected = None
    retired = None
    archive_durable = False
    source_restored = False

    def entry_matches(parent_fd, name, expected_entry):
        try:
            details = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            return False
        return (
            stat.S_ISREG(details.st_mode)
            and (details.st_dev, details.st_ino) == expected_entry
        )

    def source_entry_matches(name):
        if expected is None:
            return False
        try:
            details = os.stat(name, dir_fd=log_parent_fd, follow_symlinks=False)
        except OSError:
            return False
        return (
            stat.S_ISREG(details.st_mode)
            and (
                details.st_dev,
                details.st_ino,
                details.st_size,
                details.st_mtime_ns,
            ) == expected[:4]
        )

    def source_matches():
        return source_entry_matches(source_name)

    def archive_matches():
        if (
            expected is None
            or target_fd is None
            or target_name is None
            or target_entry is None
            or not entry_matches(archive_fd, target_name, target_entry)
        ):
            return False
        try:
            details = os.fstat(target_fd)
        except OSError:
            return False
        return (
            stat.S_ISREG(details.st_mode)
            and (details.st_dev, details.st_ino) == target_entry
            and details.st_size == expected[2]
        )

    def restore_retired():
        if (
            retired is None
            or expected is None
            or not source_entry_matches(retired)
        ):
            return False
        try:
            os.stat(source_name, dir_fd=log_parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        else:
            return False
        try:
            os.rename(
                retired,
                source_name,
                src_dir_fd=log_parent_fd,
                dst_dir_fd=log_parent_fd,
            )
        except OSError:
            return False
        if not source_matches():
            return False
        try:
            os.fsync(log_parent_fd)
        except OSError:
            pass
        return True

    try:
        source_fd, before = open_regular(log_parent_fd, source_name, logs_details.st_dev)
        expected = identity(before)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = f"{log_name}.{stamp}.{os.getpid()}.{suffix}"
        target_name = base
        attempt = 0
        while True:
            try:
                os.stat(target_name, dir_fd=archive_fd, follow_symlinks=False)
            except FileNotFoundError:
                break
            attempt += 1
            target_name = f"{base}.{attempt}"
        target_fd = os.open(
            target_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=archive_fd,
        )
        target_details = os.fstat(target_fd)
        target_entry = (target_details.st_dev, target_details.st_ino)
        if (
            not stat.S_ISREG(target_details.st_mode)
            or target_details.st_dev != archive_details.st_dev
        ):
            raise RuntimeError("archive target is unsafe")
        os.fchmod(target_fd, 0o600)
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(target_fd, view)
                view = view[written:]
        os.fsync(target_fd)
        copied = os.fstat(target_fd)
        if (
            not stat.S_ISREG(copied.st_mode)
            or (copied.st_dev, copied.st_ino) != target_entry
            or copied.st_size != expected[2]
        ):
            raise RuntimeError("archive copy is incomplete")
        if identity(os.fstat(source_fd)) != expected:
            raise RuntimeError("source changed")
        current = os.stat(source_name, dir_fd=log_parent_fd, follow_symlinks=False)
        if identity(current) != expected:
            raise RuntimeError("source changed")
        os.fsync(archive_fd)
        archive_durable = True
        retired = f".{source_name}.archive-retired-{os.getpid()}-{secrets.token_hex(8)}"
        os.rename(
            source_name,
            retired,
            src_dir_fd=log_parent_fd,
            dst_dir_fd=log_parent_fd,
        )
        moved = os.stat(retired, dir_fd=log_parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(moved.st_mode)
            or (moved.st_dev, moved.st_ino) != expected[:2]
        ):
            source_restored = restore_retired()
            raise RuntimeError("source changed")
        try:
            os.fsync(log_parent_fd)
        except OSError:
            source_restored = restore_retired()
            raise
        moved = os.stat(retired, dir_fd=log_parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(moved.st_mode)
            or (moved.st_dev, moved.st_ino) != expected[:2]
        ):
            source_restored = restore_retired()
            raise RuntimeError("source changed")
        os.unlink(retired, dir_fd=log_parent_fd)
        os.fsync(log_parent_fd)
    except (OSError, RuntimeError):
        restored = source_restored and source_matches()
        if not restored:
            restored = restore_retired()
        if (
            not archive_durable
            and target_name is not None
            and target_entry is not None
            and entry_matches(archive_fd, target_name, target_entry)
        ):
            try:
                os.unlink(target_name, dir_fd=archive_fd)
                os.fsync(archive_fd)
            except OSError:
                pass
        archive_retained = archive_durable and archive_matches()
        if restored:
            fail(
                f"Refusing unsafe log backup; source restored in place: {source_name}; "
                f"archive copy retained: {target_name}"
            )
        if source_matches():
            if archive_retained:
                fail(
                    f"Refusing unsafe log backup; preserved in place: {source_name}; "
                    f"archive copy retained: {target_name}"
                )
            fail(f"Refusing unsafe log backup; preserved in place: {source_name}")
        if archive_retained:
            fail(f"Refusing unsafe log backup; archive copy retained: {target_name}")
        fail(f"Refusing unsafe log backup; no preserved copy could be verified: {source_name}")
    finally:
        if target_fd is not None:
            os.close(target_fd)
        if source_fd is not None:
            os.close(source_fd)


def move(source_name, target_name):
    descriptor = None
    try:
        descriptor, before = open_regular(log_parent_fd, source_name, logs_details.st_dev)
        expected = identity(before)
        try:
            os.stat(target_name, dir_fd=log_parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("target exists")
        os.rename(
            source_name,
            target_name,
            src_dir_fd=log_parent_fd,
            dst_dir_fd=log_parent_fd,
        )
        moved = os.stat(target_name, dir_fd=log_parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(moved.st_mode)
            or (moved.st_dev, moved.st_ino) != expected[:2]
        ):
            raise RuntimeError("source changed")
    except (OSError, RuntimeError):
        fail(f"Refusing unsafe log backup; preserved in place: {source_name}")
    finally:
        if descriptor is not None:
            os.close(descriptor)


numeric = checked_names()
for suffix, name in numeric:
    if suffix > backup_count:
        archive(name, suffix)

try:
    current_fd, current_details = open_regular(log_parent_fd, log_name, logs_details.st_dev)
except FileNotFoundError:
    current_fd = None
if current_fd is not None:
    os.close(current_fd)
    if current_details.st_size >= max_bytes:
        final_name = f"{log_name}.{backup_count}"
        try:
            os.stat(final_name, dir_fd=log_parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            archive(final_name, backup_count)
        for index in range(backup_count, 1, -1):
            previous = f"{log_name}.{index - 1}"
            try:
                os.stat(previous, dir_fd=log_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            move(previous, f"{log_name}.{index}")
        move(log_name, f"{log_name}.1")
os.close(archive_fd)
os.close(log_parent_fd)
' \
    "${CORTEX_LOGS_FD:?}" "$LOGS_DIR" "$LOG_FILE" \
    "$allowed_archive_root" "$archive_prefix" "$LOG_ARCHIVE_DIR" \
    "$max_bytes" "$backup_count" "$external_archive"
}

_canonical_log_file() {
  "$PYTHON" -c '
import sys
from pathlib import Path

logs = Path(sys.argv[1])
target = Path(sys.argv[2])
if not logs.is_absolute() or not target.is_absolute() or ".." in target.parts:
    raise SystemExit(2)
if logs.is_symlink() or target.is_symlink():
    raise SystemExit(2)
logs_resolved = logs.resolve(strict=True)
component = logs
try:
    relative = target.relative_to(logs)
except ValueError:
    raise SystemExit(2)
if not relative.parts:
    raise SystemExit(2)
for part in relative.parts[:-1]:
    component = component / part
    if component.is_symlink():
        raise SystemExit(2)
resolved = target.resolve(strict=False)
try:
    resolved.relative_to(logs_resolved)
except ValueError:
    raise SystemExit(2)
print(resolved)
' "$LOGS_DIR" "$LOG_FILE"
}

_canonical_archive_dir() {
  "$PYTHON" -c '
import sys
from pathlib import Path

path, allowed, required_prefix = (Path(value) for value in sys.argv[1:])
if (
    not path.is_absolute()
    or not allowed.is_absolute()
    or required_prefix.is_absolute()
    or ".." in path.parts
    or ".." in allowed.parts
    or ".." in required_prefix.parts
    or not required_prefix.parts
):
    raise SystemExit(2)
allowed_resolved = allowed.resolve(strict=True)
if allowed.is_symlink() or not allowed_resolved.is_dir():
    raise SystemExit(2)
lexical_path = path
for alias, canonical in (
    (Path("/var"), Path("/private/var")),
    (Path("/tmp"), Path("/private/tmp")),
):
    try:
        alias_relative = path.relative_to(alias)
    except ValueError:
        continue
    lexical_path = canonical / alias_relative
    break
try:
    lexical_relative = lexical_path.relative_to(allowed_resolved)
except ValueError:
    raise SystemExit(2)
if not lexical_relative.parts:
    raise SystemExit(2)
if lexical_relative.parts[:len(required_prefix.parts)] != required_prefix.parts:
    raise SystemExit(2)
component = allowed_resolved
for part in lexical_relative.parts:
    component = component / part
    if component.is_symlink():
        raise SystemExit(2)
resolved = path.resolve(strict=False)
try:
    relative = resolved.relative_to(allowed_resolved)
except ValueError:
    raise SystemExit(2)
if not relative.parts:
    raise SystemExit(2)
print(resolved)
' "$LOG_ARCHIVE_DIR" "$1" "$2"
}

_ensure_private_archive_dir() {
  "$PYTHON" -c '
import os
import stat
import sys
from pathlib import Path

allowed, target = (Path(value) for value in sys.argv[1:])
allowed = allowed.resolve(strict=True)
target = target.resolve(strict=False)
try:
    relative = target.relative_to(allowed)
except ValueError:
    raise SystemExit(2)
if not relative.parts:
    raise SystemExit(2)

directory_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
descriptor = os.open(allowed, directory_flags)
try:
    allowed_details = os.fstat(descriptor)
    if not stat.S_ISDIR(allowed_details.st_mode):
        raise SystemExit(2)
    allowed_device = allowed_details.st_dev
    for position, part in enumerate(relative.parts):
        created = False
        try:
            child = os.open(part, directory_flags, dir_fd=descriptor)
        except FileNotFoundError:
            os.mkdir(part, 0o700, dir_fd=descriptor)
            created = True
            child = os.open(part, directory_flags, dir_fd=descriptor)
        details = os.fstat(child)
        final = position == len(relative.parts) - 1
        unsafe_mode = details.st_mode & (0o077 if final else 0o022)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or details.st_dev != allowed_device
            or (not created and unsafe_mode)
        ):
            os.close(child)
            raise SystemExit(2)
        if created:
            os.fchmod(child, 0o700)
        os.close(descriptor)
        descriptor = child
finally:
    os.close(descriptor)
' "$1" "$2"
}

_status_text() {
  local payload="$1" state pid reason
  state="$(_json_field "$payload" state)"
  pid="$(_json_field "$payload" pid)"
  reason="$(_json_field "$payload" reason)"
  case "$state" in
    owned)
      printf 'Cortex Bridge fonctionne : http://127.0.0.1:%s (pid %s)\n' "$PORT" "$pid"
      ;;
    stopped)
      printf 'Cortex Bridge est arrêté.\nPour le lancer : scripts/cortex.sh start\n'
      ;;
    stale)
      printf 'Aucune instance active : la fiche processus était périmée et a été nettoyée.\nPour lancer : scripts/cortex.sh start\n'
      ;;
    foreign)
      printf 'Le port %s est utilisé par un autre processus :\n' "$PORT"
      "$PYTHON" -c '
import json, sys
payload = json.loads(sys.argv[1])
commands = payload.get("listener_commands") or {}
for pid in payload.get("listener_pids") or []:
    command = commands.get(str(pid)) or commands.get(pid) or ""
    print(f"  pid {pid} : {command or chr(63)}")
' "$payload"
      printf "Si c'est une console Cortex lancée à la main : kill <pid>, puis scripts/cortex.sh start\n"
      ;;
    *)
      printf 'État du serveur incertain : %s (%s)\n' "$state" "$reason"
      ;;
  esac
}

case "$COMMAND" in
  runtime-home)
    printf '%s\n' "$CORTEX_HOME"
    ;;

  storage-check)
    _check_external_storage >/dev/null
    ;;

  start)
    if [ "${CORTEX_START_INSTALL_LOCK_HELD:-}" != "1" ]; then
      export CORTEX_START_INSTALL_LOCK_HELD=1
      exec "$PYTHON" "$OWNERSHIP" with-shared-lock \
        --lock "$CORTEX_HOME/.install.lock" -- \
        bash "$ROOT/scripts/cortex.sh" "$@"
    fi
    if ! _start_lock_acquire; then
      echo "Cortex Bridge start is already in progress." >&2
      exit 1
    fi
    trap '_start_lock_release' EXIT
    if ! "$PYTHON" -c 'import fastapi,uvicorn,playwright,websockets'; then
      echo "Cortex Bridge runtime dependencies are incomplete. Re-run the approved installer plan." >&2
      exit 1
    fi
    storage_root=""
    if _external_storage_configured; then
      storage_root="$(_check_external_storage)"
    fi
    VALIDATED_STORAGE_ROOT="$storage_root"
    if [ -z "$LOG_ARCHIVE_DIR" ]; then
      if [ -n "$storage_root" ]; then
        LOG_ARCHIVE_DIR="$storage_root/99_QUARANTINE/logs"
      else
        LOG_ARCHIVE_DIR="$LOGS_DIR/archive"
      fi
    fi
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    if [ "$state" = "owned" ]; then
      _status_text "$status_json"
      exit 0
    fi
    if [ "$state" = "foreign" ]; then
      echo "Refusing to start: port $PORT is owned by a foreign process." >&2
      exit 1
    fi
    if [ "$state" != "stopped" ] && [ "$state" != "stale" ]; then
      echo "Refusing to start: process ownership state is $state." >&2
      exit 1
    fi
    if [ "$state" = "stale" ] && [ -n "$(_port_pid)" ]; then
      echo "Refusing to start: stale identity and an unverified listener on port $PORT." >&2
      exit 1
    fi

    _rotate_log_before_start
    instance_token="$($PYTHON -c 'import secrets; print(secrets.token_urlsafe(32))')"
    if ! launch_state="$(_launch_private_server "$instance_token")"; then
      echo "Refusing to launch through an unverified runtime tree." >&2
      exit 2
    fi
    pid="$(_json_field "$launch_state" pid)"
    case "$pid" in
      ''|*[!0-9]*)
        _abort_unverified_start "$launch_state" >/dev/null 2>&1 || true
        echo "Refusing a malformed launch identity." >&2
        exit 2
        ;;
    esac
    for _attempt in $(seq 1 40); do
      if curl -sf --max-time 1 "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1 \
        && [ "$(_port_pid)" = "$pid" ]; then
        if _capture_private_ownership_record "$launch_state"; then
          echo "Cortex Bridge ready: http://127.0.0.1:$PORT"
          echo "Logs: $LOG_FILE"
          exit 0
        else
          capture_status=$?
          _abort_unverified_start "$launch_state" >/dev/null 2>&1 || true
          exit "$capture_status"
        fi
      fi
      sleep 0.25
    done
    _abort_unverified_start "$launch_state" >/dev/null 2>&1 || true
    echo "Cortex Bridge did not become ready; authenticated cleanup was attempted." >&2
    exit 1
    ;;

  stop)
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    if [ "$state" = "stopped" ]; then
      echo "Cortex Bridge is stopped."
      exit 0
    fi
    if [ "$state" != "owned" ]; then
      echo "Refusing to stop: process state is $state, not owned." >&2
      exit 1
    fi
    pid="$(_json_field "$status_json" pid)"
    kill -TERM "$pid"
    for _attempt in $(seq 1 40); do
      status_json="$(_ownership_status)"
      state="$(_json_field "$status_json" state)"
      if [ "$state" = "stopped" ] || { [ "$state" = "stale" ] && [ -z "$(_port_pid)" ]; }; then
        rm -f "$PID_RECORD"
        echo "Cortex Bridge stopped."
        exit 0
      fi
      if [ "$state" = "foreign" ]; then
        echo "Cortex owner exited but a foreign listener now owns port $PORT; no further signal sent." >&2
        exit 1
      fi
      sleep 0.25
    done
    echo "Owned process did not stop within 10 seconds; no force-kill was attempted." >&2
    exit 1
    ;;

  status)
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    # A stale record whose process and listener are both gone only creates
    # confusion: clean it up so the next start never sees it.
    if [ "$state" = "stale" ] && [ -z "$(_port_pid)" ]; then
      rm -f "$PID_RECORD"
    fi
    if [ "$OUTPUT_MODE" = "--json" ]; then
      printf '%s\n' "$status_json"
    else
      _status_text "$status_json"
    fi
    [ "$state" = "owned" ]
    ;;

  doctor)
    if [ -n "$OUTPUT_MODE" ]; then
      exec "$PYTHON" "$ROOT/console/installer.py" doctor "$OUTPUT_MODE"
    fi
    exec "$PYTHON" "$ROOT/console/installer.py" doctor
    ;;

  logs)
    exec tail -f "$LOG_FILE"
    ;;

  go)
    # Lancement complet en une commande : serveur + Chrome + console + guidage.
    bash "$ROOT/scripts/cortex.sh" start || exit 1
    CONSOLE_URL="http://127.0.0.1:$PORT/"

    # Profil Chrome qui porte l'extension Cortex (défaut : dernier profil actif).
    CHROME_PROFILE="$("$PYTHON" - <<'PYEOF'
import json, pathlib, sys
base = pathlib.Path.home() / "Library/Application Support/Google/Chrome"
found = None
try:
    state = json.loads((base / "Local State").read_text())
    last = state.get("profile", {}).get("last_used") or "Default"
except Exception:
    last = "Default"
for sp in sorted(base.glob("*/Secure Preferences")):
    try:
        data = json.loads(sp.read_text())
    except Exception:
        continue
    for ext in (data.get("extensions", {}) or {}).get("settings", {}).values():
        if "cortex" in json.dumps(ext).lower():
            found = sp.parent.name
            break
    if found:
        break
print(found or last)
PYEOF
)"

    if pgrep -x "Google Chrome" >/dev/null 2>&1; then
      open -a "Google Chrome" "$CONSOLE_URL"
    else
      open -a "Google Chrome" --args --profile-directory="$CHROME_PROFILE" "$CONSOLE_URL"
    fi

    echo
    echo "Cortex Bridge est prêt : $CONSOLE_URL"
    echo "Profil Chrome utilisé : $CHROME_PROFILE"
    echo
    echo "Étapes dans l'onglet Cortex qui vient de s'ouvrir :"
    echo "  1. L'extension se couple automatiquement à la console (aucun code à copier)."
    echo "  2. Clique « Ouvrir ChatGPT » : l'onglet ChatGPT rejoint le même groupe d'onglets."
    echo "  3. Écris ta tâche dans le chat : ChatGPT propose, tu valides, Cortex exécute."
    echo
    echo "Vérifier l'installation : scripts/cortex.sh doctor"
    echo "Auto-test complet : scripts/cortex.sh selftest"
    echo "Tout arrêter proprement : scripts/cortex.sh stop"
    ;;

  selftest)
    # Auto-diagnostic complet : vérifie serveur, extension, protocole, DOM.
    FAIL=0
    VERSION=""
    echo "=== Cortex Bridge — auto-test ==="
    echo

    # 1. Serveur
    echo -n "[1/4] Serveur en écoute sur le port $PORT... "
    STATUS_JSON=$(curl -sf --max-time 3 "http://127.0.0.1:$PORT/api/status" 2>/dev/null || true)
    if [ -z "$STATUS_JSON" ]; then
      echo "ÉCHEC — serveur non accessible. Lance scripts/cortex.sh start d'abord."
      FAIL=1
    else
      VERSION=$(_json_field "$STATUS_JSON" version)
      RUNTIME=$(_json_field "$STATUS_JSON" runtime_mode)
      echo "OK (version $VERSION, runtime=$RUNTIME)"
    fi

    # 2. Extension
    echo -n "[2/4] Extension Chrome couplée... "
    EXT_JSON=$(curl -sf --max-time 3 "http://127.0.0.1:$PORT/api/chrome-extension/status" 2>/dev/null || true)
    if [ -z "$EXT_JSON" ]; then
      echo "ÉCHEC — impossible de lire le statut extension."
      FAIL=1
    else
      EXT_STATE=$(_json_field "$EXT_JSON" state)
      EXT_PAIRED=$(_json_field "$EXT_JSON" paired)
      if [ "$EXT_STATE" = "paired" ] || [ "$EXT_PAIRED" = "True" ]; then
        echo "OK (état: $EXT_STATE)"
      else
        echo "ATTENTION — état: $EXT_STATE (pas encore couplée)"
        echo "  → Ouvre la console dans Chrome, l'extension se couple automatiquement."
        FAIL=1
      fi
    fi

    # 3. DOM ChatGPT (probe) — seulement si extension couplée
    echo -n "[3/4] Probe DOM ChatGPT... "
    PROBE_JSON=$(curl -sf --max-time 10 "http://127.0.0.1:$PORT/api/transport/probe" 2>/dev/null || true)
    if [ -z "$PROBE_JSON" ]; then
      echo "ATTENTION — probe indisponible (extension peut-être pas couplée ou onglet ChatGPT absent)."
      echo "  → Ouvre un onglet ChatGPT via « Ouvrir ChatGPT » dans la console."
    else
      FAILURES=$(_json_field "$PROBE_JSON" failures)
      COMPOSER=$(_json_field "$PROBE_JSON" composer)
      if [ "$FAILURES" = "[]" ] || [ -z "$FAILURES" ]; then
        echo "OK (composer=$COMPOSER)"
      else
        echo "ATTENTION — failures: $FAILURES"
      fi
    fi

    # 4. Version
    echo -n "[4/4] Cohérence version... "
    REPO_VERSION=$(cat "$ROOT/VERSION" 2>/dev/null || echo "inconnue")
    if [ -n "$VERSION" ] && [ "$VERSION" = "$REPO_VERSION" ]; then
      echo "OK ($VERSION)"
    elif [ -z "$VERSION" ]; then
      echo "IGNORÉ — serveur non disponible, impossible de vérifier."
    else
      echo "ATTENTION — VERSION=$REPO_VERSION mais serveur=$VERSION"
    fi

    echo
    if [ "$FAIL" -eq 0 ]; then
      echo "✅ Tous les tests sont passés — Cortex Bridge est opérationnel."
    else
      echo "⚠️  Certains tests ont échoué. Corrige les points signalés ci-dessus."
    fi
    exit "$FAIL"
    ;;

  help|--help|-h|*)
    echo "Usage: scripts/cortex.sh {go|start|stop|status [--json]|doctor [--json]|selftest|logs}"
    ;;
esac
