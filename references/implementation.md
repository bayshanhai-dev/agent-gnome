# How an agent operates a GNOME desktop

This document describes the practical control stack for a human-watchable
GNOME session. The desktop is the substrate. Chrome is the primary browser tool
inside that session, but an agent can operate other visible desktop applications
through the same observation, input, ownership, and safety rules.

## The session substrate

The target is a real GNOME session with a display, windows, keyboard focus,
workspaces, and one real pointer. It may be local to the machine running the
agent, or remote through RDP or VNC so a human can watch the same display and
take over. The agent either runs inside that session or attaches to it locally;
the control path should not create a second invisible desktop that the human
cannot inspect.

Treat the session as one shared physical workspace. There is one active pointer
and one keyboard focus, even if several agent processes have isolated windows
or workspaces. Before visible interaction, identify the session, window,
workspace, and target application, then acquire the pointer lock described in
`architecture.md`. Release it when the action sequence ends or the human asks
to take over.

## Layer 1 — semantic control (AT-SPI)

GNOME applications expose an accessibility tree through AT-SPI over D-Bus. The
tree can provide roles, accessible names, states, relationships, and screen
coordinates for controls and containers. An agent can inspect that structure
and target a control by role and name rather than guessing from pixels.

Tools such as `pyatspi` and `dogtail` can read the tree and invoke supported
actions, including clicking a button or setting text in an entry. A typical
semantic operation is:

1. Find the active application and its window in the accessibility tree.
2. Locate a control by its role and accessible name.
3. Check its state and whether the requested action is available.
4. Invoke the action, then re-read the relevant subtree.

This is normally the fastest and most reliable layer. It remains grounded in
the live application state and is less sensitive to window size, theme, and
pixel position. It is weaker for canvas-style UIs, custom-drawn controls, and
applications whose accessibility coverage is incomplete or inaccurate. When a
needed object is absent or its action cannot be invoked safely, use the next
layer rather than guessing an object name.

## Layer 2 — visual control

Visual control combines a current screenshot with vision-model grounding and
virtual keyboard or mouse input. On X11, use an X11 capture tool for the
relevant display. In a remote session, use the session's frame capture when
that is the authoritative view the human is watching. Inject input with
`xdotool` on X11, or with `ydotool` and `uinput` on Wayland where the setup
permits it.

This layer works on anything visible, including custom canvases and controls
that do not appear in AT-SPI. It costs more time and is more fragile: window
moves, scaling, theme changes, scrolling, and overlays can cause coordinate
drift. Take a fresh screenshot after every meaningful step, use the visible
pointer, and verify that the expected state changed before continuing. Never
reuse coordinates after focus, window geometry, or scroll position may have
changed.

## Layer 3 — browser control

Chrome runs inside the GNOME session and can be driven over CDP bound to
localhost only. This is the most structured layer for browser pages: it can
inspect the page, wait for stable state, extract authorized visible data, and
perform approved UI work while the human watches the same window.

Use the browser layer only with the ownership, pointer-lock, confirmation, and
secret-handling rules in `SKILL.md`. The detailed component model, isolation
rules, and recovery behavior are in [architecture.md](architecture.md).

### Electron apps: the CDP GUI layer

Electron desktop apps are Chromium renderers, but their custom UI may not appear
in AT-SPI. When semantic control is unavailable, launch the app with a
localhost-only remote debugging port and connect to its renderer over CDP. Read
the visible DOM for labels and element geometry, then drive the real window with
CDP input events such as `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`,
and `Input.insertText`. Use renderer JavaScript only to observe UI state and
target controls; do not mutate the document through internal app APIs.

Apply the same localhost-only safety rule as the browser layer: bind remote
debugging to loopback, keep the session and window human-watchable, and follow
the ownership, pointer-lock, confirmation, and verification rules.

## The control loop

Every desktop task follows the same loop:

```text
observe (tree or screenshot)
    -> decide
    -> act at the highest layer that can do the step
    -> verify by re-observing
    -> repeat
```

Start with AT-SPI when the target is exposed clearly. Use screenshots and
virtual input when the semantic tree cannot see or perform the step. Use CDP
when the target is inside Chrome and page-level structure is more useful than
desktop-level coordinates. Escalate down a layer when the higher layer cannot
see the target, cannot express the action, or returns an ambiguous result.

Verification is part of the action, not an optional final check. For a read,
confirm that the expected object or text is present. For a local preparation,
confirm the new focus, value, route, or view. For an outward-facing action,
stop at the final control until the exact human confirmation required by the
safety model is present, then verify the visible result without exposing
secrets.

## Human channel

The human watches the same GNOME session through the local display or remote
desktop connection and can take over at any time. Agent actions stay visible:
the real pointer moves, the focused window changes, and typed or clicked input
appears in the session.

When the human takes over, release the pointer lock and pause scripted input.
When control returns, re-observe the accessibility tree or take a new
screenshot. Discard stale element handles and coordinates, and re-check the
active window, workspace, focus, page, and form state before acting again.

## Choosing a layer

| Task type | Preferred layer | Fallback |
| --- | --- | --- |
| Read a standard GNOME button, menu, or text field | AT-SPI | Screenshot plus virtual input |
| Set text or activate a named accessible control | AT-SPI | Screenshot plus virtual input |
| Operate a canvas, custom drawing, or inaccessible widget | Screenshot plus virtual input | Ask the human or use a supported app path |
| Inspect or operate a Chrome page with structured DOM state | Localhost CDP | AT-SPI, then screenshot plus virtual input |
| Prove what the human saw on screen | Screenshot or remote frame capture | AT-SPI state, if sufficient |
| Perform a consequential action | Highest reliable layer, with confirmation gate | Stop and ask the human |

The preferred layer is a reliability choice, not permission to bypass safety
checks. A lower-level click, keypress, or CDP call remains subject to the same
ownership and confirmation requirements.

## Failure modes

### Stale coordinates

Coordinates become invalid after a window moves, a workspace changes, a page
scrolls, display scaling changes, or a dialog appears. Re-observe immediately
before visual input and re-screenshot after each step. Prefer AT-SPI or CDP
handles when they expose the needed target.

### Focus theft and concurrent agents

Another agent or the human can change focus while an agent is preparing input.
Mitigate this with per-agent workspaces, explicit window and tab ownership, and
the pointer lock described in `architecture.md`. If ownership or focus is
uncertain, stop; do not force focus or click another session's window.

### Wayland restrictions

Wayland limits global input injection and screen capture compared with X11.
Where policy and local configuration permit, a `uinput`-based path such as
`ydotool` can provide virtual input, and the remote session's frame capture can
provide the authoritative screenshot. If capture or injection is unavailable,
fall back to AT-SPI or ask the human to perform the step. Do not weaken the
session's isolation merely to obtain global input.

### Ambiguous results

After a crash, disconnect, human takeover, or lost input event, the action may
have an unknown outcome. Stop issuing commands, re-observe the session, and
verify before retrying. Never repeat a consequential action solely because the
first attempt did not return a clear response.
