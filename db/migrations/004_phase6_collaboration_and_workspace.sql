-- ==============================================================================
-- 004_phase6_collaboration_and_workspace.sql - Collaboration, Workspace & RLS
-- Phase 6 — Production Collaboration & Cloud PostgreSQL Synchronization
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Research Projects Table
CREATE TABLE IF NOT EXISTS public.research_projects (
    id TEXT PRIMARY KEY,
    owner_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED', 'COMPLETED')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_research_projects_owner ON public.research_projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_research_projects_updated_at ON public.research_projects(updated_at DESC);

-- 2. Project Memberships Table (Role-Based Access Control)
CREATE TABLE IF NOT EXISTS public.project_members (
    membership_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES public.research_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('OWNER', 'EDITOR', 'VIEWER')),
    invited_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project ON public.project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user ON public.project_members(user_id);

-- 3. Manuscripts Table
CREATE TABLE IF NOT EXISTS public.manuscripts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES public.research_projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 1,
    brief_id TEXT,
    review_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_manuscripts_project ON public.manuscripts(project_id);

-- 4. Manuscript Revisions Table
CREATE TABLE IF NOT EXISTS public.manuscript_revisions (
    revision_id TEXT PRIMARY KEY,
    manuscript_id TEXT NOT NULL REFERENCES public.manuscripts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    author_notes TEXT DEFAULT '',
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    claims JSONB NOT NULL DEFAULT '[]'::jsonb,
    references JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_matrix JSONB NOT NULL DEFAULT '{}'::jsonb,
    diff_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE (manuscript_id, version)
);

CREATE INDEX IF NOT EXISTS idx_manuscript_revisions_manuscript ON public.manuscript_revisions(manuscript_id);

-- 5. Manuscript Exports Table
CREATE TABLE IF NOT EXISTS public.manuscript_exports (
    export_id TEXT PRIMARY KEY,
    manuscript_id TEXT NOT NULL REFERENCES public.manuscripts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('markdown', 'latex', 'bibtex', 'html', 'pdf')),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_manuscript_exports_manuscript ON public.manuscript_exports(manuscript_id, version, format);

-- 6. Sync Outbox Table (Durable Queue for Idempotent Synchronization)
CREATE TABLE IF NOT EXISTS public.sync_outbox (
    event_id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES public.research_projects(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'SYNCED', 'FAILED', 'CONFLICT')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    synced_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sync_outbox_status ON public.sync_outbox(status);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_project ON public.sync_outbox(project_id);

-- ==============================================================================
-- Row Level Security (RLS) Policies
-- ==============================================================================

ALTER TABLE public.research_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.manuscripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.manuscript_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.manuscript_exports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_outbox ENABLE ROW LEVEL SECURITY;

-- Project Access Helper Functions or Policies

-- 1. Projects: Selectable by Owner or Members
CREATE POLICY "Projects accessible by owner or members"
    ON public.research_projects
    FOR SELECT
    USING (
        auth.uid() = owner_id
        OR EXISTS (
            SELECT 1 FROM public.project_members pm
            WHERE pm.project_id = public.research_projects.id
              AND pm.user_id = auth.uid()
        )
    );

CREATE POLICY "Projects insertable by authenticated users"
    ON public.research_projects
    FOR INSERT
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Projects modifiable by owner"
    ON public.research_projects
    FOR UPDATE
    USING (auth.uid() = owner_id)
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Projects deletable by owner"
    ON public.research_projects
    FOR DELETE
    USING (auth.uid() = owner_id);

-- 2. Project Members Policies
CREATE POLICY "Project members viewable by project participants"
    ON public.project_members
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.research_projects rp
            WHERE rp.id = public.project_members.project_id
              AND (rp.owner_id = auth.uid() OR public.project_members.user_id = auth.uid())
        )
    );

CREATE POLICY "Project members manageable by owner"
    ON public.project_members
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.research_projects rp
            WHERE rp.id = public.project_members.project_id
              AND rp.owner_id = auth.uid()
        )
    );

-- 3. Manuscripts Policies
CREATE POLICY "Manuscripts readable by project participants"
    ON public.manuscripts
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.research_projects rp
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE rp.id = public.manuscripts.project_id
              AND (rp.owner_id = auth.uid() OR pm.user_id = auth.uid())
        )
    );

CREATE POLICY "Manuscripts modifiable by owners and editors"
    ON public.manuscripts
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.research_projects rp
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE rp.id = public.manuscripts.project_id
              AND (rp.owner_id = auth.uid() OR (pm.user_id = auth.uid() AND pm.role IN ('OWNER', 'EDITOR')))
        )
    );

-- 4. Manuscript Revisions Policies
CREATE POLICY "Revisions readable by project participants"
    ON public.manuscript_revisions
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.manuscripts m
            JOIN public.research_projects rp ON rp.id = m.project_id
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE m.id = public.manuscript_revisions.manuscript_id
              AND (rp.owner_id = auth.uid() OR pm.user_id = auth.uid())
        )
    );

CREATE POLICY "Revisions insertable by owners and editors"
    ON public.manuscript_revisions
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.manuscripts m
            JOIN public.research_projects rp ON rp.id = m.project_id
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE m.id = public.manuscript_revisions.manuscript_id
              AND (rp.owner_id = auth.uid() OR (pm.user_id = auth.uid() AND pm.role IN ('OWNER', 'EDITOR')))
        )
    );

-- 5. Manuscript Exports Policies
CREATE POLICY "Exports accessible by project participants"
    ON public.manuscript_exports
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.manuscripts m
            JOIN public.research_projects rp ON rp.id = m.project_id
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE m.id = public.manuscript_exports.manuscript_id
              AND (rp.owner_id = auth.uid() OR pm.user_id = auth.uid())
        )
    );

-- 6. Sync Outbox Policies
CREATE POLICY "Outbox events manageable by project participants"
    ON public.sync_outbox
    FOR ALL
    USING (
        project_id IS NULL
        OR EXISTS (
            SELECT 1 FROM public.research_projects rp
            LEFT JOIN public.project_members pm ON pm.project_id = rp.id
            WHERE rp.id = public.sync_outbox.project_id
              AND (rp.owner_id = auth.uid() OR pm.user_id = auth.uid())
        )
    );
