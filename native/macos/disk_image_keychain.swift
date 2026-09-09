import Darwin
import CryptoKit
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

private struct NativeChildIdentity: Equatable {
    let pid: pid_t
    let parentPID: pid_t
    let groupID: pid_t
    let uid: uid_t
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let executableDevice: UInt32
    let executableInode: UInt64
    let executablePath: String
}

private func nativePathString(_ bytes: UnsafeRawBufferPointer) -> String? {
    guard let end = bytes.firstIndex(of: 0), end > 0 else { return nil }
    return String(bytes: bytes.prefix(end), encoding: .utf8)
}

private func nativeChildSnapshot(_ pid: pid_t, deadline: UInt64) -> NativeChildIdentity? {
    guard pid > 0, let now = monotonicNanoseconds(), now < deadline else { return nil }
    var bsd = proc_bsdinfo()
    guard proc_pidinfo(pid, PROC_PIDTBSDINFO, 0, &bsd, Int32(MemoryLayout.size(ofValue: bsd)))
            == MemoryLayout.size(ofValue: bsd),
          bsd.pbi_pid == UInt32(pid), bsd.pbi_ppid == UInt32(getpid()),
          bsd.pbi_pgid == UInt32(pid), bsd.pbi_uid == geteuid(),
          bsd.pbi_start_tvsec > 0, bsd.pbi_start_tvusec < 1_000_000 else { return nil }
    // proc_info.h defines PROC_PIDPATHINFO_MAXSIZE as 4*MAXPATHLEN; the
    // compound macro is not imported by Swift.
    var pathBytes = [UInt8](repeating: 0, count: 4 * Int(MAXPATHLEN))
    let pathCount = pathBytes.withUnsafeMutableBytes {
        proc_pidpath(pid, $0.baseAddress, UInt32($0.count))
    }
    guard pathCount > 0, let path = pathBytes.withUnsafeBytes(nativePathString) else { return nil }
    // Obtain vnode identity from the child's mapped executable, not from stat
    // of its pathname (which could now name a replacement). Walk boundedly.
    var address: UInt64 = 0
    for _ in 0..<1_024 {
        guard let now = monotonicNanoseconds(), now < deadline else { return nil }
        var region = proc_regionwithpathinfo()
        guard proc_pidinfo(pid, PROC_PIDREGIONPATHINFO, address, &region,
                          Int32(MemoryLayout.size(ofValue: region))) == MemoryLayout.size(ofValue: region) else { return nil }
        let regionPath = withUnsafeBytes(of: region.prp_vip.vip_path, nativePathString)
        let vnode = region.prp_vip.vip_vi.vi_stat
        if regionPath == path, region.prp_prinfo.pri_protection & UInt32(VM_PROT_EXECUTE) != 0,
           vnode.vst_mode & UInt16(S_IFMT) == UInt16(S_IFREG), vnode.vst_ino != 0 {
            return NativeChildIdentity(pid: pid, parentPID: pid_t(bsd.pbi_ppid),
                groupID: pid_t(bsd.pbi_pgid), uid: bsd.pbi_uid,
                startSeconds: bsd.pbi_start_tvsec, startMicroseconds: bsd.pbi_start_tvusec,
                executableDevice: vnode.vst_dev, executableInode: vnode.vst_ino, executablePath: path)
        }
        let start = region.prp_prinfo.pri_address
        let size = region.prp_prinfo.pri_size
        guard size > 0, start <= UInt64.max - size, start + size > address else { return nil }
        address = start + size
    }
    return nil
}

private func nativeChildWaitable(_ pid: pid_t, requireStopped: Bool, deadline: UInt64) -> Bool {
    while let now = monotonicNanoseconds(), now < deadline {
        var info = siginfo_t()
        let result = waitid(P_PID, id_t(pid), &info, WEXITED | WSTOPPED | WCONTINUED | WNOHANG | WNOWAIT)
        if result == 0 {
            return !requireStopped || (info.si_pid == pid && info.si_code == CLD_STOPPED)
        }
        if errno != EINTR { return false }
    }
    return false
}

private final class RegisteredNativeChild {
    let identity: NativeChildIdentity
    private var resumed = false
    private var reaped = false
    private var revoked = false
    private var signalsSent = Set<Int32>()

    private init(identity: NativeChildIdentity) { self.identity = identity }

    static func captureSuspended(pid: pid_t, executableFD: Int32, deadline limit: UInt64) -> RegisteredNativeChild? {
        guard let now = monotonicNanoseconds(), now < limit, now <= UInt64.max - brokerIOBudgetNS else { return nil }
        let deadline = min(limit, now + brokerIOBudgetNS)
        var executable = stat()
        guard fstat(executableFD, &executable) == 0, executable.st_mode & S_IFMT == S_IFREG,
              let first = nativeChildSnapshot(pid, deadline: deadline),
              first.executableDevice == UInt32(bitPattern: Int32(executable.st_dev)),
              first.executableInode == UInt64(executable.st_ino),
              nativeChildWaitable(pid, requireStopped: true, deadline: deadline),
              nativeChildSnapshot(pid, deadline: deadline) == first else { return nil }
        return RegisteredNativeChild(identity: first)
    }

    func resume(deadline limit: UInt64) -> Bool {
        guard !resumed, !reaped, !revoked, signalsSent.isEmpty,
              let now = monotonicNanoseconds(), now < limit, now <= UInt64.max - brokerIOBudgetNS else { return false }
        let deadline = min(limit, now + brokerIOBudgetNS)
        guard nativeChildSnapshot(identity.pid, deadline: deadline) == identity,
              nativeChildWaitable(identity.pid, requireStopped: true, deadline: deadline) else {
            revoked = true
            return false
        }
        guard let finalNow = monotonicNanoseconds(), finalNow < deadline else { return false }
        // Consume before the syscall: uncertain delivery never grants a retry.
        resumed = true
        return kill(identity.pid, SIGCONT) == 0
    }

    func signalGroup(_ signal: Int32, deadline limit: UInt64) -> Bool {
        guard !reaped, !revoked, signal == SIGTERM || signal == SIGKILL,
              !signalsSent.contains(signal),
              let now = monotonicNanoseconds(), now < limit, now <= UInt64.max - brokerIOBudgetNS else { return false }
        let deadline = min(limit, now + brokerIOBudgetNS)
        while let now = monotonicNanoseconds(), now < deadline {
            guard nativeChildSnapshot(identity.pid, deadline: deadline) == identity,
                  nativeChildWaitable(identity.pid, requireStopped: false, deadline: deadline) else {
                revoked = true
                return false
            }
            guard let finalNow = monotonicNanoseconds(), finalNow < deadline else { return false }
            signalsSent.insert(signal)
            if kill(-identity.groupID, signal) == 0 { return true }
            if errno != EINTR { return false }
        }
        return false
    }

    func reapExited(deadline: UInt64) -> Int32? {
        guard !reaped, !revoked, let now = monotonicNanoseconds(), now < deadline else { return nil }
        var info = siginfo_t()
        let observed = waitid(P_PID, id_t(identity.pid), &info, WEXITED | WNOHANG | WNOWAIT)
        if observed != 0 {
            if errno != EINTR { revoked = true }
            return nil
        }
        if info.si_pid == 0 { return nil }
        // Darwin waitid leaves si_uid unset; UID was checked in the registered
        // BSD identity and again before signaling. Use its actual exit-event
        // contract here, not an unpopulated field.
        guard info.si_pid == identity.pid, info.si_signo == SIGCHLD,
              [CLD_EXITED, CLD_KILLED, CLD_DUMPED].contains(info.si_code) else {
            revoked = true
            return nil
        }
        guard let finalNow = monotonicNanoseconds(), finalNow < deadline else { return nil }
        var status: Int32 = 0
        let result = waitpid(identity.pid, &status, WNOHANG)
        if result == identity.pid {
            reaped = true
            return status
        }
        if result < 0 && errno != EINTR { revoked = true }
        return nil
    }

    func groupIsAbsent(deadline: UInt64) -> Bool {
        // Only observation after exact reap; this never sends TERM or KILL.
        guard reaped, let now = monotonicNanoseconds(), now < deadline else { return false }
        return kill(-identity.groupID, 0) == -1 && errno == ESRCH
    }
}

private final class NativeOwnedProcess {
    let pid: pid_t
    private var executableFD: Int32
    private(set) var stdinFD: Int32
    private(set) var stdoutFD: Int32
    private(set) var stderrFD: Int32
    private(set) var registration: RegisteredNativeChild?
    private(set) var unresolved = false
    private var registrationAttempted = false
    private var resumed = false

    init(pid: pid_t, executableFD: Int32, stdinFD: Int32, stdoutFD: Int32, stderrFD: Int32) {
        self.pid = pid
        self.executableFD = executableFD
        self.stdinFD = stdinFD
        self.stdoutFD = stdoutFD
        self.stderrFD = stderrFD
    }

    func register(deadline: UInt64) -> Bool {
        guard !registrationAttempted else { return false }
        registrationAttempted = true
        registration = RegisteredNativeChild.captureSuspended(pid: pid,
            executableFD: executableFD, deadline: deadline)
        unresolved = registration == nil
        return !unresolved
    }

    func resume(deadline: UInt64) -> Bool {
        guard !unresolved, !resumed, let registration else { return false }
        guard registration.resume(deadline: deadline) else {
            unresolved = true
            return false
        }
        resumed = true
        return true
    }

    func closeInput() {
        if stdinFD >= 0 { close(stdinFD); stdinFD = -1 }
    }

    fileprivate func closeHandles() {
        for fd in [stdinFD, stdoutFD, stderrFD, executableFD] where fd >= 0 { close(fd) }
        stdinFD = -1; stdoutFD = -1; stderrFD = -1; executableFD = -1
    }

    deinit { closeHandles() }
}

// The persistent controller must retain this owner and must not exit while
// children is nonempty. An unregistered child remains suspended and owned;
// no cleanup signal is fabricated when identity proof is unavailable.
private final class NativeSpawnOwner {
    private(set) var children = [NativeOwnedProcess]()

    func spawnSuspended(executable: String, argv: [String], deadline: UInt64) -> NativeOwnedProcess? {
        guard argv.first == executable, !executable.contains("\0"),
              !argv.contains(where: { $0.contains("\0") }),
              let now = monotonicNanoseconds(), now < deadline else { return nil }
        let executableFD = open(executable, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        guard executableFD >= 0 else { return nil }
        var held = stat()
        var transferred = false
        var descriptors = [Int32]()
        defer {
            if !transferred {
                descriptors.forEach { close($0) }
                close(executableFD)
            }
        }
        guard fstat(executableFD, &held) == 0, held.st_mode & S_IFMT == S_IFREG else { return nil }
        for _ in 0..<3 {
            var pair: [Int32] = [-1, -1]
            guard pipe(&pair) == 0 else { return nil }
            descriptors.append(contentsOf: pair)
        }
        // Keep source descriptors distinct from the three destinations. Closed
        // stdio is a pre-spawn failure, never an accidentally closed child pipe.
        guard descriptors.allSatisfy({ $0 > STDERR_FILENO }) else { return nil }
        let inputRead = descriptors[0], inputWrite = descriptors[1]
        let outputRead = descriptors[2], outputWrite = descriptors[3]
        let errorRead = descriptors[4], errorWrite = descriptors[5]
        do {
            try setNonBlocking(inputWrite)
            try setNonBlocking(outputRead)
            try setNonBlocking(errorRead)
        } catch { return nil }
        var actions: posix_spawn_file_actions_t?
        guard posix_spawn_file_actions_init(&actions) == 0 else { return nil }
        defer { posix_spawn_file_actions_destroy(&actions) }
        guard posix_spawn_file_actions_adddup2(&actions, inputRead, STDIN_FILENO) == 0,
              posix_spawn_file_actions_adddup2(&actions, outputWrite, STDOUT_FILENO) == 0,
              posix_spawn_file_actions_adddup2(&actions, errorWrite, STDERR_FILENO) == 0 else { return nil }
        for fd in descriptors {
            guard posix_spawn_file_actions_addclose(&actions, fd) == 0 else { return nil }
        }
        var attributes: posix_spawnattr_t?
        guard posix_spawnattr_init(&attributes) == 0 else { return nil }
        defer { posix_spawnattr_destroy(&attributes) }
        guard posix_spawnattr_setflags(&attributes,
              Int16(POSIX_SPAWN_START_SUSPENDED | POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT)) == 0,
              posix_spawnattr_setpgroup(&attributes, 0) == 0 else { return nil }
        // Path-based exec must still name the held vnode immediately beforehand.
        var pathStat = stat()
        guard lstat(executable, &pathStat) == 0,
              pathStat.st_dev == held.st_dev, pathStat.st_ino == held.st_ino,
              pathStat.st_mode == held.st_mode, pathStat.st_uid == held.st_uid,
              let finalNow = monotonicNanoseconds(), finalNow < deadline else { return nil }
        var pid: pid_t = 0
        let result = withCStringArray(argv) { arguments in
            withCStringArray(childEnvironment) { environment in
                executable.withCString {
                    posix_spawn(&pid, $0, &actions, &attributes, arguments, environment)
                }
            }
        }
        guard result == 0 else { return nil }
        let child = NativeOwnedProcess(pid: pid, executableFD: executableFD,
            stdinFD: inputWrite, stdoutFD: outputRead, stderrFD: errorRead)
        children.append(child)
        transferred = true
        close(inputRead); close(outputWrite); close(errorWrite)
        return child
    }

    func releaseCompleted(_ child: NativeOwnedProcess, deadline: UInt64) -> Bool {
        guard let index = children.firstIndex(where: { $0 === child }),
              child.registration?.groupIsAbsent(deadline: deadline) == true else { return false }
        child.closeHandles()
        children.remove(at: index)
        return true
    }
}

private enum NativePumpControl { case keepGoing, cancel, ownerLost }

private struct NativePumpResult {
    let code: String
    let stdout: Data
    let stderr: Data
    let childReaped: Bool
    let groupAbsent: Bool
}

private enum NativeCommandPump {
    // A bounded drain lets owner-control processing run even during output
    // floods. Output is private parser input, never public protocol evidence.
    private static func drain(_ fd: Int32, into output: inout Data, eof: inout Bool,
                              discard: Bool, deadline: UInt64) -> String? {
        if eof { return nil }
        var bytes = [UInt8](repeating: 0, count: 4_096)
        for _ in 0..<16 {
            guard let now = monotonicNanoseconds(), now < deadline else { return "DEADLINE_EXPIRED" }
            let count = bytes.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress, $0.count) }
            if count > 0 {
                if !discard {
                    guard output.count + count <= childOutputLimit else { return "PROCESS_OUTPUT_LIMIT" }
                    output.append(contentsOf: bytes.prefix(count))
                }
            } else if count == 0 { eof = true; return nil }
            else if errno == EAGAIN || errno == EWOULDBLOCK { return nil }
            else if errno != EINTR { return "PROCESS_IO_FAILED" }
        }
        return nil
    }

    static func run(owner: NativeSpawnOwner, executable: String, argv: [String],
                    secret: SecretBuffer?, effectDeadline: UInt64, cleanupDeadline finalCleanupDeadline: UInt64,
                    control: (Int, Int) -> NativePumpControl) -> NativePumpResult {
        var stdout = Data(), stderr = Data()
        var outEOF = false, errEOF = false
        var status: Int32?
        func result(_ code: String, reaped: Bool, absent: Bool) -> NativePumpResult {
            NativePumpResult(code: code, stdout: stdout, stderr: stderr,
                             childReaped: reaped, groupAbsent: absent)
        }
        guard finalCleanupDeadline >= effectDeadline,
              secret == nil || isValidDiskImageSecret(secret!),
              let now = monotonicNanoseconds(), now < effectDeadline else {
            return result("INVALID_REQUEST", reaped: true, absent: true)
        }
        var cleanupDeadline = finalCleanupDeadline
        let cleanupBudgetNS = finalCleanupDeadline - effectDeadline
        guard let child = owner.spawnSuspended(executable: executable, argv: argv, deadline: effectDeadline) else {
            return result("PROCESS_SPAWN_FAILED", reaped: true, absent: true)
        }
        guard child.register(deadline: effectDeadline), let registration = child.registration,
              child.resume(deadline: effectDeadline) else {
            return result("SUPERVISION_UNRESOLVED", reaped: false, absent: false)
        }
        if secret == nil { child.closeInput() }
        var inputOffset = 0
        var failure: String?
        func recordFailure(_ code: String) {
            guard failure == nil else { return }
            failure = code
            guard let observed = monotonicNanoseconds() else { cleanupDeadline = 0; return }
            let (deadline, overflow) = observed.addingReportingOverflow(cleanupBudgetNS)
            cleanupDeadline = min(finalCleanupDeadline, overflow ? finalCleanupDeadline : deadline)
        }
        var killAt: UInt64?
        var killed = false
        while let now = monotonicNanoseconds(), now < cleanupDeadline {
            if let problem = drain(child.stdoutFD, into: &stdout, eof: &outEOF,
                                   discard: failure != nil, deadline: cleanupDeadline) {
                recordFailure(problem)
            }
            if let problem = drain(child.stderrFD, into: &stderr, eof: &errEOF,
                                   discard: failure != nil, deadline: cleanupDeadline) {
                recordFailure(problem)
            }
            if failure == nil {
                switch control(stdout.count, stderr.count) {
                case .keepGoing: break
                case .cancel: recordFailure("CANCELLED")
                case .ownerLost: recordFailure("CHANNEL_LOST")
                }
                if let current = monotonicNanoseconds(), current >= effectDeadline {
                    recordFailure("DEADLINE_EXPIRED")
                }
            }
            // All signal decisions must precede reap. EOF on both streams or
            // an already-issued KILL ends this command's signal sequence.
            if status == nil && ((outEOF && errEOF) || killed) {
                status = registration.reapExited(deadline: cleanupDeadline)
            }
            if let status, outEOF, errEOF,
               registration.groupIsAbsent(deadline: cleanupDeadline),
               owner.releaseCompleted(child, deadline: cleanupDeadline) {
                let exitCode = status == 0 ? "OK" : (waitStatusSignaled(status) ? "PROCESS_SIGNALED" : "PROCESS_EXIT_NONZERO")
                return result(failure ?? exitCode,
                              reaped: true, absent: true)
            }
            if failure != nil {
                child.closeInput()
                if status == nil && killAt == nil {
                    guard registration.signalGroup(SIGTERM, deadline: cleanupDeadline),
                          let current = monotonicNanoseconds() else {
                        return result("SUPERVISION_UNRESOLVED", reaped: false, absent: false)
                    }
                    let grace = UInt64(childTermGraceSeconds * 1_000_000_000)
                    killAt = current > UInt64.max - grace ? cleanupDeadline : min(cleanupDeadline, current + grace)
                } else if status == nil, !killed, let killAt,
                          let current = monotonicNanoseconds(), current >= killAt {
                    guard registration.signalGroup(SIGKILL, deadline: cleanupDeadline) else {
                        return result("SUPERVISION_UNRESOLVED", reaped: false, absent: false)
                    }
                    killed = true
                }
            } else if let secret, child.stdinFD >= 0 {
                guard let current = monotonicNanoseconds(), current < effectDeadline else { continue }
                let written: Int
                if inputOffset < secret.count {
                    written = secret.withUnsafeBytes {
                        Darwin.write(child.stdinFD, $0.baseAddress!.advanced(by: inputOffset), secret.count - inputOffset)
                    }
                    if written > 0 { inputOffset += written }
                } else {
                    var nul: UInt8 = 0
                    written = Darwin.write(child.stdinFD, &nul, 1)
                    if written == 1 { child.closeInput() }
                }
                if written < 0 && errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK {
                    recordFailure("PROCESS_STDIN_FAILED")
                }
            }
            var descriptors = [pollfd(fd: child.stdoutFD, events: outEOF ? 0 : Int16(POLLIN), revents: 0),
                               pollfd(fd: child.stderrFD, events: errEOF ? 0 : Int16(POLLIN), revents: 0)]
            if child.stdinFD >= 0 && failure == nil {
                descriptors.append(pollfd(fd: child.stdinFD, events: Int16(POLLOUT), revents: 0))
            }
            guard let current = monotonicNanoseconds(), current < cleanupDeadline else { break }
            let bound = failure == nil ? min(effectDeadline, cleanupDeadline) : cleanupDeadline
            let delay = bound > current ? min(UInt64(20), (bound - current) / 1_000_000) : 0
            let polled = poll(&descriptors, nfds_t(descriptors.count), Int32(delay))
            if polled < 0 && errno != EINTR { recordFailure("PROCESS_IO_FAILED") }
        }
        child.closeInput()
        return result("SUPERVISION_UNRESOLVED", reaped: status != nil, absent: false)
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

// MARK: - Persistent S3 broker mode

private enum BrokerMessageType: String {
    case hello = "HELLO", recover = "RECOVER", recovered = "RECOVERED"
    case start = "START", started = "STARTED", cancel = "CANCEL", status = "STATUS"
    case result = "RESULT", close = "CLOSE", closedReady = "CLOSED_READY"
    case commitAck = "COMMIT_ACK", committed = "COMMITTED"
    case reconcileProbe = "RECONCILE_PROBE"
    case reconciliationResult = "RECONCILIATION_RESULT"
    case reconciliationAck = "RECONCILIATION_ACK"
    case finalized = "FINALIZED", lateClose = "LATE_CLOSE"
    case protocolError = "PROTOCOL_ERROR"
}

private let brokerFrameLimit = 16 * 1024
private let brokerIOBudgetNS: UInt64 = 2_000_000_000

private indirect enum BrokerJSON {
    case object([String: BrokerJSON])
    case array([BrokerJSON])
    case string(String)
    case unsigned(UInt64)
    case bool(Bool)
    case null
}

private func brokerJSON(from value: Any) -> BrokerJSON? {
    if value is NSNull { return .null }
    if let string = value as? String { return .string(string) }
    if let array = value as? [Any] {
        var converted = [BrokerJSON]()
        converted.reserveCapacity(array.count)
        for item in array {
            guard let element = brokerJSON(from: item) else { return nil }
            converted.append(element)
        }
        return .array(converted)
    }
    if let dictionary = value as? [String: Any] {
        var converted = [String: BrokerJSON]()
        for (key, item) in dictionary {
            guard let element = brokerJSON(from: item) else { return nil }
            converted[key] = element
        }
        return .object(converted)
    }
    if let number = value as? NSNumber {
        if String(cString: number.objCType) == "c" {
            return .bool(number.boolValue)
        }
        let representation = number.stringValue
        guard !representation.isEmpty,
              representation.allSatisfy({ $0 >= "0" && $0 <= "9" }),
              let integer = UInt64(representation) else { return nil }
        return .unsigned(integer)
    }
    return nil
}

private func brokerJSONString(_ value: String) -> String {
    var output = "\""
    for scalar in value.unicodeScalars {
        switch scalar.value {
        case 0x22: output += "\\\""
        case 0x5C: output += "\\\\"
        case 0x00...0x1F: output += String(format: "\\u%04x", scalar.value)
        default: output.unicodeScalars.append(scalar)
        }
    }
    output += "\""
    return output
}

private func canonicalBrokerJSON(_ value: BrokerJSON) -> Data? {
    func encode(_ item: BrokerJSON) -> String {
        switch item {
        case .null: return "null"
        case .bool(let flag): return flag ? "true" : "false"
        case .unsigned(let integer): return String(integer)
        case .string(let string): return brokerJSONString(string)
        case .array(let array): return "[" + array.map(encode).joined(separator: ",") + "]"
        case .object(let object):
            let keys = object.keys.sorted {
                Array($0.utf8).lexicographicallyPrecedes(Array($1.utf8))
            }
            return "{" + keys.map { brokerJSONString($0) + ":" + encode(object[$0]!) }
                .joined(separator: ",") + "}"
        }
    }
    return encode(value).data(using: .utf8)
}

private func parseCanonicalBrokerObject(_ payload: Data) -> [String: BrokerJSON]? {
    guard let raw = try? JSONSerialization.jsonObject(with: payload, options: [.fragmentsAllowed]),
          let converted = brokerJSON(from: raw),
          case .object(let object) = converted,
          canonicalBrokerJSON(converted) == payload else { return nil }
    return object
}

private func brokerFrame(_ object: [String: BrokerJSON]) -> Data? {
    guard let payload = canonicalBrokerJSON(.object(object)),
          payload.count <= brokerFrameLimit else { return nil }
    var frame = Data()
    var length = UInt32(payload.count).bigEndian
    frame.append(Data(bytes: &length, count: MemoryLayout<UInt32>.size))
    frame.append(payload)
    return frame
}

private func monotonicNanoseconds() -> UInt64? {
    var value = timespec()
    guard clock_gettime(CLOCK_MONOTONIC, &value) == 0,
          value.tv_sec >= 0, value.tv_nsec >= 0 else { return nil }
    let seconds = UInt64(value.tv_sec)
    let nanos = UInt64(value.tv_nsec)
    guard seconds <= (UInt64.max - nanos) / 1_000_000_000 else { return nil }
    return seconds * 1_000_000_000 + nanos
}

private func brokerPoll(_ descriptor: Int32, events: Int16, deadline: UInt64) -> Bool {
    while true {
        guard let now = monotonicNanoseconds(), now < deadline else { return false }
        let remaining = deadline - now
        let milliseconds = Int32(min((remaining + 999_999) / 1_000_000, UInt64(Int32.max)))
        var item = pollfd(fd: descriptor, events: events, revents: 0)
        let result = poll(&item, 1, milliseconds)
        if result > 0 { return (item.revents & events) != 0 }
        if result == 0 { return false }
        if errno != EINTR { return false }
    }
}

private enum BrokerReadResult {
    case pending
    case frame([String: BrokerJSON])
    case eof
    case invalid
    case deadline
}

// One bounded, nonblocking step; retain partial frames across control-loop ticks.
// A terminal read error is sticky so trailing data cannot revive a failed channel.
private final class IncrementalBrokerReader {
    private var bytes = Data()
    private var payloadLength: Int?
    private var terminal: BrokerReadResult?
    var hasPartialFrame: Bool { !bytes.isEmpty }

    func step(_ descriptor: Int32, deadline: UInt64) -> BrokerReadResult {
        if let terminal { return terminal }
        func fail(_ result: BrokerReadResult) -> BrokerReadResult {
            terminal = result
            bytes.removeAll(keepingCapacity: false)
            return result
        }
        for attempt in 0...8 {
            guard let now = monotonicNanoseconds(), now < deadline else { return fail(.deadline) }
            if payloadLength == nil && bytes.count == 4 {
                let length = bytes.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
                guard length > 0, length <= brokerFrameLimit else { return fail(.invalid) }
                payloadLength = Int(length)
            }
            let target = payloadLength.map { $0 + 4 } ?? 4
            if bytes.count == target, payloadLength != nil {
                guard let object = parseCanonicalBrokerObject(Data(bytes.dropFirst(4))) else {
                    return fail(.invalid)
                }
                bytes.removeAll(keepingCapacity: false)
                payloadLength = nil
                return .frame(object)
            }
            // Decode bytes received on the final attempt before yielding; a
            // blocking wrapper must not poll for bytes already fully buffered.
            if attempt == 8 { return .pending }
            var buffer = [UInt8](repeating: 0, count: min(4_096, target - bytes.count))
            let count = buffer.withUnsafeMutableBytes {
                recv(descriptor, $0.baseAddress, $0.count, MSG_DONTWAIT)
            }
            if count > 0 {
                bytes.append(contentsOf: buffer.prefix(count))
            } else if count == 0 {
                return fail(bytes.isEmpty ? .eof : .invalid)
            } else if errno == EAGAIN || errno == EWOULDBLOCK {
                return .pending
            } else if errno != EINTR {
                return fail(.invalid)
            }
        }
        return .pending
    }
}

// Borrowed authenticated owner connection, valid only while its command runs.
// Construct only after START authorization and STARTED cursor consumption.
// This does not authenticate a fresh socket or grant operation authority.
private final class BrokerRunningControl {
    private let descriptor: Int32
    private let workflowID: String
    private let generation: UInt64
    private let nonce: String
    private let commandSHA256: String
    private var nextIncoming: UInt64?
    private var nextOutgoing: UInt64?
    private let reader = IncrementalBrokerReader()
    private var partialDeadline: UInt64?
    private var output = Data()
    private var outputOffset = 0
    private var outputDeadline: UInt64 = 0
    private var terminal: NativePumpControl?
    private(set) var errorCode: String?

    init(descriptor: Int32, workflowID: String, generation: UInt64, nonce: String,
         commandSHA256: String, nextIncoming: UInt64, nextOutgoing: UInt64) {
        self.descriptor = descriptor; self.workflowID = workflowID
        self.generation = generation; self.nonce = nonce; self.commandSHA256 = commandSHA256
        self.nextIncoming = nextIncoming; self.nextOutgoing = nextOutgoing
        // Darwin send(MSG_DONTWAIT) alone can wait on a full stream socket.
        // Enforce the descriptor invariant, retaining all unrelated flags.
        let flags = fcntl(descriptor, F_GETFL)
        if flags < 0 || fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) != 0 {
            errorCode = "CHANNEL_LOST"
            terminal = .ownerLost
        }
    }

    private func fail(_ code: String) -> NativePumpControl {
        errorCode = code
        terminal = .ownerLost
        return .ownerLost
    }

    private func flush(deadline: UInt64) -> Bool {
        guard !output.isEmpty else { return true }
        guard let now = monotonicNanoseconds(), now < min(deadline, outputDeadline) else {
            _ = fail("DEADLINE_EXPIRED"); return false
        }
        let count = output.withUnsafeBytes {
            send(descriptor, $0.baseAddress!.advanced(by: outputOffset), $0.count - outputOffset, MSG_DONTWAIT)
        }
        if count > 0 {
            outputOffset += count
            if outputOffset == output.count { output.removeAll(); outputOffset = 0; return true }
        } else if count == 0 || (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) {
            _ = fail("CHANNEL_LOST")
        }
        return false
    }

    func step(deadline: UInt64) -> NativePumpControl {
        if let terminal { return terminal }
        guard flush(deadline: deadline) else { return terminal ?? .keepGoing }
        guard let now = monotonicNanoseconds(), now < deadline,
              now <= UInt64.max - brokerIOBudgetNS else { return fail("DEADLINE_EXPIRED") }
        switch reader.step(descriptor, deadline: min(deadline, partialDeadline ?? deadline)) {
        case .pending:
            if reader.hasPartialFrame && partialDeadline == nil {
                partialDeadline = min(deadline, now + brokerIOBudgetNS)
            }
            return .keepGoing
        case .eof: return fail("CHANNEL_LOST")
        case .invalid: return fail("INVALID_FRAME")
        case .deadline: return fail("DEADLINE_EXPIRED")
        case .frame(let frame):
            partialDeadline = nil
            guard Set(frame.keys) == ["version", "type", "workflow_id", "generation", "connection_nonce", "cursor", "payload"],
                  brokerUInt(frame["version"]) == 1,
                  let type = brokerString(frame["type"]),
                  case .object(let payload)? = frame["payload"] else { return fail("INVALID_FRAME") }
            guard brokerString(frame["workflow_id"]) == workflowID,
                  brokerUInt(frame["generation"]) == generation else { return fail("STALE_GENERATION") }
            guard brokerString(frame["connection_nonce"]) == nonce else { return fail("AUTH_FAILED") }
            guard let expected = nextIncoming, brokerUInt(frame["cursor"]) == expected else { return fail("REPLAY") }
            // Consume before any control action or response is made observable.
            nextIncoming = expected == UInt64.max ? nil : expected + 1
            if type == "CANCEL" {
                guard Set(payload.keys) == ["command_sha256", "reason"],
                      let reason = brokerString(payload["reason"]),
                      ["CLIENT_CANCELLED", "SHUTDOWN_REQUESTED"].contains(reason) else { return fail("INVALID_FRAME") }
                guard brokerDigest(payload["command_sha256"]) == commandSHA256 else { return fail("AUTH_FAILED") }
                terminal = .cancel
                return .cancel
            }
            guard type == "STATUS" else { return fail("INVALID_STATE") }
            guard payload.isEmpty else { return fail("INVALID_FRAME") }
            guard let outgoing = nextOutgoing else { return fail("REPLAY") }
            let reply: [String: BrokerJSON] = ["version": .unsigned(1), "type": .string("STATUS"),
                "workflow_id": .string(workflowID), "generation": .unsigned(generation),
                "connection_nonce": .string(nonce), "cursor": .unsigned(outgoing),
                "payload": .object(["phase": .string("running"), "command_sha256": .string(commandSHA256),
                    "result_sha256": .null, "closed_ready_sha256": .null,
                    "child_reaped": .bool(false), "group_absent": .bool(false)])]
            guard let encoded = brokerFrame(reply) else { return fail("INVALID_FRAME") }
            nextOutgoing = outgoing == UInt64.max ? nil : outgoing + 1
            output = encoded
            outputDeadline = min(deadline, now + brokerIOBudgetNS)
            _ = flush(deadline: deadline)
            return terminal ?? .keepGoing
        }
    }
}

private func readBrokerBytes(
    _ descriptor: Int32, count: Int, deadline: UInt64, allowInitialEOF: Bool
) -> (Data?, Bool) {
    var output = Data()
    while output.count < count {
        guard brokerPoll(descriptor, events: Int16(POLLIN), deadline: deadline) else {
            return (nil, false)
        }
        var buffer = [UInt8](repeating: 0, count: count - output.count)
        let received = buffer.withUnsafeMutableBytes {
            Darwin.read(descriptor, $0.baseAddress, $0.count)
        }
        if received > 0 {
            output.append(contentsOf: buffer.prefix(received))
        } else if received == 0 {
            return (allowInitialEOF && output.isEmpty ? Data() : nil, true)
        } else if errno != EINTR {
            return (nil, true)
        }
    }
    return (output, true)
}

private func readBrokerFrame(_ descriptor: Int32, deadline: UInt64) -> BrokerReadResult {
    let reader = IncrementalBrokerReader()
    while true {
        let result = reader.step(descriptor, deadline: deadline)
        if case .pending = result {
            guard brokerPoll(descriptor, events: Int16(POLLIN), deadline: deadline) else { return .deadline }
        } else { return result }
    }
}

private func writeBrokerFrame(_ descriptor: Int32, _ object: [String: BrokerJSON], deadline: UInt64) -> Bool {
    guard let frame = brokerFrame(object) else { return false }
    var offset = 0
    return frame.withUnsafeBytes { raw in
        while offset < raw.count {
            guard brokerPoll(descriptor, events: Int16(POLLOUT), deadline: deadline) else {
                return false
            }
            let written = Darwin.write(descriptor, raw.baseAddress!.advanced(by: offset), raw.count - offset)
            if written > 0 { offset += written }
            else if written < 0, errno == EINTR { continue }
            else { return false }
        }
        return true
    }
}

@_silgen_name("_NSGetEnviron")
private func cortexNSGetEnviron()
    -> UnsafeMutablePointer<UnsafeMutablePointer<UnsafeMutablePointer<CChar>?>?>

private func originalBrokerEnvironment() -> [String: String]? {
    var argumentMaximum: Int32 = 0
    var maximumSize = MemoryLayout<Int32>.size
    var maximumMib = [Int32(CTL_KERN), Int32(KERN_ARGMAX)]
    let maximumResult = maximumMib.withUnsafeMutableBufferPointer {
        sysctl($0.baseAddress, 2, &argumentMaximum, &maximumSize, nil, 0)
    }
    guard maximumResult == 0, argumentMaximum > 0 else { return nil }
    var bytes = [UInt8](repeating: 0, count: Int(argumentMaximum))
    var actualSize = bytes.count
    var argumentsMib = [Int32(CTL_KERN), Int32(KERN_PROCARGS2), getpid()]
    let argumentsResult = argumentsMib.withUnsafeMutableBufferPointer { mib in
        bytes.withUnsafeMutableBytes {
            sysctl(mib.baseAddress, 3, $0.baseAddress, &actualSize, nil, 0)
        }
    }
    guard argumentsResult == 0, actualSize >= MemoryLayout<Int32>.size else { return nil }
    let argumentCount = bytes.withUnsafeBytes { $0.load(as: Int32.self) }
    guard argumentCount > 0 else { return nil }
    var index = MemoryLayout<Int32>.size

    func skipCString() -> Bool {
        guard index < actualSize else { return false }
        while index < actualSize, bytes[index] != 0 { index += 1 }
        guard index < actualSize else { return false }
        index += 1
        return true
    }

    guard skipCString() else { return nil }
    while index < actualSize, bytes[index] == 0 { index += 1 }
    for _ in 0..<argumentCount {
        guard skipCString() else { return nil }
    }
    var environment = [String: String]()
    while index < actualSize, bytes[index] != 0 {
        let start = index
        guard skipCString(),
              let entry = String(bytes: bytes[start..<(index - 1)], encoding: .utf8),
              let separator = entry.firstIndex(of: "=") else { return nil }
        let key = String(entry[..<separator])
        let value = String(entry[entry.index(after: separator)...])
        guard !key.isEmpty, environment[key] == nil else { return nil }
        environment[key] = value
    }
    return environment
}

private func currentBrokerEnvironment() -> [String: String]? {
    guard let environmentPointer = cortexNSGetEnviron().pointee else { return nil }
    var environment = [String: String]()
    var index = 0
    while let entryPointer = environmentPointer[index] {
        let entry = String(cString: entryPointer)
        guard let separator = entry.firstIndex(of: "=") else { return nil }
        let key = String(entry[..<separator])
        let value = String(entry[entry.index(after: separator)...])
        guard environment[key] == nil else { return nil }
        environment[key] = value
        index += 1
    }
    return environment
}

private func exactBrokerEnvironment() -> Bool {
    let expected = [
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
    ]
    guard originalBrokerEnvironment() == expected,
          var current = currentBrokerEnvironment() else { return false }
    let coreFoundationKey = "__CF_USER_TEXT_ENCODING"
    if let synthesized = current[coreFoundationKey] {
        let prefix = String(format: "0x%X:0x0:", geteuid())
        guard [prefix + "0x0", prefix + "0x1"].contains(synthesized),
              unsetenv(coreFoundationKey) == 0 else { return false }
        current.removeValue(forKey: coreFoundationKey)
    }
    return current == expected
}

private func parseBrokerArguments(_ arguments: [String]) -> (Int32, Int32, Int32, UUID, UInt64)? {
    guard arguments.count == 10,
          arguments[0] == "--broker-fd",
          arguments[2] == "--start-capability-fd",
          arguments[4] == "--recovery-authority-fd",
          arguments[6] == "--workflow-id",
          arguments[8] == "--generation",
          let brokerFD = Int32(arguments[1]),
          let capabilityFD = Int32(arguments[3]),
          let recoveryFD = Int32(arguments[5]),
          let workflowID = UUID(uuidString: arguments[7]),
          let generation = UInt64(arguments[9]),
          brokerFD >= 0, capabilityFD >= 0, recoveryFD >= 0,
          brokerFD != capabilityFD, brokerFD != recoveryFD,
          capabilityFD != recoveryFD else { return nil }
    return (brokerFD, capabilityFD, recoveryFD, workflowID, generation)
}

private struct BrokerListenerIdentity {
    let path: String
    let descriptorDevice: dev_t
    let descriptorInode: ino_t
    let pathDevice: dev_t
    let pathInode: ino_t
    let uid: uid_t
    let mode: mode_t
}

private struct ValidatedBrokerListener {
    let identity: BrokerListenerIdentity
    let pendingConnection: Int32?
}

private func socketIntegerOption(_ descriptor: Int32, level: Int32, option: Int32) -> Int32? {
    var value: Int32 = 0
    var length = socklen_t(MemoryLayout<Int32>.size)
    guard getsockopt(descriptor, level, option, &value, &length) == 0,
          length == MemoryLayout<Int32>.size else { return nil }
    return value
}

private struct UnixSocketAddressObservation {
    let address: sockaddr_un
    let length: socklen_t
}

private let unixSocketAddressHeaderLength = socklen_t(
    MemoryLayout<UInt8>.size + MemoryLayout<sa_family_t>.size
)

private func unixSocketAddress(
    _ descriptor: Int32, peer: Bool
) -> UnixSocketAddressObservation? {
    var address = sockaddr_un()
    var length = socklen_t(MemoryLayout<sockaddr_un>.size)
    let result = withUnsafeMutablePointer(to: &address) { pointer in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            peer ? getpeername(descriptor, $0, &length) : getsockname(descriptor, $0, &length)
        }
    }
    guard result == 0,
          length >= unixSocketAddressHeaderLength,
          length <= socklen_t(MemoryLayout<sockaddr_un>.size),
          address.sun_family == sa_family_t(AF_UNIX),
          socklen_t(address.sun_len) >= unixSocketAddressHeaderLength,
          socklen_t(address.sun_len) <= length else { return nil }
    return UnixSocketAddressObservation(address: address, length: length)
}

private func unixSocketPath(_ observation: UnixSocketAddressObservation) -> String? {
    var address = observation.address
    guard observation.length > unixSocketAddressHeaderLength else { return nil }
    return withUnsafePointer(to: &address.sun_path) { pointer in
        pointer.withMemoryRebound(to: CChar.self, capacity: 104) {
            $0.pointee == 0 ? nil : String(cString: $0)
        }
    }
}

private func unixSocketNameIsEmpty(_ observation: UnixSocketAddressObservation) -> Bool {
    let nameLength = Int(observation.length - unixSocketAddressHeaderLength)
    return withUnsafeBytes(of: observation.address.sun_path) {
        $0.prefix(nameLength).allSatisfy { $0 == 0 }
    }
}

private func validateBrokerListener(_ descriptor: Int32) -> ValidatedBrokerListener? {
    guard socketIntegerOption(descriptor, level: SOL_SOCKET, option: SO_TYPE) == SOCK_STREAM,
          let address = unixSocketAddress(descriptor, peer: false),
          let path = unixSocketPath(address), !path.isEmpty else { return nil }
    let flags = fcntl(descriptor, F_GETFL)
    guard flags >= 0, fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0 else { return nil }
    let probe = accept(descriptor, nil, nil)
    guard probe >= 0 || errno == EAGAIN || errno == EWOULDBLOCK else { return nil }
    var descriptorStat = stat()
    var pathStat = stat()
    guard fstat(descriptor, &descriptorStat) == 0,
          lstat(path, &pathStat) == 0,
          (descriptorStat.st_mode & S_IFMT) == S_IFSOCK,
          (pathStat.st_mode & S_IFMT) == S_IFSOCK,
          descriptorStat.st_uid == geteuid(),
          pathStat.st_uid == geteuid(),
          (pathStat.st_mode & 0o777) == 0o600 else { return nil }
    let parent = (path as NSString).deletingLastPathComponent
    var parentStat = stat()
    guard lstat(parent, &parentStat) == 0,
          (parentStat.st_mode & S_IFMT) == S_IFDIR,
          parentStat.st_uid == geteuid(),
          (parentStat.st_mode & 0o077) == 0 else { return nil }
    return ValidatedBrokerListener(
        identity: BrokerListenerIdentity(
            path: path,
            descriptorDevice: descriptorStat.st_dev, descriptorInode: descriptorStat.st_ino,
            pathDevice: pathStat.st_dev, pathInode: pathStat.st_ino,
            uid: pathStat.st_uid, mode: pathStat.st_mode & 0o777
        ),
        pendingConnection: probe >= 0 ? probe : nil
    )
}

private func listenerStillMatches(_ descriptor: Int32, _ identity: BrokerListenerIdentity) -> Bool {
    var descriptorStat = stat()
    var pathStat = stat()
    return fstat(descriptor, &descriptorStat) == 0
        && lstat(identity.path, &pathStat) == 0
        && descriptorStat.st_dev == identity.descriptorDevice
        && descriptorStat.st_ino == identity.descriptorInode
        && pathStat.st_dev == identity.pathDevice
        && pathStat.st_ino == identity.pathInode
        && pathStat.st_uid == identity.uid
        && (pathStat.st_mode & 0o777) == identity.mode
}

private func validateCapabilitySocket(_ descriptor: Int32) -> Bool {
    guard socketIntegerOption(descriptor, level: SOL_SOCKET, option: SO_TYPE) == SOCK_STREAM,
          let local = unixSocketAddress(descriptor, peer: false),
          let peer = unixSocketAddress(descriptor, peer: true),
          unixSocketNameIsEmpty(local),
          unixSocketNameIsEmpty(peer),
          peerAuditSHA256(descriptor) != nil else { return false }
    var details = stat()
    return fstat(descriptor, &details) == 0 && (details.st_mode & S_IFMT) == S_IFSOCK
}

private func consumeRecoveryRoot(_ descriptor: Int32) -> SecretBuffer? {
    defer { close(descriptor) }
    var details = stat()
    guard fstat(descriptor, &details) == 0,
          (details.st_mode & S_IFMT) == S_IFIFO,
          (fcntl(descriptor, F_GETFL) & O_ACCMODE) == O_RDONLY,
          let now = monotonicNanoseconds(), now <= UInt64.max - brokerIOBudgetNS else { return nil }
    let deadline = now + brokerIOBudgetNS
    let root = SecretBuffer(count: 32)
    var count = 0
    var accepted = false
    defer { if !accepted { root.zeroize() } }
    while count < root.count {
        guard brokerPoll(descriptor, events: Int16(POLLIN), deadline: deadline) else { return nil }
        let received = root.withUnsafeMutableBytes {
            Darwin.read(descriptor, $0.baseAddress!.advanced(by: count), root.count - count)
        }
        if received > 0 { count += received }
        else if received == 0 { return nil }
        else if errno != EINTR { return nil }
    }
    // An exact root requires EOF, not just an available 32-byte prefix. Keep
    // any surplus byte mutable and erase it; never copy authority into Data.
    var extra: UInt8 = 0
    defer { memset_s(&extra, 1, 0, 1) }
    while brokerPoll(descriptor, events: Int16(POLLIN), deadline: deadline) {
        let received = Darwin.read(descriptor, &extra, 1)
        if received == 0 {
            accepted = true
            return root
        }
        if received > 0 || errno != EINTR { return nil }
    }
    return nil
}

private func acceptBrokerConnection(_ listener: Int32) -> Int32? {
    guard let now = monotonicNanoseconds(), now <= UInt64.max - brokerIOBudgetNS else { return nil }
    let deadline = now + brokerIOBudgetNS
    let flags = fcntl(listener, F_GETFL)
    guard flags >= 0, fcntl(listener, F_SETFL, flags | O_NONBLOCK) == 0 else { return nil }
    while brokerPoll(listener, events: Int16(POLLIN), deadline: deadline) {
        let accepted = accept(listener, nil, nil)
        if accepted >= 0 { return accepted }
        if errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK { return nil }
    }
    return nil
}

private func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func currentExecutableIdentity() -> [String: BrokerJSON]? {
    var required: UInt32 = 0
    _ = _NSGetExecutablePath(nil, &required)
    guard required > 0 else { return nil }
    var buffer = [CChar](repeating: 0, count: Int(required))
    guard _NSGetExecutablePath(&buffer, &required) == 0 else { return nil }
    let path = String(cString: buffer)
    let descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
    guard descriptor >= 0 else { return nil }
    defer { close(descriptor) }
    var details = stat()
    guard fstat(descriptor, &details) == 0, (details.st_mode & S_IFMT) == S_IFREG else { return nil }
    var hasher = SHA256()
    var chunk = [UInt8](repeating: 0, count: 1024 * 1024)
    while true {
        let count = chunk.withUnsafeMutableBytes { Darwin.read(descriptor, $0.baseAddress, $0.count) }
        if count > 0 { hasher.update(data: Data(chunk.prefix(count))) }
        else if count == 0 { break }
        else if errno != EINTR { return nil }
    }
    let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
    return [
        "broker_dev_u32": .unsigned(UInt64(UInt32(bitPattern: Int32(details.st_dev)))),
        "broker_ino": .unsigned(UInt64(details.st_ino)),
        "broker_uid": .unsigned(UInt64(details.st_uid)),
        "broker_mode": .unsigned(UInt64(details.st_mode & 0o777)),
        "broker_sha256": .string(digest),
    ]
}

private func currentBootIdentity() -> (UInt64, UInt64)? {
    var boot = timeval()
    var size = MemoryLayout<timeval>.size
    guard sysctlbyname("kern.boottime", &boot, &size, nil, 0) == 0,
          size == MemoryLayout<timeval>.size,
          boot.tv_sec > 0, boot.tv_usec >= 0, boot.tv_usec < 1_000_000 else { return nil }
    return (UInt64(boot.tv_sec), UInt64(boot.tv_usec))
}

private func connectionNonce() -> String? {
    var bytes = [UInt8](repeating: 0, count: 32)
    guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess,
          bytes.contains(where: { $0 != 0 }) else { return nil }
    return bytes.map { String(format: "%02x", $0) }.joined()
}

private func peerAuditSHA256(_ descriptor: Int32) -> String? {
    var token = audit_token_t()
    var length = socklen_t(MemoryLayout<audit_token_t>.size)
    guard getsockopt(descriptor, SOL_LOCAL, LOCAL_PEERTOKEN, &token, &length) == 0,
          length == MemoryLayout<audit_token_t>.size else { return nil }
    let words: [UInt32] = withUnsafeBytes(of: token) { raw in
        Array(raw.bindMemory(to: UInt32.self))
    }
    guard words.count == 8, words[1] == UInt32(geteuid()) else { return nil }
    let projection: BrokerJSON = .object([
        "pid": .unsigned(UInt64(words[5])),
        "effective_uid": .unsigned(UInt64(words[1])),
        "effective_gid": .unsigned(UInt64(words[2])),
        "audit_session_id": .unsigned(UInt64(words[6])),
        "pid_version": .unsigned(UInt64(words[7])),
    ])
    guard let canonical = canonicalBrokerJSON(projection) else { return nil }
    return sha256Hex(canonical)
}

private func brokerString(_ value: BrokerJSON?) -> String? {
    guard case .string(let string)? = value else { return nil }
    return string
}

private func brokerUInt(_ value: BrokerJSON?) -> UInt64? {
    guard case .unsigned(let integer)? = value else { return nil }
    return integer
}

private struct AuthorizedBrokerStart {
    let recordSHA256: String
    let requestSHA256: String
    let request: [String: BrokerJSON]
    let effectBudgetNS: UInt64
    let cleanupBudgetNS: UInt64
}

// Structural public protocol validation, distinct from legacy helper arguments.
// Retained no-follow filesystem and operation preconditions are still required
// before any effect; this parser alone confers no execution authority.
private func validatedBrokerPublicRequest(_ request: [String: BrokerJSON]) -> HelperRequest? {
    guard Set(request.keys) == ["schema_version", "operation", "image_path", "mount_path",
        "volume_name", "size", "transaction_id", "expected_encryption_uuid", "disposable", "cleanup_approved"],
          brokerUInt(request["schema_version"]) == 1,
          let rawOperation = brokerString(request["operation"]),
          let operation = Operation(rawValue: rawOperation),
          let image = brokerString(request["image_path"]), isLexicallySafeAbsolutePath(image),
          let transaction = brokerString(request["transaction_id"]),
          let uuid = UUID(uuidString: transaction), uuid.uuidString.lowercased() == transaction,
          case .bool(let disposable)? = request["disposable"],
          case .bool(let cleanup)? = request["cleanup_approved"] else { return nil }
    func optionalString(_ key: String) -> Bool {
        if case .null? = request[key] { return true }
        return brokerString(request[key]) != nil
    }
    guard ["mount_path", "volume_name", "size", "expected_encryption_uuid"].allSatisfy(optionalString) else { return nil }
    let mount = brokerString(request["mount_path"])
    let volume = brokerString(request["volume_name"])
    let size = brokerString(request["size"])
    let encryption = brokerString(request["expected_encryption_uuid"])
    if let mount, !isLexicallySafeAbsolutePath(mount) { return nil }
    if let encryption {
        guard let value = UUID(uuidString: encryption), value.uuidString.lowercased() == encryption else { return nil }
    }
    switch operation {
    case .create:
        guard encryption == nil, mount == nil,
              size == (disposable ? "64m" : "256g"),
              volume == (disposable ? "CORTEX_BRIDGE_SPIKE" : "CORTEX_BRIDGE_2026_09") else { return nil }
    case .mount, .detach:
        guard encryption != nil, mount != nil, size == nil, volume == nil else { return nil }
    case .inspectItem, .deleteDisposableItem:
        guard encryption != nil, mount == nil, size == nil, volume == nil else { return nil }
        if operation == .deleteDisposableItem && !(disposable && cleanup) { return nil }
    }
    return HelperRequest(schema_version: 1, operation: operation, image_path: image,
        mount_path: mount, volume_name: volume, size: size, transaction_id: uuid,
        expected_encryption_uuid: encryption, disposable: disposable, cleanup_approved: cleanup)
}

private func brokerDigest(_ value: BrokerJSON?) -> String? {
    guard let text = brokerString(value), text.utf8.count == 64,
          text.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) else { return nil }
    return text
}

// Only the inherited private endpoint can carry this authority. This function
// validates START binding, not the operation's semantic/pre-effect conditions.
private func consumeStartGrant(
    _ descriptor: Int32, start: [String: BrokerJSON], workflowID: String,
    generation: UInt64, nonce: String, peerAudit: String, boot: (UInt64, UInt64)
) -> AuthorizedBrokerStart? {
    defer { close(descriptor) }
    let flags = fcntl(descriptor, F_GETFL)
    guard flags >= 0, fcntl(descriptor, F_SETFL, flags | O_NONBLOCK) == 0,
          let now = monotonicNanoseconds(), now <= UInt64.max - brokerIOBudgetNS else { return nil }
    let deadline = now + brokerIOBudgetNS
    guard case .frame(let grant) = readBrokerFrame(descriptor, deadline: deadline) else { return nil }
    // The producer publishes exactly one frame and closes. Reject trailing data
    // rather than leaving a second authorization available to a later reader.
    let (trailing, ready) = readBrokerBytes(descriptor, count: 1, deadline: deadline, allowInitialEOF: true)
    guard ready, let trailing, trailing.isEmpty,
          Set(grant.keys) == ["version", "type", "workflow_id", "generation",
              "record_sha256", "request_sha256", "operation", "effect_budget_ns",
              "cleanup_budget_ns", "boot_seconds", "boot_microseconds",
              "connection_nonce", "peer_audit_sha256"],
          brokerUInt(grant["version"]) == 1, brokerString(grant["type"]) == "START_GRANT",
          brokerString(grant["workflow_id"]) == workflowID,
          brokerUInt(grant["generation"]) == generation,
          brokerString(grant["connection_nonce"]) == nonce,
          brokerString(grant["peer_audit_sha256"]) == peerAudit,
          brokerUInt(grant["boot_seconds"]) == boot.0,
          brokerUInt(grant["boot_microseconds"]) == boot.1,
          let recordHash = brokerDigest(grant["record_sha256"]),
          let requestHash = brokerDigest(grant["request_sha256"]),
          let operation = brokerString(grant["operation"]),
          ["create", "mount", "detach", "inspect-item", "delete-disposable-item",
           "probe-mounted-image"].contains(operation),
          let effect = brokerUInt(grant["effect_budget_ns"]), effect > 0, effect <= 40_000_000_000,
          let cleanup = brokerUInt(grant["cleanup_budget_ns"]), cleanup > 0, cleanup <= 12_000_000_000,
          case .object(let payload)? = start["payload"],
          Set(payload.keys) == ["request", "request_sha256", "effect_budget_ns", "cleanup_budget_ns"],
          brokerString(payload["request_sha256"]) == requestHash,
          brokerUInt(payload["effect_budget_ns"]) == effect,
          brokerUInt(payload["cleanup_budget_ns"]) == cleanup,
          case .object(let request)? = payload["request"],
          brokerString(request["operation"]) == operation,
          let canonicalRequest = canonicalBrokerJSON(.object(request)) else { return nil }
    var projection = Data("CORTEX-S3\0REQUEST\0V1\0".utf8)
    projection.append(canonicalRequest)
    guard sha256Hex(projection) == requestHash else { return nil }
    return AuthorizedBrokerStart(recordSHA256: recordHash, requestSHA256: requestHash,
        request: request, effectBudgetNS: effect, cleanupBudgetNS: cleanup)
}

private func protocolErrorCode(
    _ object: [String: BrokerJSON], workflowID: String, generation: UInt64, nonce: String
) -> String {
    guard Set(object.keys) == [
        "version", "type", "workflow_id", "generation", "connection_nonce", "cursor", "payload"
    ], brokerUInt(object["version"]) == 1,
       case .object? = object["payload"] else { return "INVALID_FRAME" }
    guard brokerString(object["workflow_id"]) == workflowID,
          brokerUInt(object["generation"]) == generation else { return "STALE_GENERATION" }
    guard brokerString(object["connection_nonce"]) == nonce else { return "AUTH_FAILED" }
    guard brokerUInt(object["cursor"]) == 0 else { return "REPLAY" }
    guard let rawType = brokerString(object["type"]),
          let type = BrokerMessageType(rawValue: rawType) else { return "INVALID_FRAME" }
    switch type {
    case .start, .recover, .cancel, .status, .close, .commitAck, .lateClose,
         .reconcileProbe, .reconciliationAck:
        return "AUTH_FAILED"
    case .hello, .recovered, .started, .result, .closedReady, .committed,
         .reconciliationResult, .finalized, .protocolError:
        return "INVALID_STATE"
    }
}

private func runPersistentBroker(arguments: [String]) -> Int32? {
    guard arguments.first == "--broker-fd" else { return nil }
    guard exactBrokerEnvironment(), let parsed = parseBrokerArguments(arguments) else { return 64 }
    signal(SIGPIPE, SIG_IGN)
    guard validateCapabilitySocket(parsed.1),
          let recoveryRoot = consumeRecoveryRoot(parsed.2) else { return 64 }
    defer { recoveryRoot.zeroize() }
    guard
          let validatedListener = validateBrokerListener(parsed.0) else { return 64 }
    var noSigPipe: Int32 = 1
    _ = setsockopt(parsed.0, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))
    guard let connection = validatedListener.pendingConnection ?? acceptBrokerConnection(parsed.0),
          listenerStillMatches(parsed.0, validatedListener.identity) else { return 70 }
    defer { close(connection) }
    _ = setsockopt(connection, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))
    let connectionFlags = fcntl(connection, F_GETFL)
    guard connectionFlags >= 0,
          fcntl(connection, F_SETFL, connectionFlags | O_NONBLOCK) == 0,
          let nonce = connectionNonce(),
          let boot = currentBootIdentity(),
          let peerAudit = peerAuditSHA256(connection),
          var payload = currentExecutableIdentity(),
          let writeStart = monotonicNanoseconds(), writeStart <= UInt64.max - brokerIOBudgetNS else { return 70 }
    payload["boot_seconds"] = .unsigned(boot.0)
    payload["boot_microseconds"] = .unsigned(boot.1)
    payload["peer_audit_sha256"] = .string(peerAudit)
    let workflowID = parsed.3.uuidString.lowercased()
    let hello: [String: BrokerJSON] = [
        "version": .unsigned(1),
        "type": .string(BrokerMessageType.hello.rawValue),
        "workflow_id": .string(workflowID),
        "generation": .unsigned(parsed.4),
        "connection_nonce": .string(nonce),
        "cursor": .unsigned(0),
        "payload": .object(payload),
    ]
    guard writeBrokerFrame(connection, hello, deadline: writeStart + brokerIOBudgetNS),
          let readStart = monotonicNanoseconds(), readStart <= UInt64.max - brokerIOBudgetNS else { return 70 }
    switch readBrokerFrame(connection, deadline: readStart + brokerIOBudgetNS) {
    case .eof:
        return 0
    case .pending, .invalid, .deadline:
        return 64
    case .frame(let message):
        var code = protocolErrorCode(message, workflowID: workflowID, generation: parsed.4, nonce: nonce)
        if code == "AUTH_FAILED", brokerString(message["type"]) == "START",
           brokerString(message["connection_nonce"]) == nonce,
           let authorized = consumeStartGrant(parsed.1, start: message, workflowID: workflowID,
               generation: parsed.4, nonce: nonce, peerAudit: peerAudit, boot: boot) {
            // Authorization is real; supervised dispatch/terminal commit is not
            // connected yet. Never report STARTED or fall back to one-shot code.
            code = validatedBrokerPublicRequest(authorized.request) == nil ? "INVALID_FRAME" : "INVALID_STATE"
        }
        guard let errorStart = monotonicNanoseconds(), errorStart <= UInt64.max - brokerIOBudgetNS else { return 64 }
        let response: [String: BrokerJSON] = [
            "version": .unsigned(1),
            "type": .string(BrokerMessageType.protocolError.rawValue),
            "workflow_id": .string(workflowID),
            "generation": .unsigned(parsed.4),
            "connection_nonce": .string(nonce),
            "cursor": .unsigned(1),
            "payload": .object(["code": .string(code)]),
        ]
        _ = writeBrokerFrame(connection, response, deadline: errorStart + brokerIOBudgetNS)
        return 64
    }
}

private func runMain() -> Int32 {
    signal(SIGPIPE, SIG_IGN)
    let arguments = Array(CommandLine.arguments.dropFirst())

    if let brokerResult = runPersistentBroker(arguments: arguments) {
        return brokerResult
    }

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
