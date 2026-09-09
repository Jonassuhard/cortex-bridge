"""Copy reviewed resource trees into exclusively owned installer staging.

Only retained directory descriptors are used. No live publication, deletion,
legacy-path adoption or lock acquisition happens here. Failure leaves partial
staging for the install transaction to retain/reconcile, never a success record.
The caller owns both the source review and staging exclusion.
"""
import hashlib
import os
import stat

from executor import fd_ops

MAX_ENTRIES = 50000
MAX_BYTES = 1024 * 1024 * 1024
MAX_DEPTH = 64
APPLICATION_RESOURCE_TREES = ("frontend/out", "frontend/fallback", "chrome-extension", "scripts")


def _stable(before, after):
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError("Resource changed during staging")


def _private(fd):
    details = os.fstat(fd)
    if (not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o700):
        raise ValueError("Private owned staging directory required")


def _file(fd, destination=None):
    before = os.fstat(fd)
    if before.st_size > MAX_BYTES:
        raise ValueError("Resource byte limit exceeded")
    digest = hashlib.sha256()
    size = 0
    while True:
        block = os.read(fd, 65536)
        if not block:
            break
        size += len(block)
        if size > before.st_size or size > MAX_BYTES:
            raise ValueError("Resource grew during staging")
        digest.update(block)
        if destination is not None:
            remaining = memoryview(block)
            while remaining:
                written = os.write(destination, remaining)
                if written <= 0:
                    raise OSError("Resource write made no progress")
                remaining = remaining[written:]
    _stable(before, os.fstat(fd))
    if size != before.st_size:
        raise ValueError("Resource length changed")
    return size, digest.hexdigest()


def _inventory(root, *, private=False, omit_python_cache=False):
    records = []
    total = 0

    def visit(directory, prefix, depth):
        nonlocal total
        if depth > MAX_DEPTH:
            raise ValueError("Resource depth limit exceeded")
        if private:
            _private(directory)
        before = os.fstat(directory)
        for name in sorted(os.listdir(directory)):
            if omit_python_cache and (name == "__pycache__" or name.endswith((".pyc", ".pyo"))):
                continue
            if len(records) >= MAX_ENTRIES:
                raise ValueError("Resource entry limit exceeded")
            parts = fd_ops.components(name)
            if len(parts) != 1:
                raise ValueError("Invalid resource name")
            path = f"{prefix}/{name}" if prefix else name
            named = fd_ops.stat_at(directory, name)
            if stat.S_ISDIR(named.st_mode):
                child = fd_ops.open_directory_at(directory, name)
                try:
                    _stable(named, os.fstat(child))
                    records.append(dict(path=path, kind="directory", mode=0o700))
                    visit(child, path, depth + 1)
                    _stable(os.fstat(child), fd_ops.stat_at(directory, name))
                finally:
                    os.close(child)
            elif stat.S_ISREG(named.st_mode):
                child = fd_ops.open_regular_at(directory, name)
                try:
                    _stable(named, os.fstat(child))
                    mode = 0o700 if named.st_mode & 0o111 else 0o600
                    if private and (named.st_uid != os.getuid() or stat.S_IMODE(named.st_mode) != mode):
                        raise ValueError("Installed resource permissions changed")
                    size, digest = _file(child)
                    total += size
                    if total > MAX_BYTES:
                        raise ValueError("Resource tree byte limit exceeded")
                    records.append(dict(path=path, kind="file", mode=mode, size=size, sha256=digest))
                    _stable(os.fstat(child), fd_ops.stat_at(directory, name))
                finally:
                    os.close(child)
            else:
                raise ValueError("Links and special resources are forbidden")
        _stable(before, os.fstat(directory))

    visit(root, "", 0)
    return sorted(records, key=lambda record: record["path"])


def verify_resource_tree(root_fd, records):
    """Require the exact private tree, including empty directories and modes."""
    if _inventory(root_fd, private=True) != records:
        raise ValueError("Installed resource tree does not match its manifest")


def stage_resource_tree(source_fd, staging_parent_fd, name, *, omit_python_cache=False):
    """Create one new tree; return an ordered relative content manifest."""
    if len(fd_ops.components(name)) != 1:
        raise ValueError("A staging leaf name is required")
    _private(staging_parent_fd)
    records = _inventory(source_fd, omit_python_cache=omit_python_cache)
    os.mkdir(name, 0o700, dir_fd=staging_parent_fd)
    target = fd_ops.open_directory_at(staging_parent_fd, name)
    try:
        _private(target)
        for record in records:
            with fd_ops.open_parent(target, record["path"]) as (parent, leaf):
                if record["kind"] == "directory":
                    fd_ops.create_directory_at(parent, leaf)
                    continue
                source = fd_ops.open_regular_at(source_fd, record["path"])
                destination = None
                try:
                    destination = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                          | os.O_NOFOLLOW | os.O_CLOEXEC, record["mode"], dir_fd=parent)
                    os.fchmod(destination, record["mode"])
                    size, digest = _file(source, destination)
                    if (size, digest) != (record["size"], record["sha256"]):
                        raise ValueError("Resource differs from preflight manifest")
                    os.fsync(destination)
                    fd_ops.fsync_directory(parent)
                finally:
                    os.close(source)
                    if destination is not None:
                        os.close(destination)
        if _inventory(source_fd, omit_python_cache=omit_python_cache) != records:
            raise ValueError("Source tree changed during staging")
        verify_resource_tree(target, records)
        fd_ops.fsync_directory(target)
        fd_ops.fsync_directory(staging_parent_fd)
        return records
    finally:
        os.close(target)


def verify_application_resources(app_fd, manifest):
    """Verify the required resource set, not the Python/native generation."""
    _private(app_fd)
    if type(manifest) is not dict or list(manifest) != list(APPLICATION_RESOURCE_TREES):
        raise ValueError("Application resource manifest is incomplete or unordered")
    for relative, records in manifest.items():
        root = fd_ops.open_directory_at(app_fd, relative)
        try:
            verify_resource_tree(root, records)
        finally:
            os.close(root)


def stage_application_resources(source_root_fd, app_fd):
    """Assemble all required resources in a private unpublished app directory.

    Python, helpers, provenance and the atomic generation selector are managed
    by the enclosing installer. No fallback to old installed paths is allowed.
    """
    _private(app_fd)
    sources = {}
    try:
        # Discover every source and conflict before starting any copy.
        for relative in APPLICATION_RESOURCE_TREES:
            sources[relative] = fd_ops.open_directory_at(source_root_fd, relative)
            _inventory(sources[relative], omit_python_cache=relative == "scripts")
        for name in ("frontend", "chrome-extension", "scripts"):
            try:
                fd_ops.stat_at(app_fd, name)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError("Application resources already exist")
        fd_ops.create_directory_at(app_fd, "frontend")
        manifest = {}
        for relative, source in sources.items():
            with fd_ops.open_parent(app_fd, relative) as (parent, leaf):
                manifest[relative] = stage_resource_tree(source, parent, leaf, omit_python_cache=relative == "scripts")
        for relative, source in sources.items():
            if _inventory(source, omit_python_cache=relative == "scripts") != manifest[relative]:
                raise ValueError("Application sources changed during assembly")
        verify_application_resources(app_fd, manifest)
        fd_ops.fsync_directory(app_fd)
        return manifest
    finally:
        for source in sources.values():
            os.close(source)
