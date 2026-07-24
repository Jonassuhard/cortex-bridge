# Manual fallback (zero-automation mode)

If you cannot — or do not want to — automate your browser, Cortex Bridge
still works in **manual relay mode**: you are the transport.

## How it works

1. Open the console (`http://127.0.0.1:8420`) and open the **fallback
   payload** for your mission (`GET /api/missions/<id>/fallback-payload`,
   or the console button). It contains the exact mission contract.
2. Paste it into any ChatGPT conversation yourself.
3. When ChatGPT answers with a ` ```cortex-decision ` block, run the
   requested action locally — or let the console executor run it — then
   paste the ` ```cortex-report ` block back into the conversation.
4. Repeat until ChatGPT emits a terminal COMPLETE or BLOCKED decision.

The contract is self-contained: it teaches ChatGPT the cortex.v1 protocol,
the available tools **with their exact argument schemas**, the workspace
path, and the safety rules. Any ChatGPT model can follow it; nothing is
tied to the automation.

## What you lose vs. the automated transport

- Delivery proof and duplicate detection (you are the guarantee that each
  message lands once).
- Automatic pause/resume and conversation locking.
- Live timeline in the console.

## What you keep

- The cortex.v1 protocol and validation rules (you can paste decisions into
  the local validator if you want them checked).
- The workspace-confined tool executor and the write-approval policy, when
  you drive tools through the console instead of by hand.
- The audit store, if you route the reports through the console API.

Manual mode is also the escape hatch when ChatGPT deploys a frontend change
that breaks the DOM contract: missions keep working by hand while the
transport selectors are updated. See
[troubleshooting.md](troubleshooting.md).
