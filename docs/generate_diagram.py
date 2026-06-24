"""
Generate agentic architecture diagram for hackathon slides.
Run: python docs/generate_diagram.py
Output: docs/architecture_diagram.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe

fig, ax = plt.subplots(1, 1, figsize=(18, 11))
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis("off")
fig.patch.set_facecolor("#0F1117")
ax.set_facecolor("#0F1117")

# ── Color palette ──────────────────────────────────────────────────────────────
C_BLUE   = "#4C9BE8"
C_PURPLE = "#A855F7"
C_GREEN  = "#22C55E"
C_ORANGE = "#F97316"
C_RED    = "#EF4444"
C_TEAL   = "#14B8A6"
C_GRAY   = "#374151"
C_WHITE  = "#F9FAFB"
C_YELLOW = "#EAB308"
C_BG     = "#1F2937"


def box(ax, x, y, w, h, label, sublabel="", color=C_BLUE, fontsize=11, sublabel_size=8.5, radius=0.25):
    rect = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle=f"round,pad=0.05,rounding_size={radius}",
        linewidth=1.5, edgecolor=color,
        facecolor=C_BG, zorder=3
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.18 if sublabel else 0), label,
            ha="center", va="center", fontsize=fontsize,
            color=color, fontweight="bold", zorder=4)
    if sublabel:
        ax.text(x, y - 0.28, sublabel,
                ha="center", va="center", fontsize=sublabel_size,
                color="#9CA3AF", zorder=4)


def arrow(ax, x1, y1, x2, y2, color="#6B7280", lw=1.5, style="->"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=2)


def label_arrow(ax, x, y, text, color="#9CA3AF", fontsize=7.5):
    ax.text(x, y, text, ha="center", va="center",
            fontsize=fontsize, color=color,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#0F1117", edgecolor="none"),
            zorder=5)


# ── Title ──────────────────────────────────────────────────────────────────────
ax.text(9, 10.4, "Zurich NB Intelligence — Agentic AI Architecture",
        ha="center", va="center", fontsize=16, color=C_WHITE,
        fontweight="bold")
ax.text(9, 10.0, "EU AI Act Aligned  |  Explainable AI  |  Knowledge Graph Discovery",
        ha="center", va="center", fontsize=9.5, color="#9CA3AF")

# ── Layer labels ───────────────────────────────────────────────────────────────
for ly, ltext, lcolor in [
    (9.2, "USER", "#6B7280"),
    (7.5, "INTERFACE", "#6B7280"),
    (5.8, "AGENT LAYER", "#6B7280"),
    (3.8, "TOOLS", "#6B7280"),
    (1.8, "DATA LAYER", "#6B7280"),
]:
    ax.text(0.6, ly, ltext, ha="center", va="center",
            fontsize=7, color=lcolor, fontweight="bold",
            rotation=0, alpha=0.7)

# horizontal dividers
for yline in [8.6, 6.8, 4.8, 2.8]:
    ax.axhline(yline, color="#1F2937", linewidth=1, alpha=0.8, zorder=1)

# ── User ───────────────────────────────────────────────────────────────────────
box(ax, 9, 9.2, 3.5, 0.7, "Underwriter Query", "Natural language question", C_WHITE, 10)

# ── Streamlit Dashboard ────────────────────────────────────────────────────────
box(ax, 9, 7.5, 5.0, 0.8, "Streamlit Dashboard", "AI Agent  |  XAI Explorer  |  Governance  |  KG Insights", C_TEAL, 10.5)

arrow(ax, 9, 8.85, 9, 7.9, C_WHITE)
arrow(ax, 9, 7.1, 9, 6.55, C_TEAL)

# ── Orchestrator ───────────────────────────────────────────────────────────────
box(ax, 9, 5.9, 5.5, 1.0,
    "Orchestrator Agent  (Claude API)",
    "Reasons step-by-step  |  Selects tools  |  Chain of Thought visible",
    C_PURPLE, 11)

# ── Tools row ─────────────────────────────────────────────────────────────────
tool_y = 3.8
tools = [
    (3.0,  "Query\nSubmissions",   "CSV / SQLite",     C_BLUE),
    (6.3,  "Risk\nScore",          "ScoringRules",     C_ORANGE),
    (9.6,  "KG\nDiscovery",        "3 queries",        C_GREEN),
    (12.9, "Explain\nDecision",    "XAI + Narrative",  C_YELLOW),
]

for tx, tlabel, tsub, tcolor in tools:
    box(ax, tx, tool_y, 2.8, 1.3, tlabel, tsub, tcolor, 9.5)
    arrow(ax, 9, 5.4, tx, tool_y + 0.65, tcolor, lw=1.2)
    arrow(ax, tx, tool_y - 0.65, 9, 5.4, tcolor, lw=1.2)

# ── Data layer ────────────────────────────────────────────────────────────────
data_y = 1.8
data_nodes = [
    (3.0,  "Submissions\nCSV / SQLite",   "46K rows",         C_BLUE),
    (6.3,  "PDF\nExtracted Fields",       "162 PDFs / 26col", C_BLUE),
    (9.6,  "Knowledge\nGraph",            "NetworkX",         C_GREEN),
    (12.9, "Audit\nLog + Bias",           "EU AI Act",        C_RED),
]

for dx, dlabel, dsub, dcolor in data_nodes:
    box(ax, dx, data_y, 2.8, 1.2, dlabel, dsub, dcolor, 9, sublabel_size=8)

# arrows tools → data
for (tx, *_), (dx, *_) in zip(tools, data_nodes):
    arrow(ax, tx, tool_y - 0.65, dx, data_y + 0.6, "#374151", lw=1.0)

# ── XAI + Governance output ───────────────────────────────────────────────────
box(ax, 15.8, 5.9, 2.8, 2.2,
    "Output",
    "FAST_TRACK\nSTANDARD_UW\nFRESH_UW\n+ Confidence\n+ XAI Waterfall",
    C_GREEN, 9.5)

arrow(ax, 11.75, 5.9, 14.4, 5.9, C_GREEN, lw=1.5)
label_arrow(ax, 13.1, 6.05, "recommendation\n+ explanation", C_GREEN, 7)

# ── EU AI Act badge ───────────────────────────────────────────────────────────
badge = FancyBboxPatch((14.8, 1.1), 2.9, 0.75,
                        boxstyle="round,pad=0.05,rounding_size=0.15",
                        linewidth=1.5, edgecolor=C_RED,
                        facecolor="#1F2937", zorder=3)
ax.add_patch(badge)
ax.text(16.25, 1.48, "EU AI Act", ha="center", fontsize=8.5,
        color=C_RED, fontweight="bold", zorder=4)
ax.text(16.25, 1.22, "High-Risk · Art.13·14·15", ha="center",
        fontsize=7, color="#9CA3AF", zorder=4)

# ── Human-in-the-loop note ────────────────────────────────────────────────────
ax.text(9, 0.35,
        "⚠️  All recommendations are ADVISORY ONLY — Human underwriter decision required  (EU AI Act Art. 14)",
        ha="center", va="center", fontsize=8.5, color="#9CA3AF",
        style="italic")

plt.tight_layout(pad=0.3)
out = "docs/architecture_diagram.png"
plt.savefig(out, dpi=180, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print(f"Saved -> {out}")
plt.show()
