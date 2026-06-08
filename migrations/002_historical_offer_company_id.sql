-- Migration 002: Add company_id to historicaloffer
-- Required by Phase 2 of Plan C (Guided Intake Wizard) — closes cross-company
-- data leak in similarity_search (CONT-10).
-- Existing rows get company_id = NULL; they will not appear in company-scoped
-- searches until manually assigned.

ALTER TABLE historicaloffer ADD COLUMN company_id TEXT REFERENCES company(id);
CREATE INDEX IF NOT EXISTS ix_historicaloffer_company_id ON historicaloffer(company_id);
