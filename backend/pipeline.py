import re
import time
import datetime
import json
import urllib.parse
import asyncio
from typing import TypedDict, List, Dict, Any, Optional
from backend.tools import web_search, scrape_url
from backend.scholarly import search_scholarly_sources, SourceCandidate
from backend.agents import (
    build_search_agent, 
    build_verifier_agent,
    verifier_chain,
    FactVerificationReport,
    writer_chain, 
    critic_chain,
    CriticScore,
    follow_up_chain,
    mindmap_extractor_chain,
    router_chain,
    mindmap_qa_chain,
    mindmap_updater_chain,
    conversation_summarizer_chain,
    report_expander_chain,
    strip_chain_of_thought,
    safe_extract_json
)
import tiktoken
import logging
from backend.memory.vault import write_note, read_note, DEFAULT_VAULT_DIR
from backend.memory.db import DEFAULT_DB_PATH
from backend.memory.index import index_note, hybrid_search
from backend.memory.session import SessionMemory, DEFAULT_TOKEN_BUDGET

logger = logging.getLogger("ThothPipeline")
DEFAULT_MAX_CONTEXT_TOKENS = 6000

def _slugify(text: str, max_len: int = 40) -> str:
    """Creates a clean filename/identifier slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", text.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:max_len] if cleaned else "note"

def count_tokens(text: str, model_encoding: str = "cl100k_base") -> int:
    """Counts token count of a given string using tiktoken."""
    if not text:
        return 0
    try:
        encoding = tiktoken.get_encoding(model_encoding)
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4

def truncate_text_to_tokens(text: str, max_tokens: int, model_encoding: str = "cl100k_base") -> str:
    """Truncates text so its token count does not exceed max_tokens."""
    if not text or max_tokens <= 0:
        return ""
    try:
        encoding = tiktoken.get_encoding(model_encoding)
        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        logger.warning(f"[TOKEN BUDGET] Truncating context text from {len(tokens)} tokens to {max_tokens} token ceiling.")
        print(f"\n[WARNING] [TOKEN BUDGET] Truncating context text from {len(tokens)} tokens to {max_tokens} token ceiling.")
        return encoding.decode(tokens[:max_tokens])
    except Exception:
        char_limit = max_tokens * 4
        if len(text) > char_limit:
            logger.warning(f"[TOKEN BUDGET] Truncating text from {len(text)} chars to {char_limit} chars.")
            print(f"\n[WARNING] [TOKEN BUDGET] Truncating text from {len(text)} chars to {char_limit} chars.")
            return text[:char_limit]
        return text

def fit_context_to_token_budget(
    topic: str,
    context_block: str,
    summary: str,
    chat_turns: List[Dict[str, Any]],
    user_query: str,
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
) -> tuple:
    """
    Assembles context, summary, and recent raw chat turns fitting within max_tokens ceiling.
    Drops oldest chat turns first when exceeding budget.
    Returns: (trimmed_context_block, trimmed_summary, kept_recent_turns_text)
    """
    fixed_text = f"Topic: {topic}\nUser Query: {user_query}"
    fixed_tokens = count_tokens(fixed_text)
    
    remaining_budget = max_tokens - fixed_tokens
    if remaining_budget <= 200:
        logger.warning(f"[TOKEN BUDGET] Fixed prompt components near max_tokens ceiling ({fixed_tokens}/{max_tokens}).")
        print(f"\n[WARNING] [TOKEN BUDGET] Fixed prompt components near max_tokens ceiling ({fixed_tokens}/{max_tokens}).")
        return truncate_text_to_tokens(context_block, 200), truncate_text_to_tokens(summary, 100), ""
        
    context_budget = int(remaining_budget * 0.55)
    summary_budget = int(remaining_budget * 0.20)
    
    trimmed_context = truncate_text_to_tokens(context_block, context_budget) if count_tokens(context_block) > context_budget else context_block
    trimmed_summary = truncate_text_to_tokens(summary, summary_budget) if count_tokens(summary) > summary_budget else summary
    
    used_so_far = fixed_tokens + count_tokens(trimmed_context) + count_tokens(trimmed_summary)
    turns_budget = max_tokens - used_so_far
    
    kept_turns = []
    current_turns_tokens = 0
    
    for turn in reversed(chat_turns):
        turn_str = f"User: {turn.get('user_query', '')}\nAssistant: {turn.get('assistant_response', '')}\n"
        t_tokens = count_tokens(turn_str)
        if current_turns_tokens + t_tokens <= turns_budget:
            kept_turns.insert(0, turn_str)
            current_turns_tokens += t_tokens
        else:
            logger.warning(f"[TOKEN BUDGET] Dropped older raw chat turn #{turn.get('turn')} to fit within {max_tokens} token budget.")
            print(f"\n[WARNING] [TOKEN BUDGET] Dropped older raw chat turn #{turn.get('turn')} to fit within {max_tokens} token budget.")
            
    recent_turns_text = "\n".join(kept_turns)
    return trimmed_context, trimmed_summary, recent_turns_text

# 1. State Definition
class ResearchMindMap(TypedDict):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class ResearchState(TypedDict):
    topic: str
    role: str
    tone: str
    language: str
    scrape_top_n: int
    min_score: float
    max_retries: int
    attempt: int
    
    # Core research data
    search_results: str
    scraped_content: str
    report: str
    feedback: str
    verifier_feedback: str
    score: float
    follow_up_questions: List[str]
    
    # Conversational & Mind Map Persistent Memory
    mindmap: ResearchMindMap
    cumulative_sources: List[Dict[str, Any]]
    conversation_summary: str
    chat_turns: List[Dict[str, Any]]


def _extract_domain(url: str) -> str:
    """Extract clean domain name from URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return url

def _extract_urls_from_text(text: str) -> List[str]:
    """Extract all URLs from a text blob."""
    url_pattern = r'https?://[^\s)\]"\'>]+'
    found = re.findall(url_pattern, text)
    # Deduplicate while preserving order
    seen = set()
    cleaned = []
    for u in found:
        # Strip trailing punctuation
        u_clean = u.rstrip(".,;:")
        if u_clean not in seen:
            seen.add(u_clean)
            cleaned.append(u_clean)
    return cleaned

# 2. Node Implementations for Initial Research Graph
def search_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 1 - Search Agent is querying scholarly databases & web...")
    print("=" * 50)
    
    topic = state.get("topic", "")
    target_count = max(int(state.get("scrape_top_n", 5) or 5), 5)
    candidates: List[SourceCandidate] = []
    
    try:
        def _run_async_search():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(asyncio.run, search_scholarly_sources(topic, max_results=target_count, min_scholarly_results=min(target_count, 4))).result()
            else:
                return asyncio.run(search_scholarly_sources(topic, max_results=target_count, min_scholarly_results=min(target_count, 4)))

        candidates = _run_async_search()
    except Exception as e:
        logger.warning(f"[SEARCH NODE] Error in scholarly search: {e}. Falling back to web search agent.")
        print(f"\n[WARNING] [SEARCH NODE] Scholarly search encountered error: {e}. Using web search fallback...")

    if candidates:
        results = "\n\n------\n\n".join(c.to_formatted_snippet() for c in candidates)
        cumulative_sources = []
        for c in candidates:
            if c.url:
                domain = _extract_domain(c.url)
                cumulative_sources.append({
                    "url": c.url,
                    "domain": domain,
                    "title": c.title,
                    "doi": c.doi,
                    "arxiv_id": c.arxiv_id,
                    "source_api": c.source_api,
                    "citation_count": c.citation_count,
                    "added_in_turn": 0
                })
        
        print("\nSearch Results (Scholarly + Web Fallback):\n", results[:300] + "..." if len(results) > 300 else results)
        print(f"Extracted {len(cumulative_sources)} structured sources from scholarly search step.")
        return {
            "search_results": results,
            "cumulative_sources": cumulative_sources
        }

    # Fallback to web search agent if no candidates returned
    logger.info("[SEARCH NODE] Falling back to standard web search agent...")
    search_agent = build_search_agent()
    search_result = search_agent.invoke({
        "messages": [("user", f"Find recent, reliable and detailed information about: {topic}. Always cite source URLs.")]
    })
    
    results = search_result["messages"][-1].content
    
    # Extract URLs from tool messages and final content
    extracted_urls = []
    for msg in search_result.get("messages", []):
        if msg.type == "tool" or hasattr(msg, "content"):
            extracted_urls.extend(_extract_urls_from_text(str(msg.content)))
    extracted_urls = list(dict.fromkeys(extracted_urls))
    
    cumulative_sources = []
    for u in extracted_urls:
        domain = _extract_domain(u)
        cumulative_sources.append({
            "url": u,
            "domain": domain,
            "title": f"Registry source from {domain}",
            "added_in_turn": 0
        })
        
    print("\nSearch Results (Web Fallback):\n", results[:300] + "..." if len(results) > 300 else results)
    print(f"Extracted {len(cumulative_sources)} source URLs from web search fallback.")
    
    return {
        "search_results": results,
        "cumulative_sources": cumulative_sources
    }

def scrape_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print(f"Step 2 - Reader Agent is scraping top {state['scrape_top_n']} resources...")
    print("=" * 50)
    
    # Gather candidate URLs
    existing_sources = state.get("cumulative_sources", [])
    urls = [s.get("url") for s in existing_sources if s.get("url")][:state["scrape_top_n"]]
    
    if not urls:
        urls = _extract_urls_from_text(state.get("search_results", ""))[:state["scrape_top_n"]]
        
    scraped_content = ""
    cumulative_sources = list(existing_sources)
    
    for url in urls:
        print(f"\nScraping: {url}")
        domain = _extract_domain(url)
        if not any(s.get("url") == url for s in cumulative_sources):
            cumulative_sources.append({
                "url": url,
                "domain": domain,
                "title": f"Source from {domain}",
                "added_in_turn": 0
            })
        try:
            # Fast direct tool execution
            scrape_res = scrape_url.invoke({"url": url})
            scraped_content += f"\n\n--- Source: {url} ---\n{scrape_res[:3000]}"
        except Exception as e:
            scraped_content += f"\n\n--- Source: {url} ---\n(Failed to scrape: {e})"
        
    print("\nScraped Content length:", len(scraped_content))
    return {
        "scraped_content": scraped_content,
        "cumulative_sources": cumulative_sources
    }

def writer_node(state: ResearchState) -> dict:
    attempt = state.get("attempt", 0) + 1
    print("\n" + "= " * 50)
    print(f"Step 3 - Writer is drafting/revising the report (attempt {attempt})...")
    print("=" * 50)
    
    # Query Vault memory for 4-8 relevant notes via Hybrid Search if store exists
    vault_notes_text = ""
    try:
        from backend.memory.index import hybrid_search
        hits = hybrid_search(state["topic"], top_k=4)
        if hits:
            vault_notes_text = "\n\n".join([
                f"--- Vault Note [{n.get('note_id')}]:\n{n.get('content', '')[:800]}"
                for n in hits
            ])
    except Exception as e:
        logger.debug(f"[WRITER] Vault memory lookup skipped/empty: {e}")

    # Build SessionMemory context if conversational turns exist
    from backend.memory.session import SessionMemory, DEFAULT_TOKEN_BUDGET
    session_mem = SessionMemory(
        initial_summary=state.get("conversation_summary", ""),
        initial_turns=state.get("chat_turns", [])
    )
    raw_research = (
        f"SEARCH RESULTS:\n{state.get('search_results', '')}\n\n"
        f"DETAILED SCRAPED CONTENT:\n{state.get('scraped_content', '')}"
    )
    if vault_notes_text:
        raw_research += f"\n\nPRIOR VAULT KNOWLEDGE:\n{vault_notes_text}"

    session_ctx = session_mem.get_context(
        token_budget=DEFAULT_TOKEN_BUDGET,
        retrieved_notes_text=raw_research
    )
    
    research_combined = session_ctx["retrieved_notes"]
    if session_ctx["summary"]:
        research_combined += f"\n\nPRIOR RESEARCH SUMMARY:\n{session_ctx['summary']}"
    if session_ctx["recent_turns"]:
        research_combined += f"\n\nRECENT CONVERSATION TURNS:\n{session_ctx['recent_turns']}"
    
    prior_feedback = ""
    if state.get("verifier_feedback"):
        prior_feedback += f"\nFact Verifier Feedback:\n{state['verifier_feedback']}\n"
    if state.get("feedback"):
        prior_feedback += f"\nCritic Quality Feedback:\n{state['feedback']}\n"
        
    if prior_feedback:
        research_combined += f"\n\nFEEDBACK TO ADDRESS IN THIS REVISION:\n{prior_feedback}"
        
    raw_report = writer_chain.invoke({
        "topic": state["topic"],
        "role": state.get("role", "senior academic researcher"),
        "tone": state.get("tone", "formal and analytical"),
        "language": state.get("language", "English"),
        "research": research_combined,
        "current_date": datetime.datetime.now().strftime("%B %d, %Y")
    })
    report = strip_chain_of_thought(raw_report)
    
    print("\nDrafted Synthesis Report Preview:\n", report[:400] + "...")
    return {"report": report, "attempt": attempt, "verifier_feedback": "", "feedback": ""}

def verifier_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 4 - SLM Truth Guard is verifying factual integrity...")
    print("=" * 50)
    
    # Build structured source material with explicit [src-...] identifiers
    sources_blocks = []
    for idx, s in enumerate(state.get("cumulative_sources", []), 1):
        s_title = s.get("title") or s.get("url") or f"source_{idx}"
        s_slug = _slugify(s_title, 35)
        src_id = f"src-{s_slug}"
        content_snippet = s.get("snippet") or s.get("abstract") or ""
        sources_blocks.append(
            f"[{src_id}] Title: {s.get('title', 'N/A')}\nURL: {s.get('url', 'N/A')}\nContent:\n{content_snippet[:1500]}"
        )
    
    if sources_blocks:
        sources_material = "\n\n---\n\n".join(sources_blocks)
    else:
        sources_material = (
            f"SEARCH RESULTS:\n{state.get('search_results', '')[:2500]}\n\n"
            f"SCRAPED CONTENT:\n{state.get('scraped_content', '')[:2500]}"
        )
    
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    raw_response = verifier_chain.invoke({
        "sources": sources_material,
        "report": state.get("report", "")[:3500],
        "current_date": current_date
    })
    
    parsed = safe_extract_json(raw_response, default=None)
    
    has_issues = False
    feedback_lines = []
    verification_results = []
    
    if parsed and isinstance(parsed, dict) and "results" in parsed:
        try:
            report_obj = FactVerificationReport(**parsed)
            for res in report_obj.results:
                verification_results.append(res.dict())
                if not res.is_valid:
                    has_issues = True
                    feedback_lines.append(f"- CLAIM: '{res.claim}' -> {res.reason_if_failed}")
        except Exception:
            for res in parsed.get("results", []):
                if isinstance(res, dict):
                    verification_results.append(res)
                    if not res.get("is_valid", True):
                        has_issues = True
                        reason = res.get("reason_if_failed", "Contradiction or unsupported claim.")
                        feedback_lines.append(f"- CLAIM: '{res.get('claim')}' -> {reason}")
    elif isinstance(raw_response, str) and ("contradict" in raw_response.lower() or "unsupported" in raw_response.lower() or "false" in raw_response.lower()):
        has_issues = True
        feedback_lines.append(raw_response)
        
    verifier_log = raw_response if isinstance(raw_response, str) else json.dumps(parsed, indent=2)
    feedback = "\n".join(feedback_lines) if has_issues else ""
    
    print("\nSLM Truth Guard Log:\n", verifier_log)
    print(f"\nVerification Status: {'FLAGGED FOR REVISION' if has_issues else 'PASSED'}")
    
    return {"verifier_feedback": feedback, "verification_results": verification_results}

def critic_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 5 - LLM Critic is evaluating quality and depth...")
    print("=" * 50)
    
    raw_result = critic_chain.invoke({
        "topic": state["topic"],
        "report": state["report"],
    })
    
    try:
        if isinstance(raw_result, dict):
            critic_score = CriticScore(**raw_result)
        elif isinstance(raw_result, CriticScore):
            critic_score = raw_result
        else:
            raise ValueError(f"Unexpected critic_chain output type: {type(raw_result)}")
    except Exception as e:
        raise ValueError(f"Failed to parse structured CriticScore from LLM output: {e}\nRaw output: {raw_result}") from e
        
    score = float(critic_score.overall_score)
    
    # Format human-readable markdown for UI log and state feedback
    feedback = (
        f"**Scores**\n"
        f"| Dimension | Score /10 |\n"
        f"|---|---|\n"
        f"| Faithfulness | {critic_score.faithfulness} |\n"
        f"| Relevance | {critic_score.relevance} |\n"
        f"| Completeness | {critic_score.completeness} |\n"
        f"| Evidence Quality | {critic_score.evidence_quality} |\n"
        f"| Clarity & Coherence | {critic_score.clarity_and_coherence} |\n"
        f"| **Overall** | **{critic_score.overall_score:.1f}** |\n\n"
        f"**Strengths**\n" + "\n".join([f"- {s}" for s in critic_score.strengths]) + "\n\n"
        f"**Areas to Improve**\n" + "\n".join([f"- {a}" for a in critic_score.areas_to_improve]) + "\n\n"
        f"**Verdict**\n{critic_score.verdict}\n\n"
        f"**Reasoning**\n{critic_score.reasoning}"
    )
    
    print("\nCritic Feedback:\n", feedback)
    print(f"\nOverall Score: {score}/10")
    
    return {"feedback": feedback, "score": score}

def mindmap_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 6 - Constructing Concept Mind Map Knowledge Graph...")
    print("=" * 50)
    
    # Gather extracted URLs
    sources_text = "\n".join([s.get("url", "") for s in state.get("cumulative_sources", [])])
    if not sources_text:
        sources_text = "\n".join(_extract_urls_from_text(state.get("report", "")))
        
    raw_mindmap = mindmap_extractor_chain.invoke({
        "topic": state["topic"],
        "report": state["report"][:4000],  # Keep token efficient
        "sources": sources_text
    })
    
    mindmap = safe_extract_json(raw_mindmap, default=None)
    if not mindmap or not isinstance(mindmap, dict) or "nodes" not in mindmap:
        print("Mindmap fallback triggered due to JSON parse anomaly.")
        # Robust fallback graph structure
        mindmap = {
            "nodes": [
                {"id": "root", "label": state["topic"], "type": "topic", "details": f"Central topic: {state['topic']}", "group": "topic"},
                {"id": "sub_1", "label": "Key Findings", "type": "subtopic", "details": "Core discovered insights", "group": "subtopic"},
                {"id": "sub_2", "label": "Knowledge Gaps", "type": "subtopic", "details": "Open research vectors", "group": "subtopic"},
                {"id": "sub_3", "label": "Methodology", "type": "subtopic", "details": "Verification and synthesis", "group": "subtopic"}
            ],
            "edges": [
                {"from": "root", "to": "sub_1", "label": "findings"},
                {"from": "root", "to": "sub_2", "label": "gaps"},
                {"from": "root", "to": "sub_3", "label": "method"}
            ]
        }
        
    print(f"Mind Map constructed with {len(mindmap.get('nodes', []))} nodes and {len(mindmap.get('edges', []))} edges.")
    return {"mindmap": mindmap}

def follow_up_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 7 - Generating dynamic follow-up questions...")
    print("=" * 50)
    
    raw_response = follow_up_chain.invoke({
        "topic": state["topic"],
        "report": state["report"][:3000],
        "recent_context": "Initial research run completed."
    })
    
    questions = safe_extract_json(raw_response, default=[])
    if not questions or not isinstance(questions, list):
        questions = [
            f"What are the major open technical challenges in {state['topic']}?",
            f"What are the latest 2026 breakthroughs regarding {state['topic']}?",
            f"How can these findings be applied in real-world deployment?"
        ]
        
    print("\nSuggested Follow-up Questions:")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
        
    return {"follow_up_questions": questions}

# Wrapper functions re-exporting orchestrator execution for backward compatibility
def stream_research_pipeline(*args, **kwargs):
    from backend.orchestrator import stream_research_pipeline as _stream
    yield from _stream(*args, **kwargs)

def run_research_pipeline(*args, **kwargs):
    from backend.orchestrator import run_research_pipeline as _run
    return _run(*args, **kwargs)

def create_initial_state(*args, **kwargs):
    from backend.orchestrator import create_initial_state as _create
    return _create(*args, **kwargs)

# ==============================================================================
# 5. Long-Running Conversational Multi-Turn Follow-Up Engine
# ==============================================================================
def stream_followup_turn(
    current_state: Dict[str, Any],
    user_query: str,
    mode_override: str = "auto",
    cancel_event=None,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
):
    """
    Executes a single conversational follow-up turn incrementally.
    Maintains hierarchical Mind Map memory and token budget.
    """
    topic = current_state.get("topic", "Research Topic")
    mindmap = current_state.get("mindmap", {"nodes": [], "edges": []})
    report = current_state.get("report", "")
    cumulative_sources = list(current_state.get("cumulative_sources", []))
    chat_turns = list(current_state.get("chat_turns", []))
    conversation_summary = current_state.get("conversation_summary", "")
    
    # 1. Routing Phase
    route = "LOCAL_QA"
    reasoning = "Answerable directly from existing research context."
    search_query = ""
    
    if mode_override == "local_qa":
        route = "LOCAL_QA"
        reasoning = "Manual override: Fast Local Knowledge QA."
    elif mode_override == "web_probe":
        route = "WEB_SEARCH"
        reasoning = "Manual override: Targeted Live Web Probe."
        search_query = f"{topic} {user_query}"
    elif mode_override == "expand_report":
        route = "REPORT_EXPANSION"
        reasoning = "Manual override: Living Synthesis Report Expansion."
    else:
        # Autonomous Agentic Router
        mindmap_summary = f"{len(mindmap.get('nodes', []))} concepts mapped. Nodes: " + ", ".join(
            [n.get("label", "") for n in mindmap.get("nodes", [])[:8]]
        )
        report_summary = report[:1200]
        
        raw_route = router_chain.invoke({
            "topic": topic,
            "mindmap_summary": mindmap_summary,
            "report_summary": report_summary,
            "user_query": user_query
        })
        route_data = safe_extract_json(raw_route, default={})
        route = route_data.get("route", "LOCAL_QA")
        reasoning = route_data.get("reasoning", "Autonomous routing decision.")
        search_query = route_data.get("search_query", "")
        if route == "WEB_SEARCH" and not search_query:
            search_query = f"{topic} {user_query}"
            
    yield "router", {
        "route": route,
        "reasoning": reasoning,
        "search_query": search_query
    }
    
    if cancel_event and cancel_event.is_set():
        return

    answer_text = ""
    citations = []
    new_scraped_data = ""
    turn_index = len(chat_turns) + 1
    
    # 2. Execution Phase
    # Query Vault memory for 4-8 relevant notes via Hybrid Search
    vault_notes = []
    try:
        from backend.memory.index import hybrid_search
        vault_notes = hybrid_search(user_query, top_k=6)
    except Exception as e:
        logger.debug(f"[FOLLOWUP] Vault hybrid search error: {e}")

    vault_notes_text = "\n\n".join([
        f"--- Vault Note [{n.get('note_id')}]:\n{n.get('content', '')[:1000]}"
        for n in vault_notes
    ]) if vault_notes else ""

    from backend.memory.session import SessionMemory, DEFAULT_TOKEN_BUDGET
    session_memory = SessionMemory(
        initial_summary=conversation_summary,
        initial_turns=chat_turns
    )

    if route == "LOCAL_QA":
        # Grounded Q&A over Mind Map, Vault Notes, and Report with token budgeting
        context_nodes = [
            f"- [{n.get('type', 'node').upper()}] {n.get('label', '')}: {n.get('details', '')}"
            for n in mindmap.get("nodes", [])
        ]
        raw_context = (
            "MIND MAP KNOWLEDGE GRAPH:\n" + "\n".join(context_nodes) +
            "\n\nSYNTHESIS REPORT EXCERPT:\n" + report
        )
        if vault_notes_text:
            raw_context += f"\n\nRELEVANT VAULT KNOWLEDGE:\n{vault_notes_text}"

        session_ctx = session_memory.get_context(
            token_budget=DEFAULT_TOKEN_BUDGET,
            retrieved_notes_text=raw_context
        )
        
        history_context = session_ctx["summary"]
        if session_ctx["recent_turns"]:
            history_context += f"\n\nRecent Dialogue:\n{session_ctx['recent_turns']}"
            
        answer_text = strip_chain_of_thought(mindmap_qa_chain.invoke({
            "topic": topic,
            "context": session_ctx["retrieved_notes"],
            "history_summary": history_context or "No previous follow-up history.",
            "user_query": user_query
        }))
        citations = _extract_urls_from_text(answer_text)
        yield "answer", {
            "answer": answer_text,
            "route": "LOCAL_QA",
            "citations": citations
        }

    elif route == "WEB_SEARCH":
        # High-Speed Targeted Sub-Search via direct tool execution (1.2s)
        search_output = web_search.invoke({"query": search_query})
        yield "subsearch", {"query": search_query, "results": search_output}
        
        new_urls = _extract_urls_from_text(search_output)[:2]
        new_scraped_data = ""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_source_ids = []
        
        for idx, u in enumerate(new_urls, 1):
            domain = _extract_domain(u)
            s_slug = _slugify(domain or f"source_{turn_index}_{idx}", 30)
            src_id = f"src-{s_slug}_{turn_index}_{idx}"
            new_source_ids.append(src_id)

            if not any(s.get("url") == u for s in cumulative_sources):
                cumulative_sources.append({
                    "url": u,
                    "domain": domain,
                    "title": f"Follow-up probe: {search_query[:35]}",
                    "added_in_turn": turn_index
                })
            try:
                scrape_content = scrape_url.invoke({"url": u})
                new_scraped_data += f"\n\n--- Source: {u} ---\n{scrape_content[:2000]}"
            except Exception as e:
                scrape_content = f"(Scrape error: {e})"
                new_scraped_data += f"\n\n--- Source: {u} ---\n{scrape_content}"
                
            # Persist source note into Vault
            try:
                src_body = f"# Source: {u}\n\n- **URL**: {u}\n- **Domain**: {domain}\n- **Turn**: {turn_index}\n\n## Content\n{scrape_content[:2500]}"
                write_note(note_id=src_id, note_type="sources", content=src_body, frontmatter={"type": "sources", "created": now_iso, "confidence": 1.0, "sources": []})
                src_note_obj = read_note(src_id)
                index_note(src_note_obj)
            except Exception as e:
                logger.error(f"[FOLLOWUP VAULT] Failed to write source note {src_id}: {e}")
                
            yield "subscrape", {"scraped": new_scraped_data, "urls": new_urls}
        
        # Update Mind Map with newly discovered sub-branch
        existing_mm_json = json.dumps(mindmap)
        raw_updated_mm = mindmap_updater_chain.invoke({
            "existing_mindmap_json": existing_mm_json,
            "followup_query": user_query,
            "new_research": f"SEARCH:\n{search_output}\n\nSCRAPED:\n{new_scraped_data}"
        })
        updated_mindmap = safe_extract_json(raw_updated_mm, default=mindmap)
        if isinstance(updated_mindmap, dict) and "nodes" in updated_mindmap:
            mindmap = updated_mindmap
            yield "mindmap_update", {"mindmap": mindmap}
            
        # Formulate grounded answer with token budgeting
        raw_context = (
            f"NEW SEARCH RESULTS:\n{search_output}\n\n"
            f"NEW SCRAPED CONTENT:\n{new_scraped_data}\n\n"
            f"MIND MAP NODES:\n" + "\n".join([n.get('label', '') for n in mindmap.get('nodes', [])])
        )
        if vault_notes_text:
            raw_context += f"\n\nPRIOR VAULT KNOWLEDGE:\n{vault_notes_text}"

        session_ctx = session_memory.get_context(
            token_budget=DEFAULT_TOKEN_BUDGET,
            retrieved_notes_text=raw_context
        )
        history_context = session_ctx["summary"]
        if session_ctx["recent_turns"]:
            history_context += f"\n\nRecent Dialogue:\n{session_ctx['recent_turns']}"
            
        answer_text = strip_chain_of_thought(mindmap_qa_chain.invoke({
            "topic": topic,
            "context": session_ctx["retrieved_notes"],
            "history_summary": history_context or "None",
            "user_query": user_query
        }))
        citations = new_urls + _extract_urls_from_text(answer_text)

        # Persist finding topic note into Vault for future turns
        fu_topic_slug = _slugify(search_query or user_query, 35)
        finding_note_id = f"topic-fu-{fu_topic_slug}_{turn_index}"
        primary_src = new_source_ids[0] if new_source_ids else "src-web-search"
        finding_body = f"""# Follow-Up Finding: {user_query}

## Claims
- {answer_text[:180].replace(chr(10), ' ')} [[{primary_src}]]

## Analysis
{answer_text}
"""
        try:
            write_note(note_id=finding_note_id, note_type="topics", content=finding_body, frontmatter={"type": "topics", "created": now_iso, "confidence": 0.9, "sources": new_source_ids})
            fu_note_obj = read_note(finding_note_id)
            index_note(fu_note_obj)
            logger.info(f"[FOLLOWUP VAULT] Persisted finding note: {finding_note_id}")
        except Exception as e:
            logger.error(f"[FOLLOWUP VAULT] Failed to write finding note {finding_note_id}: {e}")

        yield "vault_update", {
            "vault_notes": [finding_note_id] + new_source_ids,
            "finding_note": finding_note_id
        }

        yield "answer", {
            "answer": answer_text,
            "route": "WEB_SEARCH",
            "citations": list(set(citations))
        }

    elif route == "REPORT_EXPANSION":
        # Draft a new section to expand the synthesis report with token budgeting
        trimmed_report = truncate_text_to_tokens(report, int(max_context_tokens * 0.4))
        raw_draft = report_expander_chain.invoke({
            "topic": topic,
            "user_query": user_query,
            "research_data": f"Prior Report & Scraped Context:\n{trimmed_report}",
            "report_overview": trimmed_report[:1000]
        })
        section_draft = strip_chain_of_thought(raw_draft)
        
        updated_report = report.strip() + "\n\n" + section_draft.strip()
        yield "report_expansion", {
            "new_section": section_draft,
            "updated_report": updated_report
        }
        
        # Update mindmap node for the new section
        new_node_id = f"section_{turn_index}"
        mindmap.get("nodes", []).append({
            "id": new_node_id,
            "label": f"Section: {user_query[:30]}...",
            "type": "subtopic",
            "details": section_draft[:150],
            "group": "subtopic"
        })
        mindmap.get("edges", []).append({
            "from": mindmap.get("nodes", [{}])[0].get("id", "root"),
            "to": new_node_id,
            "label": "expanded"
        })
        yield "mindmap_update", {"mindmap": mindmap}

        # Persist expanded section into Vault
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        section_slug = _slugify(user_query, 30)
        section_note_id = f"topic-section-{section_slug}_{turn_index}"
        sec_body = f"""# Section: {user_query}

## Claims
- {section_draft[:180].replace(chr(10), ' ')} [[topic-{_slugify(topic, 30)}]]

## Content
{section_draft}
"""
        try:
            write_note(note_id=section_note_id, note_type="topics", content=sec_body, frontmatter={"type": "topics", "created": now_iso, "confidence": 0.95, "sources": []})
            sec_obj = read_note(section_note_id)
            index_note(sec_obj)
        except Exception as e:
            logger.error(f"[EXPANSION VAULT] Failed to persist section note {section_note_id}: {e}")

        yield "vault_update", {
            "vault_notes": [section_note_id]
        }
        
        answer_text = f"**I have drafted a new section and merged it into your Synthesis Report:**\n\n{section_draft}"
        yield "answer", {
            "answer": answer_text,
            "route": "REPORT_EXPANSION",
            "citations": []
        }

    # 3. Memory & Proactive Pills Phase
    chat_turns.append({
        "turn": turn_index,
        "user_query": user_query,
        "assistant_response": answer_text,
        "route": route,
        "citations": citations,
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")
    })
    
    # Proactive rolling summarizer (triggers on turn >= 2 or when turns exceed 1,000 tokens)
    total_turns_tokens = sum(count_tokens(t.get('assistant_response', '') + t.get('user_query', '')) for t in chat_turns)
    if len(chat_turns) >= 2 or total_turns_tokens > 1000:
        recent_turns_text = "\n".join([
            f"User: {t['user_query']}\nAssistant: {t['assistant_response'][:250]}..."
            for t in chat_turns
        ])
        conversation_summary = conversation_summarizer_chain.invoke({
            "existing_summary": conversation_summary or "Initial research synthesis completed.",
            "recent_turns": recent_turns_text
        })
        
    # Generate proactive next-step follow-up pills
    recent_context = f"Summary: {conversation_summary}\nLast Query: {user_query}"
    raw_pills = follow_up_chain.invoke({
        "topic": topic,
        "report": report[:2000],
        "recent_context": recent_context
    })
    new_follow_ups = safe_extract_json(raw_pills, default=[
        "Can you elaborate on the practical implications of this?",
        "What are the major contradictory perspectives in the literature?",
        "How can we integrate this with existing industry benchmarks?"
    ])
    
    # 4. Completion Yield
    yield "followup_complete", {
        "user_query": user_query,
        "answer": answer_text,
        "route": route,
        "citations": citations,
        "mindmap": mindmap,
        "cumulative_sources": cumulative_sources,
        "chat_turns": chat_turns,
        "conversation_summary": conversation_summary,
        "follow_up_questions": new_follow_ups,
        "report": current_state.get("report", "")
    }

if __name__ == "__main__":
    topic = "humans of bihar and ai"
    print(f"Running pipeline for topic: '{topic}'")
    run_research_pipeline(topic)
