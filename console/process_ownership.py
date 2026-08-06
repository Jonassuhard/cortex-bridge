"""Exact process identity and listener ownership checks."""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "pid",
    "start_time",
    "executable",
    "argv_hash",
    "instance_token",
    "port",
}
LISTENER_PROBE_TIMEOUT_SECONDS = 10


class ListenerProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessStatus:
    state: str
    pid: int | None = None
    listener_pids: list[int] = field(default_factory=list)
    reason: str | None = None


def _ps_value(pid: int, field_name: str) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", f"{field_name}="],
        capture_output=True,
        text=True,
        check=False,
        timeout=3,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ProcessLookupError(pid)
    return result.stdout.strip()


def capture_identity(pid: int, port: int, instance_token: str) -> dict[str, Any]:
    if pid <= 0 or not 0 < int(port) < 65536 or not instance_token:
        raise ValueError("invalid process identity input")
    command = _ps_value(pid, "command")
    return {
        "pid": int(pid),
        "start_time": _ps_value(pid, "lstart"),
        "executable": _ps_value(pid, "comm"),
        "argv_hash": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "instance_token": instance_token,
        "port": int(port),
    }


def listener_pids(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
            timeout=LISTENER_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ListenerProbeError("listener probe timed out") from exc
    except OSError as exc:
        raise ListenerProbeError("listener probe failed") from exc
    if result.returncode not in {0, 1}:
        raise ListenerProbeError("listener probe failed")
    pids = {int(line) for line in result.stdout.splitlines() if line.strip().isdigit()}
    return sorted(pids)


def _valid_record(record: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(record, dict)
        and REQUIRED_FIELDS == set(record)
        and isinstance(record.get("pid"), int)
        and isinstance(record.get("port"), int)
        and all(record.get(name) for name in REQUIRED_FIELDS - {"pid", "port"})
    )


def classify(record: dict[str, Any] | None, port: int) -> ProcessStatus:
    try:
        listeners = listener_pids(port)
    except ListenerProbeError as exc:
        pid = record.get("pid") if isinstance(record, dict) else None
        return ProcessStatus("unknown", pid, [], str(exc))
    if record is None:
        return ProcessStatus("foreign" if listeners else "stopped", listener_pids=listeners)
    if not _valid_record(record) or record["port"] != int(port):
        return ProcessStatus("stale", record.get("pid") if isinstance(record, dict) else None, listeners, "invalid record")
    pid = int(record["pid"])
    try:
        current = capture_identity(pid, int(port), str(record["instance_token"]))
    except (OSError, ProcessLookupError, subprocess.SubprocessError):
        return ProcessStatus("foreign" if listeners else "stale", pid, listeners, "process is gone")
    for key in ("pid", "start_time", "executable", "argv_hash", "port"):
        if current[key] != record[key]:
            return ProcessStatus("stale", pid, listeners, f"identity mismatch: {key}")
    if listeners == [pid]:
        return ProcessStatus("owned", pid, listeners)
    if listeners:
        return ProcessStatus("foreign", pid, listeners, "port belongs to another process")
    return ProcessStatus("stale", pid, [], "owned process is not listening")


def load_record(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if _valid_record(payload) else None


def write_record(path: Path, record: dict[str, Any]) -> None:
    if not _valid_record(record):
        raise ValueError("invalid process identity record")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _status_payload(record_path: Path, port: int) -> dict[str, Any]:
    status = classify(load_record(record_path), port)
    return {
        "state": status.state,
        "pid": status.pid,
        "listener_pids": status.listener_pids,
        "reason": status.reason,
        "port": port,
        "record": str(record_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--record", type=Path, required=True)
    status_parser.add_argument("--port", type=int, required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--record", type=Path, required=True)
    capture_parser.add_argument("--pid", type=int, required=True)
    capture_parser.add_argument("--port", type=int, required=True)
    capture_parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)

    if args.command == "status":
        print(json.dumps(_status_payload(args.record, args.port), sort_keys=True))
        return 0
    record = capture_identity(args.pid, args.port, args.token)
    write_record(args.record, record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
