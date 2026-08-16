import streamlit as st
import time
import json
import re
import datetime
from theme import (
    inject_theme,
    render_blobs,
    render_header,
    render_planner_stepper,
    render_interactive_mindmap,
    render_copy_widget
)
from ui_adapter import ResearchPipelineRunner, NODE_LABEL_MAP, NODE_ORDER

st.set_page_config(
    page_title="Thoth: Agentic Research ✦",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 1. Inject Visual Theme & Styling
inject_theme()
render_blobs()

# 2. Initialize Session State — auto-migrate stale runner objects
if (
    "runner" not in st.session_state
    or getattr(st.session_state.runner, "_schema_version", 0)
       != ResearchPipelineRunner.SCHEMA_VERSION
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

if "topic_input" not in st.session_state:
    st.session_state.topic_input = "Latest breakthroughs in Quantum Computing and AI algorithms 2026"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "followup_mode" not in st.session_state:
    st.session_state.followup_mode = "auto"

if "scratchpad_text" not in st.session_state:
    st.session_state.scratchpad_text = ""

# Sync background runner updates
if runner.is_running() or runner.is_completed or runner.followup_completed:
    st.session_state.active_node = runner.active_node
    st.session_state.node_statuses = list(runner.node_statuses)
    st.session_state.node_durations = dict(runner.node_durations)
    st.session_state.node_logs = dict(runner.node_logs)
    if runner.final_state:
        st.session_state.final_state.update(runner.final_state)

    # Thread-safely consume completed follow-up response in main Streamlit thread
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

# 3. Sidebar Configuration
with st.sidebar:
    st.markdown('<div style="font-weight: 700; font-size: 1.1rem; color: #FFFFFF; margin-bottom: 1rem;">Configuration</div>', unsafe_allow_html=True)
    
    role = st.selectbox(
        "Target Role",
        ["Senior Academic Researcher", "Technical Copywriter", "Financial Analyst", "Staff Software Engineer", "Biomedical Scientist"]
    )
    tone = st.selectbox(
        "Tone",
        ["Formal & Analytical", "Informative & Casual", "Executive Summary", "Investigative & In-Depth"]
    )
    language = st.selectbox(
        "Language",
        ["English", "Hindi", "Spanish", "French", "German", "Japanese"]
    )
    scrape_top_n = st.slider("Pages to Scrape", min_value=1, max_value=5, value=2)
    
    with st.expander("Advanced Thresholds", expanded=False):
        min_score = st.slider("Min Quality Score", min_value=0.0, max_value=10.0, value=6.5, step=0.5)
        max_retries = st.number_input("Max Critic Retries", min_value=1, max_value=5, value=2)
        st.caption("Customizes multi-agent state graph thresholds and SLM verification loops.")

# 4. Top Header
render_header()

# 5. Split-Screen Layout: 40/60 (Chat Pane / Workspace Pane)
col_chat, col_workspace = st.columns([40, 60], gap="large")

# ==============================================================================
# LEFT PANE: RESEARCH COPILOT CHAT (40% Width)
# ==============================================================================
with col_chat:
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    # Main Query Prompt Input Box
    research_query = st.text_area(
        "Research Objective",
        value=st.session_state.topic_input,
        placeholder="Enter research topic, question, or hypothesis...",
        height=85,
        label_visibility="collapsed"
    )
    
    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        start_btn = st.button("✦ Launch Research", key="start_research_btn", use_container_width=True)
    with col_btn2:
        cancel_btn = st.button("Cancel", key="cancel_research_btn", use_container_width=True)
        
    if cancel_btn and runner.is_running():
        runner.cancel()
        st.info("Cancellation signal sent to agent pipeline.")
        
    if start_btn:
        if not research_query.strip():
            st.warning("Please enter a research topic to proceed.")
        else:
            st.session_state.topic_input = research_query.strip()
            st.session_state.node_statuses = ["active"] + ["pending"] * 6
            st.session_state.node_logs = {k: "" for k in st.session_state.node_logs}
            st.session_state.final_state = {}
            st.session_state.node_durations = {}
            st.session_state.chat_history = []
            
            # Start initial research pipeline
            runner.start(
                topic=research_query.strip(),
                role=role.lower(),
                tone=tone.lower(),
                language=language,
                scrape_top_n=scrape_top_n,
                min_score=min_score,
                max_retries=int(max_retries),
                on_complete=lambda final_state, durations: st.session_state.final_state.update(final_state)
            )
            st.rerun()

    # Chat Message Thread
    final_report = st.session_state.final_state.get("report", "")
    follow_ups = st.session_state.final_state.get("follow_up_questions", [])
    
    # Display conversation messages
    for idx, msg in enumerate(st.session_state.chat_history):
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-msg-user">{msg["text"]}</div>', unsafe_allow_html=True)
        else:
            route = msg.get("route", "LOCAL_QA")
            badge_class = "local-qa" if route == "LOCAL_QA" else ("web-search" if route == "WEB_SEARCH" else "report-expansion")
            badge_label = "✦ Context QA" if route == "LOCAL_QA" else ("🌐 Live Web Probe" if route == "WEB_SEARCH" else "📝 Living Report Expansion")
            
            st.markdown(
                f'<div class="route-badge {badge_class}">{badge_label}</div>'
                f'<div class="chat-msg-agent">{msg["text"]}</div>',
                unsafe_allow_html=True
            )
            
            # 1-Click Merge to Synthesis Report Button
            col_m1, col_m2 = st.columns([2, 1])
            with col_m2:
                if st.button("✦ Merge to Report", key=f"merge_btn_{idx}", help="Append this finding into the Synthesis Report"):
                    current_rep = st.session_state.final_state.get("report", "")
                    merge_section = f"\n\n### Follow-Up Investigation: {msg.get('query_title', 'Key Finding')}\n{msg['text']}"
                    st.session_state.final_state["report"] = current_rep + merge_section
                    st.success("Merged into Synthesis Report!")
                    st.rerun()

    # Streaming / Status Indicators
    if runner.is_active:
        st.markdown(
            '<div class="chat-msg-agent" style="color: var(--text-muted);">'
            '✦ Thoth agents are actively searching registries, scraping sources, and synthesizing mind map...'
            '</div>',
            unsafe_allow_html=True
        )
    elif runner.is_followup_active:
        ev = runner.active_followup_event or "processing"
        st.markdown(
            f'<div class="chat-msg-agent" style="color: #38BDF8; font-weight: 500;">'
            f'✦ Executing follow-up probe: <code>{ev}</code> (querying registries & Mind Map)...'
            '</div>',
            unsafe_allow_html=True
        )
    elif final_report and not st.session_state.chat_history:
        st.markdown(
            '<div class="chat-msg-agent">'
            '✦ Verified research synthesis & Concept Mind Map generated. You can ask any follow-up question below '
            'or click a suggested exploration vector.'
            '</div>',
            unsafe_allow_html=True
        )

    # Multi-Turn Follow-Up Controls (Only shown once initial report is ready)
    if final_report and not runner.is_active:
        st.markdown("<div style='margin-top: 1.2rem;'></div>", unsafe_allow_html=True)
        
        # Mode Selector
        col_m_label, col_mode = st.columns([1, 2])
        with col_m_label:
            st.markdown("<span style='font-size:0.82rem; font-weight:600; color:var(--text-secondary);'>Route Mode:</span>", unsafe_allow_html=True)
        with col_mode:
            mode_choice = st.radio(
                "Follow-up Mode",
                ["Auto ✦", "⚡ Fast QA", "🌐 Web Probe", "📝 Expand Report"],
                horizontal=True,
                label_visibility="collapsed",
                key="mode_radio"
            )
            mode_map = {
                "Auto ✦": "auto",
                "⚡ Fast QA": "local_qa",
                "🌐 Web Probe": "web_probe",
                "📝 Expand Report": "expand_report"
            }
            st.session_state.followup_mode = mode_map.get(mode_choice, "auto")

        # Proactive Follow-up Suggestion Pills
        suggestions = follow_ups if follow_ups else [
            f"What are the practical solutions and interventions to address these challenges?",
            f"Compare these findings against latest 2026 empirical benchmarks",
            f"What are the major policy and funding implications?"
        ]
        
        st.markdown("<div style='font-size:0.8rem; color:var(--text-muted); margin-top:0.6rem; margin-bottom:0.3rem;'>Suggested Follow-Ups:</div>", unsafe_allow_html=True)
        for i, q in enumerate(suggestions[:3]):
            if st.button(f"✦ {q}", key=f"chat_pill_{i}", use_container_width=True, disabled=runner.is_running()):
                # Trigger follow-up turn asynchronously
                st.session_state.chat_history.append({"role": "user", "text": q})
                runner.start_followup(
                    current_state=st.session_state.final_state,
                    user_query=q,
                    mode_override=st.session_state.followup_mode
                )
                st.rerun()

        # Follow-up Free-Form Chat Input Bar
        st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)
        col_fq1, col_fq2 = st.columns([4, 1])
        with col_fq1:
            chat_followup_input = st.text_input(
                "Ask a follow-up question",
                placeholder="Ask any follow-up question or probe new angle...",
                label_visibility="collapsed",
                key="chat_followup_input",
                disabled=runner.is_running()
            )
        with col_fq2:
            send_followup_btn = st.button("✦ Ask", key="send_chat_followup", use_container_width=True, disabled=runner.is_running())
            
        if send_followup_btn and chat_followup_input.strip():
            user_q = chat_followup_input.strip()
            st.session_state.chat_history.append({"role": "user", "text": user_q})
            runner.start_followup(
                current_state=st.session_state.final_state,
                user_query=user_q,
                mode_override=st.session_state.followup_mode
            )
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# RIGHT PANE: TABBED RESEARCH WORKSPACE (60% Width)
# ==============================================================================
with col_workspace:
    # 1. Pinned Horizontal Stepper Rail
    active_idx = NODE_ORDER.index(st.session_state.active_node) if st.session_state.active_node in NODE_ORDER else 0
    render_planner_stepper(
        active_idx=active_idx,
        statuses=st.session_state.node_statuses,
        durations=st.session_state.node_durations
    )
    
    # 2. Workspace Tabs (Featuring Concept Mind Map)
    tab_report, tab_mindmap, tab_matrix, tab_audit, tab_notes = st.tabs([
        "Synthesis Report",
        "✦ Concept Mind Map",
        "Literature Matrix",
        "Truth Guard Audit",
        "Notes & Export"
    ])
    
    # --------------------------------------------------------------------------
    # TAB 1: SYNTHESIS REPORT (Editorial Serif Typography)
    # --------------------------------------------------------------------------
    with tab_report:
        if final_report:
            # Render Source Domain Chips from cumulative sources
            cum_sources = st.session_state.final_state.get("cumulative_sources", [])
            if cum_sources:
                chips_html = ["<div style='margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 6px;'>"]
                for idx, s in enumerate(cum_sources[:8], 1):
                    url = s.get("url", "#")
                    domain = s.get("domain", url)
                    chips_html.append(
                        f'<a class="chip" href="{url}" target="_blank">'
                        f'<span class="chip-dot" style="background:var(--ok);"></span>'
                        f'[{idx}] {domain}'
                        f'</a>'
                    )
                chips_html.append("</div>")
                st.markdown("".join(chips_html), unsafe_allow_html=True)
                
            # Render Prose with Editorial Serif
            st.markdown(f'<div class="editorial-prose">{final_report}</div>', unsafe_allow_html=True)
            
            # Action Buttons Row
            st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
            col_a1, col_a2 = st.columns([1, 1])
            with col_a1:
                st.download_button(
                    label="Download Report (.md)",
                    data=final_report,
                    file_name=f"thoth_synthesis_{int(time.time())}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            with col_a2:
                render_copy_widget(final_report, "Copy Markdown")
        elif runner.is_running():
            st.info("Agents are actively drafting and synthesizing the research report...")
        else:
            st.markdown(
                '<div style="color: var(--text-muted); padding: 3rem 1rem; text-align: center;">'
                'Enter a research objective on the left and click <strong>Launch Research</strong> to generate a verified synthesis report.'
                '</div>',
                unsafe_allow_html=True
            )

    # --------------------------------------------------------------------------
    # TAB 2: CONCEPT MIND MAP (Interactive Dynamic Knowledge Graph)
    # --------------------------------------------------------------------------
    with tab_mindmap:
        mindmap_data = st.session_state.final_state.get("mindmap", {})
        if mindmap_data and mindmap_data.get("nodes"):
            st.markdown(
                "<div style='font-size:0.85rem; color:var(--text-secondary); margin-bottom: 8px;'>"
                "Interactive concept graph with drag, zoom, and live follow-up expansion. Hover over nodes to inspect evidence."
                "</div>",
                unsafe_allow_html=True
            )
            render_interactive_mindmap(mindmap_data, height=520)
        elif runner.is_running():
            st.info("Concept Mind Map will be generated once research drafting completes...")
        else:
            st.markdown(
                '<div style="color: var(--text-muted); padding: 3rem 1rem; text-align: center;">'
                'The interactive Concept Mind Map will appear here after initial research synthesis completes.'
                '</div>',
                unsafe_allow_html=True
            )

    # --------------------------------------------------------------------------
    # TAB 3: LITERATURE REVIEW MATRIX (Cumulative Deduplicated Sources)
    # --------------------------------------------------------------------------
    with tab_matrix:
        cum_sources = st.session_state.final_state.get("cumulative_sources", [])
        if cum_sources:
            rows_html = []
            for i, s in enumerate(cum_sources, 1):
                url = s.get("url", "#")
                domain = s.get("domain", url)
                title = s.get("title", f"Source {i}")
                turn = s.get("added_in_turn", 0)
                turn_label = "Initial Synthesis" if turn == 0 else f"Follow-up #{turn}"
                
                rows_html.append(
                    f'<tr>'
                    f'<td style="width: 25%; font-weight: 500; color: #FFFFFF;">Source #{i}: <a href="{url}" target="_blank" style="color: var(--text-secondary); text-decoration: underline;">{domain}</a></td>'
                    f'<td style="width: 35%;">{title}</td>'
                    f'<td style="width: 20%; color: var(--text-muted);">{turn_label}</td>'
                    f'<td style="width: 20%; text-align: center;"><span class="status-pill verified">✓ Verified</span></td>'
                    f'</tr>'
                )
                
            matrix_html = f"""
            <table class="matrix-table">
                <thead>
                    <tr>
                        <th style="width: 25%;">Source / Domain</th>
                        <th style="width: 35%;">Extracted Title / Scope</th>
                        <th style="width: 20%;">Discovery Vector</th>
                        <th style="width: 20%; text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
            """
            st.markdown(matrix_html, unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="color: var(--text-muted); padding: 3rem 1rem; text-align: center;">'
                'The literature matrix will populate automatically with verified sources and follow-up probes.'
                '</div>',
                unsafe_allow_html=True
            )

    # --------------------------------------------------------------------------
    # TAB 4: TRUTH GUARD AUDIT & QUALITY EVALUATION
    # --------------------------------------------------------------------------
    with tab_audit:
        verifier_log = st.session_state.node_logs.get("verifier", "")
        critic_log = st.session_state.node_logs.get("critic", "")
        
        if verifier_log or critic_log:
            if verifier_log:
                st.markdown("<div style='font-weight: 600; font-size: 0.95rem; margin-bottom: 0.4rem; color: #FFFFFF;'>SLM Fact-Verifier (Truth Guard)</div>", unsafe_allow_html=True)
                st.markdown(f'<div class="log-pane">{verifier_log}</div>', unsafe_allow_html=True)
            if critic_log:
                st.markdown("<div style='font-weight: 600; font-size: 0.95rem; margin-top: 1rem; margin-bottom: 0.4rem; color: #FFFFFF;'>LLM-as-a-Judge Quality Audit</div>", unsafe_allow_html=True)
                st.markdown(f'<div class="log-pane">{critic_log}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="color: var(--text-muted); padding: 3rem 1rem; text-align: center;">'
                'Verification audit logs and quality evaluation scores will appear here during pipeline execution.'
                '</div>',
                unsafe_allow_html=True
            )

    # --------------------------------------------------------------------------
    # TAB 5: RESEARCH NOTES & SCRATCHPAD
    # --------------------------------------------------------------------------
    with tab_notes:
        st.markdown("<div style='font-weight: 600; font-size: 0.95rem; margin-bottom: 0.4rem; color: #FFFFFF;'>Research Scratchpad & Synthesis Export</div>", unsafe_allow_html=True)
        st.session_state.scratchpad_text = st.text_area(
            "Scratchpad Notes",
            value=st.session_state.scratchpad_text,
            placeholder="Jot down notes, citations, hypothesis thoughts, or snippets from the report...",
            height=260,
            label_visibility="collapsed"
        )
        if st.session_state.scratchpad_text:
            st.download_button(
                label="Export Notes (.txt)",
                data=st.session_state.scratchpad_text,
                file_name=f"thoth_notes_{int(time.time())}.txt",
                mime="text/plain"
            )

# 6. Auto-poll UI while background worker thread is active
if runner.is_running():
    time.sleep(1.0)
    st.rerun()

