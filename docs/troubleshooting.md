# Troubleshooting

Start with machine-readable diagnostics:

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh status --json
```

## The console does not start

Run doctor. If the port is foreign, Cortex Bridge refuses to take ownership or stop that process. Change the port or stop the foreign service yourself after identifying it.

## The fallback diagnostic page appears

The static UI is missing or invalid. Rebuild it:

```bash
./scripts/build-ui.sh
```

The fallback page cannot send messages or start execution.

## ChatGPT requires login, CAPTCHA or rate-limit recovery

Open the dedicated Chromium profile and resolve the account state manually. Cortex Bridge does not type credentials, solve CAPTCHA or bypass a rate limit.

## Conversation switching times out

Selection has a 10-second hard budget. Use **Recharger la conversation** after checking the dedicated browser. Cortex Bridge does not retry a send automatically.

## A message is marked uncertain

Check the ChatGPT conversation directly. Delivery uncertainty means the click may have happened but confirmation failed. Sending again automatically could duplicate the message, so Cortex Bridge pauses.

## A third conversation cannot send

Two distinct conversation writers are already active. Finish or cancel one. The blocked conversation’s draft and selected file should remain intact.

## An attachment is rejected

Check extension, content and size. Images are limited to 20 MiB. Other supported files are limited to 512 MiB. Office files must contain the correct DOCX, XLSX or PPTX internal structure. Symlinks and misleading extensions are rejected.

## Execution is unavailable

Open the preflight and verify the workspace, executor, approvals and requested capabilities. Write, process and network permissions are disabled by default. Ollama is optional; deterministic execution should remain available.

## Stop refuses the process

The persisted owner no longer matches PID, start time, executable, arguments, token or port. Cortex Bridge refuses to signal it. Inspect `doctor --json` and identify the process outside Cortex Bridge.

## Installer approval fails

Any option change creates a different plan hash. Run a new dry-run, review it and approve the new exact hash. Never copy a hash from another machine or an older plan.

## Logs

```bash
./scripts/cortex.sh logs
```

Logs live under `CORTEX_HOME`. Remove personal content before sharing a report.
