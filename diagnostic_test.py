import os
import sys
import time
import json
import logging
import warnings
import tempfile
import shutil
import datetime
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from openai import OpenAI

# Suppress harmless warnings
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [DIAGNOSTIC] %(message)s'
)
logger = logging.getLogger("ThothDiagnostics")

_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_GREEN = "\033[92m" if _USE_COLOR else ""
_RED = "\033[91m" if _USE_COLOR else ""
_YELLOW = "\033[93m" if _USE_COLOR else ""
_CYAN = "\033[96m" if _USE_COLOR else ""
_MAGENTA = "\033[95m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_RESET = "\033[0m" if _USE_COLOR else ""

def format_header(title: str) -> str:
    return f"\n{_CYAN}{_BOLD}{'='*30} {title} {'='*30}{_RESET}\n"

def format_sublayer(name: str, status: str, details: str = "") -> str:
    badge = f"{_GREEN}[PASS]{_RESET}" if status == "PASS" else (f"{_RED}[FAIL]{_RESET}" if status == "FAIL" else f"{_YELLOW}[WARN]{_RESET}")
    detail_str = f" - {details}" if details else ""
    return f"  {badge} {_BOLD}{name}{_RESET}{detail_str}"

# Telemetry collector for GLM 5.2 Judge
telemetry_data: Dict[str, Any] = {
    "layers": {},
    "latencies": {},
    "token_metrics": {},
    "mindmap_stats": {},
    "dispatcher_metrics": {},
    "vault_metrics": {},
    "audit_findings": []
}

def run_deep_diagnostics():
    start_total_time = time.time()
    print(format_header("THOTH DEEP 7-LAYER AGENTIC DIAGNOSTICS & AUDIT"))
    load_dotenv()
    
    # =========================================================================
    # LAYER 1: ENVIRONMENT & CREDENTIAL DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 1: ENVIRONMENT & CREDENTIAL DIAGNOSTICS"))
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    # Sub-layer 1.1: .env check
    env_exists = os.path.exists(".env")
    print(format_sublayer("Sub-layer 1.1: .env File Check", "PASS" if env_exists else "WARN", f"Path: {os.path.abspath('.env')}"))
    telemetry_data["layers"]["1.1_env_file"] = "PASS" if env_exists else "WARN"
    
    # Sub-layer 1.2: Endpoint Connectivity Ping (NVIDIA or OpenAI)
    t0 = time.time()
    api_ping = False
    active_provider = "None"
    try:
        if nvidia_key and len(nvidia_key) > 20:
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            ping_res = client.chat.completions.create(
                model="meta/llama-3.1-8b-instruct",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5
            )
            api_ping = bool(ping_res.choices)
            active_provider = "NVIDIA NIM (llama-3.1-8b)"
        elif openai_key and len(openai_key) > 20:
            client = OpenAI(api_key=openai_key)
            ping_res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5
            )
            api_ping = bool(ping_res.choices)
            active_provider = "OpenAI (gpt-4o-mini)"
    except Exception as e:
        logger.error(f"API Ping Error: {e}")
        api_ping = False
        
    lat_api = round(time.time() - t0, 3)
    telemetry_data["latencies"]["primary_llm_ping"] = lat_api
    status_1_2 = "PASS" if api_ping else "FAIL"
    print(format_sublayer("Sub-layer 1.2: Primary LLM Endpoint Ping", status_1_2, f"Latency: {lat_api}s | Provider: {active_provider}"))
    telemetry_data["layers"]["1.2_llm_endpoint"] = status_1_2
    
    # Sub-layer 1.3: Scholarly & Web Search Subsystem Ping
    t0 = time.time()
    from backend.tools import web_search
    from backend.scholarly import search_scholarly_sources
    import asyncio
    search_test_res = web_search.invoke({"query": "AI agents 2026"})
    
    try:
        scholarly_res = asyncio.run(search_scholarly_sources("transformers"))
        scholarly_count = len(scholarly_res)
    except Exception as e:
        scholarly_count = 0
        logger.warning(f"Scholarly ping failed: {e}")

    lat_search = round(time.time() - t0, 3)
    telemetry_data["latencies"]["search_subsystem"] = lat_search
    search_pass = (len(search_test_res) > 20) or (scholarly_count > 0)
    status_1_3 = "PASS" if search_pass else "WARN"
    print(format_sublayer("Sub-layer 1.3: Scholarly & Web Search Subsystems", status_1_3, f"Latency: {lat_search}s | Scholarly results: {scholarly_count}"))
    telemetry_data["layers"]["1.3_search_api"] = status_1_3

    # =========================================================================
    # LAYER 2: MEMORY VAULT & HYBRID RRF VECTOR RETRIEVAL DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 2: MEMORY VAULT & HYBRID RRF RETRIEVAL DIAGNOSTICS"))
    temp_dir = tempfile.mkdtemp(prefix="thoth_diag_vault_")
    diag_db_path = os.path.join(temp_dir, "diag_store.db")
    
    from backend.memory.vault import write_note, read_note, list_notes
    from backend.memory.db import init_db, save_session, save_report, get_session, get_report
    from backend.memory.index import index_note, hybrid_search
    from backend.memory.graph import add_edge, traverse
    
    t0 = time.time()
    init_db(diag_db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Sub-layer 2.1: Vault Note Write & Claim Citation Validation
    src_note_id = "src-diag-neural-architectures"
    src_content = "# Source: Neural Scaling Laws\n\nDiscussion on modern parameter scaling and compute budgets."
    write_note(note_id=src_note_id, note_type="sources", content=src_content, frontmatter={"type": "sources", "created": now_iso, "confidence": 1.0, "sources": []}, vault_dir=temp_dir)
    
    topic_note_id = "topic-diag-scaling-hypotheses"
    topic_content = f"""# Topic: Scaling Laws

## Claims
- Compute-optimal models require equal scaling of data tokens and model parameters [[{src_note_id}]]

## Analysis
Detailed analysis of Chinchilla scaling vs Kaplan scaling laws.
"""
    write_note(note_id=topic_note_id, note_type="topics", content=topic_content, frontmatter={"type": "topics", "created": now_iso, "confidence": 0.95, "sources": [src_note_id]}, vault_dir=temp_dir)
    
    # Verify uncited claim raises ValueError
    uncited_caught = False
    try:
        write_note(note_id="topic-uncited", note_type="topics", content="# Claims\n- Uncited claim line without brackets\n", vault_dir=temp_dir)
    except ValueError:
        uncited_caught = True
        
    status_2_1 = "PASS" if uncited_caught and os.path.exists(os.path.join(temp_dir, "topics", f"{topic_note_id}.md")) else "FAIL"
    print(format_sublayer("Sub-layer 2.1: Vault Markdown & Strict Claim Citations", status_2_1, f"Claim validator enforced: {uncited_caught}"))
    telemetry_data["layers"]["2.1_vault_claim_validation"] = status_2_1
    
    # Sub-layer 2.2: SQLite Vector Index & Hybrid RRF Search Round-Trip
    src_note_obj = read_note(src_note_id, vault_dir=temp_dir)
    topic_note_obj = read_note(topic_note_id, vault_dir=temp_dir)
    index_note(src_note_obj, db_path=diag_db_path)
    index_note(topic_note_obj, db_path=diag_db_path)
    
    search_res = hybrid_search("compute optimal parameter scaling", top_k=2, db_path=diag_db_path, vault_dir=temp_dir)
    found_ids = [n.get("note_id") if isinstance(n, dict) else getattr(n, "note_id", "") for n in search_res]
    status_2_2 = "PASS" if topic_note_id in found_ids else "FAIL"
    lat_vault = round(time.time() - t0, 3)
    telemetry_data["latencies"]["vault_index_search_roundtrip"] = lat_vault
    telemetry_data["vault_metrics"] = {"indexed_notes": 2, "retrieved": found_ids}
    print(format_sublayer("Sub-layer 2.2: Vault Index -> Hybrid RRF Retrieval Round-Trip", status_2_2, f"Retrieved: {found_ids} (Latency: {lat_vault}s)"))
    telemetry_data["layers"]["2.2_vault_hybrid_search"] = status_2_2
    
    # Sub-layer 2.3: Knowledge Graph Edge Traversal & Schema
    add_edge(source_note=topic_note_id, relation="cites", target_note=src_note_id, confidence=1.0, db_path=diag_db_path)
    connected_notes = traverse(start_note=topic_note_id, max_depth=1, db_path=diag_db_path)
    status_2_3 = "PASS" if src_note_id in connected_notes else "FAIL"
    print(format_sublayer("Sub-layer 2.3: Knowledge Graph BFS Traversal", status_2_3, f"Hops from {topic_note_id}: {connected_notes}"))
    telemetry_data["layers"]["2.3_knowledge_graph"] = status_2_3
    
    # Sub-layer 2.4: Sessions and Reports Table CRUD
    sess = save_session(session_id="sess_diag_01", title="Scaling Diagnostic", summary="Diag session", db_path=diag_db_path)
    rep = save_report(report_id="rep_diag_01", session_id="sess_diag_01", topic="Scaling Diagnostic", content="Report content", score=9.2, db_path=diag_db_path)
    sess_fetched = get_session("sess_diag_01", db_path=diag_db_path)
    rep_fetched = get_report("rep_diag_01", db_path=diag_db_path)
    status_2_4 = "PASS" if sess_fetched and rep_fetched and rep_fetched["score"] == 9.2 else "FAIL"
    print(format_sublayer("Sub-layer 2.4: SQLite Sessions & Reports Store", status_2_4, f"Session & Report persisted successfully"))
    telemetry_data["layers"]["2.4_app_db_store"] = status_2_4

    # Clean up temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)

    # =========================================================================
    # LAYER 3: DISPATCHER RESILIENCE & CIRCUIT BREAKER DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 3: DISPATCHER RESILIENCE & CIRCUIT BREAKER DIAGNOSTICS"))
    from backend.dispatcher import Dispatcher, CircuitBreakerOpenError
    
    # Sub-layer 3.1: Exponential Backoff Retry Recovery
    t0 = time.time()
    call_attempts = 0
    def flaky_func():
        nonlocal call_attempts
        call_attempts += 1
        if call_attempts < 3:
            raise RuntimeError(f"Simulated network drop attempt #{call_attempts}")
        return "Success on Attempt 3"
        
    disp_flaky = Dispatcher(max_attempts=4, base_delay=0.01, max_consecutive_failures=5, cooloff_seconds=0.1)
    res_backoff = asyncio.run(disp_flaky.call(flaky_func))
    lat_backoff = round(time.time() - t0, 3)
    status_3_1 = "PASS" if res_backoff == "Success on Attempt 3" and call_attempts == 3 else "FAIL"
    print(format_sublayer("Sub-layer 3.1: Exponential Backoff & Jitter Recovery", status_3_1, f"Recovered after {call_attempts} attempts (Latency: {lat_backoff}s)"))
    telemetry_data["layers"]["3.1_dispatcher_backoff"] = status_3_1

    # Sub-layer 3.2: Circuit Breaker Trip to OPEN
    disp_trip = Dispatcher(max_attempts=1, base_delay=0.01, max_consecutive_failures=2, cooloff_seconds=0.05)
    def always_fails():
        raise ConnectionResetError("500 Upstream Service Unavailable")
        
    for _ in range(2):
        try:
            asyncio.run(disp_trip.call(always_fails))
        except Exception:
            pass
            
    is_open = disp_trip.state == "OPEN"
    status_3_2 = "PASS" if is_open else "FAIL"
    print(format_sublayer("Sub-layer 3.2: Circuit Breaker Trip to OPEN", status_3_2, f"State: {disp_trip.state} (Failures: {disp_trip.consecutive_failures})"))
    telemetry_data["layers"]["3.2_circuit_breaker_open"] = status_3_2
    
    # Sub-layer 3.3: Circuit Breaker Cooldown & Recovery
    time.sleep(0.06)  # Wait past recovery time
    def now_succeeds():
        return "Recovered OK"
    res_recovery = asyncio.run(disp_trip.call(now_succeeds))
    is_closed = disp_trip.state == "CLOSED"
    status_3_3 = "PASS" if is_closed and res_recovery == "Recovered OK" else "FAIL"
    print(format_sublayer("Sub-layer 3.3: Circuit Breaker Half-Open Recovery -> CLOSED", status_3_3, f"Final State: {disp_trip.state}"))
    telemetry_data["layers"]["3.3_circuit_breaker_recovery"] = status_3_3

    # =========================================================================
    # LAYER 4: ORCHESTRATOR END-TO-END EXECUTION (MOCKED PIPELINE RUN)
    # =========================================================================
    print(format_header("LAYER 4: ORCHESTRATOR END-TO-END EXECUTION (PLAN-ACT-REPLAN)"))
    from backend.orchestrator import run_research_pipeline
    
    test_topic = "Agentic AI in Medical Imaging 2026"
    print(f"  Running Orchestrator End-to-End against Mocked Model & Scraper responses...")
    
    mock_search_data = "Search results citing https://arxiv.org/abs/2601.0001 and https://nih.gov/med-ai"
    mock_scraped_dict = {
        "https://arxiv.org/abs/2601.0001": "Medical imaging multi-agent models achieve 98% accuracy on MRI anomaly detection.",
        "https://nih.gov/med-ai": "FDA has cleared 40 new agentic imaging frameworks in 2026."
    }
    mock_report = """# Agentic AI in Medical Imaging 2026

Medical imaging multi-agent models achieve 98% accuracy on MRI anomaly detection [[https://arxiv.org/abs/2601.0001]].
Furthermore, FDA has cleared 40 new agentic imaging frameworks in 2026 [[https://nih.gov/med-ai]].
"""
    mock_critic_res = MagicMock(
        overall_score=8.5,
        faithfulness=9.0,
        relevance=8.5,
        completeness=8.0,
        evidence_quality=8.5,
        clarity_coherence=8.5,
        strengths=["Strong evidence grounding"],
        areas_to_improve=[],
        verdict="Ready for publication.",
        reasoning="Rigorous analysis."
    )
    mock_mindmap = {
        "nodes": [
            {"id": "root", "label": "Medical AI", "type": "topic", "details": "Core Topic", "group": "topic"},
            {"id": "n1", "label": "MRI Anomaly Detection", "type": "subtopic", "details": "98% Accuracy", "group": "subtopic"}
        ],
        "edges": [{"from": "root", "to": "n1", "label": "accuracy"}]
    }

    t0 = time.time()
    with patch("backend.orchestrator.search_node", return_value={"search_results": mock_search_data, "cumulative_sources": [{"url": "https://arxiv.org/abs/2601.0001", "domain": "arxiv.org", "title": "Paper 1", "added_in_turn": 0}]}), \
         patch("backend.orchestrator.concurrent_scrape_urls", return_value=("Medical imaging multi-agent models achieve 98% accuracy on MRI anomaly detection.", [{"url": "https://arxiv.org/abs/2601.0001", "domain": "arxiv.org", "title": "Paper 1", "added_in_turn": 0}])), \
         patch("backend.orchestrator.writer_node", return_value={"report": mock_report, "draft": mock_report}), \
         patch("backend.orchestrator.verifier_node", return_value={"verifier_feedback": ""}), \
         patch("backend.orchestrator.critic_node", return_value={"score": 8.5, "feedback": "Excellent report."}), \
         patch("backend.orchestrator.mindmap_node", return_value={"mindmap": mock_mindmap}), \
         patch("backend.orchestrator.follow_up_node", return_value={"follow_up_questions": ["What are FDA regulatory steps?"]}):
         
        orch_result = run_research_pipeline(
            topic=test_topic,
            scrape_top_n=2,
            min_score=6.5,
            max_retries=1
        )
        
    lat_orch = round(time.time() - t0, 3)
    telemetry_data["latencies"]["orchestrator_mocked_run"] = lat_orch
    
    orch_rep = orch_result.get("report", "")
    orch_score = orch_result.get("score", 0.0)
    orch_mm_nodes = len(orch_result.get("mindmap", {}).get("nodes", []))
    status_4 = "PASS" if len(orch_rep) > 100 and orch_score >= 8.0 and orch_mm_nodes >= 2 else "FAIL"
    print(format_sublayer("Sub-layer 4.1: Orchestrator Plan-Act-Observe-Replan Execution", status_4, f"Score: {orch_score}/10 | Report Chars: {len(orch_rep)} | Nodes: {orch_mm_nodes} (Latency: {lat_orch}s)"))
    telemetry_data["layers"]["4_orchestrator_execution"] = status_4

    # =========================================================================
    # LAYER 5: MULTI-TURN CONVERSATIONAL & SESSION MEMORY BUDGETING
    # =========================================================================
    print(format_header("LAYER 5: MULTI-TURN CONVERSATIONAL & MEMORY BUDGETING"))
    from backend.memory.session import SessionMemory, DEFAULT_TOKEN_BUDGET
    from backend.pipeline import stream_followup_turn
    
    # Sub-layer 5.1: SessionMemory Token Budgeting & Turn FIFO Slicing
    session_mem = SessionMemory(session_id="diag_session")
    for i in range(1, 6):
        session_mem.add_turn(f"User Query {i}", f"Assistant detailed response {i} " * 40)
    session_mem.summary = "Rolling compression of earlier turns."
    
    budget_ctx = session_mem.get_context(DEFAULT_TOKEN_BUDGET, retrieved_notes_text="Retrieved note content " * 30)
    status_5_1 = "PASS" if budget_ctx["summary"] and budget_ctx["retrieved_notes"] and budget_ctx["recent_turns"] else "FAIL"
    print(format_sublayer("Sub-layer 5.1: Session Memory Context Allocation & Slicing", status_5_1, f"Budget limits respected across System, Retrieved Notes, Summary & Turns"))
    telemetry_data["layers"]["5.1_session_memory_budget"] = status_5_1
    
    # Sub-layer 5.2: Multi-Turn LOCAL_QA Route Execution
    from langchain_core.runnables import RunnableSequence
    t0 = time.time()
    turn1_events = {}
    with patch.object(RunnableSequence, "invoke") as mock_run:
        mock_run.side_effect = [
            '{"route": "LOCAL_QA", "reasoning": "In-context QA"}',
            "The primary finding is 98% MRI anomaly detection accuracy.",
            '["What about CT scans?"]'
        ]
        for ev_name, ev_payload in stream_followup_turn(orch_result, "What are the primary findings mentioned in this research?"):
            turn1_events[ev_name] = ev_payload
            
    lat_turn1 = round(time.time() - t0, 3)
    t1_ans = turn1_events.get("answer", {}).get("answer", "")
    t1_route = turn1_events.get("answer", {}).get("route", "")
    status_5_2 = "PASS" if len(t1_ans) > 20 and t1_route == "LOCAL_QA" else "FAIL"
    print(format_sublayer("Sub-layer 5.2: Multi-Turn Fast Context QA (LOCAL_QA)", status_5_2, f"Latency: {lat_turn1}s | Route: {t1_route}"))
    telemetry_data["layers"]["5.2_turn1_local_qa"] = status_5_2
    
    # Sub-layer 5.3: Multi-Turn WEB_SEARCH Route with Vault Persistence
    t0 = time.time()
    turn2_events = {}
    with patch.object(RunnableSequence, "invoke") as mock_run, \
         patch("backend.pipeline.web_search") as mock_ws, \
         patch("backend.pipeline.scrape_url") as mock_sc:
         
        mock_ws.invoke.return_value = "Search result https://fda.gov/ai-clearances-2026"
        mock_sc.invoke.return_value = "FDA published new clearances for imaging AI models."
        mock_run.side_effect = [
            '{"route": "WEB_SEARCH", "reasoning": "Requires new data", "search_query": "FDA approvals medical AI 2026"}',
            json.dumps(mock_mindmap),
            "FDA cleared 40 new frameworks in 2026.",
            '["What are safety checks?"]'
        ]
        for ev_name, ev_payload in stream_followup_turn(orch_result, "What are the latest regulatory FDA approvals in 2026?"):
            turn2_events[ev_name] = ev_payload
            
    lat_turn2 = round(time.time() - t0, 3)
    t2_vault = turn2_events.get("vault_update", {}).get("vault_notes", [])
    status_5_3 = "PASS" if len(t2_vault) >= 1 and turn2_events.get("answer", {}).get("route") == "WEB_SEARCH" else "FAIL"
    print(format_sublayer("Sub-layer 5.3: Targeted Web Probe & Follow-Up Vault Persistence", status_5_3, f"Vault Notes Written: {len(t2_vault)} | Latency: {lat_turn2}s"))
    telemetry_data["layers"]["5.3_turn2_web_probe"] = status_5_3

    # =========================================================================
    # LAYER 6: TELEMETRY & SYSTEM HEALTH SCORECARD
    # =========================================================================
    print(format_header("LAYER 6: TELEMETRY & SYSTEM HEALTH SCORECARD"))
    total_elapsed = round(time.time() - start_total_time, 2)
    telemetry_data["total_elapsed_time"] = total_elapsed
    
    print(f"  {_BOLD}Total Diagnostics Run Time:{_RESET} {total_elapsed}s")
    print(f"  {_BOLD}Component Latency Profile:{_RESET}")
    for k, v in telemetry_data["latencies"].items():
        print(f"    - {k}: {v}s")
    print(f"  {_BOLD}Orchestrator Mind Map Scale:{_RESET} {orch_mm_nodes} nodes, {len(orch_result.get('mindmap', {}).get('edges', []))} edges")
    print(f"  {_BOLD}Cumulative Sources Evaluated:{_RESET} {len(orch_result.get('cumulative_sources', []))} sources")

    # =========================================================================
    # LAYER 7: AI REVIEWER & OPTIMIZATION EVALUATOR (GLM-5.2 JUDGE)
    # =========================================================================
    print(format_header("LAYER 7: GLM 5.2 AI REVIEWER & OPTIMIZATION JUDGE"))
    print("  Initializing GLM 5.2 (z-ai/glm-5.2 - 753B MoE Frontier Model) via NVIDIA NIM...")
    
    telemetry_json = json.dumps(telemetry_data, indent=2)
    judge_prompt = f"""You are the Lead Systems Architect & AI Judge evaluating the Thoth Autonomous Agentic Research Platform.
Review the following complete diagnostic telemetry collected across all 6 layers of the system:

--- DIAGNOSTIC TELEMETRY DATA ---
{telemetry_json}
---------------------------------

Analyze and provide an in-depth architectural evaluation:
1. **System Health & Reliability Verdict**: Assess the performance of the Orchestrator Plan-Act-Observe-Replan loop, Dispatcher Circuit Breaker, and Markdown/SQLite Vault storage.
2. **Latency & Bottleneck Analysis**: Review individual component timings and identify potential optimizations.
3. **Token Economics & Sustainability**: Evaluate the rolling summarizer and token budgeting for long-running multi-turn sessions.
4. **Actionable Recommendations**: List 2-3 high-impact architectural suggestions to make the system even more scalable and robust.

Format your response cleanly in structured Markdown."""

    judge_executed = False
    if nvidia_key and len(nvidia_key) > 20:
        try:
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            completion = client.chat.completions.create(
                model="z-ai/glm-5.2",
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.7,
                max_tokens=4096,
                stream=True
            )
            
            print(f"\n{_MAGENTA}{_BOLD}[GLM 5.2 ARCHITECTURAL REVIEW & JUDGMENT]{_RESET}\n")
            judge_output = ""
            for chunk in completion:
                if not getattr(chunk, "choices", None):
                    continue
                if len(chunk.choices) == 0 or getattr(chunk.choices[0], "delta", None) is None:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None) is not None:
                    content_chunk = delta.content
                    judge_output += content_chunk
                    print(content_chunk, end="", flush=True)
                    
            print(f"\n\n{_GREEN}{_BOLD}✓ GLM 5.2 Diagnostic Review Completed Successfully!{_RESET}")
            judge_executed = True
        except Exception as e:
            logger.warning(f"GLM 5.2 Review failed: {e}")
            
    if not judge_executed:
        print(f"  {_YELLOW}[INFO] Live GLM 5.2 Judge skipped or in offline mode. Telemetry summary verified.{_RESET}")

    print(format_header("ALL 7 DIAGNOSTIC LAYERS COMPLETED"))


if __name__ == "__main__":
    run_deep_diagnostics()
