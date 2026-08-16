import streamlit as st
import streamlit.components.v1 as components
import json

AURORA_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    /* Base Palette: Near-Black / Deep Charcoal */
    --bg-base:        #0C0D12;
    --bg-surface:     #13151F;
    --bg-elevated:    #181A26;
    --bg-glow:        radial-gradient(circle at 20% -10%, rgba(124,58,237,0.12), transparent 50%),
                       radial-gradient(circle at 90% 10%, rgba(6,182,212,0.08), transparent 45%);

    /* Single Signature Accent Hue */
    --accent:         #7C3AED;
    --accent-glow:    rgba(124, 58, 237, 0.35);
    --accent-subtle:  rgba(124, 58, 237, 0.12);
    --accent-border:  rgba(124, 58, 237, 0.28);
    --aurora:         linear-gradient(120deg, #4F46E5 0%, #7C3AED 45%, #06B6D4 100%);

    /* 4-Step Gray Scale & Borders */
    --card:           rgba(255, 255, 255, 0.04);
    --card-hover:     rgba(255, 255, 255, 0.07);
    --border:         rgba(255, 255, 255, 0.10);
    --border-subtle:  rgba(255, 255, 255, 0.06);
    --border-hover:   rgba(255, 255, 255, 0.20);

    /* Muted Semantic Colors */
    --ok:             #34D399;
    --ok-bg:          rgba(52, 211, 153, 0.10);
    --ok-border:      rgba(52, 211, 153, 0.24);
    --warn:           #FBBF24;
    --warn-bg:        rgba(251, 191, 36, 0.10);
    --warn-border:    rgba(251, 191, 36, 0.24);
    --error:          #F87171;
    --error-bg:       rgba(248, 113, 113, 0.10);
    --error-border:   rgba(248, 113, 113, 0.24);
    --idle:           #52525B;

    /* Text Scale */
    --text-primary:   #F4F4F6;
    --text-secondary: #A1A1AA;
    --text-muted:     #71717A;
    --text-faint:     #52525B;

    /* Spacing System (4/8/12/16/24/32px) */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-6: 24px;
    --space-8: 32px;

    --radius:    12px;
    --radius-sm: 8px;
    --radius-pill: 999px;
    --ease:      cubic-bezier(0.4, 0, 0.2, 1);
}

/* App shell */
.stApp {
    background-color: var(--bg-base) !important;
    background-image: var(--bg-glow) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary) !important;
}

header[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding-top: 1.5rem !important; max-width: 1360px !important; }

/* Ambient background glow */
.aurora-blob {
    position: fixed;
    border-radius: 50%;
    filter: blur(100px);
    opacity: 0.15;
    z-index: 0;
    pointer-events: none;
}
.blob-1 { width: 440px; height: 440px; background: #7C3AED; top: -100px; left: -100px; }
.blob-2 { width: 380px; height: 380px; background: #06B6D4; bottom: -100px; right: -80px; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #090A0E !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { color: var(--text-primary); }

/* Form Controls & High-Contrast Inputs */
.stTextInput input, .stTextArea textarea {
    background-color: var(--bg-surface) !important;
    color: #FFFFFF !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.92rem !important;
    padding: var(--space-2) var(--space-3) !important;
    transition: border-color 0.2s var(--ease);
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent-border) !important;
}
.stWidgetLabel p, label[data-testid="stWidgetLabel"], label {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    margin-bottom: var(--space-1) !important;
}

/* BaseWeb Select Boxes */
div[data-baseweb="select"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}
div[data-baseweb="select"] > div {
    background-color: var(--bg-surface) !important;
    color: #FFFFFF !important;
}
div[data-baseweb="select"] span, div[data-baseweb="select"] div, div[data-baseweb="select"] p {
    color: #FFFFFF !important;
}
div[data-baseweb="select"] svg { fill: #FFFFFF !important; }
div[data-baseweb="popover"], ul[role="listbox"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border-hover) !important;
    color: #FFFFFF !important;
}
li[role="option"] {
    background-color: var(--bg-surface) !important;
    color: #FFFFFF !important;
}
li[role="option"]:hover, li[aria-selected="true"] {
    background-color: var(--accent-subtle) !important;
    color: #FFFFFF !important;
}

/* Primary and Download Action Buttons */
.stButton > button, 
.stDownloadButton > button, 
div[data-testid="stDownloadButton"] > button {
    position: relative !important;
    overflow: hidden !important;
    background: var(--aurora) !important;
    background-size: 200% 200% !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    color: #FFFFFF !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 0.55rem 1.3rem !important;
    transition: transform 0.15s var(--ease), box-shadow 0.25s var(--ease) !important;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4) !important;
}
.stButton > button:hover, 
.stDownloadButton > button:hover, 
div[data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px var(--accent-glow) !important;
    color: #FFFFFF !important;
}
.stButton > button p, .stDownloadButton > button p, .stButton > button span, .stDownloadButton > button span {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* Expander Dark Card Styling */
div[data-testid="stExpander"] {
    background-color: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    overflow: hidden !important;
    margin-bottom: var(--space-3) !important;
}
div[data-testid="stExpander"] details { background-color: var(--bg-surface) !important; }
div[data-testid="stExpander"] details summary {
    background-color: var(--bg-surface) !important;
    color: #FFFFFF !important;
    border-radius: var(--radius-sm) !important;
    padding: var(--space-2) var(--space-3) !important;
}
div[data-testid="stExpander"] details summary:hover { background-color: var(--bg-elevated) !important; }
div[data-testid="stExpander"] details summary p, 
div[data-testid="stExpander"] details summary span,
div[data-testid="stExpander"] summary * {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    fill: #FFFFFF !important;
}
.streamlit-expanderHeader {
    background-color: var(--bg-surface) !important;
    color: #FFFFFF !important;
}

/* ==========================================================================
   1. HORIZONTAL AGENT PLANNER STEPPER RAIL
   ========================================================================== */
.planner-stepper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-4);
    width: 100%;
}
.step-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: 0.82rem;
    cursor: default;
    transition: all 0.2s var(--ease);
}
.step-item.pending {
    color: var(--text-muted);
}
.step-item.active {
    color: #FFFFFF;
    font-weight: 600;
}
.step-item.done {
    color: var(--text-secondary);
}
.step-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    transition: background 0.3s var(--ease), box-shadow 0.3s var(--ease);
}
.step-item.pending .step-dot { background: var(--idle); }
.step-item.active .step-dot {
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
    animation: step-pulse 1.8s infinite;
}
.step-item.done .step-dot { background: var(--ok); }
.step-divider {
    flex: 1;
    height: 1px;
    background: var(--border);
    margin: 0 var(--space-3);
}
@keyframes step-pulse {
    0%   { box-shadow: 0 0 0 0 rgba(124,58,237,0.6); }
    70%  { box-shadow: 0 0 0 6px rgba(124,58,237,0); }
    100% { box-shadow: 0 0 0 0 rgba(124,58,237,0); }
}

/* ==========================================================================
   2. STICKY TABS WITH ACCENT UNDERLINE & BADGES
   ========================================================================== */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: var(--space-4) !important;
    padding-bottom: 0px !important;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    border: none !important;
    color: var(--text-secondary) !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    padding: var(--space-2) var(--space-3) !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.2s var(--ease), border-color 0.2s var(--ease) !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #FFFFFF !important;
}
.stTabs [aria-selected="true"] {
    color: #FFFFFF !important;
    font-weight: 600 !important;
    border-bottom: 2px solid var(--accent) !important;
}
.tab-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    font-size: 0.72rem;
    font-weight: 600;
    padding: 1px 6px;
    margin-left: 6px;
    color: var(--text-secondary);
}
.tab-badge.highlight {
    background: var(--accent-subtle);
    border-color: var(--accent-border);
    color: #FFFFFF;
}

/* ==========================================================================
   3. EDITORIAL PROSE TYPOGRAPHY (SYNTHESIS REPORT ONLY)
   ========================================================================== */
.editorial-prose {
    font-family: 'Newsreader', Georgia, serif !important;
    font-size: 1.06rem !important;
    line-height: 1.78 !important;
    color: #F4F4F6 !important;
    letter-spacing: -0.005em !important;
}
.editorial-prose p {
    font-family: 'Newsreader', Georgia, serif !important;
    margin-bottom: 1.25rem !important;
    color: #EAEAEA !important;
}
.editorial-prose h1, .editorial-prose h2, .editorial-prose h3, .editorial-prose h4 {
    font-family: 'Inter', sans-serif !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    margin-top: 1.8rem !important;
    margin-bottom: 0.8rem !important;
    letter-spacing: -0.02em !important;
}
.editorial-prose h3 {
    font-size: 1.35rem !important;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 0.4rem;
}
.editorial-prose strong, .editorial-prose b {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}
.editorial-prose blockquote {
    border-left: 3px solid var(--accent) !important;
    background: var(--accent-subtle) !important;
    padding: var(--space-3) var(--space-4) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
    color: #E4E4E7 !important;
    font-style: italic !important;
    margin: 1.4rem 0 !important;
}

/* ==========================================================================
   4. DENSE DATA TABLE (LITERATURE REVIEW MATRIX)
   ========================================================================== */
.matrix-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: var(--space-3);
    font-family: 'Inter', sans-serif;
    font-size: 0.85rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    overflow: hidden;
}
.matrix-table th {
    background-color: var(--bg-surface);
    color: #FFFFFF;
    font-weight: 600;
    text-align: left;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 0.82rem;
    letter-spacing: 0.02em;
}
.matrix-table td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    vertical-align: top;
    line-height: 1.55;
}
.matrix-table tr:nth-child(even) {
    background-color: rgba(255, 255, 255, 0.02);
}
.matrix-table tr:hover {
    background-color: rgba(255, 255, 255, 0.04);
}
.status-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    font-size: 0.75rem;
    font-weight: 600;
}
.status-pill.verified {
    background: var(--ok-bg);
    border: 1px solid var(--ok-border);
    color: var(--ok);
}
.status-pill.flagged {
    background: var(--warn-bg);
    border: 1px solid var(--warn-border);
    color: var(--warn);
}
.status-pill.contradicted {
    background: var(--error-bg);
    border: 1px solid var(--error-border);
    color: var(--error);
}

/* ==========================================================================
   5. CHAT BUBBLES & COPILOT CONVERSATION
   ========================================================================== */
.chat-container {
    max-width: 680px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding-bottom: var(--space-6);
}
.chat-msg-user {
    align-self: flex-end;
    background: var(--accent-subtle);
    border: 1px solid var(--accent-border);
    color: #FFFFFF;
    padding: var(--space-3) var(--space-4);
    border-radius: 14px 14px 2px 14px;
    max-width: 85%;
    font-size: 0.92rem;
    line-height: 1.55;
}
.chat-msg-agent {
    align-self: flex-start;
    color: var(--text-primary);
    padding: 0;
    max-width: 100%;
    font-size: 0.92rem;
    line-height: 1.65;
}
.suggestion-scroll-row {
    display: flex;
    gap: var(--space-2);
    overflow-x: auto;
    padding: var(--space-2) 0;
    scrollbar-width: thin;
    margin-top: var(--space-2);
}
.suggestion-pill {
    flex-shrink: 0;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    color: var(--text-secondary);
    padding: 4px 12px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.2s var(--ease);
}
.suggestion-pill:hover {
    border-color: var(--accent);
    color: #FFFFFF;
    background: var(--accent-subtle);
}

/* Citation Chip */
.chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.25rem 0.65rem;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.04);
    color: var(--text-primary) !important;
    text-decoration: none;
    transition: border-color 0.2s var(--ease), background 0.2s var(--ease);
}
.chip:hover {
    border-color: var(--border-hover);
    background: var(--card-hover);
    color: #FFFFFF !important;
}
.chip-dot { width: 7px; height: 7px; border-radius: 50%; }

/* Log Pane */
.log-pane {
    font-family: 'Space Grotesk', monospace;
    font-size: 0.82rem;
    line-height: 1.55;
    color: #C9CBD3;
    background: #08090D;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-3);
    max-height: 260px;
    overflow-y: auto;
    white-space: pre-wrap;
}

/* Follow-up Route Badges */
.route-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    margin-bottom: 6px;
}
.route-badge.local-qa {
    background: rgba(124, 58, 237, 0.15);
    border: 1px solid rgba(124, 58, 237, 0.35);
    color: #C4B5FD;
}
.route-badge.web-search {
    background: rgba(6, 182, 212, 0.15);
    border: 1px solid rgba(6, 182, 212, 0.35);
    color: #67E8F9;
}
.route-badge.report-expansion {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.35);
    color: #6EE7B7;
}

/* Mind Map Container */
.mindmap-frame {
    background: #090A0E;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    margin-top: var(--space-2);
}
</style>
"""

def inject_theme():
    """Injects the Aurora Dark CSS into the Streamlit app."""
    st.markdown(AURORA_CSS, unsafe_allow_html=True)

def render_blobs():
    """Renders subtle background ambient glow blobs."""
    st.markdown('<div class="aurora-blob blob-1"></div><div class="aurora-blob blob-2"></div>', unsafe_allow_html=True)

def render_header():
    """Renders clean title and subtitle."""
    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
            <div>
                <span style="font-weight: 700; font-size: 1.5rem; background: var(--aurora); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">✦ Thoth: Agentic Research ✦</span>
                <span style="color: var(--text-muted); font-size: 0.9rem; margin-left: 8px;">Autonomous Multi-Agent Workspace</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_planner_stepper(active_idx: int, statuses: list, durations: dict = None):
    """
    Renders a compact horizontal stepper progress rail pinned to the top of the workspace pane.
    """
    NODES = [
        ("Search", "Querying registries"),
        ("Reader", "Scraping full text"),
        ("Writer", "Drafting synthesis"),
        ("Verifier", "Fact verification"),
        ("Critic", "Quality evaluation"),
        ("Mind Map", "Concept graph"),
        ("Follow-Up", "Deep dive ready")
    ]
    durations = durations or {}
    
    items_html = []
    for i, (name, desc) in enumerate(NODES):
        s = statuses[i] if i < len(statuses) else "pending"
        dur_str = f" ({durations[name]:.1f}s)" if name in durations else ""
        
        items_html.append(
            f'<div class="step-item {s}">'
            f'<div class="step-dot"></div>'
            f'<span>{name}{dur_str}</span>'
            f'</div>'
        )
        if i < len(NODES) - 1:
            items_html.append('<div class="step-divider"></div>')
            
    stepper_html = f'<div class="planner-stepper">{"".join(items_html)}</div>'
    st.markdown(stepper_html, unsafe_allow_html=True)

def render_interactive_mindmap(mindmap_data: dict, height: int = 500):
    """
    Renders a dynamic, dark-themed interactive force-directed graph (Concept Mind Map)
    using vis.js within an isolated HTML component.
    """
    if not mindmap_data or not mindmap_data.get("nodes"):
        st.info("✦ Concept Mind Map will appear here once initial research synthesis is completed.")
        return

    # Palette configurations for node types
    COLOR_MAP = {
        "topic": {"bg": "#7C3AED", "border": "#A78BFA", "highlight": "#C4B5FD"},
        "subtopic": {"bg": "#0284C7", "border": "#38BDF8", "highlight": "#7DD3FC"},
        "finding": {"bg": "#059669", "border": "#34D399", "highlight": "#6EE7B7"},
        "source": {"bg": "#D97706", "border": "#FBBF24", "highlight": "#FDE68A"},
        "followup": {"bg": "#DB2777", "border": "#F472B6", "highlight": "#FBCFE8"}
    }

    vis_nodes = []
    for n in mindmap_data.get("nodes", []):
        ntype = n.get("type", "finding")
        colors = COLOR_MAP.get(ntype, COLOR_MAP["finding"])
        label = n.get("label", "Concept")
        details = n.get("details", "")
        url = n.get("url", "")
        
        # Tooltip HTML
        title_tooltip = f"<b>{label}</b><br><span style='font-size:11px;color:#CBD5E1;'>{details}</span>"
        if url:
            title_tooltip += f"<br><a href='{url}' target='_blank' style='color:#38BDF8;font-size:10px;'>{url}</a>"
            
        vis_nodes.append({
            "id": n.get("id"),
            "label": label if len(label) < 28 else label[:25] + "...",
            "title": title_tooltip,
            "shape": "box" if ntype in ["topic", "subtopic"] else "dot",
            "size": 25 if ntype == "topic" else (18 if ntype == "subtopic" else 12),
            "color": {
                "background": colors["bg"],
                "border": colors["border"],
                "highlight": {"background": colors["highlight"], "border": "#FFFFFF"}
            },
            "font": {
                "color": "#FFFFFF",
                "face": "Inter, sans-serif",
                "size": 13 if ntype == "topic" else (11 if ntype == "subtopic" else 10)
            },
            "margin": 8,
            "borderWidth": 1.5,
            "shadow": {"enabled": True, "color": "rgba(0,0,0,0.5)", "size": 6}
        })

    vis_edges = []
    for e in mindmap_data.get("edges", []):
        vis_edges.append({
            "from": e.get("from") or e.get("source"),
            "to": e.get("to") or e.get("target"),
            "label": e.get("label", ""),
            "color": {"color": "rgba(255,255,255,0.18)", "highlight": "#A78BFA"},
            "font": {"color": "#94A3B8", "size": 9, "align": "middle"},
            "arrows": "to",
            "smooth": {"type": "cubicBezier", "roundness": 0.4}
        })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
                background: #090A0E;
                overflow: hidden;
                font-family: 'Inter', sans-serif;
            }}
            #mindmap-container {{
                width: 100%;
                height: {height}px;
                background: radial-gradient(circle at center, #13151F 0%, #090A0E 100%);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
            }}
            .legend {{
                position: absolute;
                bottom: 12px;
                left: 12px;
                background: rgba(12, 13, 18, 0.85);
                backdrop-filter: blur(8px);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 6px 12px;
                display: flex;
                gap: 12px;
                font-size: 11px;
                color: #94A3B8;
                pointer-events: none;
                z-index: 10;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .legend-dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
            }}
        </style>
    </head>
    <body>
        <div id="mindmap-container"></div>
        <div class="legend">
            <div class="legend-item"><div class="legend-dot" style="background:#7C3AED;"></div> Topic</div>
            <div class="legend-item"><div class="legend-dot" style="background:#0284C7;"></div> Sub-Theme</div>
            <div class="legend-item"><div class="legend-dot" style="background:#059669;"></div> Finding</div>
            <div class="legend-item"><div class="legend-dot" style="background:#D97706;"></div> Source</div>
            <div class="legend-item"><div class="legend-dot" style="background:#DB2777;"></div> Follow-Up</div>
        </div>

        <script type="text/javascript">
            const nodes = new vis.DataSet({nodes_json});
            const edges = new vis.DataSet({edges_json});

            const container = document.getElementById('mindmap-container');
            const data = {{ nodes: nodes, edges: edges }};
            const options = {{
                nodes: {{
                    borderWidthSelected: 2
                }},
                edges: {{
                    width: 1.2
                }},
                physics: {{
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{
                        gravitationalConstant: -38,
                        centralGravity: 0.008,
                        springLength: 80,
                        springConstant: 0.12,
                        damping: 0.88
                    }},
                    stabilization: {{ iterations: 120 }}
                }},
                interaction: {{
                    hover: true,
                    tooltipDelay: 100,
                    zoomView: true,
                    dragView: true
                }}
            }};

            const network = new vis.Network(container, data, options);
        </script>
    </body>
    </html>
    """
    if hasattr(st, "html"):
        st.html(html_code)
    else:
        components.html(html_code, height=height + 10)

def render_copy_widget(text_to_copy: str, button_label: str = "Copy Markdown"):
    """Renders a fast HTML/JS copy-to-clipboard widget."""
    escaped_json = json.dumps(text_to_copy)
    copy_html = f"""
    <button id="copy-btn" style="
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.14);
        color: #F4F4F6;
        padding: 0.55rem 1.2rem;
        border-radius: 8px;
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
        width: 100%;
    ">{button_label}</button>
    <script>
        const btn = document.getElementById('copy-btn');
        const text = {escaped_json};
        btn.addEventListener('click', () => {{
            navigator.clipboard.writeText(text).then(() => {{
                btn.innerText = '✓ Copied!';
                btn.style.borderColor = '#34D399';
                btn.style.color = '#34D399';
                setTimeout(() => {{
                    btn.innerText = '{button_label}';
                    btn.style.borderColor = 'rgba(255,255,255,0.14)';
                    btn.style.color = '#F4F4F6';
                }}, 2200);
            }}).catch(err => {{
                console.error('Copy failed', err);
            }});
        }});
        btn.addEventListener('mouseenter', () => {{
            btn.style.background = 'rgba(255,255,255,0.12)';
        }});
        btn.addEventListener('mouseleave', () => {{
            btn.style.background = 'rgba(255,255,255,0.06)';
        }});
    </script>
    """
    if hasattr(st, "html"):
        st.html(copy_html)
    else:
        components.html(copy_html, height=45)

# Backwards compatibility alias
render_pipeline = render_planner_stepper

