# Cortex Bridge session primer

- Active project: Cortex Bridge v0.5 release candidate on `codex/v050-release-qa`.
- Completed: secure loopback Chrome-extension channel, same-window tab routing,
  two-writer isolation, third-writer refusal, French connection UI, English
  installation and agent guides, synthetic image guide, animated architecture,
  dependency/privacy gates, and a real clean macOS install/Doctor/reinstall/
  uninstall cycle.
- Verified automated totals: 375 backend tests, 10 extension tests, 119 Vitest
  tests, 35 frontend runtime/privacy tests, 12 E2E tests plus one skipped guide,
  and 4 accessibility tests.
- Open blocker: authenticated ChatGPT.com automation is
  `BLOCKED_BY_PROVIDER_TERMS`; current OpenAI Europe terms prohibit automatic
  or programmatic extraction of data or Output. Do not mark live conversations,
  uploads, screenshots, mini-sites, or the release verdict as ready.
- Delivery: branch `codex/v050-release-qa` is pushed to pull request #1; backend,
  frontend, public-tree, and release-gates are green. No tag, merge, or release
  was created.
- Next exact action: replace the blocked consumer-site adapter with an
  officially supported provider transport before running any authenticated
  live gate.
