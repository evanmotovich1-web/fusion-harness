# DuckDB v2.0 preview SQL lab

Compact teaching lab for the SQL surfaces announced in the [DuckDB v2.0 highlights](https://duckdb.org/2026/08/17/duckdb-20-highlights) post (2026-08-17). Codename: **Cyanoptera**.

This is a **preview** lab. A green `LAB_SUCCESS` is only legal after `run.sh` detects DuckDB **major version ≥ 2** *and* `lab.sql` finishes without error. Older binaries that happen to store `VARIANT` or accept `SET VARIABLE` are **not** a pass.

Measured on this machine: `~/.duckdb/cli/latest` points at **v1.5.5 (Variegata)** again. The alpha binary remains at `~/.duckdb/cli/v2.0.0-alpha43385/duckdb` (`ca15f79c32`, Cyanoptera). `quack` is installed for that alpha only. `run.sh` skips PATH 1.5.5 and uses the preview binary when it is present.

## What it teaches

1. First-class **`VARIANT`**: storage, `variant_type` / `variant_keys` extraction, `variant_contains`.
2. **`BEFORE` / `AFTER` triggers** with an audit table. AFTER uses `REFERENCING OLD/NEW TABLE`; this alpha's BEFORE is a statement-level marker only.
3. **DML inside a `MATERIALIZED` CTE** using `DELETE … RETURNING *`.
4. **SQL variables** (`SET VARIABLE threshold = 100` then `$threshold` in expressions).
5. Nested schemas (`finance.reports`), `json_set` / `json_insert` / `json_replace` / `json_remove`, `FETCH FIRST`, `OVERLAY`, `UNNEST` in `GROUP BY`, `MERGE`, and `APPROX NEAREST` joins.
6. `dialect_compatibility_mode = spark`, and `AT TIME ZONE 'Europe/Paris'`.

Not run here, and not claimed: a live `quack_serve` / `CONNECT` session (the extension is installed and `LOAD quack` works; no server was left running), asynchronous I/O, a written storage-format v2 file, and the stable C API. `USING KEY` runs on this alpha but returns `b=0.0`, not the blog's `2.5`.

## Prerequisites

- A DuckDB CLI. Resolution order: `DUCKDB` env, then `PATH` if that binary is already v2, then `~/.duckdb/cli/v2*/duckdb`.
- For a real pass: a **v2.0 preview** build (`library_version` major ≥ 2, typically codename Cyanoptera).
- No network, no credentials, no persistent database file. The runner uses an in-memory session.

## Preview warning

DuckDB v1.5 already has a `VARIANT` type, `SET VARIABLE`, `RETURNING`, and `MATERIALIZED` CTEs. The v2.0 pieces this lab is for are:

| Surface | v2 announcement | Measured on v1.5.5 (Variegata) |
|---|---|---|
| `variant_type` / `variant_keys` / `variant_contains` | first-class shredded VARIANT | `variant_typeof` exists; `variant_type`, `variant_keys`, `variant_contains` do not |
| `CREATE TRIGGER` BEFORE/AFTER | full trigger support | parser error at `TRIGGER` |
| DML inside `WITH … AS MATERIALIZED` | INSERT/UPDATE/DELETE/COPY as CTE steps | `Parser Error: A CTE needs a SELECT` |
| `$threshold` | expression-level variables | treated as a prepared-statement parameter |

Do not read a 1.x diagnostic (`typeof(payload) = VARIANT`, `getvariable`) as v2 success.

## Run

```bash
cd duckdb20_fusion_lab
./run.sh
```

Optional:

```bash
DUCKDB=/path/to/duckdb-v2 ./run.sh          # pin a preview binary
duckdb -bail -f lab.sql                     # v2 only; skips the version gate
```

`run.sh` will:

1. Resolve the binary (`DUCKDB`, then v2 on `PATH`, then `~/.duckdb/cli/v2*/duckdb`). Print `duckdb_selection`.
2. Print `library_version`, `source_id`, and `codename` from `pragma_version()`.
3. Probe the four preview surfaces in isolation and print `feature.<name>=supported|unsupported`.
4. **If major < 2:** print `status=INCOMPATIBLE_NOT_V2`, extra 1.x diagnostics, and **exit 2**. It will not print `LAB_SUCCESS`.
5. **If major ≥ 2:** run `lab.sql` with `-bail`. Print `status=LAB_SUCCESS` only if every assertion passes; otherwise `status=LAB_FAIL`.

## Expected observations

### v2.0 preview (measured: alpha43385 Cyanoptera)

- Two `VARIANT` rows; containment matches only `user.id = 42`. `variant_type` returns `OBJECT`; `variant_keys` returns `varchar[]`.
- `UPDATE target SET val = val * 10` writes three audit rows: one BEFORE statement marker (`note = before`, values null) and two AFTER rows, `(1, 10, 100)` and `(2, 20, 200)`. This alpha rejects `REFERENCING` on BEFORE triggers and rejects `DROP TRIGGER name` without `ON table`.
- `staging` ends empty; `archive` holds the two `RETURNING` rows.
- `$threshold = 100` leaves a single order (`id = 2`, `amount = 150`).
- Nested schema `finance.reports.q3` holds `1.5`. JSON mutation yields `{"a":1,"b":2}`, `{"a":3}`, and `{"a":1}` after remove.
- `FETCH FIRST 2` returns 1 and 2. `overlay` returns `abXYef`. `UNNEST` in `GROUP BY` counts `a=2`, `b=1`.
- `MERGE` updates id 1 to 11 and inserts id 2 at 20. `APPROX NEAREST 1` matches product 10.
- Spark dialect mode sets and resets. `2026-08-14 12:00:00` in `Europe/Paris` is `18:00:00`.
- `USING KEY (a, avg(b))` returns one row with `b=0.0` on alpha43385. The blog shows `2.5`. A plain recursive average of the same rows is `2.5`. The note is not a pass of the blog result.
- `lab.sql` ends with `lab.sql finished (assertions passed)` and `run.sh` prints `status=LAB_SUCCESS` (exit 0).

### Non-v2 binary (example: v1.5.5 Variegata)

- `compatible=no`
- `feature.variant_announced=unsupported`, `feature.triggers=unsupported`, `feature.dml_cte_returning=unsupported`, `feature.sql_variables=unsupported`
- Diagnostics may show `VARIANT` storage and `getvariable` working — still **not** a pass
- `status=INCOMPATIBLE_NOT_V2`, exit code 2

## Cleanup

Nothing to delete on disk: the CLI opens an in-memory database. `lab.sql` also `DROP`s its triggers and tables at the end of a successful v2 run. Re-run `./run.sh` as often as you like.

## Files

| File | Role |
|---|---|
| `lab.sql` | Deterministic setup, examples, `error()` assertions, cleanup |
| `run.sh` | Version gate, honest probes, v2-only lab execution |
| `README.md` | This file |

Source: <https://duckdb.org/2026/08/17/duckdb-20-highlights>
