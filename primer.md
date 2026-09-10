# Cortex Bridge project primer

## Source candidate
- Version: 0.6.1. Technical preview; not a verified live or installed release.
- Public repository: linked from README.md.
- Primary branch: main. Candidate branch: codex/v061-atelier.
- See README.md, docs/verification-v061.md and CHANGELOG.md for current evidence.

## Implemented
- Atelier conversation layout, geometric project card and task states.
- Optional French CORTEX terminal on the shared FastAPI backend.
- Conversation history, replies, delivery acknowledgement and isolated drafts.
- Workspace selection, mission preflight, current-action approvals and scoped stop.
- Public use-case diagrams, terminal guide and historical benchmark context.

## Invariants
- No silent transport fallback, automatic resend or fabricated completion.
- At most two active writing conversation leases.
- Terminal drafts are in-memory, not persisted across exits.
- Expected action identity is required for terminal approval.
- Real ChatGPT/account, clean installation and provider acceptance are separate gates.

## Current publication work
- All changes stay in the independent candidate; the original local checkout
  and installed runtime must not be modified.
- User authorized commit/push and main integration if the gates permit it.
- Dependency upgrades/installations have been requested separately.
- Primary-branch integration is blocked while dependency or verification gates fail.
- Public reports must not include personal paths, account details or private records.
- Local session details, if present, are retained in ignored docs/LOCAL_SESSION_V061.md.

## Next action
Resolve the dependency audit and provide current, truthful release evidence
before main integration. The development candidate has 707 backend tests,
207 frontend unit tests, 36 runtime checks and 26 browser fixtures passing;
audit and release-manifest gates remain FAIL. See docs/verification-v061.md.
