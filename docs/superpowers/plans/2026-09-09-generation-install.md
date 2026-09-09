# Generation installation through apply_install

## Objective and scope

Install a reviewed local Cortex wheel and locked dependencies into a private
application generation through `apply_install`. Publish only after resources,
native helpers and Python imports are verified. Exercise the real installation
and HTTP lifespan in an isolated temporary home on macOS.

## Steps

1. Add an explicit `--generation-wheel` installation plan. Bind the wheel,
   interpreter, dependency lock, source resources and current selector to its hash.
2. Dispatch that plan from `apply_install` under the existing install lock.
   Install dependencies into temporary staging, copy application resources,
   compile/sign helpers, construct metadata and call the existing publisher.
3. Test changed approvals/inputs, pending publication, fresh install and actual
   installed server HTTP responses. Preserve failed staging for reconciliation.
4. Record exact results and limitations; preserve the existing application.

## Acceptance boundaries

The test must use the real installer, pip, helper compiler, metadata producer and
publisher. No fake interpreter, replaced verification function or disabled
storage guard in the end-to-end case. The Python standard library/framework
remains a host prerequisite. S3 managed startup, live ChatGPT and clean-machine
macOS acceptance are separate gates, not proven by a temporary-home install.

## Implemented interface

From a source checkout with a built Cortex wheel and exported frontend:

```sh
export CORTEX_HOME=/absolute/path/to/private/cortex-home
PYTHONPATH=.:console python3 -m installer install --generation-wheel /absolute/path/cortex_bridge-VERSION-py3-none-any.whl --dry-run --json
```

Review the returned target, inputs, dependency download and build steps. Apply
the exact returned hash with the same command and `--approve-plan HASH` in place
of `--dry-run`. No model, browser or external account is installed/connected by
this command. The existing installation command remains available for legacy
installations; this generation mode is explicit.

`apply_install` dispatches generation plans under the existing exclusive
installation/storage locks. It recomputes the approval hash, rejects a changed
target, rechecks all inputs before and after construction, verifies native build
input hashes, validates isolated Python imports, and publishes the metadata and
selector using `publish_generation`.

Success returns `status=installed`, the generation and extension paths, and
`runtime_started=false`. The install does not invoke the unfinished S3 managed
launcher. The selected generation contains all locked third-party Python
dependencies; the copied interpreter still depends on the host's Python
framework/standard library. Failed staging and previous generations remain
available for reconciliation. Successful build inputs are retained in a private
`.generation-build-UUID` directory; disk reclamation is not implemented here.

## Reproducible validation

```sh
PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_generation_install.py -v
PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_installer.py -q
PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_generation_publication.py -q
PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_runtime_wheel.py -q
```

The end-to-end test builds an actual wheel, installs locked wheels from PyPI,
builds/signs all four native helpers, calls real `apply_install`, revalidates
the published generation and starts its actual Python server outside the source
checkout. `-I -S -B` excludes host site-packages and bytecode writes. The real
lifespan/storage guard run in a new home with no external-storage configuration.
HTTP checks compare the homepage and a JavaScript asset with the installed
files. SIGTERM shutdown must complete the lifespan; Uvicorn then re-raises the
signal, as verified in the local dependency source.

A second real install injects an error only at selector publication. The test
requires the prior selector bytes and generation to remain valid and the
journal to report pending reconciliation. Unit cases also reject changed plan
content, changed wheel bytes, target drift and interrupted legacy/publication
transactions. This is not a clean-machine, S3 mount, native-bootstrap, live
Chrome or mission acceptance result.

## Executed results (macOS arm64, Python 3.14)

| Suite | Result | Time |
| --- | --- | --- |
| Generation installation, including real HTTP and failed second publication | PASS — 6 tests | 67.069 s |
| Existing installer regression | PASS — 100 tests | 84.859 s |
| Generation publication transaction | PASS — 4 tests | 0.030 s |
| Actual isolated wheel, including generation_install import | PASS — 1 test | 5.662 s |

The first end-to-end attempt exposed an incorrect test expectation for graceful
SIGTERM shutdown (expected zero instead of Uvicorn's deliberate re-raised signal).
The dependency implementation was inspected and the test now checks both the
expected signal exit and completed lifespan shutdown. No application shutdown
check or storage guard was removed. A final fresh installation suite also covers
the subsequently added legacy-transaction refusal and parent-directory fsync.

Total: 111 targeted tests passed. Git diff whitespace validation passed. No
installed user application, account connection, source version, commit or remote
branch was changed by this test run. Build/source test fixtures use temporary
storage and are removed by test cleanup; this document retains the measured
results and the test source makes them reproducible.

Storage session evidence (immediate metadata, not code correctness): console
`deb50fdf86034027b00d3d6b6052f063`, tests
`29ad3906583f4bb6aa4d3233f74d40ae`, plans
`f9accf4168234f6d85eb110e0f35792e`, root
`0a893371bb7f4db29157b7d9ce3d0f16`. Each structure is in the central Storage System
`data/folder-sessions/SESSION_ID/STRUCTURE.md`.
