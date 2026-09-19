# Disposable mini-site acceptance — 14 September 2026

Correction dated 19 September 2026: the earlier claim that these were three
executed mini-site missions is retracted. An ad hoc script wrote fixture files
and supplied preset browser, HTTP, accessibility and command-success values to
the acceptance verifier. No browser or HTTP server was run by that script, and
no Cortex executor or external model created the sites.

Command path:

```text
scripts/acceptance-mini-site.py baseline
scripts/acceptance-mini-site.py verify
```

| Run | Workspace | Baseline | Verify | Result |
|---:|---|---:|---:|---|
| 1 | fixture case 1 | 0 | 0 | Validator accepted supplied fixture values |
| 2 | fixture case 2 | 0 | 0 | Validator accepted supplied fixture values |
| 3 | fixture case 3 | 0 | 0 | Validator accepted supplied fixture values |

The verifier checked the fixture artifacts and hashes against the supplied
JSON and baseline. Viewports, console/page errors, requests, keyboard access,
reduced motion and accessibility were assertions in that JSON, not measurements.

Cleanup was not demonstrated; the earlier deletion claim is also retracted.
These runs count as zero live mini-site acceptance missions. Raw historical
commits remain available; this correction does not change their contents.
