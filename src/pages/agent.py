"""
AI Agent page — the primary UW interface.
Briefing · Free chat · Suggested questions · Chain of thought.
"""

import json
import re
import os
import streamlit as st
from pathlib import Path


# MVP-oriented questions — covers hackathon success criteria for jury
MVP_SUGGESTED = {
    "MVP-1 · Portfolio & Repeats": [
        "Show repeat customer rate by broker with a chart",
        "Which product lines have the most repeat customers?",
        "Show submission cadence — how often do customers resubmit by product?",
    ],
    "MVP-2 · Deltas & Controls": [
        "Which customers improved their security controls since first submission?",
        "Show customers with the biggest premium change between submissions",
        "Which customers switched broker since their first submission?",
    ],
    "MVP-3 · Scoring & Priority": [
        "What is the bind rate for FAST_TRACK vs FRESH_UW customers?",
        "Show me the top 10 Fast-Track candidates with their scores",
        "Which FRESH_UW customers have the most fixable risk factors?",
    ],
    "KG & Risk Discovery": [
        "Show me bridge nodes — hidden risk connections in the portfolio",
        "If MARSH fails today, what is the cascade impact?",
        "Find structural peers for our highest-risk customer",
    ],
}

# UW workflow questions — daily use by underwriters
SUGGESTED = {
    "Customer Analysis": [
        "Who is our highest-risk repeat customer and why?",
        "Which customers improved their security controls since first submission?",
        "Which customers have been declined 3 times in a row?",
    ],
    "Portfolio Trends": [
        "Which brokers have a declining approval rate year over year?",
        "What are the highest risk customers in the book right now?",
        "Are there any anomalies in the current submission pipeline?",
    ],
    "Opportunities": [
        "Show me the top Fast-Track candidates for this quarter",
        "Which customers should we proactively contact?",
        "Show me growth whitespace opportunities",
    ],
    "Cascade & Hazard Events": [
        "If a cyber attack occurs right now, what is the cascade risk?",
        "Which companies would be most affected by a MARSH portfolio shock?",
        "Show me hidden risks — High Risk customers connected to Low Risk via brokers",
    ],
    "KG & Guidelines": [
        "Find structural peers for our top Fast-Track candidate",
        "Which High Risk customers have the highest network centrality?",
        "What does the Zurich guideline say about backup requirements for cyber coverage?",
    ],
}


def _render_input() -> str | None:
    """Render text input + Ask button. Returns user_input or None."""
    if st.session_state.get("_agent_clear_input"):
        st.session_state.pop("_agent_clear_input", None)
        st.session_state.pop("agent_free_text", None)

    col_in, col_btn = st.columns([5, 1])
    with col_in:
        free_text = st.text_input(
            "question", placeholder="e.g. Who are our top Fast-Track candidates this week?",
            key="agent_free_text", label_visibility="collapsed",
        )
    with col_btn:
        send = st.button("Ask", use_container_width=True, type="primary")

    if send and free_text.strip():
        st.session_state["_agent_pending"] = free_text.strip()
        st.session_state["_agent_clear_input"] = True
        st.rerun()

    return (st.session_state.pop("_agent_pending", None)
            or st.session_state.pop("pending_query", None))


def _render_suggested():
    # Section 1 — MVP Coverage (for jury / hackathon evaluation)
    with st.expander("📊 MVP Coverage — Predefined Questions", expanded=False):
        tabs = st.tabs(list(MVP_SUGGESTED.keys()))
        for tab, (cat, questions) in zip(tabs, MVP_SUGGESTED.items()):
            with tab:
                for q in questions:
                    if st.button(q, key=f"mvp_{hash(q)}", use_container_width=True):
                        st.session_state["pending_query"] = q
                        st.rerun()

    # Section 2 — UW Workflow (daily underwriter use)
    with st.expander("💼 UW Workflow — Standard Questions", expanded=False):
        for cat, questions in SUGGESTED.items():
            st.caption(cat)
            cols = st.columns(3)
            for i, q in enumerate(questions):
                with cols[i % 3]:
                    if st.button(q, key=f"sq_{cat}_{i}", use_container_width=True):
                        st.session_state["pending_query"] = q
                        st.rerun()


def _extract_charts(text: str) -> tuple[str, list]:
    """Extract eos_chart blocks from response text. Returns (clean_text, chart_dicts)."""
    pattern = r'```eos_chart\s*(.*?)\s*```'
    charts = []
    for match in re.finditer(pattern, text, re.DOTALL):
        try:
            charts.append(json.loads(match.group(1)))
        except Exception:
            pass
    clean = re.sub(pattern, '', text, flags=re.DOTALL).strip()
    return clean, charts


def _render_charts(charts: list):
    """Render a list of chart dicts as Plotly figures."""
    import plotly.express as px
    import pandas as pd
    for chart in charts:
        try:
            df = pd.DataFrame(chart.get("data", []))
            if df.empty:
                continue
            ctype = chart.get("type", "bar")
            title = chart.get("title", "")
            x_label = chart.get("x_label", "")
            y_label = chart.get("y_label", "")

            if ctype == "pie":
                if "name" not in df.columns or "value" not in df.columns:
                    continue
                fig = px.pie(df, names="name", values="value", title=title, hole=0.3)

            elif ctype == "line":
                if "x" not in df.columns or "y" not in df.columns:
                    continue
                color_col = "series" if "series" in df.columns else None
                fig = px.line(df, x="x", y="y", color=color_col, title=title,
                              labels={"x": x_label, "y": y_label}, markers=True)

            elif ctype == "scatter":
                if "x" not in df.columns or "y" not in df.columns:
                    continue
                text_col = "name" if "name" in df.columns else None
                fig = px.scatter(df, x="x", y="y", text=text_col, title=title,
                                 labels={"x": x_label, "y": y_label},
                                 color="y", color_continuous_scale="Blues")
                fig.update_traces(textposition="top center", marker=dict(size=10))
                fig.update_layout(coloraxis_showscale=False)

            elif ctype == "heatmap":
                if "x" not in df.columns or "y" not in df.columns or "value" not in df.columns:
                    continue
                pivot = df.pivot(index="y", columns="x", values="value")
                fig = px.imshow(pivot, title=title, color_continuous_scale="Blues",
                                labels={"x": x_label, "y": y_label, "color": "value"})

            else:  # bar (default)
                if "name" not in df.columns or "value" not in df.columns:
                    continue
                fig = px.bar(df, x="name", y="value", title=title,
                             labels={"name": x_label, "value": y_label},
                             color="value", color_continuous_scale="Blues", text="value")
                fig.update_traces(textposition="outside")
                fig.update_layout(coloraxis_showscale=False)

            fig.update_layout(height=350, margin=dict(t=50, b=20))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass


@st.cache_resource
def _get_agent():
    """Single UnderwritingAgent instance per process — data loaded once, reused for all messages."""
    from src.agent.orchestrator import UnderwritingAgent
    return UnderwritingAgent()


def _run_agent(user_input: str):
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    st.session_state.agent_trace = []

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            agent = _get_agent()
            history = [{"role": m["role"], "content": m["content"]}
                       for m in st.session_state.chat_history[:-1]]
            for event in agent.chat(user_input, history=history):
                st.session_state.agent_trace.append(event)
                if event["type"] == "text":
                    full_response += event["content"]
                    placeholder.markdown(full_response + "▌")
                elif event["type"] == "tool_call":
                    placeholder.markdown(full_response + f"\n\n*Calling `{event['tool']}`...*")
            clean, charts = _extract_charts(full_response)
            placeholder.markdown(clean)
            _render_charts(charts)
        except Exception as e:
            clean, charts = full_response, []
            placeholder.markdown(f"⚠️ **Error:** {e}")

        clean += "\n\n*⚠️ Advisory only — human underwriter review required.*"
        st.session_state.chat_history.append({
            "role": "assistant", "content": clean, "charts": charts
        })
    st.rerun()


def render():
    """Entry point called by app.py."""
    st.subheader("🤖 AI Underwriting Agent")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "agent_trace" not in st.session_state:
        st.session_state.agent_trace = []

    user_input = _render_input()
    _render_suggested()
    st.divider()

    # Chat history — newest first
    for msg in reversed(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("charts"):
                _render_charts(msg["charts"])

    # Chain of thought
    if st.session_state.agent_trace:
        with st.expander("Agent Reasoning Chain", expanded=False):
            for step in st.session_state.agent_trace:
                if step["type"] == "tool_call":
                    st.markdown(f"**Tool:** `{step['tool']}`")
                    st.json(step["input"])
                elif step["type"] == "tool_result":
                    try:
                        st.json(json.loads(step["result"]))
                    except Exception:
                        st.markdown(f"**Result:** {step['result'][:300]}")
                elif step["type"] == "text":
                    st.caption(f"Thinking: {step['content'][:200]}")

    if st.session_state.chat_history:
        if st.button("Clear conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.agent_trace = []
            st.rerun()

    if user_input:
        _run_agent(user_input)
