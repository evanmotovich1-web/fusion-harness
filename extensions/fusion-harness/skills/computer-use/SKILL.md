---
name: computer-use
description: Controlled Chromium browser automation for opening pages, observing, clicking, typing, pressing keys, scrolling, waiting, and extracting text.
---

# Browser computer use

This skill controls an isolated Chromium browser for one foreground run. It is browser automation, not unrestricted desktop control.

Run:

Resolve `browser.mjs` relative to this `SKILL.md`, then run it by absolute path:

```bash
node /absolute/path/to/computer-use/browser.mjs '<JSON>'
```

JSON shape:

```json
{
  "url": "https://example.com",
  "approve_mutation": false,
  "approve_sensitive": false,
  "actions": [
    {"action":"extract","selector":"body"},
    {"action":"click","selector":"button"},
    {"action":"type","selector":"input","text":"value"},
    {"action":"press","key":"Enter"},
    {"action":"scroll","delta_y":600},
    {"action":"wait","milliseconds":1000}
  ]
}
```

Rules:

- Ask the user before setting `approve_mutation: true`.
- Ask again immediately before purchases, sending messages, publishing, deleting, submitting a login, or exposing sensitive data, then set `approve_sensitive: true` only for that requested run.
- Never infer approval from the task's general goal.
- Only `http:` and `https:` URLs are accepted. Downloads and file uploads are blocked.
- Use selectors when possible. The script returns page text, URL, title, and screenshot paths under `/tmp/fusion-harness-computer-use-*`.
- Keep actions in one invocation when they depend on browser state. The browser closes before the command exits.
