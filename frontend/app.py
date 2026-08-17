"""
Thoth · Agentic Research Sanctum & Knowledge Studio
===================================================
Streamlit front-end command center for the autonomous multi-agent research engine.

Workspaces:
    ✦ Research Lab: Inquiry Composer, Live 6-Agent Deliberation Timeline, Dual-Pane Synthesis Studio.
    ✧ Knowledge Constellation: Full-canvas interactive D3 concept mind map.
    🗄 Memory Vault: Obsidian knowledge base with real-time Reciprocal Rank Fusion hybrid search.
    📜 Codex History: SQLite persistent session library & report archives.
    ⚙ Telemetry & Oracle Control: Circuit breaker monitor, model failover indicators, and parameters.
"""

import os
import sys
import time
import streamlit as st

# Ensure project root is on sys.path
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from frontend.theme import inject_theme, render_blobs, render_starfield, render_topbar
import frontend.views as views
from frontend.ui_adapter import ResearchPipelineRunner

st.set_page_config(
    page_title="Thoth · Agentic Research Sanctum",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 1. Inject Theme, Ambient Aurora Glows & Starfield Canvas
inject_theme()
render_blobs()
render_starfield()

# 2. Initialize Session State & Background Runner
if (
    "runner" not in st.session_state
    or getattr(st.session_state.runner, "_schema_version", 0) != ResearchPipelineRunner.SCHEMA_VERSION
):
    st.session_state.runner = ResearchPipelineRunner()

runner: ResearchPipelineRunner = st.session_state.runner

if "active_node" not in st.session_state:
    st.session_state.active_node = ""

if "node_statuses" not in st.session_state:
    st.session_state.node_statuses = ["pending"] * 7

if "node_durations" not in st.session_state:
    st.session_state.node_durations = {}

if "node_logs" not in st.session_state:
    st.session_state.node_logs = {
        "search": "",
        "scrape": "",
        "writer": "",
        "verifier": "",
        "critic": "",
        "mindmap": "",
        "follow_up": ""
    }

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

if "topic_input" not in st.session_state:
    st.session_state.topic_input = "Quantum Error Correction in Neutral Atom Qubits 2026"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "followup_mode" not in st.session_state:
    st.session_state.followup_mode = "auto"

if "scratchpad_text" not in st.session_state:
    st.session_state.scratchpad_text = ""

if "selected_vault_note" not in st.session_state:
    st.session_state.selected_vault_note = ""

# 2b. Scribe Configuration Defaults
if "scribe_role" not in st.session_state:
    st.session_state.scribe_role = "Senior Academic Researcher"

if "scribe_tone" not in st.session_state:
    st.session_state.scribe_tone = "Formal & Analytical"

if "scribe_language" not in st.session_state:
    st.session_state.scribe_language = "English"

if "scribe_scrape_top_n" not in st.session_state:
    st.session_state.scribe_scrape_top_n = 3

if "scribe_min_score" not in st.session_state:
    st.session_state.scribe_min_score = 6.5

if "scribe_max_retries" not in st.session_state:
    st.session_state.scribe_max_retries = 2

# 2c. Page Router State
if "page" not in st.session_state or st.session_state.page in ["sanctum", "chamber"]:
    st.session_state.page = "lab"

# 3. Synchronize Active Background Worker Updates
if runner.is_running() or runner.is_completed or runner.followup_completed:
    st.session_state.active_node = runner.active_node
    st.session_state.node_statuses = list(runner.node_statuses)
    st.session_state.node_durations = dict(runner.node_durations)
    st.session_state.node_logs = dict(runner.node_logs)
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

# 4. Top Header Bar Navigation
final_report = st.session_state.final_state.get("report", "")

if runner.is_active:
    status_label = "Agents Deliberating"
elif runner.is_followup_active:
    status_label = "Probing Follow-Up"
elif final_report:
    status_label = "Synthesis Verified"
else:
    status_label = "Standby"

nav_clicked = render_topbar(current_page=st.session_state.page, status_label=status_label)
if nav_clicked:
    st.session_state.page = nav_clicked
    st.rerun()

# 5. Workspace Router
active_page = st.session_state.page

if active_page == "constellation":
    views.render_constellation(runner)
elif active_page == "vault":
    views.render_vault_explorer()
elif active_page == "history":
    views.render_codex_history(runner)
elif active_page == "settings":
    views.render_telemetry_settings()
else:
    views.render_lab(runner)

# 6. Auto-poll UI while background worker thread is active
if runner.is_running():
    time.sleep(1.0)
    st.rerun()
