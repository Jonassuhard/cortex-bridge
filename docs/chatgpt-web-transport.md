# ChatGPT web transport

## Runtime

The default v0.5 adapter drives ChatGPT through a dedicated persistent Playwright Chromium profile. The profile is stored under `CORTEX_HOME`; it is never committed and does not share the user’s normal browser profile.

The user opens the profile and signs in. Cortex Bridge does not enter credentials, accept terms, solve CAPTCHA or bypass rate limits.

## Conversation behavior

- At most the latest 50 conversations are returned.
- Pinned, project and recent metadata is preserved only when the page exposes it.
- A selected conversation is bound to its canonical identity before a send.
- Switching uses one absolute 10-second deadline across navigation and snapshot loading.
- A late response cannot replace a newer selection.
- Two writer sessions may send concurrently; a third writer is rejected without losing its local draft or attachment.

## Delivery integrity

Cortex Bridge types through the visible composer and observes the resulting page state. A click alone is not delivery proof. If the outcome is uncertain, the run stops in `DELIVERY_UNCERTAIN`; it never retries automatically and risks duplicating the message.

The adapter exposes explicit blocker states for login, CAPTCHA, rate limits, a closed tab, conversation mismatch, unreadable state and timeout.

## Attachments and screenshots

The browser driver can upload supported staged files and take screenshots. The HTTP API never trusts a client-supplied local path: it resolves an opaque, expiring token to a staged file under `CORTEX_HOME`.

Supported release types and size limits are documented in the [user guide](user-guide.md). Browser or ChatGPT limits can still be stricter and must be surfaced as errors, not silently truncated.

## Testing boundary

Automated tests use the synthetic transport fixture and local Playwright pages. They do not use a real account. Live login and compatibility remain manual release gates requiring explicit owner approval.

The optional WebBridge adapter is compatibility-only and is not installed because no verified official public distribution is available.
