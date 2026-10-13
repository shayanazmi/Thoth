-- ==============================================================================
-- 002_enable_rls.sql - Row Level Security Policies
-- ==============================================================================

-- Enable RLS on all tables
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.edges ENABLE ROW LEVEL SECURITY;

-- 1. Sessions Policies
CREATE POLICY "Users can view and manage their own sessions"
    ON public.sessions
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2. Reports Policies
CREATE POLICY "Users can view and manage their own reports"
    ON public.reports
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 3. Notes Policies
CREATE POLICY "Users can view and manage their own notes"
    ON public.notes
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 4. Edges Policies
CREATE POLICY "Users can view and manage their own graph edges"
    ON public.edges
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
