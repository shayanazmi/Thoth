-- Mirrors backend/memory/db.py:init_db (evidence depth, Phase 1).
-- The systematic review's search log, budgets and stopping rules; record identities and origins (keyword or
-- citation search); structured appraisal of each trial paper; the rationale behind every research-file version.
CREATE TABLE IF NOT EXISTS sys_review_searches (
    search_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    round INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,              -- keyword | backward | forward
    source TEXT NOT NULL,            -- OpenAlex | Europe PMC | Semantic Scholar
    query TEXT NOT NULL DEFAULT '',
    seed_record_id TEXT,
    page INTEGER NOT NULL DEFAULT 1,
    requested INTEGER,
    returned INTEGER,
    new_unique INTEGER,
    duplicates INTEGER,
    removed_offtopic INTEGER NOT NULL DEFAULT 0,
    total_available INTEGER,
    next_cursor TEXT,
    error TEXT,
    searched_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sys_searches_review ON sys_review_searches(review_id, searched_at);

ALTER TABLE sys_reviews ADD COLUMN IF NOT EXISTS budget_json TEXT DEFAULT '{}';
ALTER TABLE sys_reviews ADD COLUMN IF NOT EXISTS stopping_json TEXT DEFAULT '[]';
ALTER TABLE sys_review_records ADD COLUMN IF NOT EXISTS ids_json TEXT DEFAULT '{}';
ALTER TABLE sys_review_records ADD COLUMN IF NOT EXISTS origin_json TEXT DEFAULT '{}';
ALTER TABLE sys_review_records ADD COLUMN IF NOT EXISTS "rank" INTEGER;
ALTER TABLE trial_papers ADD COLUMN IF NOT EXISTS appraisal_json TEXT DEFAULT '{}';
ALTER TABLE notebook_sections ADD COLUMN IF NOT EXISTS rationale_json TEXT DEFAULT '{}';
