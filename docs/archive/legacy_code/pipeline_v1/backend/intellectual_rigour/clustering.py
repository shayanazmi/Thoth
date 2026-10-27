"""
THOTH Deep Semantic Literature Clustering & Citation Network Graph Visualization Engine
Phase 7 — Deliverable A: Thematic Clustering, Citation Topology, Bridge Papers & Structural Holes.

Provides advanced epistemological mapping of literature reviews:
- Semantic representation of papers via TF-IDF and n-gram vectors.
- Unsupervised thematic clustering with cluster labeling, keywords, and seminal paper detection.
- Directed citation network graph construction with in/out degree, betweenness centrality, and bridge scores.
- Structural hole discovery: identifying conceptually related clusters lacking citation bridges.
- Force-directed 2D layout coordinate generation for interactive visualization.
- Mermaid flowchart generation for embedded markdown publication reports.
- Full integration with PRISMA screening ledgers, snowball candidates, and SQLite persistence.
"""

from __future__ import annotations

import datetime
import math
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
from pydantic import BaseModel, Field
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.core.logging import get_logger
from backend.memory.db import (
    DEFAULT_DB_PATH,
    get_literature_clustering_db,
    init_db,
    save_citation_graph_db,
    save_literature_clustering_db,
)

logger = get_logger("LiteratureClusteringEngine")


# ==============================================================================
# Domain Models
# ==============================================================================

class ThematicCluster(BaseModel):
    cluster_id: str
    name: str
    summary: str
    keywords: List[str] = Field(default_factory=list)
    paper_ids: List[str] = Field(default_factory=list)
    size: int = 0
    seminal_paper_id: Optional[str] = None
    seminal_paper_title: Optional[str] = None
    cohesion_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "summary": self.summary,
            "keywords": self.keywords,
            "paper_ids": self.paper_ids,
            "size": self.size,
            "seminal_paper_id": self.seminal_paper_id,
            "seminal_paper_title": self.seminal_paper_title,
            "cohesion_score": round(self.cohesion_score, 4),
        }


class CitationNode(BaseModel):
    id: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    citation_count: int = 0
    prisma_disposition: str = "CANDIDATE"
    hypothesis_stance: Optional[str] = None
    cluster_id: str = "cluster-0"
    cluster_name: str = ""
    in_degree: int = 0
    out_degree: int = 0
    betweenness_centrality: float = 0.0
    bridge_score: float = 0.0
    is_bridge: bool = False
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "citation_count": self.citation_count,
            "prisma_disposition": self.prisma_disposition,
            "hypothesis_stance": self.hypothesis_stance,
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
            "betweenness_centrality": round(self.betweenness_centrality, 4),
            "bridge_score": round(self.bridge_score, 4),
            "is_bridge": self.is_bridge,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
        }


class CitationEdge(BaseModel):
    source: str
    target: str
    relation: str = "cites"  # "cites", "co_citation", "coupling", "contradicts", "semantic_link"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": round(self.weight, 4),
        }


class StructuralHole(BaseModel):
    cluster_a_id: str
    cluster_a_name: str
    cluster_b_id: str
    cluster_b_name: str
    semantic_similarity: float
    citation_bridge_count: int
    research_opportunity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_a_id": self.cluster_a_id,
            "cluster_a_name": self.cluster_a_name,
            "cluster_b_id": self.cluster_b_id,
            "cluster_b_name": self.cluster_b_name,
            "semantic_similarity": round(self.semantic_similarity, 4),
            "citation_bridge_count": self.citation_bridge_count,
            "research_opportunity": self.research_opportunity,
        }


class LiteratureCitationGraph(BaseModel):
    review_id: str
    project_id: Optional[str] = None
    nodes: List[CitationNode] = Field(default_factory=list)
    edges: List[CitationEdge] = Field(default_factory=list)
    clusters: List[ThematicCluster] = Field(default_factory=list)
    bridge_papers: List[str] = Field(default_factory=list)
    structural_holes: List[StructuralHole] = Field(default_factory=list)
    density: float = 0.0
    connected_components: int = 1
    created_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "project_id": self.project_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "clusters": [c.to_dict() for c in self.clusters],
            "bridge_papers": self.bridge_papers,
            "structural_holes": [h.to_dict() for h in self.structural_holes],
            "density": round(self.density, 4),
            "connected_components": self.connected_components,
            "created_at": self.created_at,
        }


class ClusteringResult(BaseModel):
    run_id: str
    review_id: str
    project_id: Optional[str] = None
    total_papers: int = 0
    num_clusters: int = 0
    clusters: List[ThematicCluster] = Field(default_factory=list)
    graph: LiteratureCitationGraph
    summary: str = ""
    created_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "review_id": self.review_id,
            "project_id": self.project_id,
            "total_papers": self.total_papers,
            "num_clusters": self.num_clusters,
            "clusters": [c.to_dict() for c in self.clusters],
            "graph": self.graph.to_dict(),
            "summary": self.summary,
            "created_at": self.created_at,
        }


# ==============================================================================
# Helper Functions: Data Aggregation & Normalization
# ==============================================================================

def normalize_paper_id(identifier: str) -> str:
    """Normalize paper identifiers across DOIs, ArXiv IDs, URLs, and titles."""
    if not identifier:
        return ""
    clean = str(identifier).strip()
    if clean.lower().startswith("doi:") or "10." in clean:
        match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", clean)
        if match:
            return f"doi:{match.group(0).lower().rstrip('.')}"
    if clean.lower().startswith("arxiv:") or "arxiv.org" in clean.lower():
        match = re.search(r"\d{4}\.\d{4,5}(v\d+)?", clean)
        if match:
            return f"arxiv:{match.group(0).lower()}"
    if clean.lower().startswith("s2:") or clean.lower().startswith("corpusid:"):
        return clean.lower()
    # Fallback: title slug
    slug = re.sub(r"[^a-z0-9]+", "-", clean.lower())[:60].strip("-")
    return f"paper:{slug}" if slug else f"paper:{uuid.uuid4().hex[:8]}"


def build_literature_corpus(
    review_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Extracts all papers associated with a PRISMA review:
    1. Included and screened studies from `screening_decisions`.
    2. Discovered candidates from Phase 6 `snowball_candidates`.
    3. Appraisal metrics from `prisma_reviews.evidence_matrix`.
    """
    conn = init_db(db_path)
    papers_map: Dict[str, Dict[str, Any]] = {}

    # 1. Fetch screening decisions
    try:
        cur = conn.execute("""
            SELECT decision_id, source_id, source_url, title, stage,
                   disposition, exclusion_reason, rationale, supporting_passages_json,
                   reviewer_type, study_id, created_at
            FROM screening_decisions
            WHERE review_id = ?
            ORDER BY created_at ASC
        """, (review_id,))
        for row in cur.fetchall():
            title = row["title"] or row["source_url"] or "Untitled Document"
            paper_id = normalize_paper_id(row["source_url"] or title)
            import json
            abstract = row["rationale"] or ""
            if row["supporting_passages_json"]:
                try:
                    passages = json.loads(row["supporting_passages_json"])
                    if isinstance(passages, list) and passages:
                        abstract += " " + " ".join(str(p) for p in passages)
                except Exception:
                    pass

            papers_map[paper_id] = {
                "id": paper_id,
                "title": title,
                "url": row["source_url"] or "",
                "authors": [],
                "abstract": abstract.strip(),
                "prisma_disposition": row["disposition"] or "CANDIDATE",
                "hypothesis_stance": "SUPPORTS" if row["disposition"] == "INCLUDED" else None,
                "citation_count": 0,
                "year": None,
                "source_type": "screening_decision",
                "cited_by": set(),
                "cites": set(),
            }
    except Exception as e:
        logger.warning(f"Could not load screening decisions for review {review_id}: {e}")

    # 2. Fetch Phase 6 snowball candidates
    try:
        cur = conn.execute("""
            SELECT sc.candidate_id, sc.paper_id, sc.parent_paper_id, sc.title,
                   sc.doi, sc.direction, sc.round_number, sc.provider,
                   sc.lookup_params_json, sc.created_at
            FROM snowball_candidates sc
            JOIN snowball_runs sr ON sc.run_id = sr.run_id
            WHERE sr.review_id = ?
            ORDER BY sc.round_number ASC
        """, (review_id,))
        for row in cur.fetchall():
            raw_id = row["doi"] or row["paper_id"] or row["title"]
            norm_id = normalize_paper_id(raw_id)
            parent_raw = row["parent_paper_id"]
            norm_parent = normalize_paper_id(parent_raw) if parent_raw else None

            import json
            params = {}
            if row["lookup_params_json"]:
                try:
                    params = json.loads(row["lookup_params_json"])
                except Exception:
                    params = {}

            authors = params.get("authors") or []
            abstract = params.get("abstract") or ""
            cit_count = params.get("citation_count") or 0
            pub_date = params.get("published_date") or ""
            year = None
            if pub_date:
                match = re.search(r"\b(19\d\d|20\d\d)\b", str(pub_date))
                if match:
                    year = int(match.group(1))

            if norm_id not in papers_map:
                papers_map[norm_id] = {
                    "id": norm_id,
                    "title": row["title"] or norm_id,
                    "url": params.get("url") or "",
                    "authors": authors if isinstance(authors, list) else [],
                    "abstract": abstract,
                    "prisma_disposition": "CANDIDATE",
                    "hypothesis_stance": None,
                    "citation_count": cit_count,
                    "year": year,
                    "source_type": "snowball_candidate",
                    "cited_by": set(),
                    "cites": set(),
                }
            else:
                # Merge details
                if not papers_map[norm_id]["abstract"] and abstract:
                    papers_map[norm_id]["abstract"] = abstract
                if cit_count:
                    papers_map[norm_id]["citation_count"] = max(
                        papers_map[norm_id]["citation_count"], cit_count
                    )
                if not papers_map[norm_id]["year"] and year:
                    papers_map[norm_id]["year"] = year

            # Record citation link
            if norm_parent and norm_parent != norm_id:
                if row["direction"] == "BACKWARD":
                    # parent cites candidate
                    if norm_parent in papers_map:
                        papers_map[norm_parent]["cites"].add(norm_id)
                    papers_map[norm_id]["cited_by"].add(norm_parent)
                else:
                    # candidate cites parent (FORWARD)
                    papers_map[norm_id]["cites"].add(norm_parent)
                    if norm_parent in papers_map:
                        papers_map[norm_parent]["cited_by"].add(norm_id)
    except Exception as e:
        logger.warning(f"Could not load snowball candidates for review {review_id}: {e}")

    # Convert sets to lists
    results = []
    for p in papers_map.values():
        p_copy = dict(p)
        p_copy["cited_by"] = sorted(list(p["cited_by"]))
        p_copy["cites"] = sorted(list(p["cites"]))
        results.append(p_copy)

    return results


# ==============================================================================
# Thematic Clustering Engine
# ==============================================================================

def compute_thematic_clusters(
    papers: List[Dict[str, Any]],
    n_clusters: Optional[int] = None
) -> Tuple[List[ThematicCluster], Dict[str, str], Dict[str, float]]:
    """
    Performs deterministic semantic clustering over the paper corpus:
    1. Extracts combined text representations (title + abstract).
    2. Builds TF-IDF feature vectors.
    3. Executes KMeans with deterministic seeding.
    4. Identifies top keywords, cluster labels, summaries, and seminal papers.
    """
    if not papers:
        return [], {}, {}

    if len(papers) == 1:
        single = papers[0]
        cid = "cluster-1"
        words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", single["title"])[:5]]
        cluster = ThematicCluster(
            cluster_id=cid,
            name=f"Focal Study: {single['title'][:40]}...",
            summary=f"Primary research investigation focused on {single['title']}.",
            keywords=words or ["research", "evidence"],
            paper_ids=[single["id"]],
            size=1,
            seminal_paper_id=single["id"],
            seminal_paper_title=single["title"],
            cohesion_score=1.0,
        )
        return [cluster], {single["id"]: cid}, {single["id"]: 1.0}

    # Prepare text documents
    corpus_texts = []
    for p in papers:
        text = f"{p['title']} {p['title']} {p.get('abstract', '')}"
        corpus_texts.append(text.strip())

    # TF-IDF Vectorization
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=250,
            ngram_range=(1, 2),
            min_df=1
        )
        X = vectorizer.fit_transform(corpus_texts)
        feature_names = vectorizer.get_feature_names_out()
    except Exception as e:
        logger.warning(f"TF-IDF vectorizer fallback: {e}")
        X = np.eye(len(papers))
        feature_names = [f"term_{i}" for i in range(len(papers))]

    # Determine optimal k
    num_papers = len(papers)
    if n_clusters is not None:
        k = max(1, min(n_clusters, num_papers))
    else:
        # Heuristic: between 2 and min(6, sqrt(N))
        k = max(2, min(6, int(math.ceil(math.sqrt(num_papers)))))
        k = min(k, num_papers)

    # Perform KMeans
    try:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)
        centroids = kmeans.cluster_centers_
    except Exception as e:
        logger.warning(f"KMeans failed, assigning uniform clusters: {e}")
        labels = [i % k for i in range(num_papers)]
        centroids = np.zeros((k, X.shape[1] if hasattr(X, "shape") else 1))

    # Group papers by cluster
    cluster_groups: Dict[int, List[int]] = {i: [] for i in range(k)}
    for idx, label in enumerate(labels):
        cluster_groups[label].append(idx)

    thematic_clusters: List[ThematicCluster] = []
    paper_to_cluster: Dict[str, str] = {}
    paper_cohesion_map: Dict[str, float] = {}

    for c_idx in sorted(cluster_groups.keys()):
        p_indices = cluster_groups[c_idx]
        if not p_indices:
            continue

        cid = f"cluster-{c_idx + 1}"
        cluster_papers = [papers[i] for i in p_indices]
        paper_ids = [p["id"] for p in cluster_papers]

        for pid in paper_ids:
            paper_to_cluster[pid] = cid

        # Extract top keywords from centroid
        top_keywords = []
        if hasattr(centroids, "shape") and len(feature_names) > 0 and c_idx < len(centroids):
            centroid_vec = centroids[c_idx]
            top_kw_indices = centroid_vec.argsort()[::-1][:6]
            top_keywords = [
                feature_names[i] for i in top_kw_indices
                if i < len(feature_names) and centroid_vec[i] > 0.01
            ]

        if not top_keywords:
            # Fallback: extract title words
            word_counts: Dict[str, int] = {}
            for cp in cluster_papers:
                for w in re.findall(r"[A-Za-z]{4,}", cp["title"].lower()):
                    if w not in {"with", "from", "that", "this", "study", "analysis", "using"}:
                        word_counts[w] = word_counts.get(w, 0) + 1
            top_keywords = [w for w, _ in sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

        if not top_keywords:
            top_keywords = ["evidence", "methodology"]

        # Select seminal paper (highest citations or within-cluster degree)
        seminal_paper = max(
            cluster_papers,
            key=lambda p: (p.get("citation_count", 0), len(p.get("cited_by", [])))
        )

        # Calculate cluster cohesion (average cosine similarity to centroid or pairwise)
        cohesion = 0.85
        if len(p_indices) > 1 and hasattr(X, "toarray"):
            try:
                sub_matrix = X[p_indices]
                sim_matrix = cosine_similarity(sub_matrix)
                # average off-diagonal
                n_sub = len(p_indices)
                cohesion = float((sim_matrix.sum() - n_sub) / (n_sub * (n_sub - 1)))
            except Exception:
                cohesion = 0.75

        # Format cluster name and summary
        title_words = [kw.title() for kw in top_keywords[:3]]
        cluster_name = " & ".join(title_words) if title_words else f"Theme {c_idx + 1}"
        summary = (
            f"Thematic cluster centered on {', '.join(top_keywords[:4])}. "
            f"Anchored by seminal work '{seminal_paper['title'][:60]}' "
            f"with {len(cluster_papers)} constituent studies."
        )

        t_cluster = ThematicCluster(
            cluster_id=cid,
            name=cluster_name,
            summary=summary,
            keywords=top_keywords,
            paper_ids=paper_ids,
            size=len(paper_ids),
            seminal_paper_id=seminal_paper["id"],
            seminal_paper_title=seminal_paper["title"],
            cohesion_score=max(0.0, min(1.0, cohesion)),
        )
        thematic_clusters.append(t_cluster)

        for pid in paper_ids:
            paper_cohesion_map[pid] = cohesion

    return thematic_clusters, paper_to_cluster, paper_cohesion_map


# ==============================================================================
# Citation Network Graph & Centrality Engine
# ==============================================================================

def compute_citation_network_metrics(
    papers: List[Dict[str, Any]],
    clusters: List[ThematicCluster],
    paper_to_cluster: Dict[str, str]
) -> Tuple[
    List[CitationNode],
    List[CitationEdge],
    List[str],
    List[StructuralHole],
    float,
    int
]:
    """
    Constructs a directed NetworkX graph, calculates:
    - In-degree, out-degree.
    - Betweenness centrality via Brandes' algorithm.
    - Cross-cluster Bridge Scores.
    - 2D force-directed layout coordinates $(x, y)$.
    - Structural holes across distinct clusters.
    """
    if not papers:
        return [], [], [], [], 0.0, 0

    paper_map = {p["id"]: p for p in papers}
    cluster_map = {c.cluster_id: c for c in clusters}

    # Initialize directed network graph
    G = nx.DiGraph()
    for p in papers:
        G.add_node(p["id"])

    edges_list: List[CitationEdge] = []
    seen_edges: Set[Tuple[str, str]] = set()

    # 1. Add direct citation edges from known cited_by / cites
    for p in papers:
        src = p["id"]
        # p cites target
        for tgt in p.get("cites", []):
            if tgt in paper_map and (src, tgt) not in seen_edges and src != tgt:
                seen_edges.add((src, tgt))
                G.add_edge(src, tgt, weight=1.0, relation="cites")
                edges_list.append(CitationEdge(source=src, target=tgt, relation="cites", weight=1.0))
        # target cited_by p -> p cites target
        for cby in p.get("cited_by", []):
            if cby in paper_map and (cby, src) not in seen_edges and cby != src:
                seen_edges.add((cby, src))
                G.add_edge(cby, src, weight=1.0, relation="cites")
                edges_list.append(CitationEdge(source=cby, target=src, relation="cites", weight=1.0))

    # 2. Add dialectic contradiction edges if present
    for p in papers:
        if p.get("hypothesis_stance") in {"CHALLENGES", "CONTRADICTED"}:
            for other in papers:
                if other["id"] != p["id"] and other.get("hypothesis_stance") in {"SUPPORTS", "SUPPORTED"}:
                    pair = (p["id"], other["id"])
                    if pair not in seen_edges:
                        seen_edges.add(pair)
                        G.add_edge(p["id"], other["id"], weight=1.5, relation="contradicts")
                        edges_list.append(CitationEdge(source=p["id"], target=other["id"], relation="contradicts", weight=1.5))

    # 3. If graph is too sparse (< 2 edges), add semantic similarity edges so nodes don't float completely disconnected
    if len(edges_list) < max(2, len(papers) // 2) and len(papers) > 1:
        try:
            texts = [f"{p['title']} {p.get('abstract', '')}" for p in papers]
            tfidf = TfidfVectorizer(stop_words="english", max_features=100)
            X = tfidf.fit_transform(texts)
            sim = cosine_similarity(X)
            for i in range(len(papers)):
                for j in range(i + 1, len(papers)):
                    if sim[i, j] >= 0.25:
                        s_id, t_id = papers[i]["id"], papers[j]["id"]
                        if (s_id, t_id) not in seen_edges and (t_id, s_id) not in seen_edges:
                            seen_edges.add((s_id, t_id))
                            G.add_edge(s_id, t_id, weight=float(sim[i, j]), relation="semantic_link")
                            edges_list.append(CitationEdge(source=s_id, target=t_id, relation="semantic_link", weight=float(sim[i, j])))
        except Exception as e:
            logger.debug(f"Semantic edge fallback skipped: {e}")

    # Compute graph metrics
    in_degrees = dict(G.in_degree())
    out_degrees = dict(G.out_degree())
    betweenness = nx.betweenness_centrality(G, weight="weight")
    density = float(nx.density(G))
    try:
        components = nx.number_weakly_connected_components(G)
    except Exception:
        components = 1

    # Compute Bridge Scores: Betweenness * Cross-Cluster Span
    bridge_scores: Dict[str, float] = {}
    bridge_papers: List[str] = []

    for pid in G.nodes():
        node_cluster = paper_to_cluster.get(pid, "cluster-0")
        neighbor_clusters = set()
        for neighbor in set(G.predecessors(pid)) | set(G.successors(pid)):
            n_cluster = paper_to_cluster.get(neighbor)
            if n_cluster and n_cluster != node_cluster:
                neighbor_clusters.add(n_cluster)

        # Bridge score rewards betweenness and crossing cluster boundaries
        b_score = betweenness.get(pid, 0.0) * (1.0 + 2.0 * len(neighbor_clusters))
        bridge_scores[pid] = b_score
        if len(neighbor_clusters) >= 1 or b_score >= 0.15:
            bridge_papers.append(pid)

    # 4. Generate 2D Layout Coordinates (Spring Layout / Force-Directed)
    layout_coords: Dict[str, Tuple[float, float]] = {}
    if len(papers) == 1:
        layout_coords[papers[0]["id"]] = (0.0, 0.0)
    else:
        try:
            pos = nx.spring_layout(G, k=1.8 / math.sqrt(len(papers)), iterations=60, seed=42)
            # Scale coordinates to [-100.0, 100.0]
            for pid, (x, y) in pos.items():
                layout_coords[pid] = (float(x * 100.0), float(y * 100.0))
        except Exception as e:
            logger.warning(f"Spring layout failed, generating circular coordinates: {e}")
            for i, p in enumerate(papers):
                angle = 2 * math.pi * i / len(papers)
                layout_coords[p["id"]] = (math.cos(angle) * 80.0, math.sin(angle) * 80.0)

    # 5. Build Final Node Models
    nodes_list: List[CitationNode] = []
    for p in papers:
        pid = p["id"]
        cid = paper_to_cluster.get(pid, "cluster-0")
        cname = cluster_map[cid].name if cid in cluster_map else "Uncategorized"
        x, y = layout_coords.get(pid, (0.0, 0.0))

        node = CitationNode(
            id=pid,
            title=p["title"],
            authors=p.get("authors", []),
            year=p.get("year"),
            citation_count=p.get("citation_count", 0),
            prisma_disposition=p.get("prisma_disposition", "CANDIDATE"),
            hypothesis_stance=p.get("hypothesis_stance"),
            cluster_id=cid,
            cluster_name=cname,
            in_degree=in_degrees.get(pid, 0),
            out_degree=out_degrees.get(pid, 0),
            betweenness_centrality=betweenness.get(pid, 0.0),
            bridge_score=bridge_scores.get(pid, 0.0),
            is_bridge=(pid in bridge_papers),
            x=x,
            y=y,
        )
        nodes_list.append(node)

    # 6. Discover Structural Holes between clusters
    structural_holes: List[StructuralHole] = []
    if len(clusters) >= 2:
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                c_a = clusters[i]
                c_b = clusters[j]
                # Count citation bridges between c_a and c_b
                bridge_count = 0
                for edge in edges_list:
                    src_c = paper_to_cluster.get(edge.source)
                    tgt_c = paper_to_cluster.get(edge.target)
                    if (src_c == c_a.cluster_id and tgt_c == c_b.cluster_id) or \
                       (src_c == c_b.cluster_id and tgt_c == c_a.cluster_id):
                        bridge_count += 1

                # Calculate inter-cluster keyword overlap / similarity
                overlap = len(set(c_a.keywords) & set(c_b.keywords))
                sim_score = overlap / max(1, len(set(c_a.keywords) | set(c_b.keywords)))

                # If conceptually proximate but sparsely connected: structural hole
                if bridge_count <= 1 and (sim_score >= 0.15 or len(c_a.paper_ids) + len(c_b.paper_ids) >= 4):
                    opportunity = (
                        f"Unbridged epistemic gap between '{c_a.name}' and '{c_b.name}'. "
                        f"Only {bridge_count} direct citation link(s) connect these distinct bodies of scholarship, "
                        f"indicating a fertile interdisciplinary synthesis opportunity."
                    )
                    structural_holes.append(StructuralHole(
                        cluster_a_id=c_a.cluster_id,
                        cluster_a_name=c_a.name,
                        cluster_b_id=c_b.cluster_id,
                        cluster_b_name=c_b.name,
                        semantic_similarity=float(sim_score),
                        citation_bridge_count=bridge_count,
                        research_opportunity=opportunity,
                    ))

    return nodes_list, edges_list, sorted(bridge_papers), structural_holes, density, components


# ==============================================================================
# Master Workflow Execution & Mermaid Generation
# ==============================================================================

def run_literature_clustering_and_graph(
    review_id: str,
    project_id: Optional[str] = None,
    n_clusters: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH
) -> ClusteringResult:
    """
    Executes the full semantic clustering and citation network synthesis for a PRISMA review:
    1. Aggregates review papers from screening decisions and snowball candidates.
    2. Clusters papers into coherent thematic groups.
    3. Analyzes citation topology, computes centrality metrics, bridge papers, and structural holes.
    4. Projects 2D coordinates for interactive visualization.
    5. Persists clustering and graph records in SQLite.
    """
    run_id = f"clust-{uuid.uuid4().hex[:10]}"
    logger.info(f"Executing Literature Clustering & Graph Analysis for review={review_id} (run={run_id})")

    # 1. Build paper corpus
    papers = build_literature_corpus(review_id, db_path=db_path)
    if not papers:
        logger.warning(f"No papers found for review {review_id}. Returning empty clustering graph.")
        empty_graph = LiteratureCitationGraph(review_id=review_id, project_id=project_id)
        res = ClusteringResult(
            run_id=run_id,
            review_id=review_id,
            project_id=project_id,
            total_papers=0,
            num_clusters=0,
            clusters=[],
            graph=empty_graph,
            summary="No literature review records found to cluster."
        )
        return res

    # 2. Compute thematic clusters
    clusters, paper_to_cluster, _ = compute_thematic_clusters(papers, n_clusters=n_clusters)

    # 3. Compute citation network topology and metrics
    nodes, edges, bridge_papers, structural_holes, density, components = compute_citation_network_metrics(
        papers, clusters, paper_to_cluster
    )

    # 4. Construct graph model
    citation_graph = LiteratureCitationGraph(
        review_id=review_id,
        project_id=project_id,
        nodes=nodes,
        edges=edges,
        clusters=clusters,
        bridge_papers=bridge_papers,
        structural_holes=structural_holes,
        density=density,
        connected_components=components,
    )

    summary = (
        f"Synthesized {len(papers)} scholarly papers into {len(clusters)} thematic clusters "
        f"across a citation network with {len(edges)} directed links (density {density:.3f}). "
        f"Identified {len(bridge_papers)} interdisciplinary bridge paper(s) and {len(structural_holes)} structural hole(s)."
    )

    result = ClusteringResult(
        run_id=run_id,
        review_id=review_id,
        project_id=project_id,
        total_papers=len(papers),
        num_clusters=len(clusters),
        clusters=clusters,
        graph=citation_graph,
        summary=summary,
    )

    # 5. Persist in database
    try:
        import json
        save_literature_clustering_db({
            "cluster_run_id": run_id,
            "review_id": review_id,
            "project_id": project_id,
            "algorithm": "TFIDF_KMEANS",
            "num_clusters": len(clusters),
            "clusters_json": json.dumps([c.to_dict() for c in clusters]),
            "summary": summary,
            "created_at": result.created_at,
        }, db_path=db_path)

        save_citation_graph_db({
            "graph_id": f"graph-{uuid.uuid4().hex[:10]}",
            "review_id": review_id,
            "project_id": project_id,
            "nodes_json": json.dumps([n.to_dict() for n in nodes]),
            "edges_json": json.dumps([e.to_dict() for e in edges]),
            "bridge_papers_json": json.dumps(bridge_papers),
            "structural_holes_json": json.dumps([h.to_dict() for h in structural_holes]),
            "metrics_json": json.dumps({
                "density": density,
                "connected_components": components,
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }),
            "created_at": result.created_at,
        }, db_path=db_path)
        logger.info(f"Persisted clustering run {run_id} and citation graph for review {review_id}")
    except Exception as e:
        logger.error(f"Failed to persist clustering and citation graph: {e}")

    return result


def generate_citation_network_mermaid(
    graph: LiteratureCitationGraph,
    max_nodes: int = 25
) -> str:
    """
    Renders an accessible Mermaid graph visualization highlighting clusters,
    bridge nodes, and directed citation dependencies.
    """
    if not graph.nodes:
        return "graph TD\n    empty[\"No literature records available in graph\"]"

    lines = [
        "graph TD",
        "    classDef bridge fill:#4338ca,stroke:#818cf8,stroke-width:3px,color:#ffffff;",
        "    classDef included fill:#065f46,stroke:#34d399,stroke-width:2px,color:#ffffff;",
        "    classDef candidate fill:#1e293b,stroke:#94a3b8,stroke-width:1px,color:#f8fafc;",
        "    classDef contradiction stroke:#ef4444,stroke-width:2px,stroke-dasharray: 5 5;",
    ]

    # Map node IDs to sanitized Mermaid keys
    key_map: Dict[str, str] = {}
    for idx, node in enumerate(graph.nodes[:max_nodes]):
        key_map[node.id] = f"N{idx + 1}"

    # Group by cluster subgraphs
    cluster_subgraphs: Dict[str, List[CitationNode]] = {}
    for node in graph.nodes[:max_nodes]:
        cid = node.cluster_id or "cluster-0"
        if cid not in cluster_subgraphs:
            cluster_subgraphs[cid] = []
        cluster_subgraphs[cid].append(node)

    for cid, cnodes in cluster_subgraphs.items():
        cname = cnodes[0].cluster_name or cid
        safe_cname = re.sub(r'["\n\r]', '', cname)[:35]
        lines.append(f"    subgraph {cid} [\"{safe_cname}\"]")
        for node in cnodes:
            nid = key_map[node.id]
            clean_title = re.sub(r'["\n\r]', '', node.title)[:30] + "..."
            node_label = f"{clean_title}<br/>(Citations: {node.citation_count})"
            lines.append(f"        {nid}[\"{node_label}\"]")
        lines.append("    end")

    # Add edges
    displayed_ids = set(key_map.keys())
    for edge in graph.edges:
        if edge.source in displayed_ids and edge.target in displayed_ids:
            s_key = key_map[edge.source]
            t_key = key_map[edge.target]
            if edge.relation == "contradicts":
                lines.append(f"    {s_key} -.->|contradicts| {t_key}")
            elif edge.relation == "semantic_link":
                lines.append(f"    {s_key} -.-|semantic| {t_key}")
            else:
                lines.append(f"    {s_key} -->|cites| {t_key}")

    # Apply classes
    for node in graph.nodes[:max_nodes]:
        nid = key_map[node.id]
        if node.is_bridge:
            lines.append(f"    class {nid} bridge;")
        elif node.prisma_disposition == "INCLUDED":
            lines.append(f"    class {nid} included;")
        else:
            lines.append(f"    class {nid} candidate;")

    return "\n".join(lines)
