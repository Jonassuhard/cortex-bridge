# Testing

## Current candidate: 0.6.1

Read [current results](verification-v061.md) first. The sections below include
historical v0.5 evidence and acceptance requirements, not automatic proof for
the current candidate. [Terminal commands](TERMINAL.md) and
[benchmark limits](benchmarks.md) are documented separately.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:console:tests .venv/bin/python -m unittest \
  test_terminal_client test_terminal_app test_terminal_api_integration \
  test_terminal_settings test_terminal_cli
```

This terminal slice contains 81 tests, including actual subprocess PTY input,
full-screen Textual smoke tests and output against synthetic fixtures, not a
signed-in ChatGPT session.

## Complete local gate

```bash
PYTHON=$HOME/.local/share/cortex-bridge/venv/bin/python ./scripts/test-all.sh
```

The gate runs backend tests, Python compilation, Manifest V3 protocol tests,
fallback syntax, dependency audit, frontend unit/runtime/coverage/type/lint,
static build, Playwright E2E and accessibility fixtures, runtime verification,
and public privacy checks.

Playwright is the synthetic browser test tool. It is not the product transport.

## v0.5 release test matrix

Every row is a separate release zone. A synthetic result may prove local logic,
but it never replaces a required observation in the owner's signed-in Chrome
profile.

| Zone | Automated evidence | Required real evidence | Release condition |
| --- | --- | --- | --- |
| Installer consent | dry run, immutable hash, wrong-hash rejection, rollback | apply one reviewed hash in an isolated macOS home | install and idempotent reinstall succeed without `sudo` |
| Process ownership | PID identity, stale PID and foreign-port tests | start, HTTP 200, status, stop and released port | no foreign process is signalled or removed |
| Chrome extension protocol | allowlist, pairing expiry/replay, protocol attestation, competing-extension isolation, heartbeat, reconnect and bounded commands | unpacked extension pairs in the same Chrome window | protocol generation matches, a stale second extension cannot corrupt the active status, then the probe reports the real composer and zero pending commands |
| Conversation discovery | deduplication, 50-item cap and truthful metadata fixtures | refresh a pinned, project and recent conversation; remove one and refresh | no fabricated category, duplicate or deleted conversation remains |
| Navigation | cached UI, pending-target detection, separate composer readiness and ten A/B fixture switches | cold and warm switches between two neutral conversations | Chrome exposes the requested URL without consuming the composer budget; p95 remains below 3 seconds, hard maximum 10 seconds, no crossover |
| Message delivery | prepare, activation, visible-marker confirmation and no-resend tests | one neutral exact-response message | visible sent state precedes the reply; ambiguous delivery is never retried |
| Two writers | lease isolation and third-writer fixture scenarios | two simultaneous neutral sends plus a third attempt | A and B finish in their own tabs; the third draft is preserved and refused |
| File upload | MIME, size, symlink, staging-token, duplicate-name, normalized-text hash handoff, global AX target uniqueness, bounded composer grouping, timeout, single-use expectation and exact DOM-proof tests | one small synthetic text file sent through the current macOS Accessibility helper | one stable toolbar URL/file/composer/send target is proven, one native press starts, and a new exact text-plus-file DOM message is returned without replay |
| Screenshot upload | one-shot permission, target match and atomic PNG tests | one explicitly authorized synthetic browser capture | the capture targets the selected conversation and is consumed once |
| Mission protocol | parser, sequence, resynchronization, approvals and terminal validation | three disposable mini-sites and one self-diagnostic run | artifacts validate, processes stop, no mission merges or pushes itself |
| Executor policy | workspace boundary, process allowlist, timeout and secret-free environment | one approved local write and one approved local process | no action exceeds the displayed workspace or capability scope |
| Recovery | restart, database failure, closed-tab and content-script recovery tests | close a Cortex-owned ChatGPT tab after delivery | reading recovers without a second user message |
| Interface quality | component, E2E, console, keyboard, reduced-motion and Axe tests | inspect the shipped UI at 375, 768 and 1440 pixels | no blocker, horizontal overflow, console error or Axe violation |
| Documentation and privacy | link checker, runtime verifier, marker scan, OCR, metadata and Gitleaks | review only synthetic/redacted evidence | public tree contains no account data, private title, cookie, path or secret |
| Dependencies and package | hashed Python lock, locked npm audit, build reproducibility and CI contracts | clean lifecycle uses the packaged extension | no high-severity npm finding; every shipped artifact hash matches evidence |
| Provider compliance | evidence-validator blocker states and current official-terms link | provider authorization for the intended transport | owner approval alone never changes a provider-blocked gate to pass |
| Release integrity | evidence-schema and artifact-hash tests | inspect the exact source commit and PR checks | all rows are green before the evidence verdict becomes ready |

## Focused commands

```bash
python -m unittest tests.test_chrome_extension_bridge -v
python -m unittest tests.test_chrome_extension_driver -v
node --test chrome-extension/tests/extension.test.mjs
./scripts/cortex.sh doctor --json
cd frontend
../scripts/npmw run test:unit
../scripts/npmw run typecheck
../scripts/npmw run lint
../scripts/npmw run build
../scripts/npmw run test:e2e
../scripts/npmw run test:a11y
```

## Fixture proof

Fixtures prove pairing expiry/replay, command allowlisting, same-window tab
creation logic, connection dialog states, stale-extension isolation, automatic
Cortex-page recovery after an extension reload, exact send lifecycle, two
writers and third rejection, target-URL navigation followed by separate
composer readiness, 10-second selection, attachments, screenshots, restart,
responsive layouts, keyboard behavior, Axe, reduced motion, and absence of
unexpected browser errors.

The attachment driver fixtures inject the native activator. They prove the
extension-to-helper contract, normalized-text SHA-256 handoff without the full
prompt, absence of prompt/path/content in activation arguments and logs,
one-shot state, post-press DOM evidence, and fail-closed errors. Native helper
tests cover the globally unique AX target, toolbar-only omnibox, exact bounded
file/composer/send ancestry and timeout failures. They do not grant macOS
Accessibility or prove the current ChatGPT page.

Fixtures do not prove current compatibility with a real authenticated ChatGPT
account.

On 2026-08-25, a separate owner-authorized technical observation used the
production protocol-v2 extension in the owner's existing Chrome profile. It
confirmed one neutral text send, two isolated writers and third-writer refusal,
one small synthetic file, one privacy-masked screenshot, and three disposable
mini-sites. The mini-sites independently passed three viewport renders,
keyboard interaction, reduced motion, zero Axe violations, zero browser errors
and zero external requests. This observation proves technical behavior only;
it is not provider authorization and contains no publishable account or
conversation identifier.

## macOS attachment gate

Before a real file-send observation, run:

```bash
./scripts/cortex.sh doctor --json
```

Record the three checks separately: `swift_toolchain`, `macos_ax_helper`, and
`macos_accessibility`. A permission warning is acceptable for application
startup and text-only tests, but the file gate remains pending until all three
pass.

Use only a small synthetic file and neutral prompt. In the Cortex-bound ChatGPT
tab, record these facts without account data or conversation IDs:

1. the extension exposed the expected filename and prepared one send control;
2. the current helper had manual Accessibility permission;
3. the AX result identified one stable global target with the expected toolbar
   URL, composer hash and bounded file/composer/send group;
4. one native press was attempted, with no automatic replay;
5. a new DOM user message contained the exact normalized prompt and attachment;
6. ChatGPT returned one response.

If step 5 is absent, the result is `DELIVERY_UNCERTAIN`, not pass. Historical
attachment observations made before this helper path do not close the current
gate.

## Provider-compliance boundary

The intended live gate would check one conversation, two isolated
conversations, third rejection, a small redacted file, a redacted screenshot,
tab-close recovery, and three disposable mini-site missions. The v0.5
consumer-site adapter automatically reads ChatGPT Output, so that gate is
blocked by the current provider terms even when the account owner approves a
technical test.

Evidence stores aggregate results and hashes, never account identity, cookies,
conversation text, or unredacted media. While this blocker remains, the status
is `BLOCKED_BY_PROVIDER_TERMS`; fixture success and owner approval cannot change
it to `PASS`.

## Release evidence

Validate the evidence selected from the canonical `VERSION` file with:

```bash
./scripts/verify-release-evidence.py
```

Pass an explicit manifest path only when auditing historical evidence.
