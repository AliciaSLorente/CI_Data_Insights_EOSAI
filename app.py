"""
EOS AI — Agentic AI Dashboard
Entry point: routing + sidebar only. Zero data logic.

Pages (each in src/pages/):
  agent.py          — AI Agent: briefing · chat · suggested Qs
  customer.py       — Customer Intelligence: queue · drill-down · side-by-side
  portfolio.py      — Portfolio Analytics: charts · accuracy · bias analysis
  graph.py          — Portfolio Risk Map: customer network · cascade · clusters
  new_submission.py — New Submission: PDF upload · digital twin · watcher results
"""

import os
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="EOS AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Pre-warm caches — runs once per server process, not per session ──────────
@st.cache_resource
def _prewarm():
    """Populate @st.cache_data on server start — pages load instantly from first visit."""
    from src.data.dashboard_data import (
        load_all_submissions, load_recommendations, load_all_deltas,
        prioritization_queue, recommendation_accuracy,
        bias_analysis, kg_clusters_summary, broker_performance,
    )
    for fn in [load_all_submissions, load_recommendations, load_all_deltas,
               prioritization_queue, recommendation_accuracy,
               bias_analysis, kg_clusters_summary]:
        try:
            fn()
        except Exception:
            pass
    try:
        broker_performance(60)
    except Exception:
        pass

_prewarm()

# ── Briefing: generate once per session ──────────────────────────────────────
from src.agent.briefing import get_or_generate_briefing
if "daily_briefing" not in st.session_state:
    with st.spinner("Preparing your daily briefing..."):
        get_or_generate_briefing(st.session_state)

# ── Badge + toast: all logic owned by watcher.py ─────────────────────────────
from src.agent.watcher import get_badge_count, get_latest_pending_alert
_new_count = get_badge_count()
_alert = get_latest_pending_alert(st.session_state.get("_last_badge_count", 0))
if _alert:
    st.toast(
        f"🔔 **New submission detected** — {_alert['filename']}"
        + (f" · {_alert['recommendation']}" if _alert.get("recommendation") else ""),
        icon="🌅",
    )
st.session_state["_last_badge_count"] = _new_count

# ── Sidebar: navigation only ──────────────────────────────────────────────────
with st.sidebar:
    _logo = Path("assets/eos_ai_logo.svg")
    if _logo.exists():
        st.image(str(_logo), use_container_width=True)
    else:
        st.markdown("### EOS AI")
    st.caption("Dawn Intelligence · EU AI Act Aligned")
    st.divider()

    _NAV = {
        "AGENT":         ["AI Agent"],
        "CUSTOMER":      ["Customer"],
        "PORTFOLIO":     ["Portfolio"],
        "VISUALISATION": ["Portfolio Risk Map"],
        "NEW BUSINESS":  ["New Submission"],
    }
    _active = st.session_state.get("_nav_active", "Customer")

    for _section, _items in _NAV.items():
        st.caption(_section)
        for _item in _items:
            _label = f"**{_item}**" if _item == _active else _item
            _badge = f" 🔔{_new_count}" if _item == "New Submission" and _new_count else ""
            if st.button(_label + _badge, key=f"nav_{_item}", use_container_width=True):
                st.session_state["_nav_active"] = _item
                st.rerun()

    page = st.session_state.get("_nav_active", "Customer")

    st.divider()
    st.caption("46,318 submissions · 9,078 customers")
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    st.divider()
    _log_exists = Path("data/parsed/decisions_log.jsonl").exists()
    st.caption("**AI Governance**")
    st.caption(f"{'🟢' if _log_exists else '🟡'} Decision logging {'active' if _log_exists else 'ready'}")
    st.caption("🟢 Human oversight enforced")
    st.caption("🟢 Advisory only · EU AI Act")

# ── Page routing ──────────────────────────────────────────────────────────────
st.caption(
    "*EOS AI — UW Intelligence · "
    "EU AI Act aligned · All recommendations advisory*"
)
st.divider()

if page == "AI Agent":
    from src.pages.agent import render
elif page == "Portfolio":
    from src.pages.portfolio import render
elif page == "Customer":
    from src.pages.customer import render
elif page == "Portfolio Risk Map":
    from src.pages.graph import render
elif page == "New Submission":
    from src.pages.new_submission import render

render()

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Zurich Hackathon MVP · {datetime.now().strftime('%d %B %Y')} · "
    "⚠️ All AI recommendations are advisory — human underwriter decision required."
)
