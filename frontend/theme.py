"""
Thoth · Design System
=====================
"Hall of Wisdom" — a dark, dimensional, glass-and-gold interface inspired by
the mythic archives of the god of knowledge: obsidian marble, oracle light,
constellation gold and deep aurora nebulae.

This module owns *presentation only*. No pipeline / agent logic lives here.

Public API (unchanged, plus additions):
    inject_theme()
    render_blobs()
    render_header()
    render_planner_stepper(active_idx, statuses, durations)
    render_interactive_mindmap(mindmap_data, height)
    render_copy_widget(text_to_copy, button_label)

New helpers:
    render_hero(active=False)
    render_oracle_stats(stats)
    render_section_title(kicker, title, subtitle)
    render_empty_state(glyph, title, body)
    render_chat_bubble(role, text, badge_label, badge_class)
    render_scroll_divider()
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import random

# ==============================================================================
# DESIGN TOKENS + GLOBAL STYLESHEET
# ==============================================================================

AURORA_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;600;700&family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    /* ---- Obsidian base ---------------------------------------------- */
    --bg-void:        #05060B;
    --bg-base:        #080911;
    --bg-surface:     #0E1019;
    --bg-elevated:    #141726;

    /* ---- Oracle light: gold + aurora -------------------------------- */
    --gold:           #E7C77B;
    --gold-bright:    #FFE9B0;
    --gold-deep:      #A9821F;
    --gold-glow:      rgba(231, 199, 123, 0.35);
    --gold-subtle:    rgba(231, 199, 123, 0.10);
    --gold-border:    rgba(231, 199, 123, 0.26);

    --lapis:          #5B7CFA;
    --aether:         #7C5CFF;
    --nile:           #2FD8C6;

    --aurora:         linear-gradient(115deg, #E7C77B 0%, #C9A227 26%, #7C5CFF 62%, #2FD8C6 100%);
    --aurora-soft:    linear-gradient(115deg, rgba(231,199,123,.18), rgba(124,92,255,.16) 55%, rgba(47,216,198,.14));

    /* ---- Glass ------------------------------------------------------- */
    --glass:          rgba(255, 255, 255, 0.045);
    --glass-strong:   rgba(255, 255, 255, 0.075);
    --glass-hover:    rgba(255, 255, 255, 0.10);
    --border:         rgba(255, 255, 255, 0.10);
    --border-subtle:  rgba(255, 255, 255, 0.055);
    --border-hover:   rgba(255, 255, 255, 0.22);
    --blur:           saturate(150%) blur(22px);

    /* ---- Semantic ---------------------------------------------------- */
    --ok:             #4ADE9B;
    --ok-bg:          rgba(74, 222, 155, 0.10);
    --ok-border:      rgba(74, 222, 155, 0.26);
    --warn:           #FBBF24;
    --warn-bg:        rgba(251, 191, 36, 0.10);
    --warn-border:    rgba(251, 191, 36, 0.26);
    --error:          #F87171;
    --error-bg:       rgba(248, 113, 113, 0.10);
    --error-border:   rgba(248, 113, 113, 0.26);
    --idle:           #4B4F5C;

    /* legacy aliases (kept so older markup keeps rendering) */
    --accent:         var(--gold);
    --accent-glow:    var(--gold-glow);
    --accent-subtle:  var(--gold-subtle);
    --accent-border:  var(--gold-border);
    --card:           var(--glass);
    --card-hover:     var(--glass-hover);

    /* ---- Text -------------------------------------------------------- */
    --text-primary:   #F3F1EA;
    --text-secondary: #A7A9B8;
    --text-muted:     #767A8B;
    --text-faint:     #4E5262;

    /* ---- Geometry ---------------------------------------------------- */
    --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
    --space-4: 16px; --space-6: 24px; --space-8: 32px;
    --radius:      16px;
    --radius-sm:   10px;
    --radius-lg:   22px;
    --radius-pill: 999px;
    --ease:        cubic-bezier(0.22, 1, 0.36, 1);

    /* ---- Depth (the "3D" language) ----------------------------------- */
    --lift-1: 0 1px 0 rgba(255,255,255,.06) inset, 0 8px 24px -12px rgba(0,0,0,.9);
    --lift-2: 0 1px 0 rgba(255,255,255,.08) inset, 0 24px 60px -24px rgba(0,0,0,.95),
              0 0 0 1px rgba(255,255,255,.04);
    --lift-gold: 0 0 0 1px var(--gold-border), 0 18px 48px -22px rgba(231,199,123,.55),
                 0 1px 0 rgba(255,255,255,.14) inset;
}

/* ======================= APP SHELL ======================= */
.stApp {
    background-color: var(--bg-void) !important;
    background-image:
        radial-gradient(1200px 620px at 12% -12%, rgba(124,92,255,0.16), transparent 62%),
        radial-gradient(900px 520px at 92% 4%, rgba(47,216,198,0.10), transparent 58%),
        radial-gradient(760px 420px at 50% 108%, rgba(231,199,123,0.10), transparent 60%),
        linear-gradient(180deg, #05060B 0%, #080911 60%, #05060B 100%) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary) !important;
}

/* faint hieroglyphic star-grid overlay */
.stApp::before {
    content: "";
    position: fixed; inset: 0;
    background-image:
        linear-gradient(rgba(255,255,255,.022) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.022) 1px, transparent 1px);
    background-size: 64px 64px;
    mask-image: radial-gradient(ellipse at 50% 0%, #000 0%, transparent 78%);
    pointer-events: none;
    z-index: 0;
}

header[data-testid="stHeader"] { background: transparent !important; }
#MainMenu, footer { visibility: hidden; }
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 3rem !important;
    max-width: 1480px !important;
    position: relative; z-index: 1;
}

::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(231,199,123,.18);
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background: rgba(231,199,123,.34); background-clip: content-box; }

::selection { background: rgba(231,199,123,.28); color: #FFF; }

/* ======================= AMBIENT DEPTH LAYER ======================= */
.aurora-blob {
    position: fixed;
    border-radius: 50%;
    filter: blur(120px);
    opacity: 0.20;
    z-index: 0;
    pointer-events: none;
    will-change: transform;
}
.blob-1 { width: 520px; height: 520px; background: #7C5CFF; top: -160px;  left: -140px;  animation: drift-a 26s var(--ease) infinite alternate; }
.blob-2 { width: 460px; height: 460px; background: #2FD8C6; bottom: -180px; right: -120px; animation: drift-b 32s var(--ease) infinite alternate; }
.blob-3 { width: 380px; height: 380px; background: #E7C77B; top: 42%; left: 46%; opacity: .12; animation: drift-c 38s var(--ease) infinite alternate; }

@keyframes drift-a { to { transform: translate3d(90px, 70px, 0) scale(1.15); } }
@keyframes drift-b { to { transform: translate3d(-80px, -60px, 0) scale(1.1); } }
@keyframes drift-c { to { transform: translate3d(-120px, 60px, 0) scale(1.2); } }

/* thin gold horizon line under the header */
.horizon {
    height: 1px; width: 100%;
    background: linear-gradient(90deg, transparent, var(--gold-border) 18%, rgba(124,92,255,.35) 50%, var(--gold-border) 82%, transparent);
    margin: 6px 0 18px 0;
}

/* ======================= HERO / HEADER ======================= */
.thoth-header {
    position: relative;
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--space-6);
    padding: 18px 26px;
    border-radius: var(--radius-lg);
    background:
        linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02)),
        rgba(10,11,18,.55);
    border: 1px solid var(--border);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-2);
    overflow: hidden;
    transform-style: preserve-3d;
}
.thoth-header::after {
    content: "";
    position: absolute; inset: -40% -10% auto -10%; height: 180%;
    background: var(--aurora-soft);
    filter: blur(46px);
    opacity: .55;
    pointer-events: none;
}
.thoth-mark {
    position: relative; z-index: 2;
    display: flex; align-items: center; gap: 16px;
}
.thoth-sigil {
    width: 52px; height: 52px; flex: none;
    display: grid; place-items: center;
    border-radius: 15px;
    font-size: 1.4rem;
    color: #0B0C12;
    background: linear-gradient(150deg, var(--gold-bright), var(--gold) 45%, var(--gold-deep));
    box-shadow: var(--lift-gold), 0 0 34px -6px var(--gold-glow);
    transform: rotate(-4deg);
    transition: transform .5s var(--ease);
}
.thoth-header:hover .thoth-sigil { transform: rotate(4deg) translateY(-2px) scale(1.04); }
.thoth-title {
    font-family: 'Cinzel', serif;
    font-weight: 700;
    font-size: 1.62rem;
    letter-spacing: .09em;
    background: var(--aurora);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1.1;
}
.thoth-sub {
    font-size: .78rem; color: var(--text-muted);
    letter-spacing: .22em; text-transform: uppercase; margin-top: 3px;
}
.thoth-oracle {
    position: relative; z-index: 2;
    text-align: right;
    font-family: 'Newsreader', serif;
    font-style: italic;
    font-size: .92rem;
    color: var(--text-secondary);
    max-width: 340px;
    line-height: 1.5;
}
.thoth-oracle span { color: var(--gold); font-style: normal; font-size: .7rem; letter-spacing: .2em; text-transform: uppercase; display: block; margin-top: 4px; }

/* live pulse */
.live-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--nile); margin-right: 7px;
    box-shadow: 0 0 0 0 rgba(47,216,198,.6);
    animation: pulse-ring 1.8s infinite;
}
@keyframes pulse-ring {
    70%  { box-shadow: 0 0 0 9px rgba(47,216,198,0); }
    100% { box-shadow: 0 0 0 0 rgba(47,216,198,0); }
}

/* ======================= GLASS PANELS ======================= */
.glass-panel {
    position: relative;
    border-radius: var(--radius);
    background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.018));
    border: 1px solid var(--border);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
    padding: var(--space-6);
    transition: transform .45s var(--ease), box-shadow .45s var(--ease), border-color .3s var(--ease);
}
.glass-panel:hover { border-color: var(--border-hover); box-shadow: var(--lift-2); }

.chat-container {
    position: relative;
    border-radius: var(--radius-lg);
    background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.015));
    border: 1px solid var(--border-subtle);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
    padding: 20px 20px 8px 20px;
}

/* section titles */
.sec-kicker {
    font-size: .68rem; letter-spacing: .26em; text-transform: uppercase;
    color: var(--gold); font-weight: 600;
}
.sec-title {
    font-family: 'Cinzel', serif; font-size: 1.05rem; font-weight: 600;
    color: var(--text-primary); letter-spacing: .05em; margin-top: 3px;
}
.sec-sub { font-size: .82rem; color: var(--text-muted); margin-top: 4px; line-height: 1.55; }

/* ======================= STAT TABLETS ======================= */
.oracle-stats { display: flex; gap: 12px; flex-wrap: wrap; margin: 4px 0 14px 0; }
.stat-tablet {
    flex: 1 1 130px;
    padding: 12px 14px;
    border-radius: 14px;
    background: linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.02));
    border: 1px solid var(--border-subtle);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
    transition: transform .4s var(--ease), border-color .3s var(--ease);
}
.stat-tablet:hover { transform: translateY(-3px); border-color: var(--gold-border); }
.stat-val {
    font-family: 'Cinzel', serif; font-size: 1.4rem; font-weight: 700;
    background: var(--aurora); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.stat-key { font-size: .68rem; letter-spacing: .18em; text-transform: uppercase; color: var(--text-muted); margin-top: 2px; }

/* ======================= FORM CONTROLS ======================= */
.stTextInput input, .stTextArea textarea {
    background-color: rgba(255,255,255,.04) !important;
    color: #FFFFFF !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    font-size: .93rem !important;
    padding: 10px 14px !important;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    transition: border-color .25s var(--ease), box-shadow .25s var(--ease), background-color .25s var(--ease);
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder { color: var(--text-faint) !important; }
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--gold-border) !important;
    background-color: rgba(255,255,255,.06) !important;
    box-shadow: 0 0 0 3px rgba(231,199,123,.12), 0 0 30px -12px var(--gold-glow) !important;
}
.stWidgetLabel p, label[data-testid="stWidgetLabel"], label {
    color: var(--text-secondary) !important;
    font-weight: 600 !important;
    font-size: .78rem !important;
    letter-spacing: .12em !important;
    text-transform: uppercase !important;
    margin-bottom: var(--space-1) !important;
}

div[data-baseweb="select"] {
    background-color: rgba(255,255,255,.04) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}
div[data-baseweb="select"] > div { background-color: transparent !important; color: #FFFFFF !important; }
div[data-baseweb="select"] span, div[data-baseweb="select"] div, div[data-baseweb="select"] p { color: #FFFFFF !important; }
div[data-baseweb="select"] svg { fill: var(--gold) !important; }
div[data-baseweb="popover"], ul[role="listbox"] {
    background-color: #0E1019 !important;
    border: 1px solid var(--border-hover) !important;
    border-radius: var(--radius-sm) !important;
    color: #FFFFFF !important;
    box-shadow: var(--lift-2) !important;
}
li[role="option"] { background-color: transparent !important; color: #FFFFFF !important; }
li[role="option"]:hover, li[aria-selected="true"] {
    background-color: var(--gold-subtle) !important; color: var(--gold-bright) !important;
}

/* sliders */
div[data-testid="stSlider"] [role="slider"] {
    background: linear-gradient(150deg, var(--gold-bright), var(--gold-deep)) !important;
    box-shadow: 0 0 16px -2px var(--gold-glow) !important;
}
div[data-testid="stSlider"] div[data-baseweb="slider"] div div { background: var(--gold) !important; }

/* radio pills */
div[role="radiogroup"] label {
    background: rgba(255,255,255,.04);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-pill) !important;
    padding: 5px 12px !important;
    margin-right: 6px !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    font-size: .78rem !important;
    transition: all .25s var(--ease);
}
div[role="radiogroup"] label:hover { border-color: var(--gold-border); background: var(--gold-subtle); }

/* ======================= BUTTONS ======================= */
.stButton > button {
    background: linear-gradient(180deg, rgba(255,255,255,.09), rgba(255,255,255,.03)) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: .85rem !important;
    letter-spacing: .02em !important;
    padding: .58rem 1rem !important;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    box-shadow: var(--lift-1) !important;
    transition: transform .28s var(--ease), box-shadow .28s var(--ease), border-color .28s var(--ease), background .28s var(--ease) !important;
}
.stButton > button:hover {
    transform: translateY(-2px);
    border-color: var(--gold-border) !important;
    background: linear-gradient(180deg, rgba(231,199,123,.16), rgba(231,199,123,.05)) !important;
    box-shadow: 0 16px 34px -20px var(--gold-glow), var(--lift-1) !important;
    color: var(--gold-bright) !important;
}
.stButton > button:active { transform: translateY(0) scale(.99); }

/* primary launch button (first button inside the chat pane) */
button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(140deg, var(--gold-bright), var(--gold) 42%, var(--gold-deep)) !important;
    color: #0A0B10 !important;
    border: 1px solid rgba(255,255,255,.28) !important;
    box-shadow: var(--lift-gold) !important;
    text-shadow: none !important;
}
button[kind="primary"]:hover {
    color: #0A0B10 !important;
    transform: translateY(-2px);
    box-shadow: 0 24px 52px -20px var(--gold-glow), var(--lift-gold) !important;
}

.stDownloadButton > button {
    background: rgba(255,255,255,.05) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    font-size: .82rem !important;
    transition: all .28s var(--ease) !important;
}
.stDownloadButton > button:hover {
    border-color: var(--gold-border) !important; color: var(--gold-bright) !important; transform: translateY(-2px);
}

/* ======================= SIDEBAR ======================= */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #07080D 0%, #0A0B13 100%) !important;
    border-right: 1px solid var(--border-subtle) !important;
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
}
section[data-testid="stSidebar"] * { color: var(--text-primary); }
.sidebar-crest {
    font-family: 'Cinzel', serif; font-size: 1rem; font-weight: 600;
    letter-spacing: .18em; text-transform: uppercase;
    color: var(--gold);
    padding-bottom: 10px; margin-bottom: 14px;
    border-bottom: 1px solid var(--gold-border);
}
.sidebar-note {
    font-size: .72rem; color: var(--text-faint); line-height: 1.6;
    border-left: 2px solid var(--gold-border); padding-left: 10px; margin-top: 18px;
}

/* ======================= AGENT STEPPER RAIL ======================= */
.planner-stepper {
    display: flex; align-items: center; gap: 4px;
    flex-wrap: nowrap; overflow-x: auto;
    padding: 13px 16px;
    margin-bottom: 16px;
    border-radius: var(--radius);
    background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.015));
    border: 1px solid var(--border-subtle);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
    scrollbar-width: none;
}
.planner-stepper::-webkit-scrollbar { display: none; }
.step-item {
    display: flex; align-items: center; gap: 7px;
    padding: 6px 11px;
    border-radius: var(--radius-pill);
    font-size: .76rem; font-weight: 600; white-space: nowrap;
    color: var(--text-faint);
    border: 1px solid transparent;
    transition: all .35s var(--ease);
}
.step-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--idle);
    transition: all .35s var(--ease);
}
.step-item.active {
    color: var(--gold-bright);
    background: var(--gold-subtle);
    border-color: var(--gold-border);
    box-shadow: 0 0 26px -10px var(--gold-glow);
    transform: translateY(-1px);
}
.step-item.active .step-dot {
    background: var(--gold);
    box-shadow: 0 0 0 0 var(--gold-glow);
    animation: pulse-ring-gold 1.4s infinite;
}
@keyframes pulse-ring-gold {
    70%  { box-shadow: 0 0 0 8px rgba(231,199,123,0); }
    100% { box-shadow: 0 0 0 0 rgba(231,199,123,0); }
}
.step-item.done, .step-item.complete, .step-item.completed {
    color: var(--ok); background: var(--ok-bg); border-color: var(--ok-border);
}
.step-item.done .step-dot, .step-item.complete .step-dot, .step-item.completed .step-dot { background: var(--ok); }
.step-item.error, .step-item.failed { color: var(--error); background: var(--error-bg); border-color: var(--error-border); }
.step-item.error .step-dot, .step-item.failed .step-dot { background: var(--error); }
.step-divider {
    flex: 1 1 12px; min-width: 12px; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.14), transparent);
}

/* ======================= CHAT ======================= */
.chat-msg-user {
    position: relative;
    margin: 12px 0 12px auto;
    max-width: 90%;
    padding: 12px 16px;
    border-radius: 16px 16px 4px 16px;
    background: linear-gradient(140deg, rgba(231,199,123,.20), rgba(231,199,123,.06));
    border: 1px solid var(--gold-border);
    color: var(--text-primary);
    font-size: .9rem; line-height: 1.6;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow: 0 14px 30px -22px var(--gold-glow);
    animation: rise-in .5s var(--ease) both;
}
.chat-msg-agent {
    position: relative;
    margin: 10px 0 14px 0;
    max-width: 96%;
    padding: 14px 18px;
    border-radius: 16px 16px 16px 4px;
    background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
    border: 1px solid var(--border);
    color: var(--text-primary);
    font-size: .9rem; line-height: 1.68;
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow: var(--lift-1);
    animation: rise-in .5s var(--ease) both;
}
.chat-msg-agent::before {
    content: ""; position: absolute; left: 0; top: 14px; bottom: 14px; width: 2px;
    border-radius: 2px; background: var(--aurora); opacity: .8;
}
@keyframes rise-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

.route-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: .68rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
    padding: 3px 10px; border-radius: var(--radius-pill);
    border: 1px solid var(--border); color: var(--text-secondary);
    background: rgba(255,255,255,.04);
}
.route-badge.local-qa        { color: var(--gold); border-color: var(--gold-border); background: var(--gold-subtle); }
.route-badge.web-search      { color: var(--nile); border-color: rgba(47,216,198,.28); background: rgba(47,216,198,.09); }
.route-badge.report-expansion{ color: #B9A6FF; border-color: rgba(124,92,255,.3);  background: rgba(124,92,255,.10); }

/* thinking shimmer */
.thinking-line {
    display: flex; align-items: center; gap: 10px;
    font-size: .85rem; color: var(--text-secondary);
}
.thinking-orb {
    width: 14px; height: 14px; border-radius: 50%;
    background: conic-gradient(from 0deg, var(--gold), var(--aether), var(--nile), var(--gold));
    filter: blur(.3px);
    animation: spin 1.6s linear infinite;
    box-shadow: 0 0 18px -2px var(--gold-glow);
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ======================= CHIPS ======================= */
.chip {
    display: inline-flex; align-items: center; gap: 7px;
    padding: 5px 12px;
    border-radius: var(--radius-pill);
    background: rgba(255,255,255,.045);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary) !important;
    font-size: .74rem; text-decoration: none !important;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    transition: all .28s var(--ease);
}
.chip:hover {
    color: var(--gold-bright) !important; border-color: var(--gold-border);
    transform: translateY(-2px); box-shadow: 0 12px 26px -18px var(--gold-glow);
}
.chip-dot { width: 6px; height: 6px; border-radius: 50%; }

/* ======================= TABS ======================= */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: rgba(255,255,255,.03);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-pill);
    padding: 5px;
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    position: sticky; top: 0; z-index: 20;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: var(--radius-pill) !important;
    color: var(--text-muted) !important;
    font-size: .8rem !important; font-weight: 600 !important;
    letter-spacing: .04em;
    padding: 7px 15px !important;
    transition: all .3s var(--ease);
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text-primary) !important; background: rgba(255,255,255,.05) !important; }
.stTabs [aria-selected="true"] {
    background: linear-gradient(140deg, rgba(231,199,123,.22), rgba(124,92,255,.14)) !important;
    color: var(--gold-bright) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.14), 0 10px 26px -18px var(--gold-glow);
}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 18px; }

/* ======================= EDITORIAL PROSE ======================= */
.editorial-prose {
    font-family: 'Newsreader', Georgia, serif;
    font-size: 1.06rem;
    line-height: 1.82;
    color: #E6E4DC;
    letter-spacing: .002em;
    padding: 26px 30px;
    border-radius: var(--radius);
    background: linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.012));
    border: 1px solid var(--border-subtle);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
}
.editorial-prose h1, .editorial-prose h2, .editorial-prose h3 {
    font-family: 'Cinzel', serif;
    color: var(--text-primary);
    letter-spacing: .04em;
    margin-top: 1.7em; margin-bottom: .5em;
}
.editorial-prose h1 { font-size: 1.6rem; }
.editorial-prose h2 {
    font-size: 1.24rem;
    padding-bottom: .32em;
    border-bottom: 1px solid var(--gold-border);
}
.editorial-prose h3 { font-size: 1.05rem; color: var(--gold); }
.editorial-prose p { margin: 0 0 1.05em 0; }
.editorial-prose strong { color: #FFF6DF; font-weight: 600; }
.editorial-prose a { color: var(--nile); text-decoration: none; border-bottom: 1px solid rgba(47,216,198,.32); }
.editorial-prose a:hover { color: var(--gold-bright); border-color: var(--gold-border); }
.editorial-prose ul, .editorial-prose ol { padding-left: 1.3em; margin-bottom: 1.1em; }
.editorial-prose li { margin-bottom: .5em; }
.editorial-prose blockquote {
    margin: 1.3em 0; padding: .6em 1.2em;
    border-left: 2px solid var(--gold);
    background: var(--gold-subtle);
    border-radius: 0 10px 10px 0;
    font-style: italic; color: var(--text-secondary);
}
.editorial-prose code {
    font-family: 'JetBrains Mono', monospace; font-size: .84em;
    background: rgba(255,255,255,.06); padding: 2px 6px; border-radius: 6px; color: var(--gold-bright);
}

/* ======================= MATRIX TABLE ======================= */
.matrix-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-size: .85rem;
    border-radius: var(--radius); overflow: hidden;
    border: 1px solid var(--border-subtle);
    background: rgba(255,255,255,.02);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-1);
}
.matrix-table thead th {
    background: linear-gradient(180deg, rgba(231,199,123,.12), rgba(255,255,255,.02));
    color: var(--gold-bright);
    font-size: .7rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase;
    text-align: left; padding: 13px 16px;
    border-bottom: 1px solid var(--gold-border);
}
.matrix-table tbody td {
    padding: 13px 16px;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border-subtle);
    vertical-align: top;
}
.matrix-table tbody tr { transition: background .25s var(--ease); }
.matrix-table tbody tr:hover { background: rgba(231,199,123,.05); }
.matrix-table tbody tr:last-child td { border-bottom: none; }

.status-pill {
    display: inline-block; padding: 3px 10px; border-radius: var(--radius-pill);
    font-size: .68rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
}
.status-pill.verified { color: var(--ok); background: var(--ok-bg); border: 1px solid var(--ok-border); }
.status-pill.pending  { color: var(--warn); background: var(--warn-bg); border: 1px solid var(--warn-border); }
.status-pill.failed   { color: var(--error); background: var(--error-bg); border: 1px solid var(--error-border); }

/* ======================= LOG PANE ======================= */
.log-pane {
    font-family: 'JetBrains Mono', monospace;
    font-size: .78rem; line-height: 1.7;
    color: var(--text-secondary);
    white-space: pre-wrap; word-break: break-word;
    max-height: 380px; overflow-y: auto;
    padding: 16px 18px;
    border-radius: var(--radius-sm);
    background: rgba(5,6,11,.6);
    border: 1px solid var(--border-subtle);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}

/* ======================= EMPTY STATES ======================= */
.empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center;
    padding: 62px 26px;
    border-radius: var(--radius);
    border: 1px dashed var(--border);
    background: radial-gradient(520px 200px at 50% 0%, rgba(231,199,123,.07), transparent 70%);
}
.empty-glyph {
    width: 62px; height: 62px; display: grid; place-items: center;
    border-radius: 20px; font-size: 1.55rem;
    color: var(--gold);
    background: linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.02));
    border: 1px solid var(--gold-border);
    box-shadow: 0 0 40px -14px var(--gold-glow);
    margin-bottom: 16px;
    animation: float-y 5s ease-in-out infinite;
}
@keyframes float-y { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-7px); } }
.empty-title { font-family: 'Cinzel', serif; font-size: 1rem; letter-spacing: .08em; color: var(--text-primary); }
.empty-body  { font-size: .84rem; color: var(--text-muted); margin-top: 7px; max-width: 420px; line-height: 1.65; }

/* ======================= MISC STREAMLIT OVERRIDES ======================= */
div[data-testid="stExpander"] {
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-sm) !important;
    background: rgba(255,255,255,.03) !important;
}
div[data-testid="stAlert"] {
    background: rgba(255,255,255,.04) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    color: var(--text-primary) !important;
}
hr { border-color: var(--border-subtle) !important; }

@media (max-width: 900px) {
    .thoth-header { flex-direction: column; align-items: flex-start; }
    .thoth-oracle { text-align: left; }
}

/* ======================= SYNTHESIS CELEBRATION ======================= */
/* A gold radial sweep plays once when the synthesis report arrives.     */
.synthesis-arrived {
    animation: synthesis-sweep .9s cubic-bezier(.22,1,.36,1) both;
}
@keyframes synthesis-sweep {
    from {
        opacity: 0;
        box-shadow: 0 0 0 0 transparent;
        background-position: 0% 50%;
    }
    40% {
        box-shadow: 0 0 60px -8px rgba(231,199,123,.30);
    }
    to {
        opacity: 1;
        box-shadow: 0 0 0 0 transparent;
    }
}

/* Kicker line above the synthesis report */
.synthesis-kicker {
    font-size: .68rem; letter-spacing: .28em; text-transform: uppercase;
    color: var(--gold); font-weight: 600;
    margin-bottom: 12px; opacity: .85;
    display: flex; align-items: center; gap: 8px;
}
.synthesis-kicker::before {
    content: "✦";
    font-size: .6rem;
}

/* ======================= ORACLE FOCUS RING (B) ======================= */
/* Dramatically upgraded from the existing weak focus style.             */
.st-key-hero_inquiry .stTextArea textarea:focus {
    border-color: var(--gold) !important;
    background-color: rgba(255,255,255,.07) !important;
    box-shadow:
        0 0 0 3px rgba(231,199,123,.16),
        0 0 0 6px rgba(231,199,123,.07),
        0 0 50px -10px rgba(231,199,123,.45) !important;
    transition: all .38s cubic-bezier(.22,1,.36,1) !important;
}

/* ======================= STEPPER HEARTBEAT (C) ======================= */
/* Active step pill breathes — gives wait a living, deliberate quality. */
.step-item.active {
    animation: step-heartbeat 2.2s cubic-bezier(.22,1,.36,1) infinite !important;
}
@keyframes step-heartbeat {
    0%, 100% { transform: translateY(-1px) scale(1); }
    45%       { transform: translateY(-1px) scale(1.035); }
    55%       { transform: translateY(-1px) scale(1.035); }
}

/* ======================= FOLLOW-UP PILL HOVER (E) ======================= */
/* Pills slide right with a gold left-border on hover — "chosen path" feel. */
div[class*="st-key-chat_pill"] .stButton > button,
div[data-testid="stVerticalBlock"] .stButton > button[data-testid^="baseButton"][id*="chat_pill"] {
    border-left: 2px solid transparent !important;
    text-align: left !important;
    transition: transform .26s cubic-bezier(.22,1,.36,1),
                border-color .26s ease,
                color .22s ease,
                background .26s ease !important;
}
div[class*="st-key-chat_pill"] .stButton > button:hover,
div[data-testid="stVerticalBlock"] .stButton > button[data-testid^="baseButton"][id*="chat_pill"]:hover {
    transform: translateX(5px) !important;
    border-left-color: var(--gold) !important;
    color: var(--gold-bright) !important;
    background: linear-gradient(90deg, rgba(231,199,123,.08), rgba(255,255,255,.03)) !important;
}

/* ======================= ACTIVE TAB GLOW (F) ======================= */
/* Unmistakable context signal — gold glow under active tab text.       */
.stTabs [aria-selected="true"] {
    background: linear-gradient(140deg, rgba(231,199,123,.24), rgba(124,92,255,.16)) !important;
    color: var(--gold-bright) !important;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.18),
        0 12px 28px -16px var(--gold-glow),
        0 0 20px -6px rgba(231,199,123,.22) !important;
    text-shadow: 0 0 18px rgba(231,199,123,.45);
}

</style>
"""

# ==============================================================================
# NAV SHELL CSS — top bar, hidden sidebar, starfield, hero, agent rail,
# judge strip, settings tiles, animated counters, page transitions.
#
# Uses Streamlit's `st.container(key=...)` -> `.st-key-<key>` wrapper class
# to precisely target structural containers with CSS (no raw component
# wrapping required, no extra deps).
# ==============================================================================
NAV_CSS = """
<style>
/* ======================= KILL THE SIDEBAR ENTIRELY ======================= */
section[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarCollapsedControl"],
button[data-testid="stSidebarNavCollapseButton"] {
    display: none !important;
}
.block-container { max-width: 1320px !important; }

/* ======================= NUMBER INPUT (contrast fix) ======================= */
div[data-testid="stNumberInput"] input {
    background-color: rgba(255,255,255,.04) !important;
    color: #FFFFFF !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}
div[data-testid="stNumberInput"] button {
    background: rgba(255,255,255,.05) !important;
    color: var(--gold) !important;
    border: 1px solid var(--border) !important;
}

/* ======================= PAGE CONTAINER ======================= */
.st-key-page_wrap {
    width: 100% !important;
}

/* ======================= STARFIELD (pure CSS, layered parallax) ======================= */
.starfield-layer {
    position: fixed; inset: -10% -10% -10% -10%;
    z-index: 0; pointer-events: none;
}
.starfield-layer.sf-small {
    width: 2px; height: 2px; background: transparent; border-radius: 50%;
    box-shadow: STAR_SHADOW_SMALL;
    animation: sf-drift-small 160s linear infinite, sf-twinkle 4.5s ease-in-out infinite alternate;
}
.starfield-layer.sf-large {
    width: 3px; height: 3px; background: transparent; border-radius: 50%;
    box-shadow: STAR_SHADOW_LARGE;
    animation: sf-drift-large 220s linear infinite, sf-twinkle 6.5s ease-in-out infinite alternate-reverse;
    opacity: .85;
}
@keyframes sf-drift-small { from { transform: translate3d(0,0,0); } to { transform: translate3d(-160px, 220px, 0); } }
@keyframes sf-drift-large { from { transform: translate3d(0,0,0); } to { transform: translate3d(140px, -180px, 0); } }
@keyframes sf-twinkle { from { opacity: .35; } to { opacity: 1; } }

/* ======================= TOP BAR ======================= */
.st-key-topbar {
    position: sticky; top: 0; z-index: 200;
    margin: 0 0 20px 0;
    padding: 8px 18px;
    border-radius: var(--radius-lg);
    background: linear-gradient(180deg, rgba(14,16,25,.94), rgba(8,9,15,.90));
    border: 1px solid var(--border);
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: var(--lift-2);
}
.topbar-logo {
    display: flex; align-items: center; gap: 11px;
    font-family: 'Cinzel', serif; font-weight: 700;
    font-size: 1.15rem; letter-spacing: .14em;
    background: var(--aurora); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
    white-space: nowrap;
    padding-top: 6px;
}
.topbar-logo .glyph {
    width: 32px; height: 32px; flex: none; display: grid; place-items: center;
    border-radius: 9px; font-size: 1.05rem; color: #0B0C12;
    background: linear-gradient(150deg, var(--gold-bright), var(--gold) 45%, var(--gold-deep));
    box-shadow: var(--lift-gold);
    -webkit-text-fill-color: #0B0C12;
}
.st-key-topbar .stButton > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    font-family: 'Inter', sans-serif !important;
    font-size: .80rem !important;
    letter-spacing: .06em !important;
    color: var(--text-secondary) !important;
    padding: .45rem .85rem !important;
}
.st-key-topbar .stButton > button:hover {
    color: var(--gold-bright) !important;
    background: var(--gold-subtle) !important;
    border-color: var(--gold-border) !important;
    transform: none !important;
}
.st-key-nav_active .stButton > button {
    color: var(--gold-bright) !important;
    background: var(--gold-subtle) !important;
    border-color: var(--gold-border) !important;
}
.topbar-status {
    margin-left: auto; white-space: nowrap;
    display: flex; align-items: center; justify-content: flex-end; gap: 8px;
    font-size: .74rem; letter-spacing: .10em; text-transform: uppercase;
    color: var(--text-muted);
    padding-top: 10px;
}

/* ======================= HERO ======================= */
.st-key-hero > div {
    position: relative;
    padding: 76px 40px 56px 40px;
    border-radius: 28px;
    text-align: center;
    overflow: hidden;
    background:
        radial-gradient(900px 420px at 50% -10%, rgba(124,92,255,.20), transparent 65%),
        radial-gradient(700px 380px at 15% 110%, rgba(231,199,123,.14), transparent 60%),
        linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.012));
    border: 1px solid var(--border);
    box-shadow: var(--lift-2);
    margin-bottom: 30px;
}
.hero-eyebrow {
    display: inline-block; font-size: .72rem; letter-spacing: .38em; text-transform: uppercase;
    color: var(--gold); margin-bottom: 22px; animation: page-fade-in .7s var(--ease) both;
}
.hero-wordmark {
    font-family: 'Cinzel', serif; font-weight: 700;
    font-size: clamp(3.2rem, 8vw, 6.4rem);
    letter-spacing: .16em;
    line-height: 1;
    background: var(--aurora);
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 60px rgba(231,199,123,.28));
    animation: page-fade-in .8s var(--ease) both .05s;
}
.hero-tagline {
    font-family: 'Newsreader', serif; font-style: italic;
    font-size: 1.15rem; color: var(--text-secondary);
    max-width: 620px; margin: 18px auto 40px auto; line-height: 1.65;
    animation: page-fade-in .8s var(--ease) both .12s;
}
.st-key-hero_inquiry { max-width: 680px; margin: 0 auto; animation: page-fade-in .8s var(--ease) both .18s; }
.st-key-hero_inquiry .stTextArea textarea { text-align: center; font-size: 1.02rem !important; }

/* ======================= AGENT CARD RAIL ======================= */
.rail-heading { text-align: center; margin: 58px 0 26px 0; }
.agent-rail {
    display: flex; gap: 16px; overflow-x: auto; padding: 10px 4px 22px 4px;
    scrollbar-width: thin;
}
.agent-card {
    flex: 1 1 0; min-width: 168px;
    padding: 22px 18px;
    border-radius: 20px;
    background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.015));
    border: 1px solid var(--border-subtle);
    box-shadow: var(--lift-1);
    text-align: center;
    transform-style: preserve-3d;
    transition: transform .5s var(--ease), box-shadow .5s var(--ease), border-color .4s var(--ease);
    animation: page-fade-in .7s var(--ease) both;
}
.agent-card:hover {
    transform: perspective(800px) rotateX(4deg) rotateY(-4deg) translateY(-8px);
    border-color: var(--gold-border);
    box-shadow: var(--lift-2), 0 0 42px -16px var(--gold-glow);
}
.agent-card .num { font-family: 'Cinzel', serif; font-size: .68rem; letter-spacing: .2em; color: var(--gold); }
.agent-card .icon { font-size: 1.7rem; margin: 10px 0 6px 0; }
.agent-card .name { font-family: 'Cinzel', serif; font-weight: 600; font-size: .92rem; color: var(--text-primary); }
.agent-card .desc { font-size: .74rem; color: var(--text-muted); margin-top: 6px; line-height: 1.5; }
.agent-connector {
    align-self: center; flex: 0 0 20px; height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-border), transparent);
    position: relative; top: 0; margin-top: -22px;
}

/* ======================= JUDGE STRIP ======================= */
.judge-strip {
    display: flex; gap: 14px; flex-wrap: wrap; justify-content: center;
    margin: 8px 0 50px 0;
}
.judge-item {
    flex: 1 1 200px; max-width: 240px;
    padding: 16px 18px; border-radius: 16px;
    background: rgba(255,255,255,.03);
    border: 1px solid var(--border-subtle);
    text-align: left;
}
.judge-item .jt { font-family: 'Cinzel', serif; font-size: .82rem; color: var(--gold-bright); }
.judge-item .jd { font-size: .74rem; color: var(--text-muted); margin-top: 4px; line-height: 1.5; }

/* ======================= HERO FOOTER ======================= */
.hero-footer {
    text-align: center; margin-top: 10px; padding-top: 26px;
    border-top: 1px solid var(--border-subtle);
    font-family: 'Newsreader', serif; font-style: italic;
    color: var(--text-muted); font-size: .92rem; line-height: 1.7;
}
.hero-footer .attrib { display: block; margin-top: 8px; font-style: normal; font-size: .68rem; letter-spacing: .22em; text-transform: uppercase; color: var(--gold); }

/* ======================= SETTINGS TILES ======================= */
.settings-tile-title {
    font-family: 'Cinzel', serif; font-size: .96rem; font-weight: 600;
    color: var(--gold-bright); letter-spacing: .06em;
    display: flex; align-items: center; gap: 9px;
    margin-bottom: 4px; padding-bottom: 12px;
    border-bottom: 1px solid var(--border-subtle);
}
.settings-tile-sub { font-size: .76rem; color: var(--text-muted); margin: 6px 0 16px 0; line-height: 1.5; }

/* ======================= ANIMATED STAT (JS count-up host) ======================= */
.count-up { font-variant-numeric: tabular-nums; }

/* ======================= PROGRESS RIBBON (D) ======================= */
/* A thin gold sweep line under the stepper — pacing signal for the     */
/* user during the multi-agent wait. Resets on each new step.           */
.progress-ribbon {
    height: 2px;
    width: 100%;
    background: linear-gradient(90deg,
        transparent 0%,
        var(--gold-deep) 20%,
        var(--gold) 50%,
        var(--gold-deep) 80%,
        transparent 100%);
    border-radius: 2px;
    animation: ribbon-sweep 3.2s cubic-bezier(.22,1,.36,1) infinite;
    opacity: 0.7;
    margin: -10px 0 14px 0;
    overflow: hidden;
}
@keyframes ribbon-sweep {
    from { background-position: -100% 0; transform: scaleX(0); transform-origin: left; }
    30%  { transform: scaleX(1); transform-origin: left; }
    70%  { transform: scaleX(1); transform-origin: right; }
    to   { background-position: 200% 0; transform: scaleX(0); transform-origin: right; }
}

/* ======================= SETTINGS GLASS CARDS (G) ======================= */
/* Each settings column becomes a proper glass panel — "studio dials"   */
.st-key-settings_card_persona,
.st-key-settings_card_depth,
.st-key-settings_card_thresholds {
    padding: 22px !important;
    border-radius: var(--radius) !important;
    background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.018)) !important;
    border: 1px solid var(--border) !important;
    backdrop-filter: var(--blur) !important;
    -webkit-backdrop-filter: var(--blur) !important;
    box-shadow: var(--lift-1) !important;
    transition: transform .45s var(--ease), box-shadow .45s var(--ease), border-color .3s var(--ease) !important;
    margin-bottom: 14px !important;
}
.st-key-settings_card_persona:hover,
.st-key-settings_card_depth:hover,
.st-key-settings_card_thresholds:hover {
    border-color: var(--gold-border) !important;
    transform: translateY(-3px) !important;
    box-shadow: var(--lift-2), 0 0 40px -18px var(--gold-glow) !important;
}

/* ======================= THINKING MESSAGE ROTATION (H) ======================= */
/* The thinking orb line container fades in with a slight upward drift   */
/* on each render — the rotation itself is handled in Python (views.py). */
.thinking-line {
    animation: thinking-appear .55s cubic-bezier(.22,1,.36,1) both;
}
@keyframes thinking-appear {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: none; }
}

/* ======================= AGENT CARD CASCADE REVEAL (I) ======================= */
/* Cards assemble with a cascade — scholars filing into the library.    */
.agent-card {
    animation: card-assemble .65s cubic-bezier(.22,1,.36,1) both !important;
}
@keyframes card-assemble {
    from { opacity: 0; transform: translateY(18px) scale(.97); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
}
/* Animation delays injected inline via Python (existing pattern, upgraded timing) */

/* ======================= VAULT & CODEX GLASSWORK ======================= */
.vault-card {
    background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.015)) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 18px 22px !important;
    backdrop-filter: var(--blur) !important;
    -webkit-backdrop-filter: var(--blur) !important;
    box-shadow: var(--lift-1) !important;
    margin-bottom: 14px !important;
    transition: transform .35s var(--ease), border-color .35s var(--ease), box-shadow .35s var(--ease) !important;
}
.vault-card:hover {
    border-color: var(--gold-border) !important;
    transform: translateY(-3px) !important;
    box-shadow: var(--lift-2), 0 0 30px -15px var(--gold-glow) !important;
}
.vault-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: var(--radius-pill);
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em;
}
.vault-badge.topics { background: rgba(231,199,123,0.14); color: var(--gold); border: 1px solid var(--gold-border); }
.vault-badge.sources { background: rgba(47,216,198,0.12); color: var(--nile); border: 1px solid rgba(47,216,198,0.28); }
.vault-badge.entities { background: rgba(124,92,255,0.14); color: var(--aether); border: 1px solid rgba(124,92,255,0.28); }
.vault-badge.sessions { background: rgba(91,124,250,0.14); color: var(--lapis); border: 1px solid rgba(91,124,250,0.28); }

.wikilink-pill {
    display: inline-flex; align-items: center; gap: 4px;
    background: rgba(231,199,123,0.08); border: 1px solid rgba(231,199,123,0.22);
    border-radius: 6px; padding: 2px 8px; font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem; color: var(--gold-bright); text-decoration: none;
    margin: 2px 3px;
}
.wikilink-pill:hover {
    background: rgba(231,199,123,0.20); border-color: var(--gold);
}

.search-hit-box {
    background: rgba(14, 16, 25, 0.75); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px 20px; margin-bottom: 12px;
    backdrop-filter: var(--blur); -webkit-backdrop-filter: var(--blur);
    transition: all .3s var(--ease);
}
.search-hit-box:hover {
    border-color: var(--gold-border); transform: translateX(3px);
}
.score-tag-rrf {
    background: linear-gradient(135deg, rgba(231,199,123,0.2), rgba(124,92,255,0.2));
    border: 1px solid var(--gold-border); color: var(--gold-bright);
    font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; font-weight: 600;
    padding: 3px 8px; border-radius: var(--radius-pill);
}

/* ======================= TELEMETRY HUD & CIRCUIT BREAKER ======================= */
.telemetry-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px; margin-bottom: 24px;
}
.telemetry-tile {
    background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015));
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 18px; backdrop-filter: var(--blur);
}
.circuit-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: var(--radius-pill);
    font-weight: 700; font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase;
}
.circuit-badge.closed { background: var(--ok-bg); color: var(--ok); border: 1px solid var(--ok-border); }
.circuit-badge.open { background: var(--error-bg); color: var(--error); border: 1px solid var(--error-border); }
.circuit-badge.half_open { background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn-border); }

.scholar-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(47,216,198,0.08); border: 1px solid rgba(47,216,198,0.22);
    border-radius: var(--radius-pill); padding: 4px 12px;
    color: var(--nile); font-size: 0.78rem; font-weight: 500;
    text-decoration: none; transition: all .25s ease;
}
.scholar-chip:hover {
    background: rgba(47,216,198,0.18); border-color: var(--nile);
    box-shadow: 0 0 16px -4px rgba(47,216,198,0.5);
}

.history-card {
    background: rgba(14, 16, 25, 0.7); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px; margin-bottom: 12px;
    backdrop-filter: var(--blur); transition: all .3s ease;
}
.history-card:hover {
    border-color: var(--gold-border); box-shadow: var(--lift-1);
}

</style>

"""


def _starfield_css():
    """Deterministically generate two layers of CSS box-shadow star dots."""
    rnd = random.Random(1312)
    def dots(n, spread_x=2600, spread_y=1600, color="rgba(255,255,255,.85)"):
        pts = []
        for _ in range(n):
            x = rnd.randint(0, spread_x)
            y = rnd.randint(0, spread_y)
            pts.append(f"{x}px {y}px {color}")
        return ", ".join(pts)
    small = dots(140, color="rgba(255,255,255,.55)")
    large = dots(55, color="rgba(231,199,123,.75)")
    css = NAV_CSS.replace("STAR_SHADOW_SMALL", small).replace("STAR_SHADOW_LARGE", large)
    return css


# ==============================================================================
# RENDERERS
# ==============================================================================

def inject_theme():
    """Injects the Thoth 'Hall of Wisdom' stylesheet + nav shell + starfield."""
    st.markdown(AURORA_CSS, unsafe_allow_html=True)
    st.markdown(_starfield_css(), unsafe_allow_html=True)


def render_starfield():
    """Fixed, drifting, twinkling starfield layer (pure CSS, no JS/deps)."""
    st.markdown(
        '<div class="starfield-layer sf-small"></div>'
        '<div class="starfield-layer sf-large"></div>',
        unsafe_allow_html=True
    )


def render_blobs():
    """Renders the ambient depth layer (drifting nebulae behind the glass)."""
    st.markdown(
        '<div class="aurora-blob blob-1"></div>'
        '<div class="aurora-blob blob-2"></div>'
        '<div class="aurora-blob blob-3"></div>',
        unsafe_allow_html=True
    )


def render_header(status_label: str = "", oracle_line: str = ""):
    """Renders the masthead: sigil, wordmark and an oracle inscription."""
    oracle_line = oracle_line or "“Nothing is written that cannot be verified.”"
    status_html = (
        f'<span class="live-dot"></span>{status_label}' if status_label else "Idle · Awaiting inquiry"
    )
    st.markdown(
        f"""
        <div class="thoth-header">
            <div class="thoth-mark">
                <div class="thoth-sigil">✦</div>
                <div>
                    <div class="thoth-title">THOTH</div>
                    <div class="thoth-sub">Agentic Research Sanctum</div>
                </div>
            </div>
            <div class="thoth-oracle">
                {oracle_line}
                <span>{status_html}</span>
            </div>
        </div>
        <div class="horizon"></div>
        """,
        unsafe_allow_html=True
    )


def render_section_title(kicker: str, title: str, subtitle: str = ""):
    sub = f'<div class="sec-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="sec-kicker">{kicker}</div><div class="sec-title">{title}</div>{sub}',
        unsafe_allow_html=True
    )


def render_oracle_stats(stats):
    """stats: list of (value, label) tuples rendered as floating tablets."""
    items = "".join(
        f'<div class="stat-tablet"><div class="stat-val">{v}</div><div class="stat-key">{k}</div></div>'
        for v, k in stats
    )
    st.markdown(f'<div class="oracle-stats">{items}</div>', unsafe_allow_html=True)


def render_empty_state(glyph: str, title: str, body: str):
    st.markdown(
        f'<div class="empty-state">'
        f'<div class="empty-glyph">{glyph}</div>'
        f'<div class="empty-title">{title}</div>'
        f'<div class="empty-body">{body}</div>'
        f'</div>',
        unsafe_allow_html=True
    )


def render_thinking(message: str):
    st.markdown(
        f'<div class="chat-msg-agent"><div class="thinking-line">'
        f'<div class="thinking-orb"></div><div>{message}</div></div></div>',
        unsafe_allow_html=True
    )


def render_scroll_divider():
    st.markdown('<div class="horizon"></div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# TOP BAR NAVIGATION (replaces st.sidebar entirely)
# ------------------------------------------------------------------------------
NAV_PAGES = [
    ("lab", "✦ Research Lab"),
    ("constellation", "✧ Constellation"),
    ("vault", "🗄 Memory Vault"),
    ("history", "📜 Codex History"),
    ("settings", "⚙ Telemetry & Oracle"),
]


def render_topbar(current_page: str, status_label: str = ""):
    """Glass top bar: wordmark, page nav buttons, live status pill.

    Returns the page key to navigate to if a nav button was clicked this run,
    else None. Caller is responsible for updating session_state + st.rerun().
    """
    clicked = None
    status_html = f'<span class="live-dot"></span>{status_label}' if status_label else "Idle"

    with st.container(key="topbar"):
        col_logo, col_nav, col_status = st.columns([2.2, 4, 2], gap="small")
        with col_logo:
            st.markdown(
                '<div class="topbar-logo"><div class="glyph">✦</div>THOTH</div>',
                unsafe_allow_html=True
            )
        with col_nav:
            nav_cols = st.columns(len(NAV_PAGES))
            for (key, label), c in zip(NAV_PAGES, nav_cols):
                with c:
                    container_key = f"nav_active" if key == current_page else f"nav_inactive_{key}"
                    with st.container(key=container_key):
                        if st.button(label, key=f"nav_{key}", use_container_width=True):
                            clicked = key
        with col_status:
            st.markdown(
                f'<div class="topbar-status">{status_html}</div>',
                unsafe_allow_html=True
            )

    return clicked


# ------------------------------------------------------------------------------
# LANDING PAGE PRIMITIVES
# ------------------------------------------------------------------------------
def render_agent_rail(agents):
    """agents: list of (icon, name, desc) tuples rendered as a 3D card rail."""
    cards = []
    for i, (icon, name, desc) in enumerate(agents, 1):
        cards.append(
            f'<div class="agent-card" style="animation-delay:{i*0.08:.2f}s">'
            f'<div class="num">{i:02d}</div>'
            f'<div class="icon">{icon}</div>'
            f'<div class="name">{name}</div>'
            f'<div class="desc">{desc}</div>'
            f'</div>'
        )
        if i < len(agents):
            cards.append('<div class="agent-connector"></div>')
    st.markdown(f'<div class="agent-rail">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_judge_strip(items):
    """items: list of (title, desc) tuples — 'how the oracle judges' strip."""
    chunks = "".join(
        f'<div class="judge-item"><div class="jt">{t}</div><div class="jd">{d}</div></div>'
        for t, d in items
    )
    st.markdown(f'<div class="judge-strip">{chunks}</div>', unsafe_allow_html=True)


def render_hero_footer(quote: str, attribution: str = "The Myth of Thoth"):
    st.markdown(
        f'<div class="hero-footer">“{quote}”<span class="attrib">{attribution}</span></div>',
        unsafe_allow_html=True
    )


# ------------------------------------------------------------------------------
# ANIMATED COUNTERS (progressive enhancement over render_oracle_stats)
# ------------------------------------------------------------------------------
def render_oracle_stats_animated(stats):
    """stats: list of (value, label). Numeric-looking values count up on render;
    non-numeric values (e.g. '—', '4.0s') render statically. Falls back
    gracefully if st.html is unavailable."""
    tablets = []
    script_bits = []
    for i, (v, k) in enumerate(stats):
        raw = str(v).replace(",", "")
        is_num = raw.replace(".", "", 1).isdigit()
        el_id = f"stat-{i}"
        tablets.append(
            f'<div class="stat-tablet"><div class="stat-val count-up" id="{el_id}">'
            f'{"0" if is_num else v}</div><div class="stat-key">{k}</div></div>'
        )
        if is_num:
            target = float(raw)
            is_int = target == int(target)
            script_bits.append(
                f"animateCount('{el_id}', {target}, {str(is_int).lower()});"
            )

    html_code = f"""
    <div class="oracle-stats">{"".join(tablets)}</div>
    <script>
        function animateCount(id, target, isInt) {{
            const el = document.getElementById(id);
            if (!el) return;
            const dur = 900, start = performance.now();
            function tick(now) {{
                const p = Math.min(1, (now - start) / dur);
                const eased = 1 - Math.pow(1 - p, 3);
                const val = target * eased;
                el.textContent = isInt ? Math.round(val).toLocaleString() : val.toFixed(1);
                if (p < 1) requestAnimationFrame(tick);
            }}
            requestAnimationFrame(tick);
        }}
        {" ".join(script_bits)}
    </script>
    """
    if hasattr(st, "html"):
        st.html(html_code)
    else:
        render_oracle_stats(stats)


def render_planner_stepper(active_idx: int, statuses: list, durations: dict = None, is_active: bool = False):
    """Horizontal agent rail: Search → Reader → Writer → Verifier → Critic → Mind Map → Follow-Up.
    
    is_active: when True, renders a sweeping gold ribbon below the stepper
    as a pacing signal during the live pipeline run.
    """
    NODES = [
        ("Search", "Querying registries"),
        ("Reader", "Scraping full text"),
        ("Writer", "Drafting synthesis"),
        ("Verifier", "Fact verification"),
        ("Critic", "Quality evaluation"),
        ("Mind Map", "Concept graph"),
        ("Follow-Up", "Deep dive ready"),
    ]
    durations = durations or {}

    items_html = []
    for i, (name, desc) in enumerate(NODES):
        s = statuses[i] if i < len(statuses) else "pending"
        dur_str = f" · {durations[name]:.1f}s" if name in durations else ""
        items_html.append(
            f'<div class="step-item {s}" title="{desc}">'
            f'<div class="step-dot"></div>'
            f'<span>{name}{dur_str}</span>'
            f'</div>'
        )
        if i < len(NODES) - 1:
            items_html.append('<div class="step-divider"></div>')

    ribbon_html = '<div class="progress-ribbon"></div>' if is_active else ''
    st.markdown(
        f'<div class="planner-stepper">{"".join(items_html)}</div>{ribbon_html}',
        unsafe_allow_html=True
    )


def render_interactive_mindmap(mindmap_data: dict, height: int = 500):
    """Dimensional, dark force-directed concept graph (vis.js) in an isolated frame."""
    if not mindmap_data or not mindmap_data.get("nodes"):
        st.info("✦ The Concept Mind Map will appear once initial synthesis completes.")
        return

    COLOR_MAP = {
        "topic":    {"bg": "#C9A227", "border": "#FFE9B0", "highlight": "#FFF3D0"},
        "subtopic": {"bg": "#5B7CFA", "border": "#A9BCFF", "highlight": "#D3DDFF"},
        "finding":  {"bg": "#1FA98F", "border": "#2FD8C6", "highlight": "#8CF0E4"},
        "source":   {"bg": "#7C5CFF", "border": "#B9A6FF", "highlight": "#DED4FF"},
        "followup": {"bg": "#D9497F", "border": "#FF9CC0", "highlight": "#FFD1E2"},
    }

    vis_nodes = []
    for n in mindmap_data.get("nodes", []):
        ntype = n.get("type", "finding")
        colors = COLOR_MAP.get(ntype, COLOR_MAP["finding"])
        label = n.get("label", "Concept")
        details = n.get("details", "")
        url = n.get("url", "")

        title_tooltip = f"<b>{label}</b><br><span style='font-size:11px;color:#CBD5E1;'>{details}</span>"
        if url:
            title_tooltip += f"<br><a href='{url}' target='_blank' style='color:#2FD8C6;font-size:10px;'>{url}</a>"

        vis_nodes.append({
            "id": n.get("id"),
            "label": label if len(label) < 28 else label[:25] + "...",
            "title": title_tooltip,
            "shape": "box" if ntype in ["topic", "subtopic"] else "dot",
            "size": 26 if ntype == "topic" else (18 if ntype == "subtopic" else 12),
            "color": {
                "background": colors["bg"],
                "border": colors["border"],
                "highlight": {"background": colors["highlight"], "border": "#FFFFFF"},
            },
            "font": {
                "color": "#0B0C12" if ntype == "topic" else "#FFFFFF",
                "face": "Inter, sans-serif",
                "size": 14 if ntype == "topic" else (11 if ntype == "subtopic" else 10),
            },
            "margin": 10,
            "borderWidth": 1.5,
            "shadow": {"enabled": True, "color": "rgba(0,0,0,0.65)", "size": 14, "x": 0, "y": 6},
        })

    vis_edges = []
    for e in mindmap_data.get("edges", []):
        vis_edges.append({
            "from": e.get("from") or e.get("source"),
            "to": e.get("to") or e.get("target"),
            "label": e.get("label", ""),
            "color": {"color": "rgba(231,199,123,0.22)", "highlight": "#E7C77B"},
            "font": {"color": "#8B8F9E", "size": 9, "align": "middle", "strokeWidth": 0},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.55}},
            "smooth": {"type": "cubicBezier", "roundness": 0.45},
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
            @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600&family=Inter:wght@400;600&display=swap');
            html, body {{
                margin: 0; padding: 0; width: 100%; height: 100%;
                background: transparent; overflow: hidden;
                font-family: 'Inter', sans-serif;
            }}
            #stage {{ position: relative; width: 100%; height: {height}px; }}
            #mindmap-container {{
                width: 100%; height: {height}px;
                background:
                    radial-gradient(700px 380px at 50% 40%, rgba(124,92,255,.16), transparent 70%),
                    radial-gradient(520px 300px at 12% 90%, rgba(47,216,198,.12), transparent 70%),
                    linear-gradient(180deg, #0C0E17 0%, #06070C 100%);
                border: 1px solid rgba(231,199,123,.18);
                border-radius: 18px;
                box-shadow: inset 0 1px 0 rgba(255,255,255,.06), 0 30px 70px -40px #000;
            }}
            .legend {{
                position: absolute; bottom: 14px; left: 14px;
                background: rgba(8, 9, 15, 0.62);
                backdrop-filter: saturate(150%) blur(16px);
                -webkit-backdrop-filter: saturate(150%) blur(16px);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px; padding: 8px 14px;
                display: flex; gap: 14px; flex-wrap: wrap;
                font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
                color: #A7A9B8; pointer-events: none; z-index: 10;
            }}
            .legend-item {{ display: flex; align-items: center; gap: 6px; }}
            .legend-dot {{ width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 10px -1px currentColor; }}
            .glyph {{
                position: absolute; top: 14px; right: 16px; z-index: 10;
                font-family: 'Cinzel', serif; font-size: 11px; letter-spacing: .28em;
                color: rgba(231,199,123,.65); pointer-events: none;
            }}
        </style>
    </head>
    <body>
        <div id="stage">
            <div id="mindmap-container"></div>
            <div class="glyph">CONSTELLATION OF KNOWLEDGE</div>
            <div class="legend">
                <div class="legend-item"><div class="legend-dot" style="background:#C9A227;color:#C9A227;"></div> Topic</div>
                <div class="legend-item"><div class="legend-dot" style="background:#5B7CFA;color:#5B7CFA;"></div> Sub-Theme</div>
                <div class="legend-item"><div class="legend-dot" style="background:#2FD8C6;color:#2FD8C6;"></div> Finding</div>
                <div class="legend-item"><div class="legend-dot" style="background:#7C5CFF;color:#7C5CFF;"></div> Source</div>
                <div class="legend-item"><div class="legend-dot" style="background:#D9497F;color:#D9497F;"></div> Follow-Up</div>
            </div>
        </div>

        <script type="text/javascript">
            const nodes = new vis.DataSet({nodes_json});
            const edges = new vis.DataSet({edges_json});
            const container = document.getElementById('mindmap-container');
            const network = new vis.Network(container, {{ nodes: nodes, edges: edges }}, {{
                nodes: {{ borderWidthSelected: 2.5 }},
                edges: {{ width: 1.1, selectionWidth: 2 }},
                physics: {{
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{
                        gravitationalConstant: -42,
                        centralGravity: 0.008,
                        springLength: 96,
                        springConstant: 0.10,
                        damping: 0.9
                    }},
                    stabilization: {{ iterations: 140 }}
                }},
                interaction: {{ hover: true, tooltipDelay: 90, zoomView: true, dragView: true }}
            }});

            // gentle parallax tilt for depth
            const stage = document.getElementById('stage');
            stage.addEventListener('mousemove', (e) => {{
                const r = stage.getBoundingClientRect();
                const x = (e.clientX - r.left) / r.width - 0.5;
                const y = (e.clientY - r.top) / r.height - 0.5;
                container.style.transform =
                    `perspective(1200px) rotateY(${{x * 2.2}}deg) rotateX(${{-y * 2.2}}deg)`;
            }});
            stage.addEventListener('mouseleave', () => {{ container.style.transform = 'none'; }});
            container.style.transition = 'transform .5s cubic-bezier(.22,1,.36,1)';
        </script>
    </body>
    </html>
    """
    if hasattr(st, "html"):
        st.html(html_code)
    else:
        components.html(html_code, height=height + 12)


def render_copy_widget(text_to_copy: str, button_label: str = "Copy Markdown"):
    """Glass copy-to-clipboard control."""
    escaped_json = json.dumps(text_to_copy)
    copy_html = f"""
    <button id="copy-btn" style="
        background: linear-gradient(180deg, rgba(255,255,255,.09), rgba(255,255,255,.03));
        border: 1px solid rgba(255,255,255,.12);
        color: #F3F1EA;
        padding: .6rem 1.2rem;
        border-radius: 10px;
        font-family: 'Inter', -apple-system, sans-serif;
        font-size: .82rem;
        font-weight: 600;
        letter-spacing: .02em;
        cursor: pointer;
        width: 100%;
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        box-shadow: 0 8px 24px -14px #000;
        transition: all .28s cubic-bezier(.22,1,.36,1);
    ">{button_label}</button>
    <script>
        const btn = document.getElementById('copy-btn');
        const text = {escaped_json};
        btn.addEventListener('click', () => {{
            navigator.clipboard.writeText(text).then(() => {{
                btn.innerText = '✓ Inscribed to clipboard';
                btn.style.borderColor = '#4ADE9B';
                btn.style.color = '#4ADE9B';
                setTimeout(() => {{
                    btn.innerText = '{button_label}';
                    btn.style.borderColor = 'rgba(255,255,255,.12)';
                    btn.style.color = '#F3F1EA';
                }}, 2200);
            }}).catch(err => console.error('Copy failed', err));
        }});
        btn.addEventListener('mouseenter', () => {{
            btn.style.transform = 'translateY(-2px)';
            btn.style.borderColor = 'rgba(231,199,123,.32)';
            btn.style.color = '#FFE9B0';
        }});
        btn.addEventListener('mouseleave', () => {{
            btn.style.transform = 'none';
            btn.style.borderColor = 'rgba(255,255,255,.12)';
            btn.style.color = '#F3F1EA';
        }});
    </script>
    """
    if hasattr(st, "html"):
        st.html(copy_html)
    else:
        components.html(copy_html, height=48)


# Backwards compatibility alias
render_pipeline = render_planner_stepper