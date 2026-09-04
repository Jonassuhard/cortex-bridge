# S3 Owned-Process Supervision Implementation Plan

**Status:** Revision 7 review candidate; implementation remains frozen pending
three fresh, mutually blind, read-only reviews with `P0=0`, `P1=0`, `P2=0` and
`PASS`
**Revision-7 parent:** `7b3567637f2025c1b8c21338acad070d6561bcd9`

> **For agentic workers:** execute tasks sequentially. Preserve every gate,
> freeze every declared byte identity before the next phase and stop on the
> first failed receipt. No review result from another reviewer is visible to a
> reviewer performing an independent review.

**Goal:** implement persistent broker-owned native supervision, a byte-exact
broker/worker protocol, exclusive child-free mutation authority, exact
artifact/observer closure and reproducible 397-case evidence without granting
a worker, PID, count or decoded wire object authority.

**Architecture:** Python owns the session, artifact ledger, persistent observer
and one persistent Swift broker. Python transfers a fresh worker socket to the
broker using one validated `SCM_RIGHTS` message per invocation. Only the broker
spawns/waits/signals/reaps native children. Workers own strict requests and
secret handling, receive only broker frames and must ACK the exact final frame.
Worker loss routes native settlement through a separately ACKed admin orphan
ledger. A busy session at +115 remains `OPEN_UNRESOLVED`; broker, observer and
Python ownership persist until the sole late-close chain proves closure.

**Tech stack:** Swift 6; Darwin process, socket, ancillary, descriptor and
monotonic-clock APIs; Security.framework; Python 3.11 and 3.14 standard library;
Git plumbing and Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global constraints

- Work only in
  `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation`
  on branch `codex/v054-storage-consolidation`.
- Implementation starts only after these exact Revision 7 document bytes pass
  three fresh blind reviews with zero P0/P1/P2 and `PASS`.
- Never edit, stage or commit the pre-existing `primer.md` change.
- Between `IMPLEMENTATION_BASE` and `S3_FINAL`, change only
  `native/macos/disk_image_keychain.swift`,
  `tests/disk_image_keychain_harness.py` and
  `tests/test_disk_image_keychain_helper.py`.
- The observer adds no fourth tracked file. Its exact Swift bytes and expected
  source hash remain constants in `tests/disk_image_keychain_harness.py`; its
  source and linked executable are private ephemeral build products.
- Normal gates run no live Keychain, DiskImages, `hdiutil`, mount, detach,
  quarantine, SecurityAgent, Chrome or production action.
- Live authorization remains exact key
  `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION` with exact value
  `YES_DISPOSABLE_64_MIB_ONLY`, alongside unique flags `--integration` and
  `--allow-effects`; optional `--cleanup-approved` is captured at preparation.
- Preserve the strict ten-key request, public six-key response, stable exit/code
  table, Keychain attributes, secret representation and no-UI queries.
- No raw PID/PGID, count, wire payload or replayable idle observation is
  authority.
- Every deadline, poll, read, write, discard, wait, signal and close consumes
  the remaining interval of one immutable `CLOCK_MONOTONIC` deadline.
- Every executable shell block is self-contained under `set -euo pipefail`.
  Masked failures, disabled error mode and unasserted negative commands are
  invalid receipts.
- One writer owns a file at a time. Each task has a dedicated commit plus fresh
  read-only spec-compliance and code-quality reviews.
- S4 implementation and S4 rebaseline documentation remain outside S3.

## Revision 7 documentation completion gate

This authoring phase changes only the two documents. It executes no project
code, test, build, helper or live effect. Before the docs-only commit, record
the pre-existing primer diff hash and run only static documentary checks:

~~~bash
set -euo pipefail
DOC_PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
test "$(git rev-parse HEAD)" = 7b3567637f2025c1b8c21338acad070d6561bcd9
test -z "$(git diff --cached --name-only)"
git diff --check
python3 -c 'from pathlib import Path; paths=[Path("docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md"),Path("docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md")]; [p.read_bytes().decode("utf-8") for p in paths]'
test "$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')" = "$DOC_PRIMER_DIFF_SHA256"
test "$(git status --short --untracked-files=all)" = " M primer.md
 M docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
 M docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md"
~~~

The static checker resets Markdown fence state for each file and includes a
negative fixture whose first file ends with an open fence and whose second file
starts with a close. It requires exact Revision 7 parent/status, one gate source
block, unique maps and ranges, 397 IDs/mutants/closures/manifests, policy counts
364/26/7, source/runtime/synthetic activation sets, all protocol/resource
constants, the public code table, 22/24 model alphabets with 5,399,043/8,308,825
traces and the 14-state/19-constructor/145-member/2,030-pair/2,034-assertion
EFSM. It rejects unresolved authoring markers and every superseded literal or
model named by the Revision 7 correction contract unless a test marks the value
as an explicit negative fixture.

Stage and commit only the two documents with exact message
`docs(storage): close S3 revision 7 review gaps`. No package or review gate is
run from the mutable checkout.

## Non-circular blind documentation review

The first review package is not generated by candidate code. The coordinator
freezes a full lowercase 40-hex `DOC_CANDIDATE` and supplies each reviewer an
external literal read-only Git-plumbing identity command. Its exact command
bytes and SHA-256 are recorded in every receipt and are not loaded from the
candidate repository.

Each reviewer independently:

1. requires `rev-parse DOC_CANDIDATE^{commit}` to equal the supplied OID;
2. reads each exact allowlisted path with `ls-tree -z`, requires one `100644
   blob`, checks `cat-file -s`, streams `cat-file blob`, hashes the bytes and
   reads both documents fully;
3. extracts but does not execute the embedded gate source and hashes the exact
   slice;
4. returns canonical keys `schema_version=1`, `profile=documentation`,
   `candidate`, `identity_command_sha256`, `gate_source_sha256`, bytewise-sorted
   `manifest_entries`, `axis`, `p0`, `p1`, `p2`, `minor`, `verdict`.

The four documentation paths are fixed:

~~~text
docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md
docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
native/macos/disk_image_keychain.swift
tests/test_disk_image_keychain_helper.py
~~~

Only three receipts for the identical candidate, identity command, gate source
and four tuples with `P0=P1=P2=0/PASS` authorize extracting and running the
candidate gate. Its package and canonical manifest must be byte-identical to
the independently streamed reviewer identities. A receipt from another
candidate, profile, manifest or source hash rejects. Negative pairs mix package
A receipt with package B manifest and attempt execution before three approvals.

## Embedded `CORTEX_S3_DOC_GATE_V1`

The plan contains exactly one complete gate program. Source bytes are those
after the opening `python` fence LF and before the closing fence line, including
one final LF. It is standard-library only and never imports or executes project
code.

<!-- CORTEX_S3_DOC_GATE_V1_BEGIN -->
```python
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

SCHEMA_VERSION = 1
GIT = "/usr/bin/git"
SOURCE_LIMIT = 1_048_576
BLOB_LIMIT = 4_194_304
SMALL_GIT_LIMIT = 1_048_576
PROFILES = {
    "documentation": (
        "docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md",
        "docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md",
        "native/macos/disk_image_keychain.swift",
        "tests/test_disk_image_keychain_helper.py",
    ),
    "final": (
        "docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md",
        "docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md",
        "native/macos/disk_image_keychain.swift",
        "tests/disk_image_keychain_harness.py",
        "tests/test_disk_image_keychain_helper.py",
    ),
}
GIT_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
BEGIN = b"<!-- CORTEX_S3_DOC_GATE_V1_" + b"BEGIN -->\n```python\n"
END = b"```\n<!-- CORTEX_S3_DOC_GATE_V1_" + b"END -->"


class GateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return (json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("ascii")


def validate_gitdir(raw):
    require(os.path.isabs(raw), "gitdir_not_absolute")
    path = os.path.normpath(raw)
    require(path == raw, "gitdir_not_normalized")
    info = os.lstat(path)
    require(stat.S_ISDIR(info.st_mode), "gitdir_not_directory")
    require(not stat.S_ISLNK(info.st_mode), "gitdir_symlink")
    return path


def validate_candidate(raw):
    require(OID_RE.fullmatch(raw) is not None, "candidate_not_full_lower_oid")
    return raw


def git_bytes(gitdir, limit, *args):
    require(limit >= 0, "negative_git_limit")
    argv = [GIT, "--no-replace-objects", "--git-dir=" + gitdir, *args]
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=GIT_ENV,
        cwd="/",
    )
    try:
        data = proc.stdout.read(limit + 1)
        require(len(data) <= limit, "git_output_cap")
        status = proc.wait(timeout=30)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        proc.stdout.close()
    require(status == 0, "git_status")
    return data


def resolve_commit(gitdir, candidate):
    resolved = git_bytes(
        gitdir,
        SMALL_GIT_LIMIT,
        "rev-parse",
        "--verify",
        candidate + "^{commit}",
    )
    require(resolved == (candidate + "\n").encode("ascii"), "commit_identity")


def read_entry(gitdir, candidate, path):
    require(path in PROFILES["final"], "path_not_internal_allowlist")
    require(not path.startswith(".superpowers/"), "forbidden_review_path")
    listing = git_bytes(
        gitdir,
        SMALL_GIT_LIMIT,
        "ls-tree",
        "-z",
        candidate,
        "--",
        path,
    )
    require(listing.endswith(b"\0"), "ls_tree_not_nul_terminated")
    records = listing[:-1].split(b"\0")
    require(len(records) == 1, "ls_tree_cardinality")
    prefix, actual_path = records[0].split(b"\t", 1)
    fields = prefix.split(b" ")
    require(len(fields) == 3, "ls_tree_shape")
    mode, kind, oid = fields
    require(mode == b"100644", "blob_mode")
    require(kind == b"blob", "blob_type")
    require(actual_path == path.encode("utf-8"), "blob_path")
    require(re.fullmatch(b"[0-9a-f]{40}", oid) is not None, "blob_oid")
    size_bytes = git_bytes(gitdir, 64, "cat-file", "-s", oid.decode("ascii"))
    require(re.fullmatch(b"0|[1-9][0-9]*\n", size_bytes) is not None, "blob_size")
    size = int(size_bytes)
    require(size <= BLOB_LIMIT, "blob_size_cap")
    data = git_bytes(gitdir, size, "cat-file", "blob", oid.decode("ascii"))
    require(len(data) == size, "blob_short_read")
    return {
        "path": path,
        "mode": "100644",
        "type": "blob",
        "size": size,
        "sha256": sha256(data),
    }, data


def source_bytes_and_hash():
    source_path = os.path.abspath(__file__)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(source_path, flags)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "gate_source_not_regular")
        require(info.st_nlink == 1, "gate_source_hardlink")
        require(info.st_size <= SOURCE_LIMIT, "gate_source_cap")
        chunks = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            require(chunk, "gate_source_short_read")
            chunks.append(chunk)
            remaining -= len(chunk)
        require(os.read(fd, 1) == b"", "gate_source_grew")
    finally:
        os.close(fd)
    data = b"".join(chunks)
    return data, sha256(data)


def collect(gitdir, candidate, profile):
    require(profile in PROFILES, "profile")
    resolve_commit(gitdir, candidate)
    entries = []
    blobs = {}
    for path in sorted(PROFILES[profile], key=lambda value: value.encode("utf-8")):
        entry, data = read_entry(gitdir, candidate, path)
        entries.append(entry)
        blobs[path] = data
    return entries, blobs


def manifest_for(profile, candidate, gate_source_sha256, entries):
    require(SHA_RE.fullmatch(gate_source_sha256) is not None, "gate_source_sha")
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "candidate": candidate,
        "gate_source_sha256": gate_source_sha256,
        "entries": entries,
    }


def extract_gate_source(plan):
    require(plan.count(BEGIN) == 1, "gate_begin_cardinality")
    require(plan.count(END) == 1, "gate_end_cardinality")
    start = plan.index(BEGIN) + len(BEGIN)
    finish = plan.index(END, start)
    source = plan[start:finish]
    require(source.endswith(b"\n"), "gate_source_final_lf")
    return source


def balanced_fences(data):
    opened = None
    for line in data.decode("utf-8").splitlines():
        token = None
        if line.startswith("```"):
            token = "```"
        elif line.startswith("~~~"):
            token = "~~~"
        if token is None:
            continue
        if opened is None:
            opened = token
        else:
            require(opened == token, "mixed_fence")
            opened = None
    require(opened is None, "open_fence")


def check_docs(gitdir, candidate):
    entries, blobs = collect(gitdir, candidate, "documentation")
    spec_path = "docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md"
    plan_path = "docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md"
    spec = blobs[spec_path]
    plan = blobs[plan_path]
    for data in (spec, plan):
        require(b"\r" not in data, "carriage_return")
        require(data.endswith(b"\n"), "missing_final_lf")
        data.decode("utf-8")
        balanced_fences(data)
    own_source, own_sha = source_bytes_and_hash()
    embedded = extract_gate_source(plan)
    require(embedded == own_source, "executed_gate_differs_from_plan")
    require(sha256(embedded) == own_sha, "gate_source_hash")
    gate_block_start = plan.index(BEGIN)
    gate_block_end = plan.index(END, gate_block_start) + len(END)
    plan_contract = plan[:gate_block_start] + plan[gate_block_end:]
    joined = spec + b"\n" + plan_contract
    required = (
        b"Revision 7",
        b"7b3567637f2025c1b8c21338acad070d6561bcd9",
        b"BrokerChildFreeLease",
        b"OpenUnresolvedHandle",
        b"NativeChildLifecycleEFSM",
        b"2,034",
        b"S3T1_01..S3T1_31",
        b"S3T2_01..S3T2_45",
        b"S3T3_01..S3T3_08",
        b"S3T4_01..S3T4_157",
        b"S3T5_01..S3T5_110",
        b"364 natural",
        b"26 synthetic_gate",
        b"7 baseline_characterization",
        b"CORTEX_S3_DOC_GATE_V1",
    )
    for token in required:
        require(token in joined, "missing_required_literal:" + token.decode("ascii"))
    for marker in (b"TO" + b"DO", b"T" + b"BD", b"FIX" + b"ME"):
        require(marker not in joined, "authoring_marker")
    return manifest_for("documentation", candidate, own_sha, entries)


def safe_components(root, relative):
    require(not os.path.isabs(relative), "absolute_package_path")
    parts = relative.split("/")
    require(parts and all(part not in ("", ".", "..") for part in parts), "path_component")
    current = root
    for part in parts[:-1]:
        current = os.path.join(current, part)
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:
            info = os.lstat(current)
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "package_parent")
    return os.path.join(root, *parts)


def write_exclusive(root, relative, data):
    target = safe_components(root, relative)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            require(count > 0, "package_write")
            view = view[count:]
        os.fsync(fd)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "package_file_type")
        require(info.st_nlink == 1, "package_file_hardlink")
        require(info.st_size == len(data), "package_file_size")
    finally:
        os.close(fd)


def read_regular(path, limit):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "package_not_regular")
        require(info.st_nlink == 1, "package_hardlink")
        require(info.st_size <= limit, "package_read_cap")
        data = b""
        remaining = info.st_size
        while remaining:
            chunk = os.read(fd, min(65_536, remaining))
            require(chunk, "package_short_read")
            data += chunk
            remaining -= len(chunk)
        require(os.read(fd, 1) == b"", "package_grew")
        return data
    finally:
        os.close(fd)


def package_files(root):
    result = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        names.sort(key=lambda value: value.encode("utf-8"))
        files.sort(key=lambda value: value.encode("utf-8"))
        for name in names:
            info = os.lstat(os.path.join(directory, name))
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "package_directory")
        for name in files:
            full = os.path.join(directory, name)
            info = os.lstat(full)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "package_member")
            result.append(os.path.relpath(full, root))
    return sorted(result, key=lambda value: value.encode("utf-8"))


def verify_tree(root, expected_manifest, blobs):
    require(os.path.isabs(root), "package_root_not_absolute")
    root_info = os.lstat(root)
    require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode), "package_root")
    expected_paths = ["manifest.json"] + ["files/" + path for path in blobs]
    require(package_files(root) == sorted(expected_paths, key=lambda value: value.encode("utf-8")), "package_members")
    manifest_bytes = read_regular(os.path.join(root, "manifest.json"), BLOB_LIMIT)
    require(manifest_bytes == canonical_json(expected_manifest), "manifest_bytes")
    parsed = json.loads(manifest_bytes.decode("ascii"))
    require(parsed == expected_manifest, "manifest_value")
    require(parsed["profile"] in PROFILES, "manifest_profile")
    require(tuple(entry["path"] for entry in parsed["entries"]) == tuple(PROFILES[parsed["profile"]]), "manifest_allowlist")
    for entry in parsed["entries"]:
        require(entry["mode"] == "100644" and entry["type"] == "blob", "manifest_entry_type")
        data = read_regular(os.path.join(root, "files", entry["path"]), BLOB_LIMIT)
        require(data == blobs[entry["path"]], "package_blob_bytes")
        require(len(data) == entry["size"], "package_blob_size")
        require(sha256(data) == entry["sha256"], "package_blob_hash")


def write_tree(root, manifest, blobs):
    for path in manifest["entries"]:
        write_exclusive(root, "files/" + path["path"], blobs[path["path"]])
    write_exclusive(root, "manifest.json", canonical_json(manifest))


def generate_package(gitdir, candidate, profile, destination):
    require(os.path.isabs(destination), "destination_not_absolute")
    destination = os.path.normpath(destination)
    require(not os.path.lexists(destination), "destination_exists")
    parent = os.path.dirname(destination)
    parent_info = os.lstat(parent)
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode), "destination_parent")
    entries, blobs = collect(gitdir, candidate, profile)
    _, gate_sha = source_bytes_and_hash()
    manifest = manifest_for(profile, candidate, gate_sha, entries)
    staging = tempfile.mkdtemp(prefix=".cortex-s3-package-", dir=parent)
    os.chmod(staging, 0o700)
    try:
        write_tree(staging, manifest, blobs)
        verify_tree(staging, manifest, blobs)
        os.rename(staging, destination)
        staging = None
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if staging is not None:
            shutil.rmtree(staging)
            require(not os.path.lexists(destination), "partial_package_published")
    return manifest


def verify_package(gitdir, candidate, profile, package):
    require(os.path.isabs(package), "package_not_absolute")
    entries, blobs = collect(gitdir, candidate, profile)
    _, gate_sha = source_bytes_and_hash()
    manifest = manifest_for(profile, candidate, gate_sha, entries)
    verify_tree(os.path.normpath(package), manifest, blobs)
    return manifest


def self_test_package():
    _, gate_sha = source_bytes_and_hash()
    candidate = "1" * 40
    paths = PROFILES["documentation"]
    blobs = {path: ("fixture:" + path + "\n").encode("utf-8") for path in paths}
    entries = [{
        "path": path,
        "mode": "100644",
        "type": "blob",
        "size": len(blobs[path]),
        "sha256": sha256(blobs[path]),
    } for path in paths]
    manifest = manifest_for("documentation", candidate, gate_sha, entries)
    checks = ("extra_entry", "wrong_hash", "forbidden_review_path")
    with tempfile.TemporaryDirectory(prefix="cortex-s3-doc-gate-") as parent:
        for check in checks:
            stage = os.path.join(parent, "stage-" + check)
            final = os.path.join(parent, "final-" + check)
            os.mkdir(stage, 0o700)
            write_tree(stage, manifest, blobs)
            if check == "extra_entry":
                write_exclusive(stage, "files/extra", b"x")
            elif check == "wrong_hash":
                os.unlink(os.path.join(stage, "manifest.json"))
                altered = json.loads(json.dumps(manifest))
                altered["entries"][0]["sha256"] = "0" * 64
                write_exclusive(stage, "manifest.json", canonical_json(altered))
            else:
                write_exclusive(stage, "files/.superpowers/review.txt", b"x")
            rejected = False
            try:
                verify_tree(stage, manifest, blobs)
                os.rename(stage, final)
            except GateError:
                rejected = True
            require(rejected, "negative_fixture_accepted:" + check)
            require(not os.path.lexists(final), "negative_fixture_published:" + check)
            shutil.rmtree(stage)
    return {"schema_version": SCHEMA_VERSION, "self_tests": list(checks), "status": "PASS"}


def main(argv):
    require(argv, "missing_command")
    command = argv[0]
    require(command in ("check-docs", "self-test-package", "generate-package", "verify-package"), "command")
    if command == "self-test-package":
        require(len(argv) == 1, "self_test_argv")
        result = self_test_package()
    elif command == "check-docs":
        require(len(argv) == 3, "check_docs_argv")
        result = check_docs(validate_gitdir(argv[1]), validate_candidate(argv[2]))
    elif command == "generate-package":
        require(len(argv) == 5, "generate_argv")
        gitdir = validate_gitdir(argv[1])
        candidate = validate_candidate(argv[2])
        require(argv[3] in PROFILES, "profile")
        result = generate_package(gitdir, candidate, argv[3], argv[4])
    else:
        require(len(argv) == 5, "verify_argv")
        gitdir = validate_gitdir(argv[1])
        candidate = validate_candidate(argv[2])
        require(argv[3] in PROFILES, "profile")
        result = verify_package(gitdir, candidate, argv[3], argv[4])
    sys.stdout.buffer.write(canonical_json(result))


try:
    main(sys.argv[1:])
except (GateError, OSError, ValueError, KeyError, UnicodeError, json.JSONDecodeError) as error:
    sys.stderr.write("CORTEX_S3_DOC_GATE_V1: " + str(error) + "\n")
    raise SystemExit(2)
```
<!-- CORTEX_S3_DOC_GATE_V1_END -->

The four commands are closed:

- `check-docs GITDIR CANDIDATE` checks exact committed documentation bytes and
  that the executed source equals the embedded slice;
- `self-test-package` runs the extra-entry, wrong-hash and forbidden-review-path
  negative fixtures and proves no final destination exists;
- `generate-package GITDIR CANDIDATE PROFILE ABSOLUTE_DESTINATION` publishes
  atomically from a private directory;
- `verify-package GITDIR CANDIDATE PROFILE ABSOLUTE_PACKAGE` re-streams Git
  identities and rejects every mismatch.

The caller cannot supply paths or an allowlist. Profiles are internal:
`documentation` has the four review paths and `final` adds only
`tests/disk_image_keychain_harness.py`. Every Git subprocess is exact
`/usr/bin/git --no-replace-objects --git-dir=<validated absolute gitdir>` under
an otherwise empty environment containing only common locale/PATH and
`GIT_NO_REPLACE_OBJECTS=1`, `GIT_CONFIG_NOSYSTEM=1`,
`GIT_CONFIG_GLOBAL=/dev/null`. Synthetic tests install hostile commit/blob
replace refs and hostile global/system config, then prove original-object
identity. The `honor_git_replace_objects` mutation must fail.

## Checkpoint and evidence protocol

Before Task 1, require `HEAD == IMPLEMENTATION_BASE == DOC_CANDIDATE`, index
empty, only the known unstaged `primer.md`, exact four-blob identities, three
matching documentation receipts, approved-gate self-tests and byte-identical
package/manifest comparison. Every task records base/head, exact changed paths,
primer diff hash, test source/closure hash, interpreter, argv, status, assertion
label and environment digest.

The exact common environment is
`LANG=C`, `LC_ALL=C`, `PATH=/usr/bin:/bin:/usr/sbin:/sbin`; its canonical digest
is `332a3faa28f88fd67e9b9295487b7bbe9c0b41e2828f4283db4f339be9557e85`.
No launch inherits HOME, Python/DYLD/virtualenv/site or Git configuration.

Policies are fixed before implementation:

1. `natural`: add the independent oracle and require its assertion RED under
   Python 3.11 before production behavior;
2. `baseline_characterization`: require GREEN on `IMPLEMENTATION_BASE`, GREEN
   after its owner task, mapped-mutant failure and restored GREEN;
3. `synthetic_gate`: reject an independently constructed invalid fixture; no
   correct final-tree case is described as naturally RED.

The seven characterization cases are exactly `R45`, `S3T4_07..S3T4_11` and
`S3C4_01`. The 26 synthetic cases are exactly existing `S3T5_25..S3T5_30`, new
`S3T5_71..S3T5_89` and `S3T5_109`. All other 364 cases are natural.

Every case freezes its full owner suite, expected failures and exclusivity
claim before mutation. The runner executes the whole frozen suite and compares
failures, errors, skips, timeouts and unexpected successes exactly. A mutant
receipt is valid only for the mapped assertion
`MUTANT_<CASE>_<MUTANT_NAME>`. Import, syntax, unrelated exception, timeout,
skip or learned expected set is invalid evidence. Source/synthetic fixtures
are private regular link-count-one objects, use unchanged oracles and prove
zero residue.

## Frozen executable domains and literals

The implementation copies, rather than reinterprets, these domains. Native
control states are exactly:

~~~text
spawnedActiveFramePending, suspended, validatedSuspended, suspendedCleanup,
running, exitedUnreaped, reapedAwaitingGroup, groupAbsentAwaitingCloses,
settledPendingBrokerFrame, unresolvedNoSignalAwaitingCloses,
unresolvedPendingBrokerFrame, retiredSettled, retiredUnresolved,
channelLostCleanup
~~~

The 19 constructor counts in order are
`4,6,5,1,6,9,11,28,6,7,7,6,5,7,7,6,9,6,9`, totalling 145 members.
They are `spawn`, `publishActive`, `validate`, `cancelObserved`, `resume`,
`observeExit`, `observeWaitability`, `mintSignalPermit`, `signal`, `wait`,
`reap`, `observeGroup`, `closeNative`, `workerChannelLost`,
`adminChannelLost`, `deliverWorkerFinal`, `acknowledgeWorkerFinal`,
`publishOrphan`, `acknowledgeOrphan`. The exhaustive matrix is 2,030
state/member pairs plus four external spawn assertions. Each invalid pair
returns the byte-identical extended registry and a zero action vector.

The CS3B common header is 96 bytes: magic 0/4, version 4/1, channel 5/1,
type 6/1, flags 7/1, header length 8/2, reserved 10/2, payload length 12/4,
session 16/16, generation 32/8, directional sequence 40/8, context SHA
48/32, stream offset 80/8, stream length 88/4 and subject ordinal 92/4.
Magic is ASCII `CS3B`, version 1, channels admin=1/worker=2, flags/reserved
zero, header length `0x0060`, and integers are big-endian. ACK payload is the
paired u64 sequence, so ACK frames are exactly 104 bytes.

Admin numeric types are exact:

| Code | Type | Payload | Ancillary |
| ---: | --- | ---: | ---: |
| `0x01` | `BROKER_READY` | JSON 1..4,000 | 0 |
| `0x02` | `BROKER_READY_ACK` | 8 | 0 |
| `0x03` | `TRANSFER_WORKER_FD` | JSON 145 | 16/one FD |
| `0x04` | `TRANSFER_WORKER_FD_ACK` | 8 | 0 |
| `0x05` | `WORKER_SPAWN_FAILED` | JSON 1..4,000 | 0 |
| `0x06` | `WORKER_SPAWN_FAILED_ACK` | 8 | 0 |
| `0x07` | `BROKER_ORPHAN_SETTLEMENT` | JSON 1..4,000 | 0 |
| `0x08` | `BROKER_ORPHAN_SETTLEMENT_ACK` | 8 | 0 |
| `0x09` | `BROKER_STOP` | 0 | 0 |
| `0x0a` | `BROKER_STOPPED_ACK` | 8 | 0 |
| `0x0b` | `ADMIN_LEASE_ACQUIRE` | 0 | 0 |
| `0x0c` | `ADMIN_LEASE_GRANTED_ACK` | 8 | 0 |
| `0x0d` | `ADMIN_LEASE_RELEASE` | 0 | 0 |
| `0x0e` | `ADMIN_LEASE_RELEASED_ACK` | 8 | 0 |

Worker types are `COMMAND_JSON=0x20`, `WIRE_SECRET=0x21`,
`COMMAND_ADMITTED_ACK=0x22`, `COMMAND_CANCEL=0x23`,
`COMMAND_CANCEL_ACK=0x24`, `WORKER_LEASE_ACQUIRE=0x25`,
`WORKER_LEASE_GRANTED_ACK=0x26`, `WORKER_LEASE_RELEASE=0x27`,
`WORKER_LEASE_RELEASED_ACK=0x28`, `STDOUT_CHUNK=0x30`,
`STDOUT_END=0x31`, `STDERR_CHUNK=0x32`, `STDERR_END=0x33`,
`BROKER_SETTLED_COMMAND_JSON=0x34`,
`BROKER_UNRESOLVED_COMMAND_JSON=0x35`, `BROKER_FINAL_ACK=0x36`.

The exact resource witnesses are:

| Boundary | Exact value |
| --- | ---: |
| admin frame/payload | 4,096 / 4,000 |
| worker frame/payload | 65,536 / 65,440 |
| native stdout/stderr | 1,048,576 each |
| base command | 40 frames / 2,109,072 bytes |
| secret plus cancel command | 43 frames / 2,109,412 bytes |
| seven-command invocation | 287 frames / 238 chunks / 14,764,244 bytes |
| normal/cancel worker traces | 835 / 829 frames; 42,185,060 / 42,184,460 bytes |
| admin count witness | 34 frames / 8,415 bytes |
| separate admin byte witness | 32 frames / 12,215 bytes |
| combined reachable frame maximum | 869 |
| combined byte accounting ceiling | 42,197,275; upper bound only |
| ancillary maximum/count/closed-session total | 16 bytes / one FD / 112 bytes |
| broker/worker rolling memory | 131,168 / 2,175,020 bytes |
| observer/Python rolling retained | 16,781,364 / 20,979,868 bytes |
| JSON depth/items/key/string/token/integer | 8 / 512 / 64 / 4,096 / 24,578 / 20 |
| discard per FD | 1,048,576 bytes / 250,000,000 ns |
| shared native discard | 2,097,152 bytes / 500,000,000 ns |
| observer STOP | 52 bytes |

`S3T4_84` changes only the observer total to the explicit negative fixture
16,781,312. `S3T4_90` changes only Python retained total to the explicit
negative fixture 20,975,668. Neither value is production data.

The public response table is independently literal in this plan:

| Public code(s) | Exit | Response presence |
| --- | ---: | --- |
| `OK` | 0 | exact operation-specific six-key response |
| `INVALID_REQUEST` | 64 | none; pre-accept only |
| `CLEANUP_NOT_AUTHORIZED` | 64 | exact six-key response after accept |
| `PROTOCOL_ERROR` | 65 | exact six-key response iff stdout remains usable |
| `RANDOM_GENERATION_FAILED`, `HDIUTIL_FAILED`, `IMAGE_ENCRYPTION_INVALID`, `KEYCHAIN_ITEM_COLLISION`, `KEYCHAIN_ITEM_NOT_FOUND`, `KEYCHAIN_ITEM_AMBIGUOUS`, `KEYCHAIN_INTERACTION_FORBIDDEN`, `KEYCHAIN_SECRET_INVALID`, `KEYCHAIN_FAILED`, `MOUNT_MAPPING_INVALID`, `MOUNT_CLEANUP_UNCLEAR`, `INTERNAL_ERROR` | 70 | exact six-key response after accept |
| `SUPERVISION_UNRESOLVED` | 74 | exact six-key response iff stdout remains usable |
| `CANCELLED` | 75 | none pre-accept; exact six-key response post-accept |

Internal process facts are never public codes. Post-accept non-OK responses
carry all six keys with null UUID/device/item count. OK tuples are create
`(uuid,null,1)`, mount `(uuid,device,1)`, detach `(uuid,device,null)`, inspect
`(uuid,null,1)` and delete `(uuid,null,0)`.

The proved-close order is also literal: artifact disposition; every invocation
retired; exclusive child-free lease plus empty broker registry; broker STOP,
EOFs, exact reap and group ESRCH; final observer snapshot; observer STOP,
EOFs, exact reap and group ESRCH; `DispositionReceipt`; `CLOSED_PROVED`.
At +115 a busy registry instead creates one `OpenUnresolvedHandle` and performs
none of the STOP/disposition/close/owner-exit transitions.

## Task 1: Models, legacy removal and native EFSM reference

**Files:** create `tests/disk_image_keychain_harness.py`; modify the test module
and Swift helper.

**Ownership:** normative R26-R32/R44; `S3T1_01..S3T1_31`.

- [ ] Create an importable nonfunctional harness skeleton without process or
  effect calls; missing behavior fails by an explicit assertion result.
- [ ] Preserve the independent 22-symbol lineage model and add
  `validation_exact`, `validation_failed`, `resume_confirmed`,
  `resume_nonconfirmed`, both suspended-cleanup results and
  `settlement_frame_published`; enumerate exactly 5,399,043 depth-0..5 traces.
- [ ] Add `prepare_mount_leaf` and `remove_mount_leaf` to the independent
  24-symbol effect model and enumerate exactly 8,308,825 depth-0..5 traces.
- [ ] Delete all obsolete routes before default test selection; their source
  mutant inserts one real typecheckable handler/dispatch branch.
- [ ] Implement an independent typed native EFSM reference with the exact 14
  states, 19 constructors, 145 members, 2,030 state/member pairs and four spawn
  factory assertions. Each rejection preserves complete extended registers and
  emits one sentinel syscall only under its mapped atomic mutant.
- [ ] Cover the exact causal action-vector traces and distinct worker final
  write/ACK boundary. `S3T1_26` owns retire-on-write, fused write+ACK and
  worker-EOF-success poisoned fixtures; `S3T1_29` owns strong equality;
  `S3T1_31` reaches exact ACK/orphan fallback.
- [ ] Run every owned method, mapped full owner-suite mutant and restored suite.
- [ ] Commit exactly the three declared files with message
  `test(storage): replace legacy process probes` and obtain both read-only
  reviews.

## Task 2: Broker-owned Swift supervision and publication

**Files:** modify Swift helper and test module.

**Ownership:** normative R06-R10/R33-R35/R39; `S3T2_01..S3T2_45`.

- [ ] Add private final broker/native registries and the 14-state EFSM. Worker
  code contains no native spawn, wait, signal or reap primitive.
- [ ] Register suspended spawn before active publication; validate identity to
  `validatedSuspended`; only confirmed resume reaches running. Split
  waitability, permit mint, signal, wait and reap; retain unresolved native
  obligations without signal authority.
- [ ] Bind every signal permit to registry/session/generation/digest,
  PID-vs-group target, exact signal, observation sequence and deadline. EINTR
  only reobserves; noChild/wrong/changed/not-waitable revokes authority. All
  TERM/KILL choices precede reap; post-reap token permits only group zero.
- [ ] Implement worker/admin channel-loss, worker final write, exact final ACK,
  orphan publication and exact orphan ACK as separate total transitions.
- [ ] Make the broker arbitrate one `BrokerChildFreeLease`. Under it, give each
  Security.framework/filesystem call a distinct same-turn terminal-polled,
  generation/callsite-bound permit. New child admission, replay, substitution,
  EOF and terminal branches are total.
- [ ] Implement distinct zero-child and child-bearing response publication
  orders plus `NoResponseRequiredProof`; partial response consumes its
  candidate into protocol abnormality.
- [ ] Keep complete six-value response and code/exit/response-presence oracles.
  Zero-child paths reject broker settlement/0x12; child paths require both.
- [ ] Run all owned matrices/mutants and commit with
  `feat(storage): add broker-owned native supervision`; obtain both reviews.

## Task 3: Command provenance and invocation classes

**Files:** modify Swift helper and test module.

**Ownership:** normative R01-R05/R11-R14/R37; `S3T3_01..S3T3_08`.

- [ ] Implement closed broker command contexts with fixed executable, argv,
  stdin policy, worker origin/cutoff digest and supervisor generation.
- [ ] Mint compensation only from exact broker-settled attach output and bind
  the one current-device detach plus absence query; no caller device exists.
- [ ] Authenticate `workflow70` for create/mount/inspect/delete and `detach26`
  for every public detach. Ordinary detach must fit normal cutoff; terminal
  detach starts after +72 and fits +98.
- [ ] Keep mount compensation an internal `workflow70` broker subcommand with
  original origin/cutoff. It is neither a second worker nor terminal reserve.
- [ ] Exercise equality/+1 and every class/origin/digest substitution; run
  full owner suites/mutants and commit with
  `feat(storage): bind broker command provenance`; obtain both reviews.

## Task 4: Python session, protocol, mount, observer and open state

**Files:** modify harness and test module.

**Ownership:** normative R15-R25/R36/R38/R45;
`S3T4_01..S3T4_157` plus owner-4 `S3C4_01`.

- [ ] Seal exact common environments and environment-digest receipts for every
  compiler, source copy, clock, observer, broker and worker launch.
- [ ] Start one persistent admin socket/broker before live issuance. For each
  worker transfer one separately created socket endpoint with exactly one
  SCM_RIGHTS FD and canonical context; validate ACK before closing sender copy
  or continuing. Freeze success/failure argv and FD ledgers.
- [ ] Implement the byte-exact CS3B v2 header/type tables, fragmentation,
  ancillary and JSON grammar. Test every N/N+1 frame, byte, item, nesting,
  key/string/token, sequence, stream, command/invocation/session, backlog and
  discard boundary with its legal witness.
- [ ] Freeze normal/cancel/admin witness decompositions, rolling memory totals
  and the two arithmetic omission mutants without claiming the conservative
  byte ceiling is equality-reachable.
- [ ] Add named `prepareMountLeaf` and final removal effects under the common
  admin permit dominator. Carry dev/ino/mode/UID; reopen after detach and use
  descriptor-relative no-follow checks/enumeration only.
- [ ] Publish the exact closed `InFlightPredecessor` table, three incompatible
  Keychain presence receipts and total tombstone/quarantine/delete outcomes.
- [ ] Keep the persistent observer rolling and private. Build source, typecheck,
  compile and link without launch; record ephemeral binary identity and
  revalidate same inode/hash immediately before spawn.
- [ ] Implement broker proved-close before final observer snapshot/STOP. Each
  broker/observer shutdown substep is atomic and consumes the normative
  post-reap group-zero invariant without duplicating its owner.
- [ ] At +115 mint `OpenUnresolvedHandle` without STOP/disposition/close/owner
  exit. Permit only native-terminal -> broker-close -> observer-finalize ->
  locked-non-PASS disposition. Distinguish live-observer supervision delay,
  actual observer loss and monotone SecurityAgent escalation.
- [ ] Ensure all Python mutations pass through
  `consume_admin_child_free_permit(callsite,generation,terminal_watermark)`;
  refuse double/cross-channel leases and stale polls with zero mutation.
- [ ] Run natural cases to RED/GREEN, the seven characterization cases through
  baseline/GREEN/mutant/GREEN, full owner suites and all mapped mutants. Commit
  with `test(storage): seal brokered live effect authority`; obtain both
  reviews.

## Task 5: Contained fixture, immutable evidence and S3 closure

**Files:** modify all three implementation files.

**Ownership:** normative R40-R43; `S3T5_01..S3T5_110`.

- [ ] Preserve the immediate guardian/witness fixture, report-GO-direct-exec
  PID, exact FD inventories/close ledgers, +0.75/+1.50/+2.00/+2.50/+3.00/+5.00
  schedule and capped process-free libproc absence scan.
- [ ] Seal CPython/loader/stdlib TCB facts, revalidate before GO, install the
  audit hook after first `import sys` and before exactly the remaining seven
  direct imports. Reject project/zip/site/dynamic/transitive escape.
- [ ] Use only the approved embedded gate SHA. Exercise external bootstrap
  identity, three approvals before execution, byte-identical packages, mixed
  receipt/package rejection and exact final profile.
- [ ] Add closed `SyntheticMutant`, full pre-frozen `OWNER_SUITE`, expected
  failures/exclusivity and exact full-suite result comparison.
- [ ] Extend the static AST closure through module/class execution, bases,
  metaclasses/MRO, annotations, descriptors/properties, implicit protocols and
  import side effects; reject every unresolved/dynamic edge.
- [ ] Normalize all expected SHA locations to 64 ASCII zeroes before computing
  stable byte ranges; populate real digests without offset movement.
- [ ] Before commit, stage exactly three files, prove no worktree delta on them,
  freeze `S3_PRECOMMIT_TREE`, construct an unreferenced temporary commit with
  parent `TASK_5_BASE` and create a private detached worktree. Run every final
  suite, mutant and restored suite only there, with absolute equipped
  interpreters and project imports beneath that tree.
- [ ] Require the manifest/runner to bind tree, temporary commit, ordinal,
  phase, case/test/mutant, target blob, closure hash, interpreter, argv, result,
  assertion label and environment digest. Remove the detached worktree and
  prove zero residue.
- [ ] Recheck the index tree and commit without restaging using
  `test(storage): add contained guardian witness`. Require exact parent and
  `S3_FINAL^{tree} == S3_PRECOMMIT_TREE`.
- [ ] Create a fresh private detached worktree at exact `S3_FINAL`; rerun all
  suites and 397 mutants from those bytes. Git gates receive repository and
  commit explicitly. Mutable-checkout imports, wrong tree/parent, retained
  residue and precommit-as-final receipts reject.
- [ ] Only after the complete postcommit rerun, generate the five-path final
  package with the approved gate, compare spec/plan/path identities and begin
  three fresh blind final implementation reviews. Any finding freezes S3.

## Immutable precommit and postcommit order

The exact order is normative:

~~~text
stage exact three implementation paths
-> prove no worktree delta for those paths
-> S3_PRECOMMIT_TREE = git write-tree
-> create unreferenced temporary commit(tree, TASK_5_BASE)
-> private detached worktree for temporary commit
-> full GREEN / MUTANT / RESTORED_GREEN sequence
-> remove worktree and prove zero residue
-> recheck index tree unchanged
-> commit without restaging
-> verify expected parent and S3_FINAL tree equality
-> fresh detached worktree at S3_FINAL
-> rerun complete suites and all 397 mutants
-> approved-gate final package and exact hash/path comparisons
-> three blind final implementation reviews
~~~

`S3_FINAL` is never named before the real commit. All Git-dependent commands
receive the validated Git directory and explicit commit. A file export without
Git metadata cannot stand in for a detached Git worktree. Final spec, plan and changed-path tests
run synthetically before commit, then against exact committed bytes after it;
recording a value without equality comparison fails.

## Normative regression map

The implementation must copy this exact dictionary. Values are unique,
fully-qualified unittest IDs:

~~~python
REGRESSION_TEST_IDS = {
    "R01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_unresolved_attach_text_cannot_issue_compensation",
    "R02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_present_original_group_blocks_attach_compensation",
    "R03": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_truncated_attach_output_cannot_issue_receipt",
    "R04": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_capped_attach_output_cannot_issue_receipt",
    "R05": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_settled_attach_allows_one_bound_detach_and_absence",
    "R06": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_held_pipe_exit_uses_exited_anchor_without_zombie_getsid",
    "R07": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_post_reap_token_allows_only_one_group_absence_observation",
    "R08": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_changed_or_incomplete_identity_blocks_resume_input_and_signal",
    "R09": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitid_matrix_issues_only_exact_exited_anchor",
    "R10": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_reap_echild_cannot_issue_native_settlement",
    "R11": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_insufficient_command_and_finalization_fit_spawns_nothing",
    "R12": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_single_helper_detach_cutoff_equality_and_next_nanosecond",
    "R13": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_single_helper_absence_stops_at_twenty_six_seconds",
    "R14": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_no_stage_can_reset_original_deadline",
    "R15": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_terminal_preobservation_blocks_every_ordinary_method",
    "R16": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_observer_precedes_compile_and_terminal_compile_mints_no_live_capability",
    "R17": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_caller_operands_cannot_construct_live_work",
    "R18": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_replayed_mounted_cursor_spawns_no_second_continuation",
    "R19": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_each_indexed_mount_issues_one_detach_absence_transition",
    "R20": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_detach_and_absence_use_one_current_mapping_helper",
    "R21": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_every_normal_and_terminal_branch_mints_one_disposition_then_close",
    "R22": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_ambiguous_current_mapping_preserves_without_followup_effect",
    "R23": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_after_keychain_delete_performs_no_later_keychain_effect",
    "R24": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_securityagent_verdict_precedes_observer_and_cleanup_errors",
    "R25": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_create_and_indexed_mount_evidence_advance_only_current_cursor",
    "R26": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_related_partial_and_foreign_uid_bridge_latch_uncertainty",
    "R27": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_partial_bridge_never_authorizes_grandchild_signal",
    "R28": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_live_reread_remains_partial",
    "R29": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_esrch_reread_is_vanished",
    "R30": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_late_child_is_never_adopted_or_signalled",
    "R31": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_reused_parent_birth_is_never_adopted_or_signalled",
    "R32": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_tracked_uid_sid_or_group_change_expires_authority",
    "R33": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_term_to_kill_exited_anchor_revalidation_matrix",
    "R34": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_kill_attempt_forbids_later_group_signal",
    "R35": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_obligation_survives_nonexact_reap_and_validate_race",
    "R36": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_total_helper_tuple_and_independent_close_failure_matrix",
    "R37": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_valid_output_without_native_settlement_has_no_authority",
    "R38": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_shared_clock_and_jump_matrix_stop_at_original_deadline",
    "R39": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_application_owned_secret_lifetime_and_erasure_matrix",
    "R40": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_active_cancel_requires_0x12_then_0x13_eof_and_exact_helper_reap",
    "R41": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_production_testing_routes_and_pre_post_exec_descriptor_inventories",
    "R42": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_dynamic_python311_python314_inventory_and_order_match",
    "R43": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_go_exec_libproc_probes_pass_twenty_fresh_runs_each",
    "R44": "tests.test_disk_image_keychain_helper.DiskImageKeychainLegacyRemovalTests.test_legacy_routes_handlers_and_tests_are_absent_before_default_suite",
    "R45": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_each_flag_and_authorization_near_miss_constructs_zero_live_objects",
}
~~~

## Normative mutant map

Each value selects one implementation branch:

~~~python
REGRESSION_MUTANTS = {
    "R01": "accept_unresolved_attach_output",
    "R02": "ignore_present_original_group",
    "R03": "accept_truncated_attach_output",
    "R04": "accept_capped_attach_output",
    "R05": "skip_bound_absence_query",
    "R06": "call_getsid_after_exact_exit",
    "R07": "issue_term_from_post_reap_token",
    "R08": "resume_changed_identity",
    "R09": "accept_wrong_waitid_pid",
    "R10": "treat_reap_echild_as_success",
    "R11": "spawn_without_finalization_fit",
    "R12": "admit_detach_one_nanosecond_late",
    "R13": "admit_absence_one_nanosecond_late",
    "R14": "recompute_compensation_deadline",
    "R15": "mint_ordinary_after_terminal",
    "R16": "compile_helper_before_observer_baseline",
    "R17": "accept_caller_operation",
    "R18": "accept_replayed_mounted_cursor",
    "R19": "issue_second_cycle_detach_absence",
    "R20": "split_detach_and_absence_helpers",
    "R21": "close_without_terminal_disposition_receipt",
    "R22": "detach_ambiguous_current_mapping",
    "R23": "requery_keychain_after_terminal_delete",
    "R24": "prefer_cleanup_error_verdict",
    "R25": "select_historical_mount_receipt",
    "R26": "ignore_related_partial",
    "R27": "bridge_partial_to_grandchild",
    "R28": "treat_live_reread_as_vanished",
    "R29": "reject_esrch_vanished",
    "R30": "adopt_late_child",
    "R31": "accept_reused_parent_birth",
    "R32": "signal_after_sid_change",
    "R33": "kill_without_exited_revalidation",
    "R34": "allow_term_after_kill",
    "R35": "drop_suspended_cleanup_obligation_before_reap",
    "R36": "accept_incomplete_helper_tuple",
    "R37": "mint_permit_without_native_proof",
    "R38": "use_python_monotonic_ns_for_shared_deadline",
    "R39": "leave_wire_live_at_outcome",
    "R40": "omit_settlement_frame_before_cancel_ack",
    "R41": "accept_invalid_fixture_fd",
    "R42": "omit_dynamic_test_class",
    "R43": "start_probe_cleanup_after_reserved_window",
    "R44": "retain_legacy_process_route",
    "R45": "normalize_authorization_flag",
}
~~~

## Task-local test and mutant maps

These methods are additional to, not substitutes for, the normative 45:

~~~python
TASK_LOCAL_TEST_IDS = {
    'S3T1_01': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_explorer_stamps_transition_indices_outside_reducer',
    'S3T1_02': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_reference_machines_match_full_actions_and_final_state',
    'S3T1_03': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_positive_signal_settlement_and_disposition_counters_are_nonzero',
    'S3T1_04': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_long_traces_cover_complete_disposition_and_replays',
    'S3T1_05': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLegacyRemovalTests.test_legacy_gate_runs_before_default_selection',
    'S3T1_06': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_artifact_cursor_reference_requires_two_complete_cycles',
    'S3T1_07': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_unresolved_effect_ledger_still_mints_one_disposition_and_close',
    'S3T1_08': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_state_domain_is_exact',
    'S3T1_09': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_constructor_domain_is_exact_and_has_no_abort',
    'S3T1_10': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_member_domains_are_exact',
    'S3T1_11': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_counts_are_145_2030_and_2034',
    'S3T1_12': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_spawn_factory_is_total',
    'S3T1_13': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_active_frame_transition_is_total',
    'S3T1_14': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_identity_transition_is_total',
    'S3T1_15': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_cancel_and_resume_transitions_are_total',
    'S3T1_16': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_exit_transition_is_total',
    'S3T1_17': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_waitability_transition_is_total',
    'S3T1_18': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_signal_permit_mint_is_total',
    'S3T1_19': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_signal_consumes_exact_permit',
    'S3T1_20': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_wait_transition_is_total',
    'S3T1_21': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_reap_transition_is_total',
    'S3T1_22': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_group_transition_is_total',
    'S3T1_23': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_close_transition_is_total',
    'S3T1_24': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_worker_loss_transition_is_total',
    'S3T1_25': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_admin_loss_transition_is_total',
    'S3T1_26': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_worker_final_write_and_ack_transitions_are_distinct_and_total',
    'S3T1_27': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_orphan_publication_transition_is_total',
    'S3T1_28': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_orphan_ack_transition_is_total',
    'S3T1_29': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_strong_equality_covers_every_opaque_register_including_worker_final_ack_pending',
    'S3T1_30': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_full_candidate_reference_matrix_matches',
    'S3T1_31': 'tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_native_efsm_causal_action_vector_traces_reach_exact_worker_final_ack',
    'S3T2_01': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_anchor_tokens_reject_foreign_registry_identity',
    'S3T2_02': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_supervisor_and_issuance_registries_are_private_final_classes',
    'S3T2_03': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_native_settlement_excludes_control_descriptor',
    'S3T2_04': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_total_dfa_rejects_duplicate_terminal_frame',
    'S3T2_05': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_pre_request_deadline_rejects_more_than_seventy_seconds',
    'S3T2_06': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_mutable_keychain_staging_is_erased',
    'S3T2_07': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_wire_is_erased_before_settlement_frame',
    'S3T2_08': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_normal_exit_kind_keeps_no_child_and_protocol_failure_distinct',
    'S3T2_09': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_anchor_retains_native_obligation_until_exact_reap',
    'S3T2_10': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_one_lifecycle_executor_linearizes_cancel_spawn_and_first_write',
    'S3T2_11': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_spawn_result_matrix_inserts_obligation_only_for_spawned',
    'S3T2_12': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_control_closes_only_after_final_normal_or_terminal_transition',
    'S3T2_13': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_validated_suspended_resume_result_and_cancel_matrix',
    'S3T2_14': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_failed_identity_validation_consumes_original_anchor',
    'S3T2_15': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_generation_overflow_closes_issuance_without_wrap',
    'S3T2_16': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_normal_exit_requires_complete_or_prefix_trace_proof',
    'S3T2_17': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_ok_response_values_include_exact_mount_item_count',
    'S3T2_18': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_non_ok_response_values_are_total_and_partial_free',
    'S3T2_19': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_native_child_lifecycle_efsm_has_exact_fourteen_states',
    'S3T2_20': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_only_broker_reaches_native_process_primitives',
    'S3T2_21': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_worker_loss_preserves_broker_native_obligation',
    'S3T2_22': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_wire_frames_mint_only_local_registry_receipts',
    'S3T2_23': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_signal_permit_binds_registry_generation_target_signal_sequence_and_deadline',
    'S3T2_24': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_eintr_never_mints_signal_permit_and_only_reobserves',
    'S3T2_25': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitable_signal_permit_replay_is_rejected',
    'S3T2_26': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitable_signal_permit_target_or_signal_substitution_is_rejected',
    'S3T2_27': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_still_running_retains_obligation_but_not_signal_permit',
    'S3T2_28': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitability_or_identity_loss_irrevocably_revokes_signal_authority',
    'S3T2_29': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_all_term_and_kill_decisions_precede_reap',
    'S3T2_30': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_free_lease_refuses_new_native_admission',
    'S3T2_31': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_no_active_child_proof_requires_exclusive_child_free_lease',
    'S3T2_32': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_free_lease_release_worker_eof_and_terminal_paths_are_total',
    'S3T2_33': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_free_permit_rejects_cross_generation_replay',
    'S3T2_34': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_free_permit_rejects_cross_syscall_substitution',
    'S3T2_35': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_secrandomcopybytes_has_same_turn_terminal_poll',
    'S3T2_36': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_secitemcopymatching_has_same_turn_terminal_poll',
    'S3T2_37': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_secitemadd_has_same_turn_terminal_poll',
    'S3T2_38': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_secitemdelete_has_same_turn_terminal_poll',
    'S3T2_39': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_post_delete_requery_has_same_turn_terminal_poll',
    'S3T2_40': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_free_filesystem_mutation_has_same_turn_terminal_poll',
    'S3T2_41': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_zero_child_publication_uses_lease_without_broker_settlement_or_0x12',
    'S3T2_42': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_child_bearing_publication_requires_broker_settlement_then_0x12',
    'S3T2_43': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_response_bearing_cancel_and_operational_error_use_trace_candidate',
    'S3T2_44': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_response_free_exit_consumes_no_response_required_proof',
    'S3T2_45': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_partial_response_consumes_candidate_into_protocol_abnormal',
    'S3T3_01': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_command_permit_rejects_foreign_supervisor_registry',
    'S3T3_02': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_absence_query_rejects_wrong_command_context',
    'S3T3_03': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_invocation_class_authenticates_exact_origin_hard_delta',
    'S3T3_04': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_ordinary_public_detach_uses_detach26_stages_and_normal_cutoff',
    'S3T3_05': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_terminal_public_detach_requires_plus_72_watermark_and_plus_98_fit',
    'S3T3_06': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_mount_compensation_detach_remains_workflow70_broker_subcommand',
    'S3T3_07': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_compensation_detach_keeps_workflow_origin_and_cannot_borrow_reserve',
    'S3T3_08': 'tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_every_broker_command_binds_worker_origin_and_cutoff_digest',
    'S3T4_01': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_preparation_is_one_shot_and_accepts_no_caller_paths',
    'S3T4_02': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_transfer_consumes_only_current_cursor',
    'S3T4_03': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_terminal_interleavings_cover_spawn_registration_and_first_write',
    'S3T4_04': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_waitid_waitpid_and_popen_lifecycle_match_after_exact_reap',
    'S3T4_05': 'tests.test_disk_image_keychain_helper.DiskImageKeychainRequestTests.test_all_ten_values_come_from_registered_context',
    'S3T4_06': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_move_uses_descriptor_relative_renameatx_exclusive_only',
    'S3T4_07': 'tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_integration_flag_aliases_are_rejected_without_normalization',
    'S3T4_08': 'tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_allow_effects_flag_aliases_are_rejected_without_normalization',
    'S3T4_09': 'tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_cleanup_approved_flag_aliases_are_rejected_without_normalization',
    'S3T4_10': 'tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_key_aliases_are_rejected',
    'S3T4_11': 'tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_value_near_misses_are_rejected_without_normalization',
    'S3T4_12': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_python_adapter_matches_task1_lineage_reference_for_r26_to_r32',
    'S3T4_13': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_post_latch_keychain_result_cannot_authorize_success',
    'S3T4_14': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_exact_reviewed_observer_source_typechecks_links_and_artifacts_are_deleted',
    'S3T4_15': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_observer_two_baselines_surround_helper_compile_before_live_issuance',
    'S3T4_16': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_artifact_cursor_has_exact_states_and_current_transfer_slot',
    'S3T4_17': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_two_indexed_mount_verify_detach_absence_cycles_complete',
    'S3T4_18': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_every_consuming_effect_returns_settled_or_unresolved_ledger',
    'S3T4_19': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_mounted_cursor_starts_exactly_one_continuation_helper',
    'S3T4_20': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_continuation_uses_exact_twenty_six_second_current_mapping_schedule',
    'S3T4_21': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_keychain_absence_is_required_before_image_delete_permit',
    'S3T4_22': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_existing_exclusive_target_is_unresolved_and_never_overwritten',
    'S3T4_23': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_every_helper_outcome_matches_complete_tuple',
    'S3T4_24': 'tests.test_disk_image_keychain_helper.DiskImageKeychainClockTests.test_twenty_shared_clock_samples_fit_fifty_millisecond_brackets',
    'S3T4_25': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_preparation_terminal_consumes_no_artifact_and_closes',
    'S3T4_26': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_no_artifact_cursor_cannot_duplicate_between_live_and_terminal',
    'S3T4_27': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_persistent_observer_protocol_is_bounded_sequenced_and_private',
    'S3T4_28': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_final_snapshot_eofs_and_exact_reap',
    'S3T4_29': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_late_observer_tick_is_unavailable_not_absence',
    'S3T4_30': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_disposition_cannot_mint_before_observer_exact_reap',
    'S3T4_31': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_every_effect_including_disposition_is_registered_in_flight',
    'S3T4_32': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_uncertainty_envelope_is_bounded_and_non_authorizing',
    'S3T4_33': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_terminal_wins_before_completion_pending_observation',
    'S3T4_34': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_observer_and_cancel_win_same_readiness_batch_and_completion_waits_for_watermark',
    'S3T4_35': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_live_schedule_exact_absolute_cutoffs_and_reserves',
    'S3T4_36': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_original_helper_total_tuple_eofs_and_reap_required_by_plus_71',
    'S3T4_37': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_cleanup_after_plus_106_cannot_restore_pass',
    'S3T4_38': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_detached_and_absent_requires_external_empty_mount_directory',
    'S3T4_39': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_observer_cutoff_equality_and_next_nanosecond_are_total',
    'S3T4_40': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_extra_keys_at_every_launch_site',
    'S3T4_41': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_missing_keys_at_every_launch_site',
    'S3T4_42': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_changed_values_at_every_launch_site',
    'S3T4_43': 'tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_every_reservation_binds_environment_profile_and_digest',
    'S3T4_44': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_ready_binds_exact_environment_digest',
    'S3T4_45': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_persistent_admin_socket_and_broker_ready_precede_live_issuance',
    'S3T4_46': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_fd_transfer_acks_canonical_context_before_continue',
    'S3T4_47': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_scm_rights_extra_fd_is_rejected',
    'S3T4_48': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_scm_rights_absent_fd_is_rejected',
    'S3T4_49': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_scm_rights_double_fd_is_rejected',
    'S3T4_50': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_scm_rights_truncation_and_msg_ctrunc_are_rejected',
    'S3T4_51': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_sender_duplicate_closes_only_after_exact_transfer_ack',
    'S3T4_52': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_missing_transfer_ack_is_rejected',
    'S3T4_53': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_inverted_transfer_ack_is_rejected',
    'S3T4_54': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_transferred_fd_is_cloexec_before_registry_insertion',
    'S3T4_55': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_transferred_fd_is_nonblocking_before_registry_insertion',
    'S3T4_56': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_wrong_broker_socket_family_is_rejected',
    'S3T4_57': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_spawn_failure_after_transfer_has_total_orphan_ledger',
    'S3T4_58': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_repeated_transfer_session_generation_or_digest_is_rejected',
    'S3T4_59': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_python_broker_worker_fixture_fd_ledgers_and_independent_closes_are_exact',
    'S3T4_60': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_partial_admin_frame_is_rejected',
    'S3T4_61': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_admin_frame_cap_plus_one_is_rejected',
    'S3T4_62': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_partial_worker_broker_frame_is_rejected',
    'S3T4_63': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_broker_frame_cap_plus_one_is_rejected',
    'S3T4_64': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_native_stdout_fragmentation_is_complete_and_bounded',
    'S3T4_65': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_native_stderr_fragmentation_is_complete_and_bounded',
    'S3T4_66': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_json_depth_cap_accepts_legal_equality_and_rejects_plus_one',
    'S3T4_67': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_settled_frame_mints_only_receiving_registry_receipt',
    'S3T4_68': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_orphan_frame_mints_only_receiving_registry_receipt',
    'S3T4_69': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_lost_worker_delivery_is_unresolved_and_never_worker_success',
    'S3T4_70': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_loss_before_native_spawn_closes_one_no_effect_orphan_ledger',
    'S3T4_71': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_loss_after_native_spawn_keeps_broker_cleanup_authority',
    'S3T4_72': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_loss_after_native_reap_keeps_orphan_delivery_obligation',
    'S3T4_73': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_worker_loss_after_native_closes_still_requires_orphan_ack',
    'S3T4_74': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_lost_orphan_ack_never_retires_or_reuses_generation',
    'S3T4_75': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_second_worker_waits_for_orphan_ledger_settlement',
    'S3T4_76': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_exact_orphan_ack_retires_safely_settled_native_obligation',
    'S3T4_77': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_canonical_json_decoder_accepts_legal_integer_equality_and_rejects_every_ambiguous_or_noncanonical_form',
    'S3T4_78': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_canonical_json_encoder_emits_exact_ascii_bytes',
    'S3T4_79': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_helper_exchange_caps_equal_frozen_resource_table',
    'S3T4_80': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_native_fixture_and_wire_caps_equal_frozen_resource_table',
    'S3T4_81': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_observer_config_report_and_token_caps_equal_frozen_resource_table',
    'S3T4_82': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_compiler_and_clock_caps_equal_frozen_resource_table',
    'S3T4_83': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_exec_status_go_guardian_and_witness_caps_equal_frozen_resource_table',
    'S3T4_84': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_native_helper_r43_observer_admin_and_worker_aggregate_caps_are_exact',
    'S3T4_85': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_announced_and_read_lengths_are_checked_before_allocation_or_extension',
    'S3T4_86': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_discard_drain_byte_budget_accepts_equality_and_rejects_plus_one',
    'S3T4_87': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_discard_drain_time_budget_accepts_equality_and_rejects_plus_one',
    'S3T4_88': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_discard_budget_exhaustion_enters_authorized_cleanup_until_terminal_deadline',
    'S3T4_89': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_no_channel_uses_communicate_unbounded_read_text_mode_or_read_to_end',
    'S3T4_90': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_python_retained_total_includes_one_admin_json_ack_pair',
    'S3T4_91': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_frame_cap_is_rolling_not_lifetime',
    'S3T4_92': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_sequence_overflow_is_unresolved_without_wrap',
    'S3T4_93': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_prepare_mount_leaf_is_named_inflight_effect_before_create',
    'S3T4_94': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_final_mount_leaf_removal_is_named_disposition_effect_with_closed_outcome',
    'S3T4_95': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_mount_leaf_is_mkdirat_openat_attested_and_carried_by_cursor',
    'S3T4_96': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_post_detach_absence_reopens_and_enumerates_same_leaf_identity',
    'S3T4_97': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_mount_leaf_identity_error_symlink_replacement_nonempty_and_close_matrix_preserves',
    'S3T4_98': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_inflight_predecessor_is_exact_closed_union_including_mount_broker_and_open_unresolved_outcomes',
    'S3T4_99': 'tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_every_predecessor_operation_pair_has_one_exact_successor',
    'S3T4_100': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_keychain_presence_receipts_are_three_incompatible_types',
    'S3T4_101': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_unapproved_present_item_goes_directly_to_keychain_still_present_quarantine',
    'S3T4_102': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_ambiguous_or_missing_requery_is_presence_unknown_and_preserve_only',
    'S3T4_103': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_deletion_tombstone_is_not_public_unapproved_quarantine_state',
    'S3T4_104': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_artifact_disposition_and_child_free_lease_precede_broker_stop',
    'S3T4_105': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_busy_broker_at_plus_115_mints_open_unresolved_handle_without_any_stop_or_close',
    'S3T4_106': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_open_unresolved_handle_is_strong_identity_one_shot_and_authorizes_only_native_broker_observer_late_close',
    'S3T4_107': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_broker_stop_is_refused_while_any_invocation_is_unretired',
    'S3T4_108': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_observer_stop_is_refused_before_broker_proved_close',
    'S3T4_109': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_python_owner_cannot_exit_while_session_is_open_unresolved',
    'S3T4_110': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_open_unresolved_preserves_securityagent_fail_precedence',
    'S3T4_111': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_open_unresolved_actual_observer_loss_is_observer_unavailable_unclear',
    'S3T4_112': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_later_proved_close_cannot_upgrade_locked_terminal_verdict',
    'S3T4_113': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_full_stop_write',
    'S3T4_114': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_stdout_eof',
    'S3T4_115': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_stderr_eof',
    'S3T4_116': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_reader_joins',
    'S3T4_117': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_exit_zero',
    'S3T4_118': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_exact_waitpid',
    'S3T4_119': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_postreap_group_esrch',
    'S3T4_120': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_every_descriptor_close',
    'S3T4_121': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_final_observer_snapshot_starts_only_after_broker_proved_close',
    'S3T4_122': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_final_snapshot',
    'S3T4_123': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_full_stop_write',
    'S3T4_124': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_stdin_flush_and_close',
    'S3T4_125': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_contiguous_stopped_frame',
    'S3T4_126': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_stdout_eof',
    'S3T4_127': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_stderr_eof',
    'S3T4_128': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_reader_joins',
    'S3T4_129': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_exit_zero',
    'S3T4_130': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_postreap_group_esrch',
    'S3T4_131': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_shutdown_requires_every_descriptor_close',
    'S3T4_132': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_observer_termination_outcome_has_stopped_and_terminal_failure_variants',
    'S3T4_133': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_session_progress_separates_closed_disposition_from_strong_one_shot_open_unresolved_handle',
    'S3T4_134': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_public_code_exit_and_response_presence_table_matches_independent_literal',
    'S3T4_135': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_non_scm_rights_ancillary_data_is_rejected',
    'S3T4_136': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_transferred_fd_alias_with_stdio_control_or_admin_is_rejected',
    'S3T4_137': 'tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_broker_shutdown_requires_stdin_flush_and_close',
    'S3T4_138': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_wrong_broker_socket_type_is_rejected',
    'S3T4_139': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_json_item_cap_accepts_legal_equality_and_rejects_plus_one',
    'S3T4_140': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_json_key_cap_accepts_legal_equality_and_rejects_plus_one',
    'S3T4_141': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_global_and_broker_effective_json_string_token_caps_have_legal_equality_witnesses_and_reject_plus_one',
    'S3T4_142': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_stream_chunk_cap_accepts_legal_equality_and_rejects_plus_one',
    'S3T4_143': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_per_command_frame_and_byte_caps_accept_unique_legal_equality_and_reject_plus_one',
    'S3T4_144': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_normal_and_cancel_session_traces_are_separate_unique_legal_maxima',
    'S3T4_145': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_v2_fourth_lease_tombstone_witness_accepts_admin_frame_34_rejects_35_and_separates_wire_byte_max',
    'S3T4_146': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_open_unresolved_with_live_observer_uses_supervision_unresolved_unclear_cause',
    'S3T4_147': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_securityagent_detection_after_plus_115_escalates_unclear_to_fail',
    'S3T4_148': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_v2_header_magic_version_channels_flags_offsets_and_endianness_are_byte_exact',
    'S3T4_149': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_v2_admin_numeric_type_payload_and_ancillary_table_is_exact',
    'S3T4_150': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_v2_worker_numeric_type_and_payload_table_is_exact',
    'S3T4_151': 'tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_broker_v2_python_and_swift_golden_vectors_are_byte_identical',
    'S3T4_152': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_prepare_mount_leaf_mkdirat_is_dominated_by_admin_child_free_permit',
    'S3T4_153': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_quarantine_rename_is_dominated_by_admin_child_free_permit',
    'S3T4_154': 'tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_image_unlink_is_dominated_by_admin_child_free_permit',
    'S3T4_155': 'tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_final_mount_leaf_removal_is_dominated_by_admin_child_free_permit',
    'S3T4_156': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_broker_refuses_second_or_cross_channel_child_free_lease',
    'S3T4_157': 'tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_admin_child_free_permit_rejects_stale_poll_before_mutation_and_releases_totally',
    'S3T5_01': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_is_immediate_and_self_expiry_is_containment_only',
    'S3T5_02': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_frame_without_control_eof_is_unclear',
    'S3T5_03': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_does_not_inherit_helper_control_fd',
    'S3T5_04': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_shared_clock_parent_deadline_and_endpoints_exist_before_popen',
    'S3T5_05': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_child_report_cannot_extend_parent_deadline',
    'S3T5_06': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_cleanup_reserve_precedes_hard_deadline',
    'S3T5_07': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_reaps_exact_unreaped_interpreter_on_every_failure',
    'S3T5_08': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_validates_complete_report_before_one_go',
    'S3T5_09': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_interpreter_execs_helper_in_same_registered_pid',
    'S3T5_10': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_popen_ast_has_exact_stdio_flags_and_pass_fds',
    'S3T5_11': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_pre_go_descriptor_inventory_is_exact',
    'S3T5_12': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_status_cloexec_eof_or_fixed_failure_record_is_total',
    'S3T5_13': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_post_exec_helper_descriptor_inventory_is_exact',
    'S3T5_14': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_short_supervisor_deadline_is_testing_only_and_production_rejects_it',
    'S3T5_15': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_cleanup_reserve_reaches_no_child_spawn_path',
    'S3T5_16': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_pid_count_and_fill_byte_capacity_are_not_conflated',
    'S3T5_17': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_full_pid_buffer_is_incomplete_not_absent',
    'S3T5_18': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_procargs_errno_identity_and_framing_are_never_absent',
    'S3T5_19': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_survivor_scan_pid_and_procargs_caps_are_fixed',
    'S3T5_20': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_survivor_scan_discards_every_command_buffer',
    'S3T5_21': 'tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_cleanup_scan_has_no_process_or_shell_launch_path',
    'S3T5_22': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFixtureCallGraphTests.test_compiler_ast_resolves_closed_fixture_call_graph',
    'S3T5_23': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFixtureCallGraphTests.test_reachable_forbidden_call_source_mutant_is_rejected',
    'S3T5_24': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_harness_helper_observer_and_fixture_hashes_match_reviewed_sources',
    'S3T5_25': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_typed_mutant_manifest_is_isomorphic_and_tamper_evident',
    'S3T5_26': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_source_mutants_preserve_oracle_hash_and_delete_private_copy',
    'S3T5_27': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_exact_allowlist_hash_manifest_refuses_three_negative_fixtures',
    'S3T5_28': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_spec_blob_hash_equals_reviewed_hash',
    'S3T5_29': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_plan_blob_hash_equals_reviewed_hash',
    'S3T5_30': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_cumulative_paths_equal_exact_three_files',
    'S3T5_31': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_both_modes_close_guardian_by_work_cutoff',
    'S3T5_32': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_self_expiry_cannot_satisfy_normal_success',
    'S3T5_33': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_binds_route_digest_paths_and_source_binary_hashes',
    'S3T5_34': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_failure_uses_fixed_errno_record_reserved_exit_and_exact_wait',
    'S3T5_35': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_missing_pass_fd_is_rejected_before_go',
    'S3T5_36': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_extra_pass_fd_is_rejected_before_go',
    'S3T5_37': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_duplicate_or_stdio_aliased_child_fd_is_rejected',
    'S3T5_38': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_status_is_only_child_fd_with_cloexec',
    'S3T5_39': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fresh_interpreter_stdio_are_exact_pipes',
    'S3T5_40': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_argv0_equals_absolute_reviewed_helper',
    'S3T5_41': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_helper_handoff_is_direct_exec_not_new_process',
    'S3T5_42': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_guardian_route_never_uses_production_deadline_flag',
    'S3T5_43': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_path_equals_absolute_reviewed_helper',
    'S3T5_44': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_fresh_bootstrap_source_hash_and_isolated_argv_are_exact',
    'S3T5_45': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_fresh_bootstrap_environment_is_exact_minimal_mapping',
    'S3T5_46': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_bootstrap_report_rejects_wrong_source_hash',
    'S3T5_47': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_bootstrap_installs_audit_hook_first_and_direct_imports_match_allowlist',
    'S3T5_48': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDescriptorTests.test_parent_closes_report_duplicate_for_eof',
    'S3T5_49': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDescriptorTests.test_parent_closes_go_duplicate_for_eof',
    'S3T5_50': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDescriptorTests.test_parent_closes_exec_status_duplicate_for_eof',
    'S3T5_51': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDescriptorTests.test_parent_and_helper_close_witness_duplicates_for_eof',
    'S3T5_52': 'tests.test_disk_image_keychain_helper.DiskImageKeychainDescriptorTests.test_parent_and_helper_close_control_duplicates_for_eof',
    'S3T5_53': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_serialization_is_deterministic',
    'S3T5_54': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_changed_covered_oracle_byte_changes_digest',
    'S3T5_55': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_domain_separator_is_bound',
    'S3T5_56': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_expected_attestation_fields_normalize_to_exactly_64_ascii_zeroes_and_reject_variable_lengths',
    'S3T5_57': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_self_referential_raw_oracle_serialization_is_rejected',
    'S3T5_58': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_extra_keys',
    'S3T5_59': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_missing_keys',
    'S3T5_60': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_changed_values',
    'S3T5_61': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_fresh_interpreter_environment_rejects_missing_keys',
    'S3T5_62': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_fresh_interpreter_environment_rejects_changed_values',
    'S3T5_63': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_worker_rejects_unsealed_test_mutant_selector',
    'S3T5_64': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_worker_environment_rejects_missing_keys',
    'S3T5_65': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_worker_environment_rejects_changed_values',
    'S3T5_66': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_binds_fresh_interpreter_environment_digest',
    'S3T5_67': 'tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_binds_worker_environment_digest',
    'S3T5_68': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_interpreter_tcb_receipt_rejects_group_or_world_writable_binary',
    'S3T5_69': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_interpreter_tcb_receipt_is_revalidated_before_go',
    'S3T5_70': 'tests.test_disk_image_keychain_helper.DiskImageKeychainBootstrapTests.test_transitive_imports_are_builtin_frozen_or_below_trusted_stdlib_roots',
    'S3T5_71': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_external_documentation_bootstrap_identity_is_receipt_hashed',
    'S3T5_72': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_each_reviewer_receipt_binds_exact_four_blob_identity',
    'S3T5_73': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_embedded_documentation_gate_cannot_execute_before_three_approvals',
    'S3T5_74': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_embedded_gate_package_is_byte_identical_to_external_bootstrap_package',
    'S3T5_75': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_review_receipt_and_manifest_cannot_mix_packages',
    'S3T5_76': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_task_five_reuses_only_approved_documentation_gate_sha',
    'S3T5_77': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_doc_candidate_equals_implementation_base_before_task_one',
    'S3T5_78': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_every_multicommand_shell_receipt_uses_fail_closed_pipefail',
    'S3T5_79': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_markdown_fence_state_resets_for_each_document',
    'S3T5_80': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_temporary_commit_has_exact_tree_and_parent',
    'S3T5_81': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_worktree_cwd_pythonpath_and_imports_are_detached',
    'S3T5_82': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_runner_refuses_mutable_checkout',
    'S3T5_83': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_runner_refuses_one_mutable_project_module',
    'S3T5_84': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_receipt_rejects_wrong_tree',
    'S3T5_85': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_precommit_receipt_rejects_wrong_parent',
    'S3T5_86': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_detached_worktree_cleanup_proves_zero_residue',
    'S3T5_87': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_git_dependent_gates_receive_explicit_repository_and_commit',
    'S3T5_88': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_all_final_suites_and_mutants_rerun_from_immutable_s3_final',
    'S3T5_89': 'tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_every_execution_receipt_binds_temporary_or_final_commit',
    'S3T5_90': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_manifest_freezes_full_owning_suite_before_mutation',
    'S3T5_91': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_manifest_freezes_expected_failures_and_exclusivity_before_mutation',
    'S3T5_92': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_expected_failure_set_never_comes_from_observed_output',
    'S3T5_93': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_structural_atomicity_policy_is_prefrozen_and_independently_oracled',
    'S3T5_94': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_mutant_runner_matches_full_failure_error_skip_timeout_and_success_set',
    'S3T5_95': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_swift_runtime_mutant_activation_is_sealed_and_testing_only',
    'S3T5_96': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_resolves_every_referenced_constant',
    'S3T5_97': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_rejects_dynamic_or_unresolved_project_calls',
    'S3T5_98': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_reached_module_initializers_and_class_bodies',
    'S3T5_99': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_descriptor_and_property_accessors',
    'S3T5_100': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_bases_metaclasses_and_mro',
    'S3T5_101': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_executable_annotations',
    'S3T5_102': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_top_level_import_side_effects',
    'S3T5_103': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_oracle_closure_includes_resolved_implicit_protocol_calls',
    'S3T5_104': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_observer_build_receipt_binds_ephemeral_compiler_and_binary_identity',
    'S3T5_105': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_observer_binary_inode_and_digest_are_revalidated_before_spawn',
    'S3T5_106': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_observer_binary_has_no_cross_build_expected_digest',
    'S3T5_107': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_replaced_observer_binary_is_rejected_before_spawn',
    'S3T5_108': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_fixed_width_attestation_normalization_preserves_all_closure_offsets',
    'S3T5_109': 'tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_git_identity_ignores_replace_refs_and_inherited_object_or_config_environment',
    'S3T5_110': 'tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_owner_suite_equals_exact_owner_projection_for_every_manifest_entry',
}

TASK_LOCAL_MUTANTS = {
    'S3T1_01': 'stamp_transition_index_inside_reducer',
    'S3T1_02': 'omit_effect_disposition_action',
    'S3T1_03': 'suppress_valid_signal_action',
    'S3T1_04': 'reject_valid_absence_to_quarantine_transition',
    'S3T1_05': 'select_default_before_legacy_gate',
    'S3T1_06': 'skip_second_artifact_cycle',
    'S3T1_07': 'drop_unresolved_ledger_before_close',
    'S3T1_08': 'omit_channel_lost_cleanup_state',
    'S3T1_09': 'retain_suspended_abort_constructor',
    'S3T1_10': 'change_waitability_member_domain',
    'S3T1_11': 'miscount_signal_intents',
    'S3T1_12': 'spawn_into_existing_efsm',
    'S3T1_13': 'advance_after_partial_active_frame',
    'S3T1_14': 'treat_changed_identity_as_exact',
    'S3T1_15': 'advance_nonconfirmed_resume_to_running',
    'S3T1_16': 'accept_wrong_exit_pid',
    'S3T1_17': 'treat_eintr_as_exact_waitability',
    'S3T1_18': 'mint_unbound_signal_permit',
    'S3T1_19': 'signal_without_consuming_permit',
    'S3T1_20': 'treat_still_running_as_reaped_wait',
    'S3T1_21': 'treat_reap_echild_as_exact',
    'S3T1_22': 'accept_present_group_as_absent',
    'S3T1_23': 'settle_partial_native_close_set',
    'S3T1_24': 'retire_on_worker_channel_loss',
    'S3T1_25': 'erase_safety_facts_on_admin_loss',
    'S3T1_26': 'retire_worker_final_on_write_before_ack',
    'S3T1_27': 'retire_on_partial_orphan_publication',
    'S3T1_28': 'retire_before_exact_orphan_ack',
    'S3T1_29': 'ignore_worker_final_ack_pending_in_strong_equality',
    'S3T1_30': 'emit_sentinel_syscall_on_rejected_pair',
    'S3T1_31': 'truncate_worker_final_trace_before_exact_ack',
    'S3T2_01': 'accept_foreign_anchor_registry',
    'S3T2_02': 'expose_nonfinal_supervisor',
    'S3T2_03': 'include_control_in_native_proof',
    'S3T2_04': 'accept_duplicate_terminal_frame',
    'S3T2_05': 'accept_deadline_over_seventy_seconds',
    'S3T2_06': 'retain_mutable_keychain_staging',
    'S3T2_07': 'emit_settlement_before_wire_erasure',
    'S3T2_08': 'conflate_normal_exit_kinds',
    'S3T2_09': 'consume_suspended_cleanup_on_first_attempt',
    'S3T2_10': 'add_competing_lifecycle_reader',
    'S3T2_11': 'treat_spawn_failure_as_active_obligation',
    'S3T2_12': 'close_control_after_intermediate_settlement',
    'S3T2_13': 'advance_running_before_resume_confirmation',
    'S3T2_14': 'retain_failed_validation_anchor',
    'S3T2_15': 'wrap_issuance_generation',
    'S3T2_16': 'accept_count_only_exit_proof',
    'S3T2_17': 'omit_mount_item_count',
    'S3T2_18': 'retain_partial_values_in_error_response',
    'S3T2_19': 'retain_stale_native_efsm_state_set',
    'S3T2_20': 'allow_worker_native_process_primitive',
    'S3T2_21': 'retire_native_obligation_on_worker_channel_loss',
    'S3T2_22': 'deserialize_wire_object_as_broker_receipt',
    'S3T2_23': 'omit_signal_observation_sequence_binding',
    'S3T2_24': 'mint_signal_permit_after_eintr',
    'S3T2_25': 'accept_replayed_waitable_signal_permit',
    'S3T2_26': 'accept_substituted_signal_permit_target',
    'S3T2_27': 'reuse_signal_permit_after_still_running',
    'S3T2_28': 'retain_signal_authority_after_waitability_loss',
    'S3T2_29': 'reap_before_term_kill_decision',
    'S3T2_30': 'admit_native_child_while_child_free_lease_held',
    'S3T2_31': 'mint_no_active_child_from_idle_snapshot',
    'S3T2_32': 'strand_child_free_lease_on_worker_eof',
    'S3T2_33': 'accept_cross_generation_child_free_permit',
    'S3T2_34': 'accept_cross_syscall_child_free_permit',
    'S3T2_35': 'skip_terminal_poll_before_secrandomcopybytes',
    'S3T2_36': 'skip_terminal_poll_before_secitemcopymatching',
    'S3T2_37': 'skip_terminal_poll_before_secitemadd',
    'S3T2_38': 'skip_terminal_poll_before_secitemdelete',
    'S3T2_39': 'skip_terminal_poll_before_post_delete_requery',
    'S3T2_40': 'skip_terminal_poll_before_child_free_filesystem_mutation',
    'S3T2_41': 'inject_settlement_frame_into_zero_child_path',
    'S3T2_42': 'omit_broker_settlement_before_child_response',
    'S3T2_43': 'publish_operational_error_without_trace_candidate',
    'S3T2_44': 'emit_response_free_exit_without_no_response_proof',
    'S3T2_45': 'mint_trace_proof_after_partial_response',
    'S3T3_01': 'accept_foreign_command_registry',
    'S3T3_02': 'accept_wrong_absence_context',
    'S3T3_03': 'accept_detach26_with_wrong_hard_origin_delta',
    'S3T3_04': 'route_ordinary_detach_through_workflow70',
    'S3T3_05': 'admit_terminal_detach_before_watermark',
    'S3T3_06': 'launch_compensation_as_detach26_worker',
    'S3T3_07': 'resample_compensation_origin',
    'S3T3_08': 'accept_broker_command_origin_digest_mismatch',
    'S3T4_01': 'accept_caller_compile_path',
    'S3T4_02': 'accept_copied_historical_cursor',
    'S3T4_03': 'release_executor_before_handle_registration',
    'S3T4_04': 'call_popen_poll_before_waitpid',
    'S3T4_05': 'accept_caller_request_path',
    'S3T4_06': 'use_nonexclusive_descriptor_move',
    'S3T4_07': 'accept_integration_flag_alias',
    'S3T4_08': 'accept_allow_effects_flag_alias',
    'S3T4_09': 'accept_cleanup_approved_flag_alias',
    'S3T4_10': 'accept_authorization_key_alias',
    'S3T4_11': 'normalize_authorization_value',
    'S3T4_12': 'continue_python_adapter_after_lineage_uncertainty',
    'S3T4_13': 'accept_post_latch_keychain_success',
    'S3T4_14': 'accept_observer_without_linked_binary',
    'S3T4_15': 'skip_second_observer_baseline',
    'S3T4_16': 'scan_historical_receipts_for_cursor',
    'S3T4_17': 'skip_second_mount_cycle',
    'S3T4_18': 'drop_unresolved_effect_outcome',
    'S3T4_19': 'launch_second_continuation_helper',
    'S3T4_20': 'reset_continuation_stage_deadline',
    'S3T4_21': 'delete_image_before_keychain_absence',
    'S3T4_22': 'overwrite_existing_quarantine_target',
    'S3T4_23': 'accept_response_without_exact_tuple',
    'S3T4_24': 'accept_clock_sample_outside_bracket',
    'S3T4_25': 'skip_preparation_terminal_disposition',
    'S3T4_26': 'duplicate_no_artifact_cursor',
    'S3T4_27': 'accept_observer_sequence_gap',
    'S3T4_28': 'skip_exact_observer_reap',
    'S3T4_29': 'accept_late_observer_tick',
    'S3T4_30': 'mint_disposition_before_observer_reap',
    'S3T4_31': 'start_disposition_without_inflight_registration',
    'S3T4_32': 'treat_uncertainty_envelope_as_authority',
    'S3T4_33': 'accept_completion_before_pending_terminal',
    'S3T4_34': 'prefer_helper_completion_in_same_readiness_batch',
    'S3T4_35': 'reset_live_absolute_cutoff',
    'S3T4_36': 'accept_missing_helper_reap_by_71',
    'S3T4_37': 'restore_pass_after_late_cleanup',
    'S3T4_38': 'accept_nonempty_mount_directory',
    'S3T4_39': 'admit_observer_cutoff_plus_one_nanosecond',
    'S3T4_40': 'add_home_to_base_exec_environment',
    'S3T4_41': 'omit_lc_all_from_base_exec_environment',
    'S3T4_42': 'change_base_exec_path_value',
    'S3T4_43': 'accept_environment_digest_mismatch',
    'S3T4_44': 'accept_observer_ready_without_environment_digest',
    'S3T4_45': 'start_worker_before_broker_ready',
    'S3T4_46': 'continue_worker_before_transfer_ack',
    'S3T4_47': 'accept_extra_scm_rights_fd',
    'S3T4_48': 'accept_absent_scm_rights_fd',
    'S3T4_49': 'accept_double_scm_rights_fd',
    'S3T4_50': 'accept_truncated_scm_rights',
    'S3T4_51': 'retain_scm_rights_sender_duplicate',
    'S3T4_52': 'accept_missing_transfer_ack',
    'S3T4_53': 'accept_inverted_transfer_ack',
    'S3T4_54': 'insert_transferred_fd_without_cloexec',
    'S3T4_55': 'insert_transferred_fd_without_nonblocking',
    'S3T4_56': 'accept_wrong_broker_socket_family',
    'S3T4_57': 'lose_transferred_fd_on_worker_spawn_failure',
    'S3T4_58': 'accept_repeated_broker_transfer_context',
    'S3T4_59': 'omit_broker_failure_close_ledger_entry',
    'S3T4_60': 'accept_partial_admin_frame',
    'S3T4_61': 'accept_admin_frame_cap_plus_one',
    'S3T4_62': 'accept_partial_worker_broker_frame',
    'S3T4_63': 'accept_worker_broker_frame_cap_plus_one',
    'S3T4_64': 'drop_native_stdout_fragment',
    'S3T4_65': 'drop_native_stderr_fragment',
    'S3T4_66': 'accept_broker_json_depth_plus_one',
    'S3T4_67': 'construct_broker_settled_receipt_from_wire_fields',
    'S3T4_68': 'construct_orphan_receipt_from_wire_fields',
    'S3T4_69': 'treat_lost_worker_delivery_as_success',
    'S3T4_70': 'lose_worker_before_native_spawn_without_orphan_ledger',
    'S3T4_71': 'abandon_native_child_on_worker_loss_after_spawn',
    'S3T4_72': 'strand_reaped_obligation_on_worker_loss',
    'S3T4_73': 'strand_closed_obligation_on_worker_loss',
    'S3T4_74': 'retire_orphan_without_python_ack',
    'S3T4_75': 'admit_second_worker_before_orphan_ack',
    'S3T4_76': 'keep_safely_settled_orphan_busy_after_ack',
    'S3T4_77': 'accept_json_trailing_bytes',
    'S3T4_78': 'emit_noncanonical_json_spacing',
    'S3T4_79': 'change_helper_stdout_cap',
    'S3T4_80': 'change_native_stdout_cap',
    'S3T4_81': 'change_observer_frame_cap',
    'S3T4_82': 'change_compiler_stdout_cap',
    'S3T4_83': 'change_exec_status_cap',
    'S3T4_84': 'omit_stop_from_observer_total',
    'S3T4_85': 'allocate_before_announced_length_cap',
    'S3T4_86': 'extend_discard_byte_budget_one_past_cap',
    'S3T4_87': 'extend_discard_time_budget_one_past_deadline',
    'S3T4_88': 'continue_discard_without_authorized_cleanup',
    'S3T4_89': 'use_unbounded_channel_read',
    'S3T4_90': 'omit_admin_from_python_retained_total',
    'S3T4_91': 'treat_observer_frame_cap_as_lifetime_limit',
    'S3T4_92': 'wrap_observer_sequence_after_uint64_max',
    'S3T4_93': 'skip_prepare_mount_leaf_inflight_effect',
    'S3T4_94': 'remove_mount_leaf_without_disposition_operation',
    'S3T4_95': 'create_mount_leaf_without_descriptor_identity',
    'S3T4_96': 'enumerate_pre_mount_directory_descriptor',
    'S3T4_97': 'accept_replaced_mount_leaf_as_absent',
    'S3T4_98': 'replace_inflight_predecessor_union_with_any',
    'S3T4_99': 'accept_unlisted_inflight_transition',
    'S3T4_100': 'conflate_keychain_presence_receipts',
    'S3T4_101': 'route_unapproved_quarantine_through_keychain_absent',
    'S3T4_102': 'treat_unknown_keychain_requery_as_absent',
    'S3T4_103': 'expose_deletion_tombstone_as_unapproved_quarantine',
    'S3T4_104': 'stop_broker_before_artifact_disposition',
    'S3T4_105': 'close_busy_broker_at_plus_115',
    'S3T4_106': 'replay_open_unresolved_handle',
    'S3T4_107': 'stop_broker_with_unretired_invocation',
    'S3T4_108': 'stop_observer_before_broker_proved_close',
    'S3T4_109': 'exit_python_owner_while_open_unresolved',
    'S3T4_110': 'downgrade_securityagent_fail_to_unclear',
    'S3T4_111': 'upgrade_observer_unavailable_to_fail',
    'S3T4_112': 'upgrade_terminal_unresolved_to_pass_on_close',
    'S3T4_113': 'accept_partial_broker_stop_write',
    'S3T4_114': 'accept_missing_broker_stdout_eof',
    'S3T4_115': 'accept_missing_broker_stderr_eof',
    'S3T4_116': 'skip_broker_reader_join',
    'S3T4_117': 'accept_nonzero_broker_exit',
    'S3T4_118': 'skip_exact_broker_reap',
    'S3T4_119': 'accept_present_broker_group_after_reap',
    'S3T4_120': 'ignore_broker_descriptor_close_failure',
    'S3T4_121': 'start_final_snapshot_before_broker_group_absence',
    'S3T4_122': 'skip_observer_final_snapshot',
    'S3T4_123': 'accept_partial_observer_stop_write',
    'S3T4_124': 'mint_stopped_before_observer_stdin_close',
    'S3T4_125': 'accept_missing_observer_stopped_frame',
    'S3T4_126': 'accept_missing_observer_stdout_eof',
    'S3T4_127': 'accept_missing_observer_stderr_eof',
    'S3T4_128': 'skip_observer_reader_join',
    'S3T4_129': 'accept_nonzero_observer_exit',
    'S3T4_130': 'mint_observer_stopped_without_group_absence',
    'S3T4_131': 'ignore_observer_descriptor_close_failure',
    'S3T4_132': 'collapse_observer_termination_outcome',
    'S3T4_133': 'close_open_unresolved_handle_directly',
    'S3T4_134': 'map_keychain_failed_to_exit_64',
    'S3T4_135': 'accept_non_scm_rights_ancillary_data',
    'S3T4_136': 'accept_broker_fd_alias',
    'S3T4_137': 'mint_broker_stopped_before_stdin_close',
    'S3T4_138': 'accept_wrong_broker_socket_type',
    'S3T4_139': 'accept_broker_json_item_count_plus_one',
    'S3T4_140': 'accept_broker_json_key_length_plus_one',
    'S3T4_141': 'accept_broker_json_string_token_length_plus_one',
    'S3T4_142': 'accept_broker_chunk_cap_plus_one',
    'S3T4_143': 'accept_broker_command_cap_plus_one',
    'S3T4_144': 'accept_broker_session_cap_plus_one',
    'S3T4_145': 'accept_admin_frame_count_35',
    'S3T4_146': 'misclassify_supervision_unresolved_as_observer_unavailable',
    'S3T4_147': 'ignore_post_cutoff_securityagent_detection',
    'S3T4_148': 'change_broker_magic_byte',
    'S3T4_149': 'reuse_admin_ack_type_discriminant',
    'S3T4_150': 'reuse_worker_ack_type_discriminant',
    'S3T4_151': 'encode_broker_generation_little_endian',
    'S3T4_152': 'bypass_admin_permit_for_prepare_mount_leaf_mkdirat',
    'S3T4_153': 'bypass_admin_permit_for_quarantine_rename',
    'S3T4_154': 'bypass_admin_permit_for_image_unlink',
    'S3T4_155': 'bypass_admin_permit_for_final_mount_leaf_removal',
    'S3T4_156': 'grant_cross_channel_double_child_free_lease',
    'S3T4_157': 'mutate_after_stale_admin_terminal_poll',
    'S3T5_01': 'suspend_fixture_spawn',
    'S3T5_02': 'accept_frame_without_control_eof',
    'S3T5_03': 'inherit_control_into_fixture',
    'S3T5_04': 'create_parent_deadline_after_popen',
    'S3T5_05': 'allow_child_report_deadline_extension',
    'S3T5_06': 'start_cleanup_at_parent_hard_deadline',
    'S3T5_07': 'skip_exact_interpreter_reap',
    'S3T5_08': 'send_go_before_report_validation',
    'S3T5_09': 'accept_report_pid_different_from_popen_pid',
    'S3T5_10': 'use_relative_fresh_interpreter',
    'S3T5_11': 'skip_pre_go_descriptor_inventory',
    'S3T5_12': 'accept_malformed_exec_status',
    'S3T5_13': 'skip_post_exec_descriptor_inventory',
    'S3T5_14': 'accept_test_short_deadline_in_production',
    'S3T5_15': 'spawn_during_cleanup_reserve',
    'S3T5_16': 'pass_pid_count_as_byte_count',
    'S3T5_17': 'treat_full_pid_buffer_as_absent',
    'S3T5_18': 'skip_procargs_error',
    'S3T5_19': 'remove_survivor_scan_caps',
    'S3T5_20': 'retain_scanned_command_bytes',
    'S3T5_21': 'use_ps_subprocess_for_survivor_scan',
    'S3T5_22': 'insert_reachable_unknown_call',
    'S3T5_23': 'insert_reachable_spawn_call',
    'S3T5_24': 'desynchronize_reviewed_helper_hash',
    'S3T5_25': 'accept_manifest_wrong_target_kind',
    'S3T5_26': 'mutate_oracle_copy',
    'S3T5_27': 'allow_extra_review_package_entry',
    'S3T5_28': 'record_spec_hash_without_comparison',
    'S3T5_29': 'record_plan_hash_without_comparison',
    'S3T5_30': 'accept_extra_implementation_path',
    'S3T5_31': 'hold_guardian_open_past_work_cutoff',
    'S3T5_32': 'count_fixture_self_expiry_as_success',
    'S3T5_33': 'accept_report_without_route_digest',
    'S3T5_34': 'swap_exec_failure_reserved_exit',
    'S3T5_35': 'omit_one_pass_fd',
    'S3T5_36': 'pass_extra_fd',
    'S3T5_37': 'allow_duplicate_child_fd',
    'S3T5_38': 'set_cloexec_on_wrong_fd',
    'S3T5_39': 'inherit_fresh_interpreter_stdio',
    'S3T5_40': 'exec_with_wrong_argv0',
    'S3T5_41': 'start_helper_with_popen_instead_of_exec',
    'S3T5_42': 'route_guardian_through_production_deadline_flag',
    'S3T5_43': 'exec_with_wrong_helper_path',
    'S3T5_44': 'omit_isolated_bootstrap_flag',
    'S3T5_45': 'inherit_fresh_environment',
    'S3T5_46': 'accept_wrong_bootstrap_hash',
    'S3T5_47': 'import_site_before_bootstrap_audit_hook',
    'S3T5_48': 'retain_report_writer_duplicate',
    'S3T5_49': 'retain_go_reader_duplicate',
    'S3T5_50': 'retain_exec_status_writer_duplicate',
    'S3T5_51': 'retain_witness_writer_duplicate',
    'S3T5_52': 'retain_control_child_duplicate',
    'S3T5_53': 'shuffle_canonical_oracle_records',
    'S3T5_54': 'exclude_changed_covered_oracle_byte',
    'S3T5_55': 'accept_changed_oracle_domain_separator',
    'S3T5_56': 'use_variable_length_attestation_placeholder',
    'S3T5_57': 'hash_self_referential_raw_manifest',
    'S3T5_58': 'add_home_to_sanitized_worker_environment',
    'S3T5_59': 'omit_lc_all_from_sanitized_worker_environment',
    'S3T5_60': 'change_sanitized_worker_path_value',
    'S3T5_61': 'omit_lc_all_from_fresh_interpreter_environment',
    'S3T5_62': 'change_fresh_interpreter_path_value',
    'S3T5_63': 'forward_unsealed_test_mutant_selector',
    'S3T5_64': 'omit_lang_from_worker_environment',
    'S3T5_65': 'change_worker_locale_value',
    'S3T5_66': 'accept_report_without_fresh_environment_digest',
    'S3T5_67': 'accept_report_without_worker_environment_digest',
    'S3T5_68': 'trust_group_writable_interpreter',
    'S3T5_69': 'skip_interpreter_tcb_revalidation_before_go',
    'S3T5_70': 'accept_project_origin_transitive_import',
    'S3T5_71': 'accept_unhashed_external_doc_bootstrap',
    'S3T5_72': 'accept_reviewer_receipt_without_blob_tuple',
    'S3T5_73': 'execute_embedded_doc_gate_before_approval',
    'S3T5_74': 'accept_nonidentical_embedded_gate_package',
    'S3T5_75': 'mix_package_a_receipt_with_package_b_manifest',
    'S3T5_76': 'reuse_unapproved_doc_gate_sha',
    'S3T5_77': 'accept_doc_candidate_different_from_implementation_base',
    'S3T5_78': 'allow_masked_shell_failure',
    'S3T5_79': 'carry_fence_state_across_documents',
    'S3T5_80': 'create_precommit_commit_with_wrong_tree',
    'S3T5_81': 'use_mutable_checkout_as_pythonpath',
    'S3T5_82': 'run_precommit_suite_from_mutable_checkout',
    'S3T5_83': 'import_one_mutable_checkout_module',
    'S3T5_84': 'accept_precommit_receipt_for_wrong_tree',
    'S3T5_85': 'accept_precommit_receipt_for_wrong_parent',
    'S3T5_86': 'retain_detached_worktree_residue',
    'S3T5_87': 'assume_git_context_from_raw_archive',
    'S3T5_88': 'accept_precommit_receipts_as_final',
    'S3T5_89': 'accept_receipt_without_temporary_commit',
    'S3T5_90': 'derive_owning_suite_after_mutation',
    'S3T5_91': 'omit_multiple_expected_failure_ids',
    'S3T5_92': 'learn_expected_failures_from_observed_output',
    'S3T5_93': 'choose_structural_atomicity_after_run',
    'S3T5_94': 'ignore_mutant_timeout_in_failure_set',
    'S3T5_95': 'read_unsealed_swift_mutant_selector',
    'S3T5_96': 'omit_referenced_constant_from_oracle_closure',
    'S3T5_97': 'accept_dynamic_oracle_call',
    'S3T5_98': 'ignore_module_initializer_side_effect',
    'S3T5_99': 'ignore_property_accessor_dependency',
    'S3T5_100': 'ignore_base_mro_dependency',
    'S3T5_101': 'ignore_annotation_dependency',
    'S3T5_102': 'ignore_import_side_effect_dependency',
    'S3T5_103': 'ignore_implicit_protocol_dependency',
    'S3T5_104': 'omit_observer_compiler_identity_from_receipt',
    'S3T5_105': 'skip_observer_binary_revalidation',
    'S3T5_106': 'assert_reproducible_observer_binary_hash',
    'S3T5_107': 'accept_replaced_observer_binary',
    'S3T5_108': 'shift_closure_offsets_after_digest_insertion',
    'S3T5_109': 'honor_git_replace_objects',
    'S3T5_110': 'truncate_owner_suite_projection',
}

BASELINE_CHARACTERIZATION_TEST_IDS = {
    "S3C4_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_all_eight_valid_flag_permutations_are_preserved",
}

BASELINE_CHARACTERIZATION_MUTANTS = {
    "S3C4_01": "reject_permuted_effect_flags",
}
~~~

The legacy-shaped strings in `S3T2_16/accept_count_only_exit_proof` and
`S3T5_57/hash_self_referential_raw_manifest` are explicit negative-fixture
identifiers only. Their unchanged oracles reject those behaviors; neither
string names an accepted production mechanism or closure algorithm.

The implementation must copy the dictionaries above exactly. The task-local
map has 351 unique keys/methods and exact owner ranges 31/45/8/157/110. With
45 normative keys and `S3C4_01`, `ALL_TEST_IDS` and `ALL_MUTANTS` each have
397 unique entries.

The frozen owner and activation declarations are:

~~~python
NORMATIVE_OWNER = {
    **{f"R{i:02d}": 3 for i in (*range(1, 6), *range(11, 15), 37)},
    **{f"R{i:02d}": 2 for i in (*range(6, 11), *range(33, 36), 39)},
    **{f"R{i:02d}": 4 for i in (*range(15, 26), 36, 38, 45)},
    **{f"R{i:02d}": 1 for i in (*range(26, 33), 44)},
    **{f"R{i:02d}": 5 for i in range(40, 44)},
}

SOURCE_MUTANT_TARGETS = {
    'R17': 'tests/disk_image_keychain_harness.py',
    'R38': 'tests/disk_image_keychain_harness.py',
    'R44': 'native/macos/disk_image_keychain.swift',
    'S3T2_02': 'native/macos/disk_image_keychain.swift',
    'S3T2_10': 'native/macos/disk_image_keychain.swift',
    'S3T2_19': 'native/macos/disk_image_keychain.swift',
    'S3T2_20': 'native/macos/disk_image_keychain.swift',
    'S3T2_21': 'native/macos/disk_image_keychain.swift',
    'S3T2_22': 'native/macos/disk_image_keychain.swift',
    'S3T2_23': 'native/macos/disk_image_keychain.swift',
    'S3T2_24': 'native/macos/disk_image_keychain.swift',
    'S3T2_25': 'native/macos/disk_image_keychain.swift',
    'S3T2_26': 'native/macos/disk_image_keychain.swift',
    'S3T2_27': 'native/macos/disk_image_keychain.swift',
    'S3T2_28': 'native/macos/disk_image_keychain.swift',
    'S3T2_29': 'native/macos/disk_image_keychain.swift',
    'S3T2_30': 'native/macos/disk_image_keychain.swift',
    'S3T2_31': 'native/macos/disk_image_keychain.swift',
    'S3T2_32': 'native/macos/disk_image_keychain.swift',
    'S3T2_33': 'native/macos/disk_image_keychain.swift',
    'S3T2_34': 'native/macos/disk_image_keychain.swift',
    'S3T2_35': 'native/macos/disk_image_keychain.swift',
    'S3T2_36': 'native/macos/disk_image_keychain.swift',
    'S3T2_37': 'native/macos/disk_image_keychain.swift',
    'S3T2_38': 'native/macos/disk_image_keychain.swift',
    'S3T2_39': 'native/macos/disk_image_keychain.swift',
    'S3T2_40': 'native/macos/disk_image_keychain.swift',
    'S3T2_41': 'native/macos/disk_image_keychain.swift',
    'S3T2_42': 'native/macos/disk_image_keychain.swift',
    'S3T2_43': 'native/macos/disk_image_keychain.swift',
    'S3T2_44': 'native/macos/disk_image_keychain.swift',
    'S3T2_45': 'native/macos/disk_image_keychain.swift',
    'S3T3_03': 'native/macos/disk_image_keychain.swift',
    'S3T3_04': 'native/macos/disk_image_keychain.swift',
    'S3T3_05': 'native/macos/disk_image_keychain.swift',
    'S3T3_06': 'native/macos/disk_image_keychain.swift',
    'S3T3_07': 'native/macos/disk_image_keychain.swift',
    'S3T3_08': 'native/macos/disk_image_keychain.swift',
    'S3T4_01': 'tests/disk_image_keychain_harness.py',
    'S3T4_04': 'tests/disk_image_keychain_harness.py',
    'S3T4_05': 'tests/disk_image_keychain_harness.py',
    'S3T4_06': 'tests/disk_image_keychain_harness.py',
    'S3T4_14': 'tests/disk_image_keychain_harness.py',
    'S3T4_40': 'tests/disk_image_keychain_harness.py',
    'S3T4_41': 'tests/disk_image_keychain_harness.py',
    'S3T4_42': 'tests/disk_image_keychain_harness.py',
    'S3T4_59': 'tests/disk_image_keychain_harness.py',
    'S3T4_78': 'tests/disk_image_keychain_harness.py',
    'S3T4_79': 'tests/disk_image_keychain_harness.py',
    'S3T4_80': 'tests/disk_image_keychain_harness.py',
    'S3T4_81': 'tests/disk_image_keychain_harness.py',
    'S3T4_82': 'tests/disk_image_keychain_harness.py',
    'S3T4_83': 'tests/disk_image_keychain_harness.py',
    'S3T4_84': 'tests/disk_image_keychain_harness.py',
    'S3T4_89': 'tests/disk_image_keychain_harness.py',
    'S3T4_93': 'tests/disk_image_keychain_harness.py',
    'S3T4_94': 'tests/disk_image_keychain_harness.py',
    'S3T4_95': 'tests/disk_image_keychain_harness.py',
    'S3T4_96': 'tests/disk_image_keychain_harness.py',
    'S3T4_98': 'tests/disk_image_keychain_harness.py',
    'S3T4_100': 'tests/disk_image_keychain_harness.py',
    'S3T4_103': 'tests/disk_image_keychain_harness.py',
    'S3T4_132': 'tests/disk_image_keychain_harness.py',
    'S3T4_133': 'tests/disk_image_keychain_harness.py',
    'S3T4_134': 'native/macos/disk_image_keychain.swift',
    'S3T4_148': 'native/macos/disk_image_keychain.swift',
    'S3T4_149': 'native/macos/disk_image_keychain.swift',
    'S3T4_150': 'native/macos/disk_image_keychain.swift',
    'S3T4_151': 'native/macos/disk_image_keychain.swift',
    'S3T4_152': 'tests/disk_image_keychain_harness.py',
    'S3T4_153': 'tests/disk_image_keychain_harness.py',
    'S3T4_154': 'tests/disk_image_keychain_harness.py',
    'S3T4_155': 'tests/disk_image_keychain_harness.py',
    'S3T5_09': 'tests/disk_image_keychain_harness.py',
    'S3T5_10': 'tests/disk_image_keychain_harness.py',
    'S3T5_14': 'native/macos/disk_image_keychain.swift',
    'S3T5_15': 'tests/disk_image_keychain_harness.py',
    'S3T5_21': 'tests/disk_image_keychain_harness.py',
    'S3T5_22': 'native/macos/disk_image_keychain.swift',
    'S3T5_23': 'native/macos/disk_image_keychain.swift',
    'S3T5_24': 'tests/disk_image_keychain_harness.py',
    'S3T5_35': 'tests/disk_image_keychain_harness.py',
    'S3T5_36': 'tests/disk_image_keychain_harness.py',
    'S3T5_37': 'tests/disk_image_keychain_harness.py',
    'S3T5_38': 'tests/disk_image_keychain_harness.py',
    'S3T5_39': 'tests/disk_image_keychain_harness.py',
    'S3T5_40': 'tests/disk_image_keychain_harness.py',
    'S3T5_41': 'tests/disk_image_keychain_harness.py',
    'S3T5_42': 'native/macos/disk_image_keychain.swift',
    'S3T5_43': 'tests/disk_image_keychain_harness.py',
    'S3T5_44': 'tests/disk_image_keychain_harness.py',
    'S3T5_45': 'tests/disk_image_keychain_harness.py',
    'S3T5_47': 'tests/disk_image_keychain_harness.py',
    'S3T5_48': 'tests/disk_image_keychain_harness.py',
    'S3T5_49': 'tests/disk_image_keychain_harness.py',
    'S3T5_50': 'tests/disk_image_keychain_harness.py',
    'S3T5_51': 'tests/disk_image_keychain_harness.py',
    'S3T5_52': 'tests/disk_image_keychain_harness.py',
    'S3T5_58': 'native/macos/disk_image_keychain.swift',
    'S3T5_59': 'native/macos/disk_image_keychain.swift',
    'S3T5_60': 'native/macos/disk_image_keychain.swift',
    'S3T5_61': 'tests/disk_image_keychain_harness.py',
    'S3T5_62': 'tests/disk_image_keychain_harness.py',
    'S3T5_63': 'tests/disk_image_keychain_harness.py',
    'S3T5_64': 'tests/disk_image_keychain_harness.py',
    'S3T5_65': 'tests/disk_image_keychain_harness.py',
    'S3T5_70': 'tests/disk_image_keychain_harness.py',
    'S3T5_90': 'tests/disk_image_keychain_harness.py',
    'S3T5_91': 'tests/disk_image_keychain_harness.py',
    'S3T5_93': 'tests/disk_image_keychain_harness.py',
    'S3T5_95': 'native/macos/disk_image_keychain.swift',
    'S3T5_96': 'tests/disk_image_keychain_harness.py',
    'S3T5_97': 'tests/disk_image_keychain_harness.py',
    'S3T5_98': 'tests/disk_image_keychain_harness.py',
    'S3T5_99': 'tests/disk_image_keychain_harness.py',
    'S3T5_100': 'tests/disk_image_keychain_harness.py',
    'S3T5_101': 'tests/disk_image_keychain_harness.py',
    'S3T5_102': 'tests/disk_image_keychain_harness.py',
    'S3T5_103': 'tests/disk_image_keychain_harness.py',
    'S3T5_104': 'tests/disk_image_keychain_harness.py',
    'S3T5_106': 'tests/disk_image_keychain_harness.py',
    'S3T5_108': 'tests/disk_image_keychain_harness.py',
    'S3T5_110': 'tests/disk_image_keychain_harness.py',
}

SWIFT_RUNTIME_CASES = frozenset({
    *(f"R{i:02d}" for i in (*range(1, 15), *range(33, 36), 37, 39, 40, 41)),
    *(f"S3T2_{i:02d}" for i in range(1, 19)),
    "S3T3_01", "S3T3_02", "S3T5_01", "S3T5_03",
}) - SOURCE_MUTANT_TARGETS.keys()
assert len(SWIFT_RUNTIME_CASES) == 41

BASELINE_CHARACTERIZATION_CASES = frozenset({
    "R45",
    *(f"S3T4_{i:02d}" for i in range(7, 12)),
    "S3C4_01",
})

SYNTHETIC_GATE_CASES = frozenset({
    *(f"S3T5_{i:02d}" for i in range(25, 31)),
    *(f"S3T5_{i:02d}" for i in range(71, 90)),
    "S3T5_109",
})
assert len(BASELINE_CHARACTERIZATION_CASES) == 7
assert len(SYNTHETIC_GATE_CASES) == 26

def owner_for(case: str) -> int:
    if case in NORMATIVE_OWNER:
        return NORMATIVE_OWNER[case]
    if case == "S3C4_01":
        return 4
    match = re.fullmatch(r"S3T([1-5])_(?:0[1-9]|[1-9][0-9]{1,2})", case)
    if match is None:
        raise ValueError("unknown case")
    return int(match.group(1))

def red_policy_for(case: str) -> str:
    if case in BASELINE_CHARACTERIZATION_CASES:
        return "baseline_characterization"
    if case in SYNTHETIC_GATE_CASES:
        return "synthetic_gate"
    return "natural"

ALL_TEST_IDS = MappingProxyType(
    REGRESSION_TEST_IDS | TASK_LOCAL_TEST_IDS | BASELINE_CHARACTERIZATION_TEST_IDS
)
ALL_MUTANTS = MappingProxyType(
    REGRESSION_MUTANTS | TASK_LOCAL_MUTANTS | BASELINE_CHARACTERIZATION_MUTANTS
)
assert len(ALL_TEST_IDS) == len(ALL_MUTANTS) == 397
assert ALL_TEST_IDS.keys() == ALL_MUTANTS.keys()
assert len(SOURCE_MUTANT_TARGETS) == 123

OWNER_SUITE = MappingProxyType({
    owner: tuple(sorted(
        (case for case in ALL_TEST_IDS if owner_for(case) == owner),
        key=lambda value: value.encode("utf-8"),
    ))
    for owner in range(1, 6)
})
~~~

The 228 Revision 7 additions decompose exactly into 120 runtime, 88 source and
20 synthetic activations. `S3T5_109` is synthetic and has no source target.
Every other case outside `SOURCE_MUTANT_TARGETS` and `SYNTHETIC_GATE_CASES` is
a runtime activation whose target is selected by the closed runtime registry;
tests and oracle modules are never mutation targets.

The typed manifest union is exact:

~~~python
@dataclass(frozen=True, slots=True)
class RuntimeMutant:
    kind: Literal["runtime"]
    case: str
    owner: int
    test_id: str
    mutant_name: str
    target_file: str
    runtime_branch: str
    oracle_id: str
    oracle_sha256: str
    assertion_label: str
    red_policy: str
    owning_suite_test_ids: tuple
    expected_failure_test_ids: tuple
    exclusivity_claim: str

@dataclass(frozen=True, slots=True)
class SourceMutant:
    kind: Literal["source"]
    case: str
    owner: int
    test_id: str
    mutant_name: str
    target_file: str
    unique_anchor: str
    replacement: str
    oracle_id: str
    oracle_sha256: str
    assertion_label: str
    red_policy: str
    owning_suite_test_ids: tuple
    expected_failure_test_ids: tuple
    exclusivity_claim: str

@dataclass(frozen=True, slots=True)
class SyntheticMutant:
    kind: Literal["synthetic"]
    case: str
    owner: int
    test_id: str
    mutant_name: str
    fixture_builder_id: str
    builder_source_sha256: str
    builder_closure_sha256: str
    transformation_id: str
    private_fixture_root_contract: str
    cleanup_zero_residue_contract: str
    oracle_id: str
    oracle_sha256: str
    assertion_label: str
    red_policy: str
    owning_suite_test_ids: tuple
    expected_failure_test_ids: tuple
    exclusivity_claim: str

MUTANT_MANIFEST: MappingProxyType[
    str, RuntimeMutant | SourceMutant | SyntheticMutant
]
~~~

`SyntheticMutant` structurally rejects a target file, source range/anchor and
runtime selector. Its serialized closure includes its builder and cleanup
logic. Every record freezes
`owning_suite_test_ids == OWNER_SUITE[owner]`, expected failures and exclusivity
before observation. No output may populate those fields.

`ORACLE_CLOSURE_SHA256` is a literal 397-entry map. `ORACLE_CLOSURE` and
`MUTANT_MANIFEST` have the same exact key set. Closure serialization begins
with `CORTEX_S3_ORACLE_CLOSURE_V1\0`, resolves the full closed semantic graph
and normalizes every expected SHA location to 64 ASCII zeroes before fixed byte
ranges are computed. Digests are compared outside their own payload. The
runner recomputes closure before and after every full-owning-suite mutant run.

Source mutants use one private, owner-only, no-follow, link-count-one copy and
one typecheckable transformation; synthetic mutants build one private fixture.
Both use unchanged oracles, independently clean every owned path and prove zero
residue. Runtime Swift selectors are accepted only by a sealed testing worker
and are bound into its config/report and environment digest.

## Task ownership

| Task | Normative IDs | Task-local/characterization IDs | Final count | Boundary |
| --- | --- | --- | ---: | --- |
| 1 | R26-R32, R44 | `S3T1_01..S3T1_31` | 31 | Independent lineage/effect models, legacy removal and exact native EFSM reference. |
| 2 | R06-R10, R33-R35, R39 | `S3T2_01..S3T2_45` | 45 | Broker-only native primitives, permit-aware EFSM, child-free lease and response publication. |
| 3 | R01-R05, R11-R14, R37 | `S3T3_01..S3T3_08` | 8 | Broker command provenance, invocation classes and immutable deadline origins. |
| 4 | R15-R25, R36, R38, R45 | `S3T4_01..S3T4_157`, `S3C4_01` | 158 | Environments, broker protocol/transfer, resources, mount identity, observer, open state and Python permits. |
| 5 | R40-R43 | `S3T5_01..S3T5_110` | 110 | Contained fixture, interpreter TCB, non-circular gate, immutable worktrees, manifest/closure and final comparison. |

Arithmetic is exact:

~~~text
new task-local       = 24 + 27 + 6 + 118 + 53 = 228
all task-local       = 31 + 45 + 8 + 157 + 110 = 351
ALL_TEST_IDS         = 45 normative + 351 task-local + 1 S3C4_01 = 397
MUTANT_MANIFEST      = 397
red policies         = 364 natural + 26 synthetic_gate + 7 baseline_characterization
new activations      = 120 runtime + 88 source + 20 synthetic = 228
~~~

## Execution-contract traceability

| Contract | Primary specification section | Plan owner/range |
| --- | --- | --- |
| Persistent broker, socket transfer, worker/orphan ACK ledgers | Component/process boundary; Broker protocol v2 | Task 2; S3T2_20-S3T2_22; Task 4 S3T4_45-S3T4_76 |
| Permit-aware native EFSM and exact 2,034 assertions | Native lifecycle EFSM | Task 1 S3T1_08-S3T1_31; Task 2 S3T2_19/S3T2_23-S3T2_29 |
| Exclusive child-free lease and per-call permits | Child-free mutation authority | Task 2 S3T2_30-S3T2_40; Task 4 S3T4_152-S3T4_157 |
| Zero-child/child response publication and stable public table | Invocation classes, deadlines and publication | Task 2 S3T2_41-S3T2_45; Task 4 S3T4_134 |
| Exact environments and interpreter TCB | Exact environments and interpreter TCB | Task 4 S3T4_40-S3T4_44; Task 5 S3T5_58-S3T5_70 |
| CS3B v2 bytes, JSON, caps, witnesses and discards | Broker protocol v2 | Task 4 S3T4_60-S3T4_92/S3T4_135-S3T4_151 |
| Mount leaf, in-flight table and Keychain presence variants | Artifact, mount and in-flight algebra | Task 4 S3T4_93-S3T4_103/S3T4_152-S3T4_155 |
| Broker close, observer close, open-unresolved late close and verdict monotonicity | Observer, closure and open-unresolved progress | Task 4 S3T4_104-S3T4_133/S3T4_146-S3T4_147 |
| Public detach class, compensation origin and cutoff digest | Invocation classes, deadlines and publication | Task 3 S3T3_03-S3T3_08 |
| Non-circular docs gate and hostile Git identity | Non-circular review and immutable final tree | Task 5 S3T5_71-S3T5_89/S3T5_109 |
| Full owner suites, three mutant variants and semantic closure | Test inventory, mutants and closure | Task 5 S3T5_90-S3T5_108/S3T5_110 |
| Immutable precommit/final detached execution | Non-circular review and immutable final tree | Task 5 S3T5_80-S3T5_89; final order |

## Revision 7 finding closure

| Findings | Closure |
| --- | --- |
| 1-8 | Exact non-inheriting environments, TCB receipt, bounded IPC and no unbounded read path. |
| 9-16 | Broker-owned native lifetime, permit-aware no-signal states, worker/orphan ACK and exclusive child-free lease. |
| 17-23 | Mount identity, closed in-flight union, three Keychain presence outcomes, exact response proof and public exit table. |
| 24-30 | Invocation classes, current-mapping detach, +71/+72/+98 timing, rolling observer and proved-close order. |
| 31-35 | `OPEN_UNRESOLVED`, one-shot late-close handle, cause separation and SecurityAgent monotone precedence. |
| 36-41 | External first identity review, approved embedded gate, temporary commits/worktrees, full owning suites and closed semantic graph. |
| 42-46 | Ephemeral observer binary identity, fixed-width attestation normalization, CS3B v2 framing and exact resource witnesses. |
| 47-50 | Python admin permit dominator, no-replace Git identity, closed `SyntheticMutant` and independent `OWNER_SUITE`. |

## Final self-review checklist

- [ ] Status is Revision 7, parent is exactly
  `7b3567637f2025c1b8c21338acad070d6561bcd9`, and neither document claims
  approval.
- [ ] Python owns one persistent broker and observer; workers never invoke
  native process primitives, and worker loss preserves broker cleanup.
- [ ] Transfer uses one SCM_RIGHTS FD plus exact ACK; every FD/argv/environment
  ledger and independent close branch is total.
- [ ] CS3B v2 header, types, JSON, chunks, counts, byte witnesses, rolling
  memory and discard limits equal the frozen literals and all have N/N+1 tests.
- [ ] The native EFSM has 14 states, 19 constructors, 145 members, 2,030 pairs
  and 2,034 assertions; final write and ACK are distinct.
- [ ] Every TERM/KILL consumes an exact one-shot permit before reap; noChild,
  wrong identity/waitability or EINTR never creates authority.
- [ ] One `BrokerChildFreeLease` spans admin and worker channels; each Swift and
  Python child-free call consumes a same-turn terminal-polled callsite permit.
- [ ] `prepareMountLeaf` and final removal are named in-flight effects carrying
  dev/ino/mode/UID; post-detach verification reopens the leaf.
- [ ] In-flight predecessor/successor maps are closed; ambiguous ledgers remain
  sets, and the three Keychain presence receipts are incompatible.
- [ ] Public detach is always `detach26`; internal compensation remains the
  originating `workflow70` broker subcommand.
- [ ] Zero-child and child-bearing response orders are separate; partial writes
  cannot mint proof; the public code/exit/response table is literal.
- [ ] Broker proved-close precedes final observer snapshot/STOP. Every shutdown
  substep, exact reap, group ESRCH and FD close is required.
- [ ] Busy +115 creates `OpenUnresolvedHandle` with no STOP/disposition/close or
  owner exit; late close locks non-PASS and detection can only escalate.
- [ ] Observer frame limits are rolling backlog limits, sequence never wraps,
  source links statically and binary inode/hash is ephemeral/revalidated.
- [ ] Process/effect alphabets are 22/24 with 5,399,043/8,308,825 traces; native
  EFSM uses its separate exhaustive matrix and bounded causal traces.
- [ ] R43 uses exact isolated bootstrap/import/TCB/FD/direct-exec/libproc rules;
  self-expiry is containment only.
- [ ] Exact maps contain 351 task-local plus 45 normative plus S3C4_01; ranges
  are 31/45/8/157/110 and every method/mutant is unique.
- [ ] Policies total 364 natural, 26 synthetic-gate and seven characterization;
  no preserved behavior or real final-tree condition claims a natural RED.
- [ ] Manifest kinds are runtime/source/synthetic, expected suites/failures are
  pre-frozen, and every owning suite equals the full independent projection.
- [ ] AST closure includes implicit semantic dependencies and rejects dynamic
  escape; expected SHA locations are normalized to exactly 64 ASCII zeroes.
- [ ] Embedded gate has one sentinel pair/fence, compiles under isolated Python,
  runs its three negative self-tests and never executes project code.
- [ ] First reviewers hash Git blobs and gate source externally before any
  candidate gate execution; receipts/packages cannot be mixed.
- [ ] Every Git identity disables replacements/config inheritance and uses
  explicit validated Git directory plus full commit.
- [ ] Precommit tests run from an unreferenced temporary commit worktree; commit
  occurs without restaging; full suites and every mutant rerun from a fresh
  exact `S3_FINAL` worktree before final packaging/review.
- [ ] Final status after each implementation commit remains only the known
  unstaged `primer.md`; no package, worktree or source-copy residue remains.
- [ ] Three blind documentation reviews are still required before Task 1, and
  three fresh blind implementation reviews are required after final reruns.

## Post-S3 S4 separation

Only after accepted `S3_FINAL` may a separate documentation-only, independently
reviewed commit update the three existing S4 design/plan documents. It remains
outside `IMPLEMENTATION_BASE..S3_FINAL` and precedes any S4 code.
