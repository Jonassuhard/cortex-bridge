# Benchmark evidence

## Scope

These are historical executor-format experiments already stored in the
repository. They were not rerun for 0.6.1. They do not measure a complete
ChatGPT-to-local mission, terminal responsiveness, coding quality or a
comparison with Codex, Astra, Freebuff or another provider.

| Stored experiment | Cases | Schema validity | Tool selection | Scope compliance | False-success count | Median latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| orchestra-executor | 10 | 100% | 100% | 100% | 0 | 4.73 s |
| orchestra-executor-fallback | 10 | 0% | 0% | 0% | 10 | 5.41 s |

Sources: [primary summary](../executor/benchmark/benchmark-summary-orchestra-executor.json),
[primary cases](../executor/benchmark/benchmark-results-orchestra-executor.json),
[fallback summary](../executor/benchmark/benchmark-summary-orchestra-executor-fallback.json),
[fallback cases](../executor/benchmark/benchmark-results-orchestra-executor-fallback.json).
The [benchmark script](../executor/benchmark/benchmark_executor.py) contains the
case definitions and scoring logic. Fractions above are the stored boolean
criterion means; medians summarize per-case latency, not end-user p95.

## Interpretation limits

- Ten cases per profile are too few to support general model-quality claims.
- The stored summaries do not establish a current model version, run date,
  reproducible machine configuration or independence of repeated samples.
- JSON/tool selection is not proof that a requested file or command was
  successfully executed.
- The failing fallback stays visible; it is not removed from the comparison.
- No new ChatGPT, Freebuff, Luna, GLM or Astra benchmark was run in this update.
- Test-suite duration is not a product performance benchmark.

## Useful next measurements

A future authorized benchmark should fix the source commit, prompt set,
provider/model configuration, workspace and hardware; repeat the same cases;
record cold/warm runs, median and p95, independent artifact checks, refusals,
wrong-scope actions and false-success claims. Publish sanitized raw evidence
and failures, not only aggregate scores. Real account tests need separate
authorization and must respect provider access restrictions.
