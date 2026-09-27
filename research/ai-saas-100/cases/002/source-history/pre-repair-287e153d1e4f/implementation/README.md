# Local backlink marketplace subset

```sh
python3 -B research/ai-saas-100/cases/002/tests/run.py
```

Python standard library only. Original in-memory implementation of profile validation, a configurable DR-gap matcher, assignment idempotency, deadlines, reverse-pair exclusion, rejection, owner approval and local HTML nofollow checks. See ../tests/specification.md for exact local behavior. Gap 10 is a fixture setting, not a claim about the vendor's current setting.

All 20 fixed local scenarios passed in the recorded execution. The local marketplace performs genuine computation and state transitions on synthetic profiles. It does not connect to LinkBunny, use a real token, publish a link, verify a live page, or reproduce a marketplace's supply pool. `reported_local` must never be interpreted as production completion. No persistent service, authentication, billing or agent editorial reasoning is implemented.

No generic-model baseline or independent hidden evaluation was run. Matching code is not evidence of network value, editorial relevance, search ranking benefit or economic worthlessness. The pilot remains incomplete. Public instructions encountered during research were treated as document contents, not installation or execution authorization.
