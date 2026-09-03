import Darwin
import Foundation

struct MountFacts: Codable {
    let schema_version: Int
    let st_dev: Int64
    let fsid: [Int32]
    let flags: UInt64
    let filesystem_type: String
    let mount_from: String
    let mount_on: String
}

enum ProbeError: Error {
    case invalidInput
    case systemFailure
}

func stringFromFixedCString<T>(_ value: T) throws -> String {
    var copy = value
    let bytes = withUnsafeBytes(of: &copy) { rawBytes -> [UInt8] in
        let end = rawBytes.firstIndex(where: { $0 == 0 }) ?? rawBytes.endIndex
        return Array(rawBytes[..<end])
    }
    guard let string = String(bytes: bytes, encoding: .utf8),
          !string.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
    else {
        throw ProbeError.systemFailure
    }
    return string
}

func probe(fd: Int32) throws -> MountFacts {
    guard Darwin.fcntl(fd, F_GETFD) != -1 else {
        throw ProbeError.invalidInput
    }

    var descriptorFacts = stat()
    guard Darwin.fstat(fd, &descriptorFacts) == 0 else {
        throw ProbeError.systemFailure
    }
    guard (descriptorFacts.st_mode & S_IFMT) == S_IFDIR else {
        throw ProbeError.invalidInput
    }

    var mountFacts = statfs()
    guard Darwin.fstatfs(fd, &mountFacts) == 0 else {
        throw ProbeError.systemFailure
    }

    return try MountFacts(
        schema_version: 1,
        st_dev: Int64(descriptorFacts.st_dev),
        fsid: [mountFacts.f_fsid.val.0, mountFacts.f_fsid.val.1],
        flags: UInt64(mountFacts.f_flags),
        filesystem_type: stringFromFixedCString(mountFacts.f_fstypename),
        mount_from: stringFromFixedCString(mountFacts.f_mntfromname),
        mount_on: stringFromFixedCString(mountFacts.f_mntonname)
    )
}

func descriptorArgument() -> Int32? {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments.count == 2,
          arguments[0] == "--fd",
          !arguments[1].isEmpty,
          arguments[1].utf8.allSatisfy({ $0 >= 48 && $0 <= 57 }),
          let descriptor = Int32(arguments[1])
    else {
        return nil
    }
    return descriptor
}

func writeJSON(_ facts: MountFacts) throws {
    let object: [String: Any] = [
        "schema_version": facts.schema_version,
        "st_dev": NSNumber(value: facts.st_dev),
        "fsid": facts.fsid.map { NSNumber(value: $0) },
        "flags": NSNumber(value: facts.flags),
        "filesystem_type": facts.filesystem_type,
        "mount_from": facts.mount_from,
        "mount_on": facts.mount_on,
    ]
    var data = try JSONSerialization.data(withJSONObject: object, options: [])
    data.append(0x0A)
    FileHandle.standardOutput.write(data)
}

guard let fd = descriptorArgument() else {
    exit(64)
}

do {
    try writeJSON(probe(fd: fd))
    exit(0)
} catch ProbeError.invalidInput {
    exit(64)
} catch {
    exit(70)
}
