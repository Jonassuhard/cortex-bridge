# Local models (Ollama) — state and restore plan

Last verified: 2026-08-17, on the owner's Mac (Apple Silicon, 16 GiB unified memory).

## Current verified state

| Item | State | Evidence |
|---|---|---|
| Ollama binary | installed | `/opt/homebrew/bin/ollama` |
| Model storage symlink | **active** | `~/.ollama/models` → `<external-volume>/AI/Ollama/models`; `~/.ollama` holds 8 KB on the internal disk |
| External volume | **connected** | models and profiles live there; the volume must stay mounted while Ollama runs |
| `orchestra-executor` profile | **present** | created from `executor/configs/Modelfile.orchestra-executor` on `granite4.1:8b` |
| `orchestra-executor-fallback` profile | **present** | created from `executor/configs/Modelfile.orchestra-executor-fallback` on `qwen3.5:9b` |
| `granite4.1:8b`, `qwen3.5:9b` | **installed** | `ollama list`; 5.3 GiB + 6.6 GiB on the external volume |
| Fresh 10-case benchmark | **PASS 10/10** | schema 1.0, tool selection 1.0, scope 1.0, zero false success, median 4.73 s (2026-08-17, `orchestra-executor`) |
| Positive/negative probes | **pass** | `write_file` inside `/workspace` requested correctly; `/etc/passwd` answered BLOCKED with null tool |
| RAM watch | no swap storm | 17 % free at peak with macOS + Chrome + Ollama coexisting |
| Doctor | `ok: true` | `/api/status`: `ollama_up: true`, `executor_available: true`, storage on the external volume |
| Deterministic executor | available without Ollama | Doctor `deterministic: pass` |

The deterministic executor remains the default for missions and needs none of
this. Everything above is optional model support.

## Owner decision (taken 2026-08-16)

The owner reconnected an external volume and approved the restore: the symlink
was re-pointed to `<external-volume>/AI/Ollama/models` (the original target
volume name was absent) and both models were pulled there. No model lives on
the internal disk. Rule kept: no model is downloaded or deleted without
explicit approval.

## Acceptance gate — all items passed 2026-08-17

1. ✅ `ollama list` shows the exact tags; `ollama show` confirms Q4_K_M.
2. ✅ Fresh 10-case deterministic benchmark against the freshly created
   `orchestra-executor` profile: 10/10, zero false success.
3. ✅ Positive probe (`write_file` in `/workspace`) and negative probe
   (`/etc/passwd` → BLOCKED, null tool) both behave.
4. ✅ RAM watch during the benchmark: no swap storm (16 GiB total budget with
   macOS + Chrome + Ollama coexisting).
5. ✅ Runtime status reports `ollama_up: true`, `executor_available: true`,
   storage on the external volume.

## Restore procedure (if the volume is absent again)

```bash
# verify the symlink resolves again
ls ~/.ollama/models/manifests/registry.ollama.ai/library
# if models are actually on the external volume, they reappear immediately; otherwise:
ollama pull granite4.1:8b   # ~5 GiB, requires the volume mounted when the symlink is kept
```

Then re-create the `orchestra-executor` Modelfile profile (8K context cap for
this machine) and re-run the acceptance gate above.
