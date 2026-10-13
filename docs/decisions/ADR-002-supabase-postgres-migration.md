# ADR-002: Supabase PostgreSQL & pgvector Migration

## Status
Accepted

## Context
Thoth initially persisted sessions, reports, and knowledge graph edges in a local SQLite database (`store.db`) using raw SQL and Python `sqlite3`. While suitable for single-user prototyping, SQLite lacks native network connectivity for cloud deployment on Railway, requires manual file synchronization, cannot enforce multi-tenant Row Level Security (RLS), and relies on raw BLOB storage for vector embeddings.

## Decision
Migrate the persistent storage layer to **Supabase PostgreSQL**:
1. Port all schemas (`sessions`, `reports`, `notes`, `edges`, `embeddings`) to PostgreSQL DDL.
2. Replace SQLite vector BLOBs with native `pgvector` (`vector(384)` with IVFFlat indexing).
3. Enforce **Row Level Security (RLS)** on all tables using `auth.uid() = user_id`.
4. Implement an asynchronous repository layer in `backend/repositories/` utilizing `supabase-py` and `asyncpg`.

## Consequences
- **Positive:** Multi-tenant security out of the box. Highly scalable vector indexing. Direct interoperability with Supabase Auth.
- **Negative:** Requires PostgreSQL connection strings and internet access; local development requires Docker or Supabase CLI.
