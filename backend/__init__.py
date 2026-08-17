"""
Thoth Backend Package
====================
Exposes the multi-agent research graph engine, agent chains, and live search/scrape tools.
"""

from backend.tools import web_search, scrape_url
from backend.agents import (
    build_search_agent,
    build_verifier_agent,
    verifier_chain,
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
    safe_extract_json,
)
from backend.pipeline import (
    ResearchState,
    stream_research_pipeline,
    stream_followup_turn,
)
from backend.orchestrator import create_initial_state
from backend.dispatcher import Dispatcher, CircuitBreakerOpenError
from backend.scholarly import (
    SourceCandidate,
    search_arxiv,
    search_semantic_scholar,
    search_openalex,
    search_tavily,
    search_scholarly_sources,
)

__all__ = [
    "web_search",
    "scrape_url",
    "build_search_agent",
    "build_verifier_agent",
    "verifier_chain",
    "writer_chain",
    "critic_chain",
    "CriticScore",
    "follow_up_chain",
    "mindmap_extractor_chain",
    "router_chain",
    "mindmap_qa_chain",
    "mindmap_updater_chain",
    "conversation_summarizer_chain",
    "report_expander_chain",
    "safe_extract_json",
    "ResearchState",
    "stream_research_pipeline",
    "stream_followup_turn",
    "create_initial_state",
    "Dispatcher",
    "CircuitBreakerOpenError",
    "SourceCandidate",
    "search_arxiv",
    "search_semantic_scholar",
    "search_openalex",
    "search_tavily",
    "search_scholarly_sources",
]
