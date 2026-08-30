from langchain.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os 
from dotenv import load_dotenv

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool 
def web_search(query: str) -> str:
    """Perform web search using Tavily and return the results."""
    results = tavily.search(query=query, search_depth="advanced", max_results=5)
    return "\n------\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('content', '')[:300]}..."
        for r in results.get("results", [])
    )

from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=1, max=5),
    reraise=True
)
def _scrape_url_with_retry(url: str) -> str:
    resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    if resp.status_code in (429, 503):
        raise requests.exceptions.RequestException(f"HTTP {resp.status_code} Rate Limited/Unavailable")
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:3000]

@tool
def scrape_url(url: str) -> str:
    """Scrape and return clean text content from a given URL for deeper reading."""
    try:
        return _scrape_url_with_retry(url)
    except Exception as e:
        return f"Could not scrape URL: {str(e)}"
