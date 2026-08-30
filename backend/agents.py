from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from backend.tools import web_search, scrape_url
from dotenv import load_dotenv
import os
import json
import re
import warnings
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
import logging

logger = logging.getLogger("ThothLLM")

# Suppress harmless model-type and tool-binding UserWarnings from NVIDIA endpoints library
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_nvidia_ai_endpoints")

load_dotenv()

class FallbackLLMWrapper(Runnable):
    """Wrapper that invokes primary LLM and falls back to secondary LLM on network/5xx errors."""
    primary_llm: Any
    fallback_llm: Optional[Any]
    primary_name: str
    fallback_name: str

    def __init__(self, primary_llm: Any, fallback_llm: Optional[Any] = None, primary_name: str = "NVIDIA NIM", fallback_name: str = "Fallback Provider"):
        super().__init__()
        self.primary_llm = primary_llm
        self.fallback_llm = fallback_llm
        self.primary_name = primary_name
        self.fallback_name = fallback_name

    def invoke(self, input: Any, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        try:
            res = self.primary_llm.invoke(input, config=config, **kwargs)
            logger.info(f"[LLM Call] Served by primary provider: {self.primary_name}")
            return res
        except Exception as primary_err:
            if self.fallback_llm is not None:
                msg_warn = f"[LLM Call] Primary provider ({self.primary_name}) failed: {primary_err}. Retrying with fallback ({self.fallback_name})..."
                logger.warning(msg_warn)
                print(f"\n[WARNING] {msg_warn}")
                try:
                    res = self.fallback_llm.invoke(input, config=config, **kwargs)
                    msg_fb = f"[LLM Call] Served by fallback provider: {self.fallback_name}"
                    logger.info(msg_fb)
                    print(f"[INFO] {msg_fb}")
                    return res
                except Exception as fallback_err:
                    msg_err = f"[LLM Call] Fallback provider ({self.fallback_name}) also failed: {fallback_err}"
                    logger.error(msg_err)
                    raise fallback_err from primary_err
            else:
                logger.error(f"[LLM Call] Primary provider ({self.primary_name}) failed: {primary_err}. No fallback provider configured.")
                raise primary_err

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackLLMWrapper":
        primary_bound = self.primary_llm.bind_tools(tools, **kwargs) if hasattr(self.primary_llm, "bind_tools") else self.primary_llm
        fallback_bound = self.fallback_llm.bind_tools(tools, **kwargs) if (self.fallback_llm and hasattr(self.fallback_llm, "bind_tools")) else None
        return FallbackLLMWrapper(
            primary_llm=primary_bound,
            fallback_llm=fallback_bound,
            primary_name=self.primary_name,
            fallback_name=self.fallback_name
        )


# Fast Primary LLM for reasoning, drafting & mind map structuring
_primary_llm = ChatNVIDIA(
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

# Ultra-Fast High-Precision SLM for Truth Guard Fact-Verification & Local Q&A
_primary_verifier_llm = ChatNVIDIA(
    model="nvidia/nemotron-3.5-lightning-30b-a3b",
    api_key=os.getenv("NVIDIA_API_KEY"),
    temperature=0.1,  # Strict factual consistency
    max_completion_tokens=2048,
    timeout=60,
    model_kwargs={
        "chat_template_kwargs": {"enable_thinking": False},
    }
)

# Configure Fallback Provider (Groq / OpenAI / OpenAI-Compatible)
groq_key = os.getenv("GROQ_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if groq_key and len(groq_key) > 10 and not groq_key.startswith("dummy"):
    groq_primary_model = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
    _fallback_llm = ChatOpenAI(model=groq_primary_model, api_key=groq_key, base_url="https://api.groq.com/openai/v1", temperature=0.6, timeout=60)
    _fallback_verifier_llm = ChatOpenAI(model="llama-3.1-8b-instant", api_key=groq_key, base_url="https://api.groq.com/openai/v1", temperature=0.1, timeout=30)
    _fb_name = f"Groq ({groq_primary_model})"
elif openai_key and len(openai_key) > 10 and not openai_key.startswith("sk-dummy") and not openai_key.startswith("dummy"):
    _fallback_llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.6, timeout=60)
    _fallback_verifier_llm = ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=0.1, timeout=30)
    _fb_name = "OpenAI"
else:
    _fallback_llm = None
    _fallback_verifier_llm = None
    _fb_name = "None"

llm = FallbackLLMWrapper(primary_llm=_primary_llm, fallback_llm=_fallback_llm, primary_name="NVIDIA-Nemotron-30B", fallback_name=_fb_name)
verifier_llm = FallbackLLMWrapper(primary_llm=_primary_verifier_llm, fallback_llm=_fallback_verifier_llm, primary_name="NVIDIA-Llama-8B", fallback_name=_fb_name)

def get_llm():
    """Returns the configured primary/fallback LLM client."""
    return llm

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

# Pydantic models for structured verification response
class VerificationResult(BaseModel):
    claim: str = Field(description="The claim being verified from the report")
    is_valid: bool = Field(description="True if supported by sources/web search, False if contradicted or unsupported")
    reason_if_failed: str = Field(default="", description="Clear explanation of the contradiction or why it is unsupported; empty if verified")
    supporting_source_id: Optional[str] = Field(default="", description="The exact source identifier (e.g. 'src-...' or '[src-...]') that supports this claim; populated ONLY when is_valid is true, empty string otherwise")

class FactVerificationReport(BaseModel):
    results: List[VerificationResult] = Field(description="List of verification results for all key claims in the report")

# Pydantic model for structured Critic quality evaluation
class CriticScore(BaseModel):
    faithfulness: float = Field(ge=0.0, le=10.0, description="Score out of 10 for factual grounding in sources with no hallucinations")
    relevance: float = Field(ge=0.0, le=10.0, description="Score out of 10 for directly addressing the research topic")
    completeness: float = Field(ge=0.0, le=10.0, description="Score out of 10 for presence and depth of all required sections")
    evidence_quality: float = Field(ge=0.0, le=10.0, description="Score out of 10 for findings backed by traceable real sources")
    clarity_and_coherence: float = Field(ge=0.0, le=10.0, description="Score out of 10 for logical structure and readability")
    overall_score: float = Field(ge=0.0, le=10.0, description="Overall score out of 10, computed as average of all 5 dimensions")
    strengths: List[str] = Field(description="2-3 specific things the report did well")
    areas_to_improve: List[str] = Field(description="2-3 specific actionable improvement suggestions")
    verdict: str = Field(description="One sentence summarizing report quality and readiness")
    reasoning: str = Field(description="Detailed evaluation reasoning behind the assigned scores")

# 3rd Agent: Fact-Verifier SLM Chain (The Truth Guard)
verifier_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the Fact-Verifier Agent (The Truth Guard). Today's date is {current_date}.

Your job is to analyze key factual claims in the drafted research report and verify them against the provided source material.
Each source in the source material is labeled with an explicit identifier like `[src-identifier]` or `Source 1 (src-identifier): ...`.

Rules for Verification:
1. For each key claim in the report, determine if it is VERIFIED (is_valid: true) or CONTRADICTED/FABRICATED (is_valid: false).
2. Directly Supported Facts & Empirical Numbers: Must directly match the source material. Specify the exact `supporting_source_id` (e.g. "src-arxiv_1311_2485" or "src-brave_aa1").
3. Plausible Logical Inferences & Domain Synthesis: High-level logical deductions that naturally synthesize findings without inventing false data (e.g. "Translating multi-omics pipelines to clinical practice requires prospective cohort trials") should be marked `is_valid: true` attributed to the primary related source ID.
4. Hard Contradictions & Fabricated Specifics: If a claim invents non-existent trial names, falsifies specific statistics/percentages, or directly contradicts source material, mark `is_valid: false`, set `supporting_source_id` to "", and provide a clear explanation in `reason_if_failed`.

Output strictly valid JSON matching this schema:
{{
  "results": [
    {{
      "claim": "The claim being verified",
      "is_valid": true,
      "reason_if_failed": "",
      "supporting_source_id": "src-exact_source_id"
    }}
  ]
}}

Output ONLY the JSON object, with NO markdown code block or backticks."""),
    ("human", """Source Material:
{sources}

Drafted Report to Verify:
{report}

Perform the factual verification audit now.""")
])

verifier_chain = verifier_prompt | verifier_llm | StrOutputParser()

def build_verifier_agent():
    """Helper returning verifier_chain for backward compatibility."""
    return verifier_chain

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

# Critic Chain (LLM-as-a-Judge with Structured JSON Output)
critic_parser = JsonOutputParser(pydantic_object=CriticScore)

critic_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a rigorous research quality evaluator (LLM-as-a-Judge).

Score the report across these 5 dimensions, each out of 10:
- **faithfulness** (10): Are all claims grounded in the source data? No hallucinations?
- **relevance** (10): Does the report directly address the research topic?
- **completeness** (10): Are all required sections present and sufficiently detailed?
- **evidence_quality** (10): Are findings backed by traceable, real sources?
- **clarity_and_coherence** (10): Is the writing logical, well-structured, and readable?

Compute overall_score as the average of all 5 dimensions (out of 10).

{format_instructions}"""),
    ("human", """Topic: {topic}

Report to evaluate:
{report}

Evaluate the report now.""")
]).partial(format_instructions=critic_parser.get_format_instructions())

critic_chain = critic_prompt | llm | StrOutputParser()

# Follow-up Questions Generator Chain
follow_up_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an inquisitive research editor and strategic thought partner.
Given a topic, synthesis/answer, and recent dialogue, generate 3 high-impact, forward-thinking follow-up questions or actions that help the user explore the most important next steps.

Rules:
1. Make them specific, actionable, and forward-looking (e.g. comparing alternatives, investigating bottlenecks, analyzing empirical trade-offs, or exploring real-world deployment).
2. Avoid generic questions like "Would you like to know more?" or "Can you provide more details?".
3. Output ONLY a valid JSON array of 3 strings. Do NOT include markdown code fences (```json) or conversational commentary.
Example:
["Research empirical trade-offs against alternative architectures", "Compare scaling bottlenecks with recent hardware benchmarks", "What are the primary operational constraints for real-world deployment?"]"""),
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
    ("system", """You are Thoth, an autonomous scientific intelligence and research thought partner.
Answer the user's follow-up question accurately using the provided Research context, synthesis report, and prior dialogue.

Rules:
1. Provide a direct, well-structured, and rigorous answer.
2. Ground your claims in the provided knowledge base and cited sources.
3. If the user challenges a conclusion or asks for counterarguments/limitations, critically inspect the assumptions, highlight alternative interpretations from the literature, and specify the weakest empirical links.
4. If the knowledge base does not contain sufficient details to answer fully, state what is known and specify the exact research question required to resolve the gap.
5. Keep the tone insightful, intellectually honest, and concise.
6. Output ONLY the clean answer without internal chain-of-thought tags, reasoning monologues, or repetitive meta-commentary."""),
    ("human", """Topic: {topic}

Context / Knowledge Base:
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

Rules:
1. Write the new or updated section in clean markdown format.
2. Include a clear section heading (e.g. `### Section Title`), evidence-grounded paragraphs, and source links.
3. Do NOT repeat the entire report; generate only the focused section to be appended or merged.
4. CRITICAL: Do NOT include internal monologue, chain-of-thought, reasoning steps, or preamble like "Let me outline...", "I will write...", "The full prior report...". Output ONLY the final markdown section starting immediately with the section heading."""),
    ("human", """Original Topic: {topic}

Follow-Up Request:
{user_query}

Research Evidence:
{research_data}

Current Report Overview:
{report_overview}

Draft the section expansion now. Start immediately with the `### ` heading.""")
])

report_expander_chain = report_expander_prompt | llm | StrOutputParser()

# Direct conversational chat prompt for greetings, meta questions, and fast conversational Q&A
direct_chat_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Thoth (Djehuty), the ancient Egyptian deity of wisdom, truth, mathematics, and writing, operating as an autonomous multi-agent research intelligence.
- For greetings or casual conversation, respond with dignity, warmth, and concise elegance in 2-3 sentences.
- Inform the user that you are ready to conduct deep, verified autonomous research on any scientific, technical, or humanities topic.
- Offer 2-3 specific example research topics they can ask you to investigate (e.g., Quantum Error Correction, CRISPR Prime Editing, LLM Alignment).
- Keep responses concise, direct, and free of fluff or artificial filler."""),
    ("human", "{user_query}")
])

direct_chat_chain = direct_chat_prompt | verifier_llm | StrOutputParser()




def strip_chain_of_thought(text: Any) -> str:
    """Removes <think> tags, reasoning traces, and preamble from LLM responses."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = getattr(text, "content", str(text))
    if not text:
        return ""
    # Strip <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL).strip()
    
    # If the text has reasoning preamble before the actual markdown title (e.g. "Let's do it.", "I'll draft...", etc.)
    # and contains a heading like "### " or "## " or "# "
    match = re.search(r"(?m)^(#{1,4}\s+.+)$", cleaned)
    if match and match.start() > 0:
        preamble = cleaned[:match.start()].strip()
        meta_phrases = ["let me", "i need to", "i will", "the user wants", "i should", "let's do", "let draft", "i'll draft", "i'll write", "structure:"]
        if any(phrase in preamble.lower() for phrase in meta_phrases):
            cleaned = cleaned[match.start():].strip()

    return cleaned


# Helper function to parse JSON safely
def safe_extract_json(raw_text: Any, default: Any = None) -> Any:
    """Extracts JSON object or array from LLM response safely, removing thinking tokens & markdown codeblocks."""
    if raw_text is None:
        return default
    if isinstance(raw_text, (dict, list)):
        return raw_text
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    text = raw_text.strip()
    if not text:
        return default

    # 1. Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Check for markdown code fence contents
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        fenced_content = fence_match.group(1).strip()
        try:
            return json.loads(fenced_content)
        except Exception:
            pass

    # 3. Clean raw markdown code block tags if unbalanced
    cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 4. Extract first outermost JSON object {...} or array [...]
    try:
        start_brace = cleaned.find('{')
        end_brace = cleaned.rfind('}')
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            return json.loads(cleaned[start_brace:end_brace+1])
    except Exception:
        pass

    try:
        start_bracket = cleaned.find('[')
        end_bracket = cleaned.rfind(']')
        if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
            return json.loads(cleaned[start_bracket:end_bracket+1])
    except Exception:
        pass

    # 5. Salvage complete objects from truncated/unclosed JSON arrays
    try:
        start_bracket = cleaned.find('[')
        if start_bracket != -1:
            obj_matches = re.findall(r"(\{[^{}]+\})", cleaned[start_bracket:])
            if obj_matches:
                salvaged = []
                for obj_str in obj_matches:
                    try:
                        salvaged.append(json.loads(obj_str))
                    except Exception:
                        pass
                if salvaged:
                    return {"results": salvaged} if any("claim" in p for p in salvaged) else salvaged
    except Exception:
        pass

    return default
