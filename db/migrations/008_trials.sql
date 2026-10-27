-- Mirrors backend/memory/db.py:init_db.
-- The trial (docs/features/05, 06): a hypothesis on trial, its witnesses and the verdict.
CREATE TABLE IF NOT EXISTS trials (
    trial_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    subclaims_json TEXT NOT NULL,
    status TEXT NOT NULL,
    strategy_json TEXT NOT NULL DEFAULT '{}',
    verdict_json TEXT NOT NULL DEFAULT '{}',
    adjacent_json TEXT NOT NULL DEFAULT '[]',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trials_thread ON trials(thread_id, created_at);

CREATE TABLE IF NOT EXISTS trial_papers (
    paper_id TEXT PRIMARY KEY,
    trial_id TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    access TEXT NOT NULL DEFAULT 'pending',
    text_source TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL DEFAULT '{}',
    row_json TEXT NOT NULL DEFAULT '{}',
    weight DOUBLE PRECISION,
    i_say_user TEXT,
    status TEXT NOT NULL DEFAULT 'found',
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trial_papers_trial ON trial_papers(trial_id, created_at);
