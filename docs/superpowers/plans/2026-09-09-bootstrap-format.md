# Stable bootstrap format alignment

## Requirement and implementation

The normative S3 supervision design names `bootstrap/bootstrap-v1.json` and
defines `bootstrap_manifest_sha256` with the literal ASCII domain
`CORTEX-S3\0BOOTSTRAP-MANIFEST\0V1\0`.

The initial generation installer incorrectly used `manifest.json` and a
different digest domain. Both the writer and inspector now use the specified
format. The executable and retained source/build-profile identities are
unchanged by this format correction. No existing user installation is rewritten.

## Test contract

The real installation test requires the specified manifest path and independently
recomputes its digest using a literal domain and canonical JSON, not a production
constant or hashing helper. It subsequently exercises installed native startup,
HTTP, shutdown, tamper refusal, compatible-bootstrap reuse and interrupted
generation publication with prior selector preservation.

RED: the actual installation failed the new manifest assertion in 55.855 s.
Fresh complete installation suite: seven PASS in 81.293 s.
Publication plus runtime-wheel suites: nine PASS in 4.248 s.
Extension suite (`node --test chrome-extension/tests/*.mjs`): 145 PASS,
zero skipped, 1.595 s. These are extension fixtures, not live Chrome acceptance.
Total for this checkpoint: 161 targeted cases; no global release verdict.

## Migration still open

Development installations containing the former manifest format are rejected;
they are not silently relabelled or rehashed. Migration must explicitly bind the
old state and approved new state, preserve the previous launcher and generation,
hold all required exclusive locks and reject unresolved workflows. A successful
initial install test alone does not prove that upgrade path.
