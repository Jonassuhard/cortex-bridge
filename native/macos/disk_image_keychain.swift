import Darwin
import Foundation
import Security

enum Operation: String, Codable {
    case create
    case mount
    case detach
    case inspectItem = "inspect-item"
    case deleteDisposableItem = "delete-disposable-item"
}

struct HelperRequest: Codable {
    let schema_version: Int
    let operation: Operation
    let image_path: String
    let mount_path: String?
    let volume_name: String?
    let size: String?
    let transaction_id: UUID
    let expected_encryption_uuid: String?
    let disposable: Bool
    let cleanup_approved: Bool
}

struct HelperResponse: Codable {
    let schema_version: Int
    let operation: String
    let code: String
    let encryption_uuid: String?
    let device: String?
    let item_count: Int?
}

private let keychainService = "com.cortexbridge.encrypted-storage"
private let keychainDescription = "disk image password"
private let hdiutilPath = "/usr/bin/hdiutil"
private let childEnvironment = [
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG=C",
    "LC_ALL=C",
]

final class SecretBuffer {
    var bytes: [UInt8]
    let sourceRandomByteCount: Int?

    init(_ bytes: [UInt8], sourceRandomByteCount: Int? = nil) {
        self.bytes = bytes
        self.sourceRandomByteCount = sourceRandomByteCount
    }

    func zeroize() {
        bytes.withUnsafeMutableBytes { rawBuffer in
            guard let base = rawBuffer.baseAddress else { return }
            memset_s(base, rawBuffer.count, 0, rawBuffer.count)
        }
    }

    deinit {
        zeroize()
    }
}

enum HelperFailure: Error {
    case invalidRequest
    case cleanupNotAuthorized
    case randomFailure
    case hdiutilFailure
    case invalidEncryption
    case keychainCollision
    case keychainNotFound
    case keychainAmbiguous
    case keychainInteractionForbidden
    case keychainFailure
    case invalidMountMapping

    var code: String {
        switch self {
        case .invalidRequest: return "INVALID_REQUEST"
        case .cleanupNotAuthorized: return "CLEANUP_NOT_AUTHORIZED"
        case .randomFailure: return "RANDOM_GENERATION_FAILED"
        case .hdiutilFailure: return "HDIUTIL_FAILED"
        case .invalidEncryption: return "IMAGE_ENCRYPTION_INVALID"
        case .keychainCollision: return "KEYCHAIN_ITEM_COLLISION"
        case .keychainNotFound: return "KEYCHAIN_ITEM_NOT_FOUND"
        case .keychainAmbiguous: return "KEYCHAIN_ITEM_AMBIGUOUS"
        case .keychainInteractionForbidden: return "KEYCHAIN_INTERACTION_FORBIDDEN"
        case .keychainFailure: return "KEYCHAIN_FAILED"
        case .invalidMountMapping: return "MOUNT_MAPPING_INVALID"
        }
    }

    var exitCode: Int32 {
        switch self {
        case .invalidRequest, .cleanupNotAuthorized:
            return 64
        default:
            return 70
        }
    }
}

protocol RandomSource {
    func bytes(count: Int) throws -> SecretBuffer
}

protocol HdiutilRunning {
    func run(argv: [String], secret: SecretBuffer?) throws -> Data
}

struct KeychainSelector {
    let account: String
    let transactionTag: Data
}

struct KeychainItem {
    let account: String
    let label: String
    let transactionTag: Data
    let secret: SecretBuffer
}

protocol KeychainStoring {
    func countForAccount(_ account: String) throws -> Int
    func count(selector: KeychainSelector, action: String) throws -> Int
    func add(_ item: KeychainItem) throws
    func read(selector: KeychainSelector) throws -> [SecretBuffer]
    func delete(selector: KeychainSelector) throws
}

struct SystemRandomSource: RandomSource {
    func bytes(count: Int) throws -> SecretBuffer {
        var bytes = [UInt8](repeating: 0, count: count)
        let status = bytes.withUnsafeMutableBytes { rawBuffer -> Int32 in
            guard let base = rawBuffer.baseAddress else { return errSecParam }
            return SecRandomCopyBytes(kSecRandomDefault, count, base)
        }
        guard status == errSecSuccess else {
            bytes.withUnsafeMutableBytes { rawBuffer in
                if let base = rawBuffer.baseAddress {
                    memset_s(base, rawBuffer.count, 0, rawBuffer.count)
                }
            }
            throw HelperFailure.randomFailure
        }
        return SecretBuffer(bytes, sourceRandomByteCount: count)
    }
}

private func isInteractionStatus(_ status: OSStatus) -> Bool {
    status == errSecInteractionNotAllowed || status == errSecAuthFailed || status == errSecUserCanceled
}

private func throwForSecurityStatus(_ status: OSStatus) throws {
    if isInteractionStatus(status) {
        throw HelperFailure.keychainInteractionForbidden
    }
    throw HelperFailure.keychainFailure
}

protocol SecurityCalling {
    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?)
    func add(_ query: [String: Any]) -> OSStatus
    func delete(_ query: [String: Any]) -> OSStatus
}

struct SystemSecurityAdapter: SecurityCalling {
    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?) {
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        return (status, result)
    }

    func add(_ query: [String: Any]) -> OSStatus {
        SecItemAdd(query as CFDictionary, nil)
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        SecItemDelete(query as CFDictionary)
    }
}

final class SystemKeychainStore: KeychainStoring {
    private let security: SecurityCalling
    private let trackSecret: ((SecretBuffer) -> Void)?

    init(
        security: SecurityCalling = SystemSecurityAdapter(),
        trackSecret: ((SecretBuffer) -> Void)? = nil
    ) {
        self.security = security
        self.trackSecret = trackSecret
    }

    private func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
            kSecAttrService as String: keychainService,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
            kSecUseAuthenticationUI as String: kSecUseAuthenticationUIFail,
        ]
    }

    private func strictQuery(selector: KeychainSelector) -> [String: Any] {
        var query = baseQuery(account: selector.account)
        query[kSecAttrGeneric as String] = selector.transactionTag
        return query
    }

    private func resultCount(status: OSStatus, result: Any?) throws -> Int {
        if status == errSecItemNotFound { return 0 }
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            return 0
        }
        if let values = result as? [Any] { return values.count }
        return result == nil ? 0 : 1
    }

    func countForAccount(_ account: String) throws -> Int {
        var query = baseQuery(account: account)
        query[kSecMatchLimit as String] = kSecMatchLimitAll
        query[kSecReturnAttributes as String] = true
        let (status, result) = security.copyMatching(query)
        return try resultCount(
            status: status,
            result: result
        )
    }

    func count(selector: KeychainSelector, action: String) throws -> Int {
        var query = strictQuery(selector: selector)
        query[kSecMatchLimit as String] = kSecMatchLimitAll
        query[kSecReturnAttributes as String] = true
        let (status, result) = security.copyMatching(query)
        return try resultCount(
            status: status,
            result: result
        )
    }

    func add(_ item: KeychainItem) throws {
        var query = baseQuery(account: item.account)
        query[kSecAttrLabel as String] = item.label
        query[kSecAttrDescription as String] = keychainDescription
        query[kSecAttrGeneric as String] = item.transactionTag
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        query[kSecValueData as String] = Data(item.secret.bytes)
        let status = security.add(query)
        if status == errSecDuplicateItem { throw HelperFailure.keychainCollision }
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            return
        }
    }

    func read(selector: KeychainSelector) throws -> [SecretBuffer] {
        var query = strictQuery(selector: selector)
        query[kSecMatchLimit as String] = kSecMatchLimitAll
        query[kSecReturnData as String] = true
        let (status, result) = security.copyMatching(query)
        if status == errSecItemNotFound { return [] }
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            return []
        }

        let values: [Data]
        if let array = result as? [Data] {
            values = array
        } else if let data = result as? Data {
            values = [data]
        } else {
            throw HelperFailure.keychainFailure
        }
        return values.map { data in
            let secret = SecretBuffer([UInt8](data))
            trackSecret?(secret)
            return secret
        }
    }

    func delete(selector: KeychainSelector) throws {
        let query = strictQuery(selector: selector)
        let status = security.delete(query)
        if status == errSecItemNotFound { throw HelperFailure.keychainNotFound }
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            return
        }
    }
}

private func withCStringArray<R>(
    _ strings: [String],
    _ body: (UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>) -> R
) -> R {
    let allocated = strings.map { strdup($0)! }
    defer { allocated.forEach { free($0) } }
    var pointers = allocated.map { Optional($0) }
    pointers.append(nil)
    return pointers.withUnsafeMutableBufferPointer { buffer in
        body(buffer.baseAddress!)
    }
}

private func spawnChild(
    executable: String,
    argv: [String],
    secret: SecretBuffer?
) throws -> Data {
        guard argv.count >= 2, argv[0] == executable else {
            throw HelperFailure.invalidRequest
        }
        var inputPipe = [Int32](repeating: -1, count: 2)
        var outputPipe = [Int32](repeating: -1, count: 2)
        guard Darwin.pipe(&inputPipe) == 0 else { throw HelperFailure.hdiutilFailure }
        guard Darwin.pipe(&outputPipe) == 0 else {
            Darwin.close(inputPipe[0])
            Darwin.close(inputPipe[1])
            throw HelperFailure.hdiutilFailure
        }

        func closeDescriptor(_ descriptor: inout Int32) {
            if descriptor >= 0 {
                Darwin.close(descriptor)
                descriptor = -1
            }
        }
        defer {
            closeDescriptor(&inputPipe[0])
            closeDescriptor(&inputPipe[1])
            closeDescriptor(&outputPipe[0])
            closeDescriptor(&outputPipe[1])
        }

        var actions: posix_spawn_file_actions_t?
        guard posix_spawn_file_actions_init(&actions) == 0 else {
            throw HelperFailure.hdiutilFailure
        }
        defer { posix_spawn_file_actions_destroy(&actions) }
        guard posix_spawn_file_actions_adddup2(&actions, inputPipe[0], STDIN_FILENO) == 0,
              posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDOUT_FILENO) == 0,
              posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDERR_FILENO) == 0,
              posix_spawn_file_actions_addclose(&actions, inputPipe[1]) == 0,
              posix_spawn_file_actions_addclose(&actions, outputPipe[0]) == 0,
              posix_spawn_file_actions_addclose(&actions, inputPipe[0]) == 0,
              posix_spawn_file_actions_addclose(&actions, outputPipe[1]) == 0
        else {
            throw HelperFailure.hdiutilFailure
        }

        var attributes: posix_spawnattr_t?
        guard posix_spawnattr_init(&attributes) == 0 else {
            throw HelperFailure.hdiutilFailure
        }
        defer { posix_spawnattr_destroy(&attributes) }
        let flags = Int16(POSIX_SPAWN_CLOEXEC_DEFAULT)
        guard posix_spawnattr_setflags(&attributes, flags) == 0 else {
            throw HelperFailure.hdiutilFailure
        }

        var pid = pid_t()
        let spawnStatus: Int32 = withCStringArray(argv) { argvPointer in
            withCStringArray(childEnvironment) { environmentPointer in
                executable.withCString { executablePointer in
                    posix_spawn(
                        &pid,
                        executablePointer,
                        &actions,
                        &attributes,
                        argvPointer,
                        environmentPointer
                    )
                }
            }
        }
        guard spawnStatus == 0 else { throw HelperFailure.hdiutilFailure }

        closeDescriptor(&inputPipe[0])
        closeDescriptor(&outputPipe[1])

        if let secret {
            var wireBytes = secret.bytes
            wireBytes.append(0)
            defer {
                wireBytes.withUnsafeMutableBytes { rawBuffer in
                    if let base = rawBuffer.baseAddress {
                        memset_s(base, rawBuffer.count, 0, rawBuffer.count)
                    }
                }
            }
            var written = 0
            while written < wireBytes.count {
                let result = wireBytes.withUnsafeBytes { rawBuffer -> Int in
                    guard let base = rawBuffer.baseAddress else { return -1 }
                    return Darwin.write(
                        inputPipe[1],
                        base.advanced(by: written),
                        rawBuffer.count - written
                    )
                }
                if result < 0 && errno == EINTR { continue }
                guard result > 0 else {
                    closeDescriptor(&inputPipe[1])
                    _ = waitpid(pid, nil, 0)
                    throw HelperFailure.hdiutilFailure
                }
                written += result
            }
        }
        closeDescriptor(&inputPipe[1])

        var output = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = Darwin.read(outputPipe[0], &buffer, buffer.count)
            if count < 0 && errno == EINTR { continue }
            guard count >= 0 else {
                _ = waitpid(pid, nil, 0)
                throw HelperFailure.hdiutilFailure
            }
            if count == 0 { break }
            output.append(buffer, count: count)
        }
        closeDescriptor(&outputPipe[0])

        var status: Int32 = 0
        let waitResult = waitpid(pid, &status, 0)
        let terminatedNormally = (status & 0x7F) == 0
        let childExitCode = (status >> 8) & 0xFF
        guard waitResult == pid,
              terminatedNormally,
              childExitCode == 0
        else {
            throw HelperFailure.hdiutilFailure
        }
        return output
}

final class PosixHdiutilRunner: HdiutilRunning {
    func run(argv: [String], secret: SecretBuffer?) throws -> Data {
        guard argv.first == hdiutilPath else { throw HelperFailure.invalidRequest }
        return try spawnChild(executable: hdiutilPath, argv: argv, secret: secret)
    }
}

private let base64URLAlphabet = Array(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_".utf8
)

func encodeBase64URL(_ random: SecretBuffer) throws -> SecretBuffer {
    guard random.bytes.count == 32 else { throw HelperFailure.randomFailure }
    var encoded = [UInt8]()
    encoded.reserveCapacity(43)
    var index = 0
    while index + 3 <= random.bytes.count {
        let value = UInt32(random.bytes[index]) << 16
            | UInt32(random.bytes[index + 1]) << 8
            | UInt32(random.bytes[index + 2])
        encoded.append(base64URLAlphabet[Int((value >> 18) & 0x3F)])
        encoded.append(base64URLAlphabet[Int((value >> 12) & 0x3F)])
        encoded.append(base64URLAlphabet[Int((value >> 6) & 0x3F)])
        encoded.append(base64URLAlphabet[Int(value & 0x3F)])
        index += 3
    }
    let remaining = random.bytes.count - index
    if remaining == 2 {
        let value = UInt32(random.bytes[index]) << 16
            | UInt32(random.bytes[index + 1]) << 8
        encoded.append(base64URLAlphabet[Int((value >> 18) & 0x3F)])
        encoded.append(base64URLAlphabet[Int((value >> 12) & 0x3F)])
        encoded.append(base64URLAlphabet[Int((value >> 6) & 0x3F)])
    } else if remaining == 1 {
        let value = UInt32(random.bytes[index]) << 16
        encoded.append(base64URLAlphabet[Int((value >> 18) & 0x3F)])
        encoded.append(base64URLAlphabet[Int((value >> 12) & 0x3F)])
    }
    guard encoded.count == 43 else { throw HelperFailure.randomFailure }
    return SecretBuffer(encoded, sourceRandomByteCount: random.bytes.count)
}

private func normalizedKey(_ key: String) -> String {
    key.lowercased().replacingOccurrences(of: "_", with: "-")
}

private func recursiveValue(keys: Set<String>, object: Any) -> Any? {
    if let dictionary = object as? [String: Any] {
        for (key, value) in dictionary where keys.contains(normalizedKey(key)) {
            return value
        }
        for value in dictionary.values {
            if let found = recursiveValue(keys: keys, object: value) { return found }
        }
    } else if let array = object as? [Any] {
        for value in array {
            if let found = recursiveValue(keys: keys, object: value) { return found }
        }
    }
    return nil
}

struct EncryptionFacts {
    let uuid: String
}

func parseEncryptionFacts(_ data: Data, expectedUUID: String?) throws -> EncryptionFacts {
    let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
    guard let encrypted = recursiveValue(
        keys: ["encrypted", "image-encrypted"], object: plist
    ) as? Bool, encrypted,
    let passphraseCount = recursiveValue(
        keys: ["passphrase-count", "passphrase-slot-count"], object: plist
    ) as? NSNumber, passphraseCount.intValue == 1,
    let privateKeyCount = recursiveValue(
        keys: ["private-key-count", "private-key-slot-count"], object: plist
    ) as? NSNumber, privateKeyCount.intValue == 0,
    let uuid = recursiveValue(
        keys: ["encryption-uuid", "image-encryption-uuid"], object: plist
    ) as? String,
    !uuid.isEmpty,
    UUID(uuidString: uuid) != nil,
    expectedUUID == nil || uuid == expectedUUID
    else {
        throw HelperFailure.invalidEncryption
    }
    return EncryptionFacts(uuid: uuid)
}

private func imageBasename(_ path: String) throws -> String {
    guard !path.isEmpty,
          !path.utf8.contains(0),
          !path.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }),
          let last = path.split(separator: "/", omittingEmptySubsequences: true).last,
          !last.isEmpty
    else {
        throw HelperFailure.invalidRequest
    }
    return String(last)
}

private func transactionTag(_ request: HelperRequest) -> Data {
    Data(request.transaction_id.uuidString.lowercased().utf8)
}

private func requiredExpectedUUID(_ request: HelperRequest) throws -> String {
    guard let expected = request.expected_encryption_uuid,
          UUID(uuidString: expected) != nil
    else {
        throw HelperFailure.invalidRequest
    }
    return expected
}

private func requiredMountPath(_ request: HelperRequest) throws -> String {
    guard let mountPath = request.mount_path, !mountPath.isEmpty else {
        throw HelperFailure.invalidRequest
    }
    return mountPath
}

private func mappingDevices(
    from data: Data,
    imagePath: String,
    mountPath: String
) throws -> [String] {
    let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
    guard let dictionary = plist as? [String: Any],
          let images = dictionary["images"] as? [[String: Any]]
    else {
        throw HelperFailure.invalidMountMapping
    }
    var devices = [String]()
    for image in images {
        let candidatePath = image["image_path"] as? String ?? image["image-path"] as? String
        guard candidatePath == imagePath else { continue }
        let entities = image["system_entities"] as? [[String: Any]]
            ?? image["system-entities"] as? [[String: Any]]
            ?? []
        for entity in entities {
            let candidateMount = entity["mount_point"] as? String
                ?? entity["mount-point"] as? String
            let device = entity["dev_entry"] as? String
                ?? entity["dev-entry"] as? String
            if candidateMount == mountPath, let device, device.hasPrefix("/dev/disk") {
                devices.append(device)
            }
        }
    }
    return devices
}

private func validatedRequest(_ request: HelperRequest) throws {
    guard request.schema_version == 1,
          request.image_path.hasPrefix("/"),
          !request.image_path.utf8.contains(0)
    else {
        throw HelperFailure.invalidRequest
    }
    _ = try imageBasename(request.image_path)
    switch request.operation {
    case .create:
        guard let volumeName = request.volume_name,
              let size = request.size,
              !volumeName.isEmpty,
              !size.isEmpty,
              request.expected_encryption_uuid == nil
        else { throw HelperFailure.invalidRequest }
    case .mount, .detach:
        _ = try requiredExpectedUUID(request)
        _ = try requiredMountPath(request)
    case .inspectItem, .deleteDisposableItem:
        _ = try requiredExpectedUUID(request)
    }
}

func perform(
    request: HelperRequest,
    random: RandomSource,
    hdiutil: HdiutilRunning,
    keychain: KeychainStoring
) throws -> HelperResponse {
    try validatedRequest(request)
    let selector: (String) -> KeychainSelector = { account in
        KeychainSelector(account: account, transactionTag: transactionTag(request))
    }

    switch request.operation {
    case .create:
        guard let size = request.size, let volumeName = request.volume_name else {
            throw HelperFailure.invalidRequest
        }
        let randomBytes = try random.bytes(count: 32)
        defer { randomBytes.zeroize() }
        let secret = try encodeBase64URL(randomBytes)
        defer { secret.zeroize() }
        _ = try hdiutil.run(
            argv: [
                hdiutilPath, "create", "-stdinpass", "-encryption", "AES-256",
                "-type", "SPARSEBUNDLE", "-size", size, "-fs", "APFS",
                "-volname", volumeName, request.image_path,
            ],
            secret: secret
        )
        let encryptionData = try hdiutil.run(
            argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
            secret: nil
        )
        let facts = try parseEncryptionFacts(encryptionData, expectedUUID: nil)
        guard try keychain.countForAccount(facts.uuid) == 0 else {
            throw HelperFailure.keychainCollision
        }
        try keychain.add(
            KeychainItem(
                account: facts.uuid,
                label: try imageBasename(request.image_path),
                transactionTag: transactionTag(request),
                secret: secret
            )
        )
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: facts.uuid,
            device: nil,
            item_count: 1
        )

    case .mount:
        let expected = try requiredExpectedUUID(request)
        let mountPath = try requiredMountPath(request)
        let matches = try keychain.read(selector: selector(expected))
        guard matches.count == 1, let secret = matches.first else {
            matches.forEach { $0.zeroize() }
            throw matches.isEmpty ? HelperFailure.keychainNotFound : HelperFailure.keychainAmbiguous
        }
        defer { secret.zeroize() }
        _ = try hdiutil.run(
            argv: [
                hdiutilPath, "attach", "-stdinpass", "-owners", "on",
                "-nobrowse", "-mountpoint", mountPath, request.image_path,
            ],
            secret: secret
        )
        let encryptionData = try hdiutil.run(
            argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
            secret: nil
        )
        _ = try parseEncryptionFacts(encryptionData, expectedUUID: expected)
        let info = try hdiutil.run(argv: [hdiutilPath, "info", "-plist"], secret: nil)
        let devices = try mappingDevices(
            from: info, imagePath: request.image_path, mountPath: mountPath
        )
        guard devices.count == 1 else { throw HelperFailure.invalidMountMapping }
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: expected,
            device: devices[0],
            item_count: 1
        )

    case .detach:
        let expected = try requiredExpectedUUID(request)
        let mountPath = try requiredMountPath(request)
        let encryptionData = try hdiutil.run(
            argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
            secret: nil
        )
        _ = try parseEncryptionFacts(encryptionData, expectedUUID: expected)
        let info = try hdiutil.run(argv: [hdiutilPath, "info", "-plist"], secret: nil)
        let devices = try mappingDevices(
            from: info, imagePath: request.image_path, mountPath: mountPath
        )
        guard devices.count == 1 else { throw HelperFailure.invalidMountMapping }
        _ = try hdiutil.run(
            argv: [hdiutilPath, "detach", devices[0]],
            secret: nil
        )
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: expected,
            device: devices[0],
            item_count: nil
        )

    case .inspectItem:
        let expected = try requiredExpectedUUID(request)
        let count = try keychain.count(selector: selector(expected), action: "inspect")
        guard count == 1 else {
            throw count == 0 ? HelperFailure.keychainNotFound : HelperFailure.keychainAmbiguous
        }
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: expected,
            device: nil,
            item_count: count
        )

    case .deleteDisposableItem:
        guard request.disposable, request.cleanup_approved else {
            throw HelperFailure.cleanupNotAuthorized
        }
        let expected = try requiredExpectedUUID(request)
        let exactSelector = selector(expected)
        let count = try keychain.count(selector: exactSelector, action: "inspect")
        guard count == 1 else {
            throw count == 0 ? HelperFailure.keychainNotFound : HelperFailure.keychainAmbiguous
        }
        try keychain.delete(selector: exactSelector)
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: expected,
            device: nil,
            item_count: 0
        )
    }
}

private func responseObject(_ response: HelperResponse) -> [String: Any] {
    [
        "schema_version": response.schema_version,
        "operation": response.operation,
        "code": response.code,
        "encryption_uuid": response.encryption_uuid ?? NSNull(),
        "device": response.device ?? NSNull(),
        "item_count": response.item_count ?? NSNull(),
    ]
}

private func writeJSONObject(_ object: Any) {
    guard var data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) else {
        exit(70)
    }
    data.append(0x0A)
    FileHandle.standardOutput.write(data)
}

#if CORTEX_STORAGE_HELPER_TESTING
private func environmentValue(_ name: String) -> String? {
    name.withCString { pointer in
        guard let value = Darwin.getenv(pointer) else { return nil }
        return String(cString: value)
    }
}

final class BufferTracker {
    var buffers = [SecretBuffer]()

    func track(_ buffer: SecretBuffer) -> SecretBuffer {
        buffers.append(buffer)
        return buffer
    }

    var allZeroed: Bool {
        buffers.allSatisfy { $0.bytes.allSatisfy { $0 == 0 } }
    }
}

final class FakeRandomSource: RandomSource {
    let tracker: BufferTracker

    init(tracker: BufferTracker) {
        self.tracker = tracker
    }

    func bytes(count: Int) throws -> SecretBuffer {
        tracker.track(SecretBuffer(Array(0..<UInt8(count)), sourceRandomByteCount: count))
    }
}

final class FakeHdiutilRunner: HdiutilRunning {
    let scenario: String
    let tracker: BufferTracker
    var calls = [[String: Any]]()

    init(scenario: String, tracker: BufferTracker) {
        self.scenario = scenario
        self.tracker = tracker
    }

    private func plist(_ object: Any) throws -> Data {
        try PropertyListSerialization.data(
            fromPropertyList: object, format: .xml, options: 0
        )
    }

    func run(argv: [String], secret: SecretBuffer?) throws -> Data {
        var call: [String: Any] = [
            "argv": argv,
            "environment": childEnvironment,
            "posix_spawn_cloexec_default": true,
            "unrelated_inherited_fd_count": 0,
        ]
        if let secret {
            _ = tracker.track(secret)
            let allowed = Set(base64URLAlphabet)
            call["source_random_byte_count"] = secret.sourceRandomByteCount ?? NSNull()
            call["secret_payload_count"] = secret.bytes.count
            call["secret_payload_is_base64url"] = secret.bytes.allSatisfy { allowed.contains($0) }
            call["secret_payload_contains_nul"] = secret.bytes.contains(0)
            call["secret_wire_count"] = secret.bytes.count + 1
            call["terminal_nul_count"] = 1
        }
        calls.append(call)

        guard argv.count >= 2 else { throw HelperFailure.hdiutilFailure }
        let command = argv[1]
        if scenario == "hdiutil-error", command == "attach" {
            throw HelperFailure.hdiutilFailure
        }
        if command == "isencrypted" {
            if scenario == "bad-encryption" {
                return try plist([
                    "encrypted": true,
                    "passphrase_count": 2,
                    "private_key_count": 0,
                    "encryption_uuid": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
                ])
            }
            return try plist([
                "encrypted": true,
                "passphrase_count": 1,
                "private_key_count": 0,
                "encryption_uuid": "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE",
            ])
        }
        if command == "info" {
            let entity: [String: Any] = [
                "mount_point": "/private/tmp/CORTEX_TEST_MOUNT",
                "dev_entry": "/dev/disk99",
            ]
            let entities: [[String: Any]]
            if scenario == "mapping-zero" {
                entities = []
            } else if scenario == "mapping-multiple" {
                entities = [entity, entity]
            } else {
                entities = [entity]
            }
            return try plist([
                "images": [[
                    "image_path": "/private/tmp/CORTEX_TEST.sparsebundle",
                    "system_entities": entities,
                ]],
            ])
        }
        return Data()
    }
}

final class FakeSecurityAdapter: SecurityCalling {
    let scenario: String
    var calls = [[String: Any]]()

    init(scenario: String) {
        self.scenario = scenario
    }

    private func stringValue(_ query: [String: Any], key: CFString) -> String {
        if let value = query[key as String] as? String { return value }
        return ""
    }

    private func boolValue(_ query: [String: Any], key: CFString) -> Bool {
        query[key as String] as? Bool ?? false
    }

    private func normalizedQuery(_ query: [String: Any], action: String) -> [String: Any] {
        var result: [String: Any] = [
            "action": action,
            "class": stringValue(query, key: kSecClass) == (kSecClassGenericPassword as String)
                ? "generic-password" : "invalid",
            "account": stringValue(query, key: kSecAttrAccount),
            "service": stringValue(query, key: kSecAttrService),
            "data_protection_keychain": boolValue(query, key: kSecUseDataProtectionKeychain),
            "synchronizable": boolValue(query, key: kSecAttrSynchronizable),
            "authentication_ui": stringValue(query, key: kSecUseAuthenticationUI)
                == (kSecUseAuthenticationUIFail as String) ? "fail" : "invalid",
        ]
        if let tag = query[kSecAttrGeneric as String] as? Data {
            result["generic_tag"] = String(data: tag, encoding: .utf8) ?? ""
        }
        if query[kSecAttrLabel as String] != nil {
            result["label"] = stringValue(query, key: kSecAttrLabel)
        }
        if query[kSecAttrDescription as String] != nil {
            result["description"] = stringValue(query, key: kSecAttrDescription)
        }
        if query[kSecAttrAccessible as String] != nil {
            result["accessible"] = stringValue(query, key: kSecAttrAccessible)
                == (kSecAttrAccessibleWhenUnlockedThisDeviceOnly as String)
                ? "when-unlocked-this-device-only" : "invalid"
        }
        if let secret = query[kSecValueData as String] as? Data {
            result["secret_length"] = secret.count
        }
        return result
    }

    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?) {
        let isRead = boolValue(query, key: kSecReturnData)
        let isStrict = query[kSecAttrGeneric as String] != nil
        let action = isRead ? "read" : (isStrict ? "inspect" : "collision-check")
        calls.append(normalizedQuery(query, action: action))
        if scenario == "interaction" { return (errSecInteractionNotAllowed, nil) }
        if scenario == "zero-match" { return (errSecItemNotFound, nil) }
        let count = scenario == "multiple-match" ? 2 : 1
        if action == "collision-check", scenario != "collision" {
            return (errSecItemNotFound, nil)
        }
        if isRead {
            return (errSecSuccess, (0..<count).map { _ in Data(repeating: 65, count: 43) })
        }
        return (errSecSuccess, (0..<count).map { _ in ["matched": true] })
    }

    func add(_ query: [String: Any]) -> OSStatus {
        calls.append(normalizedQuery(query, action: "add"))
        return scenario == "interaction" ? errSecInteractionNotAllowed : errSecSuccess
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        calls.append(normalizedQuery(query, action: "delete"))
        return scenario == "interaction" ? errSecInteractionNotAllowed : errSecSuccess
    }
}

private func runFileDescriptorChild(foreignDescriptorText: String) -> Int32 {
    guard let foreignDescriptor = Int32(foreignDescriptorText) else { return 64 }
    let wire = [UInt8](FileHandle.standardInput.readDataToEndOfFile())
    let foreignClosed = Darwin.fcntl(foreignDescriptor, F_GETFD) == -1 && errno == EBADF
    let openDescriptors = (0..<64).compactMap { candidate -> Int? in
        Darwin.fcntl(Int32(candidate), F_GETFD) == -1 ? nil : candidate
    }
    let payload = wire.last == 0 ? Array(wire.dropLast()) : wire
    let allowed = Set(base64URLAlphabet)
    writeJSONObject([
        "foreign_fd_closed": foreignClosed,
        "open_fds": openDescriptors,
        "secret_wire_count": wire.count,
        "secret_payload_count": payload.count,
        "terminal_nul_count": wire.filter { $0 == 0 }.count,
        "secret_payload_is_base64url": payload.allSatisfy { allowed.contains($0) },
        "environment": [
            "PATH": environmentValue("PATH") ?? "",
            "LANG": environmentValue("LANG") ?? "",
            "LC_ALL": environmentValue("LC_ALL") ?? "",
        ],
        "home_present": environmentValue("HOME") != nil,
    ])
    return foreignClosed ? 0 : 70
}

private func runSpawnProbe() -> Int32 {
    let foreignDescriptor = Darwin.open("/dev/null", O_RDONLY)
    guard foreignDescriptor >= 0 else { return 70 }
    defer { Darwin.close(foreignDescriptor) }
    guard Darwin.fcntl(foreignDescriptor, F_SETFD, 0) == 0 else { return 70 }

    let secret = SecretBuffer([UInt8](repeating: 65, count: 43))
    let childOutput: Data
    do {
        childOutput = try spawnChild(
            executable: CommandLine.arguments[0],
            argv: [
                CommandLine.arguments[0],
                "--fd-child",
                String(foreignDescriptor),
            ],
            secret: secret
        )
    } catch {
        secret.zeroize()
        return 70
    }
    secret.zeroize()

    guard var observation = try? JSONSerialization.jsonObject(with: childOutput) as? [String: Any]
    else { return 70 }
    observation["parent_buffer_zeroed"] = secret.bytes.allSatisfy { $0 == 0 }
    writeJSONObject(observation)
    return 0
}

private func runTestHarness(request: HelperRequest, scenario: String) -> Int32 {
    let tracker = BufferTracker()
    let fakeHdiutil = FakeHdiutilRunner(scenario: scenario, tracker: tracker)
    let fakeSecurity = FakeSecurityAdapter(scenario: scenario)
    let fakeKeychain = SystemKeychainStore(
        security: fakeSecurity,
        trackSecret: { secret in _ = tracker.track(secret) }
    )
    let response: HelperResponse
    let exitCode: Int32
    do {
        response = try perform(
            request: request,
            random: FakeRandomSource(tracker: tracker),
            hdiutil: fakeHdiutil,
            keychain: fakeKeychain
        )
        exitCode = 0
    } catch let failure as HelperFailure {
        response = HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: failure.code,
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )
        exitCode = failure.exitCode
    } catch {
        response = HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "INTERNAL_ERROR",
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )
        exitCode = 70
    }
    writeJSONObject([
        "response": responseObject(response),
        "hdiutil_calls": fakeHdiutil.calls,
        "keychain_calls": fakeSecurity.calls,
        "all_buffers_zeroed": tracker.allZeroed,
        "security_agent_observations": 0,
    ])
    return exitCode
}
#endif

private func runMain() -> Int32 {
    signal(SIGPIPE, SIG_IGN)
    let arguments = Array(CommandLine.arguments.dropFirst())

    #if CORTEX_STORAGE_HELPER_TESTING
    if arguments.count == 1, arguments[0] == "--spawn-probe" {
        return runSpawnProbe()
    }
    if arguments.count == 2, arguments[0] == "--fd-child" {
        return runFileDescriptorChild(foreignDescriptorText: arguments[1])
    }
    let scenario: String?
    if arguments.count == 2, arguments[0] == "--test-scenario" {
        scenario = arguments[1]
    } else if arguments.isEmpty {
        scenario = nil
    } else {
        return 64
    }
    #else
    guard arguments.isEmpty else { return 64 }
    #endif

    let input = FileHandle.standardInput.readDataToEndOfFile()
    guard !input.isEmpty,
          let request = try? JSONDecoder().decode(HelperRequest.self, from: input)
    else {
        return 64
    }

    #if CORTEX_STORAGE_HELPER_TESTING
    if let scenario {
        return runTestHarness(request: request, scenario: scenario)
    }
    #endif

    do {
        let response = try perform(
            request: request,
            random: SystemRandomSource(),
            hdiutil: PosixHdiutilRunner(),
            keychain: SystemKeychainStore()
        )
        writeJSONObject(responseObject(response))
        return 0
    } catch let failure as HelperFailure {
        writeJSONObject(responseObject(HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: failure.code,
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )))
        return failure.exitCode
    } catch {
        writeJSONObject(responseObject(HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "INTERNAL_ERROR",
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )))
        return 70
    }
}

exit(runMain())
