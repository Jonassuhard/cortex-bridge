import CryptoKit
import CoreFoundation
import Darwin
import Foundation

private func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(78)
}

private func openDirectory(_ path: String) -> Int32 {
    guard path.hasPrefix("/") else { return -1 }
    var fd = Darwin.open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
    for component in path.split(separator: "/") {
        if component == "." || component == ".." { if fd >= 0 { Darwin.close(fd) }; return -1 }
        guard fd >= 0 else { return -1 }
        let next = openat(fd, String(component), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        Darwin.close(fd)
        fd = next
    }
    return fd
}

private func privateDirectory(_ path: String) -> Bool {
    let fd = openDirectory(path)
    guard fd >= 0 else { return false }
    defer { Darwin.close(fd) }
    var details = stat()
    guard fstat(fd, &details) == 0,
          (details.st_mode & S_IFMT) == S_IFDIR,
          details.st_uid == getuid(),
          (details.st_mode & 0o7777) == 0o700 else { return false }
    return true
}

private func readPrivateFile(_ path: String, mode: mode_t = 0o600) -> Data? {
    let url = URL(fileURLWithPath: path)
    let parent = openDirectory(url.deletingLastPathComponent().path)
    guard parent >= 0 else { return nil }
    defer { Darwin.close(parent) }
    let descriptor = openat(parent, url.lastPathComponent, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
    guard descriptor >= 0 else { return nil }
    defer { Darwin.close(descriptor) }
    return readPrivateDescriptor(descriptor, mode: mode)
}

private func readPrivateDescriptor(_ descriptor: Int32, mode: mode_t = 0o600) -> Data? {
    guard lseek(descriptor, 0, SEEK_SET) == 0 else { return nil }
    var details = stat()
    guard fstat(descriptor, &details) == 0,
          (details.st_mode & S_IFMT) == S_IFREG,
          details.st_uid == getuid(),
          details.st_nlink == 1,
          (details.st_mode & 0o7777) == mode,
          details.st_size >= 0,
          details.st_size <= 16 * 1024 * 1024 else { return nil }
    var result = Data()
    var buffer = [UInt8](repeating: 0, count: 65536)
    while true {
        let count = buffer.withUnsafeMutableBytes { raw in
            Darwin.read(descriptor, raw.baseAddress, raw.count)
        }
        if count == 0 { break }
        if count < 0 {
            if errno == EINTR { continue }
            return nil
        }
        result.append(buffer, count: count)
        guard result.count <= details.st_size else { return nil }
    }
    var after = stat()
    guard result.count == details.st_size, fstat(descriptor, &after) == 0,
          stable(details, after) else { return nil }
    return result
}

private func retainVerifiedFile(_ path: String, expectedDigest: String, mode: mode_t = 0o600) -> Int32 {
    let url = URL(fileURLWithPath: path)
    let parent = openDirectory(url.deletingLastPathComponent().path)
    guard parent >= 0 else { fail("CORTEX_BOOTSTRAP_INVALID: handoff parent") }
    defer { Darwin.close(parent) }
    let fd = openat(parent, url.lastPathComponent, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK)
    guard fd >= 0, let bytes = readPrivateDescriptor(fd, mode: mode), digest(bytes) == expectedDigest else {
        if fd >= 0 { Darwin.close(fd) }
        fail("CORTEX_BOOTSTRAP_INVALID: handoff file changed")
    }
    return fd
}

private func stable(_ a: stat, _ b: stat) -> Bool {
    a.st_dev == b.st_dev && a.st_ino == b.st_ino && a.st_mode == b.st_mode &&
    a.st_uid == b.st_uid && a.st_nlink == b.st_nlink && a.st_size == b.st_size &&
    a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec &&
    a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
}

private func verifyApplicationTree(_ path: String, manifest: [String: Any]) {
    guard let expected = manifest["app_tree"] as? [[String: Any]], expected.count <= 50000 else {
        fail("CORTEX_BOOTSTRAP_INVALID: application manifest")
    }
    let root = openDirectory(path)
    guard root >= 0 else { fail("CORTEX_BOOTSTRAP_INVALID: application directory") }
    defer { Darwin.close(root) }
    var records: [[String: Any]] = []
    var total: Int64 = 0
    func visit(_ directory: Int32, prefix: String, depth: Int) {
        var before = stat()
        guard depth <= 64, fstat(directory, &before) == 0,
              before.st_uid == getuid(), before.st_mode & 0o7777 == 0o700 else {
            fail("CORTEX_BOOTSTRAP_INVALID: application directory")
        }
        let copy = dup(directory)
        guard copy >= 0, let stream = fdopendir(copy) else {
            if copy >= 0 { Darwin.close(copy) }
            fail("CORTEX_BOOTSTRAP_INVALID: application enumeration")
        }
        defer { closedir(stream) }
        while true {
            errno = 0
            guard let entry = readdir(stream) else {
                if errno != 0 { fail("CORTEX_BOOTSTRAP_INVALID: application enumeration") }
                break
            }
            let name = withUnsafePointer(to: &entry.pointee.d_name) {
                $0.withMemoryRebound(to: CChar.self, capacity: 1024) { String(cString: $0) }
            }
            if name == "." || name == ".." { continue }
            guard !name.isEmpty, !name.contains("/"), records.count < 50000 else {
                fail("CORTEX_BOOTSTRAP_INVALID: application entry")
            }
            let relative = prefix.isEmpty ? name : prefix + "/" + name
            var named = stat()
            guard fstatat(directory, name, &named, AT_SYMLINK_NOFOLLOW) == 0 else {
                fail("CORTEX_BOOTSTRAP_INVALID: application entry")
            }
            let kind = named.st_mode & S_IFMT
            guard kind == S_IFDIR || kind == S_IFREG else {
                fail("CORTEX_BOOTSTRAP_INVALID: application link or special file")
            }
            let child = openat(directory, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK | (kind == S_IFDIR ? O_DIRECTORY : 0))
            guard child >= 0 else { fail("CORTEX_BOOTSTRAP_INVALID: application entry") }
            defer { Darwin.close(child) }
            var opened = stat()
            guard fstat(child, &opened) == 0, stable(named, opened), opened.st_uid == getuid() else {
                fail("CORTEX_BOOTSTRAP_INVALID: application changed")
            }
            if kind == S_IFDIR {
                records.append(["path": relative, "kind": "directory", "mode": 0o700])
                visit(child, prefix: relative, depth: depth + 1)
            } else {
                let mode = opened.st_mode & 0o111 == 0 ? 0o600 : 0o700
                guard opened.st_mode & 0o7777 == mode, opened.st_nlink == 1,
                      opened.st_size >= 0, opened.st_size <= 1024 * 1024 * 1024 else {
                    fail("CORTEX_BOOTSTRAP_INVALID: application file")
                }
                var hash = SHA256()
                var size: Int64 = 0
                var buffer = [UInt8](repeating: 0, count: 65536)
                while true {
                    let count = buffer.withUnsafeMutableBytes { Darwin.read(child, $0.baseAddress, $0.count) }
                    if count == 0 { break }
                    if count < 0 {
                        if errno == EINTR { continue }
                        fail("CORTEX_BOOTSTRAP_INVALID: application read")
                    }
                    size += Int64(count)
                    total += Int64(count)
                    guard size <= opened.st_size, total <= 1024 * 1024 * 1024 else {
                        fail("CORTEX_BOOTSTRAP_INVALID: application size")
                    }
                    hash.update(data: Data(buffer.prefix(count)))
                }
                guard size == opened.st_size else { fail("CORTEX_BOOTSTRAP_INVALID: application size") }
                let sha = hash.finalize().map { String(format: "%02x", $0) }.joined()
                records.append(["path": relative, "kind": "file", "mode": mode, "size": size, "sha256": sha])
            }
            var after = stat()
            var afterName = stat()
            guard fstat(child, &after) == 0, fstatat(directory, name, &afterName, AT_SYMLINK_NOFOLLOW) == 0,
                  stable(opened, after), stable(after, afterName) else {
                fail("CORTEX_BOOTSTRAP_INVALID: application changed")
            }
        }
        var after = stat()
        guard fstat(directory, &after) == 0, stable(before, after) else {
            fail("CORTEX_BOOTSTRAP_INVALID: application directory changed")
        }
    }
    visit(root, prefix: "", depth: 0)
    records.sort { Array(($0["path"] as! String).utf8).lexicographicallyPrecedes(Array(($1["path"] as! String).utf8)) }
    guard canonicalJSON(records) == canonicalJSON(expected) else {
        fail("CORTEX_BOOTSTRAP_INVALID: application tree mismatch")
    }
}

private func privateExecutable(_ path: String) -> Bool {
    var details = stat()
    guard lstat(path, &details) == 0,
          (details.st_mode & S_IFMT) == S_IFREG,
          details.st_uid == getuid(),
          (details.st_mode & 0o7777) == 0o700 else { return false }
    return true
}

// Foundation may accept repeated object keys. Scan raw, valid JSON before
// using its parsed dictionary, comparing decoded UTF-8 keys at each nesting.
private struct UniqueJSONKeys {
    let bytes: [UInt8]
    var index = 0

    mutating func whitespace() {
        while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 }
    }

    mutating func string() -> Data {
        let start = index
        guard index < bytes.count, bytes[index] == 34 else { fail("CORTEX_BOOTSTRAP_INVALID: JSON string") }
        index += 1
        while index < bytes.count {
            if bytes[index] == 92 { index += 2; continue }
            if bytes[index] == 34 {
                index += 1
                let raw = Data(bytes[start..<index])
                guard let decoded = try? JSONSerialization.jsonObject(with: raw, options: [.fragmentsAllowed]),
                      let text = decoded as? String else { fail("CORTEX_BOOTSTRAP_INVALID: JSON string") }
                return Data(text.utf8)
            }
            index += 1
        }
        fail("CORTEX_BOOTSTRAP_INVALID: JSON string")
    }

    mutating func value(depth: Int = 0) {
        whitespace()
        guard depth <= 128, index < bytes.count else { fail("CORTEX_BOOTSTRAP_INVALID: JSON depth") }
        let first = bytes[index]
        if first == 34 { _ = string(); return }
        if first == 123 || first == 91 {
            let object = first == 123
            let end: UInt8 = object ? 125 : 93
            var keys = Set<Data>()
            index += 1
            whitespace()
            if index < bytes.count && bytes[index] == end { index += 1; return }
            while index < bytes.count {
                whitespace()
                if object {
                    guard keys.insert(string()).inserted else { fail("CORTEX_BOOTSTRAP_INVALID: duplicate JSON key") }
                    whitespace()
                    guard index < bytes.count, bytes[index] == 58 else { fail("CORTEX_BOOTSTRAP_INVALID: JSON colon") }
                    index += 1
                }
                value(depth: depth + 1)
                whitespace()
                guard index < bytes.count else { fail("CORTEX_BOOTSTRAP_INVALID: JSON end") }
                if bytes[index] == end { index += 1; return }
                guard bytes[index] == 44 else { fail("CORTEX_BOOTSTRAP_INVALID: JSON comma") }
                index += 1
            }
            fail("CORTEX_BOOTSTRAP_INVALID: JSON end")
        }
        let start = index
        while index < bytes.count && ![9, 10, 13, 32, 44, 93, 125].contains(bytes[index]) { index += 1 }
        guard index > start else { fail("CORTEX_BOOTSTRAP_INVALID: JSON value") }
    }
}

private func jsonObject(_ data: Data, label: String) -> [String: Any] {
    guard let object = try? JSONSerialization.jsonObject(with: data),
          let dictionary = object as? [String: Any] else {
        fail("CORTEX_BOOTSTRAP_INVALID: \(label)")
    }
    var scanner = UniqueJSONKeys(bytes: Array(data))
    scanner.value()
    scanner.whitespace()
    guard scanner.index == data.count else { fail("CORTEX_BOOTSTRAP_INVALID: JSON trailing data") }
    return dictionary
}

private func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func validDigest(_ value: Any?) -> String? {
    guard let value = value as? String, value.count == 64,
          value.unicodeScalars.allSatisfy({
              ($0.value >= 48 && $0.value <= 57) || ($0.value >= 97 && $0.value <= 102)
          }) else { return nil }
    return value
}

// Match storage_reconciliation.canonical_json: UTF-8 key order, integer-only
// numbers, compact unescaped Unicode strings and domain-separated SHA-256.
private func canonicalJSON(_ value: Any) -> String {
    if let object = value as? [String: Any] {
        let keys = object.keys.sorted { Array($0.utf8).lexicographicallyPrecedes(Array($1.utf8)) }
        return "{" + keys.map { canonicalJSON($0) + ":" + canonicalJSON(object[$0]!) }.joined(separator: ",") + "}"
    }
    if let items = value as? [Any] {
        return "[" + items.map { canonicalJSON($0) }.joined(separator: ",") + "]"
    }
    if let text = value as? String {
        var result = "\""
        for scalar in text.unicodeScalars {
            switch scalar.value {
            case 0x22: result += "\\\""
            case 0x5C: result += "\\\\"
            case 0x00...0x1F: result += String(format: "\\u%04x", scalar.value)
            default: result.unicodeScalars.append(scalar)
            }
        }
        return result + "\""
    }
    if value is NSNull { return "null" }
    if let number = value as? NSNumber {
        if CFGetTypeID(number) == CFBooleanGetTypeID() { return number.boolValue ? "true" : "false" }
        let kind = String(cString: number.objCType)
        let text = number.stringValue
        guard kind != "f", kind != "d", UInt64(text) != nil else {
            fail("CORTEX_BOOTSTRAP_INVALID: canonical number")
        }
        return text
    }
    fail("CORTEX_BOOTSTRAP_INVALID: canonical value")
}

private func verifyInterpreter(home: String, generation: String, record: [String: Any], manifest: [String: Any]) {
    let path = "\(home)/installed-generations/\(generation)/app/bin/python"
    guard let expected = manifest["interpreter"] as? [String: Any],
          expected["target"] as? String == "app/bin/python",
          let expectedHash = validDigest(expected["sha256"]),
          validDigest(record["interpreter_sha256"]) == expectedHash,
          let bytes = readPrivateFile(path, mode: 0o700),
          digest(bytes) == expectedHash else {
        fail("CORTEX_BOOTSTRAP_INVALID: interpreter digest")
    }
    var details = stat()
    guard lstat(path, &details) == 0, privateExecutable(path) else {
        fail("CORTEX_BOOTSTRAP_INVALID: interpreter identity")
    }
    let actual: [String: UInt64] = [
        "dev_u32": UInt64(UInt32(bitPattern: details.st_dev)),
        "ino": UInt64(details.st_ino), "uid": UInt64(details.st_uid),
        "mode": UInt64(details.st_mode & 0o7777)
    ]
    for (key, value) in actual {
        guard let manifestValue = expected[key] as? NSNumber,
              let recordValue = record["interpreter_" + key] as? NSNumber,
              canonicalJSON(manifestValue) == String(value),
              canonicalJSON(recordValue) == String(value) else {
            fail("CORTEX_BOOTSTRAP_INVALID: interpreter identity")
        }
    }
}

private func preserveEnvironment(_ name: String) -> String? {
    guard let raw = getenv(name) else { return nil }
    return String(cString: raw)
}

private func execGeneration(home: String, generation: String, descriptors: [Int32]) -> Never {
    let app = "\(home)/installed-generations/\(generation)/app"
    let interpreter = "\(app)/bin/python"
    guard privateDirectory("\(home)/installed-generations/\(generation)"),
          privateDirectory(app),
          privateDirectory("\(app)/bin"),
          privateDirectory("\(app)/python"),
          privateExecutable(interpreter) else {
        fail("CORTEX_BOOTSTRAP_INVALID: generation interpreter")
    }

    var preserved: [String: String] = [:]
    for name in ["CORTEX_STORAGE_BOOTSTRAP", "CORTEX_STORAGE_REQUIRED_MARKER", "CORTEX_STORAGE_HOST", "CORTEX_STORAGE_IMAGE",
                 "CORTEX_STORAGE_MOUNT", "CORTEX_STORAGE_ROOT", "PORT",
                 "PLAYWRIGHT_BROWSERS_PATH"] {
        if let value = preserveEnvironment(name) { preserved[name] = value }
    }
    for name in ProcessInfo.processInfo.environment.keys where preserved[name] == nil {
        unsetenv(name)
    }
    setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin", 1)
    setenv("LANG", "C", 1)
    setenv("LC_ALL", "C", 1)
    setenv("CORTEX_HOME", home, 1)
    setenv("CORTEX_GENERATION_ID", generation, 1)
    for (name, value) in preserved { setenv(name, value, 1) }

    var arguments: [UnsafeMutablePointer<CChar>?] = []
    for descriptor in descriptors {
        guard fcntl(descriptor, F_SETFD, 0) == 0 else { fail("CORTEX_BOOTSTRAP_INVALID: handoff descriptor") }
    }
    let entrypoint = "import sys; sys.path.insert(0,sys.argv[1]); from installed_storage_runtime import bootstrap_main; bootstrap_main()"
    for argument in [interpreter, "-I", "-S", "-B", "-c", entrypoint, "\(app)/python", home] + descriptors.map({ String($0) }) {
        guard let copy = strdup(argument) else { fail("CORTEX_BOOTSTRAP_EXEC_FAILED") }
        arguments.append(copy)
    }
    arguments.append(nil)
    defer { for pointer in arguments { free(pointer) } }
    arguments.withUnsafeMutableBufferPointer { buffer in
        _ = execv(buffer[0]!, buffer.baseAddress!)
    }
    fail("CORTEX_BOOTSTRAP_EXEC_FAILED")
}

private func run() -> Int32 {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments.count == 2, arguments[0] == "--home" else {
        fail("usage: cortex-launch --home HOME")
    }
    // Foundation standardization can rewrite /private/var to the /var
    // symlink. Preserve the supplied absolute path for no-follow traversal.
    let home = arguments[1]
    guard privateDirectory(home) else { fail("CORTEX_BOOTSTRAP_INVALID: home") }

    let lockPath = "\(home)/.install.lock"
    let lock = Darwin.open(lockPath, O_RDWR | O_CLOEXEC | O_NOFOLLOW)
    guard lock >= 0 else { fail("CORTEX_BOOTSTRAP_INVALID: install lock") }
    var lockDetails = stat()
    guard fstat(lock, &lockDetails) == 0,
          (lockDetails.st_mode & S_IFMT) == S_IFREG,
          lockDetails.st_uid == getuid(),
          (lockDetails.st_mode & 0o7777) == 0o600,
          flock(lock, LOCK_SH) == 0 else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: install lock")
    }
    _ = fcntl(lock, F_SETFD, 0)

    guard privateDirectory("\(home)/installed-generations") else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: generation root")
    }
    let selectorPath = "\(home)/current-generation.json"
    guard let selectorData = readPrivateFile(selectorPath) else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: selector")
    }
    let selector = jsonObject(selectorData, label: "selector")
    guard selector["schema_version"] as? Int == 1,
          let generation = selector["generation_id"] as? String,
          let generationUUID = UUID(uuidString: generation),
          generationUUID.uuidString.lowercased() == generation,
          let recordDigest = validDigest(selector["generation_record_sha256"]) else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: selector")
    }
    let recordPath = "\(home)/installed-generations/\(generation)/generation-record.json"
    guard let recordData = readPrivateFile(recordPath) else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: generation record")
    }
    let record = jsonObject(recordData, label: "generation record")
    var unsignedRecord = record
    unsignedRecord.removeValue(forKey: "generation_record_sha256")
    let computedRecordDigest = digest(Data(("CORTEX-S3\0INSTALLED-GENERATION\0V1\0" + canonicalJSON(unsignedRecord)).utf8))
    guard record["schema_version"] as? Int == 1,
          record["generation_id"] as? String == generation,
          validDigest(record["generation_record_sha256"]) == recordDigest,
          computedRecordDigest == recordDigest,
          let manifestDigest = validDigest(record["owned_manifest_sha256"]),
          let manifestData = readPrivateFile("\(home)/installed-generations/\(generation)/owned-manifest.json"),
          digest(manifestData) == manifestDigest else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: generation")
    }
    let manifest = jsonObject(manifestData, label: "owned manifest")
    guard manifest["schema_version"] as? Int == 1,
          let nativeHelpers = manifest["native_helpers"] as? [String: Any],
          !nativeHelpers.isEmpty else {
        Darwin.close(lock)
        fail("CORTEX_BOOTSTRAP_INVALID: owned manifest")
    }
    verifyInterpreter(home: home, generation: generation, record: record, manifest: manifest)
    verifyApplicationTree("\(home)/installed-generations/\(generation)/app", manifest: manifest)
    // Reopen under the installation lock and bind every retained descriptor to
    // the exact verified bytes. Python revalidates these handles before start.
    let generationPath = "\(home)/installed-generations/\(generation)"
    let generationFD = openDirectory(generationPath)
    guard generationFD >= 0 else { fail("CORTEX_BOOTSTRAP_INVALID: handoff generation") }
    let selectorFD = retainVerifiedFile(selectorPath, expectedDigest: digest(selectorData))
    let recordFD = retainVerifiedFile(recordPath, expectedDigest: digest(recordData))
    let manifestFD = retainVerifiedFile(generationPath + "/owned-manifest.json", expectedDigest: manifestDigest)
    guard let interpreterDigest = validDigest(record["interpreter_sha256"]) else {
        fail("CORTEX_BOOTSTRAP_INVALID: handoff interpreter")
    }
    let interpreterFD = retainVerifiedFile(generationPath + "/app/bin/python", expectedDigest: interpreterDigest, mode: 0o700)
    execGeneration(home: home, generation: generation,
                   descriptors: [lock, selectorFD, generationFD, recordFD, manifestFD, interpreterFD])
}

exit(run())
