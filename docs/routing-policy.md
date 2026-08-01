# Execution routing policy

## Intent routing

The interface does not expose a persistent Chat/Mission toggle. A normal send is always the exact ChatGPT draft. A request for local work opens an explicit execution preflight; the user then chooses the workspace and capabilities before anything can run.

## Deterministic policy

The policy engine, not the language model, decides whether an action is allowed. Its default is workspace write with approvals; process execution remains disabled unless explicitly enabled for the mission.

For each action:

1. validate mission identity, iteration and structured arguments;
2. validate workspace confinement and capability policy;
3. obtain any required approval;
4. execute one bounded action;
5. persist evidence and return a structured result.

Duplicate action identifiers are not executed twice. Invalid protocol and uncertain delivery fail closed.

## Optional local model

An installed Ollama worker may propose structured actions. It receives no direct file or process authority. The bridge validates and runs actions through the same policy boundary and records which model, if any, was used.

If the configured model or storage is unavailable, the runtime reports that state. It does not silently claim success or substitute a cloud provider.
