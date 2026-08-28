"""One location for every mutable Cortex Bridge runtime artifact."""

from __future__ import annotations

import ctypes
import errno
import os
import secrets
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CortexPaths:
    home: Path
    settings: Path
    database: Path
    iterations: Path
    chat_runs: Path
    attachments: Path
    browser_profiles: Path
    runs: Path
    pids: Path
    logs: Path
    onboarding: Path
    transport_optin: Path

    def mutable_paths(self) -> tuple[Path, ...]:
        return (
            self.home,
            self.settings,
            self.database,
            self.iterations,
            self.chat_runs,
            self.attachments,
            self.browser_profiles,
            self.runs,
            self.pids,
            self.logs,
            self.onboarding,
            self.transport_optin,
        )


def _absolute_env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path.resolve(strict=False)


def _validate_cortex_home(path: Path) -> None:
    user_home = Path.home().resolve(strict=False)
    broad_user_directories = {
        user_home,
        *(user_home / name for name in (
            "Desktop",
            "Documents",
            "Downloads",
            "Library",
            ".config",
            ".local",
        )),
    }
    system_roots = {
        Path(raw).resolve(strict=False)
        for raw in (
            "/",
            "/Applications",
            "/Library",
            "/System",
            "/Users",
            "/Volumes",
            "/bin",
            "/etc",
            "/opt",
            "/private",
            "/private/tmp",
            "/sbin",
            "/tmp",
            "/usr",
            "/var",
        )
    }
    volumes = Path("/Volumes").resolve(strict=False)
    rejected = broad_user_directories | system_roots

    def paths_same(left: Path, right: Path) -> bool:
        if left == right:
            return True
        try:
            return left.samefile(right)
        except OSError:
            return False

    def same_location(candidate: Path) -> bool:
        return paths_same(path, candidate)

    def nearest_existing_ancestor(candidate: Path) -> Path:
        current = candidate
        while not current.exists() and current != current.parent:
            current = current.parent
        return current

    root = Path(path.anchor)
    mounted_ancestor = any(
        ancestor != root
        and ancestor.exists()
        and os.path.ismount(ancestor)
        for ancestor in (path, *path.parents)
    )
    try:
        runtime_device = nearest_existing_ancestor(path).stat().st_dev
        user_device = nearest_existing_ancestor(user_home).stat().st_dev
        different_filesystem = runtime_device != user_device
    except OSError:
        different_filesystem = True

    under_volumes = any(
        paths_same(ancestor, volumes)
        for ancestor in (path, *path.parents)
    )
    if (
        any(same_location(candidate) for candidate in rejected)
        or under_volumes
        or mounted_ancestor
        or different_filesystem
    ):
        raise ValueError(
            "CORTEX_HOME must point to a dedicated directory, not a user, "
            "system, or volume root"
        )


def build_paths() -> CortexPaths:
    home = _absolute_env_path(
        "CORTEX_HOME",
        Path.home() / ".local" / "share" / "cortex-bridge",
    )
    _validate_cortex_home(home)
    return CortexPaths(
        home=home,
        settings=home / "settings.json",
        database=home / "cortex.db",
        iterations=home / "iterations.json",
        chat_runs=home / "chat-runs.json",
        attachments=home / "attachments",
        browser_profiles=home / "browser-profiles",
        runs=home / "runs",
        pids=home / "pids",
        logs=home / "logs",
        onboarding=home / "onboarding-done.json",
        transport_optin=home / "transport-optin.json",
    )


PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
RENAME_EXCL = 0x00000004
AT_FDCWD = -2
DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def _ensure_private_directory(
    path: Path,
    *,
    expected_device: int | None = None,
) -> os.stat_result:
    if path.is_symlink():
        raise RuntimeError(f"private runtime directory is unsafe: {path}")
    path.mkdir(mode=PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    descriptor, details = _open_private_directory(
        path,
        expected_device=expected_device,
    )
    os.close(descriptor)
    return details


def _open_private_directory(
    path: Path,
    *,
    expected_device: int | None = None,
    expected_inode: int | None = None,
) -> tuple[int, os.stat_result]:
    observed = path.stat(follow_symlinks=False)
    if expected_device is not None and observed.st_dev != expected_device:
        raise RuntimeError(f"private runtime directory crosses a different filesystem: {path}")
    descriptor = os.open(path, DIRECTORY_FLAGS)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.getuid()
            or (details.st_dev, details.st_ino) != (observed.st_dev, observed.st_ino)
            or (expected_device is not None and details.st_dev != expected_device)
            or (expected_inode is not None and details.st_ino != expected_inode)
        ):
            raise RuntimeError(f"private runtime directory is unsafe: {path}")
        os.fchmod(descriptor, PRIVATE_DIRECTORY_MODE)
        return descriptor, details
    except Exception:
        os.close(descriptor)
        raise


def _restrict_private_file_at(
    parent_fd: int,
    name: str,
    path: Path,
    *,
    expected_device: int,
) -> None:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if observed.st_dev != expected_device:
        raise RuntimeError(f"private runtime file crosses a different filesystem: {path}")
    if not stat.S_ISREG(observed.st_mode):
        raise RuntimeError(f"private runtime file is unsafe: {path}")
    try:
        descriptor = os.open(name, FILE_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise RuntimeError(f"private runtime file changed: {path}") from error
    try:
        opened = os.fstat(descriptor)
        if opened.st_dev != expected_device:
            raise RuntimeError(
                f"private runtime file crosses a different filesystem: {path}"
            )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
        ):
            raise RuntimeError(f"private runtime file changed: {path}")
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
    finally:
        os.close(descriptor)


def _restrict_private_file(
    path: Path,
    *,
    expected_device: int | None = None,
) -> None:
    parent_fd, parent_details = _open_private_directory(
        path.parent,
        expected_device=expected_device,
    )
    try:
        _restrict_private_file_at(
            parent_fd,
            path.name,
            path,
            expected_device=parent_details.st_dev,
        )
    finally:
        os.close(parent_fd)


def _iter_same_device_tree(
    root: Path,
    *,
    label: str,
    expected_device: int | None = None,
):
    root_details = root.stat(follow_symlinks=False)
    if not stat.S_ISDIR(root_details.st_mode):
        raise RuntimeError(f"{label} root is unsafe: {root}")
    root_device = expected_device if expected_device is not None else root_details.st_dev
    if root_details.st_dev != root_device:
        raise RuntimeError(f"{label} crosses a different filesystem: {root}")

    def visit(directory: Path):
        for child in sorted(directory.iterdir()):
            details = child.stat(follow_symlinks=False)
            if details.st_dev != root_device:
                raise RuntimeError(
                    f"{label} crosses a different filesystem: {child}"
                )
            yield child, details
            if stat.S_ISDIR(details.st_mode):
                yield from visit(child)

    yield from visit(root)


def _restrict_private_tree(root: Path, *, expected_device: int | None = None) -> None:
    observed_root = root.stat(follow_symlinks=False)
    root_device = expected_device if expected_device is not None else observed_root.st_dev
    if observed_root.st_dev != root_device:
        raise RuntimeError(f"private runtime tree crosses a different filesystem: {root}")
    root_fd = os.open(root, DIRECTORY_FLAGS)

    def visit(directory_fd: int, directory: Path) -> None:
        with os.scandir(directory_fd) as scanner:
            entries = sorted(scanner, key=lambda item: item.name)
        for entry in entries:
            child = directory / entry.name
            try:
                observed = child.stat(follow_symlinks=False)
            except OSError as error:
                raise RuntimeError(f"private runtime tree changed: {child}") from error
            if observed.st_dev != root_device:
                raise RuntimeError(
                    f"private runtime tree crosses a different filesystem: {child}"
                )
            if stat.S_ISLNK(observed.st_mode):
                continue
            flags = DIRECTORY_FLAGS if stat.S_ISDIR(observed.st_mode) else FILE_FLAGS
            try:
                child_fd = os.open(entry.name, flags, dir_fd=directory_fd)
            except OSError as error:
                raise RuntimeError(f"private runtime tree changed: {child}") from error
            try:
                opened = os.fstat(child_fd)
                if (
                    opened.st_dev != root_device
                    or (opened.st_dev, opened.st_ino)
                    != (observed.st_dev, observed.st_ino)
                ):
                    raise RuntimeError(f"private runtime tree changed: {child}")
                if stat.S_ISDIR(observed.st_mode):
                    if not stat.S_ISDIR(opened.st_mode):
                        raise RuntimeError(f"private runtime tree changed: {child}")
                    os.fchmod(child_fd, PRIVATE_DIRECTORY_MODE)
                    visit(child_fd, child)
                elif stat.S_ISREG(observed.st_mode):
                    if not stat.S_ISREG(opened.st_mode):
                        raise RuntimeError(f"private runtime tree changed: {child}")
                    os.fchmod(child_fd, PRIVATE_FILE_MODE)
            finally:
                os.close(child_fd)

    try:
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_dev != root_device
            or (opened_root.st_dev, opened_root.st_ino)
            != (observed_root.st_dev, observed_root.st_ino)
        ):
            raise RuntimeError(f"private runtime tree changed: {root}")
        visit(root_fd, root)
    finally:
        os.close(root_fd)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_private_file_exclusive(
    source: Path,
    destination: Path,
    *,
    expected_source_device: int | None = None,
    expected_source_inode: int | None = None,
    source_fd: int | None = None,
    expected_destination_device: int | None = None,
    expected_destination_inode: int | None = None,
    destination_parent_fd: int | None = None,
) -> None:
    """Copy completely to a private inode, then publish without overwriting."""
    owns_destination_fd = destination_parent_fd is None
    if destination_parent_fd is None:
        _ensure_private_directory(
            destination.parent,
            expected_device=expected_destination_device,
        )
        destination_parent_fd, destination_details = _open_private_directory(
            destination.parent,
            expected_device=expected_destination_device,
            expected_inode=expected_destination_inode,
        )
    else:
        destination_details = os.fstat(destination_parent_fd)
        if (
            not stat.S_ISDIR(destination_details.st_mode)
            or (
                expected_destination_device is not None
                and destination_details.st_dev != expected_destination_device
            )
            or (
                expected_destination_inode is not None
                and destination_details.st_ino != expected_destination_inode
            )
        ):
            raise RuntimeError(
                f"legacy migration destination changed: {destination.parent}"
            )
    owns_source_fd = source_fd is None
    if source_fd is None:
        source_fd = os.open(source, FILE_FLAGS)
    source_details = os.fstat(source_fd)
    if (
        not stat.S_ISREG(source_details.st_mode)
        or (
            expected_source_device is not None
            and source_details.st_dev != expected_source_device
        )
        or (
            expected_source_inode is not None
            and source_details.st_ino != expected_source_inode
        )
    ):
        if owns_source_fd:
            os.close(source_fd)
        if owns_destination_fd:
            os.close(destination_parent_fd)
        raise RuntimeError(f"legacy migration source changed: {source}")
    temporary_name = (
        f".{destination.name}.migration-{os.getpid()}-{secrets.token_hex(8)}"
    )
    temporary_fd = None
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            PRIVATE_FILE_MODE,
            dir_fd=destination_parent_fd,
        )
        temporary_details = os.fstat(temporary_fd)
        if (
            not stat.S_ISREG(temporary_details.st_mode)
            or temporary_details.st_dev != destination_details.st_dev
        ):
            raise RuntimeError(
                f"legacy migration destination changed: {destination.parent}"
            )
        with (
            os.fdopen(os.dup(source_fd), "rb") as source_stream,
            os.fdopen(os.dup(temporary_fd), "wb") as destination_stream,
        ):
            shutil.copyfileobj(source_stream, destination_stream)
            destination_stream.flush()
        after = os.fstat(source_fd)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) != (
            source_details.st_dev,
            source_details.st_ino,
            source_details.st_size,
            source_details.st_mtime_ns,
        ):
            raise RuntimeError(f"legacy migration source changed: {source}")
        os.fchmod(temporary_fd, PRIVATE_FILE_MODE)
        os.fsync(temporary_fd)
        current_temporary = os.stat(
            temporary_name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(current_temporary.st_mode)
            or (current_temporary.st_dev, current_temporary.st_ino)
            != (temporary_details.st_dev, temporary_details.st_ino)
        ):
            raise RuntimeError(f"legacy migration destination changed: {destination}")
        destination_created = False
        try:
            os.link(
                temporary_name,
                destination.name,
                src_dir_fd=destination_parent_fd,
                dst_dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
            destination_created = True
        except FileExistsError as exc:
            raise RuntimeError(
                f"legacy migration destination appeared concurrently: {destination}"
            ) from exc
        published = os.stat(
            destination.name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        current_temporary = os.stat(
            temporary_name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(published.st_mode)
            or (published.st_dev, published.st_ino)
            != (temporary_details.st_dev, temporary_details.st_ino)
            or (current_temporary.st_dev, current_temporary.st_ino)
            != (temporary_details.st_dev, temporary_details.st_ino)
        ):
            if destination_created:
                try:
                    os.unlink(destination.name, dir_fd=destination_parent_fd)
                except FileNotFoundError:
                    pass
            raise RuntimeError(f"legacy migration destination changed: {destination}")
        os.fsync(destination_parent_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if owns_source_fd:
            os.close(source_fd)
        try:
            os.unlink(temporary_name, dir_fd=destination_parent_fd)
        except FileNotFoundError:
            pass
        if owns_destination_fd:
            os.close(destination_parent_fd)


def _rename_directory_exclusive(source: Path, destination: Path) -> None:
    if sys.platform != "darwin":
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), destination)
        os.rename(source, destination)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = libc.renameatx_np
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_EXCL,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)


def _rename_directory_exclusive_at(
    parent_fd: int,
    source_name: str,
    destination_name: str,
) -> None:
    if sys.platform != "darwin":
        try:
            os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(
                errno.EEXIST,
                os.strerror(errno.EEXIST),
                destination_name,
            )
        os.rename(
            source_name,
            destination_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameatx_np = libc.renameatx_np
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        parent_fd,
        os.fsencode(source_name),
        parent_fd,
        os.fsencode(destination_name),
        RENAME_EXCL,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination_name)
    raise OSError(error, os.strerror(error), destination_name)


def _copy_private_directory_exclusive(
    source: Path,
    destination: Path,
    *,
    expected_source_device: int,
    expected_source_inode: int,
    expected_destination_device: int,
    expected_destination_inode: int | None = None,
    source_fd: int | None = None,
    destination_parent_fd: int | None = None,
) -> bool:
    owns_destination_fd = destination_parent_fd is None
    if destination_parent_fd is None:
        _ensure_private_directory(
            destination.parent,
            expected_device=expected_destination_device,
        )
        destination_parent_fd, destination_details = _open_private_directory(
            destination.parent,
            expected_device=expected_destination_device,
            expected_inode=expected_destination_inode,
        )
    else:
        destination_details = os.fstat(destination_parent_fd)
        if (
            not stat.S_ISDIR(destination_details.st_mode)
            or destination_details.st_dev != expected_destination_device
            or (
                expected_destination_inode is not None
                and destination_details.st_ino != expected_destination_inode
            )
        ):
            raise RuntimeError(
                f"legacy migration destination changed: {destination.parent}"
            )
    staging_name = (
        f".{destination.name}.migration-{os.getpid()}-{secrets.token_hex(8)}"
    )
    staging_fd = None
    try:
        os.mkdir(
            staging_name,
            PRIVATE_DIRECTORY_MODE,
            dir_fd=destination_parent_fd,
        )
        created_staging = os.stat(
            staging_name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(created_staging.st_mode)
            or created_staging.st_uid != os.getuid()
            or created_staging.st_dev != destination_details.st_dev
        ):
            raise RuntimeError(
                f"legacy migration destination changed: {destination.parent}"
            )
        staging_fd = os.open(
            staging_name,
            DIRECTORY_FLAGS,
            dir_fd=destination_parent_fd,
        )
        staging_details = os.fstat(staging_fd)
        if (
            not stat.S_ISDIR(staging_details.st_mode)
            or staging_details.st_uid != os.getuid()
            or staging_details.st_dev != destination_details.st_dev
            or (staging_details.st_dev, staging_details.st_ino)
            != (created_staging.st_dev, created_staging.st_ino)
        ):
            raise RuntimeError(
                f"legacy migration destination changed: {destination.parent}"
            )
        os.fchmod(staging_fd, PRIVATE_DIRECTORY_MODE)
        copied = _copy_directory_without_symlinks(
            source,
            destination.parent / staging_name,
            expected_source_device=expected_source_device,
            expected_source_inode=expected_source_inode,
            expected_destination_device=staging_details.st_dev,
            expected_destination_inode=staging_details.st_ino,
            source_root_fd=source_fd,
            destination_root_fd=staging_fd,
        )
        os.fsync(staging_fd)
        current_staging = os.stat(
            staging_name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current_staging.st_mode)
            or (current_staging.st_dev, current_staging.st_ino)
            != (staging_details.st_dev, staging_details.st_ino)
        ):
            raise RuntimeError(f"legacy migration destination changed: {destination}")
        _rename_directory_exclusive_at(
            destination_parent_fd,
            staging_name,
            destination.name,
        )
        current_destination = os.stat(
            destination.name,
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current_destination.st_mode)
            or (current_destination.st_dev, current_destination.st_ino)
            != (staging_details.st_dev, staging_details.st_ino)
        ):
            raise RuntimeError(f"legacy migration destination changed: {destination}")
        os.fsync(destination_parent_fd)
        return copied
    finally:
        if staging_fd is not None:
            os.close(staging_fd)
        if owns_destination_fd:
            os.close(destination_parent_fd)


def ensure_layout(paths: CortexPaths | None = None) -> CortexPaths:
    paths = paths or build_paths()
    home_details = _ensure_private_directory(paths.home)
    for directory in (
        paths.attachments,
        paths.browser_profiles,
        paths.runs,
        paths.pids,
        paths.logs,
    ):
        _ensure_private_directory(directory, expected_device=home_details.st_dev)
    home_fd, opened_home = _open_private_directory(
        paths.home,
        expected_device=home_details.st_dev,
        expected_inode=home_details.st_ino,
    )
    try:
        private_files = {
            paths.settings.name: paths.settings,
            paths.database.name: paths.database,
            paths.iterations.name: paths.iterations,
            paths.chat_runs.name: paths.chat_runs,
            paths.onboarding.name: paths.onboarding,
            paths.transport_optin.name: paths.transport_optin,
        }
        with os.scandir(home_fd) as scanner:
            for entry in scanner:
                if entry.name.startswith(f"{paths.database.name}-"):
                    private_files[entry.name] = paths.home / entry.name
        for name, private_file in private_files.items():
            _restrict_private_file_at(
                home_fd,
                name,
                private_file,
                expected_device=opened_home.st_dev,
            )
    finally:
        os.close(home_fd)
    for private_tree in (
        paths.attachments,
        paths.browser_profiles,
        paths.runs,
        paths.pids,
        paths.logs,
    ):
        _restrict_private_tree(private_tree, expected_device=home_details.st_dev)
    return paths


def _copy_directory_without_symlinks(
    source: Path,
    destination: Path,
    *,
    expected_source_device: int,
    expected_source_inode: int,
    expected_destination_device: int,
    expected_destination_inode: int,
    source_root_fd: int | None = None,
    destination_root_fd: int | None = None,
) -> bool:
    copied = False
    observed_root = source.stat(follow_symlinks=False)
    owns_source_fd = source_root_fd is None
    if source_root_fd is None:
        source_root_fd = os.open(source, DIRECTORY_FLAGS)
    owns_destination_fd = destination_root_fd is None
    if destination_root_fd is None:
        destination_root_fd, _destination_details = _open_private_directory(
            destination,
            expected_device=expected_destination_device,
            expected_inode=expected_destination_inode,
        )

    def visit(
        source_fd: int,
        source_directory: Path,
        destination_fd: int,
        destination_directory: Path,
    ) -> None:
        nonlocal copied
        with os.scandir(source_fd) as scanner:
            entries = sorted(scanner, key=lambda item: item.name)
        for entry in entries:
            child = source_directory / entry.name
            details = child.stat(follow_symlinks=False)
            if details.st_dev != expected_source_device:
                raise RuntimeError(
                    f"legacy migration source tree crosses a different filesystem: {child}"
                )
            if stat.S_ISLNK(details.st_mode):
                continue
            target = destination_directory / entry.name
            flags = DIRECTORY_FLAGS if stat.S_ISDIR(details.st_mode) else FILE_FLAGS
            try:
                child_fd = os.open(entry.name, flags, dir_fd=source_fd)
            except OSError as error:
                raise RuntimeError(f"legacy migration source changed: {child}") from error
            try:
                opened = os.fstat(child_fd)
                if (
                    opened.st_dev != expected_source_device
                    or (opened.st_dev, opened.st_ino)
                    != (details.st_dev, details.st_ino)
                ):
                    raise RuntimeError(f"legacy migration source changed: {child}")
                if stat.S_ISDIR(details.st_mode):
                    if not stat.S_ISDIR(opened.st_mode):
                        raise RuntimeError(f"legacy migration source changed: {child}")
                    os.mkdir(
                        entry.name,
                        PRIVATE_DIRECTORY_MODE,
                        dir_fd=destination_fd,
                    )
                    created_destination = os.stat(
                        entry.name,
                        dir_fd=destination_fd,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(created_destination.st_mode)
                        or created_destination.st_uid != os.getuid()
                        or created_destination.st_dev != expected_destination_device
                    ):
                        raise RuntimeError(
                            f"legacy migration destination changed: {target}"
                        )
                    destination_child_fd = os.open(
                        entry.name,
                        DIRECTORY_FLAGS,
                        dir_fd=destination_fd,
                    )
                    try:
                        destination_child_details = os.fstat(destination_child_fd)
                        if (
                            not stat.S_ISDIR(destination_child_details.st_mode)
                            or destination_child_details.st_uid != os.getuid()
                            or destination_child_details.st_dev
                            != expected_destination_device
                            or (
                                destination_child_details.st_dev,
                                destination_child_details.st_ino,
                            )
                            != (
                                created_destination.st_dev,
                                created_destination.st_ino,
                            )
                        ):
                            raise RuntimeError(
                                f"legacy migration destination changed: {target}"
                            )
                        os.fchmod(destination_child_fd, PRIVATE_DIRECTORY_MODE)
                        visit(
                            child_fd,
                            child,
                            destination_child_fd,
                            target,
                        )
                        os.fsync(destination_child_fd)
                    finally:
                        os.close(destination_child_fd)
                elif stat.S_ISREG(details.st_mode):
                    if not stat.S_ISREG(opened.st_mode):
                        raise RuntimeError(f"legacy migration source changed: {child}")
                    _copy_private_file_exclusive(
                        child,
                        target,
                        expected_source_device=expected_source_device,
                        expected_source_inode=details.st_ino,
                        source_fd=child_fd,
                        expected_destination_device=expected_destination_device,
                        expected_destination_inode=os.fstat(destination_fd).st_ino,
                        destination_parent_fd=destination_fd,
                    )
                    copied = True
            finally:
                os.close(child_fd)

    try:
        opened_root = os.fstat(source_root_fd)
        opened_destination = os.fstat(destination_root_fd)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_dev != expected_source_device
            or opened_root.st_ino != expected_source_inode
            or (opened_root.st_dev, opened_root.st_ino)
            != (observed_root.st_dev, observed_root.st_ino)
        ):
            raise RuntimeError(f"legacy migration source changed: {source}")
        if (
            not stat.S_ISDIR(opened_destination.st_mode)
            or opened_destination.st_dev != expected_destination_device
            or opened_destination.st_ino != expected_destination_inode
        ):
            raise RuntimeError(f"legacy migration destination changed: {destination}")
        visit(source_root_fd, source, destination_root_fd, destination)
        os.fsync(destination_root_fd)
    finally:
        if owns_source_fd:
            os.close(source_root_fd)
        if owns_destination_fd:
            os.close(destination_root_fd)
    return copied


def migrate_legacy_state(legacy_data: Path, paths: CortexPaths | None = None) -> list[Path]:
    """Copy missing legacy state into CORTEX_HOME; never delete or overwrite."""
    paths = paths or build_paths()
    mapping = {
        "settings.json": paths.settings,
        "cortex.db": paths.database,
        "iterations.json": paths.iterations,
        "chat-runs.json": paths.chat_runs,
        "onboarding-done.json": paths.onboarding,
        "transport-optin.json": paths.transport_optin,
        "attachments": paths.attachments,
        "browser-profiles": paths.browser_profiles,
        "runs": paths.runs,
    }
    migrated: list[Path] = []
    try:
        legacy_details = legacy_data.stat(follow_symlinks=False)
    except FileNotFoundError:
        ensure_layout(paths)
        return migrated
    if not stat.S_ISDIR(legacy_details.st_mode):
        ensure_layout(paths)
        return migrated
    legacy_device = legacy_details.st_dev
    legacy_fd = os.open(legacy_data, DIRECTORY_FLAGS)
    opened_legacy = os.fstat(legacy_fd)
    if (
        not stat.S_ISDIR(opened_legacy.st_mode)
        or (opened_legacy.st_dev, opened_legacy.st_ino)
        != (legacy_details.st_dev, legacy_details.st_ino)
    ):
        os.close(legacy_fd)
        raise RuntimeError(f"legacy migration source changed: {legacy_data}")
    home_details = _ensure_private_directory(paths.home)
    home_fd, opened_home = _open_private_directory(
        paths.home,
        expected_device=home_details.st_dev,
        expected_inode=home_details.st_ino,
    )
    try:
        for name, destination in mapping.items():
            try:
                os.stat(
                    destination.name,
                    dir_fd=home_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                continue
            source = legacy_data / name
            try:
                source_details = source.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(source_details.st_mode):
                continue
            if source_details.st_dev != legacy_device:
                raise RuntimeError(
                    f"legacy migration crosses a different filesystem: {source}"
                )
            flags = (
                DIRECTORY_FLAGS
                if stat.S_ISDIR(source_details.st_mode)
                else FILE_FLAGS
            )
            try:
                source_fd = os.open(name, flags, dir_fd=legacy_fd)
            except OSError as error:
                raise RuntimeError(
                    f"legacy migration source changed: {source}"
                ) from error
            try:
                opened_source = os.fstat(source_fd)
                if (
                    opened_source.st_dev != legacy_device
                    or (opened_source.st_dev, opened_source.st_ino)
                    != (source_details.st_dev, source_details.st_ino)
                ):
                    raise RuntimeError(
                        f"legacy migration source changed: {source}"
                    )
                if stat.S_ISDIR(source_details.st_mode):
                    if not stat.S_ISDIR(opened_source.st_mode):
                        raise RuntimeError(
                            f"legacy migration source changed: {source}"
                        )
                    if _copy_private_directory_exclusive(
                        source,
                        destination,
                        expected_source_device=legacy_device,
                        expected_source_inode=source_details.st_ino,
                        expected_destination_device=opened_home.st_dev,
                        expected_destination_inode=opened_home.st_ino,
                        source_fd=source_fd,
                        destination_parent_fd=home_fd,
                    ):
                        migrated.append(destination)
                elif stat.S_ISREG(source_details.st_mode):
                    if not stat.S_ISREG(opened_source.st_mode):
                        raise RuntimeError(
                            f"legacy migration source changed: {source}"
                        )
                    _copy_private_file_exclusive(
                        source,
                        destination,
                        expected_source_device=legacy_device,
                        expected_source_inode=source_details.st_ino,
                        source_fd=source_fd,
                        expected_destination_device=opened_home.st_dev,
                        expected_destination_inode=opened_home.st_ino,
                        destination_parent_fd=home_fd,
                    )
                    migrated.append(destination)
            finally:
                os.close(source_fd)
    finally:
        os.close(home_fd)
        os.close(legacy_fd)
    ensure_layout(paths)
    return migrated


def model_directory() -> Path:
    if "CORTEX_MODEL_DIR" in os.environ:
        return _absolute_env_path("CORTEX_MODEL_DIR", Path.home() / ".ollama" / "models")
    if "CORTEX_STORAGE_PATH" in os.environ:
        return _absolute_env_path("CORTEX_STORAGE_PATH", Path.home() / ".ollama" / "models")
    return (Path.home() / ".ollama" / "models").resolve(strict=False)
