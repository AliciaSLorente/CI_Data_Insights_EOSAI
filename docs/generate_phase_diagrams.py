"""
Generate architecture diagrams for Phase 1, 2 and 3.
Run: python docs/generate_phase_diagrams.py
Output: docs/phase1_diagram.png, docs/phase2_diagram.png, docs/phase3_diagram.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUT = Path("docs")

# ── Colour palette ─────────────────────────────────────────────────────────────
BG      = "#0F1117"
CARD    = "#1F2937"
BLUE    = "#4C9BE8"
GREEN   = "#22C55E"
ORANGE  = "#F97316"
PURPLE  = "#A855F7"
TEAL    = "#14B8A6"
RED     = "#EF4444"
YELLOW  = "#EAB308"
GRAY    = "#6B7280"
WHITE   = "#F9FAFB"
LGRAY   = "#374151"


def _box(ax, x, y, w, h, label, sub="", color=BLUE, fs=9.5, sfs=8):
    rect = FancyBboxPatch((x - w/2, y - h/2), w, h,
                          boxstyle="round,pad=0.05,rounding_size=0.2",
                          linewidth=1.5, edgecolor=color,
                          facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    ax.text(x, y + (0.15 if sub else 0), label,
            ha="center", va="center", fontsize=fs,
            color=color, fontweight="bold", zorder=4)
    if sub:
        ax.text(x, y - 0.22, sub,
                ha="center", va="center", fontsize=sfs,
                color="#9CA3AF", zorder=4)


def _arr(ax, x1, y1, x2, y2, color=GRAY, lw=1.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw),
                zorder=2)


def _band(ax, y, h, label, color):
    ax.axhspan(y - h/2, y + h/2, color=color, alpha=0.06, zorder=0)
    ax.text(0.3, y, label, ha="center", va="center",
            fontsize=7, color=color, fontweight="bold", alpha=0.7)


def _setup(title, subtitle=""):
    fig, ax = plt.subplots(figsize=(16, 10))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.text(8, 9.6, title, ha="center", va="center",
            fontsize=15, color=WHITE, fontweight="bold")
    if subtitle:
        ax.text(8, 9.2, subtitle, ha="center", va="center",
                fontsize=9, color="#9CA3AF")
    return fig, ax


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1
# ══════════════════════════════════════════════════════════════════════════════
def phase1():
    fig, ax = _setup(
        "Phase 1 -- Proof of Value",
        "Renewal-like intelligence for NB decisions  |  EU AI Act Aligned  |  Advisory only"
    )

    # Layer bands
    _band(ax, 8.5, 1.0, "UW",       TEAL)
    _band(ax, 7.0, 1.0, "DASHBOARD",BLUE)
    _band(ax, 5.4, 1.2, "AGENT",    PURPLE)
    _band(ax, 3.5, 1.4, "TOOLS",    ORANGE)
    _band(ax, 1.5, 1.4, "DATA",     GREEN)

    # UW
    _box(ax, 8, 8.5, 4, 0.65, "Underwriter", "Natural language query + Dashboard navigation", WHITE, 10)

    # Dashboard - 3 pages
    for x, lbl, sub, col in [
        (3.5, "Portfolio Analytics", "Dataset 1 insights", BLUE),
        (8,   "Customer Intelligence", "Delta + History", TEAL),
        (12.5,"New Submission", "AI-powered analysis", ORANGE),
    ]:
        _box(ax, x, 7.0, 3.6, 0.65, lbl, sub, col)
    _arr(ax, 8, 8.17, 3.5, 7.33, BLUE)
    _arr(ax, 8, 8.17, 8,   7.33, TEAL)
    _arr(ax, 8, 8.17, 12.5,7.33, ORANGE)

    # Agent
    _box(ax, 8, 5.4, 6, 0.8,
         "Orchestrator Agent  (Claude Sonnet 4.6)",
         "Reasons step-by-step  |  Selects tools  |  Chain of Thought visible",
         PURPLE, 10.5)
    for x in [3.5, 8, 12.5]:
        _arr(ax, x, 6.67, 8, 5.8, PURPLE, 1.0)

    # Tools
    tools = [
        (2.0,  "query_submissions", "Dataset 1 search",   BLUE),
        (5.3,  "get_delta_analysis","First vs Latest",     ORANGE),
        (8.6,  "score_customer",    "Risk + Recommendation",GREEN),
        (11.9, "explain_decision",  "XAI Narrative",       YELLOW),
    ]
    for x, lbl, sub, col in tools:
        _box(ax, x, 3.5, 2.9, 0.9, lbl, sub, col, 9)
        _arr(ax, 8, 5.0, x, 3.95, col, 1.0)
        _arr(ax, x, 3.05, 8, 5.0, col, 1.0)

    # Data layer
    data = [
        (2.5,  "Dataset 1\nall_submissions.csv", "46K submissions",  BLUE),
        (6.0,  "Dataset 2\nPDF Extracted",       "162 PDFs  26 cols",ORANGE),
        (9.5,  "all_deltas.csv",                  "Delta first-last", GREEN),
        (13.0, "all_recommendations.csv",          "9K scored",       TEAL),
    ]
    for x, lbl, sub, col in data:
        _box(ax, x, 1.5, 2.8, 0.9, lbl, sub, col, 8.5)

    for (tx, *_), (dx, *_) in zip(tools, data):
        _arr(ax, tx, 3.05, dx, 1.95, LGRAY, 0.8)

    # Governance badge
    rect = FancyBboxPatch((13.2, 4.9), 2.5, 1.0,
                          boxstyle="round,pad=0.05,rounding_size=0.15",
                          linewidth=1.5, edgecolor=RED, facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    ax.text(14.45, 5.58, "AI Governance", ha="center", fontsize=8.5,
            color=RED, fontweight="bold", zorder=4)
    ax.text(14.45, 5.27, "Audit  |  EU AI Act", ha="center",
            fontsize=7.5, color="#9CA3AF", zorder=4)
    ax.text(14.45, 4.98, "Art. 13  14  15", ha="center",
            fontsize=7, color="#6B7280", zorder=4)

    ax.text(8, 0.25,
            "All recommendations ADVISORY ONLY -- Human underwriter decision required  (EU AI Act Art. 14)",
            ha="center", fontsize=8, color="#9CA3AF", style="italic")

    plt.tight_layout(pad=0.3)
    out = OUT / "phase1_diagram.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved -> {out}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2
# ══════════════════════════════════════════════════════════════════════════════
def phase2():
    fig, ax = _setup(
        "Phase 2 -- Agentic + Knowledge Graph + MCPs",
        "Proactive-on-demand agent  |  NetworkX real graph  |  MCP tool protocol"
    )

    _band(ax, 8.5, 1.0, "UW",        TEAL)
    _band(ax, 7.0, 1.0, "DASHBOARD", BLUE)
    _band(ax, 5.3, 1.2, "AGENT",     PURPLE)
    _band(ax, 3.4, 1.4, "MCP TOOLS", ORANGE)
    _band(ax, 1.5, 1.4, "DATA + KG", GREEN)

    # UW
    _box(ax, 8, 8.5, 5, 0.65,
         "Underwriter", "Query  |  Dashboard  |  Proactive insights surface automatically",
         WHITE, 10)

    # Dashboard
    for x, lbl, sub, col in [
        (3,   "Portfolio",          "Trends + KG clusters", BLUE),
        (8,   "Customer Intel",     "Delta + Graph position", TEAL),
        (12.5,"New Submission",     "Twin + MCP-powered", ORANGE),
    ]:
        _box(ax, x, 7.0, 3.4, 0.65, lbl, sub, col)
    _arr(ax, 8, 8.17, 3,    7.33, BLUE)
    _arr(ax, 8, 8.17, 8,    7.33, TEAL)
    _arr(ax, 8, 8.17, 12.5, 7.33, ORANGE)

    # Agent - proactive
    _box(ax, 6.5, 5.3, 7, 0.8,
         "Orchestrator Agent  (Claude Sonnet 4.6)",
         "Reactive queries  |  Proactive portfolio summary on load  |  Pre-proposed Q by category",
         PURPLE, 10)
    for x in [3, 8, 12.5]:
        _arr(ax, x, 6.67, 6.5, 5.7, PURPLE, 0.9)

    # MCP Tools
    mcp_tools = [
        (1.4,  "mcp://submissions", "Dataset 1 query",  BLUE),
        (4.2,  "mcp://delta",       "PDF delta analysis",ORANGE),
        (7.0,  "mcp://kg",          "Graph traversal",   GREEN),
        (9.8,  "mcp://score",       "Risk + XAI",        YELLOW),
        (12.6, "mcp://websearch",   "Company context",   TEAL),
    ]
    for x, lbl, sub, col in mcp_tools:
        _box(ax, x, 3.4, 2.5, 0.9, lbl, sub, col, 8.5)
        _arr(ax, 6.5, 4.9, x, 3.85, col, 0.9)
        _arr(ax, x, 2.95, 6.5, 4.9, col, 0.9)

    # Data + KG
    data = [
        (1.4,  "all_submissions", "46K rows",           BLUE),
        (4.2,  "all_deltas\nPDF fields", "162 PDFs",    ORANGE),
        (7.0,  "knowledge_graph.pkl", "NetworkX 10K nodes",GREEN),
        (9.8,  "all_recommendations\ngraph_metrics", "Scored",YELLOW),
        (12.6, "Web / External", "Real-time signals",   TEAL),
    ]
    for x, lbl, sub, col in data:
        _box(ax, x, 1.5, 2.5, 0.9, lbl, sub, col, 8)

    for (tx, *_), (dx, *_) in zip(mcp_tools, data):
        _arr(ax, tx, 2.95, dx, 1.95, LGRAY, 0.7)

    # KMeans badge
    rect = FancyBboxPatch((14.0, 3.0), 1.8, 0.8,
                          boxstyle="round,pad=0.05,rounding_size=0.1",
                          linewidth=1.2, edgecolor=GREEN, facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    ax.text(14.9, 3.5, "KMeans", ha="center", fontsize=8, color=GREEN,
            fontweight="bold", zorder=4)
    ax.text(14.9, 3.2, "k=3 validated", ha="center", fontsize=7,
            color="#9CA3AF", zorder=4)

    # Model metrics badge
    rect2 = FancyBboxPatch((14.0, 4.0), 1.8, 0.8,
                           boxstyle="round,pad=0.05,rounding_size=0.1",
                           linewidth=1.2, edgecolor=YELLOW, facecolor=CARD, zorder=3)
    ax.add_patch(rect2)
    ax.text(14.9, 4.5, "Model Metrics", ha="center", fontsize=8, color=YELLOW,
            fontweight="bold", zorder=4)
    ax.text(14.9, 4.2, "Score calibration", ha="center", fontsize=7,
            color="#9CA3AF", zorder=4)

    ax.text(8, 0.25,
            "Proactive insights surface on dashboard load -- Agent informs, does NOT act -- Human oversight maintained",
            ha="center", fontsize=8, color="#9CA3AF", style="italic")

    plt.tight_layout(pad=0.3)
    out = OUT / "phase2_diagram.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved -> {out}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3
# ══════════════════════════════════════════════════════════════════════════════
def phase3():
    fig, ax = _setup(
        "Phase 3 -- Multi-Agent  |  Production",
        "MyBook/PC integration  |  Feedback loop  |  EU AI Act Art.43 conformity assessment"
    )

    _band(ax, 8.8, 0.8, "SYSTEMS",   TEAL)
    _band(ax, 7.4, 0.8, "INTERFACE", BLUE)
    _band(ax, 5.8, 1.2, "AGENTS",    PURPLE)
    _band(ax, 3.8, 1.4, "MCP TOOLS", ORANGE)
    _band(ax, 1.8, 1.4, "DATA",      GREEN)

    # External systems
    for x, lbl, col in [(3, "MyBook", TEAL), (8, "PolicyCenter", TEAL),
                         (13, "eFile", TEAL)]:
        _box(ax, x, 8.8, 2.8, 0.55, lbl, "Live Zurich system", col, 9)

    # Interface
    _box(ax, 8, 7.4, 8, 0.6,
         "UW Interface + API Layer (FastAPI)",
         "Authentication (Azure AD SSO)  |  Multi-tenant  |  Streamlit or React",
         BLUE, 10)

    # Multi-agent
    agents = [
        (2.5,  "Data Agent",      "Ingest + enrich",  BLUE),
        (5.5,  "Risk Agent",      "Score + recommend", ORANGE),
        (8.5,  "KG Agent",        "Graph discovery",  GREEN),
        (11.5, "Report Agent",    "XAI + narratives", YELLOW),
        (14.5, "Governance Agent","Audit + compliance",RED),
    ]
    for x, lbl, sub, col in agents:
        _box(ax, x, 5.8, 2.7, 0.9, lbl, sub, col, 9)
    _arr(ax, 8, 7.1, 8, 6.25, PURPLE, 1.2)
    # Orchestrator connects to all agents
    for x, *_ in agents:
        _arr(ax, 8, 6.25, x, 6.25, PURPLE, 0.7)

    # Orchestrator node
    rect = FancyBboxPatch((6.5, 5.95), 3, 0.6,
                          boxstyle="round,pad=0.05,rounding_size=0.1",
                          linewidth=2, edgecolor=PURPLE, facecolor=CARD, zorder=5)
    ax.add_patch(rect)
    ax.text(8, 6.25, "Orchestrator", ha="center", va="center",
            fontsize=9.5, color=PURPLE, fontweight="bold", zorder=6)

    # MCP Tools
    mcp = [
        (2.5,  "mcp://data",     BLUE),
        (5.5,  "mcp://scoring",  ORANGE),
        (8.5,  "mcp://kg",       GREEN),
        (11.5, "mcp://report",   YELLOW),
        (14.5, "mcp://audit",    RED),
    ]
    for x, lbl, col in mcp:
        _box(ax, x, 3.8, 2.5, 0.75, lbl, "MCP server", col, 8.5)

    for (ax_, *_), (mx, *_) in zip(agents, mcp):
        _arr(ax, ax_, 5.35, mx, 4.18, LGRAY, 0.8)

    # Data
    data_nodes = [
        (2.5,  "Live submissions",   "Real-time",      BLUE),
        (5.5,  "Scored + deltas",    "Versioned",      ORANGE),
        (8.5,  "KG + embeddings",    "Vector DB",      GREEN),
        (11.5, "Outcomes + claims",  "Loss ratio data",YELLOW),
        (14.5, "Audit + compliance", "Art.43 ready",   RED),
    ]
    for x, lbl, sub, col in data_nodes:
        _box(ax, x, 1.8, 2.5, 0.85, lbl, sub, col, 8)

    for (mx, *_), (dx, *_) in zip(mcp, data_nodes):
        _arr(ax, mx, 3.43, dx, 2.23, LGRAY, 0.7)

    # Feedback loop
    ax.annotate("", xy=(1.0, 5.8), xytext=(1.0, 1.8),
                arrowprops=dict(arrowstyle="<->", color=GREEN,
                                lw=1.5, connectionstyle="arc3,rad=0.0"),
                zorder=2)
    ax.text(0.55, 3.8, "Feedback\nloop", ha="center", fontsize=7.5,
            color=GREEN, fontweight="bold")

    ax.text(8, 0.3,
            "Third-party conformity assessment required (EU AI Act Art.43)  |  "
            "GDPR-compliant learning  |  Drift monitoring  |  Human oversight at all stages",
            ha="center", fontsize=7.5, color="#9CA3AF", style="italic")

    plt.tight_layout(pad=0.3)
    out = OUT / "phase3_diagram.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved -> {out}")
    plt.close()


if __name__ == "__main__":
    print("Generating phase diagrams...")
    phase1()
    phase2()
    phase3()
    print("Done. Files in docs/")
