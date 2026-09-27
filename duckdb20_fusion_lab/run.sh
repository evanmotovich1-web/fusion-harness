#!/usr/bin/env bash
# duckdb20_fusion_lab/run.sh
# Detects the installed DuckDB version, runs lab.sql only on v2.0+,
# and never claims success on a non-v2 preview.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LAB_SQL="$ROOT/lab.sql"

if [[ ! -f "$LAB_SQL" ]]; then
  echo "error: missing $LAB_SQL" >&2
  exit 2
fi

duckdb_libver() {
  "$1" -csv -noheader -c "SELECT library_version FROM pragma_version();" 2>/dev/null | head -n 1
}

duckdb_major() {
  printf '%s' "$(duckdb_libver "$1" || true)" | sed -E 's/^v?([0-9]+).*/\1/'
}

is_v2_bin() {
  local m
  m="$(duckdb_major "$1")"
  [[ "$m" =~ ^[0-9]+$ ]] && (( m >= 2 ))
}

find_preview_home() {
  local cli="$HOME/.duckdb/cli" d cand=""
  [[ -d "$cli" ]] || return 1
  for d in "$cli"/v2*/duckdb; do
    if [[ -x "$d" || -f "$d" ]] && is_v2_bin "$d"; then
      cand="$d"
    fi
  done
  [[ -n "$cand" ]] || return 1
  printf '%s\n' "$cand"
}

SELECTION=""
PATH_BIN=""
PATH_VER=""

if [[ -n "${DUCKDB:-}" ]]; then
  BIN="$DUCKDB"
  SELECTION=env
elif command -v duckdb >/dev/null 2>&1; then
  PATH_BIN="$(command -v duckdb)"
  PATH_VER="$(duckdb_libver "$PATH_BIN" || true)"
  if is_v2_bin "$PATH_BIN"; then
    BIN="$PATH_BIN"
    SELECTION=path
  elif PREVIEW_BIN="$(find_preview_home || true)" && [[ -n "$PREVIEW_BIN" ]]; then
    BIN="$PREVIEW_BIN"
    SELECTION=preview_home
  else
    BIN="$PATH_BIN"
    SELECTION=path
  fi
elif PREVIEW_BIN="$(find_preview_home || true)" && [[ -n "$PREVIEW_BIN" ]]; then
  BIN="$PREVIEW_BIN"
  SELECTION=preview_home
else
  echo "error: duckdb binary not found on PATH, DUCKDB, or ~/.duckdb/cli/v2*/duckdb" >&2
  echo "status=DUCKDB_MISSING"
  exit 2
fi

if [[ ! -x "$BIN" && ! -f "$BIN" ]]; then
  echo "error: duckdb binary is not executable: $BIN" >&2
  echo "status=DUCKDB_MISSING"
  exit 2
fi

echo "duckdb_bin=$BIN"
echo "duckdb_selection=$SELECTION"
if [[ -n "$PATH_BIN" && "$SELECTION" == preview_home ]]; then
  echo "duckdb_path_bin=$PATH_BIN"
  echo "duckdb_path_version=$PATH_VER"
  echo "note=PATH duckdb is not v2; using ~/.duckdb/cli preview"
fi

version_row="$("$BIN" -csv -noheader -c "SELECT library_version, source_id, codename FROM pragma_version();")"
libver="$(printf '%s' "$version_row" | cut -d, -f1)"
source_id="$(printf '%s' "$version_row" | cut -d, -f2)"
codename="$(printf '%s' "$version_row" | cut -d, -f3)"
cli_version="$("$BIN" --version 2>/dev/null || true)"

echo "duckdb_version=$libver"
echo "duckdb_source_id=$source_id"
echo "duckdb_codename=$codename"
echo "duckdb_cli_version=$cli_version"

major="$(printf '%s' "$libver" | sed -E 's/^v?([0-9]+).*/\1/')"
if [[ ! "$major" =~ ^[0-9]+$ ]]; then
  echo "error: could not parse major version from '$libver'" >&2
  echo "status=VERSION_UNPARSED"
  echo "Refusing to claim success."
  exit 2
fi

echo "duckdb_major=$major"

compatible=no
if (( major >= 2 )); then
  compatible=yes
fi
echo "compatible=$compatible"

one_line() {
  printf '%s' "$1" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//'
}

probe() {
  local key="$1"
  local sql="$2"
  local out ec
  set +e
  out="$("$BIN" -bail -c "$sql" 2>&1)"
  ec=$?
  set -e
  if [[ $ec -eq 0 ]]; then
    printf 'feature.%s=supported\n' "$key"
  else
    printf 'feature.%s=unsupported\n' "$key"
    printf 'feature.%s.error=%s\n' "$key" "$(one_line "$out")"
  fi
  return 0
}

echo
echo "=== preview-syntax probes (honest, not a pass/fail of the lab) ==="
probe variant_announced \
  "CREATE TABLE events (payload VARIANT); INSERT INTO events VALUES ('{\"user\": {\"id\": 42, \"tags\": [\"a\", \"b\"]}}'::JSON::VARIANT); SELECT variant_type(payload), variant_keys(payload) FROM events; SELECT * FROM events WHERE variant_contains(payload, {'user': {'id': 42}}::VARIANT);"
probe triggers \
  "CREATE TABLE target (id INTEGER, val INTEGER); CREATE TABLE audit (id INTEGER, old_val INTEGER, new_val INTEGER); CREATE TRIGGER trg_audit AFTER UPDATE ON target REFERENCING OLD TABLE AS o NEW TABLE AS n FOR EACH STATEMENT INSERT INTO audit SELECT n.id, o.val, n.val FROM o JOIN n ON o.id = n.id;"
probe dml_cte_returning \
  "CREATE TABLE staging (id INTEGER); CREATE TABLE archive (id INTEGER); INSERT INTO staging VALUES (1); WITH moved AS MATERIALIZED (DELETE FROM staging RETURNING *) INSERT INTO archive SELECT * FROM moved; SELECT * FROM archive;"
probe sql_variables \
  'SET VARIABLE threshold = 100; SELECT 150 > $threshold;'
probe nested_schema \
  "CREATE SCHEMA finance; CREATE SCHEMA finance.reports; CREATE TABLE finance.reports.q3 (revenue DECIMAL); INSERT INTO finance.reports.q3 VALUES (1.5); SELECT * FROM finance.reports.q3;"
probe json_mutation \
  "SELECT json_set('{\"a\":1}', '\$.b', '2'), json_insert('{\"a\":1}', '\$.c', '9'), json_replace('{\"a\":1}', '\$.a', '3'), json_remove('{\"a\":1,\"b\":2}', '\$.b');"
probe using_key \
  "WITH RECURSIVE tbl(a, b) USING KEY (a, avg(b)) AS (SELECT 1, 5 UNION SELECT a, b - 1 FROM tbl WHERE b > 0) TABLE tbl;"
probe fetch_overlay_unnest \
  "SELECT x FROM (VALUES (1),(2),(3)) t(x) ORDER BY x FETCH FIRST 2 ROWS ONLY; SELECT overlay('abcdef' PLACING 'XY' FROM 3 FOR 2); SELECT unnest(tags) FROM (VALUES (['a','b'])) t(tags) GROUP BY unnest(tags);"
probe merge_nearest \
  "CREATE TABLE dst (id INTEGER PRIMARY KEY, v INTEGER); INSERT INTO dst VALUES (1, 10); CREATE TABLE src (id INTEGER, v INTEGER); INSERT INTO src VALUES (2, 20); MERGE INTO dst USING src ON dst.id = src.id WHEN NOT MATCHED THEN INSERT VALUES (src.id, src.v); CREATE TABLE users (user_id INTEGER, embedding FLOAT[2]); CREATE TABLE products (product_id INTEGER, embedding FLOAT[2]); INSERT INTO users VALUES (1, [1.0, 0.0]); INSERT INTO products VALUES (10, [1.0, 0.0]); SELECT q.user_id, t.product_id FROM users q INNER JOIN products t APPROX NEAREST 1 BY SIMILARITY array_cosine_similarity(q.embedding, t.embedding);"
probe dialect_timezone \
  "SET dialect_compatibility_mode = 'spark'; RESET dialect_compatibility_mode; SELECT '2026-08-14 12:00:00'::TIMESTAMPTZ AT TIME ZONE 'Europe/Paris';"
probe quack_loaded \
  "LOAD quack;"

if [[ "$compatible" != "yes" ]]; then
  echo
  echo "=== 1.x diagnostics (not success criteria) ==="
  probe diagnostic_variant_storage \
    "CREATE TABLE events (payload VARIANT); INSERT INTO events VALUES ('{\"user\": {\"id\": 42}}'::JSON::VARIANT); SELECT typeof(payload) FROM events;"
  probe diagnostic_variant_typeof \
    "CREATE TABLE events (payload VARIANT); INSERT INTO events VALUES ('{\"user\": {\"id\": 42}}'::JSON::VARIANT); SELECT variant_typeof(payload) FROM events;"
  probe diagnostic_getvariable \
    "SET VARIABLE threshold = 100; SELECT getvariable('threshold');"
  probe diagnostic_json_set \
    "SELECT json_set('{\"a\":1}', '\$.b', '2');"

  echo
  echo "status=INCOMPATIBLE_NOT_V2"
  echo "Refusing to claim success: installed DuckDB is $libver ($codename), not a v2.0 preview."
  echo "Install a DuckDB v2.0 / Cyanoptera preview, or rerun with DUCKDB=/path/to/v2/duckdb"
  echo "Unsupported preview syntax is listed as feature.*.unsupported above."
  exit 2
fi

echo
echo "=== running lab.sql on v2-compatible binary ==="
set +e
"$BIN" -bail -echo -f "$LAB_SQL"
lab_ec=$?
set -e

if [[ $lab_ec -eq 0 ]]; then
  echo
  echo "status=LAB_SUCCESS"
  exit 0
fi

echo
echo "status=LAB_FAIL"
echo "v2-compatible binary was detected ($libver), but lab.sql failed (exit $lab_ec)."
echo "Not claiming a pass. See feature.* probes above for which preview syntax this binary rejected."
exit 1
