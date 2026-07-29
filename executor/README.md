# Reviewed local execution

`executor/` contains the deterministic policy and tool boundary used after an explicit execution preflight. It is not activated by ordinary chat messages.

## Default boundary

- Workspace-relative paths only, with resolved symlink checks.
- Reads may be automatic; writes and processes follow the selected approval policy.
- Process execution is disabled unless the preflight enables it.
- Executables and arguments are validated without a shell.
- Network, deployment, publishing, payment, credential and account actions are unsupported.
- Output, iteration count and wall-clock time are bounded.

The policy engine is release-critical and works without Ollama.

## Optional Ollama worker

The `configs/` and `scripts/` directories contain optional Ollama profiles for users who want a local model to propose reviewed actions. The bridge still validates and executes each action; the model receives no direct filesystem or process authority.

Ollama models are large, optional downloads. Use the consent-bound installer instead of running setup scripts blindly:

```bash
./scripts/install.sh --dry-run --json --with-ollama-model MODEL_TAG
```

Approve only the exact returned plan hash after reviewing its commands, source links, disk estimate and rollback.

See [the security model](../docs/security-model.md) and [installation guide](../INSTALL.md).
