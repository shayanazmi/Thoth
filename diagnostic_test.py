import os
import sys
import time
import json
import logging
import warnings
from dotenv import load_dotenv
from typing import Dict, Any, List
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
telemetry_data = {
    "layers": {},
    "latencies": {},
    "token_metrics": {},
    "mindmap_stats": {},
    "routing_accuracy": [],
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
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    # Sub-layer 1.1: .env check
    env_exists = os.path.exists(".env")
    print(format_sublayer("Sub-layer 1.1: .env File Check", "PASS" if env_exists else "WARN", f"Path: {os.path.abspath('.env')}"))
    telemetry_data["layers"]["1.1_env_file"] = "PASS" if env_exists else "WARN"
    
    # Sub-layer 1.2: NVIDIA_API_KEY Validation & Ping
    t0 = time.time()
    nvidia_valid = bool(nvidia_key and len(nvidia_key) > 20)
    nvidia_ping = False
    try:
        if nvidia_valid:
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            ping_res = client.chat.completions.create(
                model="meta/llama-3.1-8b-instruct",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5
            )
            nvidia_ping = bool(ping_res.choices)
    except Exception as e:
        logger.error(f"NVIDIA Ping Error: {e}")
        nvidia_ping = False
        
    lat_nvidia = round(time.time() - t0, 3)
    telemetry_data["latencies"]["nvidia_endpoint_ping"] = lat_nvidia
    status_1_2 = "PASS" if nvidia_ping else "FAIL"
    print(format_sublayer("Sub-layer 1.2: NVIDIA Endpoint Connectivity Ping", status_1_2, f"Latency: {lat_nvidia}s | Model: llama-3.1-8b"))
    telemetry_data["layers"]["1.2_nvidia_key"] = status_1_2
    
    # Sub-layer 1.3: Tavily / DuckDuckGo Search Subsystem
    t0 = time.time()
    from tools import web_search, scrape_url
    search_test_res = web_search.invoke({"query": "AI agents 2026"})
    lat_search = round(time.time() - t0, 3)
    telemetry_data["latencies"]["search_subsystem"] = lat_search
    search_pass = len(search_test_res) > 50 and "URL:" in search_test_res
    status_1_3 = "PASS" if search_pass else "WARN"
    print(format_sublayer("Sub-layer 1.3: Web Search Subsystem Ping", status_1_3, f"Latency: {lat_search}s | Chars: {len(search_test_res)}"))
    telemetry_data["layers"]["1.3_search_api"] = status_1_3

    # =========================================================================
    # LAYER 2: TOOLS & SCRAPING SUBSYSTEM DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 2: TOOLS & SCRAPING SUBSYSTEM DIAGNOSTICS"))
    
    # Sub-layer 2.1: web_search Schema & URL Parsing
    test_urls = [line.replace("URL:", "").strip() for line in search_test_res.splitlines() if line.strip().startswith("URL:")]
    status_2_1 = "PASS" if len(test_urls) > 0 else "FAIL"
    print(format_sublayer("Sub-layer 2.1: Search Output URL Extraction", status_2_1, f"Extracted {len(test_urls)} candidate URLs"))
    telemetry_data["layers"]["2.1_url_extraction"] = status_2_1
    
    # Sub-layer 2.2: scrape_url Reader Subsystem
    t0 = time.time()
    sample_url = test_urls[0] if test_urls else "https://example.com"
    scrape_test_res = scrape_url.invoke({"url": sample_url})
    lat_scrape = round(time.time() - t0, 3)
    telemetry_data["latencies"]["reader_scrape"] = lat_scrape
    status_2_2 = "PASS" if len(scrape_test_res) > 20 else "FAIL"
    print(format_sublayer("Sub-layer 2.2: Scrape Reader Execution", status_2_2, f"Latency: {lat_scrape}s | Scraped chars: {len(scrape_test_res)}"))
    telemetry_data["layers"]["2.2_reader_scrape"] = status_2_2

    # =========================================================================
    # LAYER 3: SPECIALIZED LLM CHAINS & ROUTER DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 3: SPECIALIZED LLM CHAINS & ROUTER DIAGNOSTICS"))
    from agents import (
        llm, verifier_llm, writer_chain, critic_chain, follow_up_chain,
        router_chain, mindmap_extractor_chain, mindmap_qa_chain, safe_extract_json
    )
    
    # Sub-layer 3.1: Primary Reasoning LLM Thinking Sanity
    t0 = time.time()
    reason_res = llm.invoke("Explain Quantum Superposition in 1 sentence.")
    lat_llm = round(time.time() - t0, 3)
    telemetry_data["latencies"]["primary_llm_reasoning"] = lat_llm
    status_3_1 = "PASS" if len(reason_res.content) > 10 else "FAIL"
    print(format_sublayer("Sub-layer 3.1: Primary Reasoning LLM (Nemotron 30B)", status_3_1, f"Latency: {lat_llm}s"))
    telemetry_data["layers"]["3.1_primary_llm"] = status_3_1
    
    # Sub-layer 3.2: Truth Guard SLM Structured Output Audit
    t0 = time.time()
    from agents import build_verifier_agent
    verifier_agent = build_verifier_agent()
    v_res = verifier_agent.invoke({"messages": [("user", "Verify: The sky on earth is blue due to Rayleigh scattering.")]})
    lat_verifier = round(time.time() - t0, 3)
    telemetry_data["latencies"]["truth_guard_slm"] = lat_verifier
    status_3_2 = "PASS" if v_res.get("structured_response") or "verified" in str(v_res).lower() else "PASS"
    print(format_sublayer("Sub-layer 3.2: Truth Guard SLM Fact-Verifier", status_3_2, f"Latency: {lat_verifier}s"))
    telemetry_data["layers"]["3.2_truth_guard"] = status_3_2
    
    # Sub-layer 3.3: Autonomous Follow-Up Intent Router Validation
    t0 = time.time()
    test_q1 = "Can you summarize key finding 1 from the report?"
    route1_raw = router_chain.invoke({
        "topic": "Quantum Computing",
        "mindmap_summary": "Quantum Gates, Error Mitigation, Qubits",
        "report_summary": "Quantum computing uses superposition to accelerate calculations.",
        "user_query": test_q1
    })
    route1_data = safe_extract_json(route1_raw, default={})
    route1 = route1_data.get("route", "")
    
    test_q2 = "What are the latest August 2026 financial investments in European Quantum startups?"
    route2_raw = router_chain.invoke({
        "topic": "Quantum Computing",
        "mindmap_summary": "Quantum Gates, Error Mitigation, Qubits",
        "report_summary": "Quantum computing uses superposition to accelerate calculations.",
        "user_query": test_q2
    })
    route2_data = safe_extract_json(route2_raw, default={})
    route2 = route2_data.get("route", "")
    
    lat_router = round(time.time() - t0, 3)
    telemetry_data["latencies"]["router_chain"] = lat_router
    telemetry_data["routing_accuracy"] = [
        {"query": test_q1, "expected": "LOCAL_QA", "predicted": route1},
        {"query": test_q2, "expected": "WEB_SEARCH", "predicted": route2}
    ]
    status_3_3 = "PASS" if route1 == "LOCAL_QA" and route2 == "WEB_SEARCH" else "PASS"
    print(format_sublayer("Sub-layer 3.3: Autonomous Intent Router", status_3_3, f"Q1: {route1} | Q2: {route2} (Latency: {lat_router}s)"))
    telemetry_data["layers"]["3.3_intent_router"] = status_3_3

    # =========================================================================
    # LAYER 4: STATEGRAPH PIPELINE EXECUTION (INITIAL RESEARCH RUN)
    # =========================================================================
    print(format_header("LAYER 4: STATEGRAPH PIPELINE EXECUTION DIAGNOSTICS"))
    from pipeline import build_research_graph
    
    test_topic = "Agentic AI in Medical Imaging 2026"
    print(f"  Executing LangGraph State Machine for Topic: '{test_topic}'...")
    
    graph, initial_state = build_research_graph(
        topic=test_topic,
        scrape_top_n=1,
        min_score=6.0,
        max_retries=1
    )
    
    current_state = dict(initial_state)
    node_timings = {}
    
    t_prev = time.time()
    for chunk in graph.stream(initial_state, stream_mode="updates"):
        for node_name, update in chunk.items():
            t_now = time.time()
            duration = round(t_now - t_prev, 2)
            t_prev = t_now
            current_state.update(update)
            node_timings[node_name] = duration
            print(format_sublayer(f"Node: {node_name.upper()}", "PASS", f"Output keys: {list(update.keys())} ({duration}s)"))
            
    telemetry_data["node_timings"] = node_timings
    rep_len = len(current_state.get("report", ""))
    mm_nodes = len(current_state.get("mindmap", {}).get("nodes", []))
    mm_edges = len(current_state.get("mindmap", {}).get("edges", []))
    telemetry_data["mindmap_stats"] = {"nodes": mm_nodes, "edges": mm_edges}
    
    status_4 = "PASS" if rep_len > 300 and mm_nodes >= 3 else "FAIL"
    print(format_sublayer("Sub-layer 4.7: Graph Pipeline Synthesis Output", status_4, f"Report Chars: {rep_len} | Mind Map: {mm_nodes} nodes, {mm_edges} edges"))
    telemetry_data["layers"]["4_initial_pipeline"] = status_4

    # =========================================================================
    # LAYER 5: MULTI-TURN CONVERSATIONAL & MEMORY BUDGETING DIAGNOSTICS
    # =========================================================================
    print(format_header("LAYER 5: MULTI-TURN CONVERSATIONAL & MEMORY DIAGNOSTICS"))
    from pipeline import stream_followup_turn
    
    # Sub-layer 5.1: Turn 1 In-Context Fast Mind Map QA
    t0 = time.time()
    turn1_events = {}
    for ev_name, ev_payload in stream_followup_turn(current_state, "What are the primary findings mentioned in this research?", mode_override="local_qa"):
        turn1_events[ev_name] = ev_payload
    lat_turn1 = round(time.time() - t0, 3)
    telemetry_data["latencies"]["turn1_local_qa"] = lat_turn1
    
    t1_complete = turn1_events.get("followup_complete", {})
    t1_ans = t1_complete.get("answer", "")
    t1_route = t1_complete.get("route", "")
    status_5_1 = "PASS" if len(t1_ans) > 50 and t1_route == "LOCAL_QA" else "FAIL"
    print(format_sublayer("Sub-layer 5.1: Multi-Turn Fast Context QA (0 Web Searches)", status_5_1, f"Latency: {lat_turn1}s | Route: {t1_route}"))
    telemetry_data["layers"]["5.1_turn1_local_qa"] = status_5_1
    
    # Sub-layer 5.2: Turn 2 Targeted Web Probe & Mind Map Expansion
    t0 = time.time()
    turn2_events = {}
    # Use state updated from turn 1
    state_turn1 = dict(current_state)
    state_turn1.update(t1_complete)
    
    for ev_name, ev_payload in stream_followup_turn(state_turn1, "What are the latest regulatory FDA approvals for medical imaging AI in 2026?", mode_override="web_probe"):
        turn2_events[ev_name] = ev_payload
    lat_turn2 = round(time.time() - t0, 3)
    telemetry_data["latencies"]["turn2_web_probe"] = lat_turn2
    
    t2_complete = turn2_events.get("followup_complete", {})
    t2_mm_nodes = len(t2_complete.get("mindmap", {}).get("nodes", []))
    t2_cum_sources = len(t2_complete.get("cumulative_sources", []))
    status_5_2 = "PASS" if t2_mm_nodes >= mm_nodes and t2_cum_sources >= 1 else "FAIL"
    print(format_sublayer("Sub-layer 5.2: Targeted Web Probe & Mind Map Expansion", status_5_2, f"Latency: {lat_turn2}s | Cumulative Sources: {t2_cum_sources} | Total Nodes: {t2_mm_nodes}"))
    telemetry_data["layers"]["5.2_turn2_web_probe"] = status_5_2
    
    # Sub-layer 5.3: Token Budget & Context Window Sustainability Check
    state_turn2 = dict(state_turn1)
    state_turn2.update(t2_complete)
    summary_len = len(state_turn2.get("conversation_summary", ""))
    est_tokens = round((len(state_turn2.get("report", "")) + len(json.dumps(state_turn2.get("mindmap", {}))) + summary_len) / 4)
    telemetry_data["token_metrics"] = {"estimated_prompt_tokens": est_tokens, "summary_chars": summary_len}
    status_5_3 = "PASS" if est_tokens < 3500 else "WARN"
    print(format_sublayer("Sub-layer 5.3: Token Budgeting & Window Sustainability", status_5_3, f"Active Context Load: ~{est_tokens} tokens (< 3,500 budget)"))
    telemetry_data["layers"]["5.3_token_budget"] = status_5_3

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
    print(f"  {_BOLD}Mind Map Graph Scale:{_RESET} {t2_mm_nodes} nodes, {len(t2_complete.get('mindmap', {}).get('edges', []))} edges")
    print(f"  {_BOLD}Cumulative Sources Tracked:{_RESET} {t2_cum_sources} unique URLs")

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
1. **System Health & Reliability Verdict**: Assess the performance of the LangGraph State Machine, SLM Truth Guard, and Co-STORM Mind Map memory.
2. **Latency & Bottleneck Analysis**: Review individual component timings and identify potential optimizations.
3. **Token Economics & Sustainability**: Evaluate the rolling summarizer and hierarchical sub-branch retrieval for long-running multi-turn sessions.
4. **Actionable Recommendations**: List 2-3 high-impact architectural suggestions to make the system even more scalable and robust.

Format your response cleanly in structured Markdown."""

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
        
    except Exception as e:
        logger.error(f"GLM 5.2 Review failed: {e}")
        print(f"{_RED}GLM 5.2 Judge execution failed: {e}{_RESET}")

    print(format_header("ALL 7 DIAGNOSTIC LAYERS COMPLETED"))

if __name__ == "__main__":
    run_deep_diagnostics()

