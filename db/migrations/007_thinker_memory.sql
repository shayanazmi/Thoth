-- Thinkers as co-authors (docs/features/03-thinkers.md): each thinker's current stance on a
-- project, updated after every exchange. Mirrors backend/memory/db.py:init_db.
CREATE TABLE IF NOT EXISTS thinker_memory (
    thread_id TEXT NOT NULL,
    thinker_id TEXT NOT NULL,
    stance TEXT NOT NULL,
    changes INTEGER NOT NULL DEFAULT 0,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (thread_id, thinker_id)
);
