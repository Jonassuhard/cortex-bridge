import Darwin
import Foundation

// Stable launcher.  It does not select a generation by path alone: the
// caller supplies the already-open install lock and selector descriptors.
// The full installed factory revalidates those descriptors before exec.
private let allowedEnvironment = [
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG=C",
    "LC_ALL=C",
]

private func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(78)
}

private func main() -> Int32 {
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count == 2, args[0] == "--home" else {
        fail("usage: cortex-launch --home HOME")
    }
    let home = URL(fileURLWithPath: args[1], isDirectory: true)
    let selector = home.appendingPathComponent("current-generation.json")
    guard FileManager.default.fileExists(atPath: selector.path) else {
        fail("installed generation selector is missing")
    }
    var environment: [String: String] = [:]
    for entry in allowedEnvironment {
        let parts = entry.split(separator: "=", maxSplits: 1).map(String.init)
        environment[parts[0]] = parts[1]
    }
    setenv("PATH", environment["PATH"]!, 1)
    setenv("LANG", environment["LANG"]!, 1)
    setenv("LC_ALL", environment["LC_ALL"]!, 1)
    return 0
}

exit(main())
