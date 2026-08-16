from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from tools import web_search, scrape_url
from dotenv import load_dotenv
import os
import json
import re
import warnings
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Suppress harmless model-type and tool-binding UserWarnings from NVIDIA endpoints library
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_nvidia_ai_endpoints")

load_dotenv()

# Fast Primary LLM for reasoning, drafting & mind map structuring
llm = ChatNVIDIA(
    model="nvidia/nemotron-3.5-lightning-30b-a3b",
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=0.6,
    max_completion_tokens=8192,
    timeout=120,
    model_kwargs={
        "chat_template_kwargs": {"enable_thinking": True},
        "reasoning_budget": 512  # Streamlined reasoning for fast generation
    }
)

# Ultra-Fast 8B SLM for Truth Guard Fact-Verification & Local Q&A
verifier_llm = ChatNVIDIA(
    model="meta/llama-3.1-8b-instruct",
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=0.1,  # Strict factual consistency
    max_completion_tokens=1024,
    timeout=60,
)

# 1st Agent: Web Search Expert
def build_search_agent():
    import datetime
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    return create_agent(
        model=llm,
        tools=[web_search],
        system_prompt=(
            f"You are a search expert. Today's date is {current_date}. "
            "When searching for recent information, structure your queries to target the current year or relevant range."
        )
    )

# 2nd Agent: Reader Scraping Agent
def build_render_agent():
    return create_agent(
        model=llm,
        tools=[scrape_url]
    )

# Pydantic models for structured verification response
class VerificationResult(BaseModel):
    claim: str = Field(description="The claim being verified from the report")
    is_valid: bool = Field(description="True if supported by sources/web search, False if contradicted or unsupported")
    reason_if_failed: str = Field(description="Clear explanation of the contradiction or why it is unsupported; empty if verified")

class FactVerificationReport(BaseModel):
    results: List[VerificationResult] = Field(description="List of verification results for all key claims in the report")

# 3rd Agent: Fact-Verifier SLM Agent (The Truth Guard)
def build_verifier_agent():
    import datetime
    current_date = datetime.datetime.now().strftime("%B %d, %Y")
    return create_agent(
        model=verifier_llm,
        tools=[web_search],
        response_format=FactVerificationReport,
        system_prompt=(
            f"You are the Fact-Verifier Agent (The Truth Guard). Today's date is {current_date}.\n\n"
            "Your job is to analyze claims in the drafted research report and verify them against either the scraped local text or by using the web_search tool to look up live facts.\n"
            "For each claim, determine if it is VERIFIED (is_valid: true) or CONFLATED/UNSUPPORTED (is_valid: false).\n"
            "If any facts are wrong (like mixing up different people with the same name, or claiming someone holds a job/degree they do not), flag it as a contradiction (is_valid: false) and explain why."
        )
    )

# Writer Chain
writer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a {role}. Write in a {tone} tone and respond in {language}. Today's date is {current_date}.
 
Given raw web research data, produce a structured research report with these sections:
- **Introduction**: What the topic is and why it matters.
- **Key Findings**: At least 2 well-explained findings backed by the research.
- **Knowledge Gaps**: Gaps in current literature, each with a suggested search string to investigate further.
- **Methodology**: How the research was gathered and assessed.
- **Conclusion**: Key takeaways and actionable insights.
- **Sources**: Numbered list of all URLs from the research data. Do not fabricate sources.
 
Be evidence-based and do not skip any section."""),
    ("human", """Topic: {topic}
 
Research Data:
{research}
 
Write the research report.""")
])
 
writer_chain = writer_prompt | llm | StrOutputParser()

# Critic Chain (LLM-as-a-Judge)
critic_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a rigorous research quality evaluator (LLM-as-a-Judge).

Score the report across these 5 dimensions, each out of 10:
- **Faithfulness** (10): Are all claims grounded in the source data? No hallucinations?
- **Relevance** (10): Does the report directly address the research topic?
- **Completeness** (10): Are all required sections present and sufficiently detailed?
- **Evidence Quality** (10): Are findings backed by traceable, real sources?
- **Clarity & Coherence** (10): Is the writing logical, well-structured, and readable?

Compute: Overall Score = average of all 5 dimensions (out of 10).

Your response must follow this structure:

**Scores**
| Dimension | Score /10 |
|---|---|
| Faithfulness | X |
| Relevance | X |
| Completeness | X |
| Evidence Quality | X |
| Clarity & Coherence | X |
| **Overall** | **X.X** |

**Strengths**
- [2-3 specific things the report did well]

**Areas to Improve**
- [2-3 specific, actionable suggestions]

**Verdict**
[One sentence summarising the report's quality and readiness]"""),
    ("human", """Topic: {topic}

Report to evaluate:
{report}

Evaluate the report now.""")
])

critic_chain = critic_prompt | llm | StrOutputParser()

# Follow-up Questions Generator Chain
follow_up_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an inquisitive research editor. Given a research report on a topic and any recent conversation turns, generate 3 clear, concise, and highly relevant follow-up questions that a user might want to click next to explore deeper.
Format your response as a JSON array of 3 strings. Do NOT include markdown blocks (```json) or conversational commentary.
Example output format:
["What are the primary computational bottlenecks of this architecture?", "How does this compare with the latest 2026 benchmarks?", "What are the practical deployment steps?"]"""),
    ("human", """Topic: {topic}
    
Report:
{report}

Recent Context / Questions:
{recent_context}""")
])

follow_up_chain = follow_up_prompt | llm | StrOutputParser()

# --- Mind Map Extractor Chain (Co-STORM Style Hierarchical Concept Graph) ---
mindmap_extractor_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert knowledge graph architect. Your job is to extract an intuitive, hierarchical concept graph (Mind Map) from a research report.

The graph consists of:
1. Root node: Type 'topic' (The main research theme).
2. Sub-topic nodes: Type 'subtopic' (3-5 core themes/sections from the report).
3. Finding nodes: Type 'finding' (1-2 key facts/evidence nuggets under each subtopic).
4. Source nodes: Type 'source' (Domain/URL where findings were discovered).

Output strictly valid JSON with this exact schema:
{{
  "nodes": [
    {{"id": "node_0", "label": "Topic Name", "type": "topic", "details": "Brief summary", "group": "topic"}},
    {{"id": "node_1", "label": "Sub-theme Title", "type": "subtopic", "details": "Explanation", "group": "subtopic"}},
    {{"id": "node_2", "label": "Key Finding Title", "type": "finding", "details": "Detailed verified claim", "url": "https://...", "group": "finding"}},
    {{"id": "node_3", "label": "Source: domain.com", "type": "source", "url": "https://...", "group": "source"}}
  ],
  "edges": [
    {{"from": "node_0", "to": "node_1", "label": "explores"}},
    {{"from": "node_1", "to": "node_2", "label": "evidence"}},
    {{"from": "node_2", "to": "node_3", "label": "cited_in"}}
  ]
}}

Ensure all node IDs are unique strings. Ensure all edges connect existing node IDs.
Output ONLY the JSON object, with NO markdown code block or backticks."""),
    ("human", """Topic: {topic}

Report:
{report}

Extracted Sources:
{sources}""")
])

mindmap_extractor_chain = mindmap_extractor_prompt | llm | StrOutputParser()

# --- Follow-Up Intent Router Chain ---
router_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an autonomous Research Query Router.
Analyze the user's follow-up request against the existing research mind map and report to choose the most efficient execution path.

Choose ONE of the following 3 routes:
1. "LOCAL_QA": The question can be answered completely and accurately from the existing report and Mind Map findings. (Fastest, 0 web search needed).
2. "WEB_SEARCH": The question asks for new information, specific stats, latest updates, entities, or topics NOT covered in the current report/mindmap. (Triggers 1 focused web probe).
3. "REPORT_EXPANSION": The user explicitly wants to add a new section, revise, or expand the master Synthesis Report itself.

Respond with ONLY a JSON object formatted as follows:
{{
  "route": "LOCAL_QA" | "WEB_SEARCH" | "REPORT_EXPANSION",
  "reasoning": "One concise sentence explaining the routing decision",
  "search_query": "If WEB_SEARCH, the exact single targeted search query to execute; otherwise empty string"
}}
Output NO markdown code blocks, backticks, or extra commentary."""),
    ("human", """Topic: {topic}

Mind Map Summary:
{mindmap_summary}

Report Summary:
{report_summary}

User Follow-Up Query:
{user_query}""")
])

router_chain = router_prompt | verifier_llm | StrOutputParser()

# --- Mind Map Grounded Q&A Chain ---
mindmap_qa_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Thoth's conversational research assistant.
Answer the user's follow-up question accurately using the provided Research Mind Map context, synthesis report, and prior conversation history.

Rules:
1. Provide a direct, well-structured, and clear answer.
2. Ground your claims in the provided knowledge base. If citing a source or URL from the context, include a clickable markdown link: `[Source Name](URL)`.
3. If the knowledge base does not contain sufficient details to answer fully, answer what is known and state the remaining knowledge gap.
4. Keep the tone academic, insightful, and concise."""),
    ("human", """Topic: {topic}

Context / Mind Map Sub-Tree:
{context}

Conversation History / Summary:
{history_summary}

User Question:
{user_query}""")
])

mindmap_qa_chain = mindmap_qa_prompt | llm | StrOutputParser()

# --- Mind Map Updater Chain (For Merging Follow-up Mini-Researches) ---
mindmap_updater_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Knowledge Graph Editor. Given an existing Mind Map JSON and new mini-research findings from a follow-up probe, update the Mind Map JSON.

Rules:
1. Keep all existing valid nodes and edges.
2. Add a new 'followup' or 'finding' sub-branch connected to the relevant subtopic or root topic.
3. If new URLs were discovered, add 'source' nodes and connect them with 'cited_in' edges.
4. Maintain unique node IDs (e.g. use prefix 'fu_node_1', 'fu_node_2', etc.).
5. Output ONLY the updated JSON object with "nodes" and "edges" keys. No markdown backticks or commentary."""),
    ("human", """Existing Mind Map JSON:
{existing_mindmap_json}

Follow-Up Query:
{followup_query}

New Mini-Research Findings:
{new_research}""")
])

mindmap_updater_chain = mindmap_updater_prompt | llm | StrOutputParser()

# --- Rolling Conversation Summarizer Chain ---
summarizer_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a research conversation compressor. Condense the previous dialogue history into a dense, high-signal bulleted summary of key facts established, user queries asked, and insights discovered.
Keep the summary under 200 words. Do not drop key domain entities, names, or source URLs."""),
    ("human", """Existing Summary:
{existing_summary}

Recent Conversation Turns to Incorporate:
{recent_turns}""")
])

conversation_summarizer_chain = summarizer_prompt | verifier_llm | StrOutputParser()

# --- Report Section Expander Chain ---
report_expander_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an academic research editor.
The user wants to expand or add a new section to the master Synthesis Report based on their follow-up request and new research data.

Write the new or updated section in markdown format.
Include clear heading (e.g. `### Section Title`), evidence-backed paragraphs, and source links.
Do not repeat the entire report; generate the focused section to be appended or merged."""),
    ("human", """Original Topic: {topic}

Follow-Up Request:
{user_query}

Research Evidence:
{research_data}

Current Report Overview:
{report_overview}

Draft the section expansion now.""")
])

report_expander_chain = report_expander_prompt | llm | StrOutputParser()


# Helper function to parse JSON safely
def safe_extract_json(raw_text: str, default: Any = None) -> Any:
    """Extracts JSON object or array from LLM response safely, removing markdown codeblocks."""
    if not raw_text:
        return default
    text = raw_text.strip()
    # Remove markdown code blocks
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        # Try finding the first '{' and last '}' or '[' and ']'
        try:
            start_bracket = text.find('[')
            end_bracket = text.rfind(']')
            if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
                return json.loads(text[start_bracket:end_bracket+1])
            
            start_brace = text.find('{')
            end_brace = text.rfind('}')
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                return json.loads(text[start_brace:end_brace+1])
        except Exception:
            pass
    return default

