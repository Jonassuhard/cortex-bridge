"""Incremental native framing on real sockets, without disk or Keychain effects."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_storage_broker_handshake import SOURCE, PROFILE

HARNESS = r'''
private func readerTest() -> Int32 {
    var sockets: [Int32] = [-1, -1]
    guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else { return 80 }
    defer { close(sockets[0]); close(sockets[1]) }
    let reader = IncrementalBrokerReader()
    let deadline = monotonicNanoseconds()! + 2_000_000_000
    func send(_ bytes: Data) -> Bool {
        bytes.withUnsafeBytes { Darwin.write(sockets[0], $0.baseAddress, $0.count) == $0.count }
    }
    let frame = brokerFrame(["value": .unsigned(7)])!
    let scenario = CommandLine.arguments.last!
    if scenario == "fragmented" {
        guard case .pending = reader.step(sockets[1], deadline: deadline) else { return 81 }
        for index in 0..<(frame.count - 1) {
            guard send(Data([frame[index]])),
                  case .pending = reader.step(sockets[1], deadline: deadline) else { return 82 }
        }
        guard send(Data([frame.last!])),
              case .frame(let result) = reader.step(sockets[1], deadline: deadline),
              brokerUInt(result["value"]) == 7 else { return 83 }
        return 0
    }
    if scenario == "concatenated" {
        guard send(frame + frame) else { return 84 }
        for _ in 0..<2 {
            guard case .frame(let result) = reader.step(sockets[1], deadline: deadline),
                  brokerUInt(result["value"]) == 7 else { return 85 }
        }
        guard case .pending = reader.step(sockets[1], deadline: deadline) else { return 86 }
        return 0
    }
    if scenario == "eof" {
        shutdown(sockets[0], SHUT_WR)
        guard case .eof = reader.step(sockets[1], deadline: deadline) else { return 87 }
        return 0
    }
    if scenario == "limit" {
        // {"x":"..."} adds exactly eight UTF-8 bytes to its string content.
        let wire = brokerFrame(["x": .string(String(repeating: "a", count: 16_384 - 8))])!
        guard wire.count == 16_388 else { return 93 }
        // A same-thread writer must not fill the OS socket buffer before its
        // reader gets to run; fragment transport, not the accepted frame size.
        for offset in stride(from: 0, to: wire.count - 4, by: 4_096) {
            guard send(wire.subdata(in: offset..<(offset + 4_096))),
                  case .pending = reader.step(sockets[1], deadline: deadline) else { return 94 }
        }
        guard send(wire.suffix(4)),
              case .frame(let object) = reader.step(sockets[1], deadline: deadline),
              brokerString(object["x"])?.count == 16_376 else { return 92 }
        return 0
    }
    if scenario == "deadline" {
        guard send(frame.prefix(2)),
              case .pending = reader.step(sockets[1], deadline: deadline),
              case .deadline = reader.step(sockets[1], deadline: 0),
              send(frame.dropFirst(2)),
              case .deadline = reader.step(sockets[1], deadline: deadline) else { return 88 }
        return 0
    }
    let bad: Data
    switch scenario {
    case "truncated": bad = frame.prefix(2)
    case "truncated-payload": bad = frame.dropLast()
    case "oversized": bad = Data([0, 0, 64, 1])
    case "empty": bad = Data([0, 0, 0, 0])
    case "noncanonical": bad = Data([0, 0, 0, 3, 123, 32, 125])
    default: return 89
    }
    guard send(bad) else { return 90 }
    if scenario.hasPrefix("truncated") { shutdown(sockets[0], SHUT_WR) }
    guard case .invalid = reader.step(sockets[1], deadline: deadline),
          case .invalid = reader.step(sockets[1], deadline: deadline) else { return 91 }
    return 0
}
exit(readerTest())
'''


class NativeControlReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.uname().sysname != "Darwin":
            raise unittest.SkipTest("native reader is macOS-only")
        cls.temp = tempfile.TemporaryDirectory(prefix="cortex-reader-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "reader.swift"
        definitions, separator, tail = SOURCE.read_text().rpartition("exit(runMain())")
        if not separator or tail.strip():
            raise AssertionError("production entry point changed")
        source.write_text(definitions + HARNESS)
        cls.binary = Path(cls.temp.name) / "reader"
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

    def test_socket_scenarios(self):
        for scenario in ("fragmented", "concatenated", "eof", "deadline",
                         "truncated", "truncated-payload", "oversized", "empty", "noncanonical", "limit"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], capture_output=True, timeout=5)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")
                self.assertEqual(result.returncode, 0)
