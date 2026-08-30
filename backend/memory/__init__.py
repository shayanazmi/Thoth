"""
Thoth Memory & Vault Package
============================
Provides markdown vault management, SQLite store (FTS5 + Vector BLOBs + Knowledge Graph edges),
and hybrid Reciprocal Rank Fusion (RRF) search.
"""

from backend.memory.vault import (
    Note,
    write_note,
    read_note,
    list_notes,
    extract_links,
    audit_vault_notes_citations,
    DEFAULT_VAULT_DIR,
)
from backend.memory.db import (
    init_db,
    get_connection,
    DEFAULT_DB_PATH,
    save_session,
    get_session,
    list_sessions,
    delete_session,
    save_report,
    get_report,
    list_reports,
    get_latest_report,
    get_cached_response,
    set_cached_response,
)
from backend.memory.index import (
    index_note,
    search_keyword,
    search_semantic,
    hybrid_search,
)
from backend.memory.graph import (
    add_edge,
    infer_edges_from_note,
    traverse,
    get_subgraph,
    find_contradictions_among_notes,
    format_vault_context_with_contradictions,
)
from backend.memory.session import (
    SessionMemory,
    DEFAULT_TOKEN_BUDGET,
    RESEARCH_WRITER_TOKEN_BUDGET,
    count_tokens,
    truncate_text_to_tokens,
)

__all__ = [
    "Note",
    "write_note",
    "read_note",
    "list_notes",
    "extract_links",
    "audit_vault_notes_citations",
    "DEFAULT_VAULT_DIR",
    "init_db",
    "get_connection",
    "DEFAULT_DB_PATH",
    "save_session",
    "get_session",
    "list_sessions",
    "delete_session",
    "save_report",
    "get_report",
    "list_reports",
    "get_latest_report",
    "get_cached_response",
    "set_cached_response",
    "index_note",
    "search_keyword",
    "search_semantic",
    "hybrid_search",
    "add_edge",
    "infer_edges_from_note",
    "traverse",
    "get_subgraph",
    "find_contradictions_among_notes",
    "format_vault_context_with_contradictions",
    "SessionMemory",
    "DEFAULT_TOKEN_BUDGET",
    "RESEARCH_WRITER_TOKEN_BUDGET",
    "count_tokens",
    "truncate_text_to_tokens",
]
