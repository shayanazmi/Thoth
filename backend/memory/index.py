import re
import numpy as np
from typing import List, Dict, Any, Optional, Union
import sqlite3

from backend.memory.db import init_db, get_connection, DEFAULT_DB_PATH
from backend.memory.vault import Note, read_note, extract_links, DEFAULT_VAULT_DIR
from backend.telemetry import observe, update_current_span

# Global lazy-loaded embedding model instance (CPU)
_embedding_model = None


def get_embedding_model():
    """
    Lazy-loads all-MiniLM-L6-v2 on CPU.
    """
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _embedding_model


def _sanitize_fts_query(query: str) -> str:
    """
    Sanitizes user query for SQLite FTS5 MATCH expressions.
    Extracts alphanumeric words and joins them with NEAR or space.
    """
    words = re.findall(r"\w+", query)
    if not words:
        return '""'
    # Format each word as prefix or exact match in quotes
    return " ".join(f'"{w}"' for w in words)


def index_note(
    note: Union[Note, Dict[str, Any]],
    db_path: str = DEFAULT_DB_PATH,
    model=None
):
    """
    Indexes a note into SQLite:
    1. Updates notes metadata table.
    2. Updates FTS5 full-text search index table.
    3. Computes 384-dim float32 embedding and stores raw byte BLOB.
    4. Extracts wikilinks/sources and inserts knowledge graph citation edges.
    """
    conn = init_db(db_path)

    # Normalize note representation
    if isinstance(note, Note):
        note_id = note.note_id
        note_type = note.note_type
        content = note.content
        frontmatter = note.frontmatter or {}
    else:
        note_id = note.get("note_id")
        note_type = note.get("type", "topics")
        content = note.get("content", "")
        frontmatter = note.get("frontmatter", {})

    created = frontmatter.get("created", "")
    confidence = float(frontmatter.get("confidence", 1.0))

    # Compute embedding
    embedder = model or get_embedding_model()
    # Embed combined title and content
    text_to_embed = f"{note_id}\n{content}"
    vector = embedder.encode(text_to_embed, convert_to_numpy=True)
    vector_f32 = vector.astype(np.float32)
    vector_bytes = vector_f32.tobytes()
    dim = int(vector_f32.shape[0])

    # Extract linked citations for edges
    cited_notes = extract_links(content)
    sources_fm = frontmatter.get("sources", [])
    if isinstance(sources_fm, list):
        for s in sources_fm:
            if isinstance(s, str) and s not in cited_notes:
                cited_notes.append(s)

    with conn:
        # 1. Upsert notes table
        conn.execute("""
            INSERT INTO notes (note_id, type, created, confidence)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                type = excluded.type,
                created = excluded.created,
                confidence = excluded.confidence;
        """, (note_id, note_type, created, confidence))

        # 2. Update FTS5 table
        conn.execute("DELETE FROM notes_fts WHERE note_id = ?;", (note_id,))
        conn.execute("INSERT INTO notes_fts (note_id, body) VALUES (?, ?);", (note_id, content))

        # 3. Upsert embeddings table
        conn.execute("""
            INSERT INTO embeddings (note_id, vector, dim)
            VALUES (?, ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                vector = excluded.vector,
                dim = excluded.dim;
        """, (note_id, vector_bytes, dim))

        # 4. Insert knowledge graph citation edges
        for target_id in cited_notes:
            if target_id != note_id:
                conn.execute("""
                    INSERT OR IGNORE INTO edges (source_note, relation, target_note, confidence)
                    VALUES (?, 'cites', ?, ?);
                """, (note_id, target_id, confidence))


def search_keyword(
    query: str,
    top_k: int = 5,
    db_path: str = DEFAULT_DB_PATH
) -> List[str]:
    """
    Performs BM25 keyword search against FTS5 notes_fts table.
    Returns ranked note_ids.
    """
    conn = init_db(db_path)
    fts_query = _sanitize_fts_query(query)
    if not fts_query or fts_query == '""':
        return []

    try:
        cursor = conn.execute("""
            SELECT note_id, rank
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
        """, (fts_query, top_k))
        return [row["note_id"] for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []


def search_semantic(
    query: str,
    top_k: int = 5,
    db_path: str = DEFAULT_DB_PATH,
    model=None
) -> List[str]:
    """
    Computes cosine similarity of query against all stored embedding vectors.
    Returns ranked note_ids.
    """
    conn = init_db(db_path)
    cursor = conn.execute("SELECT note_id, vector, dim FROM embeddings;")
    rows = cursor.fetchall()
    if not rows:
        return []

    embedder = model or get_embedding_model()
    query_vec = embedder.encode(query, convert_to_numpy=True).astype(np.float32)
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)

    note_ids = []
    vectors = []
    for r in rows:
        note_ids.append(r["note_id"])
        dim = r["dim"]
        vec = np.frombuffer(r["vector"], dtype=np.float32).reshape(dim)
        vectors.append(vec)

    matrix = np.array(vectors)  # shape: (N, dim)
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
    normalized_matrix = matrix / matrix_norms

    scores = np.dot(normalized_matrix, query_norm)
    top_indices = np.argsort(-scores)[:top_k]

    return [note_ids[i] for i in top_indices]


@observe(type="retriever")
def hybrid_search(
    query: str,
    top_k: int = 6,
    db_path: str = DEFAULT_DB_PATH,
    vault_dir: str = DEFAULT_VAULT_DIR,
    model=None
) -> List[Dict[str, Any]]:
    """
    Executes hybrid search (BM25 keyword + dense vector semantic),
    merges rankings via Reciprocal Rank Fusion (RRF: score = sum(1/(rank + 60))),
    and loads full note content from the markdown vault.
    """
    pool_size = max(top_k * 2, 10)
    kw_results = search_keyword(query, top_k=pool_size, db_path=db_path)
    sem_results = search_semantic(query, top_k=pool_size, db_path=db_path, model=model)

    rrf_scores: Dict[str, float] = {}

    for rank, note_id in enumerate(kw_results, 1):
        rrf_scores[note_id] = rrf_scores.get(note_id, 0.0) + (1.0 / (rank + 60.0))

    for rank, note_id in enumerate(sem_results, 1):
        rrf_scores[note_id] = rrf_scores.get(note_id, 0.0) + (1.0 / (rank + 60.0))

    # Sort descending by RRF score
    ranked_note_ids = sorted(rrf_scores.keys(), key=lambda nid: rrf_scores[nid], reverse=True)[:top_k]

    results = []
    for nid in ranked_note_ids:
        try:
            note_obj = read_note(nid, vault_dir=vault_dir)
            note_dict = note_obj.to_dict()
            note_dict["rrf_score"] = round(rrf_scores[nid], 6)
            results.append(note_dict)
        except Exception:
            # If note file is absent, return partial dictionary from db
            results.append({
                "note_id": nid,
                "type": "unknown",
                "content": "",
                "frontmatter": {},
                "rrf_score": round(rrf_scores[nid], 6)
            })

    # Propagate retrieved note text to active DeepEval retriever span for RAG evaluation
    retrieval_contexts = [r.get("content", "") for r in results if r.get("content")]
    update_current_span(retrieval_context=retrieval_contexts)

    return results
