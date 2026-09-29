# Evan Agent — project-local preview

From the project you want Evan to read:

```sh
EVAN_CHAT_MODEL=provider/chat-model EVAN_CODING_MODEL=provider/coding-model /Users/evanmotovich/fusion-harness/tools/evan/evan
```

Use exact Pi-configured model IDs. `--check` validates only their syntax, not authentication. There is no global `evan` installation. The TUI uses an app-owned persistent chat session and explicitly loads Evan's theme, commands and the standalone self-compact extension; Fusion is **not** loaded by default. Normal chat has `read,grep,find,ls`, not write or shell. The identity prompt is `IDENTITY.md` (not the Fusion temporary writer prompt).

In the TUI:

- `/evan-code relative/file :: objective` explicitly grants one exact file to a separate coding-model session. It can read or replace that file with an expected SHA256. It has no shell, Git, messaging, deployment, or test tool; an existing parent directory is required. A readback is not a passing test.
- `/evan-cancel` requests cancellation of this process's owned coding run; prior edits are not rolled back.
- `/evan-runs` shows owned receipts. Unknown cost is shown as **unknown**, never zero. Foreign-agent status is not verified or universally visible.
- `/self-compact [note]` invokes Pi's native compaction with editable instructions from `.pi/self-compact/` or a fallback. `--compactions-soft-at`, `--compactions-at`, `--compact-buffer`, `--compact-prompt` and the two singular aliases are supported by the local launcher. The prompt flag supplies additional summarizer instructions, not a full replacement system prompt. Compacted prose cannot confer permissions.

The worker records its run under `tools/evan/.state/` (gitignored). It may be **uncertain** after a restart; it is not automatically replayed. The run panel is an owned-run view, not a whole-machine supervisor. This is a restricted file-operation adapter, **not** an OS sandbox. Do not use it as a security boundary for hostile same-user processes or untrusted project code. No live provider chat or coding call, terminal UX, exact-model authentication, or paid compaction continuation was proved by the offline tests in this slice. Telegram/WhatsApp, autonomous project decisions, full tool inventory/admission, optional Fusion wiring, and a globally installed command remain outside this preview.

Offline checks: `bun test tools/evan/*.test.ts extensions/self-compact/self-compact.test.ts`. No commit, installation, or publication is implied.

---
Governed by AGENTS.md — see the repository rules for authorization boundaries.
