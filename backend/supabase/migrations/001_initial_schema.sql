-- ==============================================================================
-- 001_initial_schema.sql - Thoth Core Schema DDL
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Sessions Table
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON public.sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON public.sessions(created_at DESC);

-- 2. Reports Table
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    score DOUBLE PRECISION DEFAULT 0.0,
    verifier_feedback TEXT DEFAULT '',
    mindmap JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_reports_session_id ON public.reports(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_user_id ON public.reports(user_id);

-- 3. Notes Table (Knowledge Vault)
CREATE TABLE IF NOT EXISTS public.notes (
    note_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'source', 'topic', 'claim', 'fact'
    title TEXT DEFAULT '',
    content TEXT NOT NULL,
    confidence DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_notes_user_id ON public.notes(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_type ON public.notes(type);

-- 4. Edges Table (Knowledge Graph)
CREATE TABLE IF NOT EXISTS public.edges (
    source_note TEXT NOT NULL REFERENCES public.notes(note_id) ON DELETE CASCADE,
    relation TEXT NOT NULL CHECK (relation IN ('cites', 'supports', 'contradicts', 'part_of', 'defines', 'related')),
    target_note TEXT NOT NULL REFERENCES public.notes(note_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    confidence DOUBLE PRECISION DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    PRIMARY KEY (source_note, relation, target_note)
);

CREATE INDEX IF NOT EXISTS idx_edges_user_id ON public.edges(user_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON public.edges(target_note);
