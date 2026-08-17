"""
Thoth · Next-Generation Workspaces & Page Views
================================================
Five dedicated workspaces providing an industry-standard AI research and knowledge graph studio:

    1. render_lab(runner)            -> ✦ Research Lab (Inquiry composer, live deliberation, verified synthesis)
    2. render_constellation(runner)  -> ✧ Knowledge Constellation (Full-canvas interactive D3 concept graph)
    3. render_vault_explorer()       -> 🗄 Memory Vault Explorer (Live hybrid RRF search, note & wikilink inspector)
    4. render_codex_history(runner)  -> 📜 Codex History (SQLite persistent sessions & synthesis archive)
    5. render_telemetry_settings()   -> ⚙ Telemetry & Oracle Control (Circuit breaker, model failovers, budgets)
"""

import time
import json
import streamlit as st

from frontend.theme import (
    render_section_title,
    render_oracle_stats_animated,
    render_empty_state,
    render_thinking,
    render_planner_stepper,
    render_interactive_mindmap,
    render_copy_widget,
    render_agent_rail,
    render_judge_strip,
    render_hero_footer,
)
from frontend.ui_adapter import (
    NODE_ORDER,
    list_stored_sessions,
    list_stored_reports,
    get_stored_report_by_id,
    search_memory_vault,
    list_vault_notes,
    read_vault_note,
    traverse_vault_graph,
    get_telemetry_status,
)


# ==============================================================================
# 1. RESEARCH LAB — INQUIRY COMPOSER & SYNTHESIS STUDIO
# ==============================================================================

AGENTS = [
    ("🔍", "Search", "Queries live academic registries (arXiv, OpenAlex, Semantic Scholar) and web."),
    ("📖", "Reader", "Concurrently scrapes and normalizes full-text from top-ranked primary sources."),
    ("✍", "Writer", "Drafts a structured, citation-grounded synthesis with LLM failover protection."),
    ("🛡", "Verifier", "Truth Guard checks every assertion against source evidence without hallucinations."),
    ("⚖", "Critic", "Multi-dimensional judge scores faithfulness, relevance, completeness and evidence."),
    ("✦", "Mind Map", "Renders the force-directed concept constellation binding topics to evidence."),
]

JUDGE_ITEMS = [
    ("Faithfulness", "Every single claim is cross-referenced with source text before it is trusted."),
    ("Relevance", "Off-topic tangents and speculative noise are strictly scored down."),
    ("Completeness", "Identifies knowledge gaps and suggests specific exploration vectors."),
    ("Evidence Quality", "Prefers peer-reviewed academic literature with verifiable DOI/arXiv citations."),
]


def render_lab(runner):
    """The central deep research laboratory: Inquiry Composer, Live Agent Timeline, and Dual-Pane Synthesis."""
    final_report = st.session_state.final_state.get("report", "")
    follow_ups = st.session_state.final_state.get("follow_up_questions", [])

    with st.container(key="page_wrap"):
        # Header & Workspace Title
        render_section_title(
            "Research Lab",
            "Inquiry & Synthesis Studio",
            "Multi-agent autonomous research with live fact adjudication, academic grounding, and concept mapping."
        )
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # 1. Multi-Agent Deliberation Stepper Rail
        active_idx = NODE_ORDER.index(st.session_state.active_node) if st.session_state.active_node in NODE_ORDER else 0
        render_planner_stepper(
            active_idx=active_idx,
            statuses=st.session_state.node_statuses,
            durations=st.session_state.node_durations,
            is_active=runner.is_active or runner.is_followup_active
        )

        if runner.is_active:
            _THINKING_MSGS = [
                "The Search agent is querying academic registries (arXiv, OpenAlex, Semantic Scholar)…",
                "The Reader is fanning out concurrent scrape requests across primary sources…",
                "The Writer is drafting structured prose; the Truth Guard stands ready…",
                "The Verifier is adjudicating claims against scraped evidence slices…",
                "The Critic is evaluating multi-dimensional quality scores…",
                "Drawing the constellation of concepts and storing atomic notes in the vault…",
            ]
            _msg = _THINKING_MSGS[int(time.time()) % len(_THINKING_MSGS)]
            render_thinking(_msg)
        elif runner.is_followup_active:
            ev = runner.active_followup_event or "processing"
            render_thinking(f"Executing follow-up probe: <code>{ev}</code>")

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # 2. Dual-Pane Layout: Left (36% Copilot & Scope) | Right (64% Synthesis Canvas)
        col_copilot, col_canvas = st.columns([36, 64], gap="large")

        with col_copilot:
            # 2a. Hero Inquiry Composer
            render_section_title("Inquiry", "Objective & Scope", "Submit an inquiry to launch or refine.")
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

            research_query = st.text_area(
                "Research Objective",
                value=st.session_state.topic_input,
                placeholder="State a research topic, hypothesis, or technical inquiry...",
                height=90,
                label_visibility="collapsed",
                key="lab_query_input"
            )

            # Scope Quick Pills
            col_pill1, col_pill2 = st.columns(2)
            with col_pill1:
                st.session_state.scribe_scrape_top_n = st.selectbox(
                    "Primary Sources Depth",
                    [2, 3, 4, 5],
                    index=1,
                    key="lab_depth_select",
                    help="Number of primary sources to scrape and verify."
                )
            with col_pill2:
                st.session_state.scribe_min_score = st.selectbox(
                    "Min Quality Gate",
                    [6.0, 6.5, 7.0, 7.5, 8.0],
                    index=1,
                    key="lab_score_select",
                    help="Threshold score below which the critic loops back for revision."
                )

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                start_btn = st.button(
                    "✦ Invoke Thoth",
                    key="lab_start_btn",
                    use_container_width=True,
                    type="primary",
                    disabled=runner.is_running()
                )
            with col_btn2:
                cancel_btn = st.button("Halt", key="lab_cancel_btn", use_container_width=True)

            if cancel_btn and runner.is_running():
                runner.cancel()
                st.info("Cancellation signal dispatched to the agent pipeline.")

            if start_btn:
                if not research_query.strip():
                    st.warning("Please enter a research objective to proceed.")
                else:
                    _launch_research(runner, research_query.strip())

            st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

            # 2b. Research Copilot Dialogue & Follow-up Vectors
            render_section_title("Copilot", "Research Dialogue", "Probe new angles or expand the synthesis.")
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

            with st.container(key="copilot_thread"):
                for idx, msg in enumerate(st.session_state.chat_history):
                    if msg["role"] == "user":
                        st.markdown(f'<div class="chat-msg-user">{msg["text"]}</div>', unsafe_allow_html=True)
                    else:
                        route = msg.get("route", "LOCAL_QA")
                        badge_class = "local-qa" if route == "LOCAL_QA" else ("web-search" if route == "WEB_SEARCH" else "report-expansion")
                        badge_label = "✦ Vault Grounded QA" if route == "LOCAL_QA" else ("Academic Web Probe" if route == "WEB_SEARCH" else "Living Report Expansion")

                        st.markdown(
                            f'<div class="route-badge {badge_class}">{badge_label}</div>'
                            f'<div class="chat-msg-agent">{msg["text"]}</div>',
                            unsafe_allow_html=True
                        )

                        col_m1, col_m2 = st.columns([1, 1])
                        with col_m2:
                            if st.button("✦ Inscribe to Report", key=f"merge_btn_{idx}", help="Append this finding into the Synthesis Report"):
                                current_rep = st.session_state.final_state.get("report", "")
                                merge_section = f"\n\n### Follow-Up Investigation: {msg.get('query_title', 'Key Finding')}\n{msg['text']}"
                                st.session_state.final_state["report"] = current_rep + merge_section
                                st.success("Inscribed into the Synthesis Report.")
                                st.rerun()

                if not st.session_state.chat_history:
                    if final_report:
                        st.markdown(
                            '<div class="chat-msg-agent">'
                            '✦ The synthesis is verified and stored in the Obsidian Vault. '
                            'Ask any follow-up below, or choose one of the suggested exploration vectors.'
                            '</div>',
                            unsafe_allow_html=True
                        )
                    elif not runner.is_active:
                        render_empty_state(
                            "𓅝",
                            "The chamber awaits your inquiry",
                            "State a research objective above. Six agents will search scholarly registries, "
                            "verify claims, score quality, and map the concept graph."
                        )

                # Follow-Up Inquiry Bar & Suggested Vectors
                if final_report and not runner.is_active:
                    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
                    render_section_title("Exploration", "Follow-up Route")

                    mode_choice = st.radio(
                        "Route Mode",
                        ["Auto ✦", "Vault QA", "Web Probe", "Expand Report"],
                        horizontal=True,
                        label_visibility="collapsed",
                        key="lab_mode_radio"
                    )
                    mode_map = {
                        "Auto ✦": "auto",
                        "Vault QA": "local_qa",
                        "Web Probe": "web_probe",
                        "Expand Report": "expand_report"
                    }
                    st.session_state.followup_mode = mode_map.get(mode_choice, "auto")

                    suggestions = follow_ups if follow_ups else [
                        "What are the practical solutions and interventions to address these challenges?",
                        "Compare these findings against latest 2026 empirical benchmarks",
                        "What are the major policy and technological bottlenecks?"
                    ]

                    st.markdown(
                        "<div style='font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; "
                        "color:var(--gold); margin:.8rem 0 .4rem 0;'>Proactive Thread Suggestions</div>",
                        unsafe_allow_html=True
                    )
                    for i, q in enumerate(suggestions[:3]):
                        _label = (q[:70] + "…") if len(q) > 70 else q
                        if st.button(f"✦ {_label}", key=f"lab_pill_{i}", use_container_width=True, disabled=runner.is_running()):
                            st.session_state.chat_history.append({"role": "user", "text": q})
                            runner.start_followup(
                                current_state=st.session_state.final_state,
                                user_query=q,
                                mode_override=st.session_state.followup_mode
                            )
                            st.rerun()

                    st.markdown("<div style='margin-top: .8rem;'></div>", unsafe_allow_html=True)
                    col_fq1, col_fq2 = st.columns([3, 1])
                    with col_fq1:
                        chat_followup_input = st.text_input(
                            "Ask a follow-up question",
                            placeholder="Ask a follow-up or probe a new angle...",
                            label_visibility="collapsed",
                            key="lab_chat_input",
                            disabled=runner.is_running()
                        )
                    with col_fq2:
                        send_followup_btn = st.button("✦ Probe", key="lab_send_chat", use_container_width=True, disabled=runner.is_running())

                    if send_followup_btn and chat_followup_input.strip():
                        user_q = chat_followup_input.strip()
                        st.session_state.chat_history.append({"role": "user", "text": user_q})
                        runner.start_followup(
                            current_state=st.session_state.final_state,
                            user_query=user_q,
                            mode_override=st.session_state.followup_mode
                        )
                        st.rerun()

        with col_canvas:
            # 2c. Live Stat Telemetry Bar
            cum_sources_all = st.session_state.final_state.get("cumulative_sources", [])
            mindmap_all = st.session_state.final_state.get("mindmap", {}) or {}
            word_count = len(final_report.split()) if final_report else 0
            total_elapsed = sum(st.session_state.node_durations.values()) if st.session_state.node_durations else 0.0
            critic_score_val = st.session_state.final_state.get("score", 0.0)

            render_oracle_stats_animated([
                (len(cum_sources_all), "Sources"),
                (len(mindmap_all.get("nodes", [])), "Concepts"),
                (f"{critic_score_val:.1f}" if critic_score_val else "—", "Quality /10"),
                (f"{word_count:,}" if word_count else "—", "Words"),
                (f"{total_elapsed:.0f}s" if total_elapsed else "—", "Elapsed"),
            ])

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

            # 2d. Synthesis Tabs Deck
            tab_report, tab_sources, tab_audit, tab_notes = st.tabs([
                "Verified Synthesis",
                "Literature Matrix",
                "Truth Guard & Judge",
                "Scratchpad & Export"
            ])

            with tab_report:
                if final_report:
                    cum_sources = st.session_state.final_state.get("cumulative_sources", [])
                    if cum_sources:
                        chips_html = ["<div style='margin-bottom: 1rem; display: flex; flex-wrap: wrap; gap: 7px;'>"]
                        for idx, s in enumerate(cum_sources[:8], 1):
                            url = s.get("url", "#")
                            domain = s.get("domain", url)
                            is_pdf = url.endswith(".pdf") or "arxiv.org/pdf" in url
                            badge_icon = "📄 PDF" if is_pdf else "🌐"
                            chips_html.append(
                                f'<a class="scholar-chip" href="{url}" target="_blank">'
                                f'<span>{badge_icon} [{idx}]</span> {domain}'
                                f'</a>'
                            )
                        chips_html.append("</div>")
                        st.markdown("".join(chips_html), unsafe_allow_html=True)

                    st.markdown(
                        '<div class="synthesis-kicker">✦ Verified & Inscribed in Vault</div>',
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        f'<div class="synthesis-arrived editorial-prose">{final_report}</div>',
                        unsafe_allow_html=True
                    )

                    st.markdown("<div style='margin-top: 1.4rem;'></div>", unsafe_allow_html=True)
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
                    render_thinking("The Writer is drafting; the Truth Guard and Critic stand ready…")
                else:
                    render_empty_state(
                        "✦",
                        "No synthesis inscribed yet",
                        "Submit an inquiry from the composer on the left to launch an autonomous, "
                        "academically grounded research cycle."
                    )

            with tab_sources:
                cum_sources = st.session_state.final_state.get("cumulative_sources", [])
                if cum_sources:
                    render_section_title("Codex", "Primary Literature Matrix", "Every source retrieved and cross-referenced.")
                    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                    rows_html = []
                    for i, s in enumerate(cum_sources, 1):
                        url = s.get("url", "#")
                        domain = s.get("domain", url)
                        title = s.get("title", f"Source {i}")
                        turn = s.get("added_in_turn", 0)
                        turn_label = "Initial Turn" if turn == 0 else f"Follow-up #{turn}"

                        rows_html.append(
                            f'<tr>'
                            f'<td style="width: 25%; font-weight: 500; color: #FFF6DF;">#{i} · '
                            f'<a href="{url}" target="_blank" style="color: var(--nile); text-decoration: none;">{domain}</a></td>'
                            f'<td style="width: 40%;">{title}</td>'
                            f'<td style="width: 20%; color: var(--text-muted);">{turn_label}</td>'
                            f'<td style="width: 15%; text-align: center;"><span class="status-pill verified">Verified</span></td>'
                            f'</tr>'
                        )

                    matrix_html = f"""
                    <table class="matrix-table">
                        <thead>
                            <tr>
                                <th style="width: 25%;">Source / Registry</th>
                                <th style="width: 40%;">Title & Scope</th>
                                <th style="width: 20%;">Discovery Turn</th>
                                <th style="width: 15%; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(rows_html)}
                        </tbody>
                    </table>
                    """
                    st.markdown(matrix_html, unsafe_allow_html=True)
                else:
                    render_empty_state("☰", "No sources recorded yet", "Discovered academic papers and verified web links will appear here.")

            with tab_audit:
                verifier_log = st.session_state.node_logs.get("verifier", "")
                critic_log = st.session_state.node_logs.get("critic", "")

                if verifier_log or critic_log:
                    if verifier_log:
                        render_section_title("Truth Guard", "SLM Fact-Adjudication", "Claim-by-claim verification against primary source text.")
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                        st.markdown(f'<div class="log-pane">{verifier_log}</div>', unsafe_allow_html=True)
                    if critic_log:
                        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
                        render_section_title("Judgement", "LLM-as-a-Judge Scorecard", "Evaluates Faithfulness · Relevance · Completeness · Evidence · Clarity.")
                        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                        st.markdown(f'<div class="log-pane">{critic_log}</div>', unsafe_allow_html=True)
                else:
                    render_empty_state("⚖", "No audit traces yet", "Verification logs and quality judge scorecards will be displayed here.")

            with tab_notes:
                render_section_title("Scroll", "Research Scratchpad", "Personal notes exportable alongside the synthesis.")
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                st.session_state.scratchpad_text = st.text_area(
                    "Scratchpad Notes",
                    value=st.session_state.scratchpad_text,
                    placeholder="Jot down notes, citations, hypotheses, or snippets from the report...",
                    height=260,
                    label_visibility="collapsed",
                    key="lab_scratchpad_input"
                )
                if st.session_state.scratchpad_text:
                    st.download_button(
                        label="Export Notes (.txt)",
                        data=st.session_state.scratchpad_text,
                        file_name=f"thoth_notes_{int(time.time())}.txt",
                        mime="text/plain"
                    )


def _launch_research(runner, query: str):
    """Initializes session state and launches the async orchestrator pipeline."""
    st.session_state.topic_input = query
    st.session_state.node_statuses = ["active"] + ["pending"] * 6
    st.session_state.node_logs = {k: "" for k in st.session_state.node_logs}
    st.session_state.final_state = {}
    st.session_state.node_durations = {}
    st.session_state.chat_history = []

    runner.start(
        topic=query,
        role=st.session_state.scribe_role.lower(),
        tone=st.session_state.scribe_tone.lower(),
        language=st.session_state.scribe_language,
        scrape_top_n=st.session_state.scribe_scrape_top_n,
        min_score=st.session_state.scribe_min_score,
        max_retries=int(st.session_state.scribe_max_retries)
    )
    st.session_state.page = "lab"
    st.rerun()


# ==============================================================================
# 2. KNOWLEDGE CONSTELLATION — INTERACTIVE CONCEPT GRAPH
# ==============================================================================

def render_constellation(runner):
    """Dedicated full-canvas interactive D3 concept constellation visualizer."""
    with st.container(key="page_wrap"):
        render_section_title(
            "Knowledge Constellation",
            "Concept Mind Map & Ontology",
            "Drag, zoom, and inspect force-directed concept nodes binding topics, findings, and evidence."
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        mindmap_data = st.session_state.final_state.get("mindmap", {})
        if mindmap_data and mindmap_data.get("nodes"):
            render_interactive_mindmap(mindmap_data, height=650)
            
            # Node Inspector summary
            nodes = mindmap_data.get("nodes", [])
            edges = mindmap_data.get("edges", [])
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
            col_k1, col_k2, col_k3 = st.columns(3)
            with col_k1:
                st.markdown(f"**Total Concept Nodes:** `{len(nodes)}`")
            with col_k2:
                st.markdown(f"**Typed Relations:** `{len(edges)}`")
            with col_k3:
                st.markdown("**Graph Physics:** `Active (D3/Vis.js)`")
        elif runner.is_running():
            render_thinking("Constructing the concept constellation…")
        else:
            render_empty_state(
                "✧",
                "The constellation is unwritten",
                "Run a research inquiry from the Research Lab to generate an interactive, "
                "force-directed knowledge graph binding verified claims to source literature."
            )


# ==============================================================================
# 3. MEMORY VAULT EXPLORER — OBSIDIAN-COMPATIBLE HUB
# ==============================================================================

def render_vault_explorer():
    """Interactive Obsidian memory vault explorer with real-time hybrid RRF search."""
    with st.container(key="page_wrap"):
        render_section_title(
            "Memory Vault",
            "Obsidian Knowledge Base & Hybrid Retrieval",
            "Search, browse, and inspect markdown notes with strict claim citations, FTS5 BM25, and dense embeddings."
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # 3a. Search & Query Terminal
        col_search, col_filter = st.columns([7, 3])
        with col_search:
            vault_query = st.text_input(
                "Search Vault",
                placeholder="Query memory vault with Reciprocal Rank Fusion (BM25 + Semantic Cosine)...",
                label_visibility="collapsed",
                key="vault_search_input"
            )
        with col_filter:
            category_filter = st.selectbox(
                "Note Type Filter",
                ["All Types", "topics", "sources", "entities", "sessions"],
                label_visibility="collapsed",
                key="vault_cat_filter"
            )

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # 3b. Dual-Pane Vault Layout (Left: Note List & Search Hits | Right: Markdown Reader)
        col_list, col_reader = st.columns([40, 60], gap="large")

        with col_list:
            if vault_query.strip():
                st.markdown(f"**Hybrid Search Hits for:** *'{vault_query.strip()}'*")
                hits = search_memory_vault(vault_query.strip(), top_k=10)
                if hits:
                    for h in hits:
                        nid = h.get("note_id", "")
                        ntype = h.get("type", "topics")
                        score = h.get("rrf_score", 0.0)
                        
                        card_html = f"""
                        <div class="search-hit-box">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <span class="vault-badge {ntype}">{ntype}</span>
                                <span class="score-tag-rrf">RRF {score:.4f}</span>
                            </div>
                            <div style="font-weight:600; color:var(--text-primary); margin-bottom:4px;">{nid}</div>
                        </div>
                        """
                        st.markdown(card_html, unsafe_allow_html=True)
                        if st.button(f"Inspect {nid}", key=f"hit_btn_{nid}", use_container_width=True):
                            st.session_state.selected_vault_note = nid
                else:
                    st.info("No matching notes found via hybrid search.")
            else:
                cat_filter = None if category_filter == "All Types" else category_filter
                all_notes = list_vault_notes(note_type=cat_filter)
                st.markdown(f"**Vault Archive ({len(all_notes)} notes):**")
                
                if all_notes:
                    for nid in all_notes[:25]:
                        if st.button(f"📄 {nid}", key=f"note_btn_{nid}", use_container_width=True):
                            st.session_state.selected_vault_note = nid
                else:
                    render_empty_state("🗄", "Vault folder is empty", "Notes generated during verified research turns will appear here.")

        with col_reader:
            selected_note_id = st.session_state.get("selected_vault_note")
            if selected_note_id:
                note_data = read_vault_note(selected_note_id)
                if note_data:
                    fm = note_data.get("frontmatter", {})
                    content = note_data.get("content", "")
                    ntype = fm.get("type", "topics")
                    conf = fm.get("confidence", 1.0)
                    sources = fm.get("sources", [])
                    created = fm.get("created", "")

                    st.markdown(
                        f"""
                        <div class="vault-card">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                                <span class="vault-badge {ntype}">{ntype}</span>
                                <span style="font-size:0.75rem; color:var(--text-muted);">Confidence: <b>{conf*100:.0f}%</b> | Created: {created[:19]}</span>
                            </div>
                            <h3 style="font-family:'Cinzel', serif; color:var(--gold-bright); margin:0 0 10px 0;">{selected_note_id}</h3>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    if sources:
                        st.markdown("**Cites Sources:**")
                        pills = "".join([f'<span class="wikilink-pill">[[{s}]]</span>' for s in sources])
                        st.markdown(f"<div>{pills}</div>", unsafe_allow_html=True)
                        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

                    st.markdown("#### Note Body")
                    st.markdown(content)

                    # Graph Neighborhood
                    neighbors = traverse_vault_graph(start_note=selected_note_id, max_depth=1)
                    if neighbors:
                        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
                        st.markdown("**1-Hop Graph Connections:**")
                        for nb in neighbors[:6]:
                            st.markdown(f"- `{nb.get('target')}` (relation: *{nb.get('relation')}*)")
                else:
                    st.error(f"Failed to read note {selected_note_id}.")
            else:
                render_empty_state("📄", "Select a note", "Click any note from the list on the left to read its markdown content and metadata.")


# ==============================================================================
# 4. CODEX HISTORY — SQLITE SESSIONS & PERSISTENT REPORTS
# ==============================================================================

def render_codex_history(runner):
    """Searchable library of past SQLite research sessions and generated reports."""
    with st.container(key="page_wrap"):
        render_section_title(
            "Codex History",
            "Persistent Research Archive",
            "Browse, inspect, and reload previous research sessions and reports stored in SQLite."
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        reports = list_stored_reports(limit=40)
        sessions = list_stored_sessions(limit=40)

        if not reports and not sessions:
            render_empty_state(
                "📜",
                "No previous sessions in SQLite",
                "Every completed research turn in the Research Lab is saved permanently to the database."
            )
            return

        tab_reps, tab_sess = st.tabs([f"Stored Reports ({len(reports)})", f"Sessions ({len(sessions)})"])

        with tab_reps:
            for r in reports:
                rid = r.get("report_id", "")
                topic = r.get("topic", "Untitled Topic")
                score = r.get("score", 0.0)
                created = r.get("created_at", "")
                content = r.get("content", "")

                with st.container():
                    st.markdown(
                        f"""
                        <div class="history-card">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-family:'Cinzel', serif; font-size:1.1rem; color:var(--gold-bright);">{topic}</span>
                                <span class="score-tag-rrf">Score: {score:.1f}/10</span>
                            </div>
                            <div style="font-size:0.78rem; color:var(--text-muted); margin:6px 0 10px 0;">
                                ID: <code>{rid}</code> | Saved: {created[:19]} | Words: {len(content.split())}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    col_r1, col_r2 = st.columns([1, 4])
                    with col_r1:
                        if st.button("✦ Restore to Lab", key=f"restore_rep_{rid}"):
                            st.session_state.topic_input = topic
                            st.session_state.final_state = {
                                "topic": topic,
                                "report": content,
                                "score": score,
                                "verifier_feedback": r.get("verifier_feedback", ""),
                                "mindmap": json.loads(r["mindmap_json"]) if r.get("mindmap_json") else {}
                            }
                            st.session_state.chat_history = []
                            st.session_state.page = "lab"
                            st.success("Session restored to Research Lab.")
                            st.rerun()
                    with col_r2:
                        with st.expander("Preview Synthesis"):
                            st.markdown(content[:600] + ("..." if len(content) > 600 else ""))

        with tab_sess:
            for s in sessions:
                sid = s.get("session_id", "")
                title = s.get("title", "Untitled Session")
                summary = s.get("summary", "")
                created = s.get("created_at", "")

                st.markdown(
                    f"""
                    <div class="history-card">
                        <div style="font-weight:600; color:var(--gold-bright);">{title}</div>
                        <div style="font-size:0.75rem; color:var(--text-muted); margin:4px 0;">ID: <code>{sid}</code> | Created: {created[:19]}</div>
                        <div style="font-size:0.85rem; color:var(--text-secondary);">{summary}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


# ==============================================================================
# 5. TELEMETRY & ORACLE SETTINGS
# ==============================================================================

def render_telemetry_settings():
    """Real-time Dispatcher Circuit Breaker health dashboard, LLM failovers, and Scribe controls."""
    with st.container(key="page_wrap"):
        render_section_title(
            "Telemetry & Oracle Control",
            "System Health & Model Calibration",
            "Live Dispatcher circuit breaker status, LLM provider failover metrics, and research parameters."
        )
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        telemetry = get_telemetry_status()
        cb_state = telemetry.get("circuit_breaker_state", "CLOSED").lower()

        # Telemetry HUD Cards
        st.markdown(
            f"""
            <div class="telemetry-grid">
                <div class="telemetry-tile">
                    <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Circuit Breaker</div>
                    <div style="margin-bottom:6px;"><span class="circuit-badge {cb_state}">● {cb_state.upper()}</span></div>
                    <div style="font-size:0.72rem; color:var(--text-secondary);">Cooldown: {telemetry.get('circuit_breaker_cooloff', 0.0)}s</div>
                </div>
                <div class="telemetry-tile">
                    <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Primary Provider</div>
                    <div style="font-weight:600; color:var(--gold-bright); font-size:0.9rem;">{telemetry.get('primary_provider')}</div>
                    <div style="font-size:0.72rem; color:var(--ok);">✓ Healthy & Verified</div>
                </div>
                <div class="telemetry-tile">
                    <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Fallback Provider</div>
                    <div style="font-weight:600; color:var(--aether); font-size:0.9rem;">{telemetry.get('fallback_provider')}</div>
                    <div style="font-size:0.72rem; color:var(--text-muted);">Auto-trips on 5xx errors</div>
                </div>
                <div class="telemetry-tile">
                    <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Vault & Database</div>
                    <div style="font-weight:600; color:var(--nile); font-size:0.9rem;">{telemetry.get('vault_notes_count', 0)} notes · {telemetry.get('db_size_kb', 0)} KB</div>
                    <div style="font-size:0.72rem; color:var(--text-muted);">SQLite FTS5 + MiniLM Embeddings</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # Scribe Configuration Cards
        col1, col2, col3 = st.columns(3, gap="large")

        with col1:
            with st.container(key="settings_card_persona"):
                st.markdown('<div class="settings-tile-title">✦ Persona</div>', unsafe_allow_html=True)
                st.markdown('<div class="settings-tile-sub">Who Thoth writes as, and how it speaks.</div>', unsafe_allow_html=True)
                st.selectbox(
                    "Target Role",
                    ["Senior Academic Researcher", "Technical Copywriter", "Financial Analyst", "Staff Software Engineer", "Biomedical Scientist"],
                    key="scribe_role"
                )
                st.selectbox(
                    "Tone",
                    ["Formal & Analytical", "Informative & Casual", "Executive Summary", "Investigative & In-Depth"],
                    key="scribe_tone"
                )
                st.selectbox(
                    "Language",
                    ["English", "Hindi", "Spanish", "French", "German", "Japanese"],
                    key="scribe_language"
                )

        with col2:
            with st.container(key="settings_card_depth"):
                st.markdown('<div class="settings-tile-title">📖 Research Depth</div>', unsafe_allow_html=True)
                st.markdown('<div class="settings-tile-sub">Concurrent scrape budget per inquiry.</div>', unsafe_allow_html=True)
                st.slider("Pages to Scrape", min_value=1, max_value=5, key="scribe_scrape_top_n")
                st.markdown(
                    "<div class='sidebar-note' style='margin-top:20px;'>More pages means richer literature "
                    "grounding but longer Reader phases.</div>",
                    unsafe_allow_html=True
                )

        with col3:
            with st.container(key="settings_card_thresholds"):
                st.markdown('<div class="settings-tile-title">⚖ Quality Gate Thresholds</div>', unsafe_allow_html=True)
                st.markdown('<div class="settings-tile-sub">Calibrate critic feedback loops.</div>', unsafe_allow_html=True)
                st.slider("Min Quality Score", min_value=0.0, max_value=10.0, step=0.5, key="scribe_min_score")
                st.number_input("Max Critic Retries", min_value=1, max_value=5, key="scribe_max_retries")
                st.markdown(
                    "<div class='sidebar-note'>Thoth weighs every assertion before a word is inscribed. "
                    "Higher scores ensure rigorous synthesis.</div>",
                    unsafe_allow_html=True
                )
