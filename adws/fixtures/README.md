# Builder fixtures

Stub mode loads these instead of calling a model. Zero keys, zero network.

## Seat fixtures (shared)

`good_<seat>.json` / `bad_<seat>.json` for the four seats in
`adws/prompts/`. The good files prove each seat's gate passes on a correct
envelope; the bad files (`_invalid: true`) fail it on attempt 1 so
`--stub-bad-first` exercises the FAIL → SOFT NOTICE → PASS retry path. The
shared good files are NOT used for the named stems below
(`agents.fixture_file` refuses them there).

## Named-stem fixtures

A request file whose stem matches gets fixture-driven behavior for one DoD
check each:

| Request stem | Fixtures | Proves |
| --- | --- | --- |
| `unmeetable-requirement` | `good_spec_writer.unmeetable-requirement.json` | one blocked requirement with a recorded blocker, the rest verified; exit 4, not silence (R10) |
| `memory_search` | `preflight/memory_search.json` overlay | a request naming an uninstalled tool is a preflight blocker; zero agent launches (R1/E1) |
| `out-of-scope-write` | `good_builder.out-of-scope-write.json` | a fill claiming a path outside `adws/built/<name>/` fails `diff_claims_real`; the run is not accepted |

## Requests (`requests/`)

| File | Expected |
| --- | --- |
| `toy_complete.md` | exit 0: spec, build, validate, register; every agent phase logs AGENT → GATE |
| `toy_vague.md` | exit 3 `needs_human` with questions; nothing built. A vague request is never narrowed by inventing facts — unknowns would be `<EVAN: fill>` markers in any spec, and the intake blocks instead of guessing |
| `refusal_poem.md` | exit 2 `not_workflow` |
| `refusal_edit_sssf.md` | exit 2 `forbidden_target` |
| `refusal_push_deploy.md` | exit 2 `forbidden_target` |

The request text of `toy_complete.md` is byte-identical to
`request_verbatim` in `good_spec_writer.json`, so the shared spec fixture is
coherent with the request that selects it.
