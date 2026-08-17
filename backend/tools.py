# pyrefly: ignore[missing-import]
from langchain.tools import tool
import requests
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os 
from dotenv import load_dotenv
from rich import print

load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

@tool 
def web_search(query :str) -> str:
    """Perform web search using Tavily and return the results."""
    results = tavily.search(query=query, search_depth="advanced", max_results=5)
    
    out = []
    for r in results['results']:
        out.append(
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Snippet: {r['content'][:300]}...\n"
        )
    return "\n------\n".join(out)

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

if __name__ == "__main__":
    print(scrape_url.invoke("https://www.nature.com/subjects/computational-science"))
