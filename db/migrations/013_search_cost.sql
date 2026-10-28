-- Mirrors backend/memory/db.py:init_db.
-- What each logged search request cost: OpenAlex reports meta.cost_usd per call against the key's daily budget.
ALTER TABLE sys_review_searches ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION;
