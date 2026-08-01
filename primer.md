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
- Automated release run passed: 388 backend tests, 16 extension tests, 123
  Vitest tests plus 35 frontend contract tests, typecheck, lint, production
  build, 12 E2E tests, 4 accessibility tests, dependency audit, runtime check,
  and public privacy scan.
- Visual guide: 36 synthetic screenshots at 375, 768, and 1440 pixels; no live
  personal data is committed. Animated and static architecture diagrams remain
  in `docs/media`.
- Latest user-journey QA (2026-08-01): Doctor/start, same-window Chrome pairing,
  one neutral chat, a simple file mission, and a complex responsive mini-site
  mission all passed. Cortex remains running on port 8420 and open in Chrome;
  the temporary mini-site server is stopped.
- Mission conversations now keep orchestration prompts and decision JSON behind
  one accessible protocol disclosure, including historical missions without a
  local association. Real Chrome checks passed at desktop and 375 px with no
  horizontal overflow. Three anonymized proof captures are committed.
- Extension commands now use one serialized WebSocket writer and a bounded send
  deadline. The regression test passes and real Chrome stayed at zero pending
  commands across repeated checks.
- Release evidence: `docs/verification/v0.5.0.json` validates as
  `RELEASE_CANDIDATE_READY_FOR_OWNER_APPROVAL`.
- Open risk: the consumer-site extension is not an officially supported OpenAI
  integration. Provider-terms review remains an owner release decision.
- Git state: source/UI fixes are committed at `2573fb0`; this release-evidence
  refresh must be committed next. The user explicitly authorized pushing the
  branch and updating pull request #1, but not merging, tagging, or releasing.
- Next exact action: validate and commit the refreshed release evidence, push
  `codex/v050-release-qa`, then update pull request #1 and wait for its checks.
