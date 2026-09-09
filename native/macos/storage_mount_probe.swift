import Darwin
import Foundation

struct MountFacts: Codable {
    let schema_version: Int
    let st_dev_u32: UInt32
    let fsid_u32: [UInt32]
    let flags: UInt64
    let filesystem_type: String
    let mount_from: String
    let mount_on: String
    let volume_uuid: String
}

enum ProbeError: Error {
    case invalidInput
    case systemFailure
}

// Read only metadata for the already-held directory. No pathname is opened.
func descriptorVolumeUUID(_ fd: Int32) throws -> String {
    var attributes = attrlist()
    attributes.bitmapcount = UInt16(ATTR_BIT_MAP_COUNT)
    attributes.volattr = attrgroup_t(ATTR_VOL_INFO) | attrgroup_t(ATTR_VOL_UUID)
    var buffer = [UInt8](repeating: 0, count: 20)
    let result = buffer.withUnsafeMutableBytes {
        fgetattrlist(fd, &attributes, $0.baseAddress, $0.count, 0)
    }
    guard result == 0 else { throw ProbeError.systemFailure }
    let length = buffer.withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) }
    guard length == 20, buffer[4...].contains(where: { $0 != 0 }) else {
        throw ProbeError.systemFailure
    }
    return buffer.withUnsafeBufferPointer {
        NSUUID(uuidBytes: $0.baseAddress!.advanced(by: 4)).uuidString.lowercased()
    }
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
        st_dev_u32: UInt32(bitPattern: descriptorFacts.st_dev),
        fsid_u32: [UInt32(bitPattern: mountFacts.f_fsid.val.0), UInt32(bitPattern: mountFacts.f_fsid.val.1)],
        flags: UInt64(mountFacts.f_flags),
        filesystem_type: stringFromFixedCString(mountFacts.f_fstypename),
        mount_from: stringFromFixedCString(mountFacts.f_mntfromname),
        mount_on: stringFromFixedCString(mountFacts.f_mntonname),
        volume_uuid: descriptorVolumeUUID(fd)
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
        "st_dev_u32": NSNumber(value: facts.st_dev_u32),
        "fsid_u32": facts.fsid_u32.map { NSNumber(value: $0) },
        "flags": NSNumber(value: facts.flags),
        "filesystem_type": facts.filesystem_type,
        "mount_from": facts.mount_from,
        "mount_on": facts.mount_on,
        "volume_uuid": facts.volume_uuid,
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
