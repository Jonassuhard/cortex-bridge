# Cortex Bridge session primer

- Active project: Cortex Bridge v0.5 release candidate on
  `codex/v050-release-qa`; existing delivery is pull request #1.
- Product rule: use the real signed-in Chrome profile through the local
  extension. Never substitute the OpenAI API or a separate browser profile.
- Privacy rule: live tests use neutral synthetic markers. Never publish account
  details, sidebar titles, conversation contents, or unredacted live captures.
- Live ChatGPT gates passed: same-window pairing, one conversation, two isolated
  writers, refusal of a third writer with its draft preserved, text-file upload,
  one-shot visible-tab screenshot upload, and closed-tab recovery without a
  duplicate send.
- Conversation behavior passed: latest 50 cap, truthful pinned/project/recent
  metadata, lazy message counts, deleted-chat refresh, and ten cold A/B switches
  with zero crossover.
- Autonomous acceptance passed: three disposable mini-sites plus one Cortex-led
  repair, each with required artifacts, three viewports, zero Axe violations,
  zero browser errors, loopback HTTP 200, and clean server shutdown.
- Clean macOS lifecycle passed in a fresh `HOME` and `CORTEX_HOME`: hashed plan,
  locked install, doctor, idempotent reinstall, owned start/status, HTTP 200,
  extension-only WebSocket upgrade, clean stop, foreign-listener preservation,
  manifest uninstall, and released ports.
- Automated release run passed: 387 backend tests, 16 extension tests, 120
  Vitest tests plus 35 frontend contract tests, typecheck, lint, production
  build, 12 E2E tests, 4 accessibility tests, dependency audit, runtime check,
  and public privacy scan.
- Visual guide: 36 synthetic screenshots at 375, 768, and 1440 pixels; no live
  personal data is committed. Animated and static architecture diagrams remain
  in `docs/media`.
- Release evidence: `docs/verification/v0.5.0.json` validates as
  `RELEASE_CANDIDATE_READY_FOR_OWNER_APPROVAL`.
- Open risk: the consumer-site extension is not an officially supported OpenAI
  integration. Provider-terms review remains an owner release decision.
- Git rule: local commits are complete. Do not push, tag, merge, publish, or
  create a release without explicit confirmation at action time.
- Next exact action: obtain explicit confirmation to push
  `codex/v050-release-qa` and update pull request #1.
