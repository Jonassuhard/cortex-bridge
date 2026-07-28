#!/usr/bin/env python3
"""Create and verify evidence for a disposable local mini-site mission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = ("index.html", "style.css", "app.js", "README.md")
REQUIRED_VIEWPORTS = {375, 768, 1440}
EXTERNAL_URL_RE = re.compile(r"(?:https?:)?//[^\s\"'<>]+", re.IGNORECASE)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def snapshot_tree(root: Path, exclusions: list[Path]) -> dict[str, str]:
    resolved_root = root.resolve()
    resolved_exclusions = [item.resolve() for item in exclusions]
    snapshot: dict[str, str] = {}
    for path in sorted(resolved_root.rglob("*")):
        if not path.is_file():
            continue
        if any(path == item or is_within(path, item) for item in resolved_exclusions):
            continue
        if ".git" in path.relative_to(resolved_root).parts:
            continue
        snapshot[path.relative_to(resolved_root).as_posix()] = file_hash(path)
    return snapshot


def write_baseline(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    exclusions = [Path(item).expanduser().resolve() for item in args.exclude]
    exclusions.append(output)
    if not root.is_dir():
        print("[acceptance] invalid_root control:0")
        return 1
    for item in exclusions:
        if item != output and not is_within(item, root):
            print("[acceptance] invalid_exclusion control:0")
            return 1
    payload = {
        "schemaVersion": 1,
        "root": str(root),
        "exclude": [str(item) for item in exclusions],
        "files": snapshot_tree(root, exclusions),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[acceptance] BASELINE files={len(payload['files'])}")
    return 0


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def verify(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    evidence_path = Path(args.evidence).expanduser().resolve()
    outside_root = Path(args.outside_root).expanduser().resolve()
    baseline_path = Path(args.outside_baseline).expanduser().resolve()
    findings: set[str] = set()

    if not workspace.is_dir() or not is_within(workspace, outside_root):
        findings.add("invalid_workspace")
    try:
        evidence = load_json(evidence_path)
    except (OSError, ValueError, json.JSONDecodeError):
        evidence = {}
        findings.add("invalid_evidence")
    try:
        baseline = load_json(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError):
        baseline = {}
        findings.add("invalid_baseline")

    missing_or_invalid_artifact = False
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
        findings.add("artifact_evidence")
    for name in REQUIRED_ARTIFACTS:
        path = workspace / name
        if not path.is_file():
            findings.add("missing_artifact")
            missing_or_invalid_artifact = True
            continue
        if path.is_symlink() or not is_within(path.resolve(), workspace):
            findings.add("artifact_outside_workspace")
            missing_or_invalid_artifact = True
            continue
        expected_hash = artifacts.get(name)
        if not isinstance(expected_hash, str) or expected_hash != file_hash(path):
            findings.add("artifact_hash")
            missing_or_invalid_artifact = True
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.add("artifact_encoding")
            missing_or_invalid_artifact = True
        else:
            if EXTERNAL_URL_RE.search(content):
                findings.add("external_url")

    for path in workspace.rglob("*"):
        if not path.is_file() or path == evidence_path:
            continue
        if path.is_symlink() or not is_within(path.resolve(), workspace):
            findings.add("artifact_outside_workspace")
            continue
        if path.suffix.lower() not in {".html", ".css", ".js", ".md", ".json"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.add("artifact_encoding")
            continue
        if EXTERNAL_URL_RE.search(content):
            findings.add("external_url")

    status = evidence.get("status")
    if status != "completed":
        findings.add("incomplete_status")
    elif missing_or_invalid_artifact:
        findings.add("fake_completion")

    commands = evidence.get("commands")
    if not isinstance(commands, list) or not commands:
        findings.add("command_evidence")
    else:
        for command in commands:
            if not isinstance(command, dict) or command.get("returnCode") != 0:
                findings.add("command_failed")

    browser = evidence.get("browser")
    if not isinstance(browser, dict):
        browser = {}
        findings.add("browser_evidence")
    for key in ("pageErrors", "consoleErrors", "externalRequests"):
        value = browser.get(key)
        if not isinstance(value, list) or value:
            findings.add("browser_error")
    viewports = browser.get("viewports")
    if not isinstance(viewports, list) or not REQUIRED_VIEWPORTS.issubset(set(viewports)):
        findings.add("viewport_evidence")
    if (
        browser.get("axeViolations") != 0
        or browser.get("keyboard") is not True
        or browser.get("reducedMotion") is not True
    ):
        findings.add("accessibility_evidence")

    response_expectations = {
        "/": "text/html",
        "/style.css": "text/css",
        "/app.js": "text/javascript",
    }
    responses = evidence.get("serverResponses")
    response_map: dict[str, dict[str, Any]] = {}
    if isinstance(responses, list):
        response_map = {
            item.get("path"): item
            for item in responses
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
    for path, expected_type in response_expectations.items():
        item = response_map.get(path)
        if (
            not item
            or item.get("status") != 200
            or not str(item.get("contentType", "")).startswith(expected_type)
        ):
            findings.add("server_evidence")

    processes = evidence.get("processes")
    if not isinstance(processes, list):
        findings.add("process_evidence")
    else:
        for process in processes:
            if not isinstance(process, dict):
                findings.add("process_evidence")
                continue
            pid = process.get("pid")
            if process.get("expectedStopped") is not True or not isinstance(pid, int) or pid <= 0:
                findings.add("process_evidence")
            elif process_is_alive(pid):
                findings.add("leftover_process")

    if baseline:
        try:
            baseline_root = Path(str(baseline["root"])).resolve()
            baseline_files = baseline["files"]
            exclusions = [Path(item).resolve() for item in baseline["exclude"]]
            if baseline_root != outside_root or not isinstance(baseline_files, dict):
                raise ValueError
            current_files = snapshot_tree(outside_root, exclusions)
            if current_files != baseline_files:
                findings.add("outside_workspace_change")
        except (KeyError, TypeError, ValueError):
            findings.add("invalid_baseline")

    for category in sorted(findings):
        print(f"[acceptance] {category} control:0")
    if findings:
        print(f"[acceptance] FAILED findings={len(findings)}")
        return 1
    print(f"[acceptance] PASS artifacts={len(REQUIRED_ARTIFACTS)} viewports=3")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline", help="snapshot files outside a mission workspace")
    baseline.add_argument("--root", required=True)
    baseline.add_argument("--exclude", action="append", default=[], required=True)
    baseline.add_argument("--output", required=True)
    baseline.set_defaults(handler=write_baseline)
    verifier = subparsers.add_parser("verify", help="verify workspace artifacts and evidence")
    verifier.add_argument("--workspace", required=True)
    verifier.add_argument("--evidence", required=True)
    verifier.add_argument("--outside-root", required=True)
    verifier.add_argument("--outside-baseline", required=True)
    verifier.set_defaults(handler=verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
