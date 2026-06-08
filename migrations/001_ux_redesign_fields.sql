-- Migration: 001_ux_redesign_fields.sql
-- Created: 2026-06-05
-- Purpose: Add Phase 2 UX redesign fields to existing tables.
-- Apply: Run once against haandvaerker.db before starting the server.
-- Rollback: Dev environment only (DP-5). Drop columns or reset DB.
-- NOTE: Preserves all existing rows including company records and tokens.

ALTER TABLE timeentry ADD COLUMN action_item_id TEXT REFERENCES actionitem(id);
ALTER TABLE quoteroom ADD COLUMN price_per_m2 REAL;
ALTER TABLE invoicereminder ADD COLUMN triggered_by TEXT NOT NULL DEFAULT 'manual';
ALTER TABLE project ADD COLUMN close_reason TEXT;
ALTER TABLE project ADD COLUMN close_override INTEGER NOT NULL DEFAULT 0;
ALTER TABLE quote ADD COLUMN quote_type TEXT NOT NULL DEFAULT 'line';
ALTER TABLE enquiry ADD COLUMN address TEXT;
ALTER TABLE enquiry ADD COLUMN work_type TEXT;
ALTER TABLE enquiry ADD COLUMN timeframe TEXT;
