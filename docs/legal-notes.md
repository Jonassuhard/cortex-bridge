# Provider and account notes

Cortex Bridge v0.5 automates a consumer web interface. Provider terms and product behavior can change independently of this repository.

**Cortex Bridge is not affiliated with, endorsed, or authorized by OpenAI.**

The [OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/), effective January 16, 2026, prohibit automatically or programmatically extracting data or Output. The v0.5 consumer adapter reads ChatGPT Output programmatically, so the project does not treat authenticated consumer-site automation as an authorized release-acceptance route. The adapter ships as an explicit opt-in: the settings UI states this conflict and the account-suspension risk in French before activation, and the bridge stays disabled until the user personally accepts.

Enabling the adapter is the user's own decision, made at their own risk: under the same terms, OpenAI may restrict, suspend, or terminate access for a breach. Owner-authorized live technical runs (see `docs/verification/v1-live-qa-2026-08-15.md`) prove behavior, not permission.

This repository does not claim that a ChatGPT subscription grants programmatic API access. A compliant live release requires an officially supported provider transport, separate configuration and separate billing.

Cortex Bridge does not:

- enter or store account credentials;
- accept terms on the user’s behalf;
- solve CAPTCHA or evade anti-bot systems;
- call private ChatGPT endpoints;
- share accounts or extract another user’s data.

The user owns account, policy and cost decisions. An official-API transport is not implemented in v0.5.

This document describes product boundaries, not legal advice.
