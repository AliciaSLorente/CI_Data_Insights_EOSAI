"""
Generate EOS AI architecture diagram — Phase 2 (current).
Run: python docs/generate_diagram.py
Output: docs/architecture_diagram.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe

fig, ax = plt.subplots(1, 1, figsize=(22, 14))
ax.set_xlim(0, 22)
ax.set_ylim(0, 14)
ax.axis("off")
fig.patch.set_facecolor("#0F1117")
ax.set_facecolor("#0F1117")

C_BLUE   = "#4C9BE8"
C_PURPLE = "#A855F7"
C_GREEN  = "#22C55E"
C_ORANGE = "#F97316"
C_RED    = "#EF4444"
C_TEAL   = "#14B8A6"
C_GRAY   = "#374151"
C_WHITE  = "#F9FAFB"
C_YELLOW = "#EAB308"
C_PINK   = "#EC4899"
C_BG     = "#1F2937"
C_DARK   = "#111827"


def box(ax, x, y, w, h, label, sublabel="", color=C_BLUE, fontsize=9.5,
        sublabel_size=7.5, radius=0.2, bold=True):
    rect = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle=f"round,pad=0.05,rounding_size={radius}",
        linewidth=1.5, edgecolor=color,
        facecolor=C_BG, zorder=3
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.15 if sublabel else 0), label,
            ha="center", va="center", fontsize=fontsize,
            color=color, fontweight="bold" if bold else "normal", zorder=4)
    if sublabel:
        ax.text(x, y - 0.22, sublabel,
                ha="center", va="center", fontsize=sublabel_size,
                color="#9CA3AF", zorder=4, linespacing=1.3)


def section_bg(ax, x, y, w, h, color, alpha=0.06):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.2",
        linewidth=0.5, edgecolor=color,
        facecolor=color, alpha=alpha, zorder=1
    )
    ax.add_patch(rect)


def arrow(ax, x1, y1, x2, y2, color="#6B7280", lw=1.3):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=2)


def darrow(ax, x1, y1, x2, y2, color="#6B7280", lw=1.3):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<->", color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=2)


def lbl(ax, x, y, text, color="#9CA3AF", fontsize=7):
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=color,
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#0F1117", edgecolor="none"), zorder=5)


# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(11, 13.55, "EOS AI — Agentic Underwriting Architecture  |  Phase 2",
        ha="center", fontsize=15, color=C_WHITE, fontweight="bold")
ax.text(11, 13.15,
        "Claude Sonnet 4.6  ·  MCP SSE/HTTP (4 servers)  ·  asyncio.gather parallel tools  ·  4-layer memory  ·  RAG  ·  NetworkX KG  ·  EU AI Act Aligned",
        ha="center", fontsize=8.5, color="#9CA3AF")

# ── Layer background bands ────────────────────────────────────────────────────
section_bg(ax, 0.3, 12.2,  21.4, 0.75, C_WHITE,   0.04)   # USER
section_bg(ax, 0.3, 10.5,  21.4, 1.5,  C_TEAL,    0.05)   # INTERFACE
section_bg(ax, 0.3,  8.3,  21.4, 2.0,  C_PURPLE,  0.05)   # AGENT
section_bg(ax, 0.3,  6.6,  21.4, 1.55, C_ORANGE,  0.05)   # MCP
section_bg(ax, 0.3,  4.7,  21.4, 1.75, C_BLUE,    0.05)   # TOOLS
section_bg(ax, 0.3,  2.5,  21.4, 2.05, C_GREEN,   0.04)   # DATA

# Layer labels
for ly, ltxt in [
    (12.58, "USER"),
    (11.25, "UI · STREAMLIT"),
    ( 9.30, "AGENT LAYER"),
    ( 7.38, "MCP SERVERS"),
    ( 5.57, "TOOLS  (18 total)"),
    ( 3.52, "DATA LAYER"),
]:
    ax.text(0.75, ly, ltxt, ha="center", fontsize=6.5, color="#6B7280",
            fontweight="bold", rotation=0, alpha=0.9)

# ── USER row ──────────────────────────────────────────────────────────────────
box(ax,  7.5, 12.58, 4.5, 0.55, "Underwriter (UW)", "Natural language query", C_WHITE, 9)
box(ax, 15.5, 12.58, 4.5, 0.55, "New PDF Submission", "Drop in watch folder", C_YELLOW, 9)

# ── STREAMLIT pages ───────────────────────────────────────────────────────────
pages = [
    ( 2.8, "Customer\nIntelligence", "★ LANDING\nbriefing + queue + drill-down", C_TEAL),
    ( 6.5, "Ask EOS AI",             "18-tool chat\nMVP + UW Workflow Qs",       C_PURPLE),
    (10.2, "Portfolio\nAnalytics",   "trends · bias · accuracy\nArt.10 + 15",    C_BLUE),
    (13.9, "Portfolio\nRisk Map",    "KG network · cascade\nrisk clusters",       C_GREEN),
    (17.6, "New\nSubmission",        "auto-scan · digital twin\npdf upload",      C_ORANGE),
]
for px, plabel, psub, pc in pages:
    box(ax, px, 11.25, 3.4, 1.35, plabel, psub, pc, 8.5)

arrow(ax,  7.5, 12.3,  7.5, 11.95, C_WHITE)
arrow(ax, 15.5, 12.3, 17.6, 11.95, C_YELLOW)

# ── AGENT layer ───────────────────────────────────────────────────────────────
# Orchestrator — center
box(ax, 11.0, 9.50, 7.5, 1.55,
    "Orchestrator  —  Claude Sonnet 4.6  (eu.anthropic.claude-sonnet-4-6)",
    "ReAct loop  MAX_TURNS=10  ·  3-retry backoff  ·  4000-char result cap\n"
    "BATCHING RULE: multiple tools in one turn  →  asyncio.gather (parallel execution)\n"
    "CHART RULE: mandatory type selection (bar · pie · line · scatter · heatmap)",
    C_PURPLE, 9.5)

# Memory — left
box(ax, 3.2, 9.50, 4.2, 1.55,
    "4-Layer Memory",
    "Session  →  chat_history (last 20 turns)\n"
    "Episodic  →  decisions_log.jsonl [-100]\n"
    "Entity    →  customer_memory.json\n"
    "Semantic  →  RAG vector index",
    C_BLUE, 8.5)

# Reflexion — right
box(ax, 19.0, 9.50, 3.6, 1.55,
    "Reflexion  _reflect()",
    "2 checks  ·  max_tokens=80\ndisclaimer present?\nguidelines cited?\nArt. 13 compliance",
    C_PINK, 8.5)

# Pre-warm note
box(ax, 3.2, 8.45, 4.2, 0.5,
    "_prewarm() @st.cache_resource",
    "populates all @st.cache_data on server start",
    C_TEAL, 7.5)

darrow(ax,  5.3, 9.50, 7.25, 9.50, C_BLUE,   lw=1.2)
arrow(ax,  14.75, 9.50, 17.2, 9.50, C_PINK,  lw=1.2)
lbl(ax, 6.25, 9.65, "inject context", C_BLUE, 6.5)
lbl(ax, 15.9, 9.65, "post-response audit", C_PINK, 6.5)

arrow(ax,  7.5, 10.58,  9.5, 10.25, C_TEAL,   lw=1.2)
arrow(ax, 11.0, 10.28, 11.0,  8.35, C_PURPLE, lw=1.5)

# ── MCP SERVERS ───────────────────────────────────────────────────────────────
mcps = [
    ( 3.5, "submissions_server", ":8601\nsearch_portfolio\nget_customer_history\nget_underwriter_patterns", C_BLUE),
    ( 8.2, "scoring_server",     ":8602\nget_risk_score\nget_submission_delta\nget_control_delta",          C_ORANGE),
    (13.2, "kg_server",          ":8603\n9 KG tools + query_uw_guidelines\nNetworkX · Louvain · cascade",   C_GREEN),
    (18.5, "watcher_server",     ":8604\nscan_new_submissions\nget_pending_analyses\napprove_portfolio_update", C_YELLOW),
]
for mx, mlabel, msub, mc in mcps:
    box(ax, mx, 7.38, 4.2, 1.45, mlabel, msub, mc, 8.5)
    darrow(ax, mx, 8.10, mx if mx < 11 else mx, 8.28, mc, lw=1.1)

# connect orchestrator to each MCP
for mx, *_ in mcps:
    arrow(ax, 11.0, 8.72, mx, 8.10, "#6B7280", lw=0.9)

# ── TOOLS ─────────────────────────────────────────────────────────────────────
tool_groups = [
    ( 2.5, "Data Curation",  "search_portfolio\nget_customer_history\nget_underwriter_patterns",             C_BLUE),
    ( 6.5, "UW Metrics",     "get_risk_score\nget_submission_delta\nget_control_delta",                       C_ORANGE),
    (11.0, "KG Discovery",   "portfolio_analytics · find_structural_peers\nfind_cluster_bridges · simulate_cascade\nexplain_recommendation + 3 more", C_GREEN),
    (15.8, "Guidelines RAG", "query_uw_guidelines\n64 chunks · text-embedding-3-large\n3 Zurich UW PDFs",   C_TEAL),
    (19.5, "Watcher",        "scan_new_submissions\nget_pending_analyses\napprove_portfolio_update",          C_YELLOW),
]
for tx, tlabel, tsub, tc in tool_groups:
    box(ax, tx, 5.57, 3.6, 1.55, tlabel, tsub, tc, 8.5)
    arrow(ax, tx, 6.60, tx, 6.35, tc, lw=1.0)

# ── DATA LAYER ────────────────────────────────────────────────────────────────
data_nodes = [
    ( 2.3, "Submissions\nCSV + SQLite",    "46,318 rows\n2021–2026",        C_BLUE),
    ( 5.8, "PDF Extracted\nFields",         "162 PDFs · 25 companies\n26 fields/doc",    C_BLUE),
    ( 9.5, "Knowledge Graph\nNetworkX",     "10,232 nodes\n36,312 edges · KMeans k=3",  C_GREEN),
    (13.5, "RAG Index\nEmbeddings",         "64 chunks\ntext-embedding-3-large",         C_TEAL),
    (17.5, "Audit + Memory\nlogs",          "decisions_log.jsonl (Art.12)\ncustomer_memory.json · pending_analysis.json", C_RED),
]
for dx, dlabel, dsub, dc in data_nodes:
    box(ax, dx, 3.52, 3.6, 1.80, dlabel, dsub, dc, 8.5)
    arrow(ax, dx, 4.80, dx, 4.42, dc, lw=1.0)

# ── EU AI Act badge ───────────────────────────────────────────────────────────
badge = FancyBboxPatch((14.5, 0.45), 7.1, 1.0,
                        boxstyle="round,pad=0.05,rounding_size=0.15",
                        linewidth=1.5, edgecolor=C_RED,
                        facecolor=C_DARK, zorder=3)
ax.add_patch(badge)
ax.text(18.05, 1.08, "EU AI Act — High-Risk AI (Annex III)",
        ha="center", fontsize=8, color=C_RED, fontweight="bold", zorder=4)
ax.text(18.05, 0.72, "Art.10 [OK] Bias analysis  .  Art.12 [OK] decisions_log  .  Art.13 [OK] Reflexion  .  Art.14 [OK] UW capture  .  Art.15 [~] accuracy chart",
        ha="center", fontsize=7, color="#9CA3AF", zorder=4)

# ── Advisory note ─────────────────────────────────────────────────────────────
ax.text(7.5, 0.65,
        "[!]  All recommendations are ADVISORY ONLY",
        ha="center", fontsize=8.5, color="#9CA3AF", style="italic")
ax.text(7.5, 0.28,
        "Human underwriter decision required  (EU AI Act Art. 14)",
        ha="center", fontsize=7.5, color="#6B7280", style="italic")

plt.tight_layout(pad=0.3)
out = "docs/architecture_diagram.png"
plt.savefig(out, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved -> {out}")
plt.show()
