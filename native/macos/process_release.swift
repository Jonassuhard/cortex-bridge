import Darwin

// The parent owns authorization, durable identity and timeout/cleanup.
// This helper accepts release only from the explicitly inherited pipe.
private func run() -> Int32 {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count >= 4, args[0] == "--release-fd", args[2] == "--",
          !args[1].isEmpty, args[1].utf8.allSatisfy({ $0 >= 48 && $0 <= 57 }),
          let releaseFD = Int32(args[1]), releaseFD > 2,
          !args[3].isEmpty else {
        return 125
    }
    var info = stat()
    guard fstat(releaseFD, &info) == 0,
          (info.st_mode & S_IFMT) == S_IFIFO else {
        return 125
    }
    var byte: UInt8 = 0
    var count: Int
    repeat {
        count = Darwin.read(releaseFD, &byte, 1)
    } while count == -1 && errno == EINTR
    Darwin.close(releaseFD)
    guard count == 1, byte == 1 else {
        return 125
    }
    var arguments: [UnsafeMutablePointer<CChar>?] = []
    for argument in args.dropFirst(3) {
        guard let copy = strdup(argument) else {
            for pointer in arguments { free(pointer) }
            return 125
        }
        arguments.append(copy)
    }
    arguments.append(nil)
    defer { for pointer in arguments { free(pointer) } }
    arguments.withUnsafeMutableBufferPointer { buffer in
        _ = execvp(buffer[0]!, buffer.baseAddress!)
    }
    return 127
}

exit(run())
