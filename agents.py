from langchain.agents import create_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from tools import web_search, scrape_url
from dotenv import load_dotenv
import os
import warnings
from langchain_nvidia_ai_endpoints import ChatNVIDIA, register_model, Model

# Suppress harmless model-type and tool-binding UserWarnings from NVIDIA endpoints library
warnings.filterwarnings("ignore", category=UserWarning, module="langchain_nvidia_ai_endpoints")

load_dotenv()

# Fast Primary LLM for agents & chains
llm = ChatNVIDIA(
  model="nvidia/nemotron-3.5-lightning-30b-a3b",
  api_key=os.getenv("NVIDIA_API_KEY"),
  temperature=0.6,
  max_completion_tokens=3000,
  timeout=60,
  model_kwargs={
      "chat_template_kwargs": {"enable_thinking": True},
      "reasoning_budget": 512  # Streamlined reasoning for fast generation
  }
)

# Ultra-Fast 8B SLM for Truth Guard Fact-Verification
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
from pydantic import BaseModel, Field
from typing import List

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

# Follow-up Questions Agent
follow_up_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an inquisitive research editor. Given a research report on a topic, generate 3 clear, specific, and highly relevant follow-up questions that a user might want to ask next to explore the topic deeper.
    Format your response as a JSON array of strings. Do not include any formatting, markdown code blocks (like ```json), or conversational filler. Output ONLY the JSON array.
    Example output format:
    ["What is the exact timeline for the implementation of the AI CoE in Patna?", "How does the Kisan e-Mitra app assist farmers in Bihar?"]"""),
    ("human", """Topic: {topic}
    
Report:
{report}""")
])

follow_up_chain = follow_up_prompt | llm | StrOutputParser()
