# Cortex Bridge v0.5.0

Cortex Bridge v0.5 is a macOS technical preview for keeping a ChatGPT conversation visible while local work remains behind an explicit execution preflight.

## Highlights

- Conversation-first French interface with Pinned, Projects and Recent groups.
- At most 50 conversations, with one absolute 10-second switch deadline.
- Exact chat send path with visible delivery lifecycle and no automatic resend after uncertainty.
- Two isolated conversation writers; a third keeps its draft and attachment until a slot is free.
- Separate ChatGPT and executor status, with pipeline detail behind a drawer.
- Explicit workspace, capability, approval and limit review before local execution.
- Packaged Manifest V3 extension using ChatGPT in the user’s existing Chrome window; Playwright remains development-only.
- Validated, expiring attachment tokens for images, documents and screenshots.
- Consent-bound installer, machine-readable doctor, owned-process lifecycle and non-destructive uninstall.
- Deterministic static build, responsive and accessibility gates, privacy scanner and synthetic guide media.

## Verification boundary

The automated release suite uses synthetic fixtures and local browser pages. It does not sign in to a real ChatGPT account. Real Chrome linking, live messages, uploads and the three ChatGPT-planned mini-site missions remain explicit owner-approved gates, so the machine-readable verdict remains pending until those observations exist.

Read the [release evidence](../docs/verification/v0.5.0.json), [installation guide](../INSTALL.md), [user guide](../docs/user-guide.md) and [security policy](../SECURITY.md) before publishing this candidate.

## Compatibility

- macOS
- Python 3.11 or newer
- Node only when rebuilding the shipped interface
- Ollama optional

The consumer web adapter is experimental because the ChatGPT interface and provider policies can change independently of this project.
