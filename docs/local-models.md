# Local models (Ollama) — state and restore plan

Last verified: 2026-08-15, on the owner's Mac (Apple Silicon, 16 GiB unified memory).

## Current verified state

| Item | State | Evidence |
|---|---|---|
| Ollama binary | installed | `/opt/homebrew/bin/ollama` |
| Model storage symlink | **dangling** | `~/.ollama/models` → `<external-volume>/AI/Ollama/models` (volume not mounted) |
| External volume | **not connected** | its mount point is absent |
| `orchestra-executor` profiles | **absent** | `ollama list` fails (storage path not traversable) |
| `granite4.1:8b`, `qwen3.5:9b` | **not present locally** | no manifests under `~/.ollama`, none found on other mounted volumes |
| Internal disk free | **4.1 GiB** | `df -h /` — too small for any serious model |
| Doctor | `ollama: false` | `./scripts/cortex.sh doctor --json` |
| Deterministic executor | available without Ollama | Doctor `deterministic: pass` |

The deterministic executor remains the default for missions and needs none of
this. Everything below is optional model support.

## Decision required from the owner (before any download)

1. Reconnect the external volume, then either
   a. keep the symlink (models live on the external volume, which must stay
      connected while Ollama runs), or
   b. remove the symlink and free internal disk space first (4.1 GiB free is
      not enough for any candidate model).
2. No model is downloaded or deleted without explicit approval: downloads are
   5–13 GiB and modify external storage.

## Recommended candidates for 16 GiB unified memory

Historical conversation claims, to re-verify at install time (tags change):

| Model | Approx. size | Role |
|---|---|---|
| `granite4.1:8b` (Q4_K_M) | ~5 GiB | primary `orchestra-executor`; disciplined tool calls |
| `qwen3.5:9b` | ~6.6 GiB | fallback; multimodal + tools |
| `glm-4.7-flash` | ~8 GiB | lighter, faster alternative |
| `gpt-oss:20b` | ~13 GiB | strongest reasoning that still fits; 8K–16K context only |

Do not reuse the historical benchmark claims (Granite 10/10, Qwen tool-call
mismatch) as current facts: re-run the acceptance gate below on the actual
downloaded models.

## Acceptance gate (must pass before a model is advertised as ready)

1. `ollama list` shows the exact tag; `ollama show` confirms the quantization.
2. The 10-case deterministic benchmark passes against the freshly created
   `orchestra-executor` profile (prompt contract: JSON-in-content tool calls).
3. A positive live task (create a file in a disposable workspace) and a
   negative task (refuse reading `/etc/passwd`) both behave.
4. RAM watch during a real mission: no swap storm (16 GiB total budget with
   macOS + Chrome + Ollama coexisting).
5. `./scripts/cortex.sh doctor --json` reports `ollama: true` and the selected
   executor as ready.

## One-command restore (once the external volume is connected and decision 1 is taken)

```bash
# verify the symlink resolves again
ls ~/.ollama/models/manifests/registry.ollama.ai/library
# if models are actually on the external volume, they reappear immediately; otherwise:
ollama pull granite4.1:8b   # ~5 GiB, requires the volume mounted when the symlink is kept
```

Then re-create the `orchestra-executor` Modelfile profile (16K context cap for
this machine) and run the acceptance gate above.
