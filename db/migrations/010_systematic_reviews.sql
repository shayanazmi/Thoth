-- Mirrors backend/memory/db.py:init_db.
-- Systematic review (docs/features/05 tier 3): a protocol-driven PRISMA review whose included
-- studies feed a linked trial. Counts are always computed from these records.
CREATE TABLE IF NOT EXISTS sys_reviews (
    review_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    protocol_json TEXT NOT NULL,
    subclaims_json TEXT NOT NULL DEFAULT '[]',
    mode TEXT NOT NULL DEFAULT 'copilot',
    status TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'planned',
    trial_id TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sys_reviews_thread ON sys_reviews(thread_id, created_at);

CREATE TABLE IF NOT EXISTS sys_review_records (
    record_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    source TEXT NOT NULL,
    dup_of TEXT,
    screening_json TEXT NOT NULL DEFAULT '{}',
    ft_access TEXT,
    paper_id TEXT,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sys_records_review ON sys_review_records(review_id, created_at);
