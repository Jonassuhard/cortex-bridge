# Provider and account notes

Cortex Bridge v0.5 automates a consumer web interface. Provider terms and product behavior can change independently of this repository.

The [OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/), effective January 16, 2026, prohibit automatically or programmatically extracting data or Output. The v0.5 consumer adapter reads ChatGPT Output programmatically, so the project does not treat authenticated consumer-site automation as an authorized release-acceptance route. Its live gate remains blocked and the adapter stays opt-in and experimental.

This repository does not claim that a ChatGPT subscription grants programmatic API access. A compliant live release requires an officially supported provider transport, separate configuration and separate billing.

Cortex Bridge does not:

- enter or store account credentials;
- accept terms on the user’s behalf;
- solve CAPTCHA or evade anti-bot systems;
- call private ChatGPT endpoints;
- share accounts or extract another user’s data.

The user owns account, policy and cost decisions. An official-API transport is not implemented in v0.5.

This document describes product boundaries, not legal advice.
