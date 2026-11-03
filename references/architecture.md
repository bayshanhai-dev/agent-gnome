# Architecture Notes

This document describes the runtime behind the agent-gnome skill. It is a
design contract, not a prescription for one implementation.

## Component diagram

```text
                         watches / signs in / takes over
                 +--------------------------------------------+
                 |                 The human                  |
                 +---------------------+----------------------+
                                       |
                                       v
                 +--------------------------------------------+
                 |       Remote Linux desktop session         |
                 |  display + pointer + keyboard + workspaces  |
                 +---------------------+----------------------+
                                       |
                                       v
                 +--------------------------------------------+
                 |        Visible Chrome instance             |
                 |   windows, tabs, contexts, signed-in state  |
                 +---------------------+----------------------+
                                       ^
                                       | CDP over localhost only
          +----------------------------+----------------------------+
          |                            |                            |
 +--------+--------+          +--------+--------+          +--------+--------+
 |  Agent session  |          |  Agent session  |          |  Health jobs   |
 |  window + tab   |          |  window + tab   |          | restart/watch  |
 |  workspace      |          |  workspace      |          | reap/notify    |
 +-----------------+          +-----------------+          +-----------------+
          |                            |
          +------------ pointer lock --+
                       one real pointer
```

The human is the owner of the login and the visible desktop. Chrome is the
shared execution surface. CDP is a local control channel, not a network
service. Agent sessions coordinate through ownership records and a pointer
lock; they must not coordinate by guessing from tab titles alone.

## Window and workspace isolation

An agent session receives exactly one Chrome window and exactly one virtual
desktop workspace. Its session record should include a unique session ID, the
window identity, the workspace identity, the browser context, the current tab
target, and the lock state. The record must not include cookies, tokens, or
credential values.

Before an action, validate all of the following:

1. The session record is active and belongs to the requesting agent.
2. The target window belongs to that session.
3. The target tab belongs to that window and has not been transferred.
4. The browser context is the expected context for the task.
5. The workspace is visible or can be focused without interrupting a human
   takeover.

If any check fails, refuse the action. In particular, never use a tab found in
another session's window just because it has the desired URL. Reattach to the
agent's own target or ask the human to resolve ownership.

A workspace prevents visual collisions. A browser context provides storage
isolation for cookies, local storage, permissions, and related state. Use a new
context when sessions need separate login state; do not claim that a separate
workspace isolates cookies.

## Pointer lock

The remote desktop has one real pointer and one active keyboard focus. The
pointer lock is a short-lived lease with an owner, acquisition time, last
activity time, and safe expiration behavior. A session must hold the lease
before moving the pointer, focusing a window, typing, clicking, dragging, or
recording pointer-driven evidence.

The lock should:

- be acquired only after the session has passed window and tab ownership checks;
- be released when the action sequence ends or the human requests control;
- expire abandoned leases without clicking or typing as part of cleanup; and
- make contention visible to the waiting agent and the human.

Parallel agents may inspect isolated pages when their work does not change
visible focus. Pointer-driven work is serialized. If the human moves the
pointer or changes focus, treat that as a takeover signal, release the lock,
and revalidate state before continuing.

## Health-job responsibilities

Health jobs are small, observable maintenance loops. They should:

- detect a Chrome or desktop-session crash and restart only the affected
  component when safe;
- preserve a record of which sessions were active without preserving secrets;
- identify stale tabs using ownership, last activity, and an explicit timeout;
- monitor login presence, process health, memory pressure, and CDP reachability;
- release abandoned pointer leases safely;
- notify the human only when a condition changes, not on every polling cycle;
  and
- leave a concise reason for each restart, reaped tab, released lease, or
  login-state transition.

Health jobs must not submit forms, click dangerous buttons, alter account
settings, or silently reauthenticate. If a login expires, notify the human and
wait for visible human sign-in. If a resource is under pressure, prefer a
graceful pause and notification to destroying an active session.

## Failure modes and recovery

### Chrome or desktop crash

Mark affected sessions unavailable, stop their actions, and restart the minimum
necessary component. Do not claim that a pending outward-facing action
succeeded. After recovery, ask the human to restore login if needed, then
reacquire window, context, tab, and pointer ownership from scratch.

### CDP disconnect

Stop issuing commands. Recheck localhost reachability and Chrome health, then
reattach only to the session's owned window and tab. Re-read the page state
before repeating any action. A disconnect after a write is an unknown outcome;
verify before retrying.

### Login expiration

Pause work and notify the human. Do not inspect or relay credentials, cookies,
tokens, or recovery codes. Resume only after the human restores access in the
visible browser and the agent confirms the expected page without exposing
secret material.

### Stale tab or abandoned lock

Reap or release only when ownership and the configured timeout make staleness
unambiguous. Never reclaim a tab or pointer lease from an active session. If
uncertain, preserve the state and ask the human.

### Ownership conflict

Refuse the operation. Do not force focus, steal a window, or click a tab owned
by another agent. Report the session and target identifiers needed to resolve
the conflict, omitting sensitive page content.

### Human takeover

Release the lock, pause scripted interaction, and let the human act. On return,
reinspect the URL, page identity, selected tab, form state, and login state.
Discard stale element handles and do not assume that a partially completed
action can be safely repeated.

### Unexpected outward-facing control

Stop at the control. Classify it as gated, explain its target and consequence,
and request the exact confirmation flag required by the safety model. Never
click first and ask afterward.
