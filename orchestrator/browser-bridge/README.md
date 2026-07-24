# Browser/desktop bridge — ⚠️ unofficial, at your own risk

**Status: design stage.**

> **⚠️ WARNING — Terms of Service.**
> Automating the ChatGPT web or desktop app — sending messages and reading
> replies programmatically — **violates OpenAI's Terms of Use** (prohibition
> on automatically or programmatically extracting data or Output from the
> Services). The realistic risk is **suspension or termination of your
> ChatGPT account**.
>
> This module is documented for educational purposes only. If you use it, you
> do so at your own risk and responsibility. The compliant alternative is
> [`../api/`](../api/). See [../../docs/legal-notes.md](../../docs/legal-notes.md).

## Why this module exists

Some users want their existing **ChatGPT Pro subscription** to act as the
orchestrator instead of paying API tokens. Two technical approaches were
explored:

1. **Desktop bridge** — a local helper app that exposes the ChatGPT desktop
   app's conversation to a local API (e.g. Agentify-style tooling).
2. **Browser bridge** — browser automation (Playwright / WebBridge-style)
   driving a real Chrome session on chatgpt.com: type the task, wait for the
   reply, extract it, repeat.

## Open design problems

- Detecting reliably when the model has *finished* generating
- Resilience to UI changes (the DOM is an unstable API)
- Rate limiting and human-like pacing to reduce detection risk
- Session expiry and re-authentication
- Cloudflare / anti-bot countermeasures

## What we will NOT ship

- Any code designed to evade anti-bot protections
- Any tooling that extracts other users' data or conversations
- Account sharing or credential handling of any kind

Contributions discussing the architecture are welcome; contributions that
amount to ToS-evasion tooling are not.
