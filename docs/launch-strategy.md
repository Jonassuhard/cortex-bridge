# Cortex Bridge launch strategy

## Recommendation

Release v0.5 as a **technical preview**, not as a general-availability product. The fixture evidence is strong, but the live ChatGPT adapter remains an explicit manual gate and the release target is macOS only.

The project is niche, not unmarketable. The weak pitch is “another AI agent.” The useful pitch is:

> Keep the ChatGPT conversation you already use, while every local action stays visible, scoped and separately approved.

Lead with the problem and a 30–45 second proof. Do not lead with orchestration vocabulary; nobody wakes up desperate for another pipeline diagram.

## Comparable projects

| Project | Overlap | Cortex Bridge distinction |
|---|---|---|
| [OpenAI Codex](https://github.com/openai/codex) | Local coding agent with approvals | Cortex Bridge keeps a selected consumer ChatGPT conversation as the visible planning surface |
| [Open Interpreter](https://github.com/openinterpreter/openinterpreter) | Local model and computer execution | Cortex Bridge separates exact chat delivery from a reviewed execution preflight |
| [goose](https://github.com/aaif-goose/goose) | Local, extensible desktop/CLI agent with multiple providers | Cortex Bridge focuses on conversation mirroring, two-writer isolation and browser-delivery integrity |
| [Browser Use](https://github.com/browser-use/browser-use) | Playwright-based agent browser automation | Cortex Bridge uses the browser as a bounded ChatGPT transport, not as the executor’s unrestricted action space |

This is a crowded adjacent market. The differentiator must therefore be demonstrated, not merely asserted: conversation lock, visible delivery states, no silent resend, two isolated writers and explicit execution authority.

## Open-source decision

Keep the v0.5 core open source under MIT after the current-tree and history privacy decisions are complete.

Why:

- The product controls a browser session, files and processes; inspectable code improves trust.
- External contributors can repair selector drift and platform compatibility faster.
- The current moat is product judgment, safety contracts and execution quality, not a secret algorithm.

Conditions:

- Keep browser profiles, cookies, diagnostics, screenshots and runtime data outside Git.
- Use private security advisories and a documented disclosure process.
- Do not promise support for arbitrary forks or unofficial provider adapters.
- Reserve the Cortex Bridge name and visual identity even if the code remains MIT.
- Consider paid hosted compatibility monitoring, signed builds or managed connectors later; do not close the safety-critical core merely to create an imaginary moat.

## Channel plan

### Owned

Use GitHub as the source of truth: README, release notes, guide, architecture GIF, evidence JSON and discussions. Add a small landing page or mailing list only after external testers exist; a newsletter with no readers is simply a database with ambitions.

### Rented

1. **LinkedIn first.** Publish the build story, the problem, a short subtitled demo and a request for five macOS testers. This matches builders, automation users and professional credibility.
2. **YouTube second.** Publish a two-minute installation and mission demo plus one deeper technical walkthrough. Search and embed value last longer than a feed post.
3. **TikTok and Instagram Reels as derivatives.** Recut the same 30–45 second vertical demo. Use them for reach, not as the only explanation or support channel.
4. **Hacker News or relevant Reddit communities after five external installs.** Lead with technical trade-offs and evidence, not promotional copy.
5. **Product Hunt later.** Wait for a signed one-click package, successful external onboarding and a stable live-provider story.

## Five-stage rollout

1. **Internal candidate:** complete fixture gates, privacy scans and release evidence.
2. **Private alpha:** five invited macOS users, screen-shared installation, issue template and explicit live-adapter consent.
3. **Public technical preview:** GitHub release, LinkedIn post, short demo and known-boundary list.
4. **Beta:** signed application, automatic updates, external crash evidence and at least one official provider/API adapter.
5. **General availability:** multi-platform package, stable upgrade path, support policy and measured onboarding success.

## Launch assets

- 30–45 second silent/subtitled vertical demo.
- Two-minute “install, connect, send, preflight, verify” demo.
- Architecture GIF plus static reduced-motion image.
- Six synthetic screenshots at desktop, tablet and mobile widths.
- One technical article: why chat delivery and execution authority must be separate.
- One honest comparison page covering Codex, Open Interpreter, goose and Browser Use.

## Success criteria for the technical preview

- Five external installations without maintainer shell intervention.
- Median first successful fixture conversation under 10 minutes from clone.
- No leaked account data in issues or media.
- No duplicate sends or cross-conversation writes.
- At least three users complete a reviewed local mini-site mission.
- Every failure produces an actionable diagnostic export.

## High-value next updates

1. Signed macOS application with one-click start, stop and update.
2. Official provider/API adapter that does not depend on a changing consumer DOM.
3. Sandboxed disposable mission workspaces and clearer file-diff approval.
4. Provider-neutral agent protocol and plugin boundary.
5. Crash recovery with visible resume decisions and no duplicate delivery.
6. Windows and Linux packaging after the macOS lifecycle is stable.
7. Opt-in compatibility telemetry that records selectors and error classes, never message content.
8. Automated self-diagnostic missions that open issues or patches for review but cannot merge themselves.
