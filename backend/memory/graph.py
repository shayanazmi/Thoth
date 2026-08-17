import collections
from typing import List, Dict, Any, Optional, Union, Set
from backend.memory.db import init_db, DEFAULT_DB_PATH
from backend.memory.vault import Note, extract_links

ALLOWED_RELATIONS = {"cites", "supports", "contradicts", "part_of", "defines", "related"}


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
