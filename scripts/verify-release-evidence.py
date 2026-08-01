#!/usr/bin/env python3
"""Validate the machine-readable Cortex Bridge v0.5 release evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_SUITES = ("backend", "frontendUnit", "e2e", "a11y")
REQUIRED_GATES = (
    "privacy",
    "links",
    "secrets",
    "dependencies",
    "install",
    "doctor",
    "uninstall",
    "build",
    "e2e",
    "a11y",
)
READY = "RELEASE_CANDIDATE_READY_FOR_OWNER_APPROVAL"
PENDING = "PENDING_OWNER_APPROVAL_FOR_LIVE_GATES"
PROVIDER_BLOCKED = "RELEASE_BLOCKED_BY_PROVIDER_TERMS"


class EvidenceValidator:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.findings: set[tuple[str, str]] = set()

    def report(self, category: str, field: str) -> None:
        self.findings.add((category, field))

    def get(self, path: str) -> Any:
        value: Any = self.payload
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                self.report("missing_field", path)
                return None
            value = value[part]
        return value

    @staticmethod
    def nonnegative_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    def validate(self) -> set[tuple[str, str]]:
        if self.get("schemaVersion") != 1:
            self.report("schema_version", "schemaVersion")
        if self.get("release") != "0.5.0":
            self.report("release_version", "release")
        commit = self.get("commit")
        if not isinstance(commit, str) or not HEX40_RE.fullmatch(commit):
            self.report("commit_format", "commit")
        generated_at = self.get("generatedAt")
        if not isinstance(generated_at, str) or not generated_at.endswith("Z"):
            self.report("timestamp_format", "generatedAt")

        for key in ("os", "python", "node", "browserDriver", "executorKind"):
            value = self.get(f"environment.{key}")
            if not isinstance(value, str) or not value.strip():
                self.report("environment_value", f"environment.{key}")
        if not isinstance(self.get("environment.simulation"), bool):
            self.report("environment_value", "environment.simulation")

        suites = self.get("suites")
        if isinstance(suites, dict):
            for suite_name in REQUIRED_SUITES:
                suite = self.get(f"suites.{suite_name}")
                if not isinstance(suite, dict):
                    continue
                for count_name in ("passed", "failed", "skipped"):
                    value = self.get(f"suites.{suite_name}.{count_name}")
                    if not self.nonnegative_int(value):
                        self.report("suite_count", f"suites.{suite_name}.{count_name}")
                if suite.get("failed") != 0:
                    self.report("failed_suite", f"suites.{suite_name}")

        cached = self.get("performance.cachedUsabilityMs")
        switch_p95 = self.get("performance.switchP95Ms")
        switch_max = self.get("performance.switchMaxMs")
        if not isinstance(cached, (int, float)) or isinstance(cached, bool) or cached >= 2000:
            self.report("performance_threshold", "performance.cachedUsabilityMs")
        if (
            not isinstance(switch_p95, (int, float))
            or isinstance(switch_p95, bool)
            or switch_p95 >= 3000
        ):
            self.report("performance_threshold", "performance.switchP95Ms")
        if (
            not isinstance(switch_max, (int, float))
            or isinstance(switch_max, bool)
            or switch_max > 10000
        ):
            self.report("performance_threshold", "performance.switchMaxMs")

        runs = self.get("dualConversations.runs")
        crossovers = self.get("dualConversations.crossovers")
        preserved = self.get("dualConversations.thirdWriterDraftPreserved")
        if not self.nonnegative_int(runs) or runs < 10:
            self.report("dual_conversation_evidence", "dualConversations.runs")
        if crossovers != 0:
            self.report("dual_conversation_evidence", "dualConversations.crossovers")
        if preserved is not True:
            self.report(
                "dual_conversation_evidence",
                "dualConversations.thirdWriterDraftPreserved",
            )

        for group, minimum in (
            ("fixtureMissions", 20),
            ("coldDualRuns", 10),
            ("crashPoints", 6),
        ):
            group_runs = self.get(f"acceptance.{group}.runs")
            group_passed = self.get(f"acceptance.{group}.passed")
            if (
                not self.nonnegative_int(group_runs)
                or not self.nonnegative_int(group_passed)
                or group_runs < minimum
                or group_passed != group_runs
            ):
                self.report("acceptance_evidence", f"acceptance.{group}")

        mini_runs = self.get("acceptance.miniSites.runs")
        mini_passed = self.get("acceptance.miniSites.passed")
        mini_status = self.get("acceptance.miniSites.status")
        live_status = self.get("acceptance.liveChatGPT.status")
        single_runs = self.get("acceptance.liveChatGPT.singleConversation.runs")
        single_passed = self.get("acceptance.liveChatGPT.singleConversation.passed")
        live_dual_runs = self.get("acceptance.liveChatGPT.dualConversations.runs")
        live_dual_passed = self.get("acceptance.liveChatGPT.dualConversations.passed")
        live_crossovers = self.get("acceptance.liveChatGPT.dualConversations.crossovers")
        third_refused = self.get("acceptance.liveChatGPT.thirdWriterRefused")
        file_upload = self.get("acceptance.liveChatGPT.fileUpload")
        screenshot_upload = self.get("acceptance.liveChatGPT.screenshotUpload")
        personal_data = self.get("acceptance.liveChatGPT.personalDataRecorded")

        live_ready = (
            live_status == "PASS"
            and self.nonnegative_int(single_runs)
            and self.nonnegative_int(single_passed)
            and single_runs >= 1
            and single_passed == single_runs
            and self.nonnegative_int(live_dual_runs)
            and self.nonnegative_int(live_dual_passed)
            and live_dual_runs >= 2
            and live_dual_passed == live_dual_runs
            and live_crossovers == 0
            and third_refused is True
            and file_upload is True
            and screenshot_upload is True
            and personal_data is False
        )
        live_honestly_blocked = (
            live_status in {"PENDING_OWNER_APPROVAL", "BLOCKED_BY_PROVIDER_TERMS"}
            and single_runs == 0
            and single_passed == 0
            and live_dual_runs == 0
            and live_dual_passed == 0
            and live_crossovers is None
            and third_refused is False
            and file_upload is False
            and screenshot_upload is False
            and personal_data is False
        )

        lifecycle_status = self.get("acceptance.cleanMacosLifecycle.status")
        lifecycle_boolean_fields = (
            "realCommands",
            "install",
            "browserLaunch",
            "serviceLifecycle",
            "doctor",
            "reinstall",
            "uninstall",
            "foreignSentinelPreserved",
        )
        lifecycle_booleans = {
            name: self.get(f"acceptance.cleanMacosLifecycle.{name}")
            for name in lifecycle_boolean_fields
        }
        lifecycle_attempts = self.get("acceptance.cleanMacosLifecycle.attempts")
        lifecycle_failures = self.get("acceptance.cleanMacosLifecycle.failedAttempts")
        failures_retained = self.get(
            "acceptance.cleanMacosLifecycle.failedAttemptsRetained"
        )
        lifecycle_hashes = {
            name: self.get(f"acceptance.cleanMacosLifecycle.planHashes.{name}")
            for name in ("install", "reinstall", "uninstall")
        }
        clean_lifecycle_pass = (
            lifecycle_status == "PASS"
            and all(value is True for value in lifecycle_booleans.values())
            and self.nonnegative_int(lifecycle_attempts)
            and lifecycle_attempts >= 1
            and self.nonnegative_int(lifecycle_failures)
            and lifecycle_failures <= lifecycle_attempts
            and failures_retained is True
            and all(
                isinstance(digest, str) and HEX64_RE.fullmatch(digest)
                for digest in lifecycle_hashes.values()
            )
        )
        clean_lifecycle_not_run = (
            lifecycle_status == "NOT_RUN"
            and all(value is False for value in lifecycle_booleans.values())
            and lifecycle_attempts == 0
            and lifecycle_failures == 0
            and failures_retained is False
            and all(digest is None for digest in lifecycle_hashes.values())
        )

        verdict = self.get("verdict")
        valid_mini_counts = self.nonnegative_int(mini_runs) and self.nonnegative_int(mini_passed)
        if verdict == READY:
            if (
                not valid_mini_counts
                or mini_status != "PASS"
                or mini_runs < 3
                or mini_passed != mini_runs
            ):
                self.report("live_gate_verdict", "acceptance.miniSites")
            if not live_ready:
                self.report("live_chatgpt_evidence", "acceptance.liveChatGPT")
            if not clean_lifecycle_pass:
                self.report(
                    "clean_macos_lifecycle",
                    "acceptance.cleanMacosLifecycle",
                )
        elif verdict in {PENDING, PROVIDER_BLOCKED}:
            expected_mini_status = (
                "BLOCKED_BY_PROVIDER_TERMS"
                if verdict == PROVIDER_BLOCKED
                else "PENDING_OWNER_APPROVAL"
            )
            if not (
                valid_mini_counts
                and
                mini_status == expected_mini_status
                and mini_runs == 0
                and mini_passed == 0
            ):
                self.report("live_gate_verdict", "acceptance.miniSites")
            if not live_honestly_blocked:
                self.report("live_chatgpt_evidence", "acceptance.liveChatGPT")
            if verdict == PROVIDER_BLOCKED and live_status != "BLOCKED_BY_PROVIDER_TERMS":
                self.report("live_chatgpt_evidence", "acceptance.liveChatGPT.status")
            if not (clean_lifecycle_pass or clean_lifecycle_not_run):
                self.report(
                    "clean_macos_lifecycle",
                    "acceptance.cleanMacosLifecycle",
                )
        else:
            self.report("release_verdict", "verdict")

        gates = self.get("gates")
        if isinstance(gates, dict):
            for gate_name in REQUIRED_GATES:
                gate = self.get(f"gates.{gate_name}")
                if gate != "PASS":
                    self.report("failed_gate", f"gates.{gate_name}")
            if self.get("gates.consoleErrors") != 0:
                self.report("failed_gate", "gates.consoleErrors")

        artifacts = self.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts:
            self.report("artifact_evidence", "artifacts")
        else:
            for name, digest in artifacts.items():
                if not isinstance(name, str) or not name or not isinstance(digest, str) or not HEX64_RE.fullmatch(digest):
                    self.report("artifact_hash", "artifacts")

        return self.findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    args = parser.parse_args()
    path = Path(args.manifest)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("[release-evidence] invalid_json manifest")
        return 1
    if not isinstance(payload, dict):
        print("[release-evidence] invalid_json manifest")
        return 1
    findings = EvidenceValidator(payload).validate()
    for category, field in sorted(findings):
        print(f"[release-evidence] {category} {field}")
    if findings:
        print(f"[release-evidence] FAILED findings={len(findings)}")
        return 1
    print("[release-evidence] PASS release=0.5.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
