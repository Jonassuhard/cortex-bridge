# Legal notes — read before using the orchestrator bridges

## The short version

| Path | Status |
|---|---|
| Orchestrator via the **official OpenAI API** (pay-per-token) | ✅ Explicitly allowed — this is what the API is for |
| Local executor (Ollama, your own models) | ✅ No third-party terms involved |
| Automating the **ChatGPT web/desktop app** (posting messages and reading replies programmatically) | ⚠️ Violates OpenAI's consumer Terms of Use |

## Details

OpenAI's Terms of Use for individual users (in force since January 1, 2026)
prohibit, among other things:

> automatically or programmatically extracting data or Output from the
> Services

Driving the ChatGPT web UI or desktop app with a browser-automation tool or a
local bridge — sending messages on your behalf and scraping the replies —
falls under that prohibition. This is a **contractual** issue, not a criminal
one, but the realistic consequence is **suspension or termination of your
ChatGPT account** if detected (anti-bot measures, Cloudflare checks, etc.).

The compliant way to get the same result is the **official OpenAI API**, where
programmatic access is the intended use. That is why this repository treats
`orchestrator/api/` as the recommended path.

## Why is `orchestrator/browser-bridge/` in the repo at all?

Many people specifically want to use an existing ChatGPT Pro/Plus subscription
as the orchestrator instead of paying API tokens. The module is documented
**for educational purposes**, clearly marked as contrary to OpenAI's Terms of
Use, and provided **at your own risk**. Using it is your decision and your
responsibility — the project authors take none.

Other providers: similar restrictions generally apply to automating consumer
chat interfaces of other vendors (Anthropic, Google...). Always check the
current terms of the service you intend to automate.

## Your content

Under OpenAI's Terms of Use you own the Output of your conversations. The
restriction above is about *how* you may extract it from the consumer
interface, not about what you may do with content you legitimately have.

---

*This file is information, not legal advice. Terms change — check the current
versions at https://openai.com/policies/ before relying on this summary.*
