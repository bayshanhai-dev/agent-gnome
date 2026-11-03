---
name: agent-gnome
description: An agent skill for operating a GNOME desktop session (semantic accessibility control, visual input fallback, and a shared logged-in Chrome via localhost CDP) in a human-watchable remote Linux desktop.
---

# Agent GNOME

Use this skill to operate a real GNOME desktop session that is visible to a
human. Chrome is the primary in-session tool for browser work. The human signs
in once, and agents attach to the already signed-in browser through the local
Chrome DevTools Protocol (CDP).

The browser layer is a fallback. It is not a way around access controls, site rules,
approval requirements, or a site's prohibition on automation.

## Overview

The desktop session is the substrate. Control has three layers, in priority
order:

1. Semantic control through the AT-SPI accessibility tree.
2. Visual control through screenshots plus virtual keyboard and mouse input.
3. Browser control through CDP.

The rest of this skill details layer 3 and the shared safety and session model
that applies to all three layers. The safety rules below apply to desktop
actions as well as browser actions.

Prefer a direct API or connector when it covers the task. Choose the browser
layer when one of these cases matters:

1. The page is available only after the human signs in and there is no suitable
   authorized API or connector.
2. The useful behavior exists in a JavaScript-heavy UI with no practical API
   surface for the task.
3. The human wants to watch the work, take over, or receive screenshots as
   evidence of what happened.

Treat the browser as an observable execution surface, not as a credential
store. You may use the signed-in state to read pages and perform approved
work, but you must not obtain, copy, print, or expose secrets that make the
session possible.

## Architecture

The system has these boundaries:

- A visible Chrome instance runs inside a remote Linux desktop session.
- The human signs in through that visible browser and can watch the display.
- Agents attach to Chrome over CDP bound to localhost only.
- Every agent session owns exactly one browser window and one virtual desktop
  workspace.
- A pointer lock serializes use of the one real pointer and keyboard focus.
- An agent is refused if it tries to touch tabs owned by another session.

Keep ownership explicit. Before acting, identify the session, its window, its
workspace, and the tab target. Do not discover a target by taking over another
agent's window. If ownership is missing or ambiguous, stop and report that the
session cannot safely proceed.

Use a separate browser context when two sessions need isolated cookies or
other isolated browser state. A workspace separates visible interaction; a
browser context separates storage. Do not treat one as a replacement for the
other.

For the detailed component model, isolation rules, and recovery behavior, read
`references/architecture.md` when planning or debugging the runtime.

## Operating principles

### Make few, information-rich calls

Prefer a single call that opens the target, waits for the expected state, and
extracts the useful result. Do not spend a call on every trivial observation.
Each action should report what changed, including the target URL or page
identity, the important state transition, and any evidence captured.

When a call fails, report the last known state and the smallest safe next step.
Do not blindly repeat clicks or navigation that could duplicate an action.

### Keep the human in the loop visually

Move the visible pointer to the target before interacting. Keep the relevant
window in view so the human can follow the sequence or take over. Do not hide
the browser, teleport the pointer without explanation, or use an invisible
interaction path when a visible one is available.

When the human takes over, release the pointer lock and wait for the session to
be available again. Re-check the page after control returns; the human may have
changed the active tab, route, or form state.

### Learn a site once, then reuse the result

For a repeated workflow, inspect the page's authorized data endpoints and the
relationship between the visible controls and the data they consume. Save a
small, auditable automation for the stable parts. Revalidate assumptions when
the page changes, and keep a visible browser path for steps that require the
human or a UI-only interaction.

Do not use endpoint inspection to defeat authentication, rate limits, access
controls, or anti-automation restrictions. Do not replay a saved automation on
a different account or context without checking ownership and authorization.

## Safety rules

These are hard requirements. Treat a violation as a failed run.

1. Never read, copy, log, transmit, or expose credentials, session tokens,
   cookies, local-storage secrets, recovery codes, or similar secrets.
2. Bind the CDP port to localhost only. Never make the debugging endpoint
   reachable from the network or from an untrusted container boundary.
3. Reading pages, inspecting visible structure, and taking non-sensitive
   screenshots need no approval.
4. Any outward-facing or irreversible action requires the human's explicit
   confirmation. This includes sending, submitting, publishing, approving,
   deleting, paying, or an equivalent action with real-world effect.
5. Enforce that requirement by refusing to click or activate a dangerous
   control unless the request carries an explicit confirmation flag such as
   `confirmed_by_human: true` for that exact action.
6. Do not infer confirmation from a general instruction, a prior approval, a
   page state, a typed value, or the fact that a button is enabled.
7. Never use the browser to circumvent a policy restriction, access control,
   paywall, rate limit, consent requirement, or site rule.

When the action class is uncertain, treat it as outward-facing and ask for
confirmation. The confirmation must identify the action and its target well
enough for the human to understand what will happen.

For the full action-gating model, denylist concept, secret-handling rules, and
audit expectations, read `references/safety-model.md`.

## Session workflow

Follow this sequence for ordinary work:

1. Confirm that the remote Linux desktop session, Chrome, the expected browser
   context, and the login state are alive.
2. Claim or verify one agent session, exactly one window, and its virtual
   desktop workspace.
3. Acquire the pointer lock. If another session holds it, wait or report the
   conflict; never force focus.
4. Attach through localhost CDP and select only a tab owned by this session.
5. Navigate or inspect using a few information-rich calls. Wait for a stable
   state before extracting.
6. Classify every proposed action as read-only, reversible local preparation,
   or outward-facing/irreversible.
7. Complete read-only work immediately. For a gated action, stop at the final
   control until `confirmed_by_human: true` is supplied for that exact action.
8. Move the visible pointer, perform the approved action, and report exactly
   what changed.
9. Capture a suitable screenshot or other evidence when requested, excluding
   credentials, cookies, tokens, and unrelated private data.
10. Release the pointer lock and leave the browser in a clear, recoverable
    state. Do not close another session's tabs.

Do not assume that a successful click means the task succeeded. Verify the
result from the visible page or an authorized response, and distinguish a
queued operation from a completed one.

## Session hygiene

Use background health jobs to keep the shared runtime usable. They may:

- restart Chrome after a crash, subject to preserving the human's ability to
  sign in again;
- reap stale tabs only when ownership and staleness are unambiguous;
- watch login state, browser health, and memory pressure;
- release abandoned locks after a safe timeout; and
- notify the human only when the monitored state changes.

Health jobs must not silently submit forms, change account settings, or perform
other outward-facing actions. They should record enough state to explain a
restart, reclaimed tab, expired login, or released lock without recording
secrets.

Use separate browser contexts when sessions need isolated cookies. If a login
expires, tell the human what is needed and wait for the human to restore it in
the visible browser. Never ask the agent to extract or relay the credential.

## Extras

The pattern can support two useful evidence features:

- Element-only screenshots that crop to the relevant page element while
  excluding unrelated tabs, desktop content, and sensitive fields.
- Scripted demo recordings with captions and optional voice-over. Record only
  the intended window and redact or omit sensitive states before sharing.

These features do not weaken action gating or secret-handling rules.

## Constraints

This pattern works only while the desktop session and the human's login are
alive. Some authentication flows, device challenges, passkeys, or consent
steps cannot be performed by the browser automation and must remain on an API
tool or with the human. Use the browser only when the site's terms and the
task's authorization allow it.

There is one machine, one pointer, and one display. Parallel agents can share
the runtime only through ownership, workspace isolation, browser-context
isolation where needed, and the pointer lock. Parallel reads are possible when
their windows and targets are isolated; pointer-driven actions remain
serialized.

## When NOT to use this

Do not use the browser layer when:

- an API or connector exists and covers the task adequately;
- the site forbids automation or the requested activity is not authorized; or
- the task does not need login state, visible UI, or browser-only behavior.

When one of these conditions applies, use the appropriate authorized path or
tell the human why the browser fallback is unavailable.
