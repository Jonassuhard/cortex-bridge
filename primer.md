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
- Official transport research: ChatGPT developer-mode plugins can call an MCP
  server through a public HTTPS endpoint or Secure MCP Tunnel. The private
  tunnel requires Platform permissions and a runtime API key. Neither route
  preserves the current strict-local/no-API-credential constraint, so adopting
  one is an explicit product architecture change.
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
- Fresh complete gate passed: 416 backend tests, 44 extension tests, 125
  frontend unit tests, 35 frontend contracts, typecheck, lint, production
  build, 12 E2E tests with one documented skip, 4 accessibility tests, runtime
  verification, privacy and release-evidence validation.
- Final synthetic performance: cached usability 147.9 ms; ten-switch p95 and
  maximum 64.8 ms.
- Static gates passed: ShellCheck, Gitleaks, npm/Python audits, 70 documentation
  links including 31 external, and privacy over 293 files and 41 images.
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
  `/private/tmp/cortex-v050-clean-20260806`; plan hash
  `952ac88a626737d69fe38ec2fe5bb1dcca6ab69df466e8df4314b64ab30fac90`;
  300 MiB estimate, no sudo. Apply, doctor, start/stop, reinstall and uninstall
  require explicit approval of that exact hash.
- Source commit `9445b080653c5853a4aa921651d5529b208e4731` contains the
  hardened bridge and release gates. `docs/verification/v0.5.0.json` references
  that exact commit, real artifact hashes and the truthful
  `RELEASE_BLOCKED_BY_PROVIDER_TERMS` verdict.
- Three audited commits are still local, including the committed
  supported-transport clarification; the current candidate is not pushed. User
  authorization covers push after the stated gates pass, not merge, tag,
  release or social publication.
- Exact next action: choose between implementing an officially supported
  provider transport or publishing the branch explicitly as a blocked technical
  preview; separately approve the exact lifecycle hash if that test should run.
