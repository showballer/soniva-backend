-- ============================================================
-- Migration 005: Async voice-test analysis
--
-- /voice-test/analyze used to block until FastGPT returned, so a client
-- that backgrounded or killed the app mid-request would lose the entire
-- analysis. The endpoint now creates a row in 'processing' state and
-- returns immediately; a background task fills the result fields and
-- flips task_status to 'completed' / 'failed'. Frontend polls
-- /voice-test/result/{id} (and the history list) until the status
-- settles.
--
-- task_status is intentionally separate from `status` (which remains the
-- soft-delete flag, 1-active / 0-deleted). Existing rows backfill to
-- 'completed' since they all have full data already.
--
-- Note: columns + index are added in a single ALTER TABLE so that
-- the index creation always sees the new column. Splitting them across
-- separate statements (or running CREATE INDEX after) tripped older
-- MySQL clients with "Key column 'task_status' doesn't exist".
-- ============================================================

ALTER TABLE voice_test_results
    ADD COLUMN task_status VARCHAR(20) NOT NULL DEFAULT 'completed'
        COMMENT 'Async task: pending/processing/completed/failed' AFTER status,
    ADD COLUMN error_message VARCHAR(500) NULL
        COMMENT 'Failure reason when task_status=failed' AFTER task_status,
    ADD INDEX idx_voice_test_user_task (user_id, task_status);
