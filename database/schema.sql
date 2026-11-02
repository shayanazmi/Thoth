-- Thoth · SQLite schema (the single source of truth; backend/memory/db.py applies it at startup).
-- Developed by Shayan Azmi.

PRAGMA foreign_keys = ON;

-- Threads and projects (a thread becomes a project when a hypothesis is accepted).
CREATE TABLE IF NOT EXISTS research_projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED', 'COMPLETED')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_session ON research_projects(session_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON research_projects(updated_at DESC);

-- Ideas the researcher explicitly kept from the conversation.
CREATE TABLE IF NOT EXISTS research_ideas (
    idea_id TEXT PRIMARY KEY,
    session_id TEXT DEFAULT '',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    hypothesis TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('TENTATIVE', 'PROMOTED', 'REVISED', 'ABANDONED')),
    thinker_id TEXT DEFAULT '',
    thinker_critique TEXT DEFAULT '',
    unresolved_objections_json TEXT NOT NULL DEFAULT '[]',
    parent_idea_id TEXT DEFAULT NULL,
    revision_version INTEGER NOT NULL DEFAULT 1,
    revision_notes TEXT DEFAULT '',
    brief_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    project_id TEXT DEFAULT NULL,
    FOREIGN KEY (parent_idea_id) REFERENCES research_ideas(idea_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_ideas_session ON research_ideas(session_id);
CREATE INDEX IF NOT EXISTS idx_ideas_parent ON research_ideas(parent_idea_id);
CREATE INDEX IF NOT EXISTS idx_ideas_status ON research_ideas(status);

-- Every message: the main conversation and each one-to-one thinker room.
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_thread ON conversation_turns(thread_id, created_at);

-- Rolling summary of older turns, so long conversations stay within the model's context.
CREATE TABLE IF NOT EXISTS thread_summaries (
    thread_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    turns_covered INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

-- What Thoth proposed (a research-file change, a thinker, a heavier step) and what the researcher decided.
CREATE TABLE IF NOT EXISTS conductor_proposals (
    proposal_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_proposals_thread ON conductor_proposals(thread_id, status);

-- The living research file: every version of the question, hypothesis, rivals and design, with why it changed.
CREATE TABLE IF NOT EXISTS notebook_sections (
    section_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at REAL NOT NULL,
    rationale_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_notebook_thread ON notebook_sections(thread_id, kind, version);

-- Where each thinker stands on the project, and whether they changed their mind.
CREATE TABLE IF NOT EXISTS thinker_memory (
    thread_id TEXT NOT NULL,
    thinker_id TEXT NOT NULL,
    stance TEXT NOT NULL,
    changes INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (thread_id, thinker_id)
);

-- The hypothesis on trial: plan, sub-claims, synthesis matrix and the ruling.
CREATE TABLE IF NOT EXISTS trials (
    trial_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    subclaims_json TEXT NOT NULL,
    status TEXT NOT NULL,
    strategy_json TEXT NOT NULL DEFAULT '{}',
    verdict_json TEXT NOT NULL DEFAULT '{}',
    adjacent_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    hypothesis_version INTEGER,
    remapped_from TEXT
);
CREATE INDEX IF NOT EXISTS idx_trials_thread ON trials(thread_id, created_at);

-- Each paper read in a trial (a witness), with access level and appraisal.
CREATE TABLE IF NOT EXISTS trial_papers (
    paper_id TEXT PRIMARY KEY,
    trial_id TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    access TEXT NOT NULL DEFAULT 'pending',
    text_source TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL DEFAULT '{}',
    row_json TEXT NOT NULL DEFAULT '{}',
    weight REAL,
    i_say_user TEXT,
    status TEXT NOT NULL DEFAULT 'found',
    created_at REAL NOT NULL,
    appraisal_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trial_papers_trial ON trial_papers(trial_id, created_at);

-- Systematic reviews: protocol, mode, budget, stopping rules and status.
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
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    budget_json TEXT DEFAULT '{}',
    stopping_json TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_sys_reviews_thread ON sys_reviews(thread_id, created_at);

-- Every record a review identified, with its screening decisions.
CREATE TABLE IF NOT EXISTS sys_review_records (
    record_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    source TEXT NOT NULL,
    dup_of TEXT,
    screening_json TEXT NOT NULL DEFAULT '{}',
    ft_access TEXT,
    paper_id TEXT,
    created_at REAL NOT NULL,
    ids_json TEXT DEFAULT '{}',
    origin_json TEXT DEFAULT '{}',
    rank INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sys_records_review ON sys_review_records(review_id, created_at);

-- Every search request a review made, as made (the search record).
CREATE TABLE IF NOT EXISTS sys_review_searches (
    search_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    round INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
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
    searched_at REAL NOT NULL,
    cost_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_sys_searches_review ON sys_review_searches(review_id, searched_at);
