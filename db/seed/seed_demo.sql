-- ==============================================================================
-- seed_demo.sql - Initial Demo Seed Data
-- ==============================================================================

-- Note: Seed assumes an existing user in auth.users or can be executed with mock user UUID
-- UUID: 00000000-0000-0000-0000-000000000001
DO $$
DECLARE
    demo_user_id UUID := '00000000-0000-0000-0000-000000000001';
    demo_session_id UUID := '00000000-0000-0000-0000-000000000002';
BEGIN
    -- Verify if mock auth user exists before seeding
    IF EXISTS (SELECT 1 FROM auth.users WHERE id = demo_user_id) THEN
        INSERT INTO public.sessions (id, user_id, title, summary)
        VALUES (demo_session_id, demo_user_id, 'Quantum Error Correction Synthesis', 'Initial demo research session on cat qubits')
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO public.notes (note_id, user_id, type, title, content)
        VALUES 
            ('topic-quantum_error_correction', demo_user_id, 'topic', 'Quantum Error Correction', 'Overview of fault-tolerant quantum error correction techniques.'),
            ('src-cat_qubits_overview', demo_user_id, 'source', 'Cat Qubits 2026', 'Primary source on autonomous quantum error correction using bosonic modes.')
        ON CONFLICT (note_id) DO NOTHING;

        INSERT INTO public.edges (source_note, relation, target_note, user_id, confidence)
        VALUES 
            ('src-cat_qubits_overview', 'supports', 'topic-quantum_error_correction', demo_user_id, 0.98)
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
