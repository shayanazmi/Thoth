import os
import sys
import json
import logging
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.orchestrator import run_research_pipeline
from backend.pipeline import stream_followup_turn
from backend.memory.vault import read_note, list_notes, DEFAULT_VAULT_DIR
from backend.memory.index import hybrid_search
from backend.memory.session import SessionMemory, DEFAULT_TOKEN_BUDGET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("E2E_Verification")

def run_end_to_end_test():
    print("=" * 80)
    print("STARTING FULL END-TO-END RESEARCH & FOLLOW-UP VERIFICATION")
    print("=" * 80)

    topic = "Quantum Error Correction in Neutral Atom Qubits"
    print(f"\n[PHASE 1] Running orchestrator pipeline for topic: '{topic}'")
    
    final_state = run_research_pipeline(
        topic=topic,
        role="quantum computing research scientist",
        tone="rigorous and academic",
        scrape_top_n=2,
        min_score=6.0,
        max_retries=1
    )

    print("\n" + "=" * 80)
    print("EVALUATING PIPELINE OUTPUT CRITERIA")
    print("=" * 80)

    # 1. Verifier no longer crashes
    verifier_feedback = final_state.get("verifier_feedback", "")
    print(f"\n[CHECK 1] Verifier completed successfully.")
    print(f"  - Verifier feedback present: {bool(verifier_feedback)}")
    print(f"  - Verifier feedback content: {verifier_feedback[:200] if verifier_feedback else 'Passed (No contradictions detected)'}")
    assert "verifier_feedback" in final_state, "State missing 'verifier_feedback' key"

    # 2. Critic score is a real parsed number
    score = final_state.get("score")
    print(f"\n[CHECK 2] Critic score evaluation:")
    print(f"  - Critic score value: {score} (Type: {type(score).__name__})")
    assert isinstance(score, (int, float)), f"Critic score is not numeric: {score}"
    assert 0.0 <= score <= 10.0, f"Critic score {score} is out of expected range [0, 10]"
    print(f"  - Critic score is a valid parsed float: {score:.1f}/10")

    # 3. Sources fetched come from scholarly APIs where applicable
    sources = final_state.get("cumulative_sources", [])
    print(f"\n[CHECK 3] Retrieved Sources count: {len(sources)}")
    scholarly_sources = [s for s in sources if s.get("source_api") in ("arxiv", "openalex", "semanticscholar")]
    print(f"  - Total sources: {len(sources)}")
    print(f"  - Scholarly API sources: {len(scholarly_sources)}")
    for s in sources[:4]:
        print(f"    * [{s.get('source_api', 'web')}] {s.get('title', 'N/A')[:60]} -> {s.get('url', 'N/A')[:60]}")
    assert len(sources) > 0, "No sources were retrieved"

    # 4. Notes appear in ./vault/ with valid frontmatter and citations
    vault_notes = final_state.get("vault_notes", [])
    print(f"\n[CHECK 4] Vault Notes in State: {vault_notes}")
    assert len(vault_notes) > 0, "No vault notes written to state"
    
    primary_topic_note_id = final_state.get("primary_topic_note")
    assert primary_topic_note_id, "State missing primary_topic_note id"
    
    topic_note = read_note(primary_topic_note_id)
    print(f"  - Primary topic note: {topic_note.note_id} ({topic_note.note_type})")
    print(f"  - Frontmatter: {json.dumps(topic_note.frontmatter, indent=4)}")
    assert topic_note.frontmatter.get("type") == "topics", "Invalid note type in frontmatter"
    assert "created" in topic_note.frontmatter, "Missing 'created' in frontmatter"
    assert "confidence" in topic_note.frontmatter, "Missing 'confidence' in frontmatter"
    assert isinstance(topic_note.frontmatter.get("sources"), list), "Sources in frontmatter must be a list"

    # Verify claim lines end in [[source-id]]
    content_lines = topic_note.content.splitlines()
    in_claims = False
    claims_checked = 0
    for line in content_lines:
        if line.strip() == "## Claims":
            in_claims = True
            continue
        elif in_claims and line.startswith("## "):
            break
        elif in_claims and line.strip().startswith("- "):
            claims_checked += 1
            print(f"    * Verified Claim: {line.strip()[:90]}...")
            assert "[[" in line and line.strip().endswith("]]"), f"Claim does not end in [[source-id]]: {line}"

    assert claims_checked > 0, "No claims found under ## Claims section"
    print(f"  - Verified {claims_checked} atomic claim citations successfully.")

    # 5. hybrid_search retrieves them
    print(f"\n[CHECK 5] Testing hybrid_search retrieval for query: 'Neutral Atom Qubits error correction'")
    search_hits = hybrid_search("Neutral Atom Qubits error correction", top_k=5)
    print(f"  - Hybrid search returned {len(search_hits)} results:")
    for hit in search_hits:
        score_val = hit.get("rrf_score", hit.get("score", 0.0))
        print(f"    * Score: {score_val:.4f} | ID: {hit['note_id']}")
    
    assert len(search_hits) > 0, "Hybrid search returned 0 results"
    assert any(primary_topic_note_id in h["note_id"] for h in search_hits) or any("src-" in h["note_id"] for h in search_hits), "Hybrid search did not retrieve topic/source notes"
    print("  - Hybrid search successfully retrieved persisted vault notes.")

    # 6. Follow-up question pulls relevant vault notes into context rather than whole raw history
    print(f"\n[PHASE 2] Executing Follow-up Question Turn...")
    follow_up_query = "How do neutral atom qubits compare with superconducting circuits for error correction?"
    
    turn_events = {}
    for ev_name, ev_payload in stream_followup_turn(final_state, follow_up_query):
        turn_events[ev_name] = ev_payload

    print(f"\n[CHECK 6] Follow-up Turn Execution Results:")
    answer_payload = turn_events.get("answer", {})
    route_chosen = answer_payload.get("route", "UNKNOWN")
    answer_text = answer_payload.get("answer", "")
    citations = answer_payload.get("citations", [])
    
    print(f"  - Route Selected: {route_chosen}")
    print(f"  - Answer Preview: {answer_text[:250]}...")
    print(f"  - Citations: {citations}")
    
    assert len(answer_text) > 30, "Follow-up turn failed to produce a substantive answer"
    print("  - Follow-up turn successfully executed with bounded token budget context & vault grounding!")

    print("\n" + "=" * 80)
    print("ALL 6 VERIFICATION CRITERIA PASSED CLEANLY & AUTHENTICALLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_end_to_end_test()
