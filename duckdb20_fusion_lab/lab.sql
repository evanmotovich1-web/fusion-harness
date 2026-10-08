-- duckdb20_fusion_lab/lab.sql
-- DuckDB v2.0 preview teaching lab (Cyanoptera).
-- Requires a v2.0+ binary. run.sh will refuse to claim success on 1.x.
-- Source: https://duckdb.org/2026/08/17/duckdb-20-highlights
--
-- Surfaces this file runs on v2.0.0-alpha43385:
--   1. VARIANT storage, extraction, containment
--   2. BEFORE / AFTER triggers with an audit table
--   3. DML inside a MATERIALIZED CTE using RETURNING
--   4. SQL variables ($x)
--   5. Nested schemas, JSON mutation, FETCH FIRST, OVERLAY,
--      UNNEST in GROUP BY, MERGE, NEAREST join, dialect mode,
--      timezone conversion
-- Not in this file: a live quack_serve / CONNECT session (LOAD quack works;
-- no server was left running), async I/O, on-disk storage format v2, stable C API.
-- USING KEY runs, but this alpha returns b=0.0, not the blog's 2.5.

-- ---------------------------------------------------------------------------
-- 0. Idempotent setup
-- This alpha rejects `DROP TRIGGER name;` (it requires `ON table`) and
-- errors if that table is missing. DROP TABLE clears attached triggers.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS target;
DROP TABLE IF EXISTS audit;
DROP TABLE IF EXISTS staging;
DROP TABLE IF EXISTS archive;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS dst;
DROP TABLE IF EXISTS src;
DROP SCHEMA IF EXISTS finance CASCADE;

-- ---------------------------------------------------------------------------
-- 1. VARIANT: storage, extraction, containment
--    Announced v2 names: variant_type, variant_keys, variant_contains
-- ---------------------------------------------------------------------------
CREATE TABLE events (payload VARIANT);

INSERT INTO events
VALUES
    ('{"user": {"id": 42, "tags": ["a", "b"]}}'::JSON::VARIANT),
    ('{"user": {"id": 7}, "ok": true}'::JSON::VARIANT);

SELECT payload FROM events;

SELECT variant_type(payload) AS vtype, variant_keys(payload) AS vkeys
FROM events;

SELECT payload
FROM events
WHERE variant_contains(payload, {'user': {'id': 42}}::VARIANT);

SELECT CASE
    WHEN variant_type(payload) IS NOT NULL THEN 'PASS: variant_type'
    ELSE error('FAIL: variant_type was NULL')
END AS check_variant_type
FROM events
LIMIT 1;

SELECT CASE
    WHEN n = 1 THEN 'PASS: variant_contains matched id=42 once'
    ELSE error('FAIL: variant_contains expected 1 row, got ' || n::VARCHAR)
END AS check_variant_contains
FROM (
    SELECT count(*) AS n
    FROM events
    WHERE variant_contains(payload, {'user': {'id': 42}}::VARIANT)
);

-- ---------------------------------------------------------------------------
-- 2. BEFORE / AFTER triggers + audit table
--    AFTER uses statement-level REFERENCING OLD/NEW TABLE (launch snippet).
--    This alpha rejects transition tables on BEFORE, and rejects
--    BEFORE/UPDATE FOR EACH ROW. BEFORE is a statement marker only.
-- ---------------------------------------------------------------------------
CREATE TABLE target (id INTEGER, val INTEGER);
CREATE TABLE audit (
    id INTEGER,
    old_val INTEGER,
    new_val INTEGER,
    note VARCHAR
);

CREATE TRIGGER trg_before_upd BEFORE UPDATE ON target
FOR EACH STATEMENT
    INSERT INTO audit
    VALUES (NULL, NULL, NULL, 'before');

CREATE TRIGGER trg_after_upd AFTER UPDATE ON target
REFERENCING OLD TABLE AS o NEW TABLE AS n
FOR EACH STATEMENT
    INSERT INTO audit
    SELECT n.id, o.val, n.val, 'after'
    FROM o
    JOIN n ON o.id = n.id;

INSERT INTO target VALUES (1, 10), (2, 20);
UPDATE target SET val = val * 10 WHERE id <= 2;
SELECT * FROM audit ORDER BY note, id;

SELECT CASE
    WHEN n = 2 THEN 'PASS: AFTER audit has 2 rows'
    ELSE error('FAIL: AFTER audit expected 2 rows, got ' || n::VARCHAR)
END AS check_after_audit
FROM (SELECT count(*) AS n FROM audit WHERE note = 'after');

SELECT CASE
    WHEN n = 1 THEN 'PASS: BEFORE audit has 1 statement marker'
    ELSE error('FAIL: BEFORE audit expected 1 statement marker, got ' || n::VARCHAR)
END AS check_before_audit
FROM (SELECT count(*) AS n FROM audit WHERE note = 'before');

SELECT CASE
    WHEN old_val = 10 AND new_val = 100 THEN 'PASS: id=1 10 -> 100'
    ELSE error('FAIL: id=1 expected 10 -> 100')
END AS check_audit_values
FROM audit
WHERE id = 1 AND note = 'after';

-- ---------------------------------------------------------------------------
-- 3. DML inside a MATERIALIZED CTE using RETURNING
-- ---------------------------------------------------------------------------
CREATE TABLE staging (id INTEGER, payload VARCHAR);
CREATE TABLE archive (id INTEGER, payload VARCHAR);
INSERT INTO staging VALUES (1, 'a'), (2, 'b');

WITH moved AS MATERIALIZED (
    DELETE FROM staging RETURNING *
)
INSERT INTO archive SELECT * FROM moved;

SELECT CASE
    WHEN n = 0 THEN 'PASS: staging emptied by CTE DELETE'
    ELSE error('FAIL: staging expected 0 rows, got ' || n::VARCHAR)
END AS check_staging_empty
FROM (SELECT count(*) AS n FROM staging);

SELECT CASE
    WHEN n = 2 THEN 'PASS: archive received RETURNING rows'
    ELSE error('FAIL: archive expected 2 rows, got ' || n::VARCHAR)
END AS check_archive_moved
FROM (SELECT count(*) AS n FROM archive);

-- ---------------------------------------------------------------------------
-- 4. SQL variables ($x) — v2 expression syntax (not getvariable)
-- ---------------------------------------------------------------------------
SET VARIABLE threshold = 100;

CREATE TABLE orders (id INTEGER, amount INTEGER);
INSERT INTO orders VALUES (1, 50), (2, 150), (3, 100);

SELECT $threshold AS threshold_value;

SELECT id, amount
FROM orders
WHERE amount > $threshold
ORDER BY id;

SELECT CASE
    WHEN $threshold = 100 THEN 'PASS: $threshold == 100'
    ELSE error('FAIL: $threshold was not 100')
END AS check_variable_value;

SELECT CASE
    WHEN n = 1 THEN 'PASS: $threshold filtered to id=2'
    ELSE error('FAIL: amount > $threshold expected 1 row, got ' || n::VARCHAR)
END AS check_variable_filter
FROM (
    SELECT count(*) AS n FROM orders WHERE amount > $threshold
);

-- ---------------------------------------------------------------------------
-- 5. Nested schemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA finance;
CREATE SCHEMA finance.reports;
CREATE TABLE finance.reports.q3 (revenue DECIMAL);
INSERT INTO finance.reports.q3 VALUES (1.5);

SELECT CASE
    WHEN n = 1 THEN 'PASS: nested schema finance.reports.q3'
    ELSE error('FAIL: finance.reports.q3 expected 1 row, got ' || n::VARCHAR)
END AS check_nested_schema
FROM (SELECT count(*) AS n FROM finance.reports.q3);

-- ---------------------------------------------------------------------------
-- 6. JSON mutation
-- ---------------------------------------------------------------------------
SELECT CASE
    WHEN json_set('{"a":1}', '$.b', '2') = '{"a":1,"b":2}'::JSON
    THEN 'PASS: json_set added b'
    ELSE error('FAIL: json_set got ' || json_set('{"a":1}', '$.b', '2')::VARCHAR)
END AS check_json_set;

SELECT CASE
    WHEN json_insert('{"a":1}', '$.a', '9') = '{"a":1}'::JSON
     AND json_insert('{"a":1}', '$.c', '9') = '{"a":1,"c":9}'::JSON
    THEN 'PASS: json_insert skips existing key and adds c'
    ELSE error('FAIL: json_insert got ' || json_insert('{"a":1}', '$.c', '9')::VARCHAR)
END AS check_json_insert;

SELECT CASE
    WHEN json_replace('{"a":1}', '$.a', '3') = '{"a":3}'::JSON
    THEN 'PASS: json_replace changed a'
    ELSE error('FAIL: json_replace got ' || json_replace('{"a":1}', '$.a', '3')::VARCHAR)
END AS check_json_replace;

SELECT CASE
    WHEN json_remove('{"a":1,"b":2}', '$.b') = '{"a":1}'::JSON
    THEN 'PASS: json_remove dropped b'
    ELSE error('FAIL: json_remove got ' || json_remove('{"a":1,"b":2}', '$.b')::VARCHAR)
END AS check_json_remove;

-- ---------------------------------------------------------------------------
-- 7. Recursive CTE USING KEY
--    Blog example prints b=2.5. This alpha returns b=0.0 (last value).
--    A plain recursive CTE then avg(b) is 2.5. Do not treat 0.0 as that result.
-- ---------------------------------------------------------------------------
SELECT CASE
    WHEN n = 1 AND b = 2.5 THEN 'PASS: USING KEY avg is 2.5'
    WHEN n = 1 AND b = 0.0 THEN 'NOTE: USING KEY collapsed to 1 row with b=0.0; blog shows 2.5'
    ELSE error('FAIL: USING KEY unexpected n=' || n::VARCHAR || ' b=' || b::VARCHAR)
END AS check_using_key
FROM (
    WITH RECURSIVE tbl(a, b) USING KEY (a, avg(b)) AS (
        SELECT 1, 5
        UNION
        SELECT a, b - 1 FROM tbl WHERE b > 0
    )
    SELECT count(*) AS n, min(b) AS b FROM tbl
);

-- ---------------------------------------------------------------------------
-- 8. FETCH FIRST, OVERLAY, UNNEST in GROUP BY
-- ---------------------------------------------------------------------------
SELECT CASE
    WHEN n = 2 AND lo = 1 AND hi = 2 THEN 'PASS: FETCH FIRST 2 ROWS ONLY'
    ELSE error('FAIL: FETCH FIRST expected rows 1 and 2')
END AS check_fetch_first
FROM (
    SELECT count(*) AS n, min(x) AS lo, max(x) AS hi
    FROM (
        SELECT x FROM (VALUES (1), (2), (3)) t(x)
        ORDER BY x
        FETCH FIRST 2 ROWS ONLY
    )
);

SELECT CASE
    WHEN overlay('abcdef' PLACING 'XY' FROM 3 FOR 2) = 'abXYef'
    THEN 'PASS: overlay'
    ELSE error('FAIL: overlay got ' || overlay('abcdef' PLACING 'XY' FROM 3 FOR 2))
END AS check_overlay;

SELECT CASE
    WHEN a_n = 2 AND b_n = 1 THEN 'PASS: UNNEST in GROUP BY'
    ELSE error('FAIL: UNNEST group counts a=' || a_n::VARCHAR || ' b=' || b_n::VARCHAR)
END AS check_unnest_group
FROM (
    SELECT
        max(n) FILTER (WHERE tag = 'a') AS a_n,
        max(n) FILTER (WHERE tag = 'b') AS b_n
    FROM (
        SELECT unnest(tags) AS tag, count(*) AS n
        FROM (VALUES (['a', 'b']), (['a'])) t(tags)
        GROUP BY unnest(tags)
    )
);

-- ---------------------------------------------------------------------------
-- 9. MERGE
-- ---------------------------------------------------------------------------
CREATE TABLE dst (id INTEGER PRIMARY KEY, v INTEGER);
INSERT INTO dst VALUES (1, 10);
CREATE TABLE src (id INTEGER, v INTEGER);
INSERT INTO src VALUES (1, 11), (2, 20);

MERGE INTO dst
USING src ON dst.id = src.id
WHEN MATCHED THEN UPDATE SET v = src.v
WHEN NOT MATCHED THEN INSERT VALUES (src.id, src.v);

SELECT CASE
    WHEN n = 2 AND v1 = 11 AND v2 = 20 THEN 'PASS: MERGE updated 1 and inserted 2'
    ELSE error('FAIL: MERGE unexpected')
END AS check_merge
FROM (
    SELECT
        count(*) AS n,
        max(v) FILTER (WHERE id = 1) AS v1,
        max(v) FILTER (WHERE id = 2) AS v2
    FROM dst
);

-- ---------------------------------------------------------------------------
-- 10. APPROX NEAREST join
-- ---------------------------------------------------------------------------
CREATE TABLE users (user_id INTEGER, embedding FLOAT[2]);
CREATE TABLE products (product_id INTEGER, embedding FLOAT[2]);
INSERT INTO users VALUES (1, [1.0, 0.0]);
INSERT INTO products VALUES (10, [1.0, 0.0]), (11, [0.0, 1.0]);

SELECT CASE
    WHEN n = 1 AND product_id = 10 THEN 'PASS: NEAREST matched product 10'
    ELSE error('FAIL: NEAREST unexpected')
END AS check_nearest
FROM (
    SELECT count(*) AS n, min(t.product_id) AS product_id
    FROM users q
    INNER JOIN products t APPROX NEAREST 1
        BY SIMILARITY array_cosine_similarity(q.embedding, t.embedding)
);

-- ---------------------------------------------------------------------------
-- 11. Dialect mode and timezone without a separate ICU call
--     icu extension is already loaded in this alpha. This checks the
--     announced conversion, not that the ICU library was removed.
-- ---------------------------------------------------------------------------
SET dialect_compatibility_mode = 'spark';

SELECT CASE
    WHEN current_setting('dialect_compatibility_mode') = 'spark'
    THEN 'PASS: dialect_compatibility_mode=spark'
    ELSE error('FAIL: dialect mode was ' || current_setting('dialect_compatibility_mode'))
END AS check_dialect_spark;

RESET dialect_compatibility_mode;

SELECT CASE
    WHEN current_setting('dialect_compatibility_mode') = 'NONE'
    THEN 'PASS: dialect mode reset'
    ELSE error('FAIL: dialect mode did not reset')
END AS check_dialect_reset;

SELECT CASE
    WHEN ('2026-08-14 12:00:00'::TIMESTAMPTZ AT TIME ZONE 'Europe/Paris')
         = TIMESTAMP '2026-08-14 18:00:00'
    THEN 'PASS: Europe/Paris is 18:00 in August'
    ELSE error('FAIL: Paris conversion unexpected')
END AS check_timezone;

SELECT CASE
    WHEN current_setting('storage_compatibility_version') IS NOT NULL
    THEN 'NOTE: storage_compatibility_version='
         || current_setting('storage_compatibility_version')
         || ' (setting only; no database file written)'
    ELSE error('FAIL: storage_compatibility_version missing')
END AS check_storage_setting;

-- ---------------------------------------------------------------------------
-- 12. Cleanup
-- DROP TRIGGER on this alpha is `DROP TRIGGER [IF EXISTS] name ON table`.
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_before_upd ON target;
DROP TRIGGER IF EXISTS trg_after_upd ON target;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS target;
DROP TABLE IF EXISTS audit;
DROP TABLE IF EXISTS staging;
DROP TABLE IF EXISTS archive;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS dst;
DROP TABLE IF EXISTS src;
DROP SCHEMA IF EXISTS finance CASCADE;

SELECT 'lab.sql finished (assertions passed)' AS lab_status;
