# Cortex Bridge v0.5 UI audit

Audit date: 2026-07-29

Surfaces: synthetic fixture build at 375 × 812, 768 × 1024 and 1440 × 900

Evidence: 36 committed synthetic screenshots, Playwright interaction tests and Axe scans

## Release verdict

The fixture interface is understandable, responsive and internally consistent. No known blocking UI defect remains in the audited synthetic flows. Live ChatGPT compatibility is a separate manual release gate because the consumer website can change independently of this repository.

## What is intentionally prominent

- The selected ChatGPT conversation and its message composer.
- Separate ChatGPT and executor status pills.
- Explicit message delivery states, including uncertain delivery.
- Conversation categories, message counts and readable dates.
- A preflight dialog before any local execution.
- A visible two-writer limit with the third draft preserved.

## What stays secondary

- Bridge diagnostics and pipeline details are collapsed behind **Détails du bridge**.
- Models, transport, permissions, storage, legal notes and the architecture diagram live in **Paramètres**.
- Mission execution is not a separate primary mode. The composer stays unified; **Exécuter…** opens the safety preflight only when local work is intended.

## Defects found and fixed during the audit

| Finding | Impact | Fix and proof |
| --- | --- | --- |
| Execution preflight could appear below the sidebar at 768 px | Confirmation content was partially obscured | Raised the workspace while the backdrop is active and asserted centering plus topmost hit-testing in Playwright |
| Sidebar exposed raw ISO timestamps | Transport data was harder to scan | Added French today, yesterday and short-date formatting with a component test |
| Undeclared `--text` and `--border` tokens | Low contrast in onboarding, attachments and the information diagram | Added explicit surface tokens and a source-level test that rejects every undeclared CSS custom property |
| Icon-only settings tabs lost their accessible names at 375 px | The Info tab was ambiguous to assistive technology | Added stable French `aria-label` values and scanned the opened mobile settings panel with Axe |
| The expanded mobile burger had no accessible name | The control repeated the ambiguity between expand and menu actions | Added **Masquer les conversations** and covered the expanded state in the mobile Axe flow |
| Decorative emoji appeared in onboarding status | Added noise without conveying state | Replaced it with plain French copy; semantic status remains in the structured checks |

## Interaction assessment

- Conversation switching has an absolute 10-second budget and exposes explicit cached, stale and reload states.
- The collapsed navigation exposes one unambiguous **Déplier** control, conversation access, new conversation and settings.
- The message lifecycle remains visible from local queue to ChatGPT delivery or uncertainty; uncertain messages are never resent automatically.
- The settings panel remains usable at 375 px without hiding the accessible names of its icon tabs.
- Reduced-motion mode disables the decorative signal sweep and the architecture animation can be replaced by its static PNG.

## Remaining manual checks

- Load the unpacked extension in the owner’s Chrome profile and confirm the live ChatGPT tab, retry dialog and selectors with redacted evidence.
- Run the three approved disposable mini-site missions only after the owner authorizes the account and workspace.
- Confirm installation on a second clean macOS user before calling the release generally available.
