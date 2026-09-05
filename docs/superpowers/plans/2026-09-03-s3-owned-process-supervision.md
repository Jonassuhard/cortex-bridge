# S3 Owned-Process Supervision Implementation Plan

**Status:** Revision 11 review candidate; implementation remains frozen until these exact specification and plan bytes receive three fresh, mutually blind, read-only reviews with `P0=0`, `P1=0`, `P2=0` and `PASS`
three fresh, mutually blind, read-only reviews with `P0=0`, `P1=0`, `P2=0` and
`PASS`
**Revision-7 parent:** `8e0cbd6516415ee378a5ecb9f42a0c92c60e244c`

> **For agentic workers:** execute tasks sequentially. Preserve every gate,
> freeze every declared byte identity before the next phase and stop on the
> first failed receipt. No review result from another reviewer is visible to a
> reviewer performing an independent review.

**Goal:** implement persistent broker-owned native supervision, a byte-exact
broker/worker protocol, exclusive child-free mutation authority, exact
artifact/observer closure and reproducible 510-case evidence without granting
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
- Implementation starts only after these exact Revision 11 document bytes pass
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

## Revision 11 documentation completion gate

This authoring phase changes only the two documents. It executes no project
code, test, build, helper or live effect. Before the docs-only commit, record
the pre-existing primer diff hash and run only static documentary checks:

~~~bash
set -euo pipefail
DOC_PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
test "$(git rev-parse HEAD)" = 8e0cbd6516415ee378a5ecb9f42a0c92c60e244c
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
starts with a close. It requires exact Revision 11 parent/status, one gate source
block, unique maps and ranges, 510 IDs/mutants/closures/manifests, policy counts
364/26/7, source/runtime/synthetic activation sets, all protocol/resource
constants, the public code table, 22/24 model alphabets with 5,399,043/8,308,825
traces and the 14-state/19-constructor/145-member/2,030-pair/2,034-assertion
EFSM. It rejects unresolved authoring markers and every superseded literal or
model named by the Revision 11 correction contract unless a test marks the value
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
        b"Revision 11",
        b"8e0cbd6516415ee378a5ecb9f42a0c92c60e244c",
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
| seven-command invocation | 287 frames / 238 chunks / 14,764,324 bytes |
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
  the one AttestedPrivateMountPath mount_path detach plus absence query; no caller device exists.
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
  suites and 510 mutants from those bytes. Git gates receive repository and
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
-> rerun complete suites and all 510 mutants
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
map has 461 unique keys/methods and exact owner ranges 32/49/10/209/161. With
45 normative keys and `S3C4_01`, `ALL_TEST_IDS` and `ALL_MUTANTS` each have
510 unique entries.

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
assert len(ALL_TEST_IDS) == len(ALL_MUTANTS) == 510
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

The 228 Revision 11 additions decompose exactly into 120 runtime, 88 source and
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

`ORACLE_CLOSURE_SHA256` is a literal 510-entry map. `ORACLE_CLOSURE` and
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
all task-local       = 31 + 45 + 8 + 157 + 110 = 461
ALL_TEST_IDS         = 45 normative + 461 task-local + 1 S3C4_01 = 510
MUTANT_MANIFEST      = 510
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

## Revision 11 finding closure

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

- [ ] Status is Revision 11, parent is exactly
  `8e0cbd6516415ee378a5ecb9f42a0c92c60e244c`, and neither document claims
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
- [ ] Exact maps contain 461 task-local plus 45 normative plus S3C4_01; ranges
  are 32/49/10/209/161 and every method/mutant is unique.
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


## Complete Revision 11 ID Allocation Map (`R8_ID_MAP_V1`)

Complete `R8_ID_MAP_V1`

```text
id	owner	policy	activation	target	method	mutant	oracle_id	assertion_label	requirement_refs	status
R01	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_unresolved_attach_text_cannot_issue_compensation	accept_unresolved_attach_output	ORACLE_R01	MUTANT_R01_ACCEPT_UNRESOLVED_ATTACH_OUTPUT	BASELINE:R01	reused
R02	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_present_original_group_blocks_attach_compensation	ignore_present_original_group	ORACLE_R02	MUTANT_R02_IGNORE_PRESENT_ORIGINAL_GROUP	BASELINE:R02	reused
R03	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_truncated_attach_output_cannot_issue_receipt	accept_truncated_attach_output	ORACLE_R03	MUTANT_R03_ACCEPT_TRUNCATED_ATTACH_OUTPUT	BASELINE:R03	reused
R04	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_capped_attach_output_cannot_issue_receipt	accept_capped_attach_output	ORACLE_R04	MUTANT_R04_ACCEPT_CAPPED_ATTACH_OUTPUT	BASELINE:R04	reused
R05	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_settled_attach_allows_one_bound_detach_and_absence	skip_bound_absence_query	ORACLE_R05	MUTANT_R05_SKIP_BOUND_ABSENCE_QUERY	BASELINE:R05	reused
R06	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_held_pipe_exit_uses_exited_anchor_without_zombie_getsid	call_getsid_after_exact_exit	ORACLE_R06	MUTANT_R06_CALL_GETSID_AFTER_EXACT_EXIT	BASELINE:R06	reused
R07	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_post_reap_token_allows_only_one_group_absence_observation	issue_term_from_post_reap_token	ORACLE_R07	MUTANT_R07_ISSUE_TERM_FROM_POST_REAP_TOKEN	BASELINE:R07	reused
R08	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_changed_or_incomplete_identity_blocks_resume_input_and_signal	resume_changed_identity	ORACLE_R08	MUTANT_R08_RESUME_CHANGED_IDENTITY	BASELINE:R08	reused
R09	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_waitid_matrix_issues_only_exact_exited_anchor	accept_wrong_waitid_pid	ORACLE_R09	MUTANT_R09_ACCEPT_WRONG_WAITID_PID	BASELINE:R09	reused
R10	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_reap_echild_cannot_issue_native_settlement	treat_reap_echild_as_success	ORACLE_R10	MUTANT_R10_TREAT_REAP_ECHILD_AS_SUCCESS	BASELINE:R10	reused
R11	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_insufficient_command_and_finalization_fit_spawns_nothing	spawn_without_finalization_fit	ORACLE_R11	MUTANT_R11_SPAWN_WITHOUT_FINALIZATION_FIT	BASELINE:R11	reused
R12	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_single_helper_detach_cutoff_equality_and_next_nanosecond	admit_detach_one_nanosecond_late	ORACLE_R12	MUTANT_R12_ADMIT_DETACH_ONE_NANOSECOND_LATE	BASELINE:R12	reused
R13	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_single_helper_absence_stops_at_twenty_six_seconds	admit_absence_one_nanosecond_late	ORACLE_R13	MUTANT_R13_ADMIT_ABSENCE_ONE_NANOSECOND_LATE	BASELINE:R13	reused
R14	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_no_stage_can_reset_original_deadline	recompute_compensation_deadline	ORACLE_R14	MUTANT_R14_RECOMPUTE_COMPENSATION_DEADLINE	BASELINE:R14	reused
R15	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorityTests.test_terminal_preobservation_blocks_every_ordinary_method	mint_ordinary_after_terminal	ORACLE_R15	MUTANT_R15_MINT_ORDINARY_AFTER_TERMINAL	BASELINE:R15	reused
R16	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorityTests.test_observer_precedes_compile_and_terminal_compile_mints_no_live_capability	compile_helper_before_observer_baseline	ORACLE_R16	MUTANT_R16_COMPILE_HELPER_BEFORE_OBSERVER_BASELINE	BASELINE:R16	reused
R17	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorityTests.test_caller_operands_cannot_construct_live_work	accept_caller_operation	ORACLE_R17	MUTANT_R17_ACCEPT_CALLER_OPERATION	BASELINE:R17	reused
R18	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_replayed_mounted_cursor_spawns_no_second_continuation	accept_replayed_mounted_cursor	ORACLE_R18	MUTANT_R18_ACCEPT_REPLAYED_MOUNTED_CURSOR	BASELINE:R18	reused
R19	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_each_indexed_mount_issues_one_detach_absence_transition	issue_second_cycle_detach_absence	ORACLE_R19	MUTANT_R19_ISSUE_SECOND_CYCLE_DETACH_ABSENCE	BASELINE:R19	reused
R20	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_detach_and_absence_use_one_current_mapping_helper	split_detach_and_absence_helpers	ORACLE_R20	MUTANT_R20_SPLIT_DETACH_AND_ABSENCE_HELPERS	BASELINE:R20	reused
R21	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_every_normal_and_terminal_branch_mints_one_disposition_then_close	close_without_terminal_disposition_receipt	ORACLE_R21	MUTANT_R21_CLOSE_WITHOUT_TERMINAL_DISPOSITION_RECEIPT	BASELINE:R21	reused
R22	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_ambiguous_current_mapping_preserves_without_followup_effect	detach_ambiguous_current_mapping	ORACLE_R22	MUTANT_R22_DETACH_AMBIGUOUS_CURRENT_MAPPING	BASELINE:R22	reused
R23	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_terminal_after_keychain_delete_performs_no_later_keychain_effect	requery_keychain_after_terminal_delete	ORACLE_R23	MUTANT_R23_REQUERY_KEYCHAIN_AFTER_TERMINAL_DELETE	BASELINE:R23	reused
R24	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_securityagent_verdict_precedes_observer_and_cleanup_errors	prefer_cleanup_error_verdict	ORACLE_R24	MUTANT_R24_PREFER_CLEANUP_ERROR_VERDICT	BASELINE:R24	reused
R25	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_create_and_indexed_mount_evidence_advance_only_current_cursor	select_historical_mount_receipt	ORACLE_R25	MUTANT_R25_SELECT_HISTORICAL_MOUNT_RECEIPT	BASELINE:R25	reused
R26	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_related_partial_and_foreign_uid_bridge_latch_uncertainty	ignore_related_partial	ORACLE_R26	MUTANT_R26_IGNORE_RELATED_PARTIAL	BASELINE:R26	reused
R27	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_partial_bridge_never_authorizes_grandchild_signal	bridge_partial_to_grandchild	ORACLE_R27	MUTANT_R27_BRIDGE_PARTIAL_TO_GRANDCHILD	BASELINE:R27	reused
R28	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_zero_record_live_reread_remains_partial	treat_live_reread_as_vanished	ORACLE_R28	MUTANT_R28_TREAT_LIVE_REREAD_AS_VANISHED	BASELINE:R28	reused
R29	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_zero_record_esrch_reread_is_vanished	reject_esrch_vanished	ORACLE_R29	MUTANT_R29_REJECT_ESRCH_VANISHED	BASELINE:R29	reused
R30	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_late_child_is_never_adopted_or_signalled	adopt_late_child	ORACLE_R30	MUTANT_R30_ADOPT_LATE_CHILD	BASELINE:R30	reused
R31	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_reused_parent_birth_is_never_adopted_or_signalled	accept_reused_parent_birth	ORACLE_R31	MUTANT_R31_ACCEPT_REUSED_PARENT_BIRTH	BASELINE:R31	reused
R32	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessModelTests.test_tracked_uid_sid_or_group_change_expires_authority	signal_after_sid_change	ORACLE_R32	MUTANT_R32_SIGNAL_AFTER_SID_CHANGE	BASELINE:R32	reused
R33	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_term_to_kill_exited_anchor_revalidation_matrix	kill_without_exited_revalidation	ORACLE_R33	MUTANT_R33_KILL_WITHOUT_EXITED_REVALIDATION	BASELINE:R33	reused
R34	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_kill_attempt_forbids_later_group_signal	allow_term_after_kill	ORACLE_R34	MUTANT_R34_ALLOW_TERM_AFTER_KILL	BASELINE:R34	reused
R35	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_obligation_survives_nonexact_reap_and_validate_race	drop_suspended_cleanup_obligation_before_reap	ORACLE_R35	MUTANT_R35_DROP_SUSPENDED_CLEANUP_OBLIGATION_BEFORE_REAP	BASELINE:R35	reused
R36	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_total_helper_tuple_and_independent_close_failure_matrix	accept_incomplete_helper_tuple	ORACLE_R36	MUTANT_R36_ACCEPT_INCOMPLETE_HELPER_TUPLE	BASELINE:R36	reused
R37	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_valid_output_without_native_settlement_has_no_authority	mint_permit_without_native_proof	ORACLE_R37	MUTANT_R37_MINT_PERMIT_WITHOUT_NATIVE_PROOF	BASELINE:R37	reused
R38	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_shared_clock_and_jump_matrix_stop_at_original_deadline	use_python_monotonic_ns_for_shared_deadline	ORACLE_R38	MUTANT_R38_USE_PYTHON_MONOTONIC_NS_FOR_SHARED_DEADLINE	BASELINE:R38	reused
R39	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSecretTests.test_application_owned_secret_lifetime_and_erasure_matrix	leave_wire_live_at_outcome	ORACLE_R39	MUTANT_R39_LEAVE_WIRE_LIVE_AT_OUTCOME	BASELINE:R39	reused
R40	5	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_active_cancel_requires_0x12_then_0x13_eof_and_exact_helper_reap	omit_settlement_frame_before_cancel_ack	ORACLE_R40	MUTANT_R40_OMIT_SETTLEMENT_FRAME_BEFORE_CANCEL_ACK	BASELINE:R40	reused
R41	5	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_production_testing_routes_and_pre_post_exec_descriptor_inventories	accept_invalid_fixture_fd	ORACLE_R41	MUTANT_R41_ACCEPT_INVALID_FIXTURE_FD	BASELINE:R41	reused
R42	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_dynamic_python311_python314_inventory_and_order_match	omit_dynamic_test_class	ORACLE_R42	MUTANT_R42_OMIT_DYNAMIC_TEST_CLASS	BASELINE:R42	reused
R43	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_report_go_exec_libproc_probes_pass_twenty_fresh_runs_each	start_probe_cleanup_after_reserved_window	ORACLE_R43	MUTANT_R43_START_PROBE_CLEANUP_AFTER_RESERVED_WINDOW	BASELINE:R43	reused
R44	1	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainLegacyRemovalTests.test_legacy_routes_handlers_and_tests_are_absent_before_default_suite	retain_legacy_process_route	ORACLE_R44	MUTANT_R44_RETAIN_LEGACY_PROCESS_ROUTE	BASELINE:R44	reused
R45	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_each_flag_and_authorization_near_miss_constructs_zero_live_objects	normalize_authorization_flag	ORACLE_R45	MUTANT_R45_NORMALIZE_AUTHORIZATION_FLAG	BASELINE:R45	reused
S3T1_01	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_explorer_stamps_transition_indices_outside_reducer	stamp_transition_index_inside_reducer	ORACLE_S3T1_01	MUTANT_S3T1_01_STAMP_TRANSITION_INDEX_INSIDE_REDUCER	BASELINE:S3T1_01	reused
S3T1_02	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_reference_machines_match_full_actions_and_final_state	omit_effect_disposition_action	ORACLE_S3T1_02	MUTANT_S3T1_02_OMIT_EFFECT_DISPOSITION_ACTION	BASELINE:S3T1_02	reused
S3T1_03	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_positive_signal_settlement_and_disposition_counters_are_nonzero	suppress_valid_signal_action	ORACLE_S3T1_03	MUTANT_S3T1_03_SUPPRESS_VALID_SIGNAL_ACTION	BASELINE:S3T1_03	reused
S3T1_04	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_long_traces_cover_complete_disposition_and_replays	reject_valid_absence_to_quarantine_transition	ORACLE_S3T1_04	MUTANT_S3T1_04_REJECT_VALID_ABSENCE_TO_QUARANTINE_TRANSITION	BASELINE:S3T1_04	reused
S3T1_05	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLegacyRemovalTests.test_legacy_gate_runs_before_default_selection	select_default_before_legacy_gate	ORACLE_S3T1_05	MUTANT_S3T1_05_SELECT_DEFAULT_BEFORE_LEGACY_GATE	BASELINE:S3T1_05	reused
S3T1_06	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_artifact_cursor_reference_requires_two_complete_cycles	skip_second_artifact_cycle	ORACLE_S3T1_06	MUTANT_S3T1_06_SKIP_SECOND_ARTIFACT_CYCLE	BASELINE:S3T1_06	reused
S3T1_07	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_unresolved_effect_ledger_still_mints_one_disposition_and_close	drop_unresolved_ledger_before_close	ORACLE_S3T1_07	MUTANT_S3T1_07_DROP_UNRESOLVED_LEDGER_BEFORE_CLOSE	BASELINE:S3T1_07	reused
S3T1_08	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_state_domain_is_exact	omit_channel_lost_cleanup_state	ORACLE_S3T1_08	MUTANT_S3T1_08_OMIT_CHANNEL_LOST_CLEANUP_STATE	BASELINE:S3T1_08	reused
S3T1_09	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_constructor_domain_is_exact_and_has_no_abort	retain_suspended_abort_constructor	ORACLE_S3T1_09	MUTANT_S3T1_09_RETAIN_SUSPENDED_ABORT_CONSTRUCTOR	BASELINE:S3T1_09	reused
S3T1_10	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_member_domains_are_exact	change_waitability_member_domain	ORACLE_S3T1_10	MUTANT_S3T1_10_CHANGE_WAITABILITY_MEMBER_DOMAIN	BASELINE:S3T1_10,R7-001,R7-003	modified
S3T1_11	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_counts_are_145_2030_and_2034	miscount_signal_intents	ORACLE_S3T1_11	MUTANT_S3T1_11_MISCOUNT_SIGNAL_INTENTS	BASELINE:S3T1_11	reused
S3T1_12	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_spawn_factory_is_total	spawn_into_existing_efsm	ORACLE_S3T1_12	MUTANT_S3T1_12_SPAWN_INTO_EXISTING_EFSM	BASELINE:S3T1_12	reused
S3T1_13	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_active_frame_transition_is_total	advance_after_partial_active_frame	ORACLE_S3T1_13	MUTANT_S3T1_13_ADVANCE_AFTER_PARTIAL_ACTIVE_FRAME	BASELINE:S3T1_13	reused
S3T1_14	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_identity_transition_is_total	treat_changed_identity_as_exact	ORACLE_S3T1_14	MUTANT_S3T1_14_TREAT_CHANGED_IDENTITY_AS_EXACT	BASELINE:S3T1_14	reused
S3T1_15	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_cancel_and_resume_transitions_are_total	advance_nonconfirmed_resume_to_running	ORACLE_S3T1_15	MUTANT_S3T1_15_ADVANCE_NONCONFIRMED_RESUME_TO_RUNNING	BASELINE:S3T1_15	reused
S3T1_16	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_exit_transition_is_total	accept_wrong_exit_pid	ORACLE_S3T1_16	MUTANT_S3T1_16_ACCEPT_WRONG_EXIT_PID	BASELINE:S3T1_16	reused
S3T1_17	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_waitability_transition_is_total	treat_eintr_as_exact_waitability	ORACLE_S3T1_17	MUTANT_S3T1_17_TREAT_EINTR_AS_EXACT_WAITABILITY	BASELINE:S3T1_17	reused
S3T1_18	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_signal_permit_mint_is_total	mint_unbound_signal_permit	ORACLE_S3T1_18	MUTANT_S3T1_18_MINT_UNBOUND_SIGNAL_PERMIT	BASELINE:S3T1_18	reused
S3T1_19	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_signal_consumes_exact_permit	signal_without_consuming_permit	ORACLE_S3T1_19	MUTANT_S3T1_19_SIGNAL_WITHOUT_CONSUMING_PERMIT	BASELINE:S3T1_19	reused
S3T1_20	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_wait_transition_is_total	treat_still_running_as_reaped_wait	ORACLE_S3T1_20	MUTANT_S3T1_20_TREAT_STILL_RUNNING_AS_REAPED_WAIT	BASELINE:S3T1_20	reused
S3T1_21	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_reap_transition_is_total	treat_reap_echild_as_exact	ORACLE_S3T1_21	MUTANT_S3T1_21_TREAT_REAP_ECHILD_AS_EXACT	BASELINE:S3T1_21	reused
S3T1_22	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_group_transition_is_total	accept_present_group_as_absent	ORACLE_S3T1_22	MUTANT_S3T1_22_ACCEPT_PRESENT_GROUP_AS_ABSENT	BASELINE:S3T1_22	reused
S3T1_23	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_close_transition_is_total	settle_partial_native_close_set	ORACLE_S3T1_23	MUTANT_S3T1_23_SETTLE_PARTIAL_NATIVE_CLOSE_SET	BASELINE:S3T1_23	reused
S3T1_24	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_worker_loss_transition_is_total	retire_on_worker_channel_loss	ORACLE_S3T1_24	MUTANT_S3T1_24_RETIRE_ON_WORKER_CHANNEL_LOSS	BASELINE:S3T1_24,R7-001,R7-003	modified
S3T1_25	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_admin_loss_transition_is_total	erase_safety_facts_on_admin_loss	ORACLE_S3T1_25	MUTANT_S3T1_25_ERASE_SAFETY_FACTS_ON_ADMIN_LOSS	BASELINE:S3T1_25,R7-001,R7-003	modified
S3T1_26	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_worker_final_write_and_ack_transitions_are_distinct_and_total	retire_worker_final_on_write_before_ack	ORACLE_S3T1_26	MUTANT_S3T1_26_RETIRE_WORKER_FINAL_ON_WRITE_BEFORE_ACK	BASELINE:S3T1_26	reused
S3T1_27	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_orphan_publication_transition_is_total	retire_on_partial_orphan_publication	ORACLE_S3T1_27	MUTANT_S3T1_27_RETIRE_ON_PARTIAL_ORPHAN_PUBLICATION	BASELINE:S3T1_27	reused
S3T1_28	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_orphan_ack_transition_is_total	retire_before_exact_orphan_ack	ORACLE_S3T1_28	MUTANT_S3T1_28_RETIRE_BEFORE_EXACT_ORPHAN_ACK	BASELINE:S3T1_28	reused
S3T1_29	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_strong_equality_covers_every_opaque_register_including_worker_final_ack_pending	ignore_worker_final_ack_pending_in_strong_equality	ORACLE_S3T1_29	MUTANT_S3T1_29_IGNORE_WORKER_FINAL_ACK_PENDING_IN_STRONG_EQUALITY	BASELINE:S3T1_29	reused
S3T1_30	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_full_candidate_reference_matrix_matches	emit_sentinel_syscall_on_rejected_pair	ORACLE_S3T1_30	MUTANT_S3T1_30_EMIT_SENTINEL_SYSCALL_ON_REJECTED_PAIR	BASELINE:S3T1_30,R7-001	modified
S3T1_31	1	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_native_efsm_causal_action_vector_traces_reach_exact_worker_final_ack	truncate_worker_final_trace_before_exact_ack	ORACLE_S3T1_31	MUTANT_S3T1_31_TRUNCATE_WORKER_FINAL_TRACE_BEFORE_EXACT_ACK	BASELINE:S3T1_31	reused
S3T2_01	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_anchor_tokens_reject_foreign_registry_identity	accept_foreign_anchor_registry	ORACLE_S3T2_01	MUTANT_S3T2_01_ACCEPT_FOREIGN_ANCHOR_REGISTRY	BASELINE:S3T2_01	reused
S3T2_02	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_supervisor_and_issuance_registries_are_private_final_classes	expose_nonfinal_supervisor	ORACLE_S3T2_02	MUTANT_S3T2_02_EXPOSE_NONFINAL_SUPERVISOR	BASELINE:S3T2_02	reused
S3T2_03	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_native_settlement_excludes_control_descriptor	include_control_in_native_proof	ORACLE_S3T2_03	MUTANT_S3T2_03_INCLUDE_CONTROL_IN_NATIVE_PROOF	BASELINE:S3T2_03	reused
S3T2_04	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_total_dfa_rejects_duplicate_terminal_frame	accept_duplicate_terminal_frame	ORACLE_S3T2_04	MUTANT_S3T2_04_ACCEPT_DUPLICATE_TERMINAL_FRAME	BASELINE:S3T2_04	reused
S3T2_05	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_pre_request_deadline_rejects_more_than_seventy_seconds	accept_deadline_over_seventy_seconds	ORACLE_S3T2_05	MUTANT_S3T2_05_ACCEPT_DEADLINE_OVER_SEVENTY_SECONDS	BASELINE:S3T2_05	reused
S3T2_06	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSecretTests.test_mutable_keychain_staging_is_erased	retain_mutable_keychain_staging	ORACLE_S3T2_06	MUTANT_S3T2_06_RETAIN_MUTABLE_KEYCHAIN_STAGING	BASELINE:S3T2_06	reused
S3T2_07	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSecretTests.test_wire_is_erased_before_settlement_frame	emit_settlement_before_wire_erasure	ORACLE_S3T2_07	MUTANT_S3T2_07_EMIT_SETTLEMENT_BEFORE_WIRE_ERASURE	BASELINE:S3T2_07	reused
S3T2_08	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_normal_exit_kind_keeps_no_child_and_protocol_failure_distinct	conflate_normal_exit_kinds	ORACLE_S3T2_08	MUTANT_S3T2_08_CONFLATE_NORMAL_EXIT_KINDS	BASELINE:S3T2_08	reused
S3T2_09	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_anchor_retains_native_obligation_until_exact_reap	consume_suspended_cleanup_on_first_attempt	ORACLE_S3T2_09	MUTANT_S3T2_09_CONSUME_SUSPENDED_CLEANUP_ON_FIRST_ATTEMPT	BASELINE:S3T2_09	reused
S3T2_10	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_one_lifecycle_executor_linearizes_cancel_spawn_and_first_write	add_competing_lifecycle_reader	ORACLE_S3T2_10	MUTANT_S3T2_10_ADD_COMPETING_LIFECYCLE_READER	BASELINE:S3T2_10	reused
S3T2_11	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_spawn_result_matrix_inserts_obligation_only_for_spawned	treat_spawn_failure_as_active_obligation	ORACLE_S3T2_11	MUTANT_S3T2_11_TREAT_SPAWN_FAILURE_AS_ACTIVE_OBLIGATION	BASELINE:S3T2_11	reused
S3T2_12	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_control_closes_only_after_final_normal_or_terminal_transition	close_control_after_intermediate_settlement	ORACLE_S3T2_12	MUTANT_S3T2_12_CLOSE_CONTROL_AFTER_INTERMEDIATE_SETTLEMENT	BASELINE:S3T2_12	reused
S3T2_13	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_validated_suspended_resume_result_and_cancel_matrix	advance_running_before_resume_confirmation	ORACLE_S3T2_13	MUTANT_S3T2_13_ADVANCE_RUNNING_BEFORE_RESUME_CONFIRMATION	BASELINE:S3T2_13	reused
S3T2_14	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_failed_identity_validation_consumes_original_anchor	retain_failed_validation_anchor	ORACLE_S3T2_14	MUTANT_S3T2_14_RETAIN_FAILED_VALIDATION_ANCHOR	BASELINE:S3T2_14	reused
S3T2_15	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_generation_overflow_closes_issuance_without_wrap	wrap_issuance_generation	ORACLE_S3T2_15	MUTANT_S3T2_15_WRAP_ISSUANCE_GENERATION	BASELINE:S3T2_15	reused
S3T2_16	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_normal_exit_requires_complete_or_prefix_trace_proof	accept_count_only_exit_proof	ORACLE_S3T2_16	MUTANT_S3T2_16_ACCEPT_COUNT_ONLY_EXIT_PROOF	BASELINE:S3T2_16	reused
S3T2_17	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_ok_response_values_include_exact_mount_item_count	omit_mount_item_count	ORACLE_S3T2_17	MUTANT_S3T2_17_OMIT_MOUNT_ITEM_COUNT	BASELINE:S3T2_17	reused
S3T2_18	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_non_ok_response_values_are_total_and_partial_free	retain_partial_values_in_error_response	ORACLE_S3T2_18	MUTANT_S3T2_18_RETAIN_PARTIAL_VALUES_IN_ERROR_RESPONSE	BASELINE:S3T2_18	reused
S3T2_19	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_native_child_lifecycle_efsm_has_exact_fourteen_states	retain_stale_native_efsm_state_set	ORACLE_S3T2_19	MUTANT_S3T2_19_RETAIN_STALE_NATIVE_EFSM_STATE_SET	BASELINE:S3T2_19	reused
S3T2_20	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_only_broker_reaches_native_process_primitives	allow_worker_native_process_primitive	ORACLE_S3T2_20	MUTANT_S3T2_20_ALLOW_WORKER_NATIVE_PROCESS_PRIMITIVE	BASELINE:S3T2_20	reused
S3T2_21	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_worker_loss_preserves_broker_native_obligation	retire_native_obligation_on_worker_channel_loss	ORACLE_S3T2_21	MUTANT_S3T2_21_RETIRE_NATIVE_OBLIGATION_ON_WORKER_CHANNEL_LOSS	BASELINE:S3T2_21,R7-003	modified
S3T2_22	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_wire_frames_mint_only_local_registry_receipts	deserialize_wire_object_as_broker_receipt	ORACLE_S3T2_22	MUTANT_S3T2_22_DESERIALIZE_WIRE_OBJECT_AS_BROKER_RECEIPT	BASELINE:S3T2_22	reused
S3T2_23	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_signal_permit_binds_registry_generation_target_signal_sequence_and_deadline	omit_signal_observation_sequence_binding	ORACLE_S3T2_23	MUTANT_S3T2_23_OMIT_SIGNAL_OBSERVATION_SEQUENCE_BINDING	BASELINE:S3T2_23	reused
S3T2_24	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_eintr_never_mints_signal_permit_and_only_reobserves	mint_signal_permit_after_eintr	ORACLE_S3T2_24	MUTANT_S3T2_24_MINT_SIGNAL_PERMIT_AFTER_EINTR	BASELINE:S3T2_24	reused
S3T2_25	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_waitable_signal_permit_replay_is_rejected	accept_replayed_waitable_signal_permit	ORACLE_S3T2_25	MUTANT_S3T2_25_ACCEPT_REPLAYED_WAITABLE_SIGNAL_PERMIT	BASELINE:S3T2_25	reused
S3T2_26	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_waitable_signal_permit_target_or_signal_substitution_is_rejected	accept_substituted_signal_permit_target	ORACLE_S3T2_26	MUTANT_S3T2_26_ACCEPT_SUBSTITUTED_SIGNAL_PERMIT_TARGET	BASELINE:S3T2_26	reused
S3T2_27	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_still_running_retains_obligation_but_not_signal_permit	reuse_signal_permit_after_still_running	ORACLE_S3T2_27	MUTANT_S3T2_27_REUSE_SIGNAL_PERMIT_AFTER_STILL_RUNNING	BASELINE:S3T2_27	reused
S3T2_28	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_waitability_or_identity_loss_irrevocably_revokes_signal_authority	retain_signal_authority_after_waitability_loss	ORACLE_S3T2_28	MUTANT_S3T2_28_RETAIN_SIGNAL_AUTHORITY_AFTER_WAITABILITY_LOSS	BASELINE:S3T2_28	reused
S3T2_29	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSupervisorTests.test_all_term_and_kill_decisions_precede_reap	reap_before_term_kill_decision	ORACLE_S3T2_29	MUTANT_S3T2_29_REAP_BEFORE_TERM_KILL_DECISION	BASELINE:S3T2_29	reused
S3T2_30	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_free_lease_refuses_new_native_admission	admit_native_child_while_child_free_lease_held	ORACLE_S3T2_30	MUTANT_S3T2_30_ADMIT_NATIVE_CHILD_WHILE_CHILD_FREE_LEASE_HELD	BASELINE:S3T2_30	reused
S3T2_31	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_no_active_child_proof_requires_exclusive_child_free_lease	mint_no_active_child_from_idle_snapshot	ORACLE_S3T2_31	MUTANT_S3T2_31_MINT_NO_ACTIVE_CHILD_FROM_IDLE_SNAPSHOT	BASELINE:S3T2_31	reused
S3T2_32	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_free_lease_release_worker_eof_and_terminal_paths_are_total	strand_child_free_lease_on_worker_eof	ORACLE_S3T2_32	MUTANT_S3T2_32_STRAND_CHILD_FREE_LEASE_ON_WORKER_EOF	BASELINE:S3T2_32	reused
S3T2_33	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_free_permit_rejects_cross_generation_replay	accept_cross_generation_child_free_permit	ORACLE_S3T2_33	MUTANT_S3T2_33_ACCEPT_CROSS_GENERATION_CHILD_FREE_PERMIT	BASELINE:S3T2_33	reused
S3T2_34	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_free_permit_rejects_cross_syscall_substitution	accept_cross_syscall_child_free_permit	ORACLE_S3T2_34	MUTANT_S3T2_34_ACCEPT_CROSS_SYSCALL_CHILD_FREE_PERMIT	BASELINE:S3T2_34	reused
S3T2_35	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_secrandomcopybytes_has_same_turn_terminal_poll	skip_terminal_poll_before_secrandomcopybytes	ORACLE_S3T2_35	MUTANT_S3T2_35_SKIP_TERMINAL_POLL_BEFORE_SECRANDOMCOPYBYTES	BASELINE:S3T2_35	reused
S3T2_36	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_secitemcopymatching_has_same_turn_terminal_poll	skip_terminal_poll_before_secitemcopymatching	ORACLE_S3T2_36	MUTANT_S3T2_36_SKIP_TERMINAL_POLL_BEFORE_SECITEMCOPYMATCHING	BASELINE:S3T2_36	reused
S3T2_37	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_secitemadd_has_same_turn_terminal_poll	skip_terminal_poll_before_secitemadd	ORACLE_S3T2_37	MUTANT_S3T2_37_SKIP_TERMINAL_POLL_BEFORE_SECITEMADD	BASELINE:S3T2_37	reused
S3T2_38	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_secitemdelete_has_same_turn_terminal_poll	skip_terminal_poll_before_secitemdelete	ORACLE_S3T2_38	MUTANT_S3T2_38_SKIP_TERMINAL_POLL_BEFORE_SECITEMDELETE	BASELINE:S3T2_38	reused
S3T2_39	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_post_delete_requery_has_same_turn_terminal_poll	skip_terminal_poll_before_post_delete_requery	ORACLE_S3T2_39	MUTANT_S3T2_39_SKIP_TERMINAL_POLL_BEFORE_POST_DELETE_REQUERY	BASELINE:S3T2_39	reused
S3T2_40	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_free_filesystem_mutation_has_same_turn_terminal_poll	skip_terminal_poll_before_child_free_filesystem_mutation	ORACLE_S3T2_40	MUTANT_S3T2_40_SKIP_TERMINAL_POLL_BEFORE_CHILD_FREE_FILESYSTEM_MUTATION	BASELINE:S3T2_40	reused
S3T2_41	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_zero_child_publication_uses_lease_without_broker_settlement_or_0x12	inject_settlement_frame_into_zero_child_path	ORACLE_S3T2_41	MUTANT_S3T2_41_INJECT_SETTLEMENT_FRAME_INTO_ZERO_CHILD_PATH	BASELINE:S3T2_41	reused
S3T2_42	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_child_bearing_publication_requires_broker_settlement_then_0x12	omit_broker_settlement_before_child_response	ORACLE_S3T2_42	MUTANT_S3T2_42_OMIT_BROKER_SETTLEMENT_BEFORE_CHILD_RESPONSE	BASELINE:S3T2_42	reused
S3T2_43	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_response_bearing_cancel_and_operational_error_use_trace_candidate	publish_operational_error_without_trace_candidate	ORACLE_S3T2_43	MUTANT_S3T2_43_PUBLISH_OPERATIONAL_ERROR_WITHOUT_TRACE_CANDIDATE	BASELINE:S3T2_43	reused
S3T2_44	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_response_free_exit_consumes_no_response_required_proof	emit_response_free_exit_without_no_response_proof	ORACLE_S3T2_44	MUTANT_S3T2_44_EMIT_RESPONSE_FREE_EXIT_WITHOUT_NO_RESPONSE_PROOF	BASELINE:S3T2_44	reused
S3T2_45	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_partial_response_consumes_candidate_into_protocol_abnormal	mint_trace_proof_after_partial_response	ORACLE_S3T2_45	MUTANT_S3T2_45_MINT_TRACE_PROOF_AFTER_PARTIAL_RESPONSE	BASELINE:S3T2_45	reused
S3T3_01	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_command_permit_rejects_foreign_supervisor_registry	accept_foreign_command_registry	ORACLE_S3T3_01	MUTANT_S3T3_01_ACCEPT_FOREIGN_COMMAND_REGISTRY	BASELINE:S3T3_01	reused
S3T3_02	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_absence_query_rejects_wrong_command_context	accept_wrong_absence_context	ORACLE_S3T3_02	MUTANT_S3T3_02_ACCEPT_WRONG_ABSENCE_CONTEXT	BASELINE:S3T3_02	reused
S3T3_03	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_invocation_class_authenticates_exact_origin_hard_delta	accept_detach26_with_wrong_hard_origin_delta	ORACLE_S3T3_03	MUTANT_S3T3_03_ACCEPT_DETACH26_WITH_WRONG_HARD_ORIGIN_DELTA	BASELINE:S3T3_03	reused
S3T3_04	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_ordinary_public_detach_uses_detach26_stages_and_normal_cutoff	route_ordinary_detach_through_workflow70	ORACLE_S3T3_04	MUTANT_S3T3_04_ROUTE_ORDINARY_DETACH_THROUGH_WORKFLOW70	BASELINE:S3T3_04	reused
S3T3_05	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_terminal_public_detach_requires_accepted_plus_72_snapshot_then_plus_98_fit	treat_plus_72_as_earliest_detach_start	ORACLE_S3T3_05	MUTANT_S3T3_05_TREAT_PLUS_72_AS_EARLIEST_DETACH_START	BASELINE:S3T3_05,R7-007	modified
S3T3_06	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_mount_compensation_detach_remains_workflow70_broker_subcommand	launch_compensation_as_detach26_worker	ORACLE_S3T3_06	MUTANT_S3T3_06_LAUNCH_COMPENSATION_AS_DETACH26_WORKER	BASELINE:S3T3_06	reused
S3T3_07	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftDeadlineTests.test_compensation_detach_keeps_workflow_origin_and_cannot_borrow_reserve	resample_compensation_origin	ORACLE_S3T3_07	MUTANT_S3T3_07_RESAMPLE_COMPENSATION_ORIGIN	BASELINE:S3T3_07	reused
S3T3_08	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_every_broker_command_binds_worker_origin_and_cutoff_digest	accept_broker_command_origin_digest_mismatch	ORACLE_S3T3_08	MUTANT_S3T3_08_ACCEPT_BROKER_COMMAND_ORIGIN_DIGEST_MISMATCH	BASELINE:S3T3_08	reused
S3T4_01	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_preparation_is_one_shot_and_accepts_no_caller_paths	accept_caller_compile_path	ORACLE_S3T4_01	MUTANT_S3T4_01_ACCEPT_CALLER_COMPILE_PATH	BASELINE:S3T4_01	reused
S3T4_02	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_terminal_transfer_consumes_only_current_cursor	accept_copied_historical_cursor	ORACLE_S3T4_02	MUTANT_S3T4_02_ACCEPT_COPIED_HISTORICAL_CURSOR	BASELINE:S3T4_02	reused
S3T4_03	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_terminal_interleavings_cover_spawn_registration_and_first_write	release_executor_before_handle_registration	ORACLE_S3T4_03	MUTANT_S3T4_03_RELEASE_EXECUTOR_BEFORE_HANDLE_REGISTRATION	BASELINE:S3T4_03	reused
S3T4_04	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_waitid_waitpid_and_popen_lifecycle_match_after_exact_reap	call_popen_poll_before_waitpid	ORACLE_S3T4_04	MUTANT_S3T4_04_CALL_POPEN_POLL_BEFORE_WAITPID	BASELINE:S3T4_04	reused
S3T4_05	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainRequestTests.test_all_ten_values_come_from_registered_context	accept_caller_request_path	ORACLE_S3T4_05	MUTANT_S3T4_05_ACCEPT_CALLER_REQUEST_PATH	BASELINE:S3T4_05	reused
S3T4_06	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_move_uses_descriptor_relative_renameatx_exclusive_only	use_nonexclusive_descriptor_move	ORACLE_S3T4_06	MUTANT_S3T4_06_USE_NONEXCLUSIVE_DESCRIPTOR_MOVE	BASELINE:S3T4_06	reused
S3T4_07	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_integration_flag_aliases_are_rejected_without_normalization	accept_integration_flag_alias	ORACLE_S3T4_07	MUTANT_S3T4_07_ACCEPT_INTEGRATION_FLAG_ALIAS	BASELINE:S3T4_07	reused
S3T4_08	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_allow_effects_flag_aliases_are_rejected_without_normalization	accept_allow_effects_flag_alias	ORACLE_S3T4_08	MUTANT_S3T4_08_ACCEPT_ALLOW_EFFECTS_FLAG_ALIAS	BASELINE:S3T4_08	reused
S3T4_09	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_cleanup_approved_flag_aliases_are_rejected_without_normalization	accept_cleanup_approved_flag_alias	ORACLE_S3T4_09	MUTANT_S3T4_09_ACCEPT_CLEANUP_APPROVED_FLAG_ALIAS	BASELINE:S3T4_09	reused
S3T4_10	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_authorization_key_aliases_are_rejected	accept_authorization_key_alias	ORACLE_S3T4_10	MUTANT_S3T4_10_ACCEPT_AUTHORIZATION_KEY_ALIAS	BASELINE:S3T4_10	reused
S3T4_11	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_authorization_value_near_misses_are_rejected_without_normalization	normalize_authorization_value	ORACLE_S3T4_11	MUTANT_S3T4_11_NORMALIZE_AUTHORIZATION_VALUE	BASELINE:S3T4_11	reused
S3T4_12	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_adapter_matches_task1_lineage_reference_for_r26_to_r32	continue_python_adapter_after_lineage_uncertainty	ORACLE_S3T4_12	MUTANT_S3T4_12_CONTINUE_PYTHON_ADAPTER_AFTER_LINEAGE_UNCERTAINTY	BASELINE:S3T4_12	reused
S3T4_13	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_post_latch_keychain_result_cannot_authorize_success	accept_post_latch_keychain_success	ORACLE_S3T4_13	MUTANT_S3T4_13_ACCEPT_POST_LATCH_KEYCHAIN_SUCCESS	BASELINE:S3T4_13	reused
S3T4_14	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_exact_reviewed_observer_source_typechecks_links_and_artifacts_are_deleted	accept_observer_without_linked_binary	ORACLE_S3T4_14	MUTANT_S3T4_14_ACCEPT_OBSERVER_WITHOUT_LINKED_BINARY	BASELINE:S3T4_14	reused
S3T4_15	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_observer_two_baselines_surround_helper_compile_before_live_issuance	skip_second_observer_baseline	ORACLE_S3T4_15	MUTANT_S3T4_15_SKIP_SECOND_OBSERVER_BASELINE	BASELINE:S3T4_15	reused
S3T4_16	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_artifact_cursor_has_exact_states_and_current_transfer_slot	scan_historical_receipts_for_cursor	ORACLE_S3T4_16	MUTANT_S3T4_16_SCAN_HISTORICAL_RECEIPTS_FOR_CURSOR	BASELINE:S3T4_16	reused
S3T4_17	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_two_indexed_mount_verify_detach_absence_cycles_complete	skip_second_mount_cycle	ORACLE_S3T4_17	MUTANT_S3T4_17_SKIP_SECOND_MOUNT_CYCLE	BASELINE:S3T4_17	reused
S3T4_18	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_every_consuming_effect_returns_settled_or_unresolved_ledger	drop_unresolved_effect_outcome	ORACLE_S3T4_18	MUTANT_S3T4_18_DROP_UNRESOLVED_EFFECT_OUTCOME	BASELINE:S3T4_18	reused
S3T4_19	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_terminal_mounted_cursor_starts_exactly_one_continuation_helper	launch_second_continuation_helper	ORACLE_S3T4_19	MUTANT_S3T4_19_LAUNCH_SECOND_CONTINUATION_HELPER	BASELINE:S3T4_19	reused
S3T4_20	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_continuation_uses_exact_twenty_six_second_current_mapping_schedule	reset_continuation_stage_deadline	ORACLE_S3T4_20	MUTANT_S3T4_20_RESET_CONTINUATION_STAGE_DEADLINE	BASELINE:S3T4_20	reused
S3T4_21	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_keychain_absence_is_required_before_image_delete_permit	delete_image_before_keychain_absence	ORACLE_S3T4_21	MUTANT_S3T4_21_DELETE_IMAGE_BEFORE_KEYCHAIN_ABSENCE	BASELINE:S3T4_21	reused
S3T4_22	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_existing_exclusive_target_is_unresolved_and_never_overwritten	overwrite_existing_quarantine_target	ORACLE_S3T4_22	MUTANT_S3T4_22_OVERWRITE_EXISTING_QUARANTINE_TARGET	BASELINE:S3T4_22	reused
S3T4_23	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_every_helper_outcome_matches_complete_tuple	accept_response_without_exact_tuple	ORACLE_S3T4_23	MUTANT_S3T4_23_ACCEPT_RESPONSE_WITHOUT_EXACT_TUPLE	BASELINE:S3T4_23	reused
S3T4_24	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainClockTests.test_twenty_shared_clock_samples_fit_fifty_millisecond_brackets	accept_clock_sample_outside_bracket	ORACLE_S3T4_24	MUTANT_S3T4_24_ACCEPT_CLOCK_SAMPLE_OUTSIDE_BRACKET	BASELINE:S3T4_24	reused
S3T4_25	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_preparation_terminal_consumes_no_artifact_and_closes	skip_preparation_terminal_disposition	ORACLE_S3T4_25	MUTANT_S3T4_25_SKIP_PREPARATION_TERMINAL_DISPOSITION	BASELINE:S3T4_25	reused
S3T4_26	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_no_artifact_cursor_cannot_duplicate_between_live_and_terminal	duplicate_no_artifact_cursor	ORACLE_S3T4_26	MUTANT_S3T4_26_DUPLICATE_NO_ARTIFACT_CURSOR	BASELINE:S3T4_26	reused
S3T4_27	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_persistent_observer_protocol_is_bounded_sequenced_and_private	accept_observer_sequence_gap	ORACLE_S3T4_27	MUTANT_S3T4_27_ACCEPT_OBSERVER_SEQUENCE_GAP	BASELINE:S3T4_27	reused
S3T4_28	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_final_snapshot_eofs_and_exact_reap	skip_exact_observer_reap	ORACLE_S3T4_28	MUTANT_S3T4_28_SKIP_EXACT_OBSERVER_REAP	BASELINE:S3T4_28	reused
S3T4_29	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_late_observer_tick_is_unavailable_not_absence	accept_late_observer_tick	ORACLE_S3T4_29	MUTANT_S3T4_29_ACCEPT_LATE_OBSERVER_TICK	BASELINE:S3T4_29	reused
S3T4_30	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_disposition_cannot_mint_before_observer_exact_reap	mint_disposition_before_observer_reap	ORACLE_S3T4_30	MUTANT_S3T4_30_MINT_DISPOSITION_BEFORE_OBSERVER_REAP	BASELINE:S3T4_30	reused
S3T4_31	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_every_effect_including_disposition_is_registered_in_flight	start_disposition_without_inflight_registration	ORACLE_S3T4_31	MUTANT_S3T4_31_START_DISPOSITION_WITHOUT_INFLIGHT_REGISTRATION	BASELINE:S3T4_31	reused
S3T4_32	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_uncertainty_envelope_is_bounded_and_non_authorizing	treat_uncertainty_envelope_as_authority	ORACLE_S3T4_32	MUTANT_S3T4_32_TREAT_UNCERTAINTY_ENVELOPE_AS_AUTHORITY	BASELINE:S3T4_32	reused
S3T4_33	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_terminal_wins_before_completion_pending_observation	accept_completion_before_pending_terminal	ORACLE_S3T4_33	MUTANT_S3T4_33_ACCEPT_COMPLETION_BEFORE_PENDING_TERMINAL	BASELINE:S3T4_33	reused
S3T4_34	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_observer_and_cancel_win_same_readiness_batch_and_completion_waits_for_watermark	prefer_helper_completion_in_same_readiness_batch	ORACLE_S3T4_34	MUTANT_S3T4_34_PREFER_HELPER_COMPLETION_IN_SAME_READINESS_BATCH	BASELINE:S3T4_34	reused
S3T4_35	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_live_schedule_exact_absolute_cutoffs_and_reserves	reset_live_absolute_cutoff	ORACLE_S3T4_35	MUTANT_S3T4_35_RESET_LIVE_ABSOLUTE_CUTOFF	BASELINE:S3T4_35	reused
S3T4_36	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_original_helper_total_tuple_eofs_and_reap_required_by_plus_71	accept_missing_helper_reap_by_71	ORACLE_S3T4_36	MUTANT_S3T4_36_ACCEPT_MISSING_HELPER_REAP_BY_71	BASELINE:S3T4_36	reused
S3T4_37	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_cleanup_after_plus_106_cannot_restore_pass	restore_pass_after_late_cleanup	ORACLE_S3T4_37	MUTANT_S3T4_37_RESTORE_PASS_AFTER_LATE_CLEANUP	BASELINE:S3T4_37	reused
S3T4_38	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_detached_and_absent_requires_external_empty_mount_directory	accept_nonempty_mount_directory	ORACLE_S3T4_38	MUTANT_S3T4_38_ACCEPT_NONEMPTY_MOUNT_DIRECTORY	BASELINE:S3T4_38	reused
S3T4_39	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_observer_cutoff_equality_and_next_nanosecond_are_total	admit_observer_cutoff_plus_one_nanosecond	ORACLE_S3T4_39	MUTANT_S3T4_39_ADMIT_OBSERVER_CUTOFF_PLUS_ONE_NANOSECOND	BASELINE:S3T4_39	reused
S3T4_40	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_extra_keys_at_every_launch_site	add_home_to_base_exec_environment	ORACLE_S3T4_40	MUTANT_S3T4_40_ADD_HOME_TO_BASE_EXEC_ENVIRONMENT	BASELINE:S3T4_40	reused
S3T4_41	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_missing_keys_at_every_launch_site	omit_lc_all_from_base_exec_environment	ORACLE_S3T4_41	MUTANT_S3T4_41_OMIT_LC_ALL_FROM_BASE_EXEC_ENVIRONMENT	BASELINE:S3T4_41	reused
S3T4_42	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_base_exec_environment_rejects_changed_values_at_every_launch_site	change_base_exec_path_value	ORACLE_S3T4_42	MUTANT_S3T4_42_CHANGE_BASE_EXEC_PATH_VALUE	BASELINE:S3T4_42	reused
S3T4_43	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainPreparationTests.test_every_reservation_binds_environment_profile_and_digest	accept_environment_digest_mismatch	ORACLE_S3T4_43	MUTANT_S3T4_43_ACCEPT_ENVIRONMENT_DIGEST_MISMATCH	BASELINE:S3T4_43	reused
S3T4_44	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_ready_binds_exact_environment_digest	accept_observer_ready_without_environment_digest	ORACLE_S3T4_44	MUTANT_S3T4_44_ACCEPT_OBSERVER_READY_WITHOUT_ENVIRONMENT_DIGEST	BASELINE:S3T4_44	reused
S3T4_45	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_persistent_admin_socket_and_broker_ready_precede_live_issuance	start_worker_before_broker_ready	ORACLE_S3T4_45	MUTANT_S3T4_45_START_WORKER_BEFORE_BROKER_READY	BASELINE:S3T4_45,R7-024	modified
S3T4_46	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_fd_transfer_acks_canonical_context_before_continue	continue_worker_before_transfer_ack	ORACLE_S3T4_46	MUTANT_S3T4_46_CONTINUE_WORKER_BEFORE_TRANSFER_ACK	BASELINE:S3T4_46	reused
S3T4_47	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_scm_rights_extra_fd_is_rejected	accept_extra_scm_rights_fd	ORACLE_S3T4_47	MUTANT_S3T4_47_ACCEPT_EXTRA_SCM_RIGHTS_FD	BASELINE:S3T4_47	reused
S3T4_48	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_scm_rights_absent_fd_is_rejected	accept_absent_scm_rights_fd	ORACLE_S3T4_48	MUTANT_S3T4_48_ACCEPT_ABSENT_SCM_RIGHTS_FD	BASELINE:S3T4_48	reused
S3T4_49	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_scm_rights_double_fd_is_rejected	accept_double_scm_rights_fd	ORACLE_S3T4_49	MUTANT_S3T4_49_ACCEPT_DOUBLE_SCM_RIGHTS_FD	BASELINE:S3T4_49	reused
S3T4_50	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_scm_rights_truncation_and_msg_ctrunc_are_rejected	accept_truncated_scm_rights	ORACLE_S3T4_50	MUTANT_S3T4_50_ACCEPT_TRUNCATED_SCM_RIGHTS	BASELINE:S3T4_50	reused
S3T4_51	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_sender_duplicate_closes_only_after_exact_transfer_ack	retain_scm_rights_sender_duplicate	ORACLE_S3T4_51	MUTANT_S3T4_51_RETAIN_SCM_RIGHTS_SENDER_DUPLICATE	BASELINE:S3T4_51	reused
S3T4_52	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_missing_transfer_ack_is_rejected	accept_missing_transfer_ack	ORACLE_S3T4_52	MUTANT_S3T4_52_ACCEPT_MISSING_TRANSFER_ACK	BASELINE:S3T4_52	reused
S3T4_53	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_inverted_transfer_ack_is_rejected	accept_inverted_transfer_ack	ORACLE_S3T4_53	MUTANT_S3T4_53_ACCEPT_INVERTED_TRANSFER_ACK	BASELINE:S3T4_53	reused
S3T4_54	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_transferred_fd_is_cloexec_before_registry_insertion	insert_transferred_fd_without_cloexec	ORACLE_S3T4_54	MUTANT_S3T4_54_INSERT_TRANSFERRED_FD_WITHOUT_CLOEXEC	BASELINE:S3T4_54	reused
S3T4_55	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_transferred_fd_is_nonblocking_before_registry_insertion	insert_transferred_fd_without_nonblocking	ORACLE_S3T4_55	MUTANT_S3T4_55_INSERT_TRANSFERRED_FD_WITHOUT_NONBLOCKING	BASELINE:S3T4_55	reused
S3T4_56	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_wrong_broker_socket_family_is_rejected	accept_wrong_broker_socket_family	ORACLE_S3T4_56	MUTANT_S3T4_56_ACCEPT_WRONG_BROKER_SOCKET_FAMILY	BASELINE:S3T4_56	reused
S3T4_57	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_spawn_failure_after_transfer_has_total_orphan_ledger	lose_transferred_fd_on_worker_spawn_failure	ORACLE_S3T4_57	MUTANT_S3T4_57_LOSE_TRANSFERRED_FD_ON_WORKER_SPAWN_FAILURE	BASELINE:S3T4_57	reused
S3T4_58	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_repeated_transfer_session_generation_or_digest_is_rejected	accept_repeated_broker_transfer_context	ORACLE_S3T4_58	MUTANT_S3T4_58_ACCEPT_REPEATED_BROKER_TRANSFER_CONTEXT	BASELINE:S3T4_58	reused
S3T4_59	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_broker_worker_fixture_fd_ledgers_and_independent_closes_are_exact	omit_broker_failure_close_ledger_entry	ORACLE_S3T4_59	MUTANT_S3T4_59_OMIT_BROKER_FAILURE_CLOSE_LEDGER_ENTRY	BASELINE:S3T4_59	reused
S3T4_60	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_partial_admin_frame_is_rejected	accept_partial_admin_frame	ORACLE_S3T4_60	MUTANT_S3T4_60_ACCEPT_PARTIAL_ADMIN_FRAME	BASELINE:S3T4_60	reused
S3T4_61	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_admin_frame_cap_plus_one_is_rejected	accept_admin_frame_cap_plus_one	ORACLE_S3T4_61	MUTANT_S3T4_61_ACCEPT_ADMIN_FRAME_CAP_PLUS_ONE	BASELINE:S3T4_61	reused
S3T4_62	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_partial_worker_broker_frame_is_rejected	accept_partial_worker_broker_frame	ORACLE_S3T4_62	MUTANT_S3T4_62_ACCEPT_PARTIAL_WORKER_BROKER_FRAME	BASELINE:S3T4_62	reused
S3T4_63	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_broker_frame_cap_plus_one_is_rejected	accept_worker_broker_frame_cap_plus_one	ORACLE_S3T4_63	MUTANT_S3T4_63_ACCEPT_WORKER_BROKER_FRAME_CAP_PLUS_ONE	BASELINE:S3T4_63	reused
S3T4_64	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_native_stdout_fragmentation_is_complete_and_bounded	drop_native_stdout_fragment	ORACLE_S3T4_64	MUTANT_S3T4_64_DROP_NATIVE_STDOUT_FRAGMENT	BASELINE:S3T4_64	reused
S3T4_65	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_native_stderr_fragmentation_is_complete_and_bounded	drop_native_stderr_fragment	ORACLE_S3T4_65	MUTANT_S3T4_65_DROP_NATIVE_STDERR_FRAGMENT	BASELINE:S3T4_65	reused
S3T4_66	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_json_depth_cap_accepts_legal_equality_and_rejects_plus_one	accept_broker_json_depth_plus_one	ORACLE_S3T4_66	MUTANT_S3T4_66_ACCEPT_BROKER_JSON_DEPTH_PLUS_ONE	BASELINE:S3T4_66	reused
S3T4_67	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_settled_frame_mints_only_receiving_registry_receipt	construct_broker_settled_receipt_from_wire_fields	ORACLE_S3T4_67	MUTANT_S3T4_67_CONSTRUCT_BROKER_SETTLED_RECEIPT_FROM_WIRE_FIELDS	BASELINE:S3T4_67	reused
S3T4_68	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_orphan_frame_mints_only_receiving_registry_receipt	construct_orphan_receipt_from_wire_fields	ORACLE_S3T4_68	MUTANT_S3T4_68_CONSTRUCT_ORPHAN_RECEIPT_FROM_WIRE_FIELDS	BASELINE:S3T4_68	reused
S3T4_69	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_lost_worker_delivery_is_unresolved_and_never_worker_success	treat_lost_worker_delivery_as_success	ORACLE_S3T4_69	MUTANT_S3T4_69_TREAT_LOST_WORKER_DELIVERY_AS_SUCCESS	BASELINE:S3T4_69	reused
S3T4_70	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_loss_before_native_spawn_closes_one_no_effect_orphan_ledger	lose_worker_before_native_spawn_without_orphan_ledger	ORACLE_S3T4_70	MUTANT_S3T4_70_LOSE_WORKER_BEFORE_NATIVE_SPAWN_WITHOUT_ORPHAN_LEDGER	BASELINE:S3T4_70	reused
S3T4_71	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_loss_after_native_spawn_keeps_broker_cleanup_authority	abandon_native_child_on_worker_loss_after_spawn	ORACLE_S3T4_71	MUTANT_S3T4_71_ABANDON_NATIVE_CHILD_ON_WORKER_LOSS_AFTER_SPAWN	BASELINE:S3T4_71	reused
S3T4_72	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_loss_after_native_reap_keeps_orphan_delivery_obligation	strand_reaped_obligation_on_worker_loss	ORACLE_S3T4_72	MUTANT_S3T4_72_STRAND_REAPED_OBLIGATION_ON_WORKER_LOSS	BASELINE:S3T4_72	reused
S3T4_73	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_worker_loss_after_native_closes_still_requires_orphan_ack	strand_closed_obligation_on_worker_loss	ORACLE_S3T4_73	MUTANT_S3T4_73_STRAND_CLOSED_OBLIGATION_ON_WORKER_LOSS	BASELINE:S3T4_73	reused
S3T4_74	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_lost_orphan_ack_never_retires_or_reuses_generation	retire_orphan_without_python_ack	ORACLE_S3T4_74	MUTANT_S3T4_74_RETIRE_ORPHAN_WITHOUT_PYTHON_ACK	BASELINE:S3T4_74	reused
S3T4_75	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_second_worker_waits_for_orphan_ledger_settlement	admit_second_worker_before_orphan_ack	ORACLE_S3T4_75	MUTANT_S3T4_75_ADMIT_SECOND_WORKER_BEFORE_ORPHAN_ACK	BASELINE:S3T4_75	reused
S3T4_76	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_exact_orphan_ack_retires_safely_settled_native_obligation	keep_safely_settled_orphan_busy_after_ack	ORACLE_S3T4_76	MUTANT_S3T4_76_KEEP_SAFELY_SETTLED_ORPHAN_BUSY_AFTER_ACK	BASELINE:S3T4_76	reused
S3T4_77	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_canonical_json_decoder_accepts_legal_integer_equality_and_rejects_every_ambiguous_or_noncanonical_form	accept_json_trailing_bytes	ORACLE_S3T4_77	MUTANT_S3T4_77_ACCEPT_JSON_TRAILING_BYTES	BASELINE:S3T4_77,R7-002	modified
S3T4_78	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_canonical_json_encoder_emits_exact_ascii_bytes	emit_noncanonical_json_spacing	ORACLE_S3T4_78	MUTANT_S3T4_78_EMIT_NONCANONICAL_JSON_SPACING	BASELINE:S3T4_78,R7-002	modified
S3T4_79	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_helper_exchange_caps_equal_frozen_resource_table	change_helper_stdout_cap	ORACLE_S3T4_79	MUTANT_S3T4_79_CHANGE_HELPER_STDOUT_CAP	BASELINE:S3T4_79	reused
S3T4_80	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_native_fixture_and_wire_caps_equal_frozen_resource_table	change_native_stdout_cap	ORACLE_S3T4_80	MUTANT_S3T4_80_CHANGE_NATIVE_STDOUT_CAP	BASELINE:S3T4_80	reused
S3T4_81	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_observer_config_report_and_token_caps_equal_frozen_resource_table	change_observer_frame_cap	ORACLE_S3T4_81	MUTANT_S3T4_81_CHANGE_OBSERVER_FRAME_CAP	BASELINE:S3T4_81	reused
S3T4_82	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_compiler_and_clock_caps_equal_frozen_resource_table	change_compiler_stdout_cap	ORACLE_S3T4_82	MUTANT_S3T4_82_CHANGE_COMPILER_STDOUT_CAP	BASELINE:S3T4_82	reused
S3T4_83	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_exec_status_go_guardian_and_witness_caps_equal_frozen_resource_table	change_exec_status_cap	ORACLE_S3T4_83	MUTANT_S3T4_83_CHANGE_EXEC_STATUS_CAP	BASELINE:S3T4_83	reused
S3T4_84	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_serialized_resource_aggregates_are_dimensionally_exact	omit_stop_from_observer_total	ORACLE_S3T4_84	MUTANT_S3T4_84_OMIT_STOP_FROM_OBSERVER_TOTAL	BASELINE:S3T4_84,R7-026	modified
S3T4_85	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_announced_and_read_lengths_are_checked_before_allocation_or_extension	allocate_before_announced_length_cap	ORACLE_S3T4_85	MUTANT_S3T4_85_ALLOCATE_BEFORE_ANNOUNCED_LENGTH_CAP	BASELINE:S3T4_85	reused
S3T4_86	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_discard_drain_byte_budget_accepts_equality_and_rejects_plus_one	extend_discard_byte_budget_one_past_cap	ORACLE_S3T4_86	MUTANT_S3T4_86_EXTEND_DISCARD_BYTE_BUDGET_ONE_PAST_CAP	BASELINE:S3T4_86	reused
S3T4_87	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_discard_drain_time_budget_accepts_equality_and_rejects_plus_one	extend_discard_time_budget_one_past_deadline	ORACLE_S3T4_87	MUTANT_S3T4_87_EXTEND_DISCARD_TIME_BUDGET_ONE_PAST_DEADLINE	BASELINE:S3T4_87	reused
S3T4_88	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_discard_budget_exhaustion_enters_authorized_cleanup_until_terminal_deadline	continue_discard_without_authorized_cleanup	ORACLE_S3T4_88	MUTANT_S3T4_88_CONTINUE_DISCARD_WITHOUT_AUTHORIZED_CLEANUP	BASELINE:S3T4_88	reused
S3T4_89	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_no_channel_uses_communicate_unbounded_read_text_mode_or_read_to_end	use_unbounded_channel_read	ORACLE_S3T4_89	MUTANT_S3T4_89_USE_UNBOUNDED_CHANNEL_READ	BASELINE:S3T4_89	reused
S3T4_90	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_python_serialized_retained_total_includes_one_admin_json_ack_pair	omit_admin_from_python_retained_total	ORACLE_S3T4_90	MUTANT_S3T4_90_OMIT_ADMIN_FROM_PYTHON_RETAINED_TOTAL	BASELINE:S3T4_90,R7-026	modified
S3T4_91	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_frame_cap_is_rolling_not_lifetime	treat_observer_frame_cap_as_lifetime_limit	ORACLE_S3T4_91	MUTANT_S3T4_91_TREAT_OBSERVER_FRAME_CAP_AS_LIFETIME_LIMIT	BASELINE:S3T4_91	reused
S3T4_92	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_sequence_overflow_is_unresolved_without_wrap	wrap_observer_sequence_after_uint64_max	ORACLE_S3T4_92	MUTANT_S3T4_92_WRAP_OBSERVER_SEQUENCE_AFTER_UINT64_MAX	BASELINE:S3T4_92	reused
S3T4_93	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_prepare_mount_leaf_is_named_inflight_effect_before_create	skip_prepare_mount_leaf_inflight_effect	ORACLE_S3T4_93	MUTANT_S3T4_93_SKIP_PREPARE_MOUNT_LEAF_INFLIGHT_EFFECT	BASELINE:S3T4_93	reused
S3T4_94	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_final_mount_leaf_removal_is_named_disposition_effect_with_closed_outcome	remove_mount_leaf_without_disposition_operation	ORACLE_S3T4_94	MUTANT_S3T4_94_REMOVE_MOUNT_LEAF_WITHOUT_DISPOSITION_OPERATION	BASELINE:S3T4_94	reused
S3T4_95	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_mount_leaf_is_mkdirat_openat_attested_and_carried_by_cursor	create_mount_leaf_without_descriptor_identity	ORACLE_S3T4_95	MUTANT_S3T4_95_CREATE_MOUNT_LEAF_WITHOUT_DESCRIPTOR_IDENTITY	BASELINE:S3T4_95	reused
S3T4_96	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_post_detach_absence_reopens_and_enumerates_same_leaf_identity	enumerate_pre_mount_directory_descriptor	ORACLE_S3T4_96	MUTANT_S3T4_96_ENUMERATE_PRE_MOUNT_DIRECTORY_DESCRIPTOR	BASELINE:S3T4_96	reused
S3T4_97	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_mount_leaf_identity_error_symlink_replacement_nonempty_and_close_matrix_preserves	accept_replaced_mount_leaf_as_absent	ORACLE_S3T4_97	MUTANT_S3T4_97_ACCEPT_REPLACED_MOUNT_LEAF_AS_ABSENT	BASELINE:S3T4_97	reused
S3T4_98	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_inflight_predecessor_is_exact_closed_union_including_mount_broker_and_open_unresolved_outcomes	replace_inflight_predecessor_union_with_any	ORACLE_S3T4_98	MUTANT_S3T4_98_REPLACE_INFLIGHT_PREDECESSOR_UNION_WITH_ANY	BASELINE:S3T4_98,R7-006	modified
S3T4_99	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainExecutorTests.test_inflight_rules_expand_to_unique_closed_pairs_and_reject_unlisted_pair	accept_unlisted_inflight_transition	ORACLE_S3T4_99	MUTANT_S3T4_99_ACCEPT_UNLISTED_INFLIGHT_TRANSITION	BASELINE:S3T4_99,R7-006	modified
S3T4_100	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_keychain_presence_receipts_are_three_incompatible_types	conflate_keychain_presence_receipts	ORACLE_S3T4_100	MUTANT_S3T4_100_CONFLATE_KEYCHAIN_PRESENCE_RECEIPTS	BASELINE:S3T4_100	reused
S3T4_101	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_unapproved_present_item_goes_directly_to_keychain_still_present_quarantine	route_unapproved_quarantine_through_keychain_absent	ORACLE_S3T4_101	MUTANT_S3T4_101_ROUTE_UNAPPROVED_QUARANTINE_THROUGH_KEYCHAIN_ABSENT	BASELINE:S3T4_101	reused
S3T4_102	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_ambiguous_or_missing_requery_is_presence_unknown_and_preserve_only	treat_unknown_keychain_requery_as_absent	ORACLE_S3T4_102	MUTANT_S3T4_102_TREAT_UNKNOWN_KEYCHAIN_REQUERY_AS_ABSENT	BASELINE:S3T4_102	reused
S3T4_103	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_deletion_tombstone_is_not_public_unapproved_quarantine_state	expose_deletion_tombstone_as_unapproved_quarantine	ORACLE_S3T4_103	MUTANT_S3T4_103_EXPOSE_DELETION_TOMBSTONE_AS_UNAPPROVED_QUARANTINE	BASELINE:S3T4_103	reused
S3T4_104	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_artifact_disposition_and_child_free_lease_precede_broker_stop	stop_broker_before_artifact_disposition	ORACLE_S3T4_104	MUTANT_S3T4_104_STOP_BROKER_BEFORE_ARTIFACT_DISPOSITION	BASELINE:S3T4_104	reused
S3T4_105	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_busy_broker_at_plus_115_mints_open_unresolved_handle_without_any_stop_or_close	close_busy_broker_at_plus_115	ORACLE_S3T4_105	MUTANT_S3T4_105_CLOSE_BUSY_BROKER_AT_PLUS_115	BASELINE:S3T4_105,R7-004,R7-005	modified
S3T4_106	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_open_unresolved_handle_is_strong_identity_one_shot_and_authorizes_only_native_broker_observer_late_close	replay_open_unresolved_handle	ORACLE_S3T4_106	MUTANT_S3T4_106_REPLAY_OPEN_UNRESOLVED_HANDLE	BASELINE:S3T4_106,R7-004,R7-005	modified
S3T4_107	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_broker_stop_is_refused_while_any_invocation_is_unretired	stop_broker_with_unretired_invocation	ORACLE_S3T4_107	MUTANT_S3T4_107_STOP_BROKER_WITH_UNRETIRED_INVOCATION	BASELINE:S3T4_107,R7-004,R7-005	modified
S3T4_108	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_observer_stop_is_refused_before_broker_proved_close	stop_observer_before_broker_proved_close	ORACLE_S3T4_108	MUTANT_S3T4_108_STOP_OBSERVER_BEFORE_BROKER_PROVED_CLOSE	BASELINE:S3T4_108,R7-004,R7-005	modified
S3T4_109	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_python_owner_cannot_exit_while_session_is_open_unresolved	exit_python_owner_while_open_unresolved	ORACLE_S3T4_109	MUTANT_S3T4_109_EXIT_PYTHON_OWNER_WHILE_OPEN_UNRESOLVED	BASELINE:S3T4_109,R7-004,R7-005	modified
S3T4_110	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_open_unresolved_preserves_securityagent_fail_precedence	downgrade_securityagent_fail_to_unclear	ORACLE_S3T4_110	MUTANT_S3T4_110_DOWNGRADE_SECURITYAGENT_FAIL_TO_UNCLEAR	BASELINE:S3T4_110,R7-004,R7-005	modified
S3T4_111	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_open_unresolved_actual_observer_loss_is_observer_unavailable_unclear	upgrade_observer_unavailable_to_fail	ORACLE_S3T4_111	MUTANT_S3T4_111_UPGRADE_OBSERVER_UNAVAILABLE_TO_FAIL	BASELINE:S3T4_111,R7-004,R7-005	modified
S3T4_112	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_later_proved_close_cannot_upgrade_locked_terminal_verdict	upgrade_terminal_unresolved_to_pass_on_close	ORACLE_S3T4_112	MUTANT_S3T4_112_UPGRADE_TERMINAL_UNRESOLVED_TO_PASS_ON_CLOSE	BASELINE:S3T4_112,R7-004,R7-005	modified
S3T4_113	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_full_stop_write	accept_partial_broker_stop_write	ORACLE_S3T4_113	MUTANT_S3T4_113_ACCEPT_PARTIAL_BROKER_STOP_WRITE	BASELINE:S3T4_113	reused
S3T4_114	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_stdout_eof	accept_missing_broker_stdout_eof	ORACLE_S3T4_114	MUTANT_S3T4_114_ACCEPT_MISSING_BROKER_STDOUT_EOF	BASELINE:S3T4_114	reused
S3T4_115	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_stderr_eof	accept_missing_broker_stderr_eof	ORACLE_S3T4_115	MUTANT_S3T4_115_ACCEPT_MISSING_BROKER_STDERR_EOF	BASELINE:S3T4_115	reused
S3T4_116	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_reader_joins	skip_broker_reader_join	ORACLE_S3T4_116	MUTANT_S3T4_116_SKIP_BROKER_READER_JOIN	BASELINE:S3T4_116	reused
S3T4_117	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_exit_zero	accept_nonzero_broker_exit	ORACLE_S3T4_117	MUTANT_S3T4_117_ACCEPT_NONZERO_BROKER_EXIT	BASELINE:S3T4_117	reused
S3T4_118	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_exact_waitpid	skip_exact_broker_reap	ORACLE_S3T4_118	MUTANT_S3T4_118_SKIP_EXACT_BROKER_REAP	BASELINE:S3T4_118	reused
S3T4_119	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_postreap_group_esrch	accept_present_broker_group_after_reap	ORACLE_S3T4_119	MUTANT_S3T4_119_ACCEPT_PRESENT_BROKER_GROUP_AFTER_REAP	BASELINE:S3T4_119	reused
S3T4_120	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_every_descriptor_close	ignore_broker_descriptor_close_failure	ORACLE_S3T4_120	MUTANT_S3T4_120_IGNORE_BROKER_DESCRIPTOR_CLOSE_FAILURE	BASELINE:S3T4_120	reused
S3T4_121	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_final_observer_snapshot_starts_only_after_broker_proved_close	start_final_snapshot_before_broker_group_absence	ORACLE_S3T4_121	MUTANT_S3T4_121_START_FINAL_SNAPSHOT_BEFORE_BROKER_GROUP_ABSENCE	BASELINE:S3T4_121	reused
S3T4_122	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_final_snapshot	skip_observer_final_snapshot	ORACLE_S3T4_122	MUTANT_S3T4_122_SKIP_OBSERVER_FINAL_SNAPSHOT	BASELINE:S3T4_122	reused
S3T4_123	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_full_stop_write	accept_partial_observer_stop_write	ORACLE_S3T4_123	MUTANT_S3T4_123_ACCEPT_PARTIAL_OBSERVER_STOP_WRITE	BASELINE:S3T4_123	reused
S3T4_124	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_stdin_flush_and_close	mint_stopped_before_observer_stdin_close	ORACLE_S3T4_124	MUTANT_S3T4_124_MINT_STOPPED_BEFORE_OBSERVER_STDIN_CLOSE	BASELINE:S3T4_124	reused
S3T4_125	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_contiguous_stopped_frame	accept_missing_observer_stopped_frame	ORACLE_S3T4_125	MUTANT_S3T4_125_ACCEPT_MISSING_OBSERVER_STOPPED_FRAME	BASELINE:S3T4_125	reused
S3T4_126	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_stdout_eof	accept_missing_observer_stdout_eof	ORACLE_S3T4_126	MUTANT_S3T4_126_ACCEPT_MISSING_OBSERVER_STDOUT_EOF	BASELINE:S3T4_126	reused
S3T4_127	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_stderr_eof	accept_missing_observer_stderr_eof	ORACLE_S3T4_127	MUTANT_S3T4_127_ACCEPT_MISSING_OBSERVER_STDERR_EOF	BASELINE:S3T4_127	reused
S3T4_128	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_reader_joins	skip_observer_reader_join	ORACLE_S3T4_128	MUTANT_S3T4_128_SKIP_OBSERVER_READER_JOIN	BASELINE:S3T4_128	reused
S3T4_129	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_exit_zero	accept_nonzero_observer_exit	ORACLE_S3T4_129	MUTANT_S3T4_129_ACCEPT_NONZERO_OBSERVER_EXIT	BASELINE:S3T4_129	reused
S3T4_130	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_postreap_group_esrch	mint_observer_stopped_without_group_absence	ORACLE_S3T4_130	MUTANT_S3T4_130_MINT_OBSERVER_STOPPED_WITHOUT_GROUP_ABSENCE	BASELINE:S3T4_130	reused
S3T4_131	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_shutdown_requires_every_descriptor_close	ignore_observer_descriptor_close_failure	ORACLE_S3T4_131	MUTANT_S3T4_131_IGNORE_OBSERVER_DESCRIPTOR_CLOSE_FAILURE	BASELINE:S3T4_131	reused
S3T4_132	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_termination_outcome_has_stopped_and_terminal_failure_variants	collapse_observer_termination_outcome	ORACLE_S3T4_132	MUTANT_S3T4_132_COLLAPSE_OBSERVER_TERMINATION_OUTCOME	BASELINE:S3T4_132	reused
S3T4_133	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_session_progress_separates_closed_disposition_from_strong_one_shot_open_unresolved_handle	close_open_unresolved_handle_directly	ORACLE_S3T4_133	MUTANT_S3T4_133_CLOSE_OPEN_UNRESOLVED_HANDLE_DIRECTLY	BASELINE:S3T4_133,R7-004	modified
S3T4_134	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainControlTests.test_public_code_exit_and_response_presence_table_matches_independent_literal	map_keychain_failed_to_exit_64	ORACLE_S3T4_134	MUTANT_S3T4_134_MAP_KEYCHAIN_FAILED_TO_EXIT_64	BASELINE:S3T4_134	reused
S3T4_135	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_non_scm_rights_ancillary_data_is_rejected	accept_non_scm_rights_ancillary_data	ORACLE_S3T4_135	MUTANT_S3T4_135_ACCEPT_NON_SCM_RIGHTS_ANCILLARY_DATA	BASELINE:S3T4_135	reused
S3T4_136	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_transferred_fd_alias_with_stdio_control_or_admin_is_rejected	accept_broker_fd_alias	ORACLE_S3T4_136	MUTANT_S3T4_136_ACCEPT_BROKER_FD_ALIAS	BASELINE:S3T4_136	reused
S3T4_137	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_broker_shutdown_requires_stdin_flush_and_close	mint_broker_stopped_before_stdin_close	ORACLE_S3T4_137	MUTANT_S3T4_137_MINT_BROKER_STOPPED_BEFORE_STDIN_CLOSE	BASELINE:S3T4_137	reused
S3T4_138	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_wrong_broker_socket_type_is_rejected	accept_wrong_broker_socket_type	ORACLE_S3T4_138	MUTANT_S3T4_138_ACCEPT_WRONG_BROKER_SOCKET_TYPE	BASELINE:S3T4_138	reused
S3T4_139	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_json_item_cap_accepts_legal_equality_and_rejects_plus_one	accept_broker_json_item_count_plus_one	ORACLE_S3T4_139	MUTANT_S3T4_139_ACCEPT_BROKER_JSON_ITEM_COUNT_PLUS_ONE	BASELINE:S3T4_139	reused
S3T4_140	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_json_key_cap_accepts_legal_equality_and_rejects_plus_one	accept_broker_json_key_length_plus_one	ORACLE_S3T4_140	MUTANT_S3T4_140_ACCEPT_BROKER_JSON_KEY_LENGTH_PLUS_ONE	BASELINE:S3T4_140	reused
S3T4_141	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_global_and_broker_effective_json_string_token_caps_have_legal_equality_witnesses_and_reject_plus_one	accept_broker_json_string_token_length_plus_one	ORACLE_S3T4_141	MUTANT_S3T4_141_ACCEPT_BROKER_JSON_STRING_TOKEN_LENGTH_PLUS_ONE	BASELINE:S3T4_141	reused
S3T4_142	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_stream_chunk_cap_accepts_legal_equality_and_rejects_plus_one	accept_broker_chunk_cap_plus_one	ORACLE_S3T4_142	MUTANT_S3T4_142_ACCEPT_BROKER_CHUNK_CAP_PLUS_ONE	BASELINE:S3T4_142	reused
S3T4_143	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_per_command_frame_and_byte_caps_accept_unique_legal_equality_and_reject_plus_one	accept_broker_command_cap_plus_one	ORACLE_S3T4_143	MUTANT_S3T4_143_ACCEPT_BROKER_COMMAND_CAP_PLUS_ONE	BASELINE:S3T4_143	reused
S3T4_144	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_normal_and_cancel_session_traces_are_separate_unique_legal_maxima	accept_broker_session_cap_plus_one	ORACLE_S3T4_144	MUTANT_S3T4_144_ACCEPT_BROKER_SESSION_CAP_PLUS_ONE	BASELINE:S3T4_144	reused
S3T4_145	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_v2_fourth_lease_tombstone_witness_accepts_admin_frame_34_rejects_35_and_separates_wire_byte_max	accept_admin_frame_count_35	ORACLE_S3T4_145	MUTANT_S3T4_145_ACCEPT_ADMIN_FRAME_COUNT_35	BASELINE:S3T4_145	reused
S3T4_146	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_open_unresolved_with_live_observer_uses_supervision_unresolved_unclear_cause	misclassify_supervision_unresolved_as_observer_unavailable	ORACLE_S3T4_146	MUTANT_S3T4_146_MISCLASSIFY_SUPERVISION_UNRESOLVED_AS_OBSERVER_UNAVAILABLE	BASELINE:S3T4_146,R7-004	modified
S3T4_147	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_securityagent_detection_after_plus_115_escalates_unclear_to_fail	ignore_post_cutoff_securityagent_detection	ORACLE_S3T4_147	MUTANT_S3T4_147_IGNORE_POST_CUTOFF_SECURITYAGENT_DETECTION	BASELINE:S3T4_147,R7-004	modified
S3T4_148	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_broker_v2_header_magic_version_channels_flags_offsets_and_endianness_are_byte_exact	change_broker_magic_byte	ORACLE_S3T4_148	MUTANT_S3T4_148_CHANGE_BROKER_MAGIC_BYTE	BASELINE:S3T4_148,R7-002	modified
S3T4_149	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_broker_v2_admin_numeric_type_payload_and_ancillary_table_is_exact	reuse_admin_ack_type_discriminant	ORACLE_S3T4_149	MUTANT_S3T4_149_REUSE_ADMIN_ACK_TYPE_DISCRIMINANT	BASELINE:S3T4_149,R7-002	modified
S3T4_150	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_broker_v2_worker_numeric_type_and_payload_table_is_exact	reuse_worker_ack_type_discriminant	ORACLE_S3T4_150	MUTANT_S3T4_150_REUSE_WORKER_ACK_TYPE_DISCRIMINANT	BASELINE:S3T4_150,R7-002	modified
S3T4_151	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_broker_v2_python_and_swift_golden_vectors_are_byte_identical	encode_broker_generation_little_endian	ORACLE_S3T4_151	MUTANT_S3T4_151_ENCODE_BROKER_GENERATION_LITTLE_ENDIAN	BASELINE:S3T4_151,R7-002	modified
S3T4_152	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_prepare_mount_leaf_mkdirat_is_dominated_by_admin_child_free_permit	bypass_admin_permit_for_prepare_mount_leaf_mkdirat	ORACLE_S3T4_152	MUTANT_S3T4_152_BYPASS_ADMIN_PERMIT_FOR_PREPARE_MOUNT_LEAF_MKDIRAT	BASELINE:S3T4_152	reused
S3T4_153	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_quarantine_rename_is_dominated_by_admin_child_free_permit	bypass_admin_permit_for_quarantine_rename	ORACLE_S3T4_153	MUTANT_S3T4_153_BYPASS_ADMIN_PERMIT_FOR_QUARANTINE_RENAME	BASELINE:S3T4_153	reused
S3T4_154	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainCleanupTests.test_image_unlink_is_dominated_by_admin_child_free_permit	bypass_admin_permit_for_image_unlink	ORACLE_S3T4_154	MUTANT_S3T4_154_BYPASS_ADMIN_PERMIT_FOR_IMAGE_UNLINK	BASELINE:S3T4_154	reused
S3T4_155	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainQuarantineTests.test_final_mount_leaf_removal_is_dominated_by_admin_child_free_permit	bypass_admin_permit_for_final_mount_leaf_removal	ORACLE_S3T4_155	MUTANT_S3T4_155_BYPASS_ADMIN_PERMIT_FOR_FINAL_MOUNT_LEAF_REMOVAL	BASELINE:S3T4_155	reused
S3T4_156	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_broker_refuses_second_or_cross_channel_child_free_lease	grant_cross_channel_double_child_free_lease	ORACLE_S3T4_156	MUTANT_S3T4_156_GRANT_CROSS_CHANNEL_DOUBLE_CHILD_FREE_LEASE	BASELINE:S3T4_156	reused
S3T4_157	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_admin_child_free_permit_rejects_stale_poll_before_mutation_and_releases_totally	mutate_after_stale_admin_terminal_poll	ORACLE_S3T4_157	MUTANT_S3T4_157_MUTATE_AFTER_STALE_ADMIN_TERMINAL_POLL	BASELINE:S3T4_157	reused
S3T5_01	5	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_fixture_is_immediate_and_self_expiry_is_containment_only	suspend_fixture_spawn	ORACLE_S3T5_01	MUTANT_S3T5_01_SUSPEND_FIXTURE_SPAWN	BASELINE:S3T5_01	reused
S3T5_02	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_frame_without_control_eof_is_unclear	accept_frame_without_control_eof	ORACLE_S3T5_02	MUTANT_S3T5_02_ACCEPT_FRAME_WITHOUT_CONTROL_EOF	BASELINE:S3T5_02	reused
S3T5_03	5	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_fixture_does_not_inherit_helper_control_fd	inherit_control_into_fixture	ORACLE_S3T5_03	MUTANT_S3T5_03_INHERIT_CONTROL_INTO_FIXTURE	BASELINE:S3T5_03	reused
S3T5_04	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_shared_clock_parent_deadline_and_endpoints_exist_before_popen	create_parent_deadline_after_popen	ORACLE_S3T5_04	MUTANT_S3T5_04_CREATE_PARENT_DEADLINE_AFTER_POPEN	BASELINE:S3T5_04	reused
S3T5_05	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_child_report_cannot_extend_parent_deadline	allow_child_report_deadline_extension	ORACLE_S3T5_05	MUTANT_S3T5_05_ALLOW_CHILD_REPORT_DEADLINE_EXTENSION	BASELINE:S3T5_05	reused
S3T5_06	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_parent_cleanup_reserve_precedes_hard_deadline	start_cleanup_at_parent_hard_deadline	ORACLE_S3T5_06	MUTANT_S3T5_06_START_CLEANUP_AT_PARENT_HARD_DEADLINE	BASELINE:S3T5_06	reused
S3T5_07	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_parent_reaps_exact_unreaped_interpreter_on_every_failure	skip_exact_interpreter_reap	ORACLE_S3T5_07	MUTANT_S3T5_07_SKIP_EXACT_INTERPRETER_REAP	BASELINE:S3T5_07	reused
S3T5_08	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_parent_validates_complete_report_before_one_go	send_go_before_report_validation	ORACLE_S3T5_08	MUTANT_S3T5_08_SEND_GO_BEFORE_REPORT_VALIDATION	BASELINE:S3T5_08	reused
S3T5_09	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_interpreter_execs_helper_in_same_registered_pid	accept_report_pid_different_from_popen_pid	ORACLE_S3T5_09	MUTANT_S3T5_09_ACCEPT_REPORT_PID_DIFFERENT_FROM_POPEN_PID	BASELINE:S3T5_09	reused
S3T5_10	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_parent_popen_ast_has_exact_stdio_flags_and_pass_fds	use_relative_fresh_interpreter	ORACLE_S3T5_10	MUTANT_S3T5_10_USE_RELATIVE_FRESH_INTERPRETER	BASELINE:S3T5_10	reused
S3T5_11	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_pre_go_descriptor_inventory_is_exact	skip_pre_go_descriptor_inventory	ORACLE_S3T5_11	MUTANT_S3T5_11_SKIP_PRE_GO_DESCRIPTOR_INVENTORY	BASELINE:S3T5_11	reused
S3T5_12	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_exec_status_cloexec_eof_or_fixed_failure_record_is_total	accept_malformed_exec_status	ORACLE_S3T5_12	MUTANT_S3T5_12_ACCEPT_MALFORMED_EXEC_STATUS	BASELINE:S3T5_12	reused
S3T5_13	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_post_exec_helper_descriptor_inventory_is_exact	skip_post_exec_descriptor_inventory	ORACLE_S3T5_13	MUTANT_S3T5_13_SKIP_POST_EXEC_DESCRIPTOR_INVENTORY	BASELINE:S3T5_13	reused
S3T5_14	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_short_supervisor_deadline_is_testing_only_and_production_rejects_it	accept_test_short_deadline_in_production	ORACLE_S3T5_14	MUTANT_S3T5_14_ACCEPT_TEST_SHORT_DEADLINE_IN_PRODUCTION	BASELINE:S3T5_14	reused
S3T5_15	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_cleanup_reserve_reaches_no_child_spawn_path	spawn_during_cleanup_reserve	ORACLE_S3T5_15	MUTANT_S3T5_15_SPAWN_DURING_CLEANUP_RESERVE	BASELINE:S3T5_15	reused
S3T5_16	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_pid_count_and_fill_byte_capacity_are_not_conflated	pass_pid_count_as_byte_count	ORACLE_S3T5_16	MUTANT_S3T5_16_PASS_PID_COUNT_AS_BYTE_COUNT	BASELINE:S3T5_16	reused
S3T5_17	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_full_pid_buffer_is_incomplete_not_absent	treat_full_pid_buffer_as_absent	ORACLE_S3T5_17	MUTANT_S3T5_17_TREAT_FULL_PID_BUFFER_AS_ABSENT	BASELINE:S3T5_17	reused
S3T5_18	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_procargs_errno_identity_and_framing_are_never_absent	skip_procargs_error	ORACLE_S3T5_18	MUTANT_S3T5_18_SKIP_PROCARGS_ERROR	BASELINE:S3T5_18	reused
S3T5_19	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_survivor_scan_pid_and_procargs_caps_are_fixed	remove_survivor_scan_caps	ORACLE_S3T5_19	MUTANT_S3T5_19_REMOVE_SURVIVOR_SCAN_CAPS	BASELINE:S3T5_19	reused
S3T5_20	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_survivor_scan_discards_every_command_buffer	retain_scanned_command_bytes	ORACLE_S3T5_20	MUTANT_S3T5_20_RETAIN_SCANNED_COMMAND_BYTES	BASELINE:S3T5_20	reused
S3T5_21	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainLibprocTests.test_cleanup_scan_has_no_process_or_shell_launch_path	use_ps_subprocess_for_survivor_scan	ORACLE_S3T5_21	MUTANT_S3T5_21_USE_PS_SUBPROCESS_FOR_SURVIVOR_SCAN	BASELINE:S3T5_21	reused
S3T5_22	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainFixtureCallGraphTests.test_compiler_ast_resolves_closed_fixture_call_graph	insert_reachable_unknown_call	ORACLE_S3T5_22	MUTANT_S3T5_22_INSERT_REACHABLE_UNKNOWN_CALL	BASELINE:S3T5_22	reused
S3T5_23	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainFixtureCallGraphTests.test_reachable_forbidden_call_source_mutant_is_rejected	insert_reachable_spawn_call	ORACLE_S3T5_23	MUTANT_S3T5_23_INSERT_REACHABLE_SPAWN_CALL	BASELINE:S3T5_23	reused
S3T5_24	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_harness_helper_observer_and_fixture_hashes_match_reviewed_sources	desynchronize_reviewed_helper_hash	ORACLE_S3T5_24	MUTANT_S3T5_24_DESYNCHRONIZE_REVIEWED_HELPER_HASH	BASELINE:S3T5_24	reused
S3T5_25	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainManifestTests.test_typed_mutant_manifest_is_isomorphic_and_tamper_evident	accept_manifest_wrong_target_kind	ORACLE_S3T5_25	MUTANT_S3T5_25_ACCEPT_MANIFEST_WRONG_TARGET_KIND	BASELINE:S3T5_25	reused
S3T5_26	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainManifestTests.test_source_mutants_preserve_oracle_hash_and_delete_private_copy	mutate_oracle_copy	ORACLE_S3T5_26	MUTANT_S3T5_26_MUTATE_ORACLE_COPY	BASELINE:S3T5_26	reused
S3T5_27	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_exact_allowlist_hash_manifest_refuses_three_negative_fixtures	allow_extra_review_package_entry	ORACLE_S3T5_27	MUTANT_S3T5_27_ALLOW_EXTRA_REVIEW_PACKAGE_ENTRY	BASELINE:S3T5_27,R7-023	modified
S3T5_28	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_final_spec_blob_hash_equals_reviewed_hash	record_spec_hash_without_comparison	ORACLE_S3T5_28	MUTANT_S3T5_28_RECORD_SPEC_HASH_WITHOUT_COMPARISON	BASELINE:S3T5_28	reused
S3T5_29	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_final_plan_blob_hash_equals_reviewed_hash	record_plan_hash_without_comparison	ORACLE_S3T5_29	MUTANT_S3T5_29_RECORD_PLAN_HASH_WITHOUT_COMPARISON	BASELINE:S3T5_29	reused
S3T5_30	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_final_cumulative_paths_equal_exact_three_files	accept_extra_implementation_path	ORACLE_S3T5_30	MUTANT_S3T5_30_ACCEPT_EXTRA_IMPLEMENTATION_PATH	BASELINE:S3T5_30	reused
S3T5_31	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_both_modes_close_guardian_by_work_cutoff	hold_guardian_open_past_work_cutoff	ORACLE_S3T5_31	MUTANT_S3T5_31_HOLD_GUARDIAN_OPEN_PAST_WORK_CUTOFF	BASELINE:S3T5_31	reused
S3T5_32	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_fixture_self_expiry_cannot_satisfy_normal_success	count_fixture_self_expiry_as_success	ORACLE_S3T5_32	MUTANT_S3T5_32_COUNT_FIXTURE_SELF_EXPIRY_AS_SUCCESS	BASELINE:S3T5_32	reused
S3T5_33	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_report_binds_route_digest_paths_and_source_binary_hashes	accept_report_without_route_digest	ORACLE_S3T5_33	MUTANT_S3T5_33_ACCEPT_REPORT_WITHOUT_ROUTE_DIGEST	BASELINE:S3T5_33	reused
S3T5_34	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_exec_failure_uses_fixed_errno_record_reserved_exit_and_exact_wait	swap_exec_failure_reserved_exit	ORACLE_S3T5_34	MUTANT_S3T5_34_SWAP_EXEC_FAILURE_RESERVED_EXIT	BASELINE:S3T5_34	reused
S3T5_35	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_missing_pass_fd_is_rejected_before_go	omit_one_pass_fd	ORACLE_S3T5_35	MUTANT_S3T5_35_OMIT_ONE_PASS_FD	BASELINE:S3T5_35	reused
S3T5_36	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_extra_pass_fd_is_rejected_before_go	pass_extra_fd	ORACLE_S3T5_36	MUTANT_S3T5_36_PASS_EXTRA_FD	BASELINE:S3T5_36	reused
S3T5_37	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_duplicate_or_stdio_aliased_child_fd_is_rejected	allow_duplicate_child_fd	ORACLE_S3T5_37	MUTANT_S3T5_37_ALLOW_DUPLICATE_CHILD_FD	BASELINE:S3T5_37	reused
S3T5_38	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_exec_status_is_only_child_fd_with_cloexec	set_cloexec_on_wrong_fd	ORACLE_S3T5_38	MUTANT_S3T5_38_SET_CLOEXEC_ON_WRONG_FD	BASELINE:S3T5_38	reused
S3T5_39	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_fresh_interpreter_stdio_are_exact_pipes	inherit_fresh_interpreter_stdio	ORACLE_S3T5_39	MUTANT_S3T5_39_INHERIT_FRESH_INTERPRETER_STDIO	BASELINE:S3T5_39	reused
S3T5_40	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_exec_argv0_equals_absolute_reviewed_helper	exec_with_wrong_argv0	ORACLE_S3T5_40	MUTANT_S3T5_40_EXEC_WITH_WRONG_ARGV0	BASELINE:S3T5_40	reused
S3T5_41	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_helper_handoff_is_direct_exec_not_new_process	start_helper_with_popen_instead_of_exec	ORACLE_S3T5_41	MUTANT_S3T5_41_START_HELPER_WITH_POPEN_INSTEAD_OF_EXEC	BASELINE:S3T5_41	reused
S3T5_42	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_guardian_route_never_uses_production_deadline_flag	route_guardian_through_production_deadline_flag	ORACLE_S3T5_42	MUTANT_S3T5_42_ROUTE_GUARDIAN_THROUGH_PRODUCTION_DEADLINE_FLAG	BASELINE:S3T5_42	reused
S3T5_43	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_exec_path_equals_absolute_reviewed_helper	exec_with_wrong_helper_path	ORACLE_S3T5_43	MUTANT_S3T5_43_EXEC_WITH_WRONG_HELPER_PATH	BASELINE:S3T5_43	reused
S3T5_44	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_fresh_bootstrap_source_hash_and_isolated_argv_are_exact	omit_isolated_bootstrap_flag	ORACLE_S3T5_44	MUTANT_S3T5_44_OMIT_ISOLATED_BOOTSTRAP_FLAG	BASELINE:S3T5_44	reused
S3T5_45	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_fresh_bootstrap_environment_is_exact_minimal_mapping	inherit_fresh_environment	ORACLE_S3T5_45	MUTANT_S3T5_45_INHERIT_FRESH_ENVIRONMENT	BASELINE:S3T5_45,R7-022	modified
S3T5_46	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_bootstrap_report_rejects_wrong_source_hash	accept_wrong_bootstrap_hash	ORACLE_S3T5_46	MUTANT_S3T5_46_ACCEPT_WRONG_BOOTSTRAP_HASH	BASELINE:S3T5_46	reused
S3T5_47	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_bootstrap_installs_audit_hook_first_and_direct_imports_match_allowlist	import_site_before_bootstrap_audit_hook	ORACLE_S3T5_47	MUTANT_S3T5_47_IMPORT_SITE_BEFORE_BOOTSTRAP_AUDIT_HOOK	BASELINE:S3T5_47,R7-022	modified
S3T5_48	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDescriptorTests.test_parent_closes_report_duplicate_for_eof	retain_report_writer_duplicate	ORACLE_S3T5_48	MUTANT_S3T5_48_RETAIN_REPORT_WRITER_DUPLICATE	BASELINE:S3T5_48	reused
S3T5_49	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDescriptorTests.test_parent_closes_go_duplicate_for_eof	retain_go_reader_duplicate	ORACLE_S3T5_49	MUTANT_S3T5_49_RETAIN_GO_READER_DUPLICATE	BASELINE:S3T5_49	reused
S3T5_50	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDescriptorTests.test_parent_closes_exec_status_duplicate_for_eof	retain_exec_status_writer_duplicate	ORACLE_S3T5_50	MUTANT_S3T5_50_RETAIN_EXEC_STATUS_WRITER_DUPLICATE	BASELINE:S3T5_50	reused
S3T5_51	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDescriptorTests.test_parent_and_helper_close_witness_duplicates_for_eof	retain_witness_writer_duplicate	ORACLE_S3T5_51	MUTANT_S3T5_51_RETAIN_WITNESS_WRITER_DUPLICATE	BASELINE:S3T5_51	reused
S3T5_52	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDescriptorTests.test_parent_and_helper_close_control_duplicates_for_eof	retain_control_child_duplicate	ORACLE_S3T5_52	MUTANT_S3T5_52_RETAIN_CONTROL_CHILD_DUPLICATE	BASELINE:S3T5_52	reused
S3T5_53	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_serialization_is_deterministic	shuffle_canonical_oracle_records	ORACLE_S3T5_53	MUTANT_S3T5_53_SHUFFLE_CANONICAL_ORACLE_RECORDS	BASELINE:S3T5_53	reused
S3T5_54	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_changed_covered_oracle_byte_changes_digest	exclude_changed_covered_oracle_byte	ORACLE_S3T5_54	MUTANT_S3T5_54_EXCLUDE_CHANGED_COVERED_ORACLE_BYTE	BASELINE:S3T5_54	reused
S3T5_55	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_domain_separator_is_bound	accept_changed_oracle_domain_separator	ORACLE_S3T5_55	MUTANT_S3T5_55_ACCEPT_CHANGED_ORACLE_DOMAIN_SEPARATOR	BASELINE:S3T5_55	reused
S3T5_56	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_expected_attestation_fields_normalize_to_exactly_64_ascii_zeroes_and_reject_variable_lengths	use_variable_length_attestation_placeholder	ORACLE_S3T5_56	MUTANT_S3T5_56_USE_VARIABLE_LENGTH_ATTESTATION_PLACEHOLDER	BASELINE:S3T5_56	reused
S3T5_57	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_self_referential_raw_oracle_serialization_is_rejected	hash_self_referential_raw_manifest	ORACLE_S3T5_57	MUTANT_S3T5_57_HASH_SELF_REFERENTIAL_RAW_MANIFEST	BASELINE:S3T5_57	reused
S3T5_58	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_extra_keys	add_home_to_sanitized_worker_environment	ORACLE_S3T5_58	MUTANT_S3T5_58_ADD_HOME_TO_SANITIZED_WORKER_ENVIRONMENT	BASELINE:S3T5_58	reused
S3T5_59	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_missing_keys	omit_lc_all_from_sanitized_worker_environment	ORACLE_S3T5_59	MUTANT_S3T5_59_OMIT_LC_ALL_FROM_SANITIZED_WORKER_ENVIRONMENT	BASELINE:S3T5_59	reused
S3T5_60	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainContainedProcessProbeTests.test_sanitized_worker_environment_rejects_changed_values	change_sanitized_worker_path_value	ORACLE_S3T5_60	MUTANT_S3T5_60_CHANGE_SANITIZED_WORKER_PATH_VALUE	BASELINE:S3T5_60	reused
S3T5_61	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_fresh_interpreter_environment_rejects_missing_keys	omit_lc_all_from_fresh_interpreter_environment	ORACLE_S3T5_61	MUTANT_S3T5_61_OMIT_LC_ALL_FROM_FRESH_INTERPRETER_ENVIRONMENT	BASELINE:S3T5_61	reused
S3T5_62	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_fresh_interpreter_environment_rejects_changed_values	change_fresh_interpreter_path_value	ORACLE_S3T5_62	MUTANT_S3T5_62_CHANGE_FRESH_INTERPRETER_PATH_VALUE	BASELINE:S3T5_62	reused
S3T5_63	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_worker_rejects_unsealed_test_mutant_selector	forward_unsealed_test_mutant_selector	ORACLE_S3T5_63	MUTANT_S3T5_63_FORWARD_UNSEALED_TEST_MUTANT_SELECTOR	BASELINE:S3T5_63	reused
S3T5_64	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_worker_environment_rejects_missing_keys	omit_lang_from_worker_environment	ORACLE_S3T5_64	MUTANT_S3T5_64_OMIT_LANG_FROM_WORKER_ENVIRONMENT	BASELINE:S3T5_64	reused
S3T5_65	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_worker_environment_rejects_changed_values	change_worker_locale_value	ORACLE_S3T5_65	MUTANT_S3T5_65_CHANGE_WORKER_LOCALE_VALUE	BASELINE:S3T5_65	reused
S3T5_66	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_report_binds_fresh_interpreter_environment_digest	accept_report_without_fresh_environment_digest	ORACLE_S3T5_66	MUTANT_S3T5_66_ACCEPT_REPORT_WITHOUT_FRESH_ENVIRONMENT_DIGEST	BASELINE:S3T5_66	reused
S3T5_67	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainContainedProcessProbeTests.test_report_binds_worker_environment_digest	accept_report_without_worker_environment_digest	ORACLE_S3T5_67	MUTANT_S3T5_67_ACCEPT_REPORT_WITHOUT_WORKER_ENVIRONMENT_DIGEST	BASELINE:S3T5_67	reused
S3T5_68	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_interpreter_tcb_receipt_rejects_group_or_world_writable_binary	trust_group_writable_interpreter	ORACLE_S3T5_68	MUTANT_S3T5_68_TRUST_GROUP_WRITABLE_INTERPRETER	BASELINE:S3T5_68	reused
S3T5_69	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_interpreter_tcb_receipt_is_revalidated_before_go	skip_interpreter_tcb_revalidation_before_go	ORACLE_S3T5_69	MUTANT_S3T5_69_SKIP_INTERPRETER_TCB_REVALIDATION_BEFORE_GO	BASELINE:S3T5_69	reused
S3T5_70	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainBootstrapTests.test_transitive_imports_are_builtin_frozen_or_below_trusted_stdlib_roots	accept_project_origin_transitive_import	ORACLE_S3T5_70	MUTANT_S3T5_70_ACCEPT_PROJECT_ORIGIN_TRANSITIVE_IMPORT	BASELINE:S3T5_70	reused
S3T5_71	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_external_documentation_bootstrap_identity_is_receipt_hashed	accept_unhashed_external_doc_bootstrap	ORACLE_S3T5_71	MUTANT_S3T5_71_ACCEPT_UNHASHED_EXTERNAL_DOC_BOOTSTRAP	BASELINE:S3T5_71,R7-010,R7-011	modified
S3T5_72	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_each_reviewer_receipt_binds_exact_four_blob_identity	accept_reviewer_receipt_without_blob_tuple	ORACLE_S3T5_72	MUTANT_S3T5_72_ACCEPT_REVIEWER_RECEIPT_WITHOUT_BLOB_TUPLE	BASELINE:S3T5_72,R7-010,R7-011	modified
S3T5_73	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_embedded_documentation_gate_cannot_execute_before_three_approvals	execute_embedded_doc_gate_before_approval	ORACLE_S3T5_73	MUTANT_S3T5_73_EXECUTE_EMBEDDED_DOC_GATE_BEFORE_APPROVAL	BASELINE:S3T5_73,R7-010	modified
S3T5_74	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_embedded_gate_package_is_byte_identical_to_external_bootstrap_package	accept_nonidentical_embedded_gate_package	ORACLE_S3T5_74	MUTANT_S3T5_74_ACCEPT_NONIDENTICAL_EMBEDDED_GATE_PACKAGE	BASELINE:S3T5_74,R7-010	modified
S3T5_75	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_review_receipt_and_manifest_cannot_mix_packages	mix_package_a_receipt_with_package_b_manifest	ORACLE_S3T5_75	MUTANT_S3T5_75_MIX_PACKAGE_A_RECEIPT_WITH_PACKAGE_B_MANIFEST	BASELINE:S3T5_75,R7-010	modified
S3T5_76	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_task_five_reuses_only_approved_documentation_gate_sha	reuse_unapproved_doc_gate_sha	ORACLE_S3T5_76	MUTANT_S3T5_76_REUSE_UNAPPROVED_DOC_GATE_SHA	BASELINE:S3T5_76,R7-010	modified
S3T5_77	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_doc_candidate_equals_implementation_base_before_task_one	accept_doc_candidate_different_from_implementation_base	ORACLE_S3T5_77	MUTANT_S3T5_77_ACCEPT_DOC_CANDIDATE_DIFFERENT_FROM_IMPLEMENTATION_BASE	BASELINE:S3T5_77,R7-010,R7-011	modified
S3T5_78	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_every_multicommand_shell_receipt_uses_fail_closed_pipefail	allow_masked_shell_failure	ORACLE_S3T5_78	MUTANT_S3T5_78_ALLOW_MASKED_SHELL_FAILURE	BASELINE:S3T5_78,R7-022	modified
S3T5_79	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_structural_markdown_fence_state_resets_for_each_document	carry_fence_state_across_documents	ORACLE_S3T5_79	MUTANT_S3T5_79_CARRY_FENCE_STATE_ACROSS_DOCUMENTS	BASELINE:S3T5_79,R7-009	modified
S3T5_80	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_temporary_commit_has_exact_tree_and_parent	create_precommit_commit_with_wrong_tree	ORACLE_S3T5_80	MUTANT_S3T5_80_CREATE_PRECOMMIT_COMMIT_WITH_WRONG_TREE	BASELINE:S3T5_80,R7-011,R7-012	modified
S3T5_81	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_worktree_cwd_pythonpath_and_imports_are_detached	use_mutable_checkout_as_pythonpath	ORACLE_S3T5_81	MUTANT_S3T5_81_USE_MUTABLE_CHECKOUT_AS_PYTHONPATH	BASELINE:S3T5_81,R7-011,R7-012	modified
S3T5_82	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_runner_refuses_mutable_checkout	run_precommit_suite_from_mutable_checkout	ORACLE_S3T5_82	MUTANT_S3T5_82_RUN_PRECOMMIT_SUITE_FROM_MUTABLE_CHECKOUT	BASELINE:S3T5_82,R7-011,R7-012	modified
S3T5_83	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_runner_refuses_one_mutable_project_module	import_one_mutable_checkout_module	ORACLE_S3T5_83	MUTANT_S3T5_83_IMPORT_ONE_MUTABLE_CHECKOUT_MODULE	BASELINE:S3T5_83,R7-011,R7-012	modified
S3T5_84	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_receipt_rejects_wrong_tree	accept_precommit_receipt_for_wrong_tree	ORACLE_S3T5_84	MUTANT_S3T5_84_ACCEPT_PRECOMMIT_RECEIPT_FOR_WRONG_TREE	BASELINE:S3T5_84,R7-011,R7-012	modified
S3T5_85	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_precommit_receipt_rejects_wrong_parent	accept_precommit_receipt_for_wrong_parent	ORACLE_S3T5_85	MUTANT_S3T5_85_ACCEPT_PRECOMMIT_RECEIPT_FOR_WRONG_PARENT	BASELINE:S3T5_85,R7-011,R7-012	modified
S3T5_86	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_detached_worktree_cleanup_proves_zero_residue	retain_detached_worktree_residue	ORACLE_S3T5_86	MUTANT_S3T5_86_RETAIN_DETACHED_WORKTREE_RESIDUE	BASELINE:S3T5_86,R7-011,R7-012	modified
S3T5_87	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_git_dependent_gates_receive_explicit_repository_and_commit	assume_git_context_from_raw_archive	ORACLE_S3T5_87	MUTANT_S3T5_87_ASSUME_GIT_CONTEXT_FROM_RAW_ARCHIVE	BASELINE:S3T5_87,R7-011,R7-012	modified
S3T5_88	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_all_final_suites_and_mutants_rerun_from_immutable_s3_final	accept_precommit_receipts_as_final	ORACLE_S3T5_88	MUTANT_S3T5_88_ACCEPT_PRECOMMIT_RECEIPTS_AS_FINAL	BASELINE:S3T5_88,R7-011,R7-012	modified
S3T5_89	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainFinalComparisonTests.test_every_execution_receipt_binds_temporary_or_final_commit	accept_receipt_without_temporary_commit	ORACLE_S3T5_89	MUTANT_S3T5_89_ACCEPT_RECEIPT_WITHOUT_TEMPORARY_COMMIT	BASELINE:S3T5_89,R7-011,R7-012	modified
S3T5_90	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_manifest_freezes_full_owning_suite_before_mutation	derive_owning_suite_after_mutation	ORACLE_S3T5_90	MUTANT_S3T5_90_DERIVE_OWNING_SUITE_AFTER_MUTATION	BASELINE:S3T5_90	reused
S3T5_91	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_manifest_freezes_expected_failures_and_exclusivity_before_mutation	omit_multiple_expected_failure_ids	ORACLE_S3T5_91	MUTANT_S3T5_91_OMIT_MULTIPLE_EXPECTED_FAILURE_IDS	BASELINE:S3T5_91	reused
S3T5_92	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_expected_failure_set_never_comes_from_observed_output	learn_expected_failures_from_observed_output	ORACLE_S3T5_92	MUTANT_S3T5_92_LEARN_EXPECTED_FAILURES_FROM_OBSERVED_OUTPUT	BASELINE:S3T5_92	reused
S3T5_93	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_structural_atomicity_policy_is_prefrozen_and_independently_oracled	choose_structural_atomicity_after_run	ORACLE_S3T5_93	MUTANT_S3T5_93_CHOOSE_STRUCTURAL_ATOMICITY_AFTER_RUN	BASELINE:S3T5_93	reused
S3T5_94	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_mutant_runner_matches_full_failure_error_skip_timeout_and_success_set	ignore_mutant_timeout_in_failure_set	ORACLE_S3T5_94	MUTANT_S3T5_94_IGNORE_MUTANT_TIMEOUT_IN_FAILURE_SET	BASELINE:S3T5_94	reused
S3T5_95	5	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainManifestTests.test_swift_runtime_mutant_activation_is_sealed_and_testing_only	read_unsealed_swift_mutant_selector	ORACLE_S3T5_95	MUTANT_S3T5_95_READ_UNSEALED_SWIFT_MUTANT_SELECTOR	BASELINE:S3T5_95	reused
S3T5_96	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_resolves_every_referenced_constant	omit_referenced_constant_from_oracle_closure	ORACLE_S3T5_96	MUTANT_S3T5_96_OMIT_REFERENCED_CONSTANT_FROM_ORACLE_CLOSURE	BASELINE:S3T5_96	reused
S3T5_97	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_rejects_dynamic_or_unresolved_project_calls	accept_dynamic_oracle_call	ORACLE_S3T5_97	MUTANT_S3T5_97_ACCEPT_DYNAMIC_ORACLE_CALL	BASELINE:S3T5_97	reused
S3T5_98	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_reached_module_initializers_and_class_bodies	ignore_module_initializer_side_effect	ORACLE_S3T5_98	MUTANT_S3T5_98_IGNORE_MODULE_INITIALIZER_SIDE_EFFECT	BASELINE:S3T5_98	reused
S3T5_99	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_descriptor_and_property_accessors	ignore_property_accessor_dependency	ORACLE_S3T5_99	MUTANT_S3T5_99_IGNORE_PROPERTY_ACCESSOR_DEPENDENCY	BASELINE:S3T5_99	reused
S3T5_100	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_bases_metaclasses_and_mro	ignore_base_mro_dependency	ORACLE_S3T5_100	MUTANT_S3T5_100_IGNORE_BASE_MRO_DEPENDENCY	BASELINE:S3T5_100	reused
S3T5_101	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_executable_annotations	ignore_annotation_dependency	ORACLE_S3T5_101	MUTANT_S3T5_101_IGNORE_ANNOTATION_DEPENDENCY	BASELINE:S3T5_101	reused
S3T5_102	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_top_level_import_side_effects	ignore_import_side_effect_dependency	ORACLE_S3T5_102	MUTANT_S3T5_102_IGNORE_IMPORT_SIDE_EFFECT_DEPENDENCY	BASELINE:S3T5_102	reused
S3T5_103	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_oracle_closure_includes_resolved_implicit_protocol_calls	ignore_implicit_protocol_dependency	ORACLE_S3T5_103	MUTANT_S3T5_103_IGNORE_IMPLICIT_PROTOCOL_DEPENDENCY	BASELINE:S3T5_103	reused
S3T5_104	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_observer_build_receipt_binds_ephemeral_compiler_and_binary_identity	omit_observer_compiler_identity_from_receipt	ORACLE_S3T5_104	MUTANT_S3T5_104_OMIT_OBSERVER_COMPILER_IDENTITY_FROM_RECEIPT	BASELINE:S3T5_104	reused
S3T5_105	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_observer_binary_inode_and_digest_are_revalidated_before_spawn	skip_observer_binary_revalidation	ORACLE_S3T5_105	MUTANT_S3T5_105_SKIP_OBSERVER_BINARY_REVALIDATION	BASELINE:S3T5_105	reused
S3T5_106	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_observer_binary_has_no_cross_build_expected_digest	assert_reproducible_observer_binary_hash	ORACLE_S3T5_106	MUTANT_S3T5_106_ASSERT_REPRODUCIBLE_OBSERVER_BINARY_HASH	BASELINE:S3T5_106	reused
S3T5_107	5	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_replaced_observer_binary_is_rejected_before_spawn	accept_replaced_observer_binary	ORACLE_S3T5_107	MUTANT_S3T5_107_ACCEPT_REPLACED_OBSERVER_BINARY	BASELINE:S3T5_107	reused
S3T5_108	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_fixed_width_attestation_normalization_preserves_all_closure_offsets	shift_closure_offsets_after_digest_insertion	ORACLE_S3T5_108	MUTANT_S3T5_108_SHIFT_CLOSURE_OFFSETS_AFTER_DIGEST_INSERTION	BASELINE:S3T5_108	reused
S3T5_109	5	synthetic_gate	SyntheticMutant:r7_synthetic_v1	ABSENT	DiskImageKeychainReviewPackageTests.test_git_identity_ignores_replace_refs_and_inherited_object_or_config_environment	honor_git_replace_objects	ORACLE_S3T5_109	MUTANT_S3T5_109_HONOR_GIT_REPLACE_OBJECTS	BASELINE:S3T5_109,R7-011,R7-022	modified
S3T5_110	5	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainManifestTests.test_owner_suite_equals_exact_owner_projection_for_every_manifest_entry	truncate_owner_suite_projection	ORACLE_S3T5_110	MUTANT_S3T5_110_TRUNCATE_OWNER_SUITE_PROJECTION	BASELINE:S3T5_110	reused
S3C4_01	4	baseline_characterization	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainAuthorizationTests.test_all_eight_valid_flag_permutations_are_preserved	reject_permuted_effect_flags	ORACLE_S3C4_01	MUTANT_S3C4_01_REJECT_PERMUTED_EFFECT_FLAGS	BASELINE:S3C4_01	reused
S3T1_32	1	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainModelArchitectureTests.test_compact_efsm_rules_expand_uniquely_to_2030_pairs_and_match_python_swift_hash	omit_one_compact_efsm_rule	ORACLE_S3T1_32	MUTANT_S3T1_32_OMIT_ONE_COMPACT_EFSM_RULE	R7-001	new
S3T2_46	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftStructureTests.test_channel_loss_domains_contain_only_locally_observable_causes	accept_unobservable_channel_loss_cause	ORACLE_S3T2_46	MUTANT_S3T2_46_ACCEPT_UNOBSERVABLE_CHANNEL_LOSS_CAUSE	R7-003	new
S3T2_47	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSignalSafetyTests.test_sigpipe_is_ignored_before_every_broker_worker_write	omit_sigpipe_ignore	ORACLE_S3T2_47	MUTANT_S3T2_47_OMIT_SIGPIPE_IGNORE	R7-021	new
S3T2_48	2	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSignalSafetyTests.test_native_spawn_resets_sigpipe_and_signal_mask	inherit_ignored_sigpipe_into_native_child	ORACLE_S3T2_48	MUTANT_S3T2_48_INHERIT_IGNORED_SIGPIPE_INTO_NATIVE_CHILD	R7-021	new
S3T2_49	2	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftSignalSafetyTests.test_peer_close_matrix_returns_epipe_without_losing_native_obligation	terminate_broker_on_peer_close	ORACLE_S3T2_49	MUTANT_S3T2_49_TERMINATE_BROKER_ON_PEER_CLOSE	R7-021	new
S3T3_09	3	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_detach_argv_uses_only_attested_private_mount_path	use_numeric_device_as_detach_operand	ORACLE_S3T3_09	MUTANT_S3T3_09_USE_NUMERIC_DEVICE_AS_DETACH_OPERAND	R7-020	new
S3T3_10	3	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainSwiftProvenanceTests.test_suspended_detach_revalidation_rejects_mapping_change_before_resume	resume_detach_after_mount_identity_change	ORACLE_S3T3_10	MUTANT_S3T3_10_RESUME_DETACH_AFTER_MOUNT_IDENTITY_CHANGE	R7-020	new
S3T4_158	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_every_cs3b_type_has_one_direction_schema_header_binding_and_golden_vector	omit_cs3b_type_grammar_binding	ORACLE_S3T4_158	MUTANT_S3T4_158_OMIT_CS3B_TYPE_GRAMMAR_BINDING	R7-002	new
S3T4_159	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_every_json_frame_has_one_exact_closed_schema	omit_json_schema_field_contract	ORACLE_S3T4_159	MUTANT_S3T4_159_OMIT_JSON_SCHEMA_FIELD_CONTRACT	R7-002	new
S3T4_160	4	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_json_missing_extra_duplicate_and_nullability_matrix_rejects_without_delta	accept_json_schema_near_miss	ORACLE_S3T4_160	MUTANT_S3T4_160_ACCEPT_JSON_SCHEMA_NEAR_MISS	R7-002	new
S3T4_161	4	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_json_uint64_unicode_and_canonical_cross_language_matrix_is_exact	coerce_json_integer_or_surrogate	ORACLE_S3T4_161	MUTANT_S3T4_161_COERCE_JSON_INTEGER_OR_SURROGATE	R7-002	new
S3T4_162	4	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_terminal_json_outcome_substitution_cannot_mint_final_or_orphan_ack	accept_substituted_terminal_json_outcome	ORACLE_S3T4_162	MUTANT_S3T4_162_ACCEPT_SUBSTITUTED_TERMINAL_JSON_OUTCOME	R7-002	new
S3T4_163	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_wrong_version_before_allocation	accept_swift_cs3b_wrong_version	ORACLE_S3T4_163	MUTANT_S3T4_163_ACCEPT_SWIFT_CS3B_WRONG_VERSION	R7-014	new
S3T4_164	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_wrong_header_length_before_allocation	accept_swift_cs3b_wrong_header_length	ORACLE_S3T4_164	MUTANT_S3T4_164_ACCEPT_SWIFT_CS3B_WRONG_HEADER_LENGTH	R7-014	new
S3T4_165	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_nonzero_reserved_before_allocation	accept_swift_cs3b_nonzero_reserved	ORACLE_S3T4_165	MUTANT_S3T4_165_ACCEPT_SWIFT_CS3B_NONZERO_RESERVED	R7-014	new
S3T4_166	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_nonzero_flags_before_allocation	accept_swift_cs3b_nonzero_flags	ORACLE_S3T4_166	MUTANT_S3T4_166_ACCEPT_SWIFT_CS3B_NONZERO_FLAGS	R7-014	new
S3T4_167	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_wrong_channel_before_allocation	accept_swift_cs3b_wrong_channel	ORACLE_S3T4_167	MUTANT_S3T4_167_ACCEPT_SWIFT_CS3B_WRONG_CHANNEL	R7-014	new
S3T4_168	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_context_digest_substitution	accept_swift_cs3b_context_digest_substitution	ORACLE_S3T4_168	MUTANT_S3T4_168_ACCEPT_SWIFT_CS3B_CONTEXT_DIGEST_SUBSTITUTION	R7-014	new
S3T4_169	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_sequence_gap	accept_swift_cs3b_sequence_gap	ORACLE_S3T4_169	MUTANT_S3T4_169_ACCEPT_SWIFT_CS3B_SEQUENCE_GAP	R7-014	new
S3T4_170	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_sequence_replay	accept_swift_cs3b_sequence_replay	ORACLE_S3T4_170	MUTANT_S3T4_170_ACCEPT_SWIFT_CS3B_SEQUENCE_REPLAY	R7-014	new
S3T4_171	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_sequence_wrap	wrap_swift_cs3b_sequence	ORACLE_S3T4_171	MUTANT_S3T4_171_WRAP_SWIFT_CS3B_SEQUENCE	R7-014	new
S3T4_172	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_stream_offset_mismatch	accept_swift_cs3b_stream_offset_mismatch	ORACLE_S3T4_172	MUTANT_S3T4_172_ACCEPT_SWIFT_CS3B_STREAM_OFFSET_MISMATCH	R7-014	new
S3T4_173	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_stream_length_mismatch	accept_swift_cs3b_stream_length_mismatch	ORACLE_S3T4_173	MUTANT_S3T4_173_ACCEPT_SWIFT_CS3B_STREAM_LENGTH_MISMATCH	R7-014	new
S3T4_174	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_subject_ordinal_mismatch	accept_swift_cs3b_subject_ordinal_mismatch	ORACLE_S3T4_174	MUTANT_S3T4_174_ACCEPT_SWIFT_CS3B_SUBJECT_ORDINAL_MISMATCH	R7-014	new
S3T4_175	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_swift_cs3b_decoder_rejects_ack_binding_substitution	omit_swift_cs3b_ack_binding_comparison	ORACLE_S3T4_175	MUTANT_S3T4_175_OMIT_SWIFT_CS3B_ACK_BINDING_COMPARISON	R7-014	new
S3T4_176	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_wrong_version_before_allocation	accept_python_cs3b_wrong_version	ORACLE_S3T4_176	MUTANT_S3T4_176_ACCEPT_PYTHON_CS3B_WRONG_VERSION	R7-014	new
S3T4_177	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_wrong_header_length_before_allocation	accept_python_cs3b_wrong_header_length	ORACLE_S3T4_177	MUTANT_S3T4_177_ACCEPT_PYTHON_CS3B_WRONG_HEADER_LENGTH	R7-014	new
S3T4_178	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_nonzero_reserved_before_allocation	accept_python_cs3b_nonzero_reserved	ORACLE_S3T4_178	MUTANT_S3T4_178_ACCEPT_PYTHON_CS3B_NONZERO_RESERVED	R7-014	new
S3T4_179	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_nonzero_flags_before_allocation	accept_python_cs3b_nonzero_flags	ORACLE_S3T4_179	MUTANT_S3T4_179_ACCEPT_PYTHON_CS3B_NONZERO_FLAGS	R7-014	new
S3T4_180	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_wrong_channel_before_allocation	accept_python_cs3b_wrong_channel	ORACLE_S3T4_180	MUTANT_S3T4_180_ACCEPT_PYTHON_CS3B_WRONG_CHANNEL	R7-014	new
S3T4_181	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_context_digest_substitution	accept_python_cs3b_context_digest_substitution	ORACLE_S3T4_181	MUTANT_S3T4_181_ACCEPT_PYTHON_CS3B_CONTEXT_DIGEST_SUBSTITUTION	R7-014	new
S3T4_182	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_sequence_gap	accept_python_cs3b_sequence_gap	ORACLE_S3T4_182	MUTANT_S3T4_182_ACCEPT_PYTHON_CS3B_SEQUENCE_GAP	R7-014	new
S3T4_183	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_sequence_replay	accept_python_cs3b_sequence_replay	ORACLE_S3T4_183	MUTANT_S3T4_183_ACCEPT_PYTHON_CS3B_SEQUENCE_REPLAY	R7-014	new
S3T4_184	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_sequence_wrap	wrap_python_cs3b_sequence	ORACLE_S3T4_184	MUTANT_S3T4_184_WRAP_PYTHON_CS3B_SEQUENCE	R7-014	new
S3T4_185	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_stream_offset_mismatch	accept_python_cs3b_stream_offset_mismatch	ORACLE_S3T4_185	MUTANT_S3T4_185_ACCEPT_PYTHON_CS3B_STREAM_OFFSET_MISMATCH	R7-014	new
S3T4_186	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_stream_length_mismatch	accept_python_cs3b_stream_length_mismatch	ORACLE_S3T4_186	MUTANT_S3T4_186_ACCEPT_PYTHON_CS3B_STREAM_LENGTH_MISMATCH	R7-014	new
S3T4_187	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_subject_ordinal_mismatch	accept_python_cs3b_subject_ordinal_mismatch	ORACLE_S3T4_187	MUTANT_S3T4_187_ACCEPT_PYTHON_CS3B_SUBJECT_ORDINAL_MISMATCH	R7-014	new
S3T4_188	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_python_cs3b_decoder_rejects_ack_binding_substitution	omit_python_cs3b_ack_binding_comparison	ORACLE_S3T4_188	MUTANT_S3T4_188_OMIT_PYTHON_CS3B_ACK_BINDING_COMPARISON	R7-014	new
S3T4_189	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_admin_transport_is_one_private_anonymous_socketpair_with_exact_fd_inventory	create_path_backed_admin_socket	ORACLE_S3T4_189	MUTANT_S3T4_189_CREATE_PATH_BACKED_ADMIN_SOCKET	R7-024	new
S3T4_190	4	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_scm_rights_is_anchored_to_transfer_frame_first_byte	associate_scm_rights_with_buffered_frame	ORACLE_S3T4_190	MUTANT_S3T4_190_ASSOCIATE_SCM_RIGHTS_WITH_BUFFERED_FRAME	R7-024	new
S3T4_191	4	natural	RuntimeMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_every_rejected_ancillary_shape_closes_all_received_descriptors	leak_received_fd_on_ancillary_rejection	ORACLE_S3T4_191	MUTANT_S3T4_191_LEAK_RECEIVED_FD_ON_ANCILLARY_REJECTION	R7-024	new
S3T4_192	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_cadence_constants_and_frame_timestamps_are_exact	omit_observer_cadence_contract	ORACLE_S3T4_192	MUTANT_S3T4_192_OMIT_OBSERVER_CADENCE_CONTRACT	R7-025	new
S3T4_193	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_gap_equality_accepts_and_plus_one_latches_unavailable	accept_observer_gap_plus_one	ORACLE_S3T4_193	MUTANT_S3T4_193_ACCEPT_OBSERVER_GAP_PLUS_ONE	R7-025	new
S3T4_194	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_sleep_stall_or_late_heartbeat_cannot_restore_pass	restore_pass_after_observer_stall	ORACLE_S3T4_194	MUTANT_S3T4_194_RESTORE_PASS_AFTER_OBSERVER_STALL	R7-025	new
S3T4_195	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_seven_command_invocation_witness_recomposes_287_238_14764324	use_14764244_for_seven_command_witness	ORACLE_S3T4_195	MUTANT_S3T4_195_USE_14764244_FOR_SEVEN_COMMAND_WITNESS	R7-017	new
S3T4_196	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_serialized_byte_budgets_never_add_frame_cardinality	add_frame_slots_as_serialized_bytes	ORACLE_S3T4_196	MUTANT_S3T4_196_ADD_FRAME_SLOTS_AS_SERIALIZED_BYTES	R7-026	new
S3T4_197	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainControlTests.test_owned_allocation_caps_reserve_before_growth_and_reject_plus_one	allocate_before_owned_memory_reservation	ORACLE_S3T4_197	MUTANT_S3T4_197_ALLOCATE_BEFORE_OWNED_MEMORY_RESERVATION	R7-026	new
S3T4_198	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_open_unresolved_obligation_table_is_total_for_native_ack_orphan_lease_and_artifact	reduce_open_progress_to_native_terminal_only	ORACLE_S3T4_198	MUTANT_S3T4_198_REDUCE_OPEN_PROGRESS_TO_NATIVE_TERMINAL_ONLY	R7-004	new
S3T4_199	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainReceiptTests.test_observer_failure_alone_produces_permanent_open_unresolved_state	drop_observer_failure_open_reason	ORACLE_S3T4_199	MUTANT_S3T4_199_DROP_OBSERVER_FAILURE_OPEN_REASON	R7-004	new
S3T4_200	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_open_observation_slice_expiry_creates_no_effect_authority	mint_effect_from_open_poll_epoch	ORACLE_S3T4_200	MUTANT_S3T4_200_MINT_EFFECT_FROM_OPEN_POLL_EPOCH	R7-005	new
S3T4_201	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainDeadlineTests.test_late_close_budget_steps_equality_plus_one_and_nonresampling_are_exact	resample_late_close_deadline	ORACLE_S3T4_201	MUTANT_S3T4_201_RESAMPLE_LATE_CLOSE_DEADLINE	R7-005	new
S3T4_202	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_pid_pgid_sid_are_attested_before_ready	inherit_broker_process_group	ORACLE_S3T4_202	MUTANT_S3T4_202_INHERIT_BROKER_PROCESS_GROUP	R7-008	new
S3T4_203	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_pid_pgid_sid_are_attested_before_first_snapshot	inherit_observer_process_group	ORACLE_S3T4_203	MUTANT_S3T4_203_INHERIT_OBSERVER_PROCESS_GROUP	R7-008	new
S3T4_204	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_eof_before_first_transfer_is_open_unresolved_not_clean_close	treat_broker_ready_eof_as_clean_no_effect_close	ORACLE_S3T4_204	MUTANT_S3T4_204_TREAT_BROKER_READY_EOF_AS_CLEAN_NO_EFFECT_CLOSE	R7-015,R7-004	new
S3T4_205	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_sigkill_while_native_fixture_runs_never_mints_settlement_or_disposition	mint_disposition_after_broker_sigkill_running_child	ORACLE_S3T4_205	MUTANT_S3T4_205_MINT_DISPOSITION_AFTER_BROKER_SIGKILL_RUNNING_CHILD	R7-015,R7-004	new
S3T4_206	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_sigkill_after_fixture_exit_before_reap_preserves_waitability_unknown	treat_broker_sigkill_after_exit_as_exact_reap	ORACLE_S3T4_206	MUTANT_S3T4_206_TREAT_BROKER_SIGKILL_AFTER_EXIT_AS_EXACT_REAP	R7-015,R7-004	new
S3T4_207	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_admin_eof_while_native_fixture_runs_keeps_cleanup_and_blocks_retirement	retire_native_obligation_on_admin_eof	ORACLE_S3T4_207	MUTANT_S3T4_207_RETIRE_NATIVE_OBLIGATION_ON_ADMIN_EOF	R7-015,R7-004	new
S3T4_208	4	natural	SourceMutant	native/macos/disk_image_keychain.swift	DiskImageKeychainProcessParityTests.test_python_owner_loss_after_native_closes_before_orphan_ack_blocks_generation_reuse	reuse_generation_after_python_loss_before_orphan_ack	ORACLE_S3T4_208	MUTANT_S3T4_208_REUSE_GENERATION_AFTER_PYTHON_LOSS_BEFORE_ORPHAN_ACK	R7-015,R7-004	new
S3T4_209	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainProcessParityTests.test_broker_admin_crash_matrix_preserves_complete_fd_and_unknown_ledgers	drop_crash_fd_or_unknown_ledger_entry	ORACLE_S3T4_209	MUTANT_S3T4_209_DROP_CRASH_FD_OR_UNKNOWN_LEDGER_ENTRY	R7-015,R7-004	new
S3T5_111	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_external_approval_bootstrap_source_is_receipt_bound	drop_bootstrap_source_hash_binding	ORACLE_S3T5_111	MUTANT_S3T5_111_DROP_BOOTSTRAP_SOURCE_HASH_BINDING	R7-010	new
S3T5_112	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_approval_bundle_requires_three_distinct_closed_review_slots	accept_duplicate_review_slot	ORACLE_S3T5_112	MUTANT_S3T5_112_ACCEPT_DUPLICATE_REVIEW_SLOT	R7-010	new
S3T5_113	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_approval_bundle_rejects_reused_nonce_or_receipt_id	accept_reused_review_nonce	ORACLE_S3T5_113	MUTANT_S3T5_113_ACCEPT_REUSED_REVIEW_NONCE	R7-010	new
S3T5_114	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_approval_bundle_rejects_prior_round_replay	accept_prior_review_round	ORACLE_S3T5_114	MUTANT_S3T5_114_ACCEPT_PRIOR_REVIEW_ROUND	R7-010	new
S3T5_115	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_approval_bundle_requires_identical_candidate_tree_parent_delta_manifest_and_gate	accept_common_identity_mismatch	ORACLE_S3T5_115	MUTANT_S3T5_115_ACCEPT_COMMON_IDENTITY_MISMATCH	R7-010,R7-011	new
S3T5_116	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_gate_extraction_requires_exactly_three_zero_major_pass_receipts	extract_gate_before_three_approvals	ORACLE_S3T5_116	MUTANT_S3T5_116_EXTRACT_GATE_BEFORE_THREE_APPROVALS	R7-010	new
S3T5_117	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_identity_command_bytes_and_sha_are_both_required	accept_identity_command_sha_without_bytes	ORACLE_S3T5_117	MUTANT_S3T5_117_ACCEPT_IDENTITY_COMMAND_SHA_WITHOUT_BYTES	R7-010	new
S3T5_118	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_candidate_identity_binds_raw_commit_tree_and_single_parent	accept_unbound_commit_tree_parent	ORACLE_S3T5_118	MUTANT_S3T5_118_ACCEPT_UNBOUND_COMMIT_TREE_PARENT	R7-011	new
S3T5_119	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_documentation_delta_is_exact_two_mode_stable_paths	accept_extra_documentation_delta_path	ORACLE_S3T5_119	MUTANT_S3T5_119_ACCEPT_EXTRA_DOCUMENTATION_DELTA_PATH	R7-011	new
S3T5_120	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_whole_tree_manifest_covers_every_recursive_entry	truncate_whole_tree_manifest	ORACLE_S3T5_120	MUTANT_S3T5_120_TRUNCATE_WHOLE_TREE_MANIFEST	R7-011	new
S3T5_121	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainFinalComparisonTests.test_final_delta_is_exact_add_modify_modify_three_path_set	accept_wrong_final_delta_status	ORACLE_S3T5_121	MUTANT_S3T5_121_ACCEPT_WRONG_FINAL_DELTA_STATUS	R7-011	new
S3T5_122	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_git_identity_rejects_parent_tree_mode_and_rename_substitutions	accept_git_identity_substitution	ORACLE_S3T5_122	MUTANT_S3T5_122_ACCEPT_GIT_IDENTITY_SUBSTITUTION	R7-011	new
S3T5_123	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_parser_is_canonical_duplicate_safe_and_nonexecuting	accept_duplicate_contract_key	ORACLE_S3T5_123	MUTANT_S3T5_123_ACCEPT_DUPLICATE_CONTRACT_KEY	R7-009	new
S3T5_124	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_maps_ids_methods_mutants_and_ranges_exactly	drop_one_contract_case	ORACLE_S3T5_124	MUTANT_S3T5_124_DROP_ONE_CONTRACT_CASE	R7-009	new
S3T5_125	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_owner_projections_and_cardinalities_are_exact	misassign_one_contract_owner	ORACLE_S3T5_125	MUTANT_S3T5_125_MISASSIGN_ONE_CONTRACT_OWNER	R7-009,R7-019	new
S3T5_126	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_policies_activations_and_targets_are_exact	accept_activation_target_shape_mismatch	ORACLE_S3T5_126	MUTANT_S3T5_126_ACCEPT_ACTIVATION_TARGET_SHAPE_MISMATCH	R7-009	new
S3T5_127	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_protocol_resource_environment_and_public_tables_are_exact	change_one_protocol_resource_literal	ORACLE_S3T5_127	MUTANT_S3T5_127_CHANGE_ONE_PROTOCOL_RESOURCE_LITERAL	R7-009	new
S3T5_128	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_machine_contract_trace_efsm_and_witness_formulas_recompute	hardcode_formula_total_without_recomposition	ORACLE_S3T5_128	MUTANT_S3T5_128_HARDCODE_FORMULA_TOTAL_WITHOUT_RECOMPOSITION	R7-009,R7-017	new
S3T5_129	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_static_gate_negative_fixture_labels_are_complete_and_exact	skip_one_required_negative_fixture	ORACLE_S3T5_129	MUTANT_S3T5_129_SKIP_ONE_REQUIRED_NEGATIVE_FIXTURE	R7-009	new
S3T5_130	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_forbidden_review_path_reaches_exact_guard_before_allowlist	check_allowlist_before_forbidden_prefix	ORACLE_S3T5_130	MUTANT_S3T5_130_CHECK_ALLOWLIST_BEFORE_FORBIDDEN_PREFIX	R7-018	new
S3T5_131	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_natural_receipts_require_red_green_mutant_restored_order	accept_natural_phase_reordering	ORACLE_S3T5_131	MUTANT_S3T5_131_ACCEPT_NATURAL_PHASE_REORDERING	R7-012	new
S3T5_132	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_baseline_characterization_overlay_commit_is_deterministic	use_nondeterministic_overlay_commit_metadata	ORACLE_S3T5_132	MUTANT_S3T5_132_USE_NONDETERMINISTIC_OVERLAY_COMMIT_METADATA	R7-012	new
S3T5_133	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_baseline_overlay_production_projection_equals_implementation_base	replace_baseline_production_blob_in_overlay	ORACLE_S3T5_133	MUTANT_S3T5_133_REPLACE_BASELINE_PRODUCTION_BLOB_IN_OVERLAY	R7-012	new
S3T5_134	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_characterization_receipt_cannot_substitute_for_validation	accept_characterization_as_validation	ORACLE_S3T5_134	MUTANT_S3T5_134_ACCEPT_CHARACTERIZATION_AS_VALIDATION	R7-012	new
S3T5_135	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_synthetic_gate_receipts_never_claim_natural_red	label_synthetic_rejection_as_natural_red	ORACLE_S3T5_135	MUTANT_S3T5_135_LABEL_SYNTHETIC_REJECTION_AS_NATURAL_RED	R7-012	new
S3T5_136	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_owner_suite_expected_failures_and_exclusivity_are_prefrozen	populate_expected_sets_from_observed_output	ORACLE_S3T5_136	MUTANT_S3T5_136_POPULATE_EXPECTED_SETS_FROM_OBSERVED_OUTPUT	R7-012	new
S3T5_137	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_execution_receipt_hash_chain_rejects_ordinal_replay_and_phase_reuse	accept_replayed_execution_receipt	ORACLE_S3T5_137	MUTANT_S3T5_137_ACCEPT_REPLAYED_EXECUTION_RECEIPT	R7-012	new
S3T5_138	5	synthetic_gate	SyntheticMutant:evidence_chain_v2	ABSENT	DiskImageKeychainEvidenceProtocolTests.test_requirement_test_command_oracle_and_proof_mapping_is_total	drop_command_from_traceability_record	ORACLE_S3T5_138	MUTANT_S3T5_138_DROP_COMMAND_FROM_TRACEABILITY_RECORD	R7-012	new
S3T5_139	5	synthetic_gate	SyntheticMutant:bounded_io_v2	ABSENT	DiskImageKeychainGateIOTests.test_git_stdout_stall_hits_absolute_deadline_and_reaps	read_git_stdout_before_deadline_poll	ORACLE_S3T5_139	MUTANT_S3T5_139_READ_GIT_STDOUT_BEFORE_DEADLINE_POLL	R7-013	new
S3T5_140	5	synthetic_gate	SyntheticMutant:bounded_io_v2	ABSENT	DiskImageKeychainGateIOTests.test_git_nonblocking_output_cap_accepts_equality_and_rejects_plus_one	extend_git_output_cap_one_byte	ORACLE_S3T5_140	MUTANT_S3T5_140_EXTEND_GIT_OUTPUT_CAP_ONE_BYTE	R7-013	new
S3T5_141	5	synthetic_gate	SyntheticMutant:bounded_io_v2	ABSENT	DiskImageKeychainGateIOTests.test_git_partial_io_and_eintr_share_one_immutable_deadline	reset_git_deadline_after_eintr	ORACLE_S3T5_141	MUTANT_S3T5_141_RESET_GIT_DEADLINE_AFTER_EINTR	R7-013	new
S3T5_142	5	synthetic_gate	SyntheticMutant:toolchain_profile_v2	ABSENT	DiskImageKeychainExecutionProfileTests.test_gate_interpreter_launch_is_absolute_isolated_and_environment_closed	launch_gate_without_isolated_flags	ORACLE_S3T5_142	MUTANT_S3T5_142_LAUNCH_GATE_WITHOUT_ISOLATED_FLAGS	R7-016,R7-022	new
S3T5_143	5	synthetic_gate	SyntheticMutant:toolchain_profile_v2	ABSENT	DiskImageKeychainExecutionProfileTests.test_platform_profile_binds_os_arch_kernel_filesystem_sdk_and_libproc	omit_platform_identity_field	ORACLE_S3T5_143	MUTANT_S3T5_143_OMIT_PLATFORM_IDENTITY_FIELD	R7-016	new
S3T5_144	5	synthetic_gate	SyntheticMutant:toolchain_profile_v2	ABSENT	DiskImageKeychainExecutionProfileTests.test_final_matrix_requires_behavioral_green_and_mutants_under_python311_and_python314	accept_inventory_only_python314_receipt	ORACLE_S3T5_144	MUTANT_S3T5_144_ACCEPT_INVENTORY_ONLY_PYTHON314_RECEIPT	R7-016	new
S3T5_145	5	synthetic_gate	SyntheticMutant:toolchain_profile_v2	ABSENT	DiskImageKeychainExecutionProfileTests.test_tool_identity_mismatch_invalidates_execution_receipt	accept_changed_toolchain_identity	ORACLE_S3T5_145	MUTANT_S3T5_145_ACCEPT_CHANGED_TOOLCHAIN_IDENTITY	R7-016	new
S3T5_146	5	synthetic_gate	SyntheticMutant:toolchain_profile_v2	ABSENT	DiskImageKeychainExecutionProfileTests.test_linux_and_windows_profiles_cannot_mint_s3_native_pass	allow_unsupported_os_to_mint_pass	ORACLE_S3T5_146	MUTANT_S3T5_146_ALLOW_UNSUPPORTED_OS_TO_MINT_PASS	R7-016	new
S3T5_147	5	synthetic_gate	SyntheticMutant:bootstrap_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_doc_bootstrap_argv_environment_cwd_and_tool_receipts_are_exact	inherit_doc_bootstrap_environment	ORACLE_S3T5_147	MUTANT_S3T5_147_INHERIT_DOC_BOOTSTRAP_ENVIRONMENT	R7-022	new
S3T5_148	5	synthetic_gate	SyntheticMutant:bootstrap_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_hostile_path_pythonpath_and_sitecustomize_execute_zero_bytes	launch_doc_python_without_isolation	ORACLE_S3T5_148	MUTANT_S3T5_148_LAUNCH_DOC_PYTHON_WITHOUT_ISOLATION	R7-022	new
S3T5_149	5	synthetic_gate	SyntheticMutant:bootstrap_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_doc_git_comparison_disables_external_diff_textconv_and_config	allow_doc_diff_driver_execution	ORACLE_S3T5_149	MUTANT_S3T5_149_ALLOW_DOC_DIFF_DRIVER_EXECUTION	R7-022	new
S3T5_150	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_ondisk_git_alternates_and_unattested_commondir_are_rejected	honor_ondisk_git_alternate	ORACLE_S3T5_150	MUTANT_S3T5_150_HONOR_ONDISK_GIT_ALTERNATE	R7-011	new
S3T5_151	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_gitdir_component_symlink_permissions_and_identity_changes_reject	accept_mutable_gitdir_component	ORACLE_S3T5_151	MUTANT_S3T5_151_ACCEPT_MUTABLE_GITDIR_COMPONENT	R7-011	new
S3T5_152	5	synthetic_gate	SyntheticMutant:git_identity_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_cat_file_bytes_must_recompute_to_advertised_object_oid	accept_git_object_oid_mismatch	ORACLE_S3T5_152	MUTANT_S3T5_152_ACCEPT_GIT_OBJECT_OID_MISMATCH	R7-011	new
S3T5_153	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_review_quorum_requires_three_attributed_distinct_executions	accept_unattributed_review_receipt	ORACLE_S3T5_153	MUTANT_S3T5_153_ACCEPT_UNATTRIBUTED_REVIEW_RECEIPT	R7-010	new
S3T5_154	5	synthetic_gate	SyntheticMutant:approval_bundle_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_package_dispatch_requires_one_private_review_quorum_permit	publish_package_without_review_quorum_permit	ORACLE_S3T5_154	MUTANT_S3T5_154_PUBLISH_PACKAGE_WITHOUT_REVIEW_QUORUM_PERMIT	R7-010	new
S3T5_155	5	synthetic_gate	SyntheticMutant:package_trie_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_package_trie_rejects_extra_empty_directory	ignore_extra_package_directory	ORACLE_S3T5_155	MUTANT_S3T5_155_IGNORE_EXTRA_PACKAGE_DIRECTORY	R7-023	new
S3T5_156	5	synthetic_gate	SyntheticMutant:package_trie_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_package_enumeration_error_never_hides_members	ignore_package_enumeration_error	ORACLE_S3T5_156	MUTANT_S3T5_156_IGNORE_PACKAGE_ENUMERATION_ERROR	R7-023	new
S3T5_157	5	synthetic_gate	SyntheticMutant:package_trie_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_package_verification_is_descriptor_relative_private_and_identity_stable	reopen_package_member_by_path	ORACLE_S3T5_157	MUTANT_S3T5_157_REOPEN_PACKAGE_MEMBER_BY_PATH	R7-023	new
S3T5_158	5	synthetic_gate	SyntheticMutant:package_trie_v2	ABSENT	DiskImageKeychainReviewPackageTests.test_package_node_depth_and_directory_entry_caps_reject_plus_one	walk_package_without_node_bound	ORACLE_S3T5_158	MUTANT_S3T5_158_WALK_PACKAGE_WITHOUT_NODE_BOUND	R7-023	new
S3T5_159	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_structural_gate_rejects_superseded_literals_outside_explicit_negative_fixtures	accept_superseded_literal_outside_fixture	ORACLE_S3T5_159	MUTANT_S3T5_159_ACCEPT_SUPERSEDED_LITERAL_OUTSIDE_FIXTURE	R7-009	new
S3T5_160	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_structural_gate_cannot_be_replaced_by_token_presence_checks	replace_structural_doc_check_with_token_presence	ORACLE_S3T5_160	MUTANT_S3T5_160_REPLACE_STRUCTURAL_DOC_CHECK_WITH_TOKEN_PRESENCE	R7-009	new
S3T5_161	5	synthetic_gate	SyntheticMutant:document_contract_v2	ABSENT	DiskImageKeychainStaticContractGateTests.test_document_manifest_binds_line_counts_and_named_contract_hashes	omit_line_count_or_contract_hash_from_manifest	ORACLE_S3T5_161	MUTANT_S3T5_161_OMIT_LINE_COUNT_OR_CONTRACT_HASH_FROM_MANIFEST	R7-009	new
S3T4_210	4	natural	SourceMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_ignores_sigpipe_and_sets_so_nosigpipe_before_first_write	omit_observer_sigpipe_suppression	ORACLE_S3T4_210	MUTANT_S3T4_210_OMIT_OBSERVER_SIGPIPE_SUPPRESSION	R7-021	new
S3T4_211	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_scan_duration_equality_accepts_and_plus_one_latches_unavailable	accept_observer_scan_duration_plus_one	ORACLE_S3T4_211	MUTANT_S3T4_211_ACCEPT_OBSERVER_SCAN_DURATION_PLUS_ONE	R7-025	new
S3T4_212	4	natural	RuntimeMutant	tests/disk_image_keychain_harness.py	DiskImageKeychainObserverTests.test_observer_heartbeat_grace_equality_accepts_and_plus_one_latches_unavailable	accept_observer_heartbeat_grace_plus_one	ORACLE_S3T4_212	MUTANT_S3T4_212_ACCEPT_OBSERVER_HEARTBEAT_GRACE_PLUS_ONE	R7-025	new

```
