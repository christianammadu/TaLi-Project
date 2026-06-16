-- Find duplicate ledger rows caused by the Band terminal-reply bug
-- (fixed in 59c005b "fix(band): don't re-dispatch terminal replies to @mention handlers").
--
-- The bug committed a write to the DB but reported "Transaction failed" to the user, so
-- the user retried. Each retry got a FRESH event_id (so idempotency didn't dedupe it),
-- producing a second row with the SAME user_id + raw_text + amount + type + action a few
-- seconds/minutes apart. This script surfaces those clusters; it does NOT delete anything.
--
-- Run on PythonAnywhere (the DB only accepts connections from there):
--   mysql -u Christiana -h Christiana.mysql.pythonanywhere-services.com -p \
--         'Christiana$Bookkeeper_db' < ops/find_duplicate_records.sql
--
-- The 900s (15 min) window separates retries from genuine same-text repeats on a later
-- day. Widen/remove `AND span_secs <= 900` if you want to see every same-signature group.

-- ───────────────────────────────────────────────────────────────────────────
-- 1) TRANSACTIONS — covers sales/expenses AND debt ledger entries (both INSERT here)
-- Cluster summary: one row per suspected duplicate group.
SELECT
    HEX(user_id)                                              AS user_hex,
    type, action, amount, raw_text,
    COUNT(*)                                                  AS copies,
    TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at))   AS span_secs,
    MIN(created_at)                                           AS first_at,
    MAX(created_at)                                           AS last_at,
    GROUP_CONCAT(DISTINCT event_id ORDER BY created_at SEPARATOR ' | ') AS event_ids
FROM transactions
GROUP BY user_id, type, action, amount, raw_text
HAVING copies > 1 AND span_secs <= 900
ORDER BY span_secs, copies DESC;

-- ───────────────────────────────────────────────────────────────────────────
-- 2) TRANSACTIONS — detail rows for those clusters, with a KEEP/DELETE verdict
-- (keeps the earliest row in each cluster; later copies are the bug duplicates).
-- Review this before deleting; copy the row_id_hex values you want to remove.
SELECT
    HEX(t.id)        AS row_id_hex,
    t.event_id, t.type, t.action, t.amount, t.raw_text, t.created_at,
    CASE WHEN t.created_at = x.first_at THEN 'KEEP (earliest)'
         ELSE 'DUPLICATE -> review/delete' END AS verdict
FROM transactions t
JOIN (
    SELECT user_id, type, action, amount, raw_text,
           MIN(created_at) AS first_at,
           COUNT(*)        AS copies,
           TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)) AS span_secs
    FROM transactions
    GROUP BY user_id, type, action, amount, raw_text
    HAVING copies > 1 AND span_secs <= 900
) x
  ON  t.user_id = x.user_id AND t.type = x.type AND t.action = x.action
  AND t.amount  = x.amount  AND t.raw_text = x.raw_text
ORDER BY t.raw_text, t.amount, t.created_at;

-- ───────────────────────────────────────────────────────────────────────────
-- 3) INVENTORY_MOVEMENTS — stock messages don't write `transactions`; duplicates here
-- DOUBLE-COUNT the stock level. `notes` holds the original message text.
SELECT
    HEX(user_id)                                              AS user_hex,
    HEX(inventory_item_id)                                    AS item_hex,
    movement_type, quantity, notes,
    COUNT(*)                                                  AS copies,
    TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at))   AS span_secs,
    MIN(created_at)                                           AS first_at,
    MAX(created_at)                                           AS last_at
FROM inventory_movements
GROUP BY user_id, inventory_item_id, movement_type, quantity, notes
HAVING copies > 1 AND span_secs <= 900
ORDER BY span_secs, copies DESC;
