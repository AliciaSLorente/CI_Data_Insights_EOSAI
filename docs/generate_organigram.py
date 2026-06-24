"""
Generate a comprehensive organigram showing all scripts, dependencies and data outputs.
Run: python docs/generate_organigram.py
Output: docs/organigram.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

OUT = Path("docs/organigram.png")

BG    = "#0F1117"
CARD  = "#1F2937"
BLUE  = "#4C9BE8"
GREEN = "#22C55E"
ORANGE= "#F97316"
PURPLE= "#A855F7"
TEAL  = "#14B8A6"
RED   = "#EF4444"
YELLOW= "#EAB308"
GRAY  = "#6B7280"
WHITE = "#F9FAFB"
LGRAY = "#374151"


def box(ax, x, y, w, h, lines, color=BLUE, fs=8.0):
    rect = FancyBboxPatch((x-w/2, y-h/2), w, h,
                          boxstyle="round,pad=0.05,rounding_size=0.15",
                          linewidth=1.4, edgecolor=color,
                          facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    if isinstance(lines, str):
        lines = [lines]
    step = h / (len(lines) + 1)
    for i, line in enumerate(lines, 1):
        weight = "bold" if i == 1 else "normal"
        fsize = fs if i == 1 else fs - 1
        col = color if i == 1 else "#9CA3AF"
        ax.text(x, y + h/2 - step*i, line,
                ha="center", va="center",
                fontsize=fsize, color=col,
                fontweight=weight, zorder=4)


def arr(ax, x1, y1, x2, y2, color=GRAY, lw=1.0, style="->", label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                connectionstyle="arc3,rad=0.0"),
                zorder=2)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.05, my, label, ha="left", va="center",
                fontsize=6.5, color=color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.1", facecolor=BG, edgecolor="none"))


def csv_badge(ax, x, y, name, color=GREEN):
    rect = FancyBboxPatch((x-0.9, y-0.18), 1.8, 0.36,
                          boxstyle="round,pad=0.03,rounding_size=0.08",
                          linewidth=1.0, edgecolor=color,
                          facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    ax.text(x, y, name, ha="center", va="center",
            fontsize=6.5, color=color, zorder=4)


def band(ax, y, h, label, color):
    ax.axhspan(y-h/2, y+h/2, color=color, alpha=0.05, zorder=0)
    ax.text(0.25, y, label, ha="center", va="center",
            fontsize=7, color=color, fontweight="bold", alpha=0.8, rotation=90)


fig, ax = plt.subplots(figsize=(22, 15))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 22)
ax.set_ylim(0, 15)
ax.axis("off")

ax.text(11, 14.6, "Zurich NB Intelligence -- Script Dependency & Data Flow Organigram",
        ha="center", va="center", fontsize=14, color=WHITE, fontweight="bold")
ax.text(11, 14.2, "Left to right: offline scripts (run once) -> pre-computed data -> online dashboard",
        ha="center", va="center", fontsize=8.5, color="#9CA3AF")

# ── Layer bands ────────────────────────────────────────────────────────────────
band(ax, 12.5, 2.4, "RAW\nDATA",    ORANGE)
band(ax, 9.5,  2.4, "OFFLINE\nSCRIPTS", RED)
band(ax, 6.4,  2.0, "PRE-COMPUTED\nDATA", GREEN)
band(ax, 3.5,  2.4, "ONLINE\nDASHBOARD", BLUE)
band(ax, 0.9,  0.9, "AGENT\nTOOLS", PURPLE)

# ══════════════════════════════════════════════════════════════════════════════
# RAW DATA (top)
# ══════════════════════════════════════════════════════════════════════════════
box(ax, 5, 12.5, 3.5, 1.6,
    ["Dataset 1", "all_submissions.csv", "46,318 rows", "Company/Date/Product", "Broker/Status/Premium"],
    ORANGE)
box(ax, 10, 12.5, 3.5, 1.6,
    ["Dataset 2", "pdf_extracted_fields.csv", "162 PDFs * 26 cols", "Controls/Revenue", "Employees"],
    ORANGE)
box(ax, 15, 12.5, 3.5, 1.6,
    ["Derived", "repeat_customers.csv", "customer_broker_", "relationships.csv", "9,078 repeats"],
    ORANGE)

# ══════════════════════════════════════════════════════════════════════════════
# OFFLINE SCRIPTS
# ══════════════════════════════════════════════════════════════════════════════

# mass_scoring.py
box(ax, 3.2, 9.8, 3.6, 1.8,
    ["mass_scoring.py", "ScoringRules per customer", "5 components:", "recent_declines / approval_traj", "freq / premium / latest_status"],
    RED, 7.5)

# mass_deltas.py
box(ax, 8, 9.8, 3.6, 1.8,
    ["mass_deltas.py", "First vs Latest submission", "per customer:", "status_improved/degraded", "premium_delta / broker_changed"],
    RED, 7.5)

# precompute_kg.py
box(ax, 13.5, 9.5, 4.0, 2.4,
    ["precompute_kg.py", "8-stage offline pipeline:", "1. Risk clusters (KMeans k=3)",
     "2. Emerging risks (broker trends)", "3. Growth whitespace",
     "4. Retention risk  5. Re-application",
     "6. Cascade vuln.  7. Heatmap  8. Indicators"],
    RED, 7.2)

# build_knowledge_graph.py
box(ax, 19.5, 9.5, 3.6, 2.4,
    ["build_knowledge_graph.py", "NetworkX + KMeans:", "* Build graph 10,232 nodes", "* Customer/Broker/Sector nodes",
     "* Degree/PageRank/Betweenness", "* Community detection (Louvain)"],
    RED, 7.2)

# Arrows raw -> scripts
arr(ax, 5, 11.72, 3.2, 10.7, ORANGE, 1.0, label="all_submissions")
arr(ax, 5, 11.72, 8,   10.7, ORANGE, 1.0, label="all_submissions")
arr(ax, 5, 11.72, 13.5,10.7, ORANGE, 1.0)
arr(ax, 10,11.72, 13.5,10.7, ORANGE, 1.0, label="pdf_fields")
arr(ax, 15,11.72, 13.5,10.7, ORANGE, 1.0, label="repeat_custs")
arr(ax, 5, 11.72, 19.5,10.7, ORANGE, 1.0)
arr(ax, 10,11.72, 19.5,10.7, ORANGE, 1.0)
arr(ax, 15,11.72, 19.5,10.7, ORANGE, 1.0)

# ══════════════════════════════════════════════════════════════════════════════
# PRE-COMPUTED DATA
# ══════════════════════════════════════════════════════════════════════════════

# mass_scoring output
csv_badge(ax, 3.2, 8.3, "all_recommendations.csv", GREEN)
arr(ax, 3.2, 8.9, 3.2, 8.48, GREEN, 1.2)

# mass_deltas output
csv_badge(ax, 8, 8.3, "all_deltas.csv", GREEN)
arr(ax, 8, 8.9, 8, 8.48, GREEN, 1.2)

# precompute_kg outputs
for i, name in enumerate(["kg_clusters_summary.csv", "kg_emerging_risks.csv",
                           "kg_whitespace.csv", "kg_broker_perf.csv"]):
    csv_badge(ax, 11.5 + i*2.0, 8.3, name, TEAL)
    arr(ax, 13.5, 8.3, 11.5 + i*2.0, 8.48, TEAL, 0.8)

# build_kg outputs
csv_badge(ax, 18.8, 8.3, "knowledge_graph.pkl", PURPLE)
csv_badge(ax, 20.8, 8.3, "graph_metrics.csv", PURPLE)
arr(ax, 19.5, 8.3, 18.8, 8.48, PURPLE, 0.9)
arr(ax, 19.5, 8.3, 20.8, 8.48, PURPLE, 0.9)

# ══════════════════════════════════════════════════════════════════════════════
# ONLINE DASHBOARD (app.py pages)
# ══════════════════════════════════════════════════════════════════════════════

# dashboard_data.py (shared loader)
box(ax, 11, 6.5, 5.0, 1.6,
    ["src/data/dashboard_data.py", "@st.cache_data loaders", "load_all_submissions / load_recommendations",
     "load_all_deltas / prioritization_queue", "kg_* loaders (precomputed or live)"],
    BLUE, 7.5)

# Arrow from pre-computed to dashboard_data
for x in [3.2, 8, 11.5, 13.5, 15.5, 17.5]:
    arr(ax, x, 8.12, 11, 7.3, GREEN, 0.7)
arr(ax, 18.8, 8.12, 11, 7.3, PURPLE, 0.7)

# OVERVIEW page
box(ax, 3, 4.5, 3.4, 1.6,
    ["Overview (Part 1)", "submission_volume_by_year()", "status_distribution()", "top_products()", "broker_performance()"],
    BLUE, 7.5)

# PORTFOLIO PATTERNS (KG Insights)
box(ax, 7.5, 4.5, 3.8, 1.6,
    ["Portfolio Patterns (Part 1)", "kg_clusters_summary()", "detect_emerging_risks()", "find_growth_whitespace()", "src/models/kg_real.py"],
    TEAL, 7.5)

# CUSTOMER DRILL-DOWN
box(ax, 12.5, 4.5, 3.8, 1.6,
    ["Drill-Down (Part 2)", "customer_history()", "load_all_deltas()", "load_pdf_fields()", "XAI: waterfall_chart()"],
    BLUE, 7.5)

# NEW SUBMISSION
box(ax, 17.5, 4.5, 3.8, 1.6,
    ["New Submission (Part 2)", "find_digital_twins()", "src/models/digital_twin.py", "parse_pdf_from_upload()", "generate_twin_narrative()"],
    ORANGE, 7.5)

# Arrows dashboard_data -> pages
for x in [3, 7.5, 12.5, 17.5]:
    arr(ax, 11, 5.7, x, 5.3, BLUE, 0.9)

# ── digital_twin.py detail ─────────────────────────────────────────────────
box(ax, 17.5, 2.8, 3.8, 1.4,
    ["digital_twin.py :: find_digital_twins()", "1. Load 4 CSVs via _load_base()",
     "2. Build profiles for 9,078 customers",
     "3. Score similarity: SIC+40 / Product+25 / Broker+15 / Rev+10",
     "4. Top N twins -> aggregate outcomes",
     "5. Gap analysis vs PDF controls",
     "6. Twin vote + controls adj -> recommendation"],
    ORANGE, 6.8)
arr(ax, 17.5, 3.7, 17.5, 3.5, ORANGE, 1.0)

# ── kg_real.py detail ──────────────────────────────────────────────────────
box(ax, 7.5, 2.8, 3.8, 1.4,
    ["kg_real.py :: Portfolio analytics", "compute_risk_clusters():",
     "  KMeans k=3 on 5 features",
     "detect_emerging_risks():",
     "  Broker YoY decline / Product decline",
     "find_growth_whitespace():",
     "  Low-freq high-approval customers"],
    TEAL, 6.8)
arr(ax, 7.5, 3.7, 7.5, 3.5, TEAL, 1.0)

# ══════════════════════════════════════════════════════════════════════════════
# AGENT TOOLS
# ══════════════════════════════════════════════════════════════════════════════
for i, (lbl, col) in enumerate([
    ("query_submissions", BLUE),
    ("get_risk_score",    ORANGE),
    ("kg_discovery",      TEAL),
    ("explain_decision",  YELLOW),
]):
    bx = 3 + i * 3.8
    box(ax, bx, 0.9, 3.3, 0.65, [lbl, "orchestrator tool"], col, 7.5)

# AI Agent box
box(ax, 11, 1.7, 5.5, 0.65,
    ["AI Agent (orchestrator.py)", "Claude Sonnet 4.6 via Zurich LiteLLM proxy"],
    PURPLE, 8)
for bx in [3, 6.8, 10.6, 14.4]:
    arr(ax, 11, 1.37, bx, 1.23, PURPLE, 0.8)

# Arrow from dashboard -> agent
arr(ax, 12.5, 3.7, 11, 2.03, PURPLE, 1.0, label="AI Agent page")

# ── Legend ─────────────────────────────────────────────────────────────────────
legend_items = [
    (ORANGE, "Raw data / Input CSVs"),
    (RED,    "Offline scripts (run once)"),
    (GREEN,  "Pre-computed output CSVs"),
    (TEAL,   "KG analytics (precompute_kg)"),
    (PURPLE, "NetworkX graph artifacts"),
    (BLUE,   "Online dashboard pages"),
]
for i, (col, lbl) in enumerate(legend_items):
    lx = 0.8 + i * 3.5
    rect = FancyBboxPatch((lx-0.1, 14.45), 0.2, 0.18,
                          boxstyle="round,pad=0.02", linewidth=1,
                          edgecolor=col, facecolor=col, alpha=0.7, zorder=5)
    ax.add_patch(rect)
    ax.text(lx+0.18, 14.54, lbl, va="center", fontsize=7, color="#9CA3AF", zorder=6)

plt.tight_layout(pad=0.2)
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Saved -> {OUT}")
plt.close()
