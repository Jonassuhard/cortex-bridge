# Cortex terminal

The terminal is an optional French-language full-screen interface to the existing
local Cortex backend. It does not create another execution engine or database.
Chrome and the backend are not started without an explicit command.

From an existing managed Cortex checkout:

```sh
scripts/cortex --help
scripts/cortex --version
scripts/cortex
scripts/cortex --plain
scripts/cortex ui
```

The source wrapper uses the checkout's existing Python environment. The default
opens the Textual full-screen client. `--plain` selects the compatibility
prompt for terminals that cannot render the TUI. No global `cortex` command or
PATH change is installed by this worktree; the package entry point is defined
for an explicitly approved installation.

`scripts/cortex` shows the CORTEX header, ChatGPT/executor status cards,
conversation list and composer. The full-screen client keeps network requests
in background workers so typing remains responsive.
`scripts/cortex ui` opens the same local URL in Google Chrome on macOS, or
the default browser on other platforms. It uses fixed arguments without a
shell. Neither command sends a ChatGPT message.

The default backend is `http://127.0.0.1:8420`. To select another loopback port:

```sh
scripts/cortex --url http://127.0.0.1:18420
scripts/cortex --url http://127.0.0.1:18420 ui
```

Only root HTTP URLs with a loopback IP literal, such as `127.0.0.1`, are
accepted. The hostname `localhost` is not accepted by this client. Non-loopback
hosts, credentials, paths and query strings are rejected. `--help` and
`--version` work offline.

## Startup and connection

- `/statut`: inspect the backend's ChatGPT transport and executor states.
- `/demarrer`: delegate to this checkout's `scripts/cortex.sh start`, using
  the selected port. A wheel without the managed checkout reports this
  requirement; it never starts a substitute daemon.
- `/consentement`: review the transport warning and explicitly confirm opt-in.
- `/connecter`: use the existing Chrome-extension connection flow. If pairing
  is needed, open the Cortex web page; no pairing token is printed.
- `/reessayer`: ask the backend to verify the connection again.
- `/ui`: open the local graphical interface. Opening failure is reported with
  a manual URL, not a success message.

## Working commands

| Command | Purpose |
| --- | --- |
| `/conversations`, `/ouvrir 1` | List up to 50 conversations and select one |
| `/nouvelle` | Select a provisional new conversation |
| `/historique` | Read the selected conversation's messages |
| Ordinary text or `/chat TEXT` | Submit a chat message |
| `/brouillon` | Show this selection's unconfirmed submissions, without resending |
| `/dossier PATH` | Select the mission workspace |
| `/mission OBJECTIVE` | Review and confirm a deterministic, network-off mission |
| `/missions`, `/mission-ouvrir ID` | List and select a mission |
| `/suivre`, `/rafraichir` | Follow or refresh the selected activity |
| `/autoriser`, `/refuser` | Review and decide the current pending action |
| `/stop` | Cancel only the selected activity |
| `/reglages`, `/reglage KEY VALUE` | Read settings or confirm a change |
| `/modeles`, `/modele LABEL` | Inspect and select a backend-discovered model |
| `/aide`, `/quitter` | Show commands or exit without stopping the backend |

## Safety and limits

`QUEUED` is not delivery confirmation. Ambiguous requests are never retried
automatically. Unconfirmed submissions are kept separately in memory and are
available through `/brouillon`; they are **not persisted after terminal exit**.
The backend enforces its two-writing-conversation limit.

Ctrl-C exits follow mode without cancelling work. Cancellation requires
`/stop`. Approval applies once to the action displayed, with an atomic backend
identity check. Older backends without `pending_approval_action_id` cannot be
approved from this terminal; there is no silent downgrade. Legacy GUI clients
without the optional guard keep their existing behavior.

Terminal tests use synthetic HTTP fixtures and isolated FastAPI instances.
They do not prove live ChatGPT delivery, a provider mission, native Windows
operation, or an installed release. See [acceptance matrix](TERMINAL_ACCEPTANCE.md)
for current failures and evidence; a documented command is not a test verdict.
