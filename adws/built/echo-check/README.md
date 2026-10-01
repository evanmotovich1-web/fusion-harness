# Echo Check

Built for the request recorded in config.json. Stub-first. DRY_RUN defaults on.
Live side effects stay off unless a later human switch says otherwise.

Stub run:

    python adw_echo_check.py --fixtures --stub-agents

A bad fixture fails the named gate, the soft notice repeats that failure text, and the retry passes.

Limits: this workflow does not commit, push, or open a network client. Path checks are an allowlist plus a post-run audit, not a sandbox.
