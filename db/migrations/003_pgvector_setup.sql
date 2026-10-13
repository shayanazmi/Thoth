-- ==============================================================================
-- 003_pgvector_setup.sql - pgvector Semantic Search Extension
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "vector";

-- 5. Embeddings Table
CREATE TABLE IF NOT EXISTS public.embeddings (
    note_id TEXT PRIMARY KEY REFERENCES public.notes(note_id) ON DELETE CASCADE,
    vector vector(384) NOT NULL, -- HuggingFace all-MiniLM-L6-v2 dimension
    dim INTEGER NOT NULL DEFAULT 384,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Enable RLS on Embeddings
ALTER TABLE public.embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can access embeddings for their own notes"
    ON public.embeddings
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM public.notes
            WHERE public.notes.note_id = public.embeddings.note_id
              AND public.notes.user_id = auth.uid()
        )
    );

-- IVFFlat Cosine Similarity Index
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON public.embeddings 
USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);

-- Vector Similarity Search Helper RPC
CREATE OR REPLACE FUNCTION match_notes(
    query_embedding vector(384),
    match_threshold double precision,
    match_count int
)
RETURNS TABLE (
    note_id text,
    similarity double precision
)
LANGUAGE sql STABLE
AS $$
    SELECT
        embeddings.note_id,
        1 - (embeddings.vector <=> query_embedding) AS similarity
    FROM public.embeddings
    WHERE 1 - (embeddings.vector <=> query_embedding) > match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
$$;
