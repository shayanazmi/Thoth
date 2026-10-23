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
    prisma_node,
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
    PLAN = "PLAN"
    SEARCH = "SEARCH"
    SNOWBALL = "SNOWBALL"
    SCRAPE = "SCRAPE"
    PRISMA = "PRISMA"
    DRAFT = "DRAFT"
    TRUTH_GUARD = "TRUTH_GUARD"
    CRITIC = "CRITIC"
    REPLAN = "REPLAN"
    MINDMAP = "MINDMAP"
    VAULT = "VAULT"
    FOLLOW_UP = "FOLLOW_UP"
    COMPLETE = "COMPLETE"

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
    scrape_top_n: int = 15,
    min_score: float = 6.5,
    max_retries: int = 2,
    initial_turns: Optional[List[Dict[str, Any]]] = None,
    initial_summary: str = "",
    brief: Any = None,
    project_id: Optional[str] = None,
    db_path: Optional[str] = None,
    vault_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if hasattr(brief, "to_dict"):
        brief_data = brief.to_dict()
    elif isinstance(brief, dict):
        brief_data = dict(brief)
    else:
        brief_data = {}
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
        "circular_replan_warnings": [],
        "integrity_status": "PENDING",
        "integrity_result": {},
        "is_verified": False,
        "brief": brief_data,
        "thinker_context": brief_data.get("thinker_context") or {},
        "hypotheses": brief_data.get("hypotheses") or [],
        "selection_criteria": brief_data.get("selection_criteria") or [],
        "unresolved_questions": brief_data.get("unresolved_questions") or [],
        "counter_evidence_queries": brief_data.get("counter_evidence_queries") or [],
        "falsification_criteria": brief_data.get("falsification_criteria") or [],
        "project_id": project_id or brief_data.get("project_id"),
        "db_path": db_path,
        "vault_dir": vault_dir,
        "session_id": session_id or brief_data.get("session_id") or "",
    }

@observe(type="tool", description="Concurrently scrapes and extracts readable text from candidate URLs")
async def concurrent_scrape_urls(urls: List[str], dispatcher: Dispatcher = pipeline_dispatcher) -> Tuple[str, List[Dict[str, Any]]]:
    scraped_content = ""
    new_sources = []

    async def fetch_single_url(url: str):
        domain = _extract_domain(url)
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        source_info = {
            "url": url,
            "domain": domain,
            "title": f"Source from {domain}",
            "added_in_turn": 0,
            "extracted_text": "",
            "scrape_status": "pending",
            "scrape_error": None,
            "content_type": "unknown",
            "extraction_quality": "unknown",
            "extraction_method": "unknown",
            "extraction_warnings": [],
            "retrieval_timestamp": now_ts,
            "char_count": 0,
            "num_pages": 0,
            "is_truncated": False,
            "passages": []
        }
        try:
            res = await dispatcher.call(scrape_url.invoke, {"url": url})
            if hasattr(res, "extraction_quality"):
                source_info["content_type"] = res.content_type
                source_info["scrape_status"] = res.status
                source_info["scrape_error"] = res.error_message
                source_info["extraction_quality"] = res.extraction_quality
                source_info["extraction_method"] = res.extraction_method
                source_info["extraction_warnings"] = list(res.extraction_warnings)
                source_info["retrieval_timestamp"] = res.retrieval_timestamp or now_ts
                source_info["char_count"] = res.char_count
                source_info["num_pages"] = res.num_pages
                source_info["is_truncated"] = res.is_truncated
                source_info["passages"] = res.passages
                source_info["extracted_text"] = res.text
                if res.status == "success":
                    trunc_note = f" ({res.content_type.upper()}{' [Partial Extraction - Truncated]' if res.is_truncated else ''})" if res.content_type else ""
                    text_content = f"\n\n--- Source: {url} ---{trunc_note}\n{res.text}"
                elif res.status == "empty":
                    text_content = f"\n\n--- Source: {url} ---\n(Empty content extracted)"
                elif res.status == "unsupported":
                    text_content = f"\n\n--- Source: {url} ---\n(Unsupported content format: {res.error_message})"
                else:
                    text_content = f"\n\n--- Source: {url} ---\n(Failed to scrape: {res.error_message})"
                return source_info, text_content

            res_str = str(res or "")
            if res_str.startswith("Could not scrape URL:") or res_str.startswith("(Failed to scrape:"):
                source_info["extracted_text"] = ""
                source_info["scrape_status"] = "failed"
                source_info["scrape_error"] = res_str
                source_info["extraction_quality"] = "inaccessible"
                source_info["extraction_warnings"] = [res_str]
                text_content = f"\n\n--- Source: {url} ---\n(Failed to scrape: {res_str})"
            elif not res_str.strip():
                source_info["extracted_text"] = ""
                source_info["scrape_status"] = "empty"
                source_info["scrape_error"] = "Empty content extracted"
                source_info["extraction_quality"] = "empty"
                source_info["extraction_warnings"] = ["Empty content extracted"]
                text_content = f"\n\n--- Source: {url} ---\n(Empty content)"
            else:
                raw_len = len(res_str)
                is_truncated = raw_len > 12000
                if is_truncated:
                    extracted = res_str[:12000].rsplit(" ", 1)[0] + "... [Text truncated at character budget]"
                    extraction_quality = "partial"
                    warnings_list = ["Document text truncated at character budget"]
                else:
                    extracted = res_str
                    extraction_quality = "full"
                    warnings_list = []

                content_type = "pdf" if ("[Page " in extracted or url.lower().endswith(".pdf") or "/pdf/" in url.lower()) else "html"
                num_pages = len(re.findall(r"\[Page\s+(\d+)\]", extracted)) if content_type == "pdf" else (1 if extracted else 0)

                source_info["extracted_text"] = extracted
                source_info["scrape_status"] = "success"
                source_info["scrape_error"] = None
                source_info["content_type"] = content_type
                source_info["extraction_quality"] = extraction_quality
                source_info["extraction_method"] = "pypdf" if content_type == "pdf" else "beautifulsoup"
                source_info["extraction_warnings"] = warnings_list
                source_info["char_count"] = len(extracted)
                source_info["num_pages"] = num_pages
                source_info["is_truncated"] = is_truncated

                from backend.ingestion import create_bounded_passages
                source_info["passages"] = create_bounded_passages(
                    extracted,
                    content_type=content_type,
                    source_uri=url
                )
                trunc_note = f" ({content_type.upper()}{' [Partial Extraction - Truncated]' if is_truncated else ''})" if content_type else ""
                text_content = f"\n\n--- Source: {url} ---{trunc_note}\n{extracted}"
            return source_info, text_content
        except Exception as e:
            source_info["extracted_text"] = ""
            source_info["scrape_status"] = "failed"
            source_info["scrape_error"] = str(e)
            source_info["extraction_quality"] = "inaccessible"
            source_info["extraction_warnings"] = [str(e)]
            return source_info, f"\n\n--- Source: {url} ---\n(Failed to scrape: {e})"

    logger.info(f"[ORCHESTRATOR CONCURRENCY] Fanning out concurrent scrape requests for {len(urls)} URLs...")
    print(f"\n[INFO] [ORCHESTRATOR] Fanning out concurrent scrape requests for {len(urls)} URLs...")

    results = await asyncio.gather(*[fetch_single_url(u) for u in urls])

    for s_info, text_content in results:
        new_sources.append(s_info)
        scraped_content += text_content

    return scraped_content, new_sources

async def concurrent_verifier_and_critic(state: Dict[str, Any], dispatcher: Dispatcher = pipeline_dispatcher) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
        verifier_update = {
            "verifier_feedback": f"Verifier unavailable: {verifier_res}",
            "verification_results": [],
            "verification_status": f"UNAVAILABLE ({verifier_res})",
            "integrity_status": "INCOMPLETE",
            "is_verified": False,
            "integrity_result": {
                "status": "INCOMPLETE",
                "failure_explanations": [f"Verifier execution error: {verifier_res}"],
                "is_verified": False
            }
        }
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
    scrape_top_n: int = 15,
    min_score: float = 6.5,
    max_retries: int = 2,
    initial_turns: Optional[List[Dict[str, Any]]] = None,
    initial_summary: str = "",
    cancel_event=None,
    dispatcher: Dispatcher = pipeline_dispatcher,
    brief: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None,
    db_path: Optional[str] = None,
    vault_dir: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Generator[tuple[str, Dict[str, Any], Dict[str, Any]], None, None]:
    state = create_initial_state(
        topic=topic,
        role=role,
        tone=tone,
        language=language,
        scrape_top_n=scrape_top_n,
        min_score=min_score,
        max_retries=max_retries,
        initial_turns=initial_turns,
        initial_summary=initial_summary,
        brief=brief,
        project_id=project_id,
        db_path=db_path,
        vault_dir=vault_dir,
        session_id=session_id,
    )

    act_phase_start = time.time()

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before search.")
        state["cancelled"] = True
        yield "cancelled", {"cancelled": True, "reason": "Task cancelled."}, dict(state)
        return

    logger.info(f"[ORCHESTRATOR - PLAN] Initiating search for topic: '{topic}'")
    search_update = search_node(state)
    state.update(search_update)
    yield "search", search_update, dict(state)

    # Phase 3 (vision §5.4): lightweight scan unless the approved brief asks
    # for a formal PRISMA-aligned review.
    if (state.get("brief") or {}).get("review_mode", "scan") != "formal":
        yield from _run_scan_phase(state)
    else:
        if cancel_event and cancel_event.is_set():
            logger.info("[ORCHESTRATOR] Cancel event detected before snowball.")
            state["cancelled"] = True
            yield "cancelled", {"cancelled": True, "reason": "Task cancelled."}, dict(state)
            return

        logger.info(f"[ORCHESTRATOR - SNOWBALL] Expanding citation graph and recommendations for '{topic}'...")
        snowball_update = snowball_node(state)
        state.update(snowball_update)
        yield "snowball", snowball_update, dict(state)

        if cancel_event and cancel_event.is_set():
            logger.info("[ORCHESTRATOR] Cancel event detected before scrape.")
            state["cancelled"] = True
            yield "cancelled", {"cancelled": True, "reason": "Task cancelled."}, dict(state)
            return

        existing_sources = state.get("cumulative_sources", [])
        candidate_urls = [s.get("url") for s in existing_sources if s.get("url")][:state["scrape_top_n"]]
        if not candidate_urls:
            candidate_urls = _extract_urls_from_text(state.get("search_results", ""))[:state["scrape_top_n"]]

        if candidate_urls:
            scraped_content, new_sources = asyncio.run(concurrent_scrape_urls(candidate_urls, dispatcher))
            new_sources_by_url = {s.get("url"): s for s in new_sources if s.get("url")}

            cumulative_sources = []
            for s in existing_sources:
                s_copy = dict(s)
                u = s_copy.get("url")
                if u in new_sources_by_url:
                    scraped_meta = new_sources_by_url[u]
                    s_copy["extracted_text"] = scraped_meta.get("extracted_text", "")
                    s_copy["scrape_status"] = scraped_meta.get("scrape_status", "success")
                    s_copy["scrape_error"] = scraped_meta.get("scrape_error")
                    s_copy["content_type"] = scraped_meta.get("content_type", s_copy.get("content_type", "unknown"))
                    s_copy["extraction_quality"] = scraped_meta.get("extraction_quality", s_copy.get("extraction_quality", "unknown"))
                    s_copy["extraction_method"] = scraped_meta.get("extraction_method", s_copy.get("extraction_method", "unknown"))
                    s_copy["extraction_warnings"] = list(scraped_meta.get("extraction_warnings") or s_copy.get("extraction_warnings") or [])
                    s_copy["retrieval_timestamp"] = scraped_meta.get("retrieval_timestamp") or s_copy.get("retrieval_timestamp")
                    s_copy["char_count"] = scraped_meta.get("char_count", 0)
                    s_copy["num_pages"] = scraped_meta.get("num_pages", 0)
                    s_copy["is_truncated"] = scraped_meta.get("is_truncated", False)
                    s_copy["passages"] = list(scraped_meta.get("passages") or [])

                    # If scrape failed but source has an abstract or snippet, honestly mark as snippet_only rather than full failure
                    if s_copy["scrape_status"] != "success":
                        has_snippet = bool((s_copy.get("abstract") or s_copy.get("snippet") or "").strip())
                        if has_snippet and s_copy["extraction_quality"] == "inaccessible":
                            s_copy["extraction_quality"] = "snippet_only"
                cumulative_sources.append(s_copy)

            existing_urls = {s.get("url") for s in cumulative_sources if s.get("url")}
            for s_info in new_sources:
                if s_info.get("url") and s_info["url"] not in existing_urls:
                    cumulative_sources.append(s_info)
                    existing_urls.add(s_info["url"])

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

        # --- PRISMA 2020 Systematic Review & Evidence Synthesis Ledger ---
        logger.info("[ORCHESTRATOR - ACT] Executing PRISMA 2020 Review Accounting and Screening...")
        prisma_update = dict(prisma_node(state))
        state.update(prisma_update)
        yield "prisma", prisma_update, dict(state)

    while True:
        if cancel_event and cancel_event.is_set():
            logger.info("[ORCHESTRATOR] Cancel event detected inside revision loop.")
            return

        attempt = state.get("attempt", 0) + 1
        logger.info(f"[ORCHESTRATOR - ACT] Writer drafting report (attempt {attempt})...")
        writer_update = dict(writer_node(state))
        writer_update["attempt"] = attempt
        state.update(writer_update)
        state["attempt"] = attempt

        if attempt > 1 and state.get("rejected_claims"):
            from backend.eval.logical_integrity import detect_circular_replan
            draft_text = state.get("report", "")

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

        logger.info("[ORCHESTRATOR - ACT] Launching Verifier and Critic concurrently...")
        verifier_update, critic_update = asyncio.run(concurrent_verifier_and_critic(state, dispatcher))

        state.update(verifier_update)
        yield "verifier", verifier_update, dict(state)

        state.update(critic_update)
        yield "critic", critic_update, dict(state)

        act_phase_end = time.time()
        act_duration = round(act_phase_end - act_phase_start, 2)
        logger.info(f"[ACT PHASE TIMING] Act phase (concurrent fan-out scrape + parallel verifier/critic) completed in {act_duration}s.")
        print(f"\n[TIMING] [ACT PHASE] Completed in {act_duration}s (Concurrent fan-out active).")

        raw_integrity = state.get("integrity_status")
        if raw_integrity and raw_integrity not in ("PENDING", "UNKNOWN"):
            integrity_status = raw_integrity
        else:
            integrity_status = "FAILED" if state.get("verifier_feedback") else "PASSED"
        verifier_feedback = state.get("verifier_feedback", "")

        # 1. Fail-closed Research Integrity Gate
        if integrity_status != "PASSED" or verifier_feedback:
            for line in verifier_feedback.split("\n"):
                clean_line = line.strip().lstrip("-*• ")
                if clean_line and len(clean_line) > 10 and not clean_line.startswith("Verification"):
                    if clean_line not in state.get("rejected_claims", []):
                        state.setdefault("rejected_claims", []).append(clean_line)

            if state["attempt"] <= state["max_retries"]:
                logger.warning(f"[ORCHESTRATOR - REPLAN] Research Integrity Gate: {integrity_status}. Routing back to Writer to revise (attempt {state['attempt']}/{state['max_retries']}).")
                print(f"\n[REPLAN] Research Integrity Gate ({integrity_status}). Routing back to Writer to revise...")
                continue
            else:
                # Max retries exhausted: FAIL CLOSED!
                state["integrity_status"] = f"INTEGRITY_{integrity_status}" if not str(integrity_status).startswith("INTEGRITY_") else integrity_status
                state["is_verified"] = False
                logger.warning(
                    f"[ORCHESTRATOR - INTEGRITY GATE] Max retries reached with unresolved integrity failures ({integrity_status}). "
                    f"Report finalized as UNVERIFIED ({state['integrity_status']}). Critic score has NO authority to override."
                )
                print(f"\n[GATE CLOSED] Finalizing report as {state['integrity_status']} (unverified).")
                break

        # 2. Quality check evaluated only if integrity passed
        state["integrity_status"] = "PASSED"
        state["is_verified"] = True

        score = state.get("score", 0.0)
        min_score = state.get("min_score", 6.5)
        attempt = state.get("attempt", 0)
        max_retries = state.get("max_retries", 2)

        if score < min_score and attempt <= max_retries:
            logger.warning(f"[ORCHESTRATOR - REPLAN] Critic score {score:.1f} < threshold {min_score} (attempt {attempt}/{max_retries}). Looping back to Writer.")
            print(f"\n[REPLAN] Score {score:.1f} < threshold {min_score}. Routing back to Writer for revision...")
            continue
        else:
            logger.info(f"[ORCHESTRATOR - OBSERVE] Quality check passed with score {score:.1f}/10. Integrity: PASSED. Finalizing report.")
            break

    # Compile deterministic bibliography from verified sources
    from backend.intellectual_rigour.integrity_gate import generate_deterministic_bibliography
    final_report, deduped_sources, unresolved_citations = generate_deterministic_bibliography(
        report_text=state.get("report", ""),
        cumulative_sources=state.get("cumulative_sources", [])
    )
    state["report"] = final_report
    if unresolved_citations:
        state.setdefault("unresolved_citations", []).extend(unresolved_citations)
        if state.get("is_verified", False):
            state["is_verified"] = False
            state["integrity_status"] = "INTEGRITY_FAILED"

    if not state.get("is_verified", False):
        status_label = state.get("integrity_status", "UNVERIFIED")
        integrity_banner = (
            f"> [!CAUTION] Research Integrity Gate: {status_label}\n"
            f"> **UNVERIFIED REPORT**: This research synthesis did not pass empirical claim-to-evidence verification "
            f"or contains uncorroborated / contradicted claims. It must not be cited as established evidence.\n\n"
        )
        if not state.get("report", "").startswith("> [!CAUTION]"):
            state["report"] = integrity_banner + state.get("report", "")

    if (state.get("brief") or {}).get("review_mode", "scan") != "formal":
        state["report"] = _honest_scan_methodology(state.get("report", ""), state)

    # Phases 4/5/6 (vision §6.3, §8, §4): thinker perspective, originality, honest status.
    for node_name, node_update in _run_rigour_passes(state):
        yield node_name, node_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before vault persistence.")
        return

    logger.info("[ORCHESTRATOR - POST-VERIFICATION] Extracting atomic claims and persisting notes to Vault & Index...")
    vault_update = persist_turn_to_vault(
        state,
        vault_dir=state.get("vault_dir") or DEFAULT_VAULT_DIR,
        db_path=state.get("db_path") or DEFAULT_DB_PATH
    )
    state.update(vault_update)
    yield "vault", vault_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before mindmap.")
        return

    logger.info("[ORCHESTRATOR - ACT] Constructing concept Mind Map...")
    mindmap_update = mindmap_node(state)
    state.update(mindmap_update)
    yield "mindmap", mindmap_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before follow-up questions.")
        return

    logger.info("[ORCHESTRATOR - ACT] Generating proactive follow-up questions...")
    followup_update = follow_up_node(state)
    state.update(followup_update)
    yield "follow_up", followup_update, dict(state)

    if cancel_event and cancel_event.is_set():
        logger.info("[ORCHESTRATOR] Cancel event detected before manuscript synthesis.")
        return

    logger.info("[ORCHESTRATOR - ACT] Connecting project workspace & instantiating structured manuscript...")
    db_path = state.get("db_path") or DEFAULT_DB_PATH
    brief_data = state.get("brief") or {}
    brief_id = brief_data.get("brief_id")
    prisma_data = state.get("prisma_review") or {}
    review_id = prisma_data.get("review_id") or state.get("review_id")
    session_id = brief_data.get("session_id") or state.get("session_id") or ""
    project_id = state.get("project_id") or brief_data.get("project_id")

    from backend.workspace.project import create_project, get_project, associate_artifact, list_projects
    from backend.workspace.manuscript import create_manuscript_from_brief_and_review, create_manuscript

    project = None
    if project_id:
        try:
            project = get_project(project_id, db_path=db_path)
        except Exception:
            project = None
    if not project and session_id:
        try:
            existing_projects = list_projects(session_id=session_id, db_path=db_path)
            if existing_projects:
                project = existing_projects[0]
                project_id = project.project_id
        except Exception:
            pass
    if not project:
        proj_title = f"Project: {topic[:60]}" if topic else "THOTH Research Project"
        try:
            project = create_project(
                title=proj_title,
                description=f"Auto-instantiated project workspace for research topic '{topic}'",
                session_id=session_id,
                db_path=db_path
            )
            project_id = project.project_id
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not create project: {e}")
            project_id = f"proj_fallback_{int(time.time())}"

    state["project_id"] = project_id

    if brief_id and project_id:
        try:
            associate_artifact(project_id, "brief", brief_id, db_path=db_path)
        except Exception as e:
            logger.debug(f"[ORCHESTRATOR] Could not associate brief {brief_id}: {e}")

    if review_id and project_id:
        try:
            associate_artifact(project_id, "prisma_review", review_id, db_path=db_path)
        except Exception as e:
            logger.debug(f"[ORCHESTRATOR] Could not associate review {review_id}: {e}")

    primary_note = state.get("primary_topic_note")
    if primary_note and project_id:
        try:
            associate_artifact(project_id, "report", primary_note, db_path=db_path)
        except Exception as e:
            logger.debug(f"[ORCHESTRATOR] Could not associate report note {primary_note}: {e}")

    ms_obj = None
    rev_obj = None
    if brief_id and review_id and project_id:
        try:
            ms_obj, rev_obj = create_manuscript_from_brief_and_review(
                project_id=project_id,
                brief_id=brief_id,
                review_id=review_id,
                title=f"Systematic Review & Synthesis: {topic}",
                db_path=db_path
            )
            logger.info(f"[ORCHESTRATOR] Created structured manuscript '{ms_obj.manuscript_id}' (v{rev_obj.version}) with {len(rev_obj.claims)} claims.")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] create_manuscript_from_brief_and_review failed: {e}")

    if not ms_obj and project_id:
        try:
            report_text = state.get("report") or state.get("draft", "")
            ms_obj, rev_obj = create_manuscript(
                project_id=project_id,
                title=f"Research Synthesis: {topic}",
                brief_id=brief_id,
                review_id=review_id,
                initial_sections={
                    "abstract": {
                        "heading": "Abstract",
                        "content": f"Synthesized research report on '{topic}'.",
                        "order": 1,
                        "section_type": "standard",
                    },
                    "synthesis": {
                        "heading": "Synthesis Findings",
                        "content": report_text,
                        "order": 2,
                        "section_type": "standard",
                    }
                },
                db_path=db_path
            )
        except Exception as e:
            logger.debug(f"[ORCHESTRATOR] Fallback manuscript creation failed: {e}")

    manuscript_update = {
        "manuscript": ms_obj.to_dict() if ms_obj else {},
        "revision": rev_obj.to_dict() if rev_obj else {},
        "manuscript_id": ms_obj.manuscript_id if ms_obj else "",
        "project_id": project_id,
    }
    state.update(manuscript_update)
    yield "manuscript", manuscript_update, dict(state)

def _slugify(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_len] if cleaned else "note"

def extract_atomic_claims(
    draft: str,
    source_ids: List[str],
    verification_results: Optional[List[Dict[str, Any]]] = None
) -> List[str]:
    formatted_claims: List[str] = []
    if not source_ids:
        return formatted_claims

    valid_source_set = set(source_ids)

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
                logger.warning(f"[VAULT CLAIM] Dropping claim with missing supporting_source_id: '{claim[:50]}'")
                continue

            cleaned_src = re.sub(r"[\[\]]", "", str(raw_src_id)).strip()
            c_low = cleaned_src.lower()
            resolved_src = (
                src_lookup.get(c_low)
                or src_lookup.get(c_low.replace("-", "_"))
                or src_lookup.get(c_low.replace("_", "-"))
                or (cleaned_src if cleaned_src in valid_source_set else None)
            )

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
    topic = state.get("topic", "Research Topic")
    draft = state.get("report") or state.get("draft", "")
    sources = state.get("cumulative_sources", [])
    is_verified = bool(state.get("is_verified", False) and state.get("integrity_status") == "PASSED")
    integrity_status = state.get("integrity_status", "UNKNOWN")
    confidence = (float(state.get("score", 8.0)) / 10.0) if is_verified else 0.0
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    source_ids = []

    for idx, s in enumerate(sources, 1):
        s_title = s.get("title") or s.get("url") or f"source_{idx}"
        s_slug = _slugify(s_title, 35)
        src_id = f"src-{s_slug}"
        if src_id in source_ids:
            src_id = f"{src_id}_{idx}"
        source_ids.append(src_id)

        authors_str = ', '.join(s.get('authors', [])) if s.get('authors') else 'N/A'
        pub_date = s.get('published_date') or 'N/A'
        pmid_val = s.get('pmid') or 'N/A'
        content_val = s.get('abstract', '') or s.get('snippet', '') or (s.get('extracted_text', '')[:1000] if s.get('extracted_text') else '(No abstract provided)')

        source_body = f"""# Source: {s.get('title', 'Retrieved Source')}

- **URL**: {s.get('url', 'N/A')}
- **Domain**: {s.get('domain', 'N/A')}
- **Authors**: {authors_str}
- **Published Date**: {pub_date}
- **Source API**: {s.get('source_api', 'web')}
- **DOI**: {s.get('doi', 'N/A')}
- **ArXiv ID**: {s.get('arxiv_id', 'N/A')}
- **PMID**: {pmid_val}
- **Citation Count**: {s.get('citation_count', 0)}

## Content / Abstract
{content_val}
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

    topic_slug = _slugify(topic, 40)
    topic_note_id = f"topic-{topic_slug}"
    verification_results = state.get("verification_results", [])
    claims_list = extract_atomic_claims(draft, source_ids, verification_results=verification_results)

    integrity_banner = ""
    if not is_verified:
        integrity_banner = f"> [!WARNING] Research Integrity Gate: {integrity_status}\n> This report is a draft and did not pass empirical claim-to-evidence verification.\n\n"

    if claims_list:
        claims_text = "\n".join(claims_list)
        topic_body = f"""# Topic: {topic}
{integrity_banner}
## Claims
{claims_text}

## Synthesis Report
{draft}
"""
    else:
        topic_body = f"""# Topic: {topic}
{integrity_banner}
## Synthesis Report
{draft}
"""
    topic_fm = {
        "type": "topics",
        "created": now_iso,
        "confidence": round(confidence, 2),
        "verified": is_verified,
        "integrity_status": integrity_status,
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
    scrape_top_n: int = 15,
    min_score: float = 6.5,
    max_retries: int = 2,
    cancel_event=None,
    dispatcher: Dispatcher = pipeline_dispatcher
) -> Dict[str, Any]:
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


def _run_scan_phase(state: Dict[str, Any]):
    """Lightweight, abstract-level scan (vision §5.4). No snowball, no scraping, no PRISMA ledger."""
    from backend.intellectual_rigour.lightweight_scan import (
        MAX_SCAN_PAPERS,
        formal_review_recommendation,
        run_lightweight_scan,
    )

    sources = [dict(s) for s in state.get("cumulative_sources", [])][:MAX_SCAN_PAPERS]
    for s in sources:
        if s.get("extraction_quality") in (None, "", "unknown", "full"):
            s["extraction_quality"] = "snippet_only"  # never upgrade: only abstracts were seen
    state["cumulative_sources"] = sources
    state["scraped_content"] = "\n\n".join(
        f"[{n}] {s.get('title', '')}\n{s.get('abstract') or s.get('snippet') or ''}"
        for n, s in enumerate(sources, 1)
    ) or "(No abstracts available)"
    # Depth when it matters: one revision at most for an exploratory scan.
    state["max_retries"] = min(state.get("max_retries", 2), 1)

    brief = state.get("brief") or {}
    scan = run_lightweight_scan(sources, brief)
    state["scan_result"] = scan
    yield "scan_result", scan, dict(state)
    if scan["recommend_formal_review"]:
        yield "recommend_formal_review", formal_review_recommendation(scan, brief), dict(state)


def _honest_scan_methodology(report: str, state: Dict[str, Any]) -> str:
    """Vision §11: never fabricate methods. The writer LLM tends to invent
    inclusion criteria; for a lightweight scan we state exactly what happened."""
    scan = state.get("scan_result") or {}
    apis = sorted({p.get("source_api") for p in scan.get("papers", []) if p.get("source_api")})
    honest = (
        "Lightweight literature scan (not a systematic review). One keyword search of "
        f"{', '.join(apis) or 'the configured scholarly databases'} returned {scan.get('paper_count', 0)} papers "
        f"(capped at {scan.get('cap', 20)}). Only titles and abstracts were read; no full texts were retrieved, "
        "no citation snowballing was done, and no inclusion/exclusion screening was applied. Claims in this "
        "report are therefore abstract-level and were checked by the Truth Guard against those abstracts only."
    )
    heading = re.compile(r"^\s*(#{1,4}\s*)?(\*\*)?\s*(\d+\.\s*)?Methodology\b.*$", re.I)
    next_heading = re.compile(r"^\s*(#{1,4}\s+\S|\*\*[^*]{2,80}\*\*\s*$|(Conclusion|Bibliography|References|Limitations)\b)", re.I)
    lines = report.split("\n")
    for i, line in enumerate(lines):
        if heading.match(line):
            j = i + 1
            while j < len(lines) and not next_heading.match(lines[j]):
                j += 1
            return "\n".join(lines[:i] + ["**Methodology**", honest, ""] + lines[j:])
    return report.rstrip() + f"\n\n**Methodology**\n{honest}\n"


def _run_rigour_passes(state: Dict[str, Any]):
    brief = state.get("brief") or {}
    topic = state.get("topic", "")

    # The report the user reads is the final one (bibliography, integrity banner,
    # honest scan methodology), never an intermediate writer draft.
    yield "final_report", {"report": state.get("report", "")}

    try:
        from backend.intellectual_rigour.thinker_hook import invoke_thinker_when_useful
        thinker = invoke_thinker_when_useful("critical_review", topic, state.get("report", ""), brief)
    except Exception as exc:
        thinker = {"stage": "critical_review", "invoked": False, "reason": f"Thinker unavailable: {exc}"}
    state["thinker_perspective"] = thinker
    yield "thinker_perspective", thinker

    try:
        import backend.scholarly as sch
        from backend.intellectual_rigour.originality import assess_originality, generate_adjacent_queries

        hypothesis = (brief.get("hypotheses") or [brief.get("research_question") or topic])[0]
        queries = generate_adjacent_queries(topic, hypothesis)
        adjacent: List[Dict[str, Any]] = []
        for q in queries:
            try:
                found = asyncio.run(sch.search_scholarly_sources(q, max_results=5, min_scholarly_results=1))
                adjacent.extend(c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in (found or []))
            except Exception as exc:
                logger.warning(f"[ORIGINALITY] adjacent search failed for {q!r}: {exc}")
        originality = assess_originality(hypothesis, state.get("cumulative_sources", []), adjacent, queries)
    except Exception as exc:
        originality = {"verdict": "insufficiently_assessed", "explanation": f"Originality check failed: {exc}"}
    state["originality_assessment"] = originality
    yield "originality_assessment", originality

    from backend.reports.status import compute_report_status
    status = compute_report_status(state)
    state["report_status"] = status
    yield "report_status", status
