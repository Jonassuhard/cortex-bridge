"""Real native command/IO/cleanup tests; control triggers are test callbacks."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_storage_broker_handshake import SOURCE, PROFILE

HARNESS = r'''
private func commandPumpTest() -> Int32 {
    signal(SIGPIPE, SIG_IGN)
    if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--pump-child" {
        let scenario = CommandLine.arguments[2]
        if scenario == "success" { return 0 }
        if scenario == "closed-output" { close(1); close(2); while true { pause() } }
        if scenario == "signal" { raise(SIGUSR1); return 84 }
        if scenario == "flood" {
            let bytes = [UInt8](repeating: 120, count: 4_096)
            for _ in 0..<512 {
                _ = bytes.withUnsafeBytes { Darwin.write(1, $0.baseAddress, $0.count) }
            }
            while true { pause() }
        }
        if scenario == "nonzero" {
            let bytes: [UInt8] = [101,114,114]
            _ = bytes.withUnsafeBytes { Darwin.write(2, $0.baseAddress, $0.count) }
            return 7
        }
        if scenario == "secret" {
            var count = 0
            var byte: UInt8 = 0
            while Darwin.read(0, &byte, 1) == 1 {
                if byte == 0 {
                    let result = Array(String(count).utf8)
                    _ = result.withUnsafeBytes { Darwin.write(1, $0.baseAddress, $0.count) }
                    return count == 43 ? 0 : 81
                }
                guard byte == 65 else { return 82 }
                count += 1
            }
            return 83
        }
        if ["ignore", "short-cleanup", "short-owner-loss"].contains(scenario) { signal(SIGTERM, SIG_IGN) }
        var ready: UInt8 = 82
        _ = Darwin.write(1, &ready, 1)
        while true { pause() }
    }
    let scenario = CommandLine.arguments.last!
    let owner = NativeSpawnOwner()
    defer {
        // Emergency cleanup is test-only, scoped to unreaped direct children.
        for child in owner.children {
            var event = siginfo_t()
            if waitid(P_PID, id_t(child.pid), &event, WEXITED | WSTOPPED | WCONTINUED | WNOHANG | WNOWAIT) == 0 {
                _ = kill(child.pid, SIGKILL)
                var status: Int32 = 0
                _ = waitpid(child.pid, &status, 0)
            }
        }
    }
    let executable = CommandLine.arguments[0]
    let now = monotonicNanoseconds()!
    let effect = now + (scenario == "timeout" ? 300_000_000 : (["wire-backpressure", "wire-partial", "wire-idle"].contains(scenario) ? 4_000_000_000 : 2_000_000_000))
    let shortCleanup = ["short-cleanup", "short-owner-loss"].contains(scenario)
    let cleanup = effect + (shortCleanup ? 300_000_000 : 3_000_000_000)
    var cancelledAt: UInt64?
    var controlCalls = 0
    var firstControl: UInt64?
    var sockets: [Int32] = [-1, -1]
    var channel: BrokerRunningControl?
    var delayedWire: Data?
    if scenario.hasPrefix("wire-") {
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else { return 101 }
        channel = BrokerRunningControl(descriptor: sockets[1], workflowID: "wf", generation: 1,
            nonce: "nonce", commandSHA256: String(repeating: "a", count: 64),
            nextIncoming: scenario == "wire-wrap" ? UInt64.max : 1, nextOutgoing: 2)
        func frame(_ type: String, cursor: UInt64, payload: [String: BrokerJSON]) -> Data {
            var object: [String: BrokerJSON] = ["version": .unsigned(1), "type": .string(type),
                "workflow_id": .string("wf"), "generation": .unsigned(1),
                "connection_nonce": .string("nonce"), "cursor": .unsigned(cursor), "payload": .object(payload)]
            if scenario == "wire-nonce" { object["connection_nonce"] = .string("wrong") }
            if scenario == "wire-generation" { object["generation"] = .unsigned(2) }
            if scenario == "wire-extra" { object["extra"] = .null }
            return brokerFrame(object)!
        }
        if scenario == "wire-eof" { shutdown(sockets[0], SHUT_WR) }
        else {
            var bytes = Data()
            if ["wire-status", "wire-status-replay", "wire-wrap", "wire-backpressure"].contains(scenario) {
                bytes.append(frame("STATUS", cursor: scenario == "wire-wrap" ? UInt64.max : 1, payload: [:]))
            }
            if scenario == "wire-backpressure" {
                let fill = [UInt8](repeating: 0, count: 1_024)
                var full = false
                for _ in 0..<1_024 {
                    let sent = fill.withUnsafeBytes { send(sockets[1], $0.baseAddress, $0.count, MSG_DONTWAIT) }
                    if sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK) { full = true; break }
                }
                guard full else { return 106 }
            }
            let cursor: UInt64 = ["wire-replay", "wire-wrap"].contains(scenario) ? 0 : (scenario == "wire-status" ? 2 : 1)
            if scenario != "wire-backpressure" { bytes.append(frame("CANCEL", cursor: cursor, payload: [
                "command_sha256": .string(String(repeating: scenario == "wire-digest" ? "b" : "a", count: 64)),
                "reason": .string(scenario == "wire-reason" ? "anything" : "CLIENT_CANCELLED")])) }
            if scenario == "wire-idle" { delayedWire = bytes }
            else {
                if scenario == "wire-partial" { bytes = bytes.prefix(2) }
                guard bytes.withUnsafeBytes({ Darwin.write(sockets[0], $0.baseAddress, $0.count) }) == bytes.count else { return 102 }
            }
        }
    }
    defer { if sockets[0] >= 0 { close(sockets[0]); close(sockets[1]) } }
    let secret = scenario == "secret" ? SecretBuffer(copying: [UInt8](repeating: 65, count: 43)) : nil
    defer { secret?.zeroize() }
    let result = NativeCommandPump.run(owner: owner, executable: executable,
        argv: [executable, "--pump-child", scenario], secret: secret,
        effectDeadline: effect, cleanupDeadline: cleanup,
        control: { stdoutCount, _ in
            if let channel {
                let current = monotonicNanoseconds()!
                if firstControl == nil { firstControl = current }
                if let bytes = delayedWire, current - firstControl! > 2_200_000_000 {
                    _ = bytes.withUnsafeBytes { Darwin.write(sockets[0], $0.baseAddress, $0.count) }
                    delayedWire = nil
                }
                return channel.step(deadline: effect)
            }
            controlCalls += 1
            let current = monotonicNanoseconds()!
            if shortCleanup, stdoutCount > 0 {
                cancelledAt = current
                return scenario == "short-owner-loss" ? .ownerLost : .cancel
            }
            if firstControl == nil { firstControl = current }
            if scenario == "closed-output", current - firstControl! > 100_000_000 { return .cancel }
            if stdoutCount > 0 && ["cancel", "ignore"].contains(scenario) { return .cancel }
            if stdoutCount > 0 && scenario == "owner-lost" { return .ownerLost }
            return .keepGoing
        })
    if shortCleanup {
        guard result.code == "SUPERVISION_UNRESOLVED", !result.childReaped, !result.groupAbsent,
              owner.children.count == 1, let cancelledAt,
              monotonicNanoseconds()! - cancelledAt < 900_000_000 else { return 108 }
        return 0
    }
    guard result.childReaped, result.groupAbsent, owner.children.isEmpty else { return 90 }
    if scenario.hasPrefix("wire-") {
        if ["wire-cancel", "wire-status", "wire-idle"].contains(scenario) {
            guard result.code == "CANCELLED", channel?.errorCode == nil else { return 103 }
            if scenario == "wire-status" {
                guard case .frame(let reply) = readBrokerFrame(sockets[0], deadline: monotonicNanoseconds()! + 100_000_000),
                      brokerUInt(reply["cursor"]) == 2, brokerString(reply["type"]) == "STATUS",
                      case .object(let payload)? = reply["payload"],
                      Set(payload.keys) == ["phase", "command_sha256", "result_sha256", "closed_ready_sha256", "child_reaped", "group_absent"],
                      brokerString(payload["phase"]) == "running",
                      case .bool(false)? = payload["child_reaped"],
                      case .bool(false)? = payload["group_absent"] else { return 104 }
            }
            return 0
        }
        let expected = ["wire-replay": "REPLAY", "wire-nonce": "AUTH_FAILED",
            "wire-status-replay": "REPLAY", "wire-wrap": "REPLAY", "wire-backpressure": "DEADLINE_EXPIRED", "wire-partial": "DEADLINE_EXPIRED",
            "wire-generation": "STALE_GENERATION", "wire-extra": "INVALID_FRAME",
            "wire-digest": "AUTH_FAILED", "wire-reason": "INVALID_FRAME", "wire-eof": "CHANNEL_LOST"]
        return result.code == "CHANNEL_LOST" && channel?.errorCode == expected[scenario] ? 0 : 105
    }
    switch scenario {
    case "success": return result.code == "OK" && result.stdout.isEmpty && result.stderr.isEmpty ? 0 : 91
    case "nonzero": return result.code == "PROCESS_EXIT_NONZERO" && result.stderr == Data("err".utf8) ? 0 : 92
    case "secret": return result.code == "OK" && result.stdout == Data("43".utf8) ? 0 : 93
    case "cancel", "ignore": return result.code == "CANCELLED" ? 0 : 94
    case "owner-lost": return result.code == "CHANNEL_LOST" ? 0 : 95
    case "timeout": return result.code == "DEADLINE_EXPIRED" ? 0 : 96
    case "signal": return result.code == "PROCESS_SIGNALED" ? 0 : 98
    case "flood": return result.code == "PROCESS_OUTPUT_LIMIT" && result.stdout.count <= childOutputLimit ? 0 : 99
    case "closed-output": return result.code == "CANCELLED" && controlCalls < 1_000 ? 0 : 100
    default: return 97
    }
}
exit(commandPumpTest())
'''


class NativeCommandPumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("native command supervision is macOS-only")
        cls.temp = tempfile.TemporaryDirectory(prefix="cortex-pump-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "pump.swift"
        definitions, separator, tail = SOURCE.read_text().rpartition("exit(runMain())")
        if not separator or tail.strip():
            raise AssertionError("production entry point changed; review harness")
        source.write_text(definitions + HARNESS)
        cls.binary = Path(cls.temp.name) / "pump"
        profile = json.loads(PROFILE.read_text())
        command = ["/Library/Developer/CommandLineTools/usr/bin/swiftc", *profile["swiftc"],
                   str(source), "-o", str(cls.binary)]
        for framework in profile["frameworks"]:
            command.extend(["-framework", framework])
        result = subprocess.run(command, capture_output=True, text=True, env={**os.environ,
            "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk",
            "MACOSX_DEPLOYMENT_TARGET": "26.5"})
        if result.returncode:
            raise AssertionError(result.stderr)

    def test_real_command_scenarios(self):
        for scenario in ("success", "nonzero", "secret", "cancel", "ignore", "owner-lost", "timeout", "signal", "flood", "closed-output", "short-cleanup", "short-owner-loss"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], capture_output=True, timeout=8)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")
                self.assertEqual(result.returncode, 0)

    def test_wire_controls_on_real_child(self):
        for scenario in ("wire-cancel", "wire-status", "wire-eof", "wire-replay",
                         "wire-nonce", "wire-generation", "wire-extra", "wire-digest", "wire-reason",
                         "wire-status-replay", "wire-wrap", "wire-backpressure", "wire-partial", "wire-idle"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], capture_output=True, timeout=8)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")
                self.assertEqual(result.returncode, 0)
