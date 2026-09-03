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
    private let allocation: UnsafeMutableRawPointer
    let count: Int
    let sourceRandomByteCount: Int?
    private var erased = false

    init(count: Int, sourceRandomByteCount: Int? = nil) {
        precondition(count > 0)
        self.count = count
        self.sourceRandomByteCount = sourceRandomByteCount
        allocation = UnsafeMutableRawPointer.allocate(byteCount: count, alignment: 16)
        allocation.initializeMemory(as: UInt8.self, repeating: 0, count: count)
    }

    convenience init(copying bytes: [UInt8], sourceRandomByteCount: Int? = nil) {
        self.init(count: bytes.count, sourceRandomByteCount: sourceRandomByteCount)
        bytes.withUnsafeBytes { source in
            if let base = source.baseAddress {
                allocation.copyMemory(from: base, byteCount: bytes.count)
            }
        }
    }

    func withUnsafeBytes<R>(_ body: (UnsafeRawBufferPointer) throws -> R) rethrows -> R {
        try body(UnsafeRawBufferPointer(start: allocation, count: count))
    }

    func withUnsafeMutableBytes<R>(
        _ body: (UnsafeMutableRawBufferPointer) throws -> R
    ) rethrows -> R {
        erased = false
        return try body(UnsafeMutableRawBufferPointer(start: allocation, count: count))
    }

    func zeroize() {
        guard !erased else { return }
        memset_s(allocation, count, 0, count)
        erased = true
    }

    var isZeroed: Bool {
        erased && withUnsafeBytes { bytes in
            bytes.allSatisfy { $0 == 0 }
        }
    }

    deinit {
        zeroize()
        allocation.deallocate()
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
    case keychainSecretInvalid
    case keychainFailure
    case invalidMountMapping
    case mountCleanupUnclear

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
        case .keychainSecretInvalid: return "KEYCHAIN_SECRET_INVALID"
        case .keychainFailure: return "KEYCHAIN_FAILED"
        case .invalidMountMapping: return "MOUNT_MAPPING_INVALID"
        case .mountCleanupUnclear: return "MOUNT_CLEANUP_UNCLEAR"
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
    func run(argv: [String], secret: SecretBuffer?, deadline: Double) throws -> Data
}

protocol MonotonicClock {
    func now() -> Double
}

struct SystemMonotonicClock: MonotonicClock {
    func now() -> Double { monotonicSeconds() }
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
    func read(selector: KeychainSelector) throws -> SecretBuffer
    func delete(selector: KeychainSelector) throws
}

struct SystemRandomSource: RandomSource {
    func bytes(count: Int) throws -> SecretBuffer {
        let bytes = SecretBuffer(count: count, sourceRandomByteCount: count)
        let status = bytes.withUnsafeMutableBytes { rawBuffer -> Int32 in
            guard let base = rawBuffer.baseAddress else { return errSecParam }
            return SecRandomCopyBytes(kSecRandomDefault, count, base)
        }
        guard status == errSecSuccess else {
            bytes.zeroize()
            throw HelperFailure.randomFailure
        }
        return bytes
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
    func copyMatching(_ query: [String: Any], purpose: String) -> (OSStatus, Any?)
    func add(_ query: [String: Any]) -> OSStatus
    func delete(_ query: [String: Any]) -> OSStatus
}

struct SystemSecurityAdapter: SecurityCalling {
    func copyMatching(_ query: [String: Any], purpose: String) -> (OSStatus, Any?) {
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
        let (status, result) = security.copyMatching(query, purpose: "collision-check")
        return try resultCount(
            status: status,
            result: result
        )
    }

    func count(selector: KeychainSelector, action: String) throws -> Int {
        var query = strictQuery(selector: selector)
        query[kSecMatchLimit as String] = kSecMatchLimitAll
        query[kSecReturnAttributes as String] = true
        let (status, result) = security.copyMatching(query, purpose: action)
        return try resultCount(
            status: status,
            result: result
        )
    }

    func add(_ item: KeychainItem) throws {
        let staging = NSMutableData(length: item.secret.count)!
        item.secret.withUnsafeBytes { source in
            staging.mutableBytes.copyMemory(from: source.baseAddress!, byteCount: source.count)
        }
        defer {
            memset_s(staging.mutableBytes, staging.length, 0, staging.length)
        }
        var query = baseQuery(account: item.account)
        query[kSecAttrLabel as String] = item.label
        query[kSecAttrDescription as String] = keychainDescription
        query[kSecAttrGeneric as String] = item.transactionTag
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        query[kSecValueData as String] = staging
        let status = security.add(query)
        if status == errSecDuplicateItem { throw HelperFailure.keychainCollision }
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            return
        }
    }

    func read(selector: KeychainSelector) throws -> SecretBuffer {
        let count = try self.count(selector: selector, action: "read-count")
        guard count == 1 else {
            throw count == 0 ? HelperFailure.keychainNotFound : HelperFailure.keychainAmbiguous
        }

        var query = strictQuery(selector: selector)
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        query[kSecReturnData as String] = true
        let (status, result) = security.copyMatching(query, purpose: "read-one")
        guard status == errSecSuccess else {
            try throwForSecurityStatus(status)
            throw HelperFailure.keychainFailure
        }
        guard let data = result as? Data, !data.isEmpty else {
            throw HelperFailure.keychainFailure
        }
        let secret = SecretBuffer(count: data.count)
        secret.withUnsafeMutableBytes { destination in
            data.withUnsafeBytes { source in
                destination.copyMemory(from: source)
            }
        }
        trackSecret?(secret)
        return secret
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

enum ProcessFailureReason: String {
    case timeout = "PROCESS_TIMEOUT"
    case outputLimit = "PROCESS_OUTPUT_LIMIT"
    case stdinFailure = "PROCESS_STDIN_FAILED"
    case nonzero = "PROCESS_EXIT_NONZERO"
    case signaled = "PROCESS_SIGNALED"
    case supervision = "PROCESS_SUPERVISION_FAILED"
}

struct ProcessInvocationFailure: Error {
    let reason: ProcessFailureReason
    let stdout: Data
    let stderr: Data
    let directChildReaped: Bool
    let processGroupGone: Bool
}

final class SpawnDiagnostics {
    var stdinWriteLengths = [Int]()
    var spawnedPID: pid_t?
}

private let productionRequestDeadlineSeconds: Double = 40.0
private let productionMountCompensationReserveSeconds: Double = 12.0
private let productionMountDetachPhaseSeconds: Double = 8.0
private let productionTermGraceSeconds: Double = 2.0
private let productionReapGraceSeconds: Double = 2.0
private let productionGroupGraceSeconds: Double = 2.0

#if CORTEX_STORAGE_HELPER_TESTING
private let childTermGraceSeconds: Double = 0.15
private let childReapGraceSeconds: Double = 0.15
private let childGroupGraceSeconds: Double = 0.15
private let childOutputLimit = 4_096
#else
private let childTermGraceSeconds = productionTermGraceSeconds
private let childReapGraceSeconds = productionReapGraceSeconds
private let childGroupGraceSeconds = productionGroupGraceSeconds
private let childOutputLimit = 1_048_576
#endif

private let childTerminationBudgetSeconds = childTermGraceSeconds
    + childReapGraceSeconds
    + childGroupGraceSeconds

private func monotonicSeconds() -> Double {
    var time = timespec()
    clock_gettime(CLOCK_MONOTONIC, &time)
    return Double(time.tv_sec) + Double(time.tv_nsec) / 1_000_000_000
}

private func setNonBlocking(_ descriptor: Int32) throws {
    let flags = Darwin.fcntl(descriptor, F_GETFL)
    guard flags >= 0, Darwin.fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0 else {
        throw HelperFailure.hdiutilFailure
    }
}

private func appendAvailable(
    descriptor: Int32,
    destination: inout Data,
    eof: inout Bool,
    workDeadline: Double,
    hardDeadline: Double,
    outputLimit: Int
) throws {
    var buffer = [UInt8](repeating: 0, count: 4096)
    while true {
        guard monotonicSeconds() < workDeadline,
              monotonicSeconds() < hardDeadline else {
            throw ProcessInvocationFailure(
                reason: .timeout,
                stdout: Data(), stderr: Data(),
                directChildReaped: false, processGroupGone: false
            )
        }
        let count = Darwin.read(descriptor, &buffer, buffer.count)
        guard monotonicSeconds() < workDeadline,
              monotonicSeconds() < hardDeadline else {
            throw ProcessInvocationFailure(
                reason: .timeout,
                stdout: Data(), stderr: Data(),
                directChildReaped: false, processGroupGone: false
            )
        }
        if count > 0 {
            guard destination.count + count <= outputLimit else {
                throw ProcessInvocationFailure(
                    reason: .outputLimit,
                    stdout: Data(), stderr: Data(),
                    directChildReaped: false, processGroupGone: false
                )
            }
            destination.append(buffer, count: count)
            guard monotonicSeconds() < workDeadline,
                  monotonicSeconds() < hardDeadline else {
                throw ProcessInvocationFailure(
                    reason: .timeout,
                    stdout: Data(), stderr: Data(),
                    directChildReaped: false, processGroupGone: false
                )
            }
            continue
        }
        if count == 0 { eof = true; return }
        if errno == EINTR { continue }
        if errno == EAGAIN || errno == EWOULDBLOCK { return }
        throw HelperFailure.hdiutilFailure
    }
}

private func pauseUntil(_ deadline: Double) {
    let remaining = deadline - monotonicSeconds()
    guard remaining > 0 else { return }
    usleep(useconds_t(min(10_000.0, remaining * 1_000_000.0)))
}

private func terminateAndReap(
    pid: pid_t,
    status: inout Int32,
    hardDeadline: Double
) -> (Bool, Bool) {
    guard monotonicSeconds() < hardDeadline else { return (false, false) }
    _ = Darwin.kill(-pid, SIGTERM)
    let termDeadline = min(
        hardDeadline, monotonicSeconds() + childTermGraceSeconds
    )
    var reaped = false
    while monotonicSeconds() < termDeadline {
        let result = waitpid(pid, &status, WNOHANG)
        if result == pid { reaped = true; break }
        if result < 0 && errno == ECHILD { reaped = true; break }
        if result < 0 && errno != EINTR { break }
        pauseUntil(termDeadline)
    }
    guard monotonicSeconds() < hardDeadline else { return (reaped, false) }
    _ = Darwin.kill(-pid, SIGKILL)
    if !reaped {
        let reapDeadline = min(
            hardDeadline, monotonicSeconds() + childReapGraceSeconds
        )
        while monotonicSeconds() < reapDeadline {
            let result = waitpid(pid, &status, WNOHANG)
            if result == pid { reaped = true; break }
            if result < 0 && errno == ECHILD { reaped = true; break }
            if result < 0 && errno == EINTR { continue }
            if result < 0 { break }
            pauseUntil(reapDeadline)
        }
    }
    let groupDeadline = min(
        hardDeadline, monotonicSeconds() + childGroupGraceSeconds
    )
    var groupGone = false
    while monotonicSeconds() < groupDeadline {
        if Darwin.kill(-pid, 0) == -1 && errno == ESRCH {
            groupGone = true
            break
        }
        pauseUntil(groupDeadline)
    }
    if !groupGone,
       monotonicSeconds() < hardDeadline,
       Darwin.kill(-pid, 0) == -1,
       errno == ESRCH {
        groupGone = true
    }
    return (reaped, groupGone)
}

private func ensureProcessGroupGone(_ pid: pid_t, hardDeadline: Double) -> Bool {
    guard monotonicSeconds() < hardDeadline else { return false }
    if Darwin.kill(-pid, 0) == -1 && errno == ESRCH { return true }
    _ = Darwin.kill(-pid, SIGTERM)
    var deadline = min(
        hardDeadline, monotonicSeconds() + childTermGraceSeconds
    )
    while monotonicSeconds() < deadline {
        if Darwin.kill(-pid, 0) == -1 && errno == ESRCH { return true }
        pauseUntil(deadline)
    }
    guard monotonicSeconds() < hardDeadline else { return false }
    _ = Darwin.kill(-pid, SIGKILL)
    deadline = min(
        hardDeadline, monotonicSeconds() + childGroupGraceSeconds
    )
    while monotonicSeconds() < deadline {
        if Darwin.kill(-pid, 0) == -1 && errno == ESRCH { return true }
        pauseUntil(deadline)
    }
    guard monotonicSeconds() < hardDeadline else { return false }
    return Darwin.kill(-pid, 0) == -1 && errno == ESRCH
}

private func waitStatusExited(_ status: Int32) -> Bool {
    (status & 0x7F) == 0
}

private func waitStatusSignaled(_ status: Int32) -> Bool {
    let termination = status & 0x7F
    return termination != 0 && termination != 0x7F
}

private func waitStatusExitCode(_ status: Int32) -> Int32 {
    (status >> 8) & 0xFF
}

private func spawnChild(
    executable: String,
    argv: [String],
    secret: SecretBuffer?,
    deadline: Double,
    diagnostics: SpawnDiagnostics? = nil,
    outputLimit: Int = childOutputLimit
) throws -> Data {
    guard argv.count >= 2, argv[0] == executable else { throw HelperFailure.invalidRequest }
    let workDeadline = deadline - childTerminationBudgetSeconds
    guard monotonicSeconds() < workDeadline else {
        throw ProcessInvocationFailure(
            reason: .timeout, stdout: Data(), stderr: Data(),
            directChildReaped: true, processGroupGone: true
        )
    }
    var inputPipe = [Int32](repeating: -1, count: 2)
    var outputPipe = [Int32](repeating: -1, count: 2)
    var errorPipe = [Int32](repeating: -1, count: 2)
    guard Darwin.pipe(&inputPipe) == 0 else { throw HelperFailure.hdiutilFailure }
    guard Darwin.pipe(&outputPipe) == 0 else {
        Darwin.close(inputPipe[0]); Darwin.close(inputPipe[1])
        throw HelperFailure.hdiutilFailure
    }
    guard Darwin.pipe(&errorPipe) == 0 else {
        Darwin.close(inputPipe[0]); Darwin.close(inputPipe[1])
        Darwin.close(outputPipe[0]); Darwin.close(outputPipe[1])
        throw HelperFailure.hdiutilFailure
    }

    func closeDescriptor(_ descriptor: inout Int32) {
        if descriptor >= 0 { Darwin.close(descriptor); descriptor = -1 }
    }
    defer {
        closeDescriptor(&inputPipe[0]); closeDescriptor(&inputPipe[1])
        closeDescriptor(&outputPipe[0]); closeDescriptor(&outputPipe[1])
        closeDescriptor(&errorPipe[0]); closeDescriptor(&errorPipe[1])
    }

    var actions: posix_spawn_file_actions_t?
    guard posix_spawn_file_actions_init(&actions) == 0 else { throw HelperFailure.hdiutilFailure }
    defer { posix_spawn_file_actions_destroy(&actions) }
    guard posix_spawn_file_actions_adddup2(&actions, inputPipe[0], STDIN_FILENO) == 0,
          posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDOUT_FILENO) == 0,
          posix_spawn_file_actions_adddup2(&actions, errorPipe[1], STDERR_FILENO) == 0
    else { throw HelperFailure.hdiutilFailure }
    for descriptor in [inputPipe[0], inputPipe[1], outputPipe[0], outputPipe[1], errorPipe[0], errorPipe[1]] {
        guard posix_spawn_file_actions_addclose(&actions, descriptor) == 0 else {
            throw HelperFailure.hdiutilFailure
        }
    }

    var attributes: posix_spawnattr_t?
    guard posix_spawnattr_init(&attributes) == 0 else { throw HelperFailure.hdiutilFailure }
    defer { posix_spawnattr_destroy(&attributes) }
    let flags = Int16(POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETPGROUP)
    guard posix_spawnattr_setflags(&attributes, flags) == 0,
          posix_spawnattr_setpgroup(&attributes, 0) == 0
    else { throw HelperFailure.hdiutilFailure }

    guard monotonicSeconds() < workDeadline else {
        throw ProcessInvocationFailure(
            reason: .timeout, stdout: Data(), stderr: Data(),
            directChildReaped: true, processGroupGone: true
        )
    }
    var pid = pid_t()
    let spawnStatus: Int32 = withCStringArray(argv) { argvPointer in
        withCStringArray(childEnvironment) { environmentPointer in
            executable.withCString { executablePointer in
                posix_spawn(
                    &pid, executablePointer, &actions, &attributes,
                    argvPointer, environmentPointer
                )
            }
        }
    }
    guard spawnStatus == 0 else { throw HelperFailure.hdiutilFailure }
    diagnostics?.spawnedPID = pid
    closeDescriptor(&inputPipe[0]); closeDescriptor(&outputPipe[1]); closeDescriptor(&errorPipe[1])
    do {
        try setNonBlocking(inputPipe[1])
        try setNonBlocking(outputPipe[0])
        try setNonBlocking(errorPipe[0])
    } catch {
        var status: Int32 = 0
        let (reaped, groupGone) = terminateAndReap(
            pid: pid, status: &status, hardDeadline: deadline
        )
        throw ProcessInvocationFailure(
            reason: .supervision, stdout: Data(), stderr: Data(),
            directChildReaped: reaped, processGroupGone: groupGone
        )
    }

    var stdout = Data()
    var stderr = Data()
    var stdoutEOF = false
    var stderrEOF = false
    var secretOffset = 0
    var nulWritten = secret == nil
    if secret == nil { closeDescriptor(&inputPipe[1]) }
    var childStatus: Int32 = 0
    var childReaped = false
    var failureReason: ProcessFailureReason?

    while !childReaped || !stdoutEOF || !stderrEOF {
        if monotonicSeconds() >= workDeadline { failureReason = .timeout; break }
        var pollDescriptors = [
            pollfd(fd: inputPipe[1], events: inputPipe[1] >= 0 ? Int16(POLLOUT) : 0, revents: 0),
            pollfd(fd: outputPipe[0], events: Int16(POLLIN), revents: 0),
            pollfd(fd: errorPipe[0], events: Int16(POLLIN), revents: 0),
        ]
        let remainingMilliseconds = max(
            0, Int32((workDeadline - monotonicSeconds()) * 1_000.0)
        )
        let pollResult = Darwin.poll(
            &pollDescriptors,
            nfds_t(pollDescriptors.count),
            min(20, remainingMilliseconds)
        )
        if pollResult < 0 && errno != EINTR { failureReason = .supervision; break }

        do {
            try appendAvailable(
                descriptor: outputPipe[0], destination: &stdout, eof: &stdoutEOF,
                workDeadline: workDeadline, hardDeadline: deadline,
                outputLimit: outputLimit
            )
            try appendAvailable(
                descriptor: errorPipe[0], destination: &stderr, eof: &stderrEOF,
                workDeadline: workDeadline, hardDeadline: deadline,
                outputLimit: outputLimit
            )
        } catch let failure as ProcessInvocationFailure {
            failureReason = failure.reason
            break
        } catch {
            failureReason = .supervision
            break
        }

        if inputPipe[1] >= 0, pollDescriptors[0].revents & Int16(POLLOUT) != 0 {
            if let secret, secretOffset < secret.count {
                let result = secret.withUnsafeBytes { bytes in
                    Darwin.write(
                        inputPipe[1], bytes.baseAddress!.advanced(by: secretOffset),
                        bytes.count - secretOffset
                    )
                }
                if result > 0 { secretOffset += result; diagnostics?.stdinWriteLengths.append(result) }
                else if result < 0 && errno != EAGAIN && errno != EINTR { failureReason = .stdinFailure }
            } else if !nulWritten {
                var nul: UInt8 = 0
                let result = Darwin.write(inputPipe[1], &nul, 1)
                if result == 1 { nulWritten = true; diagnostics?.stdinWriteLengths.append(1) }
                else if result < 0 && errno != EAGAIN && errno != EINTR { failureReason = .stdinFailure }
            }
            if secretOffset == (secret?.count ?? 0), nulWritten {
                closeDescriptor(&inputPipe[1])
            }
        }
        if inputPipe[1] >= 0,
           pollDescriptors[0].revents & Int16(POLLERR | POLLHUP) != 0,
           secretOffset < (secret?.count ?? 0) || !nulWritten {
            failureReason = .stdinFailure
        }
        if failureReason != nil { break }
        let waitResult = waitpid(pid, &childStatus, WNOHANG)
        if waitResult == pid { childReaped = true }
        else if waitResult < 0 && errno != EINTR { failureReason = .supervision; break }
    }

    if let reason = failureReason {
        closeDescriptor(&inputPipe[1])
        let (reaped, groupGone) = terminateAndReap(
            pid: pid, status: &childStatus, hardDeadline: deadline
        )
        throw ProcessInvocationFailure(
            reason: reason,
            stdout: stdout,
            stderr: stderr,
            directChildReaped: reaped,
            processGroupGone: groupGone
        )
    }
    guard childReaped else {
        let (reaped, groupGone) = terminateAndReap(
            pid: pid, status: &childStatus, hardDeadline: deadline
        )
        throw ProcessInvocationFailure(
            reason: .supervision, stdout: stdout, stderr: stderr,
            directChildReaped: reaped, processGroupGone: groupGone
        )
    }
    let groupGone = ensureProcessGroupGone(pid, hardDeadline: deadline)
    guard groupGone else {
        throw ProcessInvocationFailure(
            reason: .supervision, stdout: stdout, stderr: stderr,
            directChildReaped: true, processGroupGone: false
        )
    }
    if waitStatusSignaled(childStatus) {
        throw ProcessInvocationFailure(
            reason: .signaled, stdout: stdout, stderr: stderr,
            directChildReaped: true, processGroupGone: true
        )
    }
    guard waitStatusExited(childStatus) else {
        throw ProcessInvocationFailure(
            reason: .supervision, stdout: stdout, stderr: stderr,
            directChildReaped: true, processGroupGone: true
        )
    }
    let exitCode = waitStatusExitCode(childStatus)
    guard exitCode == 0 else {
        throw ProcessInvocationFailure(
            reason: .nonzero, stdout: stdout, stderr: stderr,
            directChildReaped: true, processGroupGone: true
        )
    }
    return stdout
}

final class PosixHdiutilRunner: HdiutilRunning {
    func run(argv: [String], secret: SecretBuffer?, deadline: Double) throws -> Data {
        guard argv.first == hdiutilPath else { throw HelperFailure.invalidRequest }
        return try spawnChild(
            executable: hdiutilPath, argv: argv, secret: secret, deadline: deadline
        )
    }
}

private let base64URLAlphabet = Array(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_".utf8
)

func encodeBase64URL(_ random: SecretBuffer) throws -> SecretBuffer {
    guard random.count == 32 else { throw HelperFailure.randomFailure }
    let encoded = SecretBuffer(count: 43, sourceRandomByteCount: random.count)
    random.withUnsafeBytes { source in
        encoded.withUnsafeMutableBytes { destination in
            var sourceIndex = 0
            var destinationIndex = 0
            while sourceIndex + 3 <= source.count {
                let value = UInt32(source[sourceIndex]) << 16
                    | UInt32(source[sourceIndex + 1]) << 8
                    | UInt32(source[sourceIndex + 2])
                destination[destinationIndex] = base64URLAlphabet[Int((value >> 18) & 0x3F)]
                destination[destinationIndex + 1] = base64URLAlphabet[Int((value >> 12) & 0x3F)]
                destination[destinationIndex + 2] = base64URLAlphabet[Int((value >> 6) & 0x3F)]
                destination[destinationIndex + 3] = base64URLAlphabet[Int(value & 0x3F)]
                sourceIndex += 3
                destinationIndex += 4
            }
            let value = UInt32(source[sourceIndex]) << 16
                | UInt32(source[sourceIndex + 1]) << 8
            destination[destinationIndex] = base64URLAlphabet[Int((value >> 18) & 0x3F)]
            destination[destinationIndex + 1] = base64URLAlphabet[Int((value >> 12) & 0x3F)]
            destination[destinationIndex + 2] = base64URLAlphabet[Int((value >> 6) & 0x3F)]
        }
    }
    return encoded
}

private func isValidDiskImageSecret(_ secret: SecretBuffer) -> Bool {
    guard secret.count == 43 else { return false }
    return secret.withUnsafeBytes { bytes in
        bytes.allSatisfy { byte in
            (byte >= 65 && byte <= 90)
                || (byte >= 97 && byte <= 122)
                || (byte >= 48 && byte <= 57)
                || byte == 45
                || byte == 95
        }
    }
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

private func imageEntryCount(from data: Data, imagePath: String) throws -> Int {
    let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
    guard let dictionary = plist as? [String: Any],
          let images = dictionary["images"] as? [[String: Any]]
    else { throw HelperFailure.invalidMountMapping }
    return images.filter { image in
        let candidate = image["image_path"] as? String ?? image["image-path"] as? String
        return candidate == imagePath
    }.count
}

private func attachReceiptDevices(from data: Data, mountPath: String) -> [String] {
    guard let output = String(data: data, encoding: .utf8) else { return [] }
    return output.split(separator: "\n").compactMap { line in
        let fields = line.split(separator: "\t", omittingEmptySubsequences: false)
        guard fields.count >= 3,
              String(fields.last!) == mountPath,
              fields[0].hasPrefix("/dev/disk")
        else { return nil }
        return String(fields[0])
    }
}

private func containsControl(_ value: String) -> Bool {
    value.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
}

private func isLexicallySafeAbsolutePath(_ value: String) -> Bool {
    guard value.hasPrefix("/"), !containsControl(value), !value.utf8.contains(0) else {
        return false
    }
    let components = value.split(separator: "/", omittingEmptySubsequences: false)
    guard components.count > 1, components[0].isEmpty else { return false }
    return components.dropFirst().allSatisfy { !$0.isEmpty && $0 != "." && $0 != ".." }
}

private func validatedRequest(_ request: HelperRequest) throws {
    guard request.schema_version == 1,
          isLexicallySafeAbsolutePath(request.image_path),
          let mountPath = request.mount_path,
          isLexicallySafeAbsolutePath(mountPath),
          let volumeName = request.volume_name,
          let size = request.size,
          !containsControl(volumeName),
          !containsControl(size)
    else {
        throw HelperFailure.invalidRequest
    }
    _ = try imageBasename(request.image_path)
    let isSpike = size == "64m" && volumeName == "CORTEX_BRIDGE_SPIKE"
    let isProduction = size == "256g" && volumeName == "CORTEX_BRIDGE_2026_09"
    guard (isSpike && request.disposable) || (isProduction && !request.disposable) else {
        throw HelperFailure.invalidRequest
    }
    switch request.operation {
    case .create:
        guard request.expected_encryption_uuid == nil else {
            throw HelperFailure.invalidRequest
        }
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
    keychain: KeychainStoring,
    clock: MonotonicClock = SystemMonotonicClock()
) throws -> HelperResponse {
    let finalDeadline = clock.now() + productionRequestDeadlineSeconds
    try validatedRequest(request)
    let normalDeadline = request.operation == .mount
        ? finalDeadline - productionMountCompensationReserveSeconds
        : finalDeadline
    let mountDetachDeadline = min(
        finalDeadline,
        normalDeadline + productionMountDetachPhaseSeconds
    )
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
            secret: secret,
            deadline: normalDeadline
        )
        let encryptionData = try hdiutil.run(
            argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
            secret: nil,
            deadline: normalDeadline
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
        let secret = try keychain.read(selector: selector(expected))
        defer { secret.zeroize() }
        guard isValidDiskImageSecret(secret) else {
            throw HelperFailure.keychainSecretInvalid
        }
        let baselineInfo = try hdiutil.run(
            argv: [hdiutilPath, "info", "-plist"], secret: nil,
            deadline: normalDeadline
        )
        let baselineDevices = try mappingDevices(
            from: baselineInfo, imagePath: request.image_path, mountPath: mountPath
        )
        guard baselineDevices.isEmpty,
              try imageEntryCount(from: baselineInfo, imagePath: request.image_path) == 0
        else { throw HelperFailure.invalidMountMapping }

        var receipt: String?
        var originalFailure: Error?
        do {
            let attachOutput = try hdiutil.run(
                argv: [
                    hdiutilPath, "attach", "-stdinpass", "-owners", "on",
                    "-nobrowse", "-mountpoint", mountPath, request.image_path,
                ],
                secret: secret,
                deadline: normalDeadline
            )
            let outputReceipts = attachReceiptDevices(from: attachOutput, mountPath: mountPath)
            guard outputReceipts.count <= 1 else {
                throw HelperFailure.mountCleanupUnclear
            }
            if outputReceipts.count == 1 {
                receipt = outputReceipts[0]
            }
            let postInfo = try hdiutil.run(
                argv: [hdiutilPath, "info", "-plist"], secret: nil,
                deadline: normalDeadline
            )
            let postDevices = try mappingDevices(
                from: postInfo, imagePath: request.image_path, mountPath: mountPath
            )
            if postDevices.count > 1 {
                receipt = nil
                throw HelperFailure.mountCleanupUnclear
            }
            if postDevices.count == 1 {
                guard outputReceipts.isEmpty || outputReceipts == postDevices else {
                    receipt = nil
                    throw HelperFailure.mountCleanupUnclear
                }
                receipt = postDevices[0]
            } else if receipt != nil {
                throw HelperFailure.invalidMountMapping
            } else {
                throw HelperFailure.mountCleanupUnclear
            }

            let encryptionData = try hdiutil.run(
                argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
                secret: nil,
                deadline: normalDeadline
            )
            _ = try parseEncryptionFacts(encryptionData, expectedUUID: expected)
            let finalInfo = try hdiutil.run(
                argv: [hdiutilPath, "info", "-plist"], secret: nil,
                deadline: normalDeadline
            )
            let finalDevices = try mappingDevices(
                from: finalInfo, imagePath: request.image_path, mountPath: mountPath
            )
            guard finalDevices == [receipt!],
                  try imageEntryCount(from: finalInfo, imagePath: request.image_path) == 1
            else { throw HelperFailure.invalidMountMapping }
        } catch let failure as ProcessInvocationFailure {
            if receipt == nil {
                let outputReceipts = attachReceiptDevices(
                    from: failure.stdout, mountPath: mountPath
                )
                if outputReceipts.count == 1 {
                    receipt = outputReceipts[0]
                }
            }
            originalFailure = HelperFailure.hdiutilFailure
        } catch {
            originalFailure = error
        }

        if let originalFailure {
            guard let receipt else { throw HelperFailure.mountCleanupUnclear }
            do {
                _ = try hdiutil.run(
                    argv: [hdiutilPath, "detach", receipt], secret: nil,
                    deadline: mountDetachDeadline
                )
                let cleanupInfo = try hdiutil.run(
                    argv: [hdiutilPath, "info", "-plist"], secret: nil,
                    deadline: finalDeadline
                )
                let remaining = try mappingDevices(
                    from: cleanupInfo, imagePath: request.image_path, mountPath: mountPath
                )
                guard remaining.isEmpty,
                      try imageEntryCount(
                        from: cleanupInfo, imagePath: request.image_path
                      ) == 0
                else { throw HelperFailure.mountCleanupUnclear }
            } catch {
                throw HelperFailure.mountCleanupUnclear
            }
            if let helperFailure = originalFailure as? HelperFailure { throw helperFailure }
            throw HelperFailure.hdiutilFailure
        }
        guard let receipt else { throw HelperFailure.mountCleanupUnclear }
        return HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: "OK",
            encryption_uuid: expected,
            device: receipt,
            item_count: 1
        )

    case .detach:
        let expected = try requiredExpectedUUID(request)
        let mountPath = try requiredMountPath(request)
        let encryptionData = try hdiutil.run(
            argv: [hdiutilPath, "isencrypted", "-plist", request.image_path],
            secret: nil,
            deadline: normalDeadline
        )
        _ = try parseEncryptionFacts(encryptionData, expectedUUID: expected)
        let info = try hdiutil.run(
            argv: [hdiutilPath, "info", "-plist"], secret: nil,
            deadline: normalDeadline
        )
        let devices = try mappingDevices(
            from: info, imagePath: request.image_path, mountPath: mountPath
        )
        guard devices.count == 1,
              try imageEntryCount(from: info, imagePath: request.image_path) == 1
        else { throw HelperFailure.invalidMountMapping }
        do {
            _ = try hdiutil.run(
                argv: [hdiutilPath, "detach", devices[0]],
                secret: nil,
                deadline: normalDeadline
            )
            let detachedInfo = try hdiutil.run(
                argv: [hdiutilPath, "info", "-plist"], secret: nil,
                deadline: normalDeadline
            )
            guard try imageEntryCount(
                from: detachedInfo, imagePath: request.image_path
            ) == 0 else { throw HelperFailure.mountCleanupUnclear }
        } catch {
            throw HelperFailure.mountCleanupUnclear
        }
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
        buffers.allSatisfy { $0.isZeroed }
    }
}

final class FakeRandomSource: RandomSource {
    let tracker: BufferTracker

    init(tracker: BufferTracker) {
        self.tracker = tracker
    }

    func bytes(count: Int) throws -> SecretBuffer {
        let buffer = SecretBuffer(count: count, sourceRandomByteCount: count)
        buffer.withUnsafeMutableBytes { bytes in
            for index in 0..<count { bytes[index] = UInt8(index) }
        }
        return tracker.track(buffer)
    }
}

final class FakeMonotonicClock: MonotonicClock {
    private(set) var value: Double = 100.0

    func now() -> Double { value }
    func advance(_ seconds: Double) { value += seconds }
}

final class FakeHdiutilRunner: HdiutilRunning {
    let scenario: String
    let tracker: BufferTracker
    let clock: FakeMonotonicClock
    var calls = [[String: Any]]()
    var attached: Bool
    var infoCalls = 0
    var normalDeadline: Double?
    var compensationStarted = false

    init(
        scenario: String,
        tracker: BufferTracker,
        operation: Operation,
        clock: FakeMonotonicClock
    ) {
        self.scenario = scenario
        self.tracker = tracker
        self.clock = clock
        attached = operation == .detach
    }

    private func plist(_ object: Any) throws -> Data {
        try PropertyListSerialization.data(
            fromPropertyList: object, format: .xml, options: 0
        )
    }

    func run(argv: [String], secret: SecretBuffer?, deadline: Double) throws -> Data {
        if normalDeadline == nil { normalDeadline = deadline }
        let startedAt = clock.now()
        let workDeadline = deadline - childTerminationBudgetSeconds
        var call: [String: Any] = [
            "argv": argv,
            "environment": childEnvironment,
            "posix_spawn_cloexec_default": true,
            "unrelated_inherited_fd_count": 0,
            "absolute_deadline": deadline,
            "hard_deadline": deadline,
            "work_deadline": workDeadline,
            "termination_budget": deadline - workDeadline,
            "started_at": startedAt,
            "remaining_budget_before": max(0, deadline - startedAt),
            "deadline_phase": compensationStarted || deadline > normalDeadline!
                ? "compensation" : "normal",
            "spawned": startedAt < workDeadline,
            "termination_started_at": NSNull(),
        ]
        if let secret {
            _ = tracker.track(secret)
            let allowed = Set(base64URLAlphabet)
            call["source_random_byte_count"] = secret.sourceRandomByteCount ?? NSNull()
            call["secret_payload_count"] = secret.count
            secret.withUnsafeBytes { bytes in
                call["secret_payload_is_base64url"] = bytes.allSatisfy { allowed.contains($0) }
                call["secret_payload_contains_nul"] = bytes.contains(0)
            }
            call["secret_wire_count"] = secret.count + 1
            call["terminal_nul_count"] = 1
        }
        calls.append(call)
        let callIndex = calls.count - 1
        defer { calls[callIndex]["finished_at"] = clock.now() }

        guard startedAt < workDeadline else {
            throw ProcessInvocationFailure(
                reason: .timeout, stdout: Data(), stderr: Data(),
                directChildReaped: true, processGroupGone: true
            )
        }

        guard argv.count >= 2 else { throw HelperFailure.hdiutilFailure }
        let command = argv[1]
        if scenario == "slow-series", command == "create" {
            clock.advance(20)
        }
        if scenario == "deadline-compensation", command == "info", infoCalls == 0 {
            clock.advance(26)
        }
        if command == "attach" {
            if scenario == "hdiutil-error" { throw HelperFailure.hdiutilFailure }
            attached = true
            let receipt = Data("/dev/disk99\tApple_APFS\t/private/tmp/CORTEX_TEST_MOUNT\n".utf8)
            if scenario == "deadline-compensation" {
                clock.advance(2)
                compensationStarted = true
                throw ProcessInvocationFailure(
                    reason: .timeout, stdout: receipt, stderr: Data(),
                    directChildReaped: true, processGroupGone: true
                )
            }
            if scenario == "attach-timeout-with-receipt" {
                throw ProcessInvocationFailure(
                    reason: .timeout, stdout: receipt, stderr: Data(),
                    directChildReaped: true, processGroupGone: true
                )
            }
            if scenario == "attach-timeout-no-receipt" {
                throw ProcessInvocationFailure(
                    reason: .timeout, stdout: Data(), stderr: Data(),
                    directChildReaped: true, processGroupGone: true
                )
            }
            return receipt
        }
        if command == "detach" {
            if scenario == "compensation-detach-failure" {
                throw HelperFailure.hdiutilFailure
            }
            if scenario == "compensation-window-exhausted" {
                clock.advance(max(
                    0,
                    productionMountCompensationReserveSeconds
                        - childTerminationBudgetSeconds
                ))
            }
            attached = false
            return Data()
        }
        if command == "isencrypted" {
            if (scenario == "hard-deadline-compensation"
                || scenario == "compensation-window-exhausted"), attached {
                clock.advance(max(0, workDeadline - clock.now()))
                calls[callIndex]["termination_started_at"] = clock.now()
                clock.advance(max(0, deadline - clock.now()))
                compensationStarted = true
                throw ProcessInvocationFailure(
                    reason: .timeout, stdout: Data(), stderr: Data(),
                    directChildReaped: true, processGroupGone: true
                )
            }
            if scenario == "bad-encryption" || scenario == "post-encryption-failure"
                || scenario == "compensation-detach-failure" {
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
            infoCalls += 1
            if scenario == "postcheck-timeout", attached, infoCalls == 2 {
                throw ProcessInvocationFailure(
                    reason: .timeout, stdout: Data(), stderr: Data(),
                    directChildReaped: true, processGroupGone: true
                )
            }
            if !attached {
                return try plist(["images": []])
            }
            let entity: [String: Any] = [
                "mount_point": "/private/tmp/CORTEX_TEST_MOUNT",
                "dev_entry": "/dev/disk99",
            ]
            let entities: [[String: Any]]
            if scenario == "mapping-zero" || scenario == "post-mapping-failure"
                || scenario == "attach-timeout-no-receipt" {
                entities = []
            } else if scenario == "mapping-multiple" || scenario == "post-mapping-ambiguous" {
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
    var stagingBuffers = [NSMutableData]()
    var secretMaterializations = 0

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
        if boolValue(query, key: kSecReturnData) {
            result["return_data"] = true
        }
        if stringValue(query, key: kSecMatchLimit) == (kSecMatchLimitOne as String) {
            result["match_limit"] = "one"
        }
        return result
    }

    func copyMatching(_ query: [String: Any], purpose: String) -> (OSStatus, Any?) {
        let isRead = boolValue(query, key: kSecReturnData)
        calls.append(normalizedQuery(query, action: purpose))
        if scenario == "interaction" { return (errSecInteractionNotAllowed, nil) }
        if scenario == "zero-match" { return (errSecItemNotFound, nil) }
        let count = scenario == "multiple-match" ? 2 : 1
        if purpose == "collision-check", scenario != "collision" {
            return (errSecItemNotFound, nil)
        }
        if isRead {
            secretMaterializations += 1
            var secret = [UInt8](repeating: 65, count: 43)
            switch scenario {
            case "secret-length-42": secret.removeLast()
            case "secret-length-44": secret.append(65)
            case "secret-nul": secret[0] = 0
            case "secret-plus": secret[0] = 43
            case "secret-slash": secret[0] = 47
            case "secret-padding": secret[0] = 61
            case "secret-non-ascii": secret[0] = 0xFF
            default: break
            }
            return (errSecSuccess, Data(secret))
        }
        return (errSecSuccess, (0..<count).map { _ in ["matched": true] })
    }

    func add(_ query: [String: Any]) -> OSStatus {
        calls.append(normalizedQuery(query, action: "add"))
        if let staging = query[kSecValueData as String] as? NSMutableData {
            stagingBuffers.append(staging)
        }
        if scenario == "add-collision" { return errSecDuplicateItem }
        if scenario == "add-interaction" { return errSecInteractionNotAllowed }
        return errSecSuccess
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        calls.append(normalizedQuery(query, action: "delete"))
        return scenario == "interaction" ? errSecInteractionNotAllowed : errSecSuccess
    }

    var allStagingZeroed: Bool {
        stagingBuffers.allSatisfy { staging in
            let bytes = UnsafeRawBufferPointer(
                start: staging.bytes,
                count: staging.length
            )
            return bytes.allSatisfy { $0 == 0 }
        }
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

    let secret = SecretBuffer(copying: [UInt8](repeating: 65, count: 43))
    let diagnostics = SpawnDiagnostics()
    let childOutput: Data
    do {
        childOutput = try spawnChild(
            executable: CommandLine.arguments[0],
            argv: [
                CommandLine.arguments[0],
                "--fd-child",
                String(foreignDescriptor),
            ],
            secret: secret,
            deadline: monotonicSeconds() + 0.80,
            diagnostics: diagnostics
        )
    } catch {
        secret.zeroize()
        return 70
    }
    secret.zeroize()

    guard var observation = try? JSONSerialization.jsonObject(with: childOutput) as? [String: Any]
    else { return 70 }
    observation["parent_buffer_zeroed"] = secret.isZeroed
    observation["stdin_write_lengths"] = diagnostics.stdinWriteLengths
    observation["combined_wire_buffer_created"] = false
    writeJSONObject(observation)
    return 0
}

private func runDeadlineDrainProbe() -> Int32 {
    let hardBudgetSeconds = 0.50
    let schedulerToleranceSeconds = 0.15
    let outputLimit = 256 * 1_024 * 1_024
    let secret = SecretBuffer(copying: [UInt8](repeating: 65, count: 43))
    let diagnostics = SpawnDiagnostics()
    let startedAt = monotonicSeconds()
    var code = "UNEXPECTED_SUCCESS"
    var capturedOutputCount = 0
    var directChildReaped = false
    var processGroupGone = false
    do {
        _ = try spawnChild(
            executable: CommandLine.arguments[0],
            argv: [
                CommandLine.arguments[0],
                "--process-child",
                "continuous-output",
            ],
            secret: secret,
            deadline: startedAt + hardBudgetSeconds,
            diagnostics: diagnostics,
            outputLimit: outputLimit
        )
    } catch let failure as ProcessInvocationFailure {
        code = failure.reason.rawValue
        capturedOutputCount = failure.stdout.count + failure.stderr.count
        directChildReaped = failure.directChildReaped
        processGroupGone = failure.processGroupGone
    } catch {
        code = ProcessFailureReason.supervision.rawValue
    }
    secret.zeroize()
    let elapsedSeconds = monotonicSeconds() - startedAt
    let childPID = diagnostics.spawnedPID ?? -1
    writeJSONObject([
        "code": code,
        "hard_budget_seconds": hardBudgetSeconds,
        "scheduler_tolerance_seconds": schedulerToleranceSeconds,
        "elapsed_seconds": elapsedSeconds,
        "direct_child_reaped": directChildReaped,
        "process_group_gone": processGroupGone,
        "captured_output_count": capturedOutputCount,
        "output_limit": outputLimit,
        "secret_buffer_zeroed": secret.isZeroed,
        "child_pid": Int(childPID),
    ])
    guard code == ProcessFailureReason.timeout.rawValue,
          directChildReaped,
          processGroupGone,
          capturedOutputCount <= outputLimit,
          secret.isZeroed,
          childPID > 1,
          elapsedSeconds <= hardBudgetSeconds + schedulerToleranceSeconds
    else { return 70 }
    return 0
}

private func runProcessChild(scenario: String) -> Int32 {
    switch scenario {
    case "sleep":
        usleep(1_000_000)
        return 0
    case "ignore-term-grandchild":
        signal(SIGTERM, SIG_IGN)
        var child = pid_t()
        let arguments = [CommandLine.arguments[0], "--process-child", "grandchild-ignore"]
        _ = withCStringArray(arguments) { argvPointer in
            withCStringArray(childEnvironment) { environmentPointer in
                CommandLine.arguments[0].withCString { executablePointer in
                    posix_spawn(
                        &child, executablePointer, nil, nil,
                        argvPointer, environmentPointer
                    )
                }
            }
        }
        usleep(2_000_000)
        return 0
    case "grandchild-ignore":
        signal(SIGTERM, SIG_IGN)
        usleep(2_000_000)
        return 0
    case "stdout-cap":
        let bytes = [UInt8](repeating: 65, count: childOutputLimit + 1024)
        _ = bytes.withUnsafeBytes { Darwin.write(STDOUT_FILENO, $0.baseAddress!, $0.count) }
        return 0
    case "stderr-cap":
        let bytes = [UInt8](repeating: 66, count: childOutputLimit + 1024)
        _ = bytes.withUnsafeBytes { Darwin.write(STDERR_FILENO, $0.baseAddress!, $0.count) }
        return 0
    case "epipe":
        Darwin.close(STDIN_FILENO)
        usleep(100_000)
        return 0
    case "nonzero":
        return 7
    case "signal":
        signal(SIGTERM, SIG_DFL)
        _ = Darwin.kill(getpid(), SIGTERM)
        return 70
    case "continuous-output":
        signal(SIGTERM, SIG_IGN)
        let bytes = [UInt8](repeating: 67, count: 4096)
        while true {
            let written = bytes.withUnsafeBytes {
                Darwin.write(STDOUT_FILENO, $0.baseAddress!, $0.count)
            }
            if written > 0 { continue }
            if written < 0 && errno == EINTR { continue }
            return 0
        }
    default:
        return 64
    }
}

private func runProcessScenario(_ scenario: String) -> Int32 {
    let secret = scenario == "epipe"
        ? SecretBuffer(copying: [UInt8](repeating: 65, count: 131_072))
        : nil
    defer { secret?.zeroize() }
    do {
        _ = try spawnChild(
            executable: CommandLine.arguments[0],
            argv: [CommandLine.arguments[0], "--process-child", scenario],
            secret: secret,
            deadline: monotonicSeconds() + 0.80
        )
        writeJSONObject([
            "code": "UNEXPECTED_SUCCESS",
            "direct_child_reaped": true,
            "process_group_gone": true,
        ])
    } catch let failure as ProcessInvocationFailure {
        writeJSONObject([
            "code": failure.reason.rawValue,
            "direct_child_reaped": failure.directChildReaped,
            "process_group_gone": failure.processGroupGone,
        ])
    } catch {
        writeJSONObject([
            "code": ProcessFailureReason.supervision.rawValue,
            "direct_child_reaped": false,
            "process_group_gone": false,
        ])
    }
    return 0
}

private func runProcessPolicy() -> Int32 {
    writeJSONObject([
        "request_deadline_seconds": productionRequestDeadlineSeconds,
        "mount_compensation_reserve_seconds": productionMountCompensationReserveSeconds,
        "term_grace_seconds": productionTermGraceSeconds,
        "reap_grace_seconds": productionReapGraceSeconds,
        "group_grace_seconds": productionGroupGraceSeconds,
    ])
    return 0
}

private func runTestHarness(request: HelperRequest, scenario: String) -> Int32 {
    let tracker = BufferTracker()
    let clock = FakeMonotonicClock()
    let fakeHdiutil = FakeHdiutilRunner(
        scenario: scenario, tracker: tracker, operation: request.operation, clock: clock
    )
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
            keychain: fakeKeychain,
            clock: clock
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
    } catch is ProcessInvocationFailure {
        response = HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: HelperFailure.hdiutilFailure.code,
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )
        exitCode = 70
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
        "all_keychain_staging_zeroed": fakeSecurity.allStagingZeroed,
        "secret_materializations": fakeSecurity.secretMaterializations,
        "security_agent_observations": 0,
        "mount_compensation_budget": productionMountCompensationReserveSeconds,
    ])
    return exitCode
}
#endif

private func topLevelObjectKeys(_ input: Data) -> [String]? {
    let bytes = [UInt8](input)
    var index = 0

    func isWhitespace(_ byte: UInt8) -> Bool {
        byte == 0x20 || byte == 0x09 || byte == 0x0A || byte == 0x0D
    }

    func skippingWhitespace(_ start: Int) -> Int {
        var cursor = start
        while cursor < bytes.count, isWhitespace(bytes[cursor]) { cursor += 1 }
        return cursor
    }

    func endOfString(_ start: Int) -> Int? {
        guard start < bytes.count, bytes[start] == 0x22 else { return nil }
        var cursor = start + 1
        while cursor < bytes.count {
            if bytes[cursor] == 0x22 { return cursor + 1 }
            if bytes[cursor] == 0x5C {
                cursor += 1
                guard cursor < bytes.count else { return nil }
            }
            cursor += 1
        }
        return nil
    }

    index = skippingWhitespace(index)
    guard index < bytes.count, bytes[index] == 0x7B else { return nil }
    index += 1
    var depth = 1
    var expectingKey = true
    var keys = [String]()

    while index < bytes.count, depth > 0 {
        index = skippingWhitespace(index)
        guard index < bytes.count else { return nil }

        if depth == 1, expectingKey {
            if bytes[index] == 0x7D {
                depth = 0
                index += 1
                break
            }
            let start = index
            guard let end = endOfString(start) else { return nil }
            let encodedKey = Data(bytes[start..<end])
            guard let key = try? JSONSerialization.jsonObject(
                with: encodedKey,
                options: [.fragmentsAllowed]
            ) as? String else { return nil }
            index = skippingWhitespace(end)
            guard index < bytes.count, bytes[index] == 0x3A else { return nil }
            keys.append(key)
            expectingKey = false
            index += 1
            continue
        }

        switch bytes[index] {
        case 0x22:
            guard let end = endOfString(index) else { return nil }
            index = end
        case 0x7B, 0x5B:
            depth += 1
            index += 1
        case 0x7D, 0x5D:
            depth -= 1
            index += 1
        case 0x2C where depth == 1:
            expectingKey = true
            index += 1
        default:
            index += 1
        }
    }

    guard depth == 0, skippingWhitespace(index) == bytes.count else { return nil }
    return keys
}

private func runMain() -> Int32 {
    signal(SIGPIPE, SIG_IGN)
    let arguments = Array(CommandLine.arguments.dropFirst())

    #if CORTEX_STORAGE_HELPER_TESTING
    if arguments.count == 1, arguments[0] == "--spawn-probe" {
        return runSpawnProbe()
    }
    if arguments.count == 1, arguments[0] == "--deadline-drain-probe" {
        return runDeadlineDrainProbe()
    }
    if arguments.count == 1, arguments[0] == "--process-policy" {
        return runProcessPolicy()
    }
    if arguments.count == 2, arguments[0] == "--process-scenario" {
        return runProcessScenario(arguments[1])
    }
    if arguments.count == 2, arguments[0] == "--process-child" {
        return runProcessChild(scenario: arguments[1])
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
    let exactRequestKeys: Set<String> = [
        "schema_version", "operation", "image_path", "mount_path", "volume_name",
        "size", "transaction_id", "expected_encryption_uuid", "disposable",
        "cleanup_approved",
    ]
    guard !input.isEmpty,
          let topLevelKeys = topLevelObjectKeys(input),
          topLevelKeys.count == exactRequestKeys.count,
          Set(topLevelKeys) == exactRequestKeys,
          let rawObject = try? JSONSerialization.jsonObject(with: input),
          let rawDictionary = rawObject as? [String: Any],
          Set(rawDictionary.keys) == exactRequestKeys,
          let request = try? JSONDecoder().decode(HelperRequest.self, from: input),
          (try? validatedRequest(request)) != nil
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
    } catch is ProcessInvocationFailure {
        writeJSONObject(responseObject(HelperResponse(
            schema_version: 1,
            operation: request.operation.rawValue,
            code: HelperFailure.hdiutilFailure.code,
            encryption_uuid: nil,
            device: nil,
            item_count: nil
        )))
        return 70
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
