-- Migration: 2026-06-14-add-columns.sql
--
-- Adds two nullable columns to existing tables without touching firm data.
-- Run ONCE against haandvaerker.db using either:
--   sqlite3 haandvaerker.db < migrations/2026-06-14-add-columns.sql
-- or in Python:
--   import sqlite3, pathlib
--   con = sqlite3.connect("haandvaerker.db")
--   con.executescript(pathlib.Path("migrations/2026-06-14-add-columns.sql").read_text())
--   con.close()
--
-- Safety notes:
--   - Both columns are nullable with no default — existing rows are unaffected.
--   - SQLite ALTER TABLE ADD COLUMN is idempotent if the column already exists
--     only from SQLite 3.37.0+.  On older SQLite the duplicate-column error is
--     HARMLESS (the column already exists); you may ignore it or wrap in a
--     try/except in the Python snippet above.
--   - The 3 existing firms (PLL malerfirma, Gentofte BygningsService, CSKK)
--     are NOT touched; verify with: SELECT name FROM company;
--   - Tests use in-memory SQLite where SQLModel.metadata.create_all() already
--     includes the new columns — this script is only needed for the live DB.
--
-- Verify after running:
--   PRAGMA table_info(inboxmessage);
--   PRAGMA table_info(historicaloffer);
--   SELECT name FROM company;

-- Phase 1: tab-sikring på InboxMessage
ALTER TABLE inboxmessage ADD COLUMN processing_error VARCHAR;

-- Phase 4: erfaringsbank-link på HistoricalOffer
ALTER TABLE historicaloffer ADD COLUMN quote_id VARCHAR;
