"""
Thoth · Agentic Research Command Center & Verification Studio
============================================================
A clean, robust Streamlit interface for launching, verifying, and testing the
Thoth multi-agent autonomous research engine, Obsidian memory vault, and SQLite persistence.
"""

import os
import sys
import time
import json
import subprocess
import streamlit as st

# Ensure project root is in sys.path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from frontend.ui_adapter import (
    ResearchPipelineRunner,
    NODE_ORDER,
    NODE_LABEL_MAP,
    list_stored_sessions,
    list_stored_reports,
    get_stored_report_by_id,
    search_memory_vault,
    list_vault_notes,
    read_vault_note,
    traverse_vault_graph,
    get_telemetry_status,
)

# ------------------------------------------------------------------------------
# 1. Page Configuration
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Thoth · Agentic Research Engine",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------------------------------------------------------------------
# 2. Session State Initialization
# ------------------------------------------------------------------------------
if "runner" not in st.session_state:
    st.session_state.runner = ResearchPipelineRunner()

runner: ResearchPipelineRunner = st.session_state.runner

if "topic_input" not in st.session_state:
    st.session_state.topic_input = "Quantum Error Correction in Neutral Atom Qubits 2026"

if "final_state" not in st.session_state:
    st.session_state.final_state = {}
    try:
        from backend.memory.db import get_latest_report
        latest_rep = get_latest_report()
        if latest_rep:
            st.session_state.final_state = {
                "topic": latest_rep.get("topic", ""),
                "report": latest_rep.get("content", ""),
                "score": latest_rep.get("score", 0.0),
                "verifier_feedback": latest_rep.get("verifier_feedback", ""),
                "mindmap": latest_rep.get("mindmap", {})
            }
            if latest_rep.get("topic"):
                st.session_state.topic_input = latest_rep.get("topic")
    except Exception:
        pass

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "selected_vault_note" not in st.session_state:
    st.session_state.selected_vault_note = ""

# Synchronize runner state
if runner.is_running() or runner.is_completed or runner.followup_completed:
    if runner.final_state:
        st.session_state.final_state.update(runner.final_state)

    f_payload = runner.consume_followup_payload()
    if f_payload:
        q_title = f_payload.get("user_query", "Follow-up")
        st.session_state.chat_history.append({
            "role": "agent",
            "text": f_payload.get("answer", ""),
            "route": f_payload.get("route", "LOCAL_QA"),
            "citations": f_payload.get("citations", []),
            "query_title": q_title[:30]
        })
        if "mindmap" in f_payload and f_payload["mindmap"]:
            st.session_state.final_state["mindmap"] = f_payload["mindmap"]
        if "cumulative_sources" in f_payload and f_payload["cumulative_sources"]:
            st.session_state.final_state["cumulative_sources"] = f_payload["cumulative_sources"]
        if "follow_up_questions" in f_payload and f_payload["follow_up_questions"]:
            st.session_state.final_state["follow_up_questions"] = f_payload["follow_up_questions"]
        if f_payload.get("route") == "REPORT_EXPANSION" and "report" in f_payload:
            st.session_state.final_state["report"] = f_payload["report"]


# ------------------------------------------------------------------------------
# 3. Sidebar Navigation & Scope Controls
# ------------------------------------------------------------------------------
with st.sidebar:
    st.title("✦ THOTH")
    st.caption("Autonomous Multi-Agent Research Platform")
    st.divider()

    st.subheader("⚙ Research Scope")
    scribe_role = st.selectbox(
        "Target Persona",
        ["Senior Academic Researcher", "Technical Copywriter", "Financial Analyst", "Staff Software Engineer"],
        index=0
    )
    scribe_tone = st.selectbox(
        "Tone",
        ["Formal & Analytical", "Informative & Casual", "Executive Summary", "Investigative & In-Depth"],
        index=0
    )
    scribe_depth = st.slider("Primary Sources Scrape Depth", min_value=1, max_value=15, value=5)
    scribe_score = st.slider("Min Quality Gate Threshold", min_value=5.0, max_value=9.0, value=6.5, step=0.5)
    scribe_retries = st.selectbox("Max Critic Retries", [1, 2, 3], index=1)

    st.divider()
    telemetry = get_telemetry_status()
    cb_state = telemetry.get("circuit_breaker_state", "CLOSED")
    st.markdown(f"**Circuit Breaker:** `{cb_state}`")
    st.markdown(f"**Primary LLM:** `{telemetry.get('primary_provider')}`")
    st.markdown(f"**Fallback LLM:** `{telemetry.get('fallback_provider')}`")
    st.markdown(f"**Vault Notes:** `{telemetry.get('vault_notes_count', 0)}`")
    st.markdown(f"**DB Size:** `{telemetry.get('db_size_kb', 0)} KB`")


# ------------------------------------------------------------------------------
# 4. Main Tabs Navigation
# ------------------------------------------------------------------------------
tab_lab, tab_constellation, tab_vault, tab_history, tab_diagnostics = st.tabs([
    "✦ Research Lab",
    "✧ Concept Graph",
    "🗄 Memory Vault",
    "📜 Codex History",
    "⚙ Diagnostics & Telemetry"
])


# ==============================================================================
# TAB 1: RESEARCH LAB
# ==============================================================================
with tab_lab:
    st.header("✦ Deep Research Laboratory")
    st.write("Submit an inquiry to orchestrate autonomous multi-agent search, full-text scraping, verified drafting, SLM fact-checking, and concept mapping.")

    # Preset Topic Buttons
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        if st.button("⚛ Quantum Error Correction 2026", use_container_width=True):
            st.session_state.topic_input = "Quantum Error Correction in Neutral Atom Qubits 2026"
            st.rerun()
    with col_p2:
        if st.button("🤖 Agentic AI Reasoning Benchmarks", use_container_width=True):
            st.session_state.topic_input = "State of Agentic AI Reasoning Benchmarks and Multi-Agent Orchestration 2026"
            st.rerun()
    with col_p3:
        if st.button("🔋 Solid-State Battery Breakthroughs", use_container_width=True):
            st.session_state.topic_input = "Next-Generation Solid-State Battery Electrolytes and Commercial Milestones"
            st.rerun()

    query = st.text_area(
        "Research Objective / Topic",
        value=st.session_state.topic_input,
        height=85,
        placeholder="Enter a research topic, technical hypothesis, or question..."
    )

    col_b1, col_b2 = st.columns([4, 1])
    with col_b1:
        start_btn = st.button(
            "✦ Launch Research Cycle",
            type="primary",
            use_container_width=True,
            disabled=runner.is_running()
        )
    with col_b2:
        cancel_btn = st.button("Halt", use_container_width=True, disabled=not runner.is_running())

    if cancel_btn:
        runner.cancel()
        st.warning("Cancellation signal sent to pipeline.")

    if start_btn:
        if not query.strip():
            st.error("Please enter a research topic first.")
        else:
            st.session_state.topic_input = query.strip()
            st.session_state.final_state = {}
            st.session_state.chat_history = []
            runner.start(
                topic=query.strip(),
                role=scribe_role.lower(),
                tone=scribe_tone.lower(),
                scrape_top_n=scribe_depth,
                min_score=scribe_score,
                max_retries=int(scribe_retries)
            )
            st.rerun()

    # Agent Step Progression Status
    st.divider()
    st.subheader("Agent Deliberation Timeline")

    step_cols = st.columns(len(NODE_ORDER))
    for idx, (node_key, c) in enumerate(zip(NODE_ORDER, step_cols)):
        label = NODE_LABEL_MAP.get(node_key, node_key.capitalize())
        status = runner.node_statuses[idx] if idx < len(runner.node_statuses) else "pending"
        duration = runner.node_durations.get(node_key)

        with c:
            if status == "completed":
                st.success(f"✓ {label}" + (f"\n`{duration:.1f}s`" if duration else ""))
            elif status == "active":
                st.info(f"⏳ **{label}**\n*(running)*")
            else:
                st.caption(f"○ {label}")

    if runner.is_active:
        st.info("✦ Agents are deliberating: searching scholarly APIs, scraping evidence, drafting, and verifying claims…")
    elif runner.is_followup_active:
        st.info(f"✦ Processing follow-up query: `{runner.active_followup_event}`")

    # Research Synthesis Output
    final_report = st.session_state.final_state.get("report", "")
    if final_report:
        st.divider()
        st.subheader("Verified Synthesis & Findings")

        score_val = st.session_state.final_state.get("score", 0.0)
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Quality Score", f"{score_val:.1f} / 10" if score_val else "Verified")
        with col_m2:
            st.metric("Word Count", f"{len(final_report.split()):,} words")
        with col_m3:
            cum_sources = st.session_state.final_state.get("cumulative_sources", [])
            st.metric("Literature Grounding", f"{len(cum_sources)} Primary Sources")

        tab_rep_view, tab_sources_view, tab_audit_view, tab_chat_view = st.tabs([
            "Synthesis Report",
            "Literature Matrix",
            "Truth Guard & Critic Audit",
            "Copilot Dialogue"
        ])

        with tab_rep_view:
            st.markdown(final_report)
            st.download_button(
                "📥 Download Synthesis (.md)",
                data=final_report,
                file_name=f"thoth_research_{int(time.time())}.md",
                mime="text/markdown"
            )

        with tab_sources_view:
            cum_sources = st.session_state.final_state.get("cumulative_sources", [])
            if cum_sources:
                for idx, s in enumerate(cum_sources, 1):
                    url = s.get("url", "#")
                    title = s.get("title", f"Source {idx}")
                    turn = s.get("added_in_turn", 0)
                    is_pdf = url.endswith(".pdf") or "arxiv.org/pdf" in url
                    pdf_tag = " `[PDF]`" if is_pdf else ""

                    st.markdown(f"**{idx}. [{title}]({url})**{pdf_tag}")
                    st.caption(f"URL: {url} | Discovered: Turn {turn}")
            else:
                st.info("No sources recorded yet.")

        with tab_audit_view:
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                st.markdown("#### Truth Guard SLM Fact-Adjudication")
                verifier_log = runner.node_logs.get("verifier") or st.session_state.final_state.get("verifier_feedback", "")
                if verifier_log:
                    st.code(verifier_log, language="markdown")
                else:
                    st.info("No verifier log recorded.")
            with col_v2:
                st.markdown("#### LLM-as-a-Judge Critic Scorecard")
                critic_log = runner.node_logs.get("critic", "")
                if critic_log:
                    st.code(critic_log, language="markdown")
                else:
                    st.info("No critic scorecard recorded.")

        with tab_chat_view:
            st.markdown("#### Research Copilot Dialogue")
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    st.chat_message("user").write(msg["text"])
                else:
                    route = msg.get("route", "LOCAL_QA")
                    badge = "✦ Vault QA" if route == "LOCAL_QA" else ("🌐 Web Probe" if route == "WEB_SEARCH" else "📝 Expanded Report")
                    st.chat_message("assistant").write(f"**[{badge}]** {msg['text']}")

            follow_up_input = st.text_input("Ask a follow-up inquiry", placeholder="Ask about specific findings, methodology, or comparison...", disabled=runner.is_running())
            mode_choice = st.radio("Routing Mode", ["Auto (Smart Routing)", "Vault QA Only", "Academic Web Search", "Expand Main Report"], horizontal=True)
            mode_map = {
                "Auto (Smart Routing)": "auto",
                "Vault QA Only": "local_qa",
                "Academic Web Search": "web_probe",
                "Expand Main Report": "expand_report"
            }

            if st.button("Send Follow-Up", disabled=runner.is_running()) and follow_up_input.strip():
                user_q = follow_up_input.strip()
                st.session_state.chat_history.append({"role": "user", "text": user_q})
                runner.start_followup(
                    current_state=st.session_state.final_state,
                    user_query=user_q,
                    mode_override=mode_map.get(mode_choice, "auto")
                )
                st.rerun()


# ==============================================================================
# TAB 2: KNOWLEDGE CONSTELLATION
# ==============================================================================
with tab_constellation:
    st.header("✧ Knowledge Constellation")
    st.write("Visual and structural representation of extracted concept nodes and typed relationships.")

    mindmap_data = st.session_state.final_state.get("mindmap", {})
    if mindmap_data and mindmap_data.get("nodes"):
        nodes = mindmap_data.get("nodes", [])
        edges = mindmap_data.get("edges", [])

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.metric("Concept Nodes", len(nodes))
        with col_c2:
            st.metric("Typed Relationships", len(edges))

        col_n1, col_n2 = st.columns([1, 1])
        with col_n1:
            st.subheader("Concept Nodes")
            for n in nodes:
                st.markdown(f"- **{n.get('label')}** (`{n.get('type')}`): {n.get('details', '')}")
        with col_n2:
            st.subheader("Graph Edges")
            for e in edges:
                st.markdown(f"- `{e.get('from')}` ➔ **{e.get('label', 'relates')}** ➔ `{e.get('to')}`")

        with st.expander("Inspect Raw Mind Map JSON"):
            st.json(mindmap_data)
    else:
        st.info("Run a research cycle in the Research Lab tab to generate the concept graph.")


# ==============================================================================
# TAB 3: MEMORY VAULT EXPLORER
# ==============================================================================
with tab_vault:
    st.header("🗄 Obsidian Memory Vault & Hybrid Search")
    st.write("Query atomic notes with Reciprocal Rank Fusion (FTS5 BM25 + Dense Semantic Vector Search).")

    search_query = st.text_input("Hybrid Search Query", placeholder="Search memory vault across topics, entities, and sources...")
    cat_filter = st.selectbox("Category Filter", ["All", "topics", "sources", "entities", "sessions"])

    col_vlist, col_vview = st.columns([4, 6])

    with col_vlist:
        if search_query.strip():
            hits = search_memory_vault(search_query.strip(), top_k=10)
            st.markdown(f"**Found {len(hits)} matching notes:**")
            for h in hits:
                nid = h.get("note_id", "")
                ntype = h.get("type", "")
                score = h.get("rrf_score", 0.0)
                if st.button(f"📄 {nid} (RRF: {score:.4f})", key=f"vhit_{nid}", use_container_width=True):
                    st.session_state.selected_vault_note = nid
        else:
            cat = None if cat_filter == "All" else cat_filter
            all_notes = list_vault_notes(note_type=cat)
            st.markdown(f"**Vault Notes ({len(all_notes)}):**")
            for nid in all_notes[:30]:
                if st.button(f"📄 {nid}", key=f"vnote_{nid}", use_container_width=True):
                    st.session_state.selected_vault_note = nid

    with col_vview:
        sel_id = st.session_state.get("selected_vault_note")
        if sel_id:
            note = read_vault_note(sel_id)
            if note:
                st.subheader(f"Note: {sel_id}")
                st.json(note.get("frontmatter", {}))
                st.markdown("### Content")
                st.markdown(note.get("content", ""))

                neighbors = traverse_vault_graph(start_note=sel_id, max_depth=1)
                if neighbors:
                    st.markdown("### 1-Hop Connected Notes")
                    for nb in neighbors:
                        st.markdown(f"- `{nb.get('target')}` (*{nb.get('relation')}*)")
            else:
                st.error("Could not load note content.")
        else:
            st.info("Select a note from the left to inspect its contents and YAML frontmatter.")


# ==============================================================================
# TAB 4: CODEX HISTORY
# ==============================================================================
with tab_history:
    st.header("📜 Codex History & Persistent SQLite Archive")
    st.write("Access previously generated research reports and multi-turn sessions stored in SQLite.")

    reports = list_stored_reports(limit=25)
    if reports:
        for r in reports:
            rid = r.get("report_id", "")
            topic = r.get("topic", "Untitled")
            score = r.get("score", 0.0)
            created = r.get("created_at", "")
            content = r.get("content", "")

            with st.container():
                st.markdown(f"### {topic}")
                st.caption(f"ID: `{rid}` | Saved: {created[:19]} | Score: **{score:.1f}/10**")

                col_hr1, col_hr2 = st.columns([1, 4])
                with col_hr1:
                    if st.button("✦ Restore to Lab", key=f"restore_{rid}"):
                        st.session_state.topic_input = topic
                        st.session_state.final_state = {
                            "topic": topic,
                            "report": content,
                            "score": score,
                            "verifier_feedback": r.get("verifier_feedback", ""),
                            "mindmap": json.loads(r["mindmap_json"]) if r.get("mindmap_json") else {}
                        }
                        st.session_state.chat_history = []
                        st.success("Loaded into active workspace!")
                        st.rerun()
                with col_hr2:
                    with st.expander("Preview Text"):
                        st.markdown(content[:600] + "...")
                st.divider()
    else:
        st.info("No reports stored in SQLite database yet.")


# ==============================================================================
# TAB 5: DIAGNOSTICS & TELEMETRY
# ==============================================================================
with tab_diagnostics:
    st.header("⚙ System Diagnostics & Health HUD")
    st.write("Verify all 7 architectural layers: credentials, hybrid vault search, dispatcher circuit breaker, orchestrator mock, multi-turn memory, and frontier AI review.")

    run_diag = st.button("▶ Run Full 7-Layer Diagnostic Test", type="primary")
    if run_diag:
        st.info("Executing `diagnostic_test.py` across all 7 layers...")
        with st.spinner("Running diagnostic suite..."):
            try:
                res = subprocess.run(
                    [sys.executable, "diagnostic_test.py"],
                    capture_output=True,
                    text=True,
                    cwd=_CURRENT_DIR,
                    timeout=120
                )
                if res.returncode == 0:
                    st.success("✓ All 7 Diagnostic Layers Passed Successfully!")
                else:
                    st.warning(f"Diagnostics exited with code {res.returncode}")
                st.code(res.stdout, language="text")
                if res.stderr:
                    st.code(res.stderr, language="text")
            except Exception as e:
                st.error(f"Error executing diagnostic test: {e}")

# Auto-rerun loop while background thread is working
if runner.is_running():
    time.sleep(1.0)
    st.rerun()