import time
import asyncio
import logging
import re
import datetime
from typing import Dict, Any, Generator, Optional, List, Tuple
from backend.dispatcher import Dispatcher
from backend.tools import scrape_url
from backend.memory.vault import write_note, read_note, DEFAULT_VAULT_DIR
from backend.memory.db import DEFAULT_DB_PATH
from backend.memory.index import index_note
from backend.pipeline import (
    search_node,
    snowball_node,
    writer_node,
    verifier_node,
    critic_node,
    mindmap_node,
    follow_up_node,
    _extract_domain,
    _extract_urls_from_text
)
from backend.telemetry import observe

logger = logging.getLogger("ThothOrchestrator")


class ResearchFSMState:
    """Explicit Finite State Machine States for Autonomous Research Orchestrator."""
    PLAN = "PLAN"
    SEARCH = "SEARCH"
    SNOWBALL = "SNOWBALL"
    SCRAPE = "SCRAPE"
    DRAFT = "DRAFT"
    TRUTH_GUARD = "TRUTH_GUARD"
    CRITIC = "CRITIC"
    REPLAN = "REPLAN"
    MINDMAP = "MINDMAP"
    VAULT = "VAULT"
    FOLLOW_UP = "FOLLOW_UP"
    COMPLETE = "COMPLETE"


# Default pipeline dispatcher for concurrency capping and resilience
pipeline_dispatcher = Dispatcher(
    max_concurrent=3,
    max_attempts=3,
    base_delay=1.0,
    max_consecutive_failures=5,
    cooloff_seconds=30.0
)



def create_initial_state(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
    initial_turns: Optional[List[Dict[str, Any]]] = None,
    initial_summary: str = "",
) -> Dict[str, Any]:
    """Creates a fresh plain Python dictionary ResearchState, inheriting conversational context if present."""
    return {
        "topic": topic,
        "role": role,
        "tone": tone,
        "language": language,
        "scrape_top_n": scrape_top_n,
        "min_score": min_score,
        "max_retries": max_retries,
        "attempt": 0,
        "search_results": "",
        "scraped_content": "",
        "report": "",
        "feedback": "",
        "verifier_feedback": "",
        "score": 0.0,
        "follow_up_questions": [],
        "mindmap": {"nodes": [], "edges": []},
        "cumulative_sources": [],
        "conversation_summary": str(initial_summary or ""),
        "chat_turns": list(initial_turns or []),
        "rejected_claims": [],
        "circular_replan_warnings": []
    }


@observe(type="tool", description="Concurrently scrapes and extracts readable text from candidate URLs")
async def concurrent_scrape_urls(urls: List[str], dispatcher: Dispatcher = pipeline_dispatcher) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fans out scraping calls for all target URLs concurrently using asyncio.gather.
    Each individual scrape call passes through the Dispatcher for rate limiting and resilience.
    """
    scraped_content = ""
    new_sources = []

    async def fetch_single_url(url: str):
        domain = _extract_domain(url)
        source_info = {
            "url": url,
            "domain": domain,
            "title": f"Source from {domain}",
            "added_in_turn": 0
        }
        try:
            # Route scrape request through central Dispatcher
            res = await dispatcher.call(scrape_url.invoke, {"url": url})
            return source_info, f"\n\n--- Source: {url} ---\n{res[:3000]}"
        except Exception as e:
            return source_info, f"\n\n--- Source: {url} ---\n(Failed to scrape: {e})"

    logger.info(f"[ORCHESTRATOR CONCURRENCY] Fanning out concurrent scrape requests for {len(urls)} URLs...")
    print(f"\n[INFO] [ORCHESTRATOR] Fanning out concurrent scrape requests for {len(urls)} URLs...")

    results = await asyncio.gather(*[fetch_single_url(u) for u in urls])

    for s_info, text_content in results:
        new_sources.append(s_info)
        scraped_content += text_content

    return scraped_content, new_sources


async def concurrent_verifier_and_critic(state: Dict[str, Any], dispatcher: Dispatcher = pipeline_dispatcher) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Executes verifier_node and critic_node concurrently against the draft report using asyncio.gather.
    Both nodes perform independent reads of the same draft data.
    Gracefully handles CircuitBreakerOpenError or provider errors by returning partial fallback updates.
    """
    logger.info("[ORCHESTRATOR CONCURRENCY] Running Verifier and Critic concurrently in parallel...")
    print("\n[INFO] [ORCHESTRATOR] Running Verifier and Critic concurrently in parallel...")

    results = await asyncio.gather(
        dispatcher.call(verifier_node, state),
        dispatcher.call(critic_node, state),
        return_exceptions=True
    )

    verifier_res, critic_res = results

    if isinstance(verifier_res, Exception):
        logger.error(f"[ORCHESTRATOR CONCURRENCY] Verifier execution error / circuit trip: {verifier_res}")
        verifier_update = {"verifier_feedback": "", "verification_results": [], "verification_status": f"UNAVAILABLE ({verifier_res})"}
    else:
        verifier_update = verifier_res

    if isinstance(critic_res, Exception):
        logger.error(f"[ORCHESTRATOR CONCURRENCY] Critic execution error / circuit trip: {critic_res}")
        critic_update = {"score": 7.0, "feedback": f"Quality evaluation unavailable: {critic_res}"}
    else:
        critic_update = critic_res

    return verifier_update, critic_update


@observe(type="agent", available_tools=["search_scholarly_sources", "scrape_url", "writer_node", "verifier_node", "critic_node", "mindmap_node", "follow_up_node"])
def stream_research_pipeline(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
    initial_turns: Optional[List[Dict[str, Any]]] = None,
    initial_summary: str = "",
    cancel_event=None,
    dispatcher: Dispatcher = pipeline_dispatcher
) -> Generator[tuple[str, Dict[str, Any], Dict[str, Any]], None, None]:
    """
    Executes the multi-agent research workflow as an explicit Plan -> Act -> Observe -> Replan loop.
    Optimized with asyncio.gather concurrent scraping fan-out and parallel verifier/critic evaluation.
    Inherits conversational history and established facts when transitioning from chat.
    Yields (node_name, update, current_state) events.
    """
    state = create_initial_state(
        topic=topic,
        role=role,
        tone=tone,
        language=language,
        scrape_top_n=scrape_top_n,
        min_score=min_score,
        max_retries=max_retries,
        initial_turns=initial_turns,
        initial_summary=initial_summary
    )

    act_phase_start = time.time()

    # =========================================================================
    # 1. PLAN Phase: Initial Research Discovery Vector (Search -> Concurrent Scrape)
    # =========================================================================
    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before search.")
        return

    # ACT 1: Execute Web & Scholarly Search Node
    logger.info(f"[ORCHESTRATOR - PLAN] Initiating search for topic: '{topic}'")
    search_update = search_node(state)
    state.update(search_update)
    yield "search", search_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before snowball.")
        return

    # ACT 1.5: Execute Snowballing Node (Citation Graph & Neural Recommendations)
    logger.info(f"[ORCHESTRATOR - SNOWBALL] Expanding citation graph and recommendations for '{topic}'...")
    snowball_update = snowball_node(state)
    state.update(snowball_update)
    yield "snowball", snowball_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before scrape.")
        return

    # ACT 2: Execute Reader Concurrent Scrape Fan-Out Node

    existing_sources = state.get("cumulative_sources", [])
    candidate_urls = [s.get("url") for s in existing_sources if s.get("url")][:state["scrape_top_n"]]
    if not candidate_urls:
        candidate_urls = _extract_urls_from_text(state.get("search_results", ""))[:state["scrape_top_n"]]

    if candidate_urls:
        scraped_content, new_sources = asyncio.run(concurrent_scrape_urls(candidate_urls, dispatcher))
        cumulative_sources = list(existing_sources)
        for s_info in new_sources:
            if not any(s.get("url") == s_info["url"] for s in cumulative_sources):
                cumulative_sources.append(s_info)

        scrape_update = {
            "scraped_content": scraped_content,
            "cumulative_sources": cumulative_sources
        }
    else:
        scrape_update = {
            "scraped_content": "(No URLs found to scrape)",
            "cumulative_sources": list(existing_sources)
        }

    state.update(scrape_update)
    yield "scrape", scrape_update, dict(state)

    # =========================================================================
    # 2. REPLAN Loop: Synthesis, Parallel Verifier/Critic Evaluation & Replan
    # =========================================================================
    while True:
        if cancel_event and cancel_event.is_set():
            logger.info("[ORCHESTRATOR] Cancel event detected inside revision loop.")
            return

        # ACT 3: Execute Writer Node
        attempt = state.get("attempt", 0) + 1
        logger.info(f"[ORCHESTRATOR - ACT] Writer drafting report (attempt {attempt})...")
        writer_update = writer_node(state)
        state.update(writer_update)

        # On replan attempts, detect if the regenerated draft reintroduces previously rejected unverified claims
        if attempt > 1 and state.get("rejected_claims"):
            from backend.eval.logical_integrity import detect_circular_replan
            draft_text = state.get("report", "")
            # Split draft into sentences/bullet claims
            draft_claims = [s.strip() for s in re.split(r"[\n\.\?!]", draft_text) if len(s.strip()) > 15]
            circular_findings = detect_circular_replan(state["rejected_claims"], draft_claims)
            if circular_findings:
                state.setdefault("circular_replan_warnings", []).extend(circular_findings)
                logger.warning(
                    f"[ORCHESTRATOR - CIRCULAR REPLAN] Regenerated draft reintroduces {len(circular_findings)} "
                    f"previously rejected unverified claims without new evidence."
                )

        yield "writer", writer_update, dict(state)

        if cancel_event and cancel_event.is_set():
            logger.info("[ORCHESTRATOR] Cancel event detected before verifier/critic.")
            return

        # ACT 4 & 5: Execute Verifier Node and Critic Node CONCURRENTLY in Parallel
        logger.info("[ORCHESTRATOR - ACT] Launching Verifier and Critic concurrently...")
        verifier_update, critic_update = asyncio.run(concurrent_verifier_and_critic(state, dispatcher))

        # Yield Verifier Node Update
        state.update(verifier_update)
        yield "verifier", verifier_update, dict(state)

        # Yield Critic Node Update
        state.update(critic_update)
        yield "critic", critic_update, dict(state)

        # Log wall-clock timing for the Act phase
        act_phase_end = time.time()
        act_duration = round(act_phase_end - act_phase_start, 2)
        logger.info(f"[ACT PHASE TIMING] Act phase (concurrent fan-out scrape + parallel verifier/critic) completed in {act_duration}s.")
        print(f"\n[TIMING] [ACT PHASE] Completed in {act_duration}s (Concurrent fan-out active).")

        # OBSERVE 1: Evaluate Verifier Audit Results & Collect Rejected Claims
        verifier_feedback = state.get("verifier_feedback", "")
        if verifier_feedback:
            # Extract failed claim lines from verifier feedback to prevent circular reintroduction
            for line in verifier_feedback.split("\n"):
                clean_line = line.strip().lstrip("-*• ")
                if clean_line and len(clean_line) > 10 and not clean_line.startswith("Verification"):
                    if clean_line not in state.get("rejected_claims", []):
                        state.setdefault("rejected_claims", []).append(clean_line)

            if state["attempt"] <= state["max_retries"]:
                logger.warning(f"[ORCHESTRATOR - REPLAN] Truth Guard flagged factual contradictions. Looping back to Writer (attempt {state['attempt']}/{state['max_retries']}).")
                print(f"\n[REPLAN] Truth Guard flagged contradictions. Routing back to Writer to revise...")
                continue
            else:
                logger.warning(f"[ORCHESTRATOR - REPLAN] Truth Guard flagged contradictions but max retries ({state['max_retries']}) hit. Proceeding to finalization.")

        # OBSERVE 2: Evaluate Overall Quality Score against min_score threshold
        score = state.get("score", 0.0)
        min_score = state.get("min_score", 6.5)
        attempt = state.get("attempt", 0)
        max_retries = state.get("max_retries", 2)

        if score < min_score and attempt <= max_retries:
            logger.warning(f"[ORCHESTRATOR - REPLAN] Critic score {score:.1f} < threshold {min_score} (attempt {attempt}/{max_retries}). Looping back to Writer.")
            print(f"\n[REPLAN] Score {score:.1f} < threshold {min_score}. Routing back to Writer for revision...")
            continue
        else:
            logger.info(f"[ORCHESTRATOR - OBSERVE] Quality check passed with score {score:.1f}/10. Finalizing report.")
            break

    # =========================================================================
    # 3. Post-Verification: Markdown Vault Persistence & Immediate Indexing
    # =========================================================================
    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before vault persistence.")
        return

    logger.info("[ORCHESTRATOR - POST-VERIFICATION] Extracting atomic claims and persisting notes to Vault & Index...")
    vault_update = persist_turn_to_vault(state)
    state.update(vault_update)
    yield "vault", vault_update, dict(state)

    # =========================================================================
    # 4. ACT Phase: Final Knowledge Graph & Dynamic Follow-up Assembly
    # =========================================================================
    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before mindmap.")
        return

    # ACT 6: Execute Mind Map Construction Node
    logger.info("[ORCHESTRATOR - ACT] Constructing concept Mind Map...")
    mindmap_update = mindmap_node(state)
    state.update(mindmap_update)
    yield "mindmap", mindmap_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before follow-up questions.")
        return

    # ACT 7: Execute Follow-up Questions Generator Node
    logger.info("[ORCHESTRATOR - ACT] Generating proactive follow-up questions...")
    followup_update = follow_up_node(state)
    state.update(followup_update)
    yield "follow_up", followup_update, dict(state)


def _slugify(text: str, max_len: int = 40) -> str:
    """Creates a clean filename/identifier slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_len] if cleaned else "note"


def extract_atomic_claims(
    draft: str,
    source_ids: List[str],
    verification_results: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    """
    Extracts atomic claims from the verified results / draft and links each claim
    to its verified supporting_source_id.

    Rule: If a claim has no supporting_source_id (or was flagged invalid / unverified),
    it is omitted entirely — treating missing attribution the same as an uncited claim
    under the write-boundary rule. NO index-based round-robin fallback is used.
    """
    formatted_claims: List[str] = []
    if not source_ids:
        return formatted_claims

    valid_source_set = set(source_ids)
    
    # Build normalized lookup map for source IDs
    src_lookup: Dict[str, str] = {}
    for sid in source_ids:
        src_lookup[sid.lower()] = sid
        src_lookup[sid.lower().replace("_", "-")] = sid
        src_lookup[sid.lower().replace("-", "_")] = sid
        if sid.lower().startswith("src-"):
            src_lookup[sid[4:].lower()] = sid
            src_lookup[sid[4:].lower().replace("_", "-")] = sid

    if verification_results:
        for item in verification_results:
            if isinstance(item, dict):
                claim = item.get("claim", "").strip()
                is_valid = item.get("is_valid", False)
                raw_src_id = item.get("supporting_source_id", "")
            else:
                claim = getattr(item, "claim", "").strip()
                is_valid = getattr(item, "is_valid", False)
                raw_src_id = getattr(item, "supporting_source_id", "")

            if not is_valid or not claim:
                continue

            if not raw_src_id:
                # Missing attribution -> do not write to vault
                logger.warning(f"[VAULT CLAIM] Dropping claim with missing supporting_source_id: '{claim[:50]}'")
                continue

            # Clean raw source id
            cleaned_src = re.sub(r"[\[\]]", "", str(raw_src_id)).strip()
            c_low = cleaned_src.lower()
            resolved_src = (
                src_lookup.get(c_low)
                or src_lookup.get(c_low.replace("-", "_"))
                or src_lookup.get(c_low.replace("_", "-"))
                or (cleaned_src if cleaned_src in valid_source_set else None)
            )

            # If not found directly, check partial slug match against known source_ids
            if not resolved_src:
                c_norm = c_low.replace("-", "_")
                for sid in source_ids:
                    sid_norm = sid.lower().replace("-", "_")
                    if c_norm in sid_norm or sid_norm in c_norm:
                        resolved_src = sid
                        break

            if resolved_src and resolved_src in valid_source_set:
                formatted_claims.append(f"- {claim} [[{resolved_src}]]")
            else:
                logger.warning(f"[VAULT CLAIM] Dropping claim because source '{raw_src_id}' is not in known sources: '{claim[:50]}'")

    return formatted_claims


def persist_turn_to_vault(
    state: Dict[str, Any],
    vault_dir: str = DEFAULT_VAULT_DIR,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Persists finalized research results to the markdown vault and updates the SQLite index:
    1. Creates/writes source notes in vault/sources/ for all retrieved sources.
    2. Immediately indexes source notes into FTS5 + embeddings.
    3. Extracts atomic claims from the verified draft and writes topic note in vault/topics/.
    4. Immediately indexes the topic note into FTS5 + embeddings + knowledge graph edges.
    """
    topic = state.get("topic", "Research Topic")
    draft = state.get("report") or state.get("draft", "")
    sources = state.get("cumulative_sources", [])
    confidence = float(state.get("score", 8.0)) / 10.0
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    source_ids = []

    # 1. Write and index source notes
    for idx, s in enumerate(sources, 1):
        s_title = s.get("title") or s.get("url") or f"source_{idx}"
        s_slug = _slugify(s_title, 35)
        src_id = f"src-{s_slug}"
        if src_id in source_ids:
            src_id = f"{src_id}_{idx}"
        source_ids.append(src_id)

        source_body = f"""# Source: {s.get('title', 'Retrieved Source')}

- **URL**: {s.get('url', 'N/A')}
- **Domain**: {s.get('domain', 'N/A')}
- **Source API**: {s.get('source_api', 'web')}
- **DOI**: {s.get('doi', 'N/A')}
- **ArXiv ID**: {s.get('arxiv_id', 'N/A')}
- **Citation Count**: {s.get('citation_count', 0)}

## Content / Abstract
{s.get('snippet', '') or s.get('abstract', '(No abstract provided)')}
"""
        src_fm = {
            "type": "sources",
            "created": now_iso,
            "confidence": 1.0,
            "sources": []
        }
        try:
            write_note(note_id=src_id, note_type="sources", content=source_body, frontmatter=src_fm, vault_dir=vault_dir)
            note_obj = read_note(src_id, vault_dir=vault_dir)
            index_note(note_obj, db_path=db_path)
            logger.info(f"[VAULT] Written and indexed source note: {src_id}")
        except Exception as e:
            logger.error(f"[VAULT] Failed to write/index source note {src_id}: {e}")

    # 2. Extract atomic claims from draft and write topic note
    topic_slug = _slugify(topic, 40)
    topic_note_id = f"topic-{topic_slug}"
    verification_results = state.get("verification_results", [])
    claims_list = extract_atomic_claims(draft, source_ids, verification_results=verification_results)

    if claims_list:
        claims_text = "\n".join(claims_list)
        topic_body = f"""# Topic: {topic}

## Claims
{claims_text}

## Synthesis Report
{draft}
"""
    else:
        topic_body = f"""# Topic: {topic}

## Synthesis Report
{draft}
"""
    topic_fm = {
        "type": "topics",
        "created": now_iso,
        "confidence": round(confidence, 2),
        "sources": source_ids
    }

    try:
        write_note(note_id=topic_note_id, note_type="topics", content=topic_body, frontmatter=topic_fm, vault_dir=vault_dir)
        topic_obj = read_note(topic_note_id, vault_dir=vault_dir)
        index_note(topic_obj, db_path=db_path)
        logger.info(f"[VAULT] Written and indexed topic note: {topic_note_id}")
    except Exception as e:
        logger.error(f"[VAULT] Failed to write/index topic note {topic_note_id}: {e}")

    vault_notes = [topic_note_id] + source_ids
    return {
        "vault_notes": vault_notes,
        "primary_topic_note": topic_note_id,
        "source_notes": source_ids
    }


@observe(type="agent", available_tools=["search_scholarly_sources", "scrape_url", "writer_node", "verifier_node", "critic_node", "mindmap_node", "follow_up_node"])
def run_research_pipeline(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
    cancel_event=None,
    dispatcher: Dispatcher = pipeline_dispatcher
) -> Dict[str, Any]:
    """Executes the research pipeline synchronously and returns final state."""
    final_state = {}
    for node_name, update, current_state in stream_research_pipeline(
        topic=topic,
        role=role,
        tone=tone,
        language=language,
        scrape_top_n=scrape_top_n,
        min_score=min_score,
        max_retries=max_retries,
        cancel_event=cancel_event,
        dispatcher=dispatcher
    ):
        final_state = current_state
    return final_state
