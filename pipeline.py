import re
import time
import datetime
import json
import urllib.parse
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from tools import web_search, scrape_url
from agents import (
    build_search_agent, 
    build_render_agent, 
    build_verifier_agent,
    writer_chain, 
    critic_chain,
    follow_up_chain,
    mindmap_extractor_chain,
    router_chain,
    mindmap_qa_chain,
    mindmap_updater_chain,
    conversation_summarizer_chain,
    report_expander_chain,
    safe_extract_json
)

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

# Helper to parse scores
def _parse_overall_score(feedback: str) -> float:
    """Extract the Overall score from the critic's markdown table."""
    for line in feedback.splitlines():
        if "overall" in line.lower():
            match = re.search(r"\b(\d+(?:\.\d+)?)\b", line)
            if match:
                return float(match.group(1))
    return 0.0

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
    print("Step 1 - Search Agent is querying the web...")
    print("=" * 50)
    
    search_agent = build_search_agent()
    search_result = search_agent.invoke({
        "messages": [("user", f"Find recent, reliable and detailed information about: {state['topic']}. Always cite source URLs.")]
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
        
    print("\nSearch Results:\n", results[:300] + "..." if len(results) > 300 else results)
    print(f"Extracted {len(cumulative_sources)} source URLs from search step.")
    
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
    
    research_combined = (
        f"SEARCH RESULTS:\n{state['search_results']}\n\n"
        f"DETAILED SCRAPED CONTENT:\n{state['scraped_content']}"
    )
    
    prior_feedback = ""
    if state.get("verifier_feedback"):
        prior_feedback += f"\nFact Verifier Feedback:\n{state['verifier_feedback']}\n"
    if state.get("feedback"):
        prior_feedback += f"\nCritic Quality Feedback:\n{state['feedback']}\n"
        
    if prior_feedback:
        research_combined += f"\n\nFEEDBACK TO ADDRESS IN THIS REVISION:\n{prior_feedback}"
        
    report = writer_chain.invoke({
        "topic": state["topic"],
        "role": state.get("role", "senior academic researcher"),
        "tone": state.get("tone", "formal and analytical"),
        "language": state.get("language", "English"),
        "research": research_combined,
        "current_date": datetime.datetime.now().strftime("%B %d, %Y")
    })
    
    print("\nDrafted Synthesis Report Preview:\n", report[:400] + "...")
    return {"report": report, "attempt": attempt, "verifier_feedback": "", "feedback": ""}

def verifier_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 4 - SLM Truth Guard is verifying factual integrity...")
    print("=" * 50)
    
    verifier_agent = build_verifier_agent()
    
    prompt = (
        f"FACT CHECK VERIFICATION:\n"
        f"Source Material:\n{state['search_results'][:2500]}\n\n"
        f"Drafted Report to Verify:\n{state['report'][:3500]}\n\n"
        f"Audit all factual claims, dates, names, statistics against source material."
    )
    
    response = verifier_agent.invoke({
        "messages": [("user", prompt)]
    })
    
    verifier_log = response["messages"][-1].content
    structured = response.get("structured_response")
    
    has_issues = False
    if structured and hasattr(structured, "verification_passed"):
        has_issues = not structured.verification_passed
    elif "contradict" in verifier_log.lower() or "hallucinat" in verifier_log.lower():
        has_issues = True
        
    feedback = verifier_log if has_issues else ""
    print("\nSLM Truth Guard Log:\n", verifier_log)
    print(f"\nVerification Status: {'FLAGGED FOR REVISION' if has_issues else 'PASSED'}")
    
    return {"verifier_feedback": feedback}

def critic_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 5 - LLM Critic is evaluating quality and depth...")
    print("=" * 50)
    
    feedback = critic_chain.invoke({
        "topic": state["topic"],
        "report": state["report"],
    })
    
    score = _parse_overall_score(feedback)
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

# 3. Routing Edges
def route_after_verifier(state: ResearchState):
    if state.get("verifier_feedback"):
        print("\n[VERIFICATION FAILED] Routing back to Writer to fix contradictions...")
        return "writer"
    print("\n[VERIFICATION PASSED] Routing to Critic...")
    return "critic"

def route_after_critic(state: ResearchState):
    score = state.get("score", 0.0)
    attempt = state.get("attempt", 0)
    min_score = state.get("min_score", 6.5)
    max_retries = state.get("max_retries", 2)
    
    if score >= min_score or attempt > max_retries:
        print(f"\n[PIPELINE FINISHED] Final Score: {score}/10. Generating Mind Map...")
        return "mindmap"
    print(f"\n[SCORE BELOW THRESHOLD] Score {score}/10 < {min_score}/10. Routing back to Writer...")
    return "writer"

# 4. Pipeline Orchestration for Initial Run
def build_research_graph(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
):
    builder = StateGraph(ResearchState)
    
    # Add Nodes
    builder.add_node("search", search_node)
    builder.add_node("scrape", scrape_node)
    builder.add_node("writer", writer_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("critic", critic_node)
    builder.add_node("mindmap", mindmap_node)
    builder.add_node("follow_up", follow_up_node)
    
    # Add Edges
    builder.add_edge(START, "search")
    builder.add_edge("search", "scrape")
    builder.add_edge("scrape", "writer")
    builder.add_edge("writer", "verifier")
    builder.add_edge("mindmap", "follow_up")
    builder.add_edge("follow_up", END)
    
    # Add Conditional Edges
    builder.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {
            "writer": "writer",
            "critic": "critic"
        }
    )
    builder.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "writer": "writer",
            "mindmap": "mindmap"
        }
    )
    
    # Compile Graph
    graph = builder.compile()
    
    # Initial State
    initial_state = {
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
        "conversation_summary": "",
        "chat_turns": []
    }
    
    return graph, initial_state

def stream_research_pipeline(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
    cancel_event=None
):
    """Streams node updates from the compiled LangGraph pipeline."""
    graph, initial_state = build_research_graph(
        topic=topic,
        role=role,
        tone=tone,
        language=language,
        scrape_top_n=scrape_top_n,
        min_score=min_score,
        max_retries=max_retries
    )
    
    current_state = dict(initial_state)
    for chunk in graph.stream(initial_state, stream_mode="updates"):
        if cancel_event and cancel_event.is_set():
            print("[PIPELINE CANCELLED] Cancellation event detected. Stopping execution.")
            break
            
        for node_name, update in chunk.items():
            current_state.update(update)
            yield node_name, update, current_state

def run_research_pipeline(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
    cancel_event=None
) -> dict:
    """Executes the pipeline synchronously and returns final state."""
    final_state = {}
    for node_name, update, current_state in stream_research_pipeline(
        topic=topic,
        role=role,
        tone=tone,
        language=language,
        scrape_top_n=scrape_top_n,
        min_score=min_score,
        max_retries=max_retries,
        cancel_event=cancel_event
    ):
        final_state = current_state
    return final_state

# ==============================================================================
# 5. Long-Running Conversational Multi-Turn Follow-Up Engine
# ==============================================================================
def stream_followup_turn(
    current_state: Dict[str, Any],
    user_query: str,
    mode_override: str = "auto",
    cancel_event=None
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
    if route == "LOCAL_QA":
        # Grounded Q&A over Mind Map and Report
        context_nodes = [
            f"- [{n.get('type', 'node').upper()}] {n.get('label', '')}: {n.get('details', '')}"
            for n in mindmap.get("nodes", [])
        ]
        context_block = (
            "MIND MAP KNOWLEDGE GRAPH:\n" + "\n".join(context_nodes) +
            "\n\nSYNTHESIS REPORT EXCERPT:\n" + report[:2500]
        )
        
        answer_text = mindmap_qa_chain.invoke({
            "topic": topic,
            "context": context_block,
            "history_summary": conversation_summary or "No previous follow-up history.",
            "user_query": user_query
        })
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
        
        for u in new_urls:
            domain = _extract_domain(u)
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
                new_scraped_data += f"\n\n--- Source: {u} ---\n(Scrape error: {e})"
                
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
            
        # Formulate grounded answer
        context_block = (
            f"NEW SEARCH RESULTS:\n{search_output}\n\n"
            f"NEW SCRAPED CONTENT:\n{new_scraped_data}\n\n"
            f"MIND MAP NODES:\n" + "\n".join([n.get('label', '') for n in mindmap.get('nodes', [])])
        )
        answer_text = mindmap_qa_chain.invoke({
            "topic": topic,
            "context": context_block,
            "history_summary": conversation_summary or "None",
            "user_query": user_query
        })
        citations = new_urls + _extract_urls_from_text(answer_text)
        yield "answer", {
            "answer": answer_text,
            "route": "WEB_SEARCH",
            "citations": list(set(citations))
        }

    elif route == "REPORT_EXPANSION":
        # Draft a new section to expand the synthesis report
        section_draft = report_expander_chain.invoke({
            "topic": topic,
            "user_query": user_query,
            "research_data": f"Prior Report & Scraped Context:\n{report[:2000]}",
            "report_overview": report[:1000]
        })
        
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
    
    # Proactive rolling summarizer (triggers on turn >= 2 or when turns exceed 1500 chars)
    if len(chat_turns) >= 2 or sum(len(t.get('assistant_response', '')) for t in chat_turns) > 1500:
        recent_turns_text = "\n".join([
            f"User: {t['user_query']}\nAssistant: {t['assistant_response'][:180]}..."
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
