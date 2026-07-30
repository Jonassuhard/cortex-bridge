# Cortex Bridge session primer

- Active project: Cortex Bridge v0.5 release candidate on
  `codex/v050-release-qa`; existing delivery is pull request #1.
- Product rule: use the real signed-in Chrome profile through the local
  extension. Never substitute the OpenAI API or a separate Playwright profile.
- Privacy rule: live tests use neutral synthetic markers. Never publish account
  details, sidebar titles, conversation contents, or unblurred screenshots.
- Completed live gates: same-window pairing, one real conversation, two
  concurrent conversations without crossover, refusal of a third writer with
  its draft preserved, one text-file upload, and one explicitly authorized
  visible-tab screenshot upload.
- Latest real recovery gate: after closing the former bound tabs, Cortex
  recreated a ChatGPT tab, sent the recovery prompt once, then read the same
  conversation successfully. Snapshot evidence contains 8 messages, exactly
  one recovery user marker, and exactly one matching assistant marker.
- Root causes fixed: content-script readiness after navigation, dedicated writer
  tab allocation, serialized concurrent allocation, final background-tab paint,
  fail-closed one-shot screenshot authorization, attachment delivery
  confirmation, and stale/closed read-only tab recreation.
- Fresh focused proof after those fixes: 37 Python isolation/readiness tests and
  16 Chrome-extension tests pass. Full regression gates still need a fresh run.
- Runtime: foreground server on `http://127.0.0.1:8420`; extension paired; live
  transport probe returns HTTP 200 with `composer_present=true`.
- Remaining acceptance work: three real disposable mini-site missions, real
  50-conversation/category refresh checks, exhaustive UI/console/responsive/
  accessibility review, full automated suite, clean macOS lifecycle, anonymized
  release evidence, and final Git review.
- Release rule: do not set READY, tag, merge, publish, or claim completion until
  every remaining gate has current evidence. Git push still requires explicit
  confirmation at action time.
- Next exact action: create and observe mini-site mission 1 in
  `/tmp/cortex-bridge-qa/workspaces/site-1`, approve its bounded workspace and
  process capabilities, then verify its files, loopback server, and clean stop.
