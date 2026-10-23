-- Phase 3 (vision §5.4): lightweight scan by default; formal PRISMA review
-- runs only when the brief carries review_mode = 'formal' and that exact
-- version has been approved. Mirrors backend/memory/db.py:init_db.
ALTER TABLE research_briefs ADD COLUMN IF NOT EXISTS review_mode TEXT NOT NULL DEFAULT 'scan';
