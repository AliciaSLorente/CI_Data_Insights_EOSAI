"""
Customer Intelligence page — Queue + Drill-Down charts only.
Reuses cached loaders from dashboard_data.py. Zero new data logic.
For deeper analysis the UW navigates to AI Agent.
"""

import json
import streamlit as st
import plotly.express as px
from datetime import datetime
from pathlib import Path

DECISIONS_LOG = Path(__file__).resolve().parent.parent.parent / "data" / "parsed" / "decisions_log.jsonl"


def _log_uw_decision(customer: str, decision: str, note: str, ai_rec: str) -> None:
    """Append UW decision to decisions_log.jsonl (Art. 14 EU AI Act — human oversight)."""
    record = {
        "ts": datetime.now().isoformat(),
        "source": "uw_decision_capture",
        "customer": customer,
        "ai_recommendation": ai_rec,
        "uw_decision": decision,
        "uw_note": note,
        "override": decision != ai_rec and ai_rec not in ("", None, "N/A"),
    }
    try:
        DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _queue():
    from src.data.dashboard_data import prioritization_queue, recommendation_accuracy

    # Model validation — proof the scoring works (EU AI Act Art.15)
    acc = recommendation_accuracy()
    if not acc.empty:
        rates = {row["recommendation"]: row["bind_rate"] for _, row in acc.iterrows()}
        st.info(
            "**Model validated** — bind rate by tier: "
            + "  ·  ".join(
                f"**{rec}**: {rates.get(rec, '?')}%"
                for rec in ["FAST_TRACK", "STANDARD_UW", "FRESH_UW"]
                if rec in rates
            )
            + "  \n*Higher score → lower bind rate confirms risk separation (EU AI Act Art.15)*"
        )

    df = prioritization_queue()

    col_s, col_p, col_n = st.columns([3, 2, 1])
    with col_s:
        sort_by = st.selectbox("Sort by", [
            "Risk Score (low→high)", "Risk Score (high→low)", "# Submissions"
        ], key="q_sort")
    with col_p:
        period = st.selectbox("Period", [
            "All time", "Last 7 days", "Last 30 days", "Last 90 days"
        ], key="q_period")
    with col_n:
        show_n = st.selectbox("Show", [50, 100, 200], key="q_n")

    sort_map = {"Risk Score (low→high)": ("risk_score", True),
                "Risk Score (high→low)": ("risk_score", False),
                "# Submissions":         ("submission_count", False)}
    sort_col, sort_asc = sort_map[sort_by]

    # Apply period filter for table only (metrics stay portfolio-wide)
    import pandas as _pd
    df_table = df.copy()
    if period != "All time" and "latest_date" in df_table.columns:
        days_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}
        cutoff = _pd.Timestamp.now() - _pd.Timedelta(days=days_map[period])
        df_filtered = df_table[_pd.to_datetime(df_table["latest_date"], errors="coerce") >= cutoff]
        if not df_filtered.empty:
            df_table = df_filtered

    # Metrics computed from FULL dataset — not the paginated view
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total", f"{len(df):,}")
    with col2: st.metric("Fast-Track",  int((df["recommendation"]=="FAST_TRACK").sum()))
    with col3: st.metric("Standard UW", int((df["recommendation"]=="STANDARD_UW").sum()))
    with col4: st.metric("Fresh UW",    int((df["recommendation"]=="FRESH_UW").sum()))

    # Charts from full dataset
    col1, col2 = st.columns(2)
    with col1:
        counts = df["recommendation"].value_counts().reset_index()
        fig = px.pie(counts, names="recommendation", values="count",
                     color="recommendation",
                     color_discrete_map={"FAST_TRACK":"#22C55E",
                                         "STANDARD_UW":"#F97316",
                                         "FRESH_UW":"#EF4444"},
                     title=f"Recommendation distribution (all {len(df):,})", hole=0.3)
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.histogram(df, x="risk_score", nbins=30,
                           title="Risk score distribution (all customers)",
                           color_discrete_sequence=["#4C9BE8"])
        fig.add_vline(x=35, line_dash="dot", line_color="#22C55E",
                      annotation_text="Fast-Track")
        fig.add_vline(x=65, line_dash="dot", line_color="#EF4444",
                      annotation_text="Fresh UW")
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

    # Table — filtered by period, paginated and sorted
    df_page = df_table.sort_values(sort_col, ascending=sort_asc).head(show_n)
    display = ["Submission Account Name","submission_count","latest_date",
               "product","broker","risk_score","recommendation"]
    display = [c for c in display if c in df_page.columns]
    period_label = f" · {period}" if period != "All time" else ""
    st.caption(f"Showing {len(df_page)} of {len(df_table):,} customers — sorted by {sort_by}{period_label}")
    st.dataframe(df_page[display].rename(columns={
        "Submission Account Name":"Customer","submission_count":"Submissions",
        "latest_date":"Latest","risk_score":"Score","recommendation":"Recommendation",
    }), use_container_width=True, hide_index=True)


def _side_by_side(customer: str):
    """First vs latest submission comparison table."""
    from src.data.dashboard_data import load_pdf_fields
    import pandas as pd

    pdf_data = load_pdf_fields(customer)
    if pdf_data.empty:
        st.info("No PDF data available for this customer.")
        return
    if len(pdf_data) < 2:
        st.info("Need at least 2 PDF submissions for comparison.")
        return

    ctrl_cols  = [c for c in pdf_data.columns if c.startswith("control_")]
    pol_cols   = [c for c in pdf_data.columns if c.startswith("policy_")]
    fin_cols   = ["revenue_millions", "employee_count", "premium_usd"]

    first, latest = pdf_data.iloc[0], pdf_data.iloc[-1]

    def _fmt(v):
        """Convert booleans to readable symbols — avoids raw checkbox rendering."""
        if isinstance(v, bool):
            return "✓" if v else "✗"
        if str(v).lower() in ("true", "1"):
            return "✓"
        if str(v).lower() in ("false", "0", "nan", "none", ""):
            return "✗"
        return str(v) if pd.notna(v) else "—"

    rows = []
    for col in fin_cols + ctrl_cols + pol_cols:
        if col not in pdf_data.columns:
            continue
        label = col.replace("control_","").replace("policy_","Policy: ").replace("_"," ").title()
        v1, v2 = first.get(col), latest.get(col)
        f1, f2 = _fmt(v1), _fmt(v2)
        changed = f1 != f2
        rows.append({"Field": label,
                     f"First ({first.get('pdf_file','')[:20]})": f1,
                     f"Latest ({latest.get('pdf_file','')[:20]})": f2,
                     "Changed": "⚠️ YES" if changed else "—"})

    df = pd.DataFrame(rows)
    st.caption(f"Comparing {len(pdf_data)} PDF submissions")
    st.dataframe(
        df.style.apply(
            lambda r: ["background-color:#3d2020" if r["Changed"]=="⚠️ YES" else "" for _ in r],
            axis=1
        ),
        use_container_width=True, hide_index=True
    )


def _drilldown():
    from src.data.dashboard_data import (
        repeat_customer_list, customer_history,
        load_recommendations, load_all_deltas,
    )
    import pandas as pd

    customers = repeat_customer_list(200)
    customer = st.selectbox("Select customer:", customers, key="dd_cust")
    if not customer:
        return

    history = customer_history(customer)
    recs    = load_recommendations()
    rec_row = recs[recs["company_name"] == customer] if not recs.empty else pd.DataFrame()

    # ── AI Recommendation — prominent headline ────────────────────────────────
    if not rec_row.empty:
        r = rec_row.iloc[0]
        rec   = r["recommendation"]
        score = r["risk_score"]
        conf  = r.get("confidence", "")
        interp = {
            "FAST_TRACK":   "Low risk — stable submission, eligible for expedited processing",
            "STANDARD_UW":  "Moderate risk — proceed with standard underwriting review",
            "FRESH_UW":     "High risk — material changes detected, full review required",
        }.get(rec, "")
        color = {"FAST_TRACK": "success", "STANDARD_UW": "warning", "FRESH_UW": "error"}.get(rec, "info")
        conf_str = f" · Confidence: {conf}" if conf else ""
        getattr(st, color)(f"**AI Recommendation: {rec}** — Score {score:.0f}/100{conf_str}  \n{interp}")

        # ── Risk Score Waterfall — score component breakdown (EU AI Act Art.13) ─
        comp_cols = [c for c in recs.columns if c.startswith("comp_")]
        if comp_cols:
            comps = {c.replace("comp_","").replace("_"," ").title(): float(r[c])
                     for c in comp_cols if pd.notna(r.get(c))}
            if comps:
                import plotly.graph_objects as go
                names  = list(comps.keys())
                values = list(comps.values())
                base   = score - sum(v for v in values if v > 0)
                measure = ["relative"] * len(names) + ["total"]
                fig = go.Figure(go.Waterfall(
                    orientation="h",
                    measure=measure,
                    x=values + [score],
                    y=names + ["**Final Score**"],
                    base=base,
                    connector={"line": {"color": "#4C9BE8", "width": 1}},
                    increasing={"marker": {"color": "#EF4444"}},
                    decreasing={"marker": {"color": "#22C55E"}},
                    totals={"marker": {"color": "#F4A726", "line": {"color": "#D97706", "width": 2}}},
                    texttemplate="%{x:+.1f}",
                    textposition="outside",
                ))
                fig.update_layout(
                    title=dict(text="Score Components — what drove the risk score", font=dict(size=13)),
                    height=max(200, len(names) * 38 + 80),
                    margin=dict(l=10, r=60, t=40, b=10),
                    xaxis=dict(title="Points", range=[0, max(score + 10, 100)]),
                    showlegend=False,
                )
                with st.expander("📊 Score Breakdown", expanded=False):
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("🔴 Increases risk · 🟢 Reduces risk · 🟡 Final score  |  Advisory only")

    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Submissions", len(history))
    with col2: st.metric("Products",    history["Product Name"].nunique() if not history.empty else 0)
    with col3:
        latest = history["Current Status Description"].iloc[-1] if not history.empty else "—"
        st.metric("Latest Status", latest)

    # Pre-Call Brief
    if st.button(f"📋 Pre-Call Brief for {customer}", type="primary", key="brief_btn"):
        st.session_state["_nav_active"] = "AI Agent"
        st.session_state["pending_query"] = (
            f"Generate a pre-call brief for {customer} in 3 bullet points: "
            "1) Key changes since first submission (controls, status, broker), "
            "2) Main risk concern for the UW to address, "
            "3) The single most important question to ask the broker. "
            "Be concise — this is read in 30 seconds before a broker call."
        )
        st.rerun()

    if not history.empty:
        col1, col2 = st.columns(2)
        with col1:
            yearly = (history.dropna(subset=["Year"])
                      .assign(Year=lambda d: d["Year"].astype(int))
                      .groupby("Year").size().reset_index(name="Submissions"))
            fig = px.bar(yearly, x="Year", y="Submissions", text="Submissions",
                         title="Submission frequency",
                         color_discrete_sequence=["#4C9BE8"])
            fig.update_xaxes(type="category")
            fig.update_traces(textposition="outside")
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            sh = history["Current Status Description"].value_counts().reset_index()
            sh.columns = ["Status","Count"]
            fig = px.pie(sh, names="Status", values="Count",
                         hole=0.3, title="Decision history")
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)

    # Delta summary
    deltas = load_all_deltas()
    if not deltas.empty:
        d_row = deltas[deltas["company_name"] == customer]
        if not d_row.empty:
            d = d_row.iloc[0]
            st.divider()
            c1,c2,c3,c4 = st.columns(4)
            with c1: st.metric("Span", f"{int(d['months_span'])} months")
            with c2:
                trend = "Improved" if d["status_improved"] else ("Degraded" if d["status_degraded"] else "Stable")
                st.metric("Trend", trend)
            with c3:
                prem = f"{d['premium_delta_pct']:+.1f}%" if pd.notna(d["premium_delta_pct"]) else "N/A"
                st.metric("Premium delta", prem)
            with c4: st.metric("Broker changed", "Yes" if d["broker_changed"] else "No")

    # Controls evolution heatmap (Dataset 2 — PDF data, 25 Cyber pilot customers)
    from src.data.dashboard_data import load_pdf_companies, load_pdf_fields
    if customer in load_pdf_companies():
        pdf_data = load_pdf_fields(customer)
        if not pdf_data.empty:
            st.divider()
            st.markdown("**Controls evolution across PDF submissions**")
            st.caption("Green = present · Red = absent — answers 'what datapoints fell off?'")
            ctrl_cols = [c for c in pdf_data.columns if c.startswith("control_")]
            if ctrl_cols:
                import plotly.graph_objects as go
                labels = [c.replace("control_","").replace("_"," ").title() for c in ctrl_cols]
                pdfs   = [str(row.get("pdf_file",""))[:30] for _, row in pdf_data.iterrows()]
                z = [[1 if str(row.get(c,"False")).lower()=="true" else 0
                      for c in ctrl_cols]
                     for _, row in pdf_data.iterrows()]
                fig = go.Figure(go.Heatmap(
                    z=z, x=labels, y=pdfs,
                    colorscale=[[0,"#EF4444"],[1,"#22C55E"]],
                    showscale=False,
                    hovertemplate="%{x}<br>%{y}<br>%{z}<extra></extra>",
                ))
                fig.update_layout(
                    title="Control presence per submission (green=YES, red=NO)",
                    height=max(180, len(pdfs)*35),
                    xaxis=dict(tickangle=45),
                    margin=dict(l=40, r=20, t=50, b=40),
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.divider()
        st.caption(
            "ℹ️ Controls heatmap available for the 25 Cyber pilot customers (Dataset 2). "
            "For this customer, use the **Side-by-Side** tab or ask the agent: "
            "*'What controls changed for this customer?'*"
        )

    # ── UW Decision Capture (Art. 14 EU AI Act — human oversight) ────────────
    st.divider()
    st.markdown("**UW Decision**")
    ai_rec = rec_row.iloc[0]["recommendation"] if not rec_row.empty else "N/A"
    col_dec, col_note, col_save = st.columns([2, 3, 1])
    with col_dec:
        uw_decision = st.selectbox(
            "Decision:",
            ["— Select —", "FAST_TRACK", "STANDARD_UW", "FRESH_UW", "DECLINE", "REFER_SENIOR"],
            key=f"uw_dec_{customer}",
        )
    with col_note:
        uw_note = st.text_input(
            "Note (optional):", key=f"uw_note_{customer}",
            placeholder="e.g. Strong MFA posture, broker reliable",
        )
    with col_save:
        st.write("")
        if st.button("Log Decision", key=f"log_dec_{customer}", type="primary", use_container_width=True):
            if uw_decision != "— Select —":
                _log_uw_decision(customer, uw_decision, uw_note, ai_rec)
                override = uw_decision != ai_rec and ai_rec != "N/A"
                st.success(f"Logged: **{uw_decision}**" + (" *(override)*" if override else ""))
            else:
                st.warning("Select a decision first.")

    # Full history table
    if not history.empty:
        st.divider()
        st.markdown("**Full submission history**")
        cols = ["date_str","Product Name","National Broker Name",
                "Current Status Description","Quoted Premium Amount","Underwriter Name"]
        cols = [c for c in cols if c in history.columns]
        st.dataframe(history[cols].rename(columns={
            "date_str":"Date","Product Name":"Product",
            "National Broker Name":"Broker","Current Status Description":"Status",
            "Quoted Premium Amount":"Premium ($)","Underwriter Name":"UW",
        }), use_container_width=True, hide_index=True)


def render():
    st.subheader("👤 Customer Intelligence")

    # ── Daily Briefing banner — generated once per session in app.py ──────────
    briefing = st.session_state.get("daily_briefing", "")
    if briefing:
        with st.expander("📋 Daily Briefing", expanded=not st.session_state.get("briefing_read", False)):
            st.markdown(briefing)
            col_ask, col_close = st.columns([3, 1])
            with col_ask:
                if st.button("Ask agent about this →", key="briefing_to_agent", type="primary"):
                    st.session_state["_nav_active"] = "AI Agent"
                    st.session_state["pending_query"] = (
                        "Based on today's briefing, what should I focus on first?"
                    )
                    st.rerun()
            with col_close:
                if st.button("Mark read", key="briefing_close"):
                    st.session_state["briefing_read"] = True
                    st.rerun()

    tab_q, tab_d, tab_s = st.tabs(["Prioritization Queue", "Drill-Down", "Side-by-Side"])
    with tab_q:
        _queue()
    with tab_d:
        _drilldown()
    with tab_s:
        st.markdown("### First vs Latest Submission — What Changed?")
        st.caption("Field-by-field comparison of a customer's first and most recent PDF submission. "
                   "Highlighted rows = changed values.")
        from src.data.dashboard_data import repeat_customer_list
        c = st.selectbox("Customer:", repeat_customer_list(200), key="ss_cust")
        if c:
            _side_by_side(c)
            st.divider()
            if st.button(f"🤖 Ask agent: what changed for {c}?", type="primary",
                         key=f"ss_ask_{c}"):
                st.session_state[f"ss_run_{c}"] = True

            if st.session_state.pop(f"ss_run_{c}", False):
                query = (
                    f"What changed for {c} between their first and latest submission? "
                    "Include controls delta, status trajectory, and what the UW should ask the broker."
                )
                placeholder = st.empty()
                full_response = ""
                try:
                    from src.pages.agent import _get_agent
                    agent = _get_agent()
                    for event in agent.chat(query):
                        if event["type"] == "text":
                            full_response += event["content"]
                            placeholder.markdown(full_response + "▌")
                    placeholder.empty()  # clear streaming cursor
                except Exception as e:
                    placeholder.error(f"Agent error: {e}")
                st.session_state[f"ss_resp_{c}"] = full_response
                st.rerun()  # clean render — show stored response once only

            if st.session_state.get(f"ss_resp_{c}"):
                st.markdown("### Agent Analysis")
                st.markdown(st.session_state[f"ss_resp_{c}"])

