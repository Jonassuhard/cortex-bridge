# Surface guard and screenshot capture — v0.5.1

Two flows changed after ChatGPT introduced the Chat/Work split and after live
QA proved that unattended automation cannot depend on a physical toolbar-icon
click.

## Classic-Chat-only surface guard

ChatGPT serves classic Chat and Work surfaces behind the same `/c/<id>` URL
scheme. The extension therefore classifies the surface in the DOM before any
write:

```mermaid
flowchart TD
    A[Delivery-sensitive action<br/>prepare_text / attachment_begin / send_bare] --> B{surfaceMode}
    B -->|/c/&lt;id&gt; page: sidebar self-link aria-label ends with ", Work"| C[work]
    B -->|home: Chat/Work radiogroup checked state| D{which radio?}
    B -->|no decisive DOM signal| E[unknown]
    D -->|Work checked| F[work home]
    D -->|Chat checked| G[chat]
    B -->|self-link without suffix| G
    F --> H[click the Chat radio<br/>wait for aria-checked=true]
    H -->|switched| G
    H -->|no Chat radio / timeout| I
    C --> I[throw WORK_SURFACE_REJECTED<br/>fail closed, nothing composed]
    E --> J[proceed<br/>backward compatible, reported as surface=unknown]
    G --> K[proceed with composer flow]
```

`surface` is reported in `probe` and state payloads, so the scheduled DOM
probe records classification drift whenever ChatGPT changes its markup.

## Screenshot capture: click path + CDP fallback

```mermaid
sequenceDiagram
    participant S as Cortex server
    participant W as Service worker
    participant T as Cortex-bound ChatGPT tab
    S->>W: capture_screenshot (session)
    alt fresh pendingCapture from a toolbar-icon click (&le; 60 s)
        W->>W: validate PNG, TTL and same-conversation URL
        Note over W: mismatch → SCREENSHOT_TARGET_MISMATCH
        W-->>S: authorized capture (consumed exactly once)
    else no usable click authorization
        W->>T: chrome.debugger.attach(tabId, "1.3")
        W->>T: Page.captureScreenshot {format: "png"}
        W->>T: debugger.detach (immediately)
        Note over W,T: Chrome shows its standard<br/>"debugging" banner during capture
        W-->>S: data:image/png;base64,…
    end
```

The toolbar-click path stays primary: it is the explicit per-shot consent
grant. The CDP fallback exists so unattended local automation (self-tests,
missions) never blocks on physical input. Both paths only ever touch the tab
the Cortex session is bound to; the extension still requests no `<all_urls>`,
cookie, or history access.

## Why `debugger` and not `<all_urls>`

`chrome.tabs.captureVisibleTab` accepts only `<all_urls>` or an `activeTab`
grant — a `chatgpt.com` host permission is refused (verified live). Widening
to `<all_urls>` would expose every site the user visits. The `debugger`
permission, combined with the existing `https://chatgpt.com/*` host
permission, scopes CDP capture to ChatGPT tabs only.
