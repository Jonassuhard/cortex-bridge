# Conversation-first interface

## Product objective

Cortex Bridge should feel like a local conversation client with execution
capabilities, not like a generic observability dashboard. The user chooses a
ChatGPT conversation, writes in the center composer and follows the complete
orchestration loop without manually moving payloads between products.

## Layout

### Left — conversations

The fixed sidebar contains:

- Cortex Bridge identity
- sidebar collapse control
- search
- new ChatGPT conversation
- new autonomous mission
- project shortcuts
- recent/pinned conversations
- archived-conversation entry
- settings and local account information at the bottom

Rows can communicate idle, unread, generating, mission-running, approval and
transport-error states.

### Center — conversation

The center panel is the primary surface. It contains:

- visible ChatGPT and user messages
- response streaming
- delivery confirmation
- first-response and total latency
- code and image rendering
- execution cards
- policy and approval states
- file/test/browser evidence
- final validation
- a fixed message/mission composer

The UI does not claim to expose private chain-of-thought. It displays only
observable states such as “ChatGPT is generating”, the visible response,
structured decision summaries, active tools and validated evidence.

### Right — pipeline inspector

The right inspector is collapsible and contains concise operational state for:

- ChatGPT transport
- conversation lock
- protocol parser
- policy engine
- active mission/action
- approvals
- Granite/Qwen and Ollama
- model storage volume
- filesystem access
- persistence
- queue and recent events

Raw DOM diagnostics, full protocol JSON and verbose process logs belong in the
Diagnostics settings tab rather than the main conversation.

## Message lifecycle

Outbound messages expose these states:

```text
LOCAL_QUEUED
SENDING_TO_CHATGPT
VISIBLE_IN_CHATGPT
ACKNOWLEDGED
DELIVERY_UNCERTAIN
FAILED
```

Responses expose:

```text
WAITING
GENERATION_STARTED
STREAMING
STABLE
PARSED
INVALID_PROTOCOL
TIMED_OUT
BLOCKED_BY_LOGIN
BLOCKED_BY_CAPTCHA
BLOCKED_BY_RATE_LIMIT
```

Delivery is confirmed by observing the expected message fingerprint in the
locked conversation; a click alone is not considered proof.

## Animation language

Animations are functional rather than decorative:

- slow grid drift and restrained blue halo on the application background
- short message reveal transitions
- spinner for active observable phases
- indeterminate progress for tasks without measurable completion
- state transitions for approvals and validation
- skeletons while a conversation snapshot is loading

`prefers-reduced-motion` disables non-essential animation.

## Settings

Settings are anchored at the bottom of the conversation sidebar and divided
into:

- General
- Models
- Permissions
- Transport
- Runtime
- Storage
- Diagnostics

Model settings include the visible ChatGPT planner model, local Ollama primary
and fallback executors, context and routing. Permission settings keep
`never_delete_files` enforced by the backend.

## Responsive behavior

- Desktop: three columns.
- Medium widths: right inspector becomes an overlay/drawer.
- Small widths: both side panels become drawers and the conversation fills the
  viewport.

The center conversation remains usable at every breakpoint.
