import collections
from typing import List, Dict, Any, Optional, Union, Set, Tuple
from backend.memory.db import init_db, DEFAULT_DB_PATH
from backend.memory.vault import Note, extract_links

ALLOWED_RELATIONS = {
    "cites", "cited_by", "supports", "contradicts", "part_of",
    "defines", "related", "recommends", "authored_by"
}



def add_edge(
    source_note: str,
    relation: str,
    target_note: str,
    confidence: float = 1.0,
    db_path: str = DEFAULT_DB_PATH
):
    """
    Inserts or updates a directed relationship between two notes in the edges table.
    """
    clean_relation = relation.lower().strip()
    if clean_relation not in ALLOWED_RELATIONS:
        clean_relation = "related"

    conn = init_db(db_path)
    with conn:
        conn.execute("""
            INSERT INTO edges (source_note, relation, target_note, confidence)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_note, relation, target_note) DO UPDATE SET
                confidence = excluded.confidence;
        """, (source_note, clean_relation, target_note, float(confidence)))


def infer_edges_from_note(
    note: Union[Note, Dict[str, Any]],
    default_relation: str = "related",
    confidence: float = 1.0,
    db_path: str = DEFAULT_DB_PATH
) -> List[str]:
    """
    Automatically extracts [[wikilink]] references from note content and inserts edges.
    Returns the list of target note IDs linked.
    """
    if isinstance(note, Note):
        source_note = note.note_id
        content = note.content
        sources = note.frontmatter.get("sources", [])
    else:
        source_note = note.get("note_id", "")
        content = note.get("content", "")
        sources = note.get("frontmatter", {}).get("sources", [])

    targets = extract_links(content)
    if isinstance(sources, list):
        for s in sources:
            if isinstance(s, str) and s not in targets:
                targets.append(s)

    for target in targets:
        if target != source_note:
            add_edge(
                source_note=source_note,
                relation=default_relation,
                target_note=target,
                confidence=confidence,
                db_path=db_path
            )

    return targets


def traverse(
    start_note: str,
    relation: Optional[str] = None,
    max_depth: int = 2,
    db_path: str = DEFAULT_DB_PATH
) -> List[str]:
    """
    Traverses the knowledge graph up to max_depth hops from start_note using BFS.
    Optionally filters by relation type.
    Returns an ordered list of unique connected note IDs.
    """
    if max_depth <= 0:
        return []

    conn = init_db(db_path)
    visited: Set[str] = {start_note}
    result: List[str] = []

    # Queue contains tuples of (current_note_id, current_depth)
    queue = collections.deque([(start_note, 0)])

    while queue:
        curr_note, depth = queue.popleft()
        if depth >= max_depth:
            continue

        if relation:
            cursor = conn.execute("""
                SELECT target_note
                FROM edges
                WHERE source_note = ? AND relation = ?;
            """, (curr_note, relation.lower().strip()))
        else:
            cursor = conn.execute("""
                SELECT target_note
                FROM edges
                WHERE source_note = ?;
            """, (curr_note,))

        neighbors = [row["target_note"] for row in cursor.fetchall()]

        for neighbor in neighbors:
            if neighbor not in visited:
                visited.add(neighbor)
                result.append(neighbor)
                queue.append((neighbor, depth + 1))

    return result


def get_subgraph(
    start_note: str,
    max_depth: int = 2,
    relation: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Returns the connected subgraph (nodes + edges) up to max_depth hops from start_note.
    """
    conn = init_db(db_path)
    nodes = {start_note}
    edges_list = []

    queue = collections.deque([(start_note, 0)])
    visited_nodes = {start_note}

    while queue:
        curr_note, depth = queue.popleft()
        if depth >= max_depth:
            continue

        if relation:
            cursor = conn.execute("""
                SELECT source_note, relation, target_note, confidence
                FROM edges
                WHERE source_note = ? AND relation = ?;
            """, (curr_note, relation.lower().strip()))
        else:
            cursor = conn.execute("""
                SELECT source_note, relation, target_note, confidence
                FROM edges
                WHERE source_note = ?;
            """, (curr_note,))

        for row in cursor.fetchall():
            s, r, t, c = row["source_note"], row["relation"], row["target_note"], row["confidence"]
            edges_list.append({
                "source": s,
                "relation": r,
                "target": t,
                "confidence": c
            })
            nodes.add(t)
            if t not in visited_nodes:
                visited_nodes.add(t)
                queue.append((t, depth + 1))

    return {
        "nodes": sorted(list(nodes)),
        "edges": edges_list
    }


def find_contradictions_among_notes(
    note_ids: List[str],
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Checks if any pairs of note IDs in the provided list are connected by a 'contradicts' edge
    in the knowledge graph in either direction.
    Returns a list of contradiction dictionaries: [{'source': id_a, 'target': id_b, 'confidence': float}].
    """
    if not note_ids or len(note_ids) < 2:
        return []

    conn = init_db(db_path)
    clean_ids = [str(nid).strip() for nid in note_ids if str(nid).strip()]
    if len(clean_ids) < 2:
        return []

    placeholders = ",".join(["?"] * len(clean_ids))
    query = f"""
        SELECT source_note, relation, target_note, confidence
        FROM edges
        WHERE relation = 'contradicts'
          AND source_note IN ({placeholders})
          AND target_note IN ({placeholders});
    """
    params = clean_ids + clean_ids
    cursor = conn.execute(query, params)
    
    seen_pairs: Set[Tuple[str, str]] = set()
    contradictions = []

    for row in cursor.fetchall():
        s, t, conf = row["source_note"], row["target_note"], row["confidence"]
        # Normalize pair order to prevent duplicate reporting of bidirectional contradictions
        pair = (min(s, t), max(s, t))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            contradictions.append({
                "source": s,
                "target": t,
                "confidence": float(conf)
            })

    return contradictions


def format_vault_context_with_contradictions(
    notes: List[Dict[str, Any]],
    db_path: str = DEFAULT_DB_PATH,
    max_char_per_note: int = 800
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Formats a list of retrieved vault notes into context text for LLM synthesis.
    If any retrieved notes have 'contradicts' edges in the knowledge graph, injects
    an explicit contradiction awareness alert to prevent contradiction leakage.
    Returns (formatted_context_text, contradictions_found).
    """
    if not notes:
        return "", []

    note_ids = [n.get("note_id") for n in notes if n.get("note_id")]
    contradictions = find_contradictions_among_notes(note_ids, db_path=db_path)

    sections = []
    if contradictions:
        alert_lines = [
            "[KNOWLEDGE GRAPH CONTRADICTION ALERT]",
            "The following retrieved notes contain known direct contradictions in the research vault:"
        ]
        for c in contradictions:
            alert_lines.append(f"- Note [{c['source']}] CONTRADICTS Note [{c['target']}] (confidence {c['confidence']:.2f})")
        alert_lines.append(
            "CRITICAL WRITING DIRECTIVE: You MUST explicitly acknowledge and discuss this conflict/discrepancy "
            "in your synthesis rather than presenting both as uncontested supporting facts for the same claim."
        )
        sections.append("\n".join(alert_lines))

    for n in notes:
        nid = n.get("note_id", "unknown")
        content = n.get("content", "")[:max_char_per_note]
        sections.append(f"--- Vault Note [{nid}]:\n{content}")

    formatted_text = "\n\n".join(sections)
    return formatted_text, contradictions


def export_citation_subgraph(
    start_notes: Optional[List[str]] = None,
    max_depth: int = 2,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Exports nodes and edges from the SQLite knowledge graph formatted for
    interactive 2D/3D D3 network visualization in the UI.
    """
    conn = init_db(db_path)
    nodes_dict = {}
    edges_list = []

    # If start_notes provided, traverse around them; otherwise get recent graph
    if start_notes:
        collected_notes = set(start_notes)
        for sn in start_notes:
            connected = traverse(sn, max_depth=max_depth, db_path=db_path)
            collected_notes.update(connected)

        placeholders = ",".join(["?"] * len(collected_notes))
        cursor = conn.execute(f"""
            SELECT note_id, type, created
            FROM notes
            WHERE note_id IN ({placeholders})
        """, list(collected_notes))
        for row in cursor.fetchall():
            nodes_dict[row["note_id"]] = {
                "id": row["note_id"],
                "label": row["note_id"],
                "type": row["type"] or "concept",
                "created_at": row["created"]
            }

        edge_cursor = conn.execute(f"""
            SELECT source_note, relation, target_note, confidence
            FROM edges
            WHERE source_note IN ({placeholders}) OR target_note IN ({placeholders})
        """, list(collected_notes) + list(collected_notes))
    else:
        # Fetch all or top 50 recent notes
        cursor = conn.execute("""
            SELECT note_id, type, created
            FROM notes
            ORDER BY created DESC
            LIMIT 60
        """)
        for row in cursor.fetchall():
            nodes_dict[row["note_id"]] = {
                "id": row["note_id"],
                "label": row["note_id"],
                "type": row["type"] or "concept",
                "created_at": row["created"]
            }

        edge_cursor = conn.execute("""
            SELECT source_note, relation, target_note, confidence
            FROM edges
            LIMIT 120
        """)


    seen_edges = set()
    for erow in edge_cursor.fetchall():
        s, r, t, conf = erow["source_note"], erow["relation"], erow["target_note"], erow["confidence"]
        edge_key = (s, r, t)
        if edge_key not in seen_edges:
            seen_edges.add(edge_key)
            edges_list.append({
                "from": s,
                "to": t,
                "relation": r,
                "confidence": float(conf)
            })
            # Ensure endpoints exist in nodes_dict
            if s not in nodes_dict:
                nodes_dict[s] = {"id": s, "label": s, "type": "source" if s.startswith("src-") else "concept"}
            if t not in nodes_dict:
                nodes_dict[t] = {"id": t, "label": t, "type": "source" if t.startswith("src-") else "concept"}

    return {
        "nodes": list(nodes_dict.values()),
        "edges": edges_list
    }


