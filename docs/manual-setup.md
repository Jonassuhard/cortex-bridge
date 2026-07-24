# Manual setup — Cortex Bridge executor, step by step

This guide builds the local executor **by hand**, without running any of the
provided scripts. Use it if you want to understand every piece, adapt it to a
different OS or model, or if you simply prefer not to run shell scripts you
did not write.

The scripts in `executor/scripts/` do exactly what is described here —
reading this guide is the best way to know what they do before running them.

---

## 0. What we are building

```
Codex CLI (isolated profile)
        │
        │  openai_base_url = http://127.0.0.1:11434/v1
        ▼
Ollama server (OpenAI-compatible API)
        │
        ▼
Local model (default: gpt-oss:20b, context capped at 16K)
```

Three independent pieces: the **model**, the **serving layer** (Ollama), and
the **agent harness** (Codex CLI with its own isolated config directory).

---

## 1. Install and start Ollama

Download it from <https://ollama.com> (macOS app) or, on macOS with Homebrew:

```bash
brew install ollama
```

Start it — either by opening the app, or headless:

```bash
ollama serve
```

Verify the server is up. You should get a JSON reply (possibly an empty model
list):

```bash
curl http://127.0.0.1:11434/api/tags
# {"models":[]}
```

> **What is this port?** Ollama serves two APIs on port 11434: its native API
> (`/api/...`) and an OpenAI-compatible API (`/v1/...`). The second one is
> what lets any OpenAI-compatible client — including Codex CLI — talk to your
> local model without any adapter.

---

## 2. Choose and download a model

The executor needs a model that is good at **tool calling** (emitting
structured function calls) and fits your RAM. For a 16 GB Mac:

| Model | Download | Notes |
|---|---|---|
| `gpt-oss:20b` | ~13 GB | **Default.** MoE architecture designed to run on 16 GB |
| `glm-4.7-flash` | ~8 GB | Fastest option, strong tool calling |
| `qwen3:14b` | ~10 GB | Solid dense model, Qwen family |

Download it (this is the long step — several GB):

```bash
ollama pull gpt-oss:20b
```

Check it landed:

```bash
ollama list
```

---

## 3. Create a context-capped alias

Models advertise huge context windows (128K tokens and more). On a 16 GB
machine, using a large context starves everything else — unified memory is
shared between the model, the OS and your apps. We create a derived model
with the context capped at **16K tokens**, the sweet spot for agentic task
execution on 16 GB.

Create a file named `Modelfile` anywhere (e.g. in your home directory):

```
FROM gpt-oss:20b
PARAMETER num_ctx 16384
```

Then build the alias:

```bash
ollama create executor-16k -f Modelfile
```

> **Line by line:**
> - `FROM gpt-oss:20b` — start from the base model you just pulled. No
>   weights are duplicated; the alias shares them.
> - `PARAMETER num_ctx 16384` — default context window for this alias.
>   Raise it (e.g. 32768) if your machine has 24 GB or more.

You can now reference `executor-16k` anywhere Ollama expects a model name.

---

## 4. Smoke-test the model — including tool calling

Do not skip this. A model that chats but cannot call tools will fail
silently as an agentic executor.

**Chat test:**

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "model": "executor-16k",
        "messages": [{"role": "user", "content": "Reply with just: OK"}],
        "max_tokens": 20
      }'
```

You should get a JSON response whose `choices[0].message.content` is `OK`.

**Tool-calling test:**

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
        "model": "executor-16k",
        "messages": [{"role": "user", "content": "What time is it? Use the get_time function."}],
        "tools": [{
          "type": "function",
          "function": {
            "name": "get_time",
            "description": "Get the current time",
            "parameters": {"type": "object", "properties": {}}
          }
        }]
      }'
```

A good executor model answers with a `tool_calls` array containing a call to
`get_time` — instead of prose. If you only get prose, pick another model from
the table above.

---

## 5. Install Codex CLI

```bash
npm install -g @openai/codex
```

Verify:

```bash
codex --version
```

---

## 6. Create the isolated profile by hand

Codex reads its configuration from `$CODEX_HOME` (default `~/.codex`). We
create a **separate** home so the executor never interferes with your normal
Codex setup:

```bash
mkdir -p ~/.codex-cortex-bridge
```

Create `~/.codex-cortex-bridge/config.toml` with this content:

```toml
model = "executor-16k"
model_reasoning_effort = "high"
approval_policy = "never"
sandbox_mode = "workspace-write"

openai_base_url = "http://127.0.0.1:11434/v1"
```

> **Line by line:**
> - `model` — the Ollama alias from step 3. This is the name Codex will pass
>   to the API.
> - `model_reasoning_effort` — how hard the model reasons before answering.
>   `high` suits agentic execution; lower it if responses are too slow.
> - `approval_policy = "never"` — the executor runs commands without asking
>   you each time. This is what makes unattended loops possible — and why the
>   sandbox setting below matters.
> - `sandbox_mode = "workspace-write"` — the executor may write only inside
>   the working directory you run it in, nowhere else on your disk.
> - `openai_base_url` — the crucial redirect: instead of OpenAI's servers,
>   Codex talks to your local Ollama.

Codex requires an API key to be set even though Ollama ignores it:

```bash
export OPENAI_API_KEY=ollama
```

(Add this to your shell profile, e.g. `~/.zshrc`, if you want it permanent.)

---

## 7. Run your first task

```bash
CODEX_HOME=~/.codex-cortex-bridge codex exec \
  "List the files in the current directory and summarize what this project is"
```

If the executor answers and acts, your local half of Cortex Bridge is
working. 🎉

> **Troubleshooting:**
> - *Connection refused* → Ollama is not running (step 1).
> - *Model not found* → the name in `config.toml` must match `ollama list`
>   exactly, including the alias.
> - *Auth errors* → `OPENAI_API_KEY` is not exported in this shell.
> - *Very slow first reply* → the model is being loaded into RAM from disk;
>   subsequent runs are fast. An external drive only affects this load time.

---

## 8. (Optional) Store models on an external drive

Useful when your internal disk is nearly full. Generation speed is unaffected
— weights live in RAM once loaded.

```bash
# 1. Create the target directory on the external drive
mkdir -p /Volumes/YOUR_DRIVE/ollama/models

# 2. Move any existing models there (skip if ~/.ollama/models is empty)
mv ~/.ollama/models/* /Volumes/YOUR_DRIVE/ollama/models/ 2>/dev/null || true

# 3. Replace the local folder with a symlink
rm -rf ~/.ollama/models
ln -s /Volumes/YOUR_DRIVE/ollama/models ~/.ollama/models
```

Every future `ollama pull` now writes to the external drive. The drive must
be connected whenever you use the executor.

---

## 9. Switching backends / undoing everything

- **Point back to the cloud**: edit `~/.codex-cortex-bridge/config.toml` and
  replace the `openai_base_url` and `model` lines with your cloud provider's
  values (or keep two config files and swap them — this is what
  `executor/scripts/switch-executor.sh` automates).
- **Remove the executor entirely**:
  ```bash
  rm -rf ~/.codex-cortex-bridge
  ollama rm executor-16k gpt-oss:20b
  ```
- **Undo the external-drive symlink**:
  ```bash
  rm ~/.ollama/models          # removes only the link, not the data
  mkdir ~/.ollama/models
  ```

---

## Next step

The executor alone only runs one-off tasks. The full Cortex Bridge loop —
where a cloud orchestrator sends tasks and reads reports automatically — is
described in [`../orchestrator/README.md`](../orchestrator/README.md).
