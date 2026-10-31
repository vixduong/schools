\echo 'T1 no GUC set (expect 0 rows):'
SELECT count(*) FROM score;
\echo 'T2 GUC set to empty string, as a reset pooled connection would have (expect 0):'
SELECT set_config('app.school_id', '', false); SELECT count(*) FROM score;
\echo 'T3 transaction-local GUC = 1 (expect 2):'
BEGIN; SELECT set_config('app.school_id', '1', true); SELECT count(*) FROM score;
\echo 'T4 insert row for school 2 while scoped to 1 (expect policy violation):'
SAVEPOINT s; INSERT INTO score (school_id, student, value) VALUES (2,'X',5); 
BEGIN; SELECT set_config('app.school_id', '1', true); SELECT count(*) AS in_tx FROM score; COMMIT;
\echo 'T5 after COMMIT on same connection, GUC must be gone (expect 0 rows):'
SELECT count(*) AS after_commit FROM score;
\echo 'T6 rollback path also clears (expect 0):'
BEGIN; SELECT set_config('app.school_id', '2', true); ROLLBACK; SELECT count(*) AS after_rollback FROM score;
\echo 'T7 update across tenants is invisible (expect UPDATE 0):'
BEGIN; SELECT set_config('app.school_id', '2', true); UPDATE score SET value = 10 WHERE student = 'An'; COMMIT;
