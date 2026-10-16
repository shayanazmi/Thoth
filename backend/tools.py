from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool(description="")
def web_search(query: str) -> str:
    results = tavily.search(query=query, search_depth="advanced", max_results=5)
    return "\n------\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('content', '')[:300]}..."
        for r in results.get("results", [])
    )

from backend.ingestion import ingest_document, IngestionResult

def _scrape_url_with_retry(url: str) -> str:
    res = ingest_document(url)
    if res.status == "success":
        return res.text
    elif res.status == "empty":
        return ""
    else:
        err = res.error_message or "Unknown extraction failure"
        return f"Could not scrape URL: {err}"

def scrape_url_structured(url: str, max_chars: int = 15000) -> IngestionResult:
    """
    Structured scraping interface returning the complete IngestionResult,
    preserving content_type, num_pages, char_count, is_truncated, passages,
    extraction_quality, extraction_method, and extraction_warnings.
    """
    return ingest_document(url, max_chars=max_chars)

@tool(description="Scrapes and extracts readable text from web pages and scholarly PDF documents.")
def scrape_url(url: str) -> str:
    try:
        return _scrape_url_with_retry(url)
    except Exception as e:
        return f"Could not scrape URL: {str(e)}"
