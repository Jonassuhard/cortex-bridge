"""Consent-bound installation of a local wheel into a private generation.

Called with the install lock held. Host Python and Apple's tools are prerequisites;
this installs locked Python dependencies, not a new system interpreter.
"""
import os
import json
from pathlib import Path
import stat
import subprocess
import sys
from uuid import UUID, uuid4
import zipfile
import bootstrap_install

from executor import fd_ops
from generation_metadata import build_generation_metadata
from generation_publication import publish_generation, recover_generation_publication
from install_resource_tree import (
    APPLICATION_RESOURCE_TREES, _inventory, _file, stage_application_resources, stage_resource_tree,
)
from process_helper_build import build_native_helper_bundle

STAGING = ".generation-install-staging"


def _read_owned_metadata(path):
    from installed_storage_runtime import _read_fd_bytes
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("Unsafe installed metadata")
        return _read_fd_bytes(fd)
    finally:
        os.close(fd)


def _verified_selected_generation(home):
    from generation_metadata import GenerationMetadata, verify_generation_metadata
    from generation_publication import _private_directory, _validate_recovery_identity
    from installed_storage_runtime import _reject_duplicate_keys
    home = Path(home)
    if home != home.resolve(strict=True):
        raise ValueError("Canonical installation home required")
    _private_directory(home)
    selector_bytes = _read_owned_metadata(home / "current-generation.json")
    selected = json.loads(selector_bytes, object_pairs_hook=_reject_duplicate_keys)
    _validate_recovery_identity(selected, {"schema_version", "generation_id", "generation_record_sha256"})
    parent = home / "installed-generations"
    generation = parent / selected["generation_id"]
    _private_directory(parent)
    _private_directory(generation)
    metadata = GenerationMetadata(UUID(selected["generation_id"]),
                                  _read_owned_metadata(generation / "owned-manifest.json"),
                                  _read_owned_metadata(generation / "generation-record.json"), selector_bytes)
    verify_generation_metadata(generation, metadata)
    return generation, metadata


def doctor_locked(home):
    """Inspect the selected installation, never the checkout or a running provider.

    Caller retains the install-shared lock. This does not import selected Python,
    request accessibility, start a broker or probe the user's authenticated tabs.
    """
    from installer import current_version
    home = Path(home)
    checks = []
    identifier = None
    extension_path = None
    valid = False
    try:
        generation, metadata = _verified_selected_generation(home)
        identifier = str(metadata.generation_id)
        bootstrap_install.inspect(home, {
            "source": _snapshot(home / "bootstrap" / Path(bootstrap_install.SOURCE).name),
            "profile": _snapshot(home / "bootstrap" / Path(bootstrap_install.PROFILE).name),
        })
        recovery = recover_generation_publication(home)
        if recovery["status"] == "pending_reconciliation":
            raise ValueError("GENERATION_PUBLICATION_PENDING_RECONCILIATION")
        extension_path = generation / "app/chrome-extension"
        valid = True
        detail = "Selected generation and native bootstrap verified"
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, subprocess.SubprocessError) as error:
        detail = str(error)
    checks.append(dict(id="generation_integrity", label="Intégrité de la génération installée",
                       status="pass" if valid else "fail", required=True, detail=detail,
                       hint="" if valid else "Ne remplace pas les fichiers manuellement ; conserve les preuves et relis le plan de réparation."))
    checks.append(dict(id="chrome_extension", label="Extension de la génération sélectionnée",
                       status="pass" if valid else "fail", required=True,
                       detail="Installed files verified; Chrome pairing not tested" if valid else "Not verified",
                       path=str(extension_path) if extension_path else None, hint=""))
    configured = (home / "storage-bootstrap.json").exists() or (home / "storage-bootstrap.json").is_symlink()
    checks.append(dict(id="external_storage", label="Admission du stockage chiffré",
                       status="warning" if configured else "pass", required=configured,
                       detail="Requires broker-backed admission verification" if configured else "Not configured",
                       hint=""))
    checks.append(dict(id="runtime_connection", label="Connexion réelle Chrome et moteur",
                       status="warning", required=False, detail="Not tested by installation integrity check", hint=""))
    return dict(schema_version=1, version=current_version(), installation_mode="generation",
                generation_id=identifier, cortex_home=str(home),
                local_url=f"http://127.0.0.1:{int(os.environ.get('PORT', '8420'))}",
                ok=all(c["status"] == "pass" for c in checks if c["required"]),
                modes=dict(deterministic=valid, chrome_extension=valid, macos_native_send=False,
                           ollama=False, playwright_development=False, webbridge=False), checks=checks)


def _snapshot(path):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError("Canonical input path required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Regular input file required")
        size, sha = _file(fd)
        return {"path": str(path), "size": size, "sha256": sha}
    finally:
        os.close(fd)


def _selector(home):
    path = home / "current-generation.json"
    if not path.exists() and not path.is_symlink():
        return None
    return _snapshot(path)


def build_plan(wheel, *, bootstrap_migration=None):
    from installer import ROOT, NATIVE_HELPERS, _hashed, build_paths
    if sys.platform != "darwin":
        raise RuntimeError("GENERATION_INSTALL_REQUIRES_MACOS")
    if bootstrap_migration not in (None, "missing-v1"):
        raise ValueError("Unsupported bootstrap migration")
    wheel = Path(wheel).absolute()
    wheel_snapshot = _snapshot(wheel)
    with zipfile.ZipFile(wheel) as archive:
        if "server.py" not in archive.namelist() or not wheel.name.startswith("cortex_bridge-"):
            raise ValueError("A Cortex Bridge wheel is required")
    source = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    resources = {}
    try:
        for relative in APPLICATION_RESOURCE_TREES:
            fd = fd_ops.open_directory_at(source, relative)
            try:
                resources[relative] = _inventory(fd, omit_python_cache=relative == "scripts")
            finally:
                os.close(fd)
    finally:
        os.close(source)
    inputs = {str(p.relative_to(ROOT)): _snapshot(p) for spec in NATIVE_HELPERS
              for p in (spec.source, spec.build_profile)}
    target = build_paths().home
    bootstrap_inputs = {"source": _snapshot(ROOT / bootstrap_install.SOURCE),
                        "profile": _snapshot(ROOT / bootstrap_install.PROFILE)}
    bootstrap_before = bootstrap_install.inspect(target, bootstrap_inputs)
    previous_generation = None
    if bootstrap_migration == "missing-v1":
        if bootstrap_before is not None:
            raise ValueError("Missing-bootstrap migration requires an absent bootstrap")
        previous, metadata = _verified_selected_generation(target)
        previous_generation = {
            "generation_id": str(metadata.generation_id),
            "selector": _snapshot(target / "current-generation.json"),
            "manifest": _snapshot(previous / "owned-manifest.json"),
            "record": _snapshot(previous / "generation-record.json"),
        }
    return _hashed({
        "schema_version": 1, "action": "install", "installation_mode": "generation",
        "target": str(target), "wheel": wheel_snapshot,
        "interpreter": _snapshot(Path(sys.executable).resolve()),
        "requirements": _snapshot(ROOT / "requirements.lock"),
        "native_inputs": inputs, "resources": resources, "selector_before": _selector(target),
        "bootstrap_inputs": bootstrap_inputs,
        "bootstrap_before": bootstrap_before,
        "bootstrap_migration": bootstrap_migration,
        "previous_generation": previous_generation,
        "steps": (["Verify and preserve the previous complete generation; install its missing ABI-v1 launcher"]
                  if bootstrap_migration else []) + ["Install hash-locked dependencies from https://pypi.org/simple",
                  "Install the reviewed local wheel", "Stage UI, extension and scripts",
                  "Build and sign four native helpers", "Verify imports and generation metadata",
                  "Install or verify the immutable ABI-v1 native bootstrap",
                  "Atomically publish the selected generation"],
        "failure_policy": "Retain failed staging and previous generations for reconciliation",
        "runtime_start": False,
    })


def _copy_checked(snapshot, destination, mode=0o600):
    source = os.open(snapshot["path"], os.O_RDONLY | os.O_NOFOLLOW)
    target = None
    try:
        target = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        os.fchmod(target, mode)
        size, sha = _file(source, target)
        if (size, sha) != (snapshot["size"], snapshot["sha256"]):
            raise ValueError("Approved input changed during copy")
        os.fsync(target)
    finally:
        os.close(source)
        if target is not None:
            os.close(target)


def _assert_update_quiescent(home, lock_set):
    """Read existing storage evidence without recovering effects during install."""
    from generation_publication import _private_directory
    from installed_storage_runtime import _reject_duplicate_keys
    from storage_broker import LedgerState, _record_from_dict
    lock_set.assert_active(home=home, required_install_mode="exclusive", required_storage_mode="exclusive")
    if lock_set.admission_mode != "exclusive":
        raise RuntimeError("STORAGE_ADMISSION_EXCLUSIVE_REQUIRED")
    directory = home / "storage"
    if not directory.exists() and not directory.is_symlink():
        return
    _private_directory(directory)
    ledger = directory / "storage-workflows.jsonl"
    try:
        raw = _read_owned_metadata(ledger)
    except FileNotFoundError:
        return
    seen = set()
    for line in raw.splitlines():
        if not line:
            continue
        record = _record_from_dict(json.loads(line, object_pairs_hook=_reject_duplicate_keys))
        identity = (record.workflow_id, record.generation)
        if identity in seen:
            raise ValueError("Duplicate storage workflow record")
        seen.add(identity)
        if record.state not in (LedgerState.CLOSED_SUCCESS, LedgerState.CLOSED_FAILURE):
            raise RuntimeError("STORAGE_WORKFLOWS_OPEN")
        if record.reconciliation_required:
            # No canonical consumer of durable reconciliation is wired yet.
            # A CLOSED effect is not a reconciliation proof.
            raise RuntimeError("STORAGE_RECONCILIATION_REQUIRED")
        if record.started_monotonic_ns is not None and not (
                record.child_reaped is True and record.group_absent is True
                and record.native_cleanup_proven is True):
            raise RuntimeError("STORAGE_CLEANUP_UNPROVEN")


def apply_locked(plan, *, lock_set):
    from installer import ROOT, STAGING_NAME, build_paths
    home = build_paths().home
    _assert_update_quiescent(home, lock_set)
    if plan != build_plan(plan["wheel"]["path"], bootstrap_migration=plan.get("bootstrap_migration")):
        raise PermissionError("Generation installation inputs changed after approval")
    recovery = recover_generation_publication(home)
    if recovery["status"] == "pending_reconciliation":
        raise RuntimeError("GENERATION_PUBLICATION_PENDING_RECONCILIATION")
    legacy_staging = home / STAGING_NAME
    if legacy_staging.exists() or legacy_staging.is_symlink():
        raise RuntimeError("LEGACY_INSTALL_PENDING_RECONCILIATION")
    if (plan["selector_before"] is not None and plan["bootstrap_before"] is None
            and plan.get("bootstrap_migration") != "missing-v1"):
        raise RuntimeError("BOOTSTRAP_MIGRATION_REQUIRED")
    staging = home / STAGING
    staging.mkdir(mode=0o700)  # Never adopt an interrupted staging directory.
    try:
        wheel = staging / Path(plan["wheel"]["path"]).name
        lock = staging / "requirements.lock"
        _copy_checked(plan["wheel"], wheel)
        _copy_checked(plan["requirements"], lock)
        if plan["bootstrap_before"] is None:
            bootstrap_install.stage(staging, plan["bootstrap_inputs"])
        environment = {"PATH": os.defpath, "HOME": str(staging), "LANG": "C", "LC_ALL": "C",
                       "PIP_CONFIG_FILE": os.devnull, "PIP_INDEX_URL": "https://pypi.org/simple",
                       "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        python = plan["interpreter"]["path"]
        packages = staging / "packages"
        for args in (["--require-hashes", "--only-binary=:all:", "-r", str(lock)],
                     ["--no-deps", str(wheel)]):
            subprocess.run([python, "-m", "pip", "--isolated", "install", "--no-compile",
                            "--index-url", "https://pypi.org/simple", "--target", str(packages), *args],
                           env=environment, cwd=staging, check=True, capture_output=True, timeout=300)
        native = build_native_helper_bundle(staging)
        from installer import NATIVE_HELPERS
        for spec in NATIVE_HELPERS:
            expected_source = plan["native_inputs"][str(spec.source.relative_to(ROOT))]["sha256"]
            expected_profile = plan["native_inputs"][str(spec.build_profile.relative_to(ROOT))]["sha256"]
            if (native[spec.name]["source_sha256"] != expected_source
                    or native[spec.name]["build_profile_sha256"] != expected_profile):
                raise ValueError("Native helper was not built from the approved inputs")
        app = staging / "app"
        app_fd = os.open(app, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        source_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        packages_fd = os.open(packages, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            stage_resource_tree(packages_fd, app_fd, "python")
            resources = stage_application_resources(source_fd, app_fd)
            if resources != plan["resources"]:
                raise ValueError("Approved application resources changed")
        finally:
            for fd in (packages_fd, source_fd, app_fd):
                os.close(fd)
        _copy_checked(plan["interpreter"], app / "bin/python", 0o700)
        # A real isolated import, including binary dependencies, before publication.
        program = ("import sys,pathlib; sys.path.insert(0,sys.argv[1]); import server; "
                   "assert pathlib.Path(server.__file__).parent == pathlib.Path(sys.argv[1])")
        subprocess.run([str(app / "bin/python"), "-I", "-S", "-B", "-c", program, str(app / "python")],
                       env={**environment, "CORTEX_HOME": str(staging / "probe-home")},
                       cwd=staging, check=True, capture_output=True, timeout=30)
        if plan != build_plan(plan["wheel"]["path"], bootstrap_migration=plan.get("bootstrap_migration")):
            raise PermissionError("Generation installation inputs changed during build")
        metadata = build_generation_metadata(staging, uuid4(), native)
        _assert_update_quiescent(home, lock_set)
        bootstrap_install.publish(home, staging, plan["bootstrap_inputs"], plan["bootstrap_before"])
        result = publish_generation(home, staging, metadata)
        generation = home / "installed-generations" / result["generation_id"]
        # Keep build evidence outside the generation and allow the next install.
        os.rename(staging, home / (".generation-build-" + result["generation_id"]))
        fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return {"schema_version": 1, "status": "installed", "plan_hash": plan["plan_hash"],
                "generation_id": result["generation_id"], "generation_path": str(generation),
                "chrome_extension_path": str(generation / "app/chrome-extension"),
                "launcher_path": str(home / "bootstrap/cortex-launch"),
                "launch_argv": [str(home / "bootstrap/cortex-launch"), "--home", str(home)],
                "runtime_started": False}
    except BaseException:
        # All failures propagate; staging and any publication journal remain visible.
        raise
