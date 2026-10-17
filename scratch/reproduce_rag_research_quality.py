#!/usr/bin/env python3
"""
Reproduction script for research report quality audit on:
"Under what conditions does retrieval-augmented generation reduce factual hallucinations in large language models, and what evidence demonstrates its limitations?"
"""
import os
import sys
import json
import time
import tempfile

# Force isolated test paths
os.environ["THOTH_DB_PATH"] = "/tmp/thoth_rag_quality_test.db"
os.environ["THOTH_VAULT_DIR"] = "/tmp/thoth_rag_quality_vault"

from backend.memory.db import init_db
from backend.conversation.brief import prepare_research_brief, approve_research_brief
from backend.orchestrator import stream_research_pipeline
from backend.workspace.project import get_project, list_projects
from backend.workspace.manuscript import get_manuscript
from backend.workspace.exporter import export_manuscript

def main():
    print("=== STEP 1: INITIALIZE ISOLATED ENVIRONMENT ===")
    init_db(db_path="/tmp/thoth_rag_quality_test.db")
    os.makedirs("/tmp/thoth_rag_quality_vault", exist_ok=True)

    topic = "Under what conditions does retrieval-augmented generation reduce factual hallucinations in large language models, and what evidence demonstrates its limitations?"
    session_id = f"sess_rag_qual_{int(time.time())}"

    print(f"=== STEP 2: PREPARE & APPROVE RESEARCH BRIEF ===")
    brief = prepare_research_brief(
        session_id=session_id,
        topic=topic,
        hypothesis="RAG reliably reduces hallucinations when retrieved knowledge contains direct factual answers with high relevance, but fails or increases hallucinations when retrieved passages contain distractors or conflicting evidence.",
        objectives=[
            "Identify empirical conditions under which RAG reduces factual hallucinations in LLMs",
            "Evaluate evidence demonstrating RAG limitations, retrieval failure modes, and hallucination propagation",
            "Synthesize comparative findings across benchmark datasets and architectures"
        ],
        selection_criteria=[
            "Empirical evaluations on LLM hallucination benchmarks (e.g., TruthfulQA, HaluEval, RAG benchmarks)",
            "Studies comparing parametric-only vs retrieval-augmented model factual accuracy",
            "Failure analysis of dense/sparse retrieval noise propagation"
        ],
        unresolved_questions=[
            "What is the quantitative threshold of retrieval precision required before hallucination rate increases?",
            "How do parametric vs non-parametric memory conflicts resolve in frontier models?"
        ],
        db_path="/tmp/thoth_rag_quality_test.db"
    )
    brief_id = brief.brief_id
    print(f"Created Brief: {brief_id}")

    ok, approved_brief, msg = approve_research_brief(brief_id, version=brief.version, db_path="/tmp/thoth_rag_quality_test.db")
    print(f"Approved Brief: {ok} (status={approved_brief.approval_status} at {approved_brief.approved_at})")

    print(f"=== STEP 3: EXECUTE RESEARCH PIPELINE ===")
    final_state = {}
    node_events = []
    t0 = time.time()
    for node, update, state in stream_research_pipeline(
        topic=topic,
        brief=approved_brief.to_dict(),
        session_id=session_id,
        db_path="/tmp/thoth_rag_quality_test.db"
    ):
        elapsed = time.time() - t0
        node_events.append((node, elapsed))
        print(f"[{elapsed:6.1f}s] Completed Node: {node}")
        final_state = state

    print(f"\nPipeline finished in {time.time() - t0:.1f}s")
    
    # Extract sources and providers used
    sources = final_state.get("cumulative_sources", [])
    print(f"\nTotal cumulative sources: {len(sources)}")
    provider_counts = {}
    for s in sources:
        p = s.get("source_api", "unknown")
        provider_counts[p] = provider_counts.get(p, 0) + 1
        print(f"  - [{s.get('id')}] ({s.get('source_api')} | quality={s.get('extraction_quality')} | status={s.get('scrape_status')}) {s.get('title')[:70]}")
    print(f"Provider breakdown: {provider_counts}")

    report_text = final_state.get("report", "")
    print(f"\nSynthesis Report Length: {len(report_text)} chars, {len(report_text.split())} words")

    # Extract manuscript and export
    ms_data = final_state.get("manuscript") or {}
    mid = ms_data.get("manuscript_id") or final_state.get("manuscript_id")
    print(f"\nManuscript ID: {mid}")
    if mid:
        ms_full = get_manuscript(mid, db_path="/tmp/thoth_rag_quality_test.db")
        print(f"Manuscript title: {ms_full.get('title') if ms_full else 'N/A'}")
        
        # Export Markdown
        exp_md = export_manuscript(mid, "markdown", db_path="/tmp/thoth_rag_quality_test.db")
        print(f"Exported Markdown length: {len(exp_md.content)} chars")
        
        # Export PDF
        exp_pdf = export_manuscript(mid, "pdf", db_path="/tmp/thoth_rag_quality_test.db")
        pdf_bytes = exp_pdf.binary_bytes
        print(f"Exported PDF size: {len(pdf_bytes) if pdf_bytes else 0} bytes")
        
        # Save raw outputs to disk for detailed inspection
        output_dir = "/Users/shayanazmi/.gemini/antigravity-ide/brain/2022368f-1f46-4371-94ac-55e1274305f1/scratch/rag_quality_inspection"
        os.makedirs(output_dir, exist_ok=True)
        
        with open(f"{output_dir}/synthesis_report.md", "w") as f:
            f.write(report_text)
        with open(f"{output_dir}/exported_manuscript.md", "w") as f:
            f.write(exp_md.content)
        if pdf_bytes:
            with open(f"{output_dir}/exported_manuscript.pdf", "wb") as f:
                f.write(pdf_bytes)
        with open(f"{output_dir}/pipeline_state_meta.json", "w") as f:
            json.dump({
                "topic": topic,
                "node_events": node_events,
                "provider_counts": provider_counts,
                "source_count": len(sources),
                "sources_summary": [
                    {
                        "id": s.get("id"),
                        "title": s.get("title"),
                        "source_api": s.get("source_api"),
                        "url": s.get("url"),
                        "doi": s.get("doi"),
                        "arxiv_id": s.get("arxiv_id"),
                        "extraction_quality": s.get("extraction_quality"),
                        "scrape_status": s.get("scrape_status"),
                    }
                    for s in sources
                ]
            }, f, indent=2)
            
        print(f"\nArtifacts saved to {output_dir}")

if __name__ == "__main__":
    main()
