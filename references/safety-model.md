# Safety Model

This skill combines a signed-in state with a real UI. The safety model
therefore separates observation from actions that can affect another person,
an account, or the outside world.

## Action classes

### Read actions

Read actions observe state without changing the remote system. Examples include
opening a page, waiting for it to render, reading visible text, inspecting
non-sensitive structure, checking an authorized response, and taking a
non-sensitive screenshot. These actions need no human approval, but they still
require correct window, workspace, context, and tab ownership.

### Local preparation

Local preparation changes only the agent's current browser state and is
reversible in the ordinary workflow. Examples include scrolling, changing a
temporary view filter, filling a non-sensitive draft field, or opening a
review page. Treat a control as gated if the preparation itself causes a
network mutation, saves state, notifies someone, or has an unclear consequence.

### Gated actions

Gated actions are outward-facing or irreversible. They include sending,
submitting, publishing, approving, deleting, paying, changing permissions,
confirming a purchase, accepting a consequential consent, and equivalent
actions. A submit-like control remains gated even when its result appears
reversible or when the page calls it a draft.

## Confirmation flag

The agent may perform a gated action only when the request carries an explicit
confirmation flag for that exact action, for example:

```text
confirmed_by_human: true
target: the specific message, record, or page action
consequence: a short description of what will happen
```

The flag is not a standing permission. It must be associated with the current
target and intended consequence. Do not infer it from a general instruction,
earlier approval, a pre-filled form, an enabled button, or the presence of a
human somewhere on the desktop.

If the flag is absent, malformed, stale, or ambiguous, stop before the final
control and ask the human to confirm. Do not move past the final review point
in a way that triggers the action.

The enforcement point should be as close as possible to the actual click,
keyboard submission, or equivalent CDP event. A wrapper that merely asks for
confirmation earlier is not sufficient if a later path can bypass it.

## Button-label denylist concept

Use a denylist as a conservative signal for controls that commonly cause
external effects. It should cover labels and accessible names such as:

```text
send, submit, publish, approve, delete, remove, pay, purchase,
confirm, accept, apply, finalize, place order, invite, transfer
```

This list is not complete and is not the only gate. Also inspect the element
role, form action, surrounding copy, confirmation dialogs, keyboard shortcuts,
and the page behavior. A non-denylisted label can still be gated, and a
denylisted label can be a harmless navigation control only after the action
classifier has established that it has no outward effect.

When classification is uncertain, fail closed: treat the control as gated.
Refuse clicks, Enter-key submissions, form submissions, drag-to-confirm
gestures, and equivalent activation paths without the exact confirmation flag.

## Credential and cookie handling

The browser's signed-in state is available for authorized page work, not for
secret extraction. Never read, copy, print, serialize, transmit, or expose:

- passwords, passkeys, one-time codes, recovery codes, or security answers;
- cookies, session tokens, bearer tokens, authorization headers, or CDP
  authentication material;
- local-storage or indexed-database values that function as credentials; or
- screenshots, logs, traces, or recordings that reveal any of the above.

Avoid selecting secret fields during extraction. Redact sensitive values from
logs and screenshots. If a page exposes a secret in visible text, do not repeat
it; report only that sensitive content was present. If a task requires a
credential or device challenge, ask the human to complete it in the visible
browser.

## Localhost-only CDP

The CDP endpoint must bind to localhost only. Do not expose it through a public
interface, a network listener, an untrusted proxy, or a shared socket whose
access cannot be audited. Validate the endpoint and the target session before
attaching. A successful CDP connection does not grant permission to inspect
other sessions, cookies, storage, or credentials.

## Ownership and visibility

Safety checks include more than the action classifier:

- the agent owns the selected window, tab, workspace, and browser context;
- the pointer lock is held before visible interaction;
- the human can see the relevant state and can take over; and
- the agent will not capture unrelated private content in evidence.

If ownership, visibility, or lock state is unclear, pause rather than guessing.

## Audit expectations

Record an audit event for each meaningful action without recording secrets. A
useful event includes:

- timestamp and agent-session identifier;
- window, workspace, context, and target identifiers;
- action class and a short, non-sensitive description;
- whether the action was read-only, prepared locally, or gated;
- whether `confirmed_by_human: true` was present for a gated action;
- the visible result or verification state; and
- failures, retries, lock changes, ownership conflicts, or human takeovers.

Do not log full page HTML, raw headers, cookies, tokens, passwords, or
unredacted screenshots. Keep audit records long enough to explain a run and
its recovery, and make state changes—not polling noise—the basis for health
notifications.

## Refusal behavior

Refusal is a normal safety outcome. State the non-sensitive reason, identify the
missing condition, and offer the smallest safe next step. Examples are:

- “The control may submit externally; provide exact human confirmation before
  activation.”
- “The selected tab belongs to another session; choose an owned target.”
- “Login has expired; the human must restore it in the visible browser.”
- “The CDP endpoint is not localhost-only; do not attach.”

Never bypass a refusal by using a lower-level click, direct request, script,
keyboard shortcut, or inspected data endpoint.
