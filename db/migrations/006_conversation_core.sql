-- Conversation core (docs/features/01-conversation-core.md, 02 notebook proposals).
-- Server-side turn memory, rolling thread summaries, conductor proposals/offers,
-- and versioned notebook sections. Mirrors backend/memory/db.py:init_db.
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_thread ON conversation_turns(thread_id, created_at);

CREATE TABLE IF NOT EXISTS thread_summaries (
    thread_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    turns_covered INTEGER NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS conductor_proposals (
    proposal_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at DOUBLE PRECISION NOT NULL,
    resolved_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_proposals_thread ON conductor_proposals(thread_id, status);

CREATE TABLE IF NOT EXISTS notebook_sections (
    section_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notebook_thread ON notebook_sections(thread_id, kind, version);
