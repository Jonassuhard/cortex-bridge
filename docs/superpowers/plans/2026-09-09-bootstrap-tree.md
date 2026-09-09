# Native application-tree verification

## Scope

Verify installed application contents before Python loads generation modules.
Use no-follow directory traversal and descriptor-relative enumeration. Compare
the complete observed tree with its digest-bound manifest: files, directories,
permissions, sizes and SHA-256. Reject unlisted entries, links and special files.

## Reproductions

The real compiled native launcher initially executed the harmless probe despite
changed Python source, relaxed source permissions, an added unlisted file and a
symbolic-link ancestor. Four subtests failed before implementation (45.505 s).
After implementation they pass (33.333 s), alongside earlier record,
interpreter, path and duplicate-key corruption cases.

## Implementation

- Open every absolute directory component with O_DIRECTORY/O_NOFOLLOW.
- Read private metadata relative to a retained parent directory descriptor.
- Bound metadata reads and check identity/size/timestamps before and after.
- Enumerate application directories through retained descriptors, reject
  symlinks/special files and hardlinked files, and verify named/open identities.
- Stream file hashes; enforce 50,000 entries, depth 64 and 1 GiB total.
- Compare the exact observed tree with the manifest before executing Python.
- Compare all permission bits, including setuid/setgid/sticky, rather than
  masking them away. The special-mode mutation executed before the correction
  (49.079 s RED); native ownership/mode guards now use the full permission mask.
- Preserve the caller's absolute home path: Foundation standardization was
  observed rewriting an existing /private/var path into the /var symlink.

## Stronger integration proof

The generation-install test now also compiles the real native launcher, uses it
to start actual installed Python/HTTP, stops it, and recomputes generation
metadata afterward. Managed startup remains a separate phase in this test until
the descriptor handoff is connected; do not confuse sequential proofs with a
single composed startup.

The first stronger integration run reached real HTTP but failed the subsequent
generation inventory (62.944 s). Native startup previously used ordinary Python
module launch, allowing imports to create cache directories inside the generation.
It now uses isolated Python with site loading and bytecode writes disabled
(`-I -S -B`), and inserts only the verified application package directory.
The test explicitly rejects any generated `__pycache__` directory and still
recomputes the complete metadata after shutdown.

A subsequent run identified pre-existing source `scripts/__pycache__` copied
by the installer (65.243 s, failed). Script source staging and approval plans now
explicitly omit `__pycache__`, `.pyc` and `.pyo`; source files are preserved.
The installed-tree verifier does not omit anything: a cache added after
installation is still rejected. A new test failed before this change and the
14 resource-staging tests pass afterward (0.055 s).

## Boundaries

Not an external trust anchor: a same-user writer able to replace all expected
metadata is outside these integrity claims. Directory/file traversal is pinned
while reading; descriptors are not yet transferred through the complete native
handoff. Kernel-atomic execution of the verified interpreter and exclusion of
all non-cooperating writers are not claimed. Encrypted-volume and browser
acceptance remain open. User installation and remote Git are unchanged.

## Final executed suites — macOS arm64, 2026-09-09

Run from the worktree using
`PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p PATTERN -q`.

| Pattern | Result | Duration |
| --- | --- | --- |
| test_installed_storage_runtime.py | PASS, 12 tests | 67.243 s |
| test_generation_install.py | PASS, 6 tests | 82.172 s |
| test_install_resource_tree.py | PASS, 14 tests | 0.055 s |
| test_generation_metadata.py | PASS, 2 tests | 14.153 s |

34 targeted tests pass. The final installation run includes isolated native
HTTP, no cache directories, unchanged full generation metadata, managed HTTP,
graceful CLOSED and rejected second publication. This does not prove an installed
stable-bootstrap deployment or a composed native-to-managed startup.
`git diff --check` passed. No commit, push or release version change.

Storage sessions: native `56037b25d18446c2b0eefbae5605e2ef`, tests
`a226242696744daf9236c2171fb7ef04`, plans
`4389b579345145daa7652d3e5bd75948`, console
`2b6d2bf4690947228e66125dfa1a4d0c`, root
`641ca9f4045043b89a19abd3f81b7357`.
