-- Mirrors backend/memory/db.py:init_db.
-- Feature 04 (hypothesis): a trial is tied to the hypothesis version it tested, so an old verdict is labelled
-- stale after the hypothesis changes; a re-mapped trial (a rival swapped in) names the trial whose library it reused.
ALTER TABLE trials ADD COLUMN IF NOT EXISTS hypothesis_version INTEGER;
ALTER TABLE trials ADD COLUMN IF NOT EXISTS remapped_from TEXT;
