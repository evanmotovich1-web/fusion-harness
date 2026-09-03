# Recursive CTE notes

Use a recursive CTE when walking a graph in SQL.

```sql
WITH RECURSIVE reachable(node) AS (
  SELECT 1
  UNION ALL
  SELECT dst FROM edges, reachable WHERE src = node
)
SELECT count(*) FROM reachable;
```

The `reachable` example is the canonical single-source reachability query.
