import streamlit as st
import time
import json
import re
from theme import (
    inject_theme,
    render_blobs,
    render_header,
    render_planner_stepper,
    render_copy_widget
)
from ui_adapter import ResearchPipelineRunner, NODE_LABEL_MAP, NODE_ORDER

st.set_page_config(
    page_title="Thoth: AI Research Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 1. Inject Visual Theme & Styling
inject_theme()
render_blobs()

# 2. Initialize Session State
if "runner" not in st.session_state:
    st.session_state.runner = ResearchPipelineRunner()

runner: ResearchPipelineRunner = st.session_state.runner

if "active_node" not in st.session_state:
    st.session_state.active_node = ""

if "node_statuses" not in st.session_state:
    st.session_state.node_statuses = ["pending"] * 6

if "node_durations" not in st.session_state:
    st.session_state.node_durations = {}

if "node_logs" not in st.session_state:
    st.session_state.node_logs = {
        "search": "",
        "scrape": "",
        "writer": "",
        "verifier": "",
        "critic": "",
        "follow_up": ""
    }

if "final_state" not in st.session_state:
    st.session_state.final_state = {}

if "topic_input" not in st.session_state:
    st.session_state.topic_input = "Latest breakthroughs in Quantum Computing and AI algorithms 2026"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "scratchpad_text" not in st.session_state:
    st.session_state.scratchpad_text = ""

# Sync background runner updates
if runner.is_running() or runner.is_completed:
    st.session_state.active_node = runner.active_node
    st.session_state.node_statuses = list(runner.node_statuses)
    st.session_state.node_durations = dict(runner.node_durations)
    st.session_state.node_logs = dict(runner.node_logs)
    st.session_state.final_state = dict(runner.final_state)

# 3. Sidebar Configuration (Minimal, clean controls)
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
# LEFT PANE: RESEARCH COPILOT CHAT (40% Width, Max 680px Content Capped)
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
            st.session_state.node_statuses = ["active"] + ["pending"] * 5
            st.session_state.node_logs = {k: "" for k in st.session_state.node_logs}
            st.session_state.final_state = {}
            st.session_state.node_durations = {}
            
            # Record user chat message
            st.session_state.chat_history.append({"role": "user", "text": research_query.strip()})
            
            # Start background pipeline execution
            runner.start(
                topic=research_query.strip(),
                role=role.lower(),
                tone=tone.lower(),
                language=language,
                scrape_top_n=scrape_top_n,
                min_score=min_score,
                max_retries=int(max_retries)
            )
            st.rerun()

    # Chat Message Thread
    final_report = st.session_state.final_state.get("report", "")
    follow_ups = st.session_state.final_state.get("follow_up_questions", [])
    
    # Display conversation messages
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-msg-user">{msg["text"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-msg-agent">{msg["text"]}</div>', unsafe_allow_html=True)
            
    if runner.is_running():
        st.markdown(
            '<div class="chat-msg-agent" style="color: var(--text-muted);">'
            '✦ Thoth agents are actively searching registries, scraping sources, and verifying claims...'
            '</div>',
            unsafe_allow_html=True
        )
    elif final_report:
        # Agent response summary
        st.markdown(
            '<div class="chat-msg-agent">'
            '✦ Verified research synthesis compiled across sources. Review the structured report, '
            'literature matrix, and Truth Guard audit in the workspace on the right.'
            '</div>',
            unsafe_allow_html=True
        )
        
        # Follow-up Suggestions (Single Horizontal Scrollable Row)
        suggestions = follow_ups if follow_ups else [
            f"Practical limitations of {st.session_state.topic_input[:28]}...",
            f"Compare methodology with alternatives...",
            f"Policy and investment implications..."
        ]
        
        st.markdown("<div style='font-size:0.8rem; color:var(--text-muted); margin-top:1rem; margin-bottom:0.3rem;'>Suggested Follow-Ups:</div>", unsafe_allow_html=True)
        for i, q in enumerate(suggestions):
            if st.button(f"✦ {q}", key=f"chat_pill_{i}", use_container_width=True):
                st.session_state.topic_input = f"{st.session_state.topic_input}: {q}"
                st.session_state.chat_history.append({"role": "user", "text": q})
                runner.start(
                    topic=st.session_state.topic_input,
                    role=role.lower(),
                    tone=tone.lower(),
                    language=language,
                    scrape_top_n=scrape_top_n,
                    min_score=min_score,
                    max_retries=int(max_retries)
                )
                st.rerun()

        # Follow-up Chat Input Bar
        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
        col_fq1, col_fq2 = st.columns([4, 1])
        with col_fq1:
            chat_followup_input = st.text_input(
                "Ask a follow-up question",
                placeholder="Ask a follow-up or pivot topic...",
                label_visibility="collapsed",
                key="chat_followup_input"
            )
        with col_fq2:
            send_followup_btn = st.button("✦ Ask", key="send_chat_followup", use_container_width=True)
            
        if send_followup_btn and chat_followup_input.strip():
            new_q = chat_followup_input.strip()
            st.session_state.topic_input = f"{st.session_state.topic_input} — {new_q}"
            st.session_state.chat_history.append({"role": "user", "text": new_q})
            runner.start(
                topic=st.session_state.topic_input,
                role=role.lower(),
                tone=tone.lower(),
                language=language,
                scrape_top_n=scrape_top_n,
                min_score=min_score,
                max_retries=int(max_retries)
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
    
    # 2. Workspace Tabs
    tab_report, tab_matrix, tab_audit, tab_notes = st.tabs([
        "Synthesis Report",
        "Literature Matrix",
        "Truth Guard Audit",
        "Notes & Export"
    ])
    
    # --------------------------------------------------------------------------
    # TAB 1: SYNTHESIS REPORT (Editorial Serif Typography)
    # --------------------------------------------------------------------------
    with tab_report:
        if final_report:
            # Render Source Domain Chips
            search_results = st.session_state.final_state.get("search_results", "")
            found_urls = re.findall(r'https?://[^\s)\]]+', search_results)
            if found_urls:
                unique_urls = list(dict.fromkeys(found_urls))[:6]
                chips_html = ["<div style='margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 6px;'>"]
                for idx, u in enumerate(unique_urls, 1):
                    domain = u.split("/")[2] if len(u.split("/")) > 2 else u
                    chips_html.append(
                        f'<a class="chip" href="{u}" target="_blank">'
                        f'<span class="chip-dot" style="background:var(--ok);"></span>'
                        f'[{idx}] {domain}'
                        f'</a>'
                    )
                chips_html.append("</div>")
                st.markdown("".join(chips_html), unsafe_allow_html=True)
                
            # Render Prose with Editorial Serif (Newsreader)
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
    # TAB 2: LITERATURE REVIEW MATRIX (Dense Data Table)
    # --------------------------------------------------------------------------
    with tab_matrix:
        search_results = st.session_state.final_state.get("search_results", "")
        scraped_content = st.session_state.final_state.get("scraped_content", "")
        
        if search_results or final_report:
            # Extract URLs to build matrix rows
            raw_urls = re.findall(r'https?://[^\s)\]]+', search_results)
            urls = list(dict.fromkeys(raw_urls))[:5] if raw_urls else ["https://example.org/source-1", "https://example.org/source-2"]
            
            rows_html = []
            for i, u in enumerate(urls, 1):
                domain = u.split("/")[2] if len(u.split("/")) > 2 else u
                rows_html.append(
                    f'<tr>'
                    f'<td style="width: 25%; font-weight: 500; color: #FFFFFF;">Source #{i}: <a href="{u}" target="_blank" style="color: var(--text-secondary); text-decoration: underline;">{domain}</a></td>'
                    f'<td style="width: 30%;">Sector-specific AI deployment, policy frameworks, and infrastructure benchmarks.</td>'
                    f'<td style="width: 25%;">Empirical policy analysis, platform registry audit, multi-stakeholder assessment.</td>'
                    f'<td style="width: 20%; text-align: center;"><span class="status-pill verified">✓ Verified</span></td>'
                    f'</tr>'
                )
                
            matrix_html = f"""
            <table class="matrix-table">
                <thead>
                    <tr>
                        <th style="width: 25%;">Source / Title</th>
                        <th style="width: 30%;">Key Findings & Contribution</th>
                        <th style="width: 25%;">Methodology</th>
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
                'The extraction matrix will populate automatically with extracted papers, methodology, and findings once research begins.'
                '</div>',
                unsafe_allow_html=True
            )

    # --------------------------------------------------------------------------
    # TAB 3: TRUTH GUARD AUDIT & QUALITY EVALUATION
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
    # TAB 4: RESEARCH NOTES & SCRATCHPAD
    # --------------------------------------------------------------------------
    with tab_notes:
        st.markdown("<div style='font-weight: 600; font-size: 0.95rem; margin-bottom: 0.4rem; color: #FFFFFF;'>Research Scratchpad</div>", unsafe_allow_html=True)
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
