# Cortex Bridge session primer

- Active project: Cortex Bridge v0.5 release candidate on
  `codex/v050-release-qa`; existing delivery is pull request #1.
- Product rule: the intended product uses the real signed-in Chrome profile
  through the local unpacked extension. It never substitutes the OpenAI API or
  a separate browser profile without an explicit product decision.
- Provider blocker: the OpenAI Europe Terms of Use updated January 16, 2026
  prohibit automatic or programmatic extraction of data or Output. The v0.5
  consumer adapter performs that extraction. Owner approval cannot turn this
  route into compliant release acceptance, so no further authenticated sends
  or `READY` verdict are allowed under the current design.
- Privacy rule: any technical observation uses neutral synthetic markers.
  Never publish account details, sidebar titles, conversation contents,
  conversation IDs, cookies, logs, or unredacted live captures.
- Current source fixes content-script recovery, exact delivery confirmation,
  dedicated reusable writer tabs, two-writer isolation, direct target-tab
  creation, attachments, one-shot screenshots, protocol attestation, frontend
  reload recovery, navigation deadlines and French UI state.
- Chrome navigation now returns when Chrome accepts the requested target. It no
  longer waits for `pendingUrl`, which Chrome does not guarantee with Cortex's
  minimal permissions; composer readiness remains a separate backend check.
- A stale second extension can no longer corrupt the status of an active valid
  pairing.
- Process ownership now treats a timed-out listener probe as structured
  `unknown` and refuses start/stop actions. It never crashes or signals an
  unverified process.
- Release evidence now hashes real repository artifacts instead of accepting
  any well-formed fake digest.
- Fresh backend evidence: 414 tests passed in 128.087 seconds. The focused
  extension suite passes 44/44, release-manifest suite 13/13, and process
  ownership suite 10/10 plus ten repeated foreign-process runs.
- The previous complete gate passed extension, frontend unit/runtime,
  typecheck, lint, build, E2E, accessibility, runtime verification and privacy;
  rerun the complete gate once more after the final documentation/evidence edit.
- Static gates passed: ShellCheck, Gitleaks, npm/Python audits, 69 documentation
  links including 30 external, and privacy over 293 files and 41 images.
- Earlier owner-authorized Chrome observations are historical technical data,
  not compliant release acceptance. The latest new-chat attempt failed at the
  10-second navigation deadline before the final no-wait extension fix was
  loaded; it must not be reported as passed or retried while the provider
  blocker remains.
- The source extension and the local desktop deployment copy are synchronized.
  The latest service-worker reload was not confirmed before the provider block
  stopped live testing.
- Cortex and the controlled Chrome QA session are stopped. No test server is
  expected on loopback port 8420.
- Fresh isolated install dry run target:
  `/private/tmp/cortex-v050-clean.yDHvnq`; plan hash
  `de4fa416a41216ab428ebad22408cc8b2d803c9130dfeb02072079086c665986`;
  300 MiB estimate, no sudo. Apply, doctor, start/stop, reinstall and uninstall
  require explicit approval of that exact hash.
- `docs/verification/v0.5.0.json` is stale. The improved validator correctly
  rejects its old frontend hash. Final evidence must use a source commit, real
  artifact hashes and either `RELEASE_BLOCKED_BY_PROVIDER_TERMS` or a genuinely
  compliant transport result.
- Current changes are uncommitted and unpushed. User authorization covers push,
  not merge, tag, release or social publication.
- Exact next action: choose between implementing an officially supported
  provider transport or publishing the branch explicitly as a blocked technical
  preview; separately approve the exact lifecycle hash if that test should run.
