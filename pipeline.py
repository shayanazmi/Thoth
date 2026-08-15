import re
import time
import datetime
import json
from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END
from agents import (
    build_search_agent, 
    build_render_agent, 
    build_verifier_agent,
    writer_chain, 
    critic_chain,
    follow_up_chain
)

# 1. State Definition
class ResearchState(TypedDict):
    topic: str
    role: str
    tone: str
    language: str
    scrape_top_n: int
    min_score: float
    max_retries: int
    attempt: int
    
    # Stateful data
    search_results: str
    scraped_content: str
    report: str
    feedback: str
    verifier_feedback: str
    score: float
    follow_up_questions: List[str]

# Helper to parse scores
def _parse_overall_score(feedback: str) -> float:
    """Extract the Overall score from the critic's markdown table."""
    for line in feedback.splitlines():
        if "overall" in line.lower():
            match = re.search(r"\b(\d+(?:\.\d+)?)\b", line)
            if match:
                return float(match.group(1))
    return 0.0

# 2. Node Implementations
def search_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 1 - Search Agent is querying the web...")
    print("=" * 50)
    
    search_agent = build_search_agent()
    search_result = search_agent.invoke({
        "messages": [("user", f"Find recent, reliable and detailed information about: {state['topic']}")]
    })
    
    results = search_result["messages"][-1].content
    print("\nSearch Results:\n", results)
    
    time.sleep(2)
    return {"search_results": results}

def scrape_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print(f"Step 2 - Reader Agent is scraping top {state['scrape_top_n']} resources...")
    print("=" * 50)
    
    reader_agent = build_render_agent()
    
    # Extract URLs from search results
    urls = [
        line.replace("URL:", "").strip()
        for line in state["search_results"].splitlines()
        if line.strip().startswith("URL:")
    ][:state["scrape_top_n"]]
    
    scraped_content = ""
    for url in urls:
        print(f"\nScraping: {url}")
        try:
            reader_result = reader_agent.invoke({
                "messages": [("user", f"Scrape this URL for detailed content: {url}")]
            })
            scraped_content += f"\n\n--- Source: {url} ---\n"
            scraped_content += reader_result["messages"][-1].content
        except Exception as e:
            scraped_content += f"\n\n--- Source: {url} ---\n(Failed to scrape: {e})"
        time.sleep(1)
        
    print("\nScraped Content length:", len(scraped_content))
    time.sleep(2)
    return {"scraped_content": scraped_content}

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
        prior_feedback += f"\n[FACT-CHECKER CONTRADICTIONS]:\n{state['verifier_feedback']}\n"
    if state.get("feedback"):
        prior_feedback += f"\n[CRITIC QUALITY FEEDBACK]:\n{state['feedback']}\n"
        
    research_input = research_combined
    if prior_feedback:
        research_input += (
            f"\n\n=== Feedback to Address in Revision ===\n{prior_feedback}"
            f"\n\nPlease address the above feedback point-by-point in your revised report."
        )
        
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    
    report = writer_chain.invoke({
        "topic": state["topic"],
        "role": state["role"],
        "tone": state["tone"],
        "language": state["language"],
        "research": research_input,
        "current_date": current_date
    })
    
    print("\nDrafted Report:\n", report[:1000] + "\n...[TRUNCATED]")
    time.sleep(2)
    # Clear feedback items since they've been incorporated
    return {
        "report": report,
        "attempt": attempt,
        "verifier_feedback": "",
        "feedback": ""
    }

def verifier_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 4 - Fact-Verifier Agent is checking citations & claims...")
    print("=" * 50)
    
    verifier_agent = build_verifier_agent()
    
    prompt = (
        f"Verify the claims in this drafted report:\n\n{state['report']}\n\n"
        f"Context from scraped sources:\n{state['scraped_content']}"
    )
    
    verifier_result = verifier_agent.invoke({
        "messages": [("user", prompt)]
    })
    
    # Extract the structured response parsed into Pydantic
    structured_report = verifier_result.get("structured_response")
    
    verifier_feedback = ""
    if structured_report:
        invalid_claims = [res for res in structured_report.results if not res.is_valid]
        if invalid_claims:
            verifier_feedback = "The following claims were flagged as unsupported or contradicted:\n"
            for claim in invalid_claims:
                verifier_feedback += f"- Claim: '{claim.claim}' | Reason: {claim.reason_if_failed}\n"
                
    if verifier_feedback:
        print("\nVerifier Feedback:\n", verifier_feedback)
    else:
        print("\nAll claims successfully verified by the Truth Guard.")
        
    time.sleep(2)
    return {"verifier_feedback": verifier_feedback}

def critic_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 5 - Critic is reviewing the report...")
    print("=" * 50)
    
    feedback = critic_chain.invoke({
        "topic": state["topic"],
        "report": state["report"],
    })
    
    score = _parse_overall_score(feedback)
    print("\nCritic Feedback:\n", feedback)
    print(f"\nOverall Score: {score}/10")
    
    time.sleep(2)
    return {"feedback": feedback, "score": score}

def follow_up_node(state: ResearchState) -> dict:
    print("\n" + "= " * 50)
    print("Step 6 - Generating dynamic follow-up questions...")
    print("=" * 50)
    
    raw_response = follow_up_chain.invoke({
        "topic": state["topic"],
        "report": state["report"]
    })
    
    questions = []
    try:
        # Clean markdown code blocks if the model wrapped them
        clean_json = raw_response.replace("```json", "").replace("```", "").strip()
        questions = json.loads(clean_json)
    except Exception as e:
        print(f"Failed to parse follow-up questions JSON: {e}. Raw response: {raw_response}")
        # Fallback regex extraction
        questions = re.findall(r'"([^"]+)"', raw_response)
        if not questions:
            questions = [
                f"What are the next stages of AI deployment in {state['topic']}?",
                "Can you provide more details on the main challenges mentioned?",
                "Who are the key organizations leading this initiative?"
            ]
            
    print("\nSuggested Follow-up Questions:")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
        
    time.sleep(2)
    return {"follow_up_questions": questions}

# 3. Routing Edges
def route_after_verifier(state: ResearchState):
    if state.get("verifier_feedback"):
        # Contradictions found - loop back to writer
        print("\n[VERIFICATION FAILED] Routing back to Writer to fix contradictions...")
        return "writer"
    # Success - proceed to critic
    print("\n[VERIFICATION PASSED] Routing to Critic...")
    return "critic"

def route_after_critic(state: ResearchState):
    score = state.get("score", 0.0)
    attempt = state.get("attempt", 0)
    min_score = state.get("min_score", 6.5)
    max_retries = state.get("max_retries", 2)
    
    if score >= min_score or attempt > max_retries:
        print(f"\n[PIPELINE FINISHED] Final Score: {score}/10. Generating follow-ups...")
        return "follow_up"
    print(f"\n[SCORE BELOW THRESHOLD] Score {score}/10 < {min_score}/10. Routing back to Writer...")
    return "writer"

# 4. Pipeline Orchestration
def run_research_pipeline(
    topic: str,
    role: str = "senior academic researcher",
    tone: str = "formal and analytical",
    language: str = "English",
    scrape_top_n: int = 2,
    min_score: float = 6.5,
    max_retries: int = 2,
) -> dict:
    
    # Build Graph
    builder = StateGraph(ResearchState)
    
    # Add Nodes
    builder.add_node("search", search_node)
    builder.add_node("scrape", scrape_node)
    builder.add_node("writer", writer_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("critic", critic_node)
    builder.add_node("follow_up", follow_up_node)
    
    # Add Edges
    builder.add_edge(START, "search")
    builder.add_edge("search", "scrape")
    builder.add_edge("scrape", "writer")
    builder.add_edge("writer", "verifier")
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
            "follow_up": "follow_up"
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
        "follow_up_questions": []
    }
    
    # Execute Graph
    final_state = graph.invoke(initial_state)
    return final_state

if __name__ == "__main__":
    topic = "humans of bihar and ai"
    print(f"\nRunning pipeline for topic: '{topic}'")
    run_research_pipeline(topic)
