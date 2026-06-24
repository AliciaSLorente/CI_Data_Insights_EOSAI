"""
Generate ReAct loop and event-driven flow diagrams.
Run: python docs/generate_react_diagram.py
Output: docs/react_loop.png, docs/event_flow.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from pathlib import Path

OUT = Path("docs")
BG = "#0F1117"; CARD = "#1F2937"; WHITE = "#F9FAFB"
BLUE = "#4C9BE8"; PURPLE = "#A855F7"; GREEN = "#22C55E"
ORANGE = "#F97316"; RED = "#EF4444"; TEAL = "#14B8A6"
GRAY = "#6B7280"; YELLOW = "#EAB308"


def box(ax, x, y, w, h, lines, color=BLUE, fs=9):
    rect = FancyBboxPatch((x-w/2, y-h/2), w, h,
                          boxstyle="round,pad=0.05,rounding_size=0.18",
                          linewidth=1.5, edgecolor=color, facecolor=CARD, zorder=3)
    ax.add_patch(rect)
    if isinstance(lines, str): lines = [lines]
    step = h / (len(lines)+1)
    for i, l in enumerate(lines, 1):
        w_txt = "bold" if i == 1 else "normal"
        col = color if i == 1 else "#9CA3AF"
        ax.text(x, y+h/2-step*i, l, ha="center", va="center",
                fontsize=fs, color=col, fontweight=w_txt, zorder=4)


def arr(ax, x1, y1, x2, y2, color=GRAY, lw=1.2, label=""):
    ax.annotate("", xy=(x2,y2), xytext=(x1,y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw), zorder=2)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2+0.1
        ax.text(mx, my, label, ha="center", fontsize=7.5, color=color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.1", facecolor=BG, edgecolor="none"))


# ══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 — ReAct Loop
# ══════════════════════════════════════════════════════════════════════════════
def react_loop():
    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 14); ax.set_ylim(0, 9); ax.axis("off")
    ax.text(7, 8.6, "ReAct Agentic Loop — Zurich NB Intelligence",
            ha="center", fontsize=13, color=WHITE, fontweight="bold")
    ax.text(7, 8.2, "Reason + Act + Observe  |  Tools via MCP  |  Human-in-the-loop",
            ha="center", fontsize=8.5, color="#9CA3AF")

    # Central agent loop
    cx, cy = 7, 4.5

    # Loop boxes
    steps = [
        (7,  7.2, "PERCEIVE", ["Input: UW question\nor new PDF event"], TEAL),
        (11, 5.8, "REASON",   ["LLM (Claude) decides\nwhich tool to call next"], PURPLE),
        (11, 3.2, "ACT",      ["Call tool via MCP\nget_risk_score / find_peers\nsimulate_cascade / ..."], ORANGE),
        (7,  1.8, "OBSERVE",  ["Receive tool result\nJSON with data + governance"], BLUE),
        (3,  3.2, "REASON\nAGAIN", ["Enough information?\nCall more tools?"], PURPLE),
        (3,  5.8, "RESPOND",  ["Generate advisory\noutput for UW"], GREEN),
    ]
    for x, y, title, sub, col in steps:
        box(ax, x, y, 3.2, 1.1, [title]+sub, col, 8.5)

    # Loop arrows
    arr(ax, 7, 6.65, 9.4, 6.2, TEAL, label="question/event")
    arr(ax, 11, 5.25, 11, 3.75, PURPLE, label="tool call")
    arr(ax, 9.4, 3.2, 8.6, 2.2, ORANGE, label="result")
    arr(ax, 5.4, 1.8, 4.6, 3.2, BLUE)
    arr(ax, 3, 3.75, 3, 5.25, PURPLE, label="more tools?")
    arr(ax, 4.6, 5.8, 5.4, 6.5, GREEN, label="done")

    # MCP tools box
    box(ax, 7, 4.5, 3.8, 1.8,
        ["MCP TOOL LAYER",
         "8601 search_portfolio",
         "8602 get_risk_score / delta",
         "8603 KG / cascade / peers",
         "8604 watcher / approve"],
        ORANGE, 7.5)

    # Human decision
    box(ax, 7, 0.7, 4.5, 0.7,
        ["Human Underwriter — reviews advisory output — makes final decision"],
        RED, 8)
    arr(ax, 4.6, 5.8, 4.6, 1.05, GREEN, lw=0.8)
    arr(ax, 9.4, 6.2, 9.4, 1.05, TEAL, lw=0.8)

    ax.text(7, 0.15, "All outputs ADVISORY ONLY — EU AI Act Art.14 (Human Oversight)",
            ha="center", fontsize=7.5, color="#9CA3AF", style="italic")

    plt.tight_layout(pad=0.3)
    out = OUT / "react_loop.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved -> {out}")
    plt.close()


# ══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 — Event-driven flow
# ══════════════════════════════════════════════════════════════════════════════
def event_flow():
    fig, ax = plt.subplots(figsize=(16, 10))
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 16); ax.set_ylim(0, 10); ax.axis("off")
    ax.text(8, 9.6, "Event-Driven Agentic Flow — Full System",
            ha="center", fontsize=13, color=WHITE, fontweight="bold")
    ax.text(8, 9.2, "Three triggers: UW opens dashboard · UW asks question · New PDF arrives",
            ha="center", fontsize=8.5, color="#9CA3AF")

    # ── Trigger 1: Dashboard open ──────────────────────────────────────────────
    box(ax, 2.5, 8.2, 3.8, 0.8, ["TRIGGER 1\nUW opens dashboard"], TEAL)
    box(ax, 2.5, 6.8, 3.8, 1.0, ["Agent activates\nscan_new_submissions()\ngenerate briefing"], PURPLE, 8)
    box(ax, 2.5, 5.4, 3.8, 0.9, ["Show briefing +\nnotifications to UW"], GREEN, 8)
    arr(ax, 2.5, 7.8, 2.5, 7.3, TEAL)
    arr(ax, 2.5, 6.3, 2.5, 5.85, PURPLE)

    # ── Trigger 2: UW question ────────────────────────────────────────────────
    box(ax, 8, 8.2, 3.8, 0.8, ["TRIGGER 2\nUW types question"], BLUE)
    box(ax, 8, 6.8, 3.8, 1.0, ["Orchestrator → Claude\nchooses tools → MCP calls\n15 tools available"], PURPLE, 8)
    box(ax, 8, 5.4, 3.8, 0.9, ["Advisory response\n+ Chain of Thought"], GREEN, 8)
    arr(ax, 8, 7.8, 8, 7.3, BLUE)
    arr(ax, 8, 6.3, 8, 5.85, PURPLE)

    # ── Trigger 3: New PDF ────────────────────────────────────────────────────
    box(ax, 13.5, 8.2, 3.8, 0.8, ["TRIGGER 3\nNew PDF in folder"], ORANGE)
    box(ax, 13.5, 6.8, 3.8, 1.0, ["watcher_server\nscan_new_submissions()\nagent runs full analysis"], PURPLE, 8)
    box(ax, 13.5, 5.4, 3.8, 0.9, ["Result stored\ndashboard badge"], ORANGE, 8)
    arr(ax, 13.5, 7.8, 13.5, 7.3, ORANGE)
    arr(ax, 13.5, 6.3, 13.5, 5.85, PURPLE)

    # ── MCP layer ────────────────────────────────────────────────────────────
    for x, lbl, port, col in [
        (2,   "submissions", "8601", BLUE),
        (5.3, "scoring",     "8602", ORANGE),
        (8.6, "kg+graph",    "8603", GREEN),
        (11.9,"watcher",     "8604", TEAL),
    ]:
        box(ax, x, 3.9, 2.8, 0.9, [lbl, f"port {port}"], col, 8)
    ax.text(8, 4.7, "MCP SERVERS", ha="center", fontsize=9, color=ORANGE, fontweight="bold")
    for x in [2, 5.3, 8.6, 11.9]:
        arr(ax, 8, 5.4, x, 4.35, GRAY, 0.8)
        arr(ax, x, 3.45, 8, 5.4, GRAY, 0.8)
    arr(ax, 2.5, 5.4, 5, 5.4, GRAY, 0.8)

    # ── Data layer ────────────────────────────────────────────────────────────
    for x, lbl, col in [
        (2.5,  "CSVs\n46K submissions", BLUE),
        (6.5,  "Scores\n+Deltas", ORANGE),
        (10.5, "KG graph\n+metrics", GREEN),
        (14,   "pending_\nanalysis.json", TEAL),
    ]:
        box(ax, x, 2.2, 3.0, 0.9, [lbl], col, 8)
    ax.text(8, 1.4, "DATA LAYER", ha="center", fontsize=9, color=GRAY, fontweight="bold")
    for xs, xd in [(2, 2.5), (5.3, 6.5), (8.6, 10.5), (11.9, 14)]:
        arr(ax, xs, 3.45, xd, 2.65, GRAY, 0.7)

    # ── Human decision ────────────────────────────────────────────────────────
    box(ax, 8, 0.55, 7.5, 0.65,
        ["UW reviews advisory output → validates → decides (approve_portfolio_update if needed)"],
        RED, 8)
    arr(ax, 2.5, 4.95, 5.25, 0.9, GREEN, 0.8)
    arr(ax, 8, 4.95, 8, 0.88, GREEN, 0.8)
    arr(ax, 13.5, 4.95, 10.75, 0.9, GREEN, 0.8)

    plt.tight_layout(pad=0.3)
    out = OUT / "event_flow.png"
    plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    print(f"Saved -> {out}")
    plt.close()


if __name__ == "__main__":
    print("Generating ReAct + event-driven diagrams...")
    react_loop()
    event_flow()
    print("Done.")
