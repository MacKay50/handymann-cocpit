-- Migration: 2026-06-15-invoice-case-source-inbox.sql
--
-- Adds source_inbox_message_id to invoice_case so that InboxMessages
-- classified as invoice_payment can be promoted to InvoiceCases without
-- duplicating the original message reference.
--
-- Safe to run on existing data:
--   - The new column is nullable VARCHAR with no default — all existing rows
--     receive NULL, which is the correct sentinel meaning "not sourced from
--     an InboxMessage".
--   - No data is modified, renamed, or removed.
--   - SQLite ALTER TABLE ADD COLUMN is additive only.
--
-- Run ONCE against each live DB file:
--   sqlite3 haandvaerker.db < migrations/2026-06-15-invoice-case-source-inbox.sql
--   sqlite3 src/haandvaerker.db < migrations/2026-06-15-invoice-case-source-inbox.sql
--
-- Verify after running:
--   PRAGMA table_info(invoice_case);
--   -- Look for: source_inbox_message_id | varchar | 0 | NULL | 0

ALTER TABLE invoice_case ADD COLUMN source_inbox_message_id VARCHAR;
CREATE INDEX IF NOT EXISTS ix_invoice_case_source_inbox_message_id
    ON invoice_case (source_inbox_message_id);
