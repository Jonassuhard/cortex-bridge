#!/bin/bash
# ============================================================
# Cortex Bridge — executor setup
# Installs and validates the local Ollama executor stack.
# Usage:  bash setup-executor.sh [--model ollama-model-name]
# ============================================================
set -euo pipefail

MODEL="${2:-gpt-oss:20b}"
ALIAS="executor-16k"
PROFILE="$HOME/.codex-cortex-bridge"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIGS="$SCRIPT_DIR/../configs"

echo "==> 1/5 Checking Ollama"
if ! curl -s http://127.0.0.1:11434/api/tags > /dev/null; then
  echo "    Ollama is not responding — trying to start the app..."
  open -a Ollama 2>/dev/null || { echo "❌ Ollama is not installed: https://ollama.com"; exit 1; }
  sleep 5
fi
curl -s http://127.0.0.1:11434/api/tags > /dev/null && echo "    OK"

echo "==> 2/5 Pulling $MODEL (this is the long step)"
ollama pull "$MODEL"

echo "==> 3/5 Creating the $ALIAS alias (16K context, tuned for 16 GB RAM)"
sed "s/^FROM .*/FROM $MODEL/" "$CONFIGS/Modelfile.gpt-oss" | ollama create "$ALIAS" -f -

echo "==> 4/5 Smoke tests"
echo "--- Chat:"
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with just: OK\"}],\"max_tokens\":20}" \
  | python3 -c "import sys,json; print('   ', json.load(sys.stdin)['choices'][0]['message']['content'])"

echo "--- Tool calling (critical for agentic execution):"
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$ALIAS\",\"messages\":[{\"role\":\"user\",\"content\":\"What time is it? Use the get_time function.\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_time\",\"description\":\"Get the current time\",\"parameters\":{\"type\":\"object\",\"properties\":{}}}}]}" \
  | python3 -c "
import sys, json
msg = json.load(sys.stdin)['choices'][0]['message']
if msg.get('tool_calls'):
    print('    OK — tool call emitted:', msg['tool_calls'][0]['function']['name'])
else:
    print('    ⚠️  No tool call detected. Raw reply:', (msg.get('content') or '')[:120])
    print('    This model may not be reliable as an agentic executor.')
"

echo "==> 5/5 Creating the isolated Codex profile at $PROFILE"
mkdir -p "$PROFILE"
sed "s/^model = .*/model = \"$ALIAS\"/" "$CONFIGS/config.ollama.toml" > "$PROFILE/config.toml"

echo ""
echo "✅ Executor ready."
echo "   Run a task:  CODEX_HOME=$PROFILE codex exec \"your task here\""
echo "   If asked for an API key:  export OPENAI_API_KEY=ollama"
