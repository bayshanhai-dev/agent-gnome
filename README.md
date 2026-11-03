# agent-gnome

agent-gnome is a reusable agent skill for operating a real GNOME desktop
session in a remote Linux desktop. Its flagship capability is a shared,
signed-in Chrome inside that session: the human signs in once and can watch
while one or more agents work through local Chrome DevTools Protocol (CDP).

## What it is

This pattern gives agents a visible GNOME desktop substrate with semantic and
visual control, plus a structured browser layer for pages that are available
only after sign-in, interfaces whose useful behavior lives in JavaScript, and
workflows where screenshots or human oversight are part of the evidence. It is
not a replacement for an API, and it must never be used to evade access
controls or site policy.

## The problem

Direct APIs are usually easier to test and operate, but they do not cover every
desktop workflow, page, or account workflow. A real GNOME session makes UI work
observable and lets the human take over. The browser layer preserves the
human's login state while giving agents a structured way to attach, isolate
work, and recover from failures.

## Design principles

- **Watchable:** Chrome remains visible, pointer movement is visible, and the
  human can take over.
- **Safe multi-agent sharing:** each session owns one window and workspace;
  ownership checks and a pointer lock protect the single display.
- **Few information-rich calls:** open, wait, inspect, and extract are combined
  where practical; every action reports what changed.
- **Self-healing:** health jobs notice crashes, stale tabs, expired logins, and
  memory pressure, then recover or notify only when state changes.
- **Learn-once-reuse:** repeated UI work becomes a small, auditable automation
  after the agent understands the page's authorized data paths.

## Safety model

Reading visible pages and taking non-sensitive evidence does not require
approval. Sending, submitting, publishing, approving, deleting, paying, and
similar outward-facing or irreversible actions do. The agent must refuse the
final control unless the request includes an explicit confirmation flag for
that exact action. Credentials, cookies, tokens, and other login material are
never read, copied, logged, or exposed. CDP is localhost-only, and the browser
is never a way around policy or access restrictions.

See [references/safety-model.md](references/safety-model.md) for the detailed
gating and audit model.

## Repository layout

```text
SKILL.md                    Agent-facing instructions
README.md                   Human-facing overview and installation
LICENSE                     MIT license
references/architecture.md  Runtime design and recovery notes
references/safety-model.md  Action gating and secret-handling rules
references/implementation.md How an agent operates a GNOME desktop
```

## Install and use

Copy this folder into the agent's skills directory, preserving `SKILL.md` and
the `references/` folder. The agent can then discover or load the skill by its
name, `agent-gnome`.

Before using it, provide a visible Chrome session inside a remote Linux desktop,
keep CDP bound to localhost, and have the human complete any required sign-in
in that browser. Start with read-only inspection. Ask for explicit confirmation
immediately before an outward-facing or irreversible action.

## Contributing

Contributions are welcome when they keep the pattern generic, auditable, and
safe for human-visible operation. Please avoid adding company names, service-
specific assumptions, credential-handling shortcuts, or instructions that
weaken the confirmation gate.

## License

Released under the MIT License. See [LICENSE](LICENSE).
