"""
New Submission page — PDF upload + digital twin analysis.
Shows agent pre-analysed submissions from the watcher,
plus manual upload with full digital twin recommendation.
"""

import os
import streamlit as st
from pathlib import Path


def _pending_in_folder() -> list:
    from src.agent.watcher import get_pending_analyses
    pending = get_pending_analyses()
    return [p for p in pending if not p.get("uw_reviewed", False)]


def _auto_scan() -> int:
    """
    Scan watch folder for unprocessed PDFs and analyse them.
    Delegates to watcher.py — single source of truth for scanning logic.
    Fast no-op when nothing new (file-list diff only).
    Returns count of newly analysed PDFs.
    """
    from src.agent.watcher import (
        analyse_new_pdf, _load_processed, _save_processed,
        _load_pending, _save_pending, DATA,
    )
    watch_env = os.getenv("UW_WATCH_FOLDER", "")
    watch = Path(watch_env) if watch_env else DATA.parent / "raw" / "new_submissions"
    if not watch.exists():
        return 0
    processed = _load_processed()
    new_pdfs  = [p for p in watch.glob("*.pdf") if p.name not in processed]
    if not new_pdfs:
        return 0
    pending = _load_pending()
    for pdf in new_pdfs:
        result = analyse_new_pdf(pdf)
        pending.append(result)
        processed.append(pdf.name)
    _save_pending(pending)
    _save_processed(processed)
    return len(new_pdfs)


def _render_pending(unreviewed: list):
    from src.agent.watcher import mark_reviewed

    st.markdown(f"### 🔔 {len(unreviewed)} Submission(s) Pre-analysed by Agent")
    col_hdr, col_clear = st.columns([4, 1])
    with col_clear:
        if st.button("Clear all", key="clear_pending"):
            for item in unreviewed:
                mark_reviewed(item["filename"], "DISMISSED", "Cleared by UW")
            st.rerun()

    for item in unreviewed:
        rec = item.get("agent_recommendation", item.get("quick_recommendation", "STANDARD_UW"))
        rec_color = {"FAST_TRACK": "success", "STANDARD_UW": "warning", "FRESH_UW": "error"}
        with st.expander(f"**{item['filename']}** — {rec}", expanded=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                ext = item.get("extraction", {})
                if ext.get("product"):
                    st.markdown(f"**Product:** {ext['product']} | **Broker:** {ext.get('broker','N/A')}")
                analysis = item.get("agent_analysis", item.get("quick_rationale", ""))
                if analysis:
                    st.markdown(f"**Agent analysis:** {analysis[:400]}")
                tools = item.get("tools_used", [])
                if tools:
                    st.caption(f"Tools used: {', '.join(tools)}")
            with col2:
                getattr(st, rec_color.get(rec, "info"))(f"**{rec}**")
                if st.button("Deep dive", key=f"dd_ns_{item['filename']}"):
                    st.session_state["_nav_active"] = "AI Agent"
                    st.session_state["pending_query"] = (
                        f"Deep dive on {item['filename']}. Assessment: {rec}. "
                        f"Product: {ext.get('product','?')}, Broker: {ext.get('broker','?')}. "
                        "Provide full analysis with history, peers and guideline citations."
                    )
                    st.rerun()
                if st.button("Mark reviewed", key=f"rev_ns_{item['filename']}"):
                    mark_reviewed(item["filename"], rec, "Reviewed")
                    st.rerun()
    st.divider()


def _render_upload_form():
    from src.data.dashboard_data import load_all_submissions
    from src.data.pdf_parser import parse_pdf_from_upload
    from src.models.digital_twin import find_digital_twins, generate_twin_narrative, CONTROL_LABELS

    all_subs = load_all_submissions()
    products = sorted(all_subs["Product Name"].dropna().unique().tolist())
    brokers  = sorted(all_subs["National Broker Name"].dropna().unique().tolist())

    # PDF upload
    with st.expander("Upload PDF for auto-extraction", expanded=True):
        uploaded = st.file_uploader("Submission PDF", type=["pdf"])
        if uploaded and uploaded.name != st.session_state.get("pdf_filename", ""):
            with st.spinner(f"Extracting from {uploaded.name}..."):
                extracted = parse_pdf_from_upload(uploaded.read(), uploaded.name, products, brokers)
            if extracted.get("extraction_success"):
                st.session_state["pdf_extracted"] = extracted
                st.session_state["pdf_filename"] = uploaded.name
                for k, v in CONTROL_LABELS.items():
                    st.session_state[f"ns_ctrl_{k}"] = bool(extracted.get(k, False))
                st.session_state["ns_revenue"]   = float(extracted.get("revenue_millions") or 0)
                st.session_state["ns_employees"] = int(extracted.get("employee_count") or 0)
                st.session_state["ns_product"]   = extracted.get("product", "")
                st.session_state["ns_broker"]    = extracted.get("broker", "")
                st.rerun()
            else:
                st.error("Could not extract text from this PDF.")

        ext = st.session_state.get("pdf_extracted", {})
        if ext.get("extraction_success"):
            st.success(f"Extracted from **{st.session_state.get('pdf_filename','')}**")
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Revenue", f"${ext.get('revenue_millions',0):.1f}M")
            with c2: st.metric("Employees", str(ext.get("employee_count", "N/A")))
            with c3: st.metric("Premium", f"${ext.get('premium_usd',0):,.0f}" if ext.get("premium_usd") else "N/A")

    # Profile form
    st.markdown("#### Customer Profile")
    sic_df = all_subs[["SIC Code", "SIC Name"]].dropna().drop_duplicates()
    sic_df = sic_df[sic_df["SIC Code"].astype(str).str.strip().str.match(r"^\d+\.?\d*$")]
    sic_list = sorted(sic_df.apply(
        lambda r: f"{int(float(r['SIC Code']))} — {r['SIC Name']}", axis=1).tolist())

    _prod_idx = next((i+1 for i, p in enumerate(["—"]+products)
                      if st.session_state.get("ns_product","") and st.session_state["ns_product"] in p), 0)
    _brok_idx = next((i+1 for i, b in enumerate(["—"]+brokers)
                      if st.session_state.get("ns_broker","") and st.session_state["ns_broker"].upper()[:8] in b.upper()), 0)

    with st.form("ns_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sic_input     = st.selectbox("Industry (SIC)", ["— Not specified —"] + sic_list)
            product_input = st.selectbox("Product", ["— Not specified —"] + products, index=_prod_idx)
        with col2:
            broker_input  = st.selectbox("Broker", ["— Not specified —"] + brokers, index=_brok_idx)
            revenue_input = st.number_input("Revenue ($M)", min_value=0.0, step=1.0,
                                            value=float(st.session_state.get("ns_revenue", 0)))
        with col3:
            employees_input = st.number_input("Employees", min_value=0, step=10,
                                               value=int(st.session_state.get("ns_employees", 0)))
            n_twins = st.slider("Twins to find", 3, 10, 5)

        st.markdown("#### Security Controls")
        if ext.get("extraction_success"):
            st.caption("Pre-filled from PDF — adjust if needed")
        ctrl_cols = st.columns(4)
        controls_input = {}
        for i, (k, label) in enumerate(CONTROL_LABELS.items()):
            with ctrl_cols[i % 4]:
                controls_input[k] = st.checkbox(label, value=bool(
                    st.session_state.get(f"ns_ctrl_{k}", False)))

        submitted = st.form_submit_button("Find Digital Twins", use_container_width=True, type="primary")

    if submitted:
        sic_code = sic_input.split(" — ")[0] if sic_input != "— Not specified —" else None
        with st.spinner("Searching knowledge graph for digital twins..."):
            result = find_digital_twins(
                sic_code=sic_code,
                product=product_input if product_input != "— Not specified —" else None,
                broker=broker_input  if broker_input  != "— Not specified —" else None,
                revenue_m=revenue_input or None,
                employees=employees_input or None,
                controls=controls_input,
                n_twins=n_twins,
            )
        _show_twin_results(result, {"product": product_input, "broker": broker_input})


def _show_twin_results(result: dict, inputs: dict):
    from src.models.digital_twin import generate_twin_narrative
    import plotly.express as px

    if "error" in result:
        st.error(result["error"])
        return

    agg  = result["aggregate"]
    pred = result["predicted_recommendation"]
    conf = result["predicted_confidence"]
    col_rec = {"FAST_TRACK": "success", "STANDARD_UW": "warning", "FRESH_UW": "error"}
    getattr(st, col_rec.get(pred, "info"))(f"**{pred}** — Confidence: {conf:.0%}")

    twin_vote = result.get("twin_vote", pred)
    ctrl_adj  = result.get("ctrl_adjustment", 0)
    with st.expander("Why this recommendation?", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f"**Twin vote:** {twin_vote}")
        with c2: st.markdown(f"**Controls:** {'Upgrade' if ctrl_adj < 0 else 'Downgrade' if ctrl_adj > 0 else 'Neutral'}")
        with c3: st.markdown(f"**Final:** {pred}")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Twin Avg Approval", f"{agg['avg_approval_rate']}%")
        twins_df = __import__("pandas").DataFrame(result["twins"])
        if not twins_df.empty:
            twins_df["approval_rate"] = twins_df["approval_rate"].astype(str) + "%"
            st.dataframe(twins_df[["customer","similarity","approval_rate","risk_score","recommendation"]],
                         use_container_width=True, hide_index=True)
    with col2:
        gaps = result.get("gaps", [])
        for g in [g for g in gaps if g.get("severity") == "HIGH"]:
            st.error(f"**Missing: {g['control']}** — in {g['present_in_pct']:.0f}% of approved twins")
        for g in [g for g in gaps if g.get("severity") == "POSITIVE"][:3]:
            st.success(f"**{g['control']}** ✓ aligns with approved twins")

    st.markdown("### AI Narrative")
    st.markdown(generate_twin_narrative(result, inputs))

    # Similar Wins — twins that were actually bound
    twins_raw = result.get("twins", [])
    wins = [t for t in twins_raw if t.get("approval_rate", 0) > 50 or
            t.get("recommendation") == "FAST_TRACK"]
    if wins:
        st.divider()
        st.markdown("### Similar Wins — Customers We Bound")
        st.caption("These are structural peers that Zurich successfully bound. "
                   "What they had that this submission may be missing:")
        import pandas as pd
        wins_df = pd.DataFrame(wins)
        wins_df["approval_rate"] = wins_df["approval_rate"].astype(str) + "%"
        st.dataframe(
            wins_df[["customer","approval_rate","risk_score","recommendation"]].rename(columns={
                "customer":"Customer","approval_rate":"Approval Rate",
                "risk_score":"Score","recommendation":"Decision"
            }),
            use_container_width=True, hide_index=True
        )
        # What wins had that this submission doesn't (from gap analysis)
        high_gaps = [g["control"] for g in result.get("gaps",[]) if g.get("severity")=="HIGH"]
        if high_gaps:
            st.warning(
                f"**What these bound customers had that this submission is missing:** "
                + " · ".join(high_gaps)
            )

    # Portfolio Cascade Impact
    import streamlit.components.v1 as _components
    import re as _re
    product = inputs.get("product", "")
    broker  = inputs.get("broker", "")
    if product or broker:
        st.divider()
        with st.expander("Portfolio Impact — If approved, what's the cascade exposure?", expanded=False):
            st.caption("Shows which existing portfolio customers share the same broker/sector. "
                       "Hypothetical scenario — not a prediction.")
            if st.button("Generate cascade impact", key="cascade_ns"):
                from src.models.kg_visualisation import cascade_network_html
                broker_clean = _re.split(r"[,\s&]", broker)[0] if broker else ""
                with st.spinner("Building cascade network..."):
                    html = cascade_network_html(
                        event_type="cyber_campaign",
                        target_broker=broker_clean if broker_clean else None,
                        max_nodes=60,
                    )
                st.session_state["ns_cascade_html"] = html
            if "ns_cascade_html" in st.session_state:
                _components.html(st.session_state["ns_cascade_html"], height=480)
                st.caption("🔴 D1 Direct · 🟠 D2 Broker cascade · 🟡 D3 Sector — "
                           "HYPOTHETICAL SCENARIO ONLY, not a forecast (EU AI Act Art.15)")


def render():
    """Entry point called by app.py."""
    st.subheader("📄 New Submission Analyzer")
    st.caption("Upload a PDF for agent pre-analysis, or fill in the profile manually.")

    # Auto-scan watch folder — fast no-op when nothing new
    newly_found = _auto_scan()
    if newly_found:
        st.success(f"✅ {newly_found} new submission(s) detected and analysed automatically.")
        st.rerun()

    col_h, col_btn = st.columns([5, 1])
    with col_h:
        st.caption(f"Watch folder: `{os.getenv('UW_WATCH_FOLDER', 'data/raw/new_submissions')}`")
    with col_btn:
        if st.button("🔍 Rescan", help="Manually scan watch folder for new PDFs"):
            with st.spinner("Scanning..."):
                found = _auto_scan()
            if found:
                st.success(f"✅ {found} new PDF(s) analysed.")
                st.rerun()
            else:
                st.info("No new PDFs found in watch folder.")

    unreviewed = _pending_in_folder()
    if unreviewed:
        _render_pending(unreviewed)

    _render_upload_form()
