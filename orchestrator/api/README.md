# Official API transport reference

This directory documents a future provider-API transport. Cortex Bridge v0.5 does not ship an OpenAI API client here and does not ask for an API key during installation.

An implementation should preserve the same contracts as the browser transport:

- explicit provider configuration and costs;
- structured, bounded messages and reports;
- no hidden fallback between providers;
- no execution without a separate reviewed preflight;
- secrets stored outside the repository and never exposed to the frontend;
- deterministic retry and idempotency rules.

Until such a transport is implemented and tested, the product must not present this directory as an available connection method.
