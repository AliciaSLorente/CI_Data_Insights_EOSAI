"""
Portfolio Risk Map — interactive network visualisations.
Three views:
  1. Customer Network  — individual customer + peers in the KG
  2. Cascade Simulation — hazard event propagating through portfolio
  3. Risk Clusters     — full portfolio segmented by KMeans cluster with broker bridges
"""

import streamlit as st
import streamlit.components.v1 as components


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_metrics():
    import pandas as pd
    from pathlib import Path
    p = Path("data/parsed/graph_metrics.csv")
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data(show_spinner=False)
def _cascade_portfolio_recommendation() -> dict:
    """Portfolio-specific stress test recommendations computed from real data."""
    from src.data.dashboard_data import load_all_submissions, broker_performance
    subs = load_all_submissions()
    bp   = broker_performance(3)
    if subs.empty:
        return {}
    top_prod     = subs["Product Name"].value_counts()
    top_product  = top_prod.index[0][:45] if len(top_prod) > 0 else "Security & Privacy"
    top_pct      = int(round(top_prod.iloc[0] / len(subs) * 100, 0)) if len(top_prod) > 0 else 92
    top_broker   = bp["National Broker Name"].iloc[0] if not bp.empty else "MARSH"
    top_broker_n = int(bp["submissions"].iloc[0]) if not bp.empty else 7321
    top_broker_p = round(top_broker_n / len(subs) * 100, 1) if len(subs) > 0 else 16
    return {"top_product": top_product, "top_pct": top_pct,
            "top_broker": top_broker, "top_broker_n": top_broker_n, "top_broker_p": top_broker_p}


def _cascade_metrics(event_type: str, target_broker: str = None,
                     custom_products: list = None) -> dict:
    """Compute cascade impact statistics — reuses load_all_submissions() cache."""
    from src.data.dashboard_data import load_all_submissions
    EVENT_PRODUCTS = {
        "cyber_campaign":      ["Security", "ZCIP", "Cyber"],
        "financial_contagion": ["ProPlus", "Crime", "Professional", "Liability"],
        "supply_chain":        ["Security", "ZCIP"],
        "broker_failure":      [],
    }
    products = custom_products if custom_products else EVENT_PRODUCTS.get(event_type, ["Security"])
    subs = load_all_submissions()
    if subs.empty:
        return {}

    broker_mask  = subs["National Broker Name"].astype(str).str.contains(
        target_broker, case=False, na=False) if target_broker else None
    product_mask = subs["Product Name"].apply(
        lambda p: any(kw.lower() in str(p).lower() for kw in products)) if products else None

    if event_type == "broker_failure":
        d1 = subs[broker_mask] if broker_mask is not None else subs.head(0)
    elif target_broker and products:
        d1 = subs[broker_mask & product_mask]
    elif broker_mask is not None:
        d1 = subs[broker_mask]
    elif product_mask is not None:
        d1 = subs[product_mask]
    else:
        d1 = subs.head(0)

    d1_customers = set(d1["Submission Account Name"].unique())
    d1_brokers   = set(d1["National Broker Name"].dropna().unique())
    d2 = subs[subs["National Broker Name"].isin(d1_brokers) &
              ~subs["Submission Account Name"].isin(d1_customers)]
    d2_customers = set(d2["Submission Account Name"].unique())
    premium_col  = "Submission Product Bound Premium Amount"
    d1_prem = d1[premium_col].fillna(0).sum() if premium_col in d1.columns else 0
    d2_prem = d2[premium_col].fillna(0).sum() if premium_col in d2.columns else 0
    # Top 5 brokers by D1 customer count — actionable list for UW
    broker_d1 = (d1.groupby("National Broker Name")["Submission Account Name"]
                 .nunique().nlargest(5).reset_index()
                 .rename(columns={"Submission Account Name": "d1_customers",
                                  "National Broker Name": "broker"}))
    return {
        "d1_count": len(d1_customers), "d2_count": len(d2_customers),
        "d1_brokers": len(d1_brokers),
        "total_affected": len(d1_customers) + len(d2_customers),
        "premium_m": round((d1_prem + d2_prem) / 1_000_000, 1),
        "top_brokers": broker_d1.to_dict(orient="records"),
    }


# ── View 1: Customer Network ──────────────────────────────────────────────────

def _customer_network(customer_name: str, show_peers: bool):
    from src.models.kg_graph_analytics import customer_neighborhood, generate_graph_xai

    nb = customer_neighborhood(customer_name, max_depth=2 if show_peers else 1)
    if "error" in nb:
        st.warning(nb["error"])
        return

    gm     = _load_metrics()
    gm_row = (gm[gm["customer"] == customer_name].iloc[0].to_dict()
              if not gm.empty and customer_name in gm["customer"].values else {})

    # Metrics row — UW-relevant fields, not technical graph counts
    nodes  = nb.get("nodes", [])
    brokers_in_nb = [n["label"] for n in nodes if n.get("type") == "broker"]
    sectors_in_nb = [n["label"] for n in nodes if n.get("type") == "sector"]
    peers_count   = sum(1 for n in nodes if n.get("type") == "customer"
                        and n.get("id") != nb.get("center"))

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Broker", brokers_in_nb[0][:20] if brokers_in_nb else "N/A")
    with c2: st.metric("Sector", sectors_in_nb[0][:20] if sectors_in_nb else "N/A")
    with c3: st.metric("Peers in network", peers_count)
    with c4: st.metric("Risk Score", f"{gm_row.get('risk_score','?')}/100")
    with c5:
        rec = gm_row.get("recommendation", "?")
        color = {"FAST_TRACK": "success", "STANDARD_UW": "warning", "FRESH_UW": "error"}.get(rec, "info")
        getattr(st, color)(f"**{rec}**")

    # Full-width graph
    try:
        from pyvis.network import Network
        net = Network(height="640px", width="100%",
                      bgcolor="#0F1117", font_color="#F9FAFB")
        net.set_options("""
        {
          "nodes": {
            "borderWidth": 2,
            "shadow": {"enabled": true, "size": 12, "color": "rgba(0,0,0,0.6)"},
            "font": {"size": 12, "bold": true}
          },
          "edges": {
            "color": {"opacity": 0.5}, "width": 1.5,
            "smooth": {"type": "dynamic"}, "selectionWidth": 3
          },
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -55, "centralGravity": 0.01,
              "springLength": 120, "springConstant": 0.08, "damping": 0.4
            },
            "solver": "forceAtlas2Based",
            "stabilization": {"enabled": true, "iterations": 100, "fit": true}
          },
          "interaction": {"hover": true, "tooltipDelay": 80, "hideEdgesOnDrag": true}
        }
        """)
        for node in nb["nodes"]:
            net.add_node(node["id"], label=node["label"], color=node["color"],
                         size=node["size"], title=node["tooltip"])
        for edge in nb["edges"]:
            net.add_edge(edge["from"], edge["to"])
        components.html(net.generate_html(), height=650)
    except Exception as e:
        st.warning(f"Graph render error: {e}")

    st.caption("🔵 Customer  🟠 Broker  🟢 Sector/Fast-Track  🟣 Product  🔴 High Risk")

    # ── Highest risk peer callout ─────────────────────────────────────────────
    peer_ids = [n["id"].replace("cust::", "") for n in nodes
                if n.get("type") == "customer" and n.get("id") != nb.get("center")]
    if peer_ids and not gm.empty:
        peer_data = gm[gm["customer"].isin(peer_ids)]
        if not peer_data.empty:
            worst = peer_data.nlargest(1, "risk_score").iloc[0]
            _c = {"FAST_TRACK":"success","STANDARD_UW":"warning","FRESH_UW":"error"}.get(
                worst.get("recommendation",""), "info")
            getattr(st, _c)(
                f"**Highest risk peer:** {worst['customer']} — "
                f"Score {worst['risk_score']:.0f}/100 · {worst.get('recommendation','')} · "
                f"Cluster: {worst.get('cluster','?')}"
            )

    # XAI below in expander
    with st.expander("🤖 AI Graph Explanation", expanded=False):
        xai_key = f"graph_xai_{customer_name}"
        if st.button("Generate Explanation", key=f"xai_g_{customer_name}",
                     use_container_width=True, type="primary"):
            with st.spinner("Generating..."):
                text = generate_graph_xai(
                    customer_name=customer_name,
                    neighborhood_data=nb,
                    cluster=str(gm_row.get("cluster", "")),
                    risk_score=float(gm_row.get("risk_score", 50)),
                    recommendation=str(gm_row.get("recommendation", "STANDARD_UW")),
                )
                st.session_state[xai_key] = text
        if xai_key in st.session_state:
            st.markdown(st.session_state[xai_key])
        else:
            nodes   = nb.get("nodes", [])
            peers   = [n for n in nodes if n.get("type") == "customer"
                       and n.get("id") != nb.get("center")]
            brokers = [n["label"] for n in nodes if n.get("type") == "broker"]
            st.info(
                f"**{customer_name}** · Broker: {brokers[0] if brokers else 'N/A'} · "
                f"Peers in network: {len(peers)} · "
                f"PageRank: {gm_row.get('pagerank', 0):.6f}"
            )


# ── View 2: Cascade Simulation ────────────────────────────────────────────────

@st.cache_data(show_spinner="Building cascade networks...")
def _build_cascade(event_type: str, broker: str, max_nodes: int, custom_keywords: str = ""):
    """Cache cascade HTML by params (including custom keywords). Cleared on server restart."""
    from src.models.kg_visualisation import cascade_network_html, cascade_ripple_html
    b = broker or None
    cp = [kw.strip() for kw in custom_keywords.split(",") if kw.strip()] if custom_keywords else None
    return (
        cascade_network_html(event_type=event_type, target_broker=b,
                             max_nodes=max_nodes, height="750px", custom_products=cp),
        cascade_ripple_html(event_type=event_type, target_broker=b,
                            max_nodes=max_nodes, height="750px", custom_products=cp),
        _cascade_metrics(event_type, b, cp),
    )


def _run_cascade(event_type: str, target_broker: str, max_nodes: int, custom_keywords: str = ""):
    """Store only params — HTML lives in @st.cache_data, not session_state."""
    st.session_state["cascade_params"] = {
        "event_type":      event_type,
        "broker":          target_broker or "",
        "max_nodes":       max_nodes,
        "custom_keywords": custom_keywords,
    }


def _show_cascade():
    params = st.session_state.get("cascade_params")
    if not params:
        return

    html_network, html_ripple, metrics = _build_cascade(
        params["event_type"], params["broker"], params["max_nodes"],
        params.get("custom_keywords", "")
    )
    event      = params["event_type"]
    custom_kw  = params.get("custom_keywords", "")
    event_label = f"Custom: {custom_kw}" if event == "custom" and custom_kw else event.replace("_", " ").title()

    # Visualization style toggle
    viz_style = st.radio(
        "Visualization style:",
        ["🔵 Network Cascade — operational view",
         "🔴 Ripple Effect — structural view (degree-based)"],
        horizontal=True, key="cascade_viz_style"
    )
    html = html_ripple if "Ripple" in viz_style else html_network

    if "Ripple" in viz_style:
        st.info(
            "**Ripple Effect view** — academic-style cascade visualization.  \n"
            "**Circle size = network degree** (connections) — larger = more connected.  \n"
            "Colour gradient: dark maroon (D1) → orange (D2) → yellow (D3) → hollow (unaffected).  \n"
            "Origin broker: black circle at centre. Small broker = small circle, but can cascade far.  \n"
        )

    # Business context for D1/D2/D3 — always visible, no expander
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.error(
            "**🔴 D1 — Direct Exposure**  \n"
            "Active policy matches the event. Real claims exposure now.  \n"
            "**Action:** Review limits immediately, flag to senior UW."
        )
    with col_d2:
        st.warning(
            "**🟠 D2 — Broker Cascade**  \n"
            "Same broker as D1. Broker operational risk affects full book.  \n"
            "**Action:** Contact broker, assess concentration limits."
        )
    with col_d3:
        st.info(
            "**🟡 D3 — Sector Cascade**  \n"
            "Same sector as D2. Market-wide risk, no direct policy link.  \n"
            "**Action:** Flag for renewal cycle. Monitor sector news."
        )

    # Compliance disclaimer
    st.caption(
        "⚠️ Structural proximity analysis only — not a probability-weighted actuarial loss estimate. "
        "Gross Connected Premium = total bound premium of structurally connected customers, "
        "not expected claims."
    )

    # Impact metrics panel
    st.markdown(f"#### Cascade Impact — *{event_label}* scenario")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("D1 Direct", f"{metrics.get('d1_count', 0):,}",
                  help="Customers directly exposed — active policy matches event type or broker")
    with c2:
        st.metric("D2 Broker Cascade", f"{metrics.get('d2_count', 0):,}",
                  help="Customers sharing broker with D1 — indirect exposure via broker relationship")
    with c3:
        st.metric("Total Affected", f"{metrics.get('total_affected', 0):,}",
                  help="D1 + D2 combined — total portfolio footprint of this scenario")
    with c4:
        prem = metrics.get("premium_m", 0)
        st.metric("Gross Connected Premium", f"£{prem:.1f}M" if prem else "N/A",
                  help="Total bound premium of structurally connected customers — not probability-weighted loss")

    components.html(html, height=760)
    if "Ripple" in viz_style:
        st.caption(
            "● Origin (black) · 🟤 D1 dark maroon · 🟠 D2 orange · 🟡 D3 yellow · ○ Unaffected  |  "
            "Circle SIZE = degree (connections)  |  "
            "⚠️ Hypothetical scenario — NOT a prediction (EU AI Act Art.15)"
        )
    else:
        st.caption(
            "🔴 D1 Direct · 🟠 D2 Broker cascade · 🟡 D3 Sector cascade  |  "
            "Border: 🟢 Low Risk · 🟠 Moderate · 🔴 High Risk  |  "
            "⚠️ Hypothetical scenario — NOT a prediction (EU AI Act Art.15)"
        )

    # ── Top 5 most exposed brokers ────────────────────────────────────────────
    top_brokers = metrics.get("top_brokers", [])
    if top_brokers:
        st.markdown("##### Top brokers to contact — highest D1 customer exposure")
        import pandas as _pd_g
        tb = _pd_g.DataFrame(top_brokers)
        tb.columns = ["Broker", "D1 Customers Exposed"]
        tb.index = range(1, len(tb) + 1)
        st.dataframe(tb, use_container_width=True)
        st.caption("Contact these brokers first to review policy limits and exclusions for exposed customers.")

    # ── Agent explanation ─────────────────────────────────────────────────────
    st.divider()
    with st.expander("🤖 Ask agent: what do these results mean?", expanded=False):
        xai_key = f"cascade_xai_{event}_{params.get('broker','')}"
        if st.button("Generate explanation", key="cascade_agent_btn",
                     type="primary", use_container_width=True):
            from src.pages.agent import _get_agent
            broker_note = f"Target broker: {params['broker']}. " if params.get("broker") else ""
            query = (
                f"The cascade simulation for a {event.replace('_',' ')} scenario shows: "
                f"D1 Direct = {metrics.get('d1_count',0):,} customers directly exposed, "
                f"D2 Broker Cascade = {metrics.get('d2_count',0):,} customers via broker, "
                f"Total affected = {metrics.get('total_affected',0):,}, "
                f"Premium at risk = £{metrics.get('premium_m',0):.1f}M. "
                f"{broker_note}"
                "What does this mean for the portfolio? "
                "Which customers should the UW prioritise reviewing? "
                "What specific actions should be taken?"
            )
            placeholder = st.empty()
            full_response = ""
            try:
                agent = _get_agent()
                for ev in agent.chat(query):
                    if ev["type"] == "text":
                        full_response += ev["content"]
                        placeholder.markdown(full_response + "▌")
                placeholder.empty()
            except Exception as e:
                placeholder.error(f"Agent error: {e}")
            st.session_state[xai_key] = full_response
            st.rerun()
        if st.session_state.get(xai_key):
            st.markdown(st.session_state[xai_key])
        else:
            st.caption("Click above for an AI interpretation of these cascade results "
                       "and specific UW actions to take.")


# ── View 3: Risk Clusters ─────────────────────────────────────────────────────

def _risk_clusters():
    from src.models.kg_visualisation import cluster_life_html
    from src.data.dashboard_data import kg_clusters_summary

    # Summary metrics
    summary = kg_clusters_summary()
    if not summary.empty:
        cols = st.columns(len(summary))
        for i, (_, row) in enumerate(summary.iterrows()):
            color = {"Low Risk": "success", "Moderate Risk": "warning",
                     "High Risk": "error"}.get(row["cluster_label"], "info")
            with cols[i]:
                getattr(st, color)(
                    f"**{row['cluster_label']}**  \n"
                    f"{int(row['customers']):,} customers  \n"
                    f"Avg approval: {row['avg_approval_rate']:.1f}%"
                )

    cache_key = "cluster_life_html"
    if cache_key not in st.session_state:
        with st.spinner("Rendering risk cluster network..."):
            st.session_state[cache_key] = cluster_life_html(
                highlight_bridges=True,
                max_nodes_per_cluster=25,
                height="680px",
            )

    components.html(st.session_state[cache_key], height=670)
    st.caption(
        "🟢 Low Risk · 🟠 Moderate Risk · 🔴 High Risk · 🔷 Broker hub  |  "
        "🟣 Bridge node — High Risk customer connected to Low Risk via shared broker  |  "
        "Shape: ● Fast-Track  ■ Standard UW  ▲ Fresh UW"
    )

    # ── Bridge nodes identity table — compute once, reuse in AI explanation ──
    from src.models.kg_graph_analytics import find_cluster_bridges
    bridge_df = find_cluster_bridges(top_n=15)
    bridge_count = len(bridge_df) if not bridge_df.empty else 0

    if not bridge_df.empty:
        st.divider()
        st.markdown("##### Bridge Nodes — Hidden Correlation Risk")
        st.caption(
            "These High Risk customers share a broker with Low Risk customers, "
            "creating hidden contagion paths. Monitor these as a priority."
        )
        display_cols = [c for c in ["high_risk_customer", "broker", "low_risk_customer",
                                     "risk_score"] if c in bridge_df.columns]
        st.dataframe(
            bridge_df[display_cols].head(10).rename(columns={
                "high_risk_customer": "High Risk Customer",
                "broker": "Shared Broker",
                "low_risk_customer": "Connected Low Risk Customer",
                "risk_score": "Risk Score",
            }),
            use_container_width=True, hide_index=True
        )

    # AI Explanation — reuses bridge_df already computed above
    st.divider()
    with st.expander("🤖 AI Cluster Explanation", expanded=False):
        xai_key = "cluster_portfolio_xai"
        if st.button("Generate AI Explanation", key="cluster_xai_btn",
                     use_container_width=True, type="primary"):
            with st.spinner("Analysing portfolio risk segmentation..."):
                from src.models.kg_graph_analytics import generate_cluster_xai
                text = generate_cluster_xai(
                    cluster_summary=summary.to_dict(orient="records") if not summary.empty else [],
                    bridge_count=bridge_count,
                )
                st.session_state[xai_key] = text
        if xai_key in st.session_state:
            st.markdown(st.session_state[xai_key])
        else:
            st.caption("Click above to get an AI explanation of what these clusters "
                       "mean for your portfolio — which to prioritise, what the "
                       "bridge nodes represent, and what action to take.")


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.subheader("🕸️ Portfolio Risk Map")
    st.caption("Real NetworkX Knowledge Graph — 10,232 nodes · 36,312 edges · KMeans k=3")

    view = st.radio(
        "View:", ["Customer Network", "Cascade Simulation", "Risk Clusters"],
        horizontal=True, key="graph_view"
    )

    if view == "Customer Network":
        from src.data.dashboard_data import repeat_customer_list
        customers = repeat_customer_list(200)
        col_sel, col_opt = st.columns([4, 1])
        with col_sel:
            customer = st.selectbox("Customer:", customers, key="graph_customer")
        with col_opt:
            show_peers = st.checkbox("Show peers", value=True, key="graph_peers")
        if customer:
            _customer_network(customer, show_peers)

    elif view == "Cascade Simulation":
        st.caption(
            "Simulates a hazard event propagating through the portfolio graph. "
            "Brokers act as amplification hubs — one affected customer can cascade to hundreds."
        )

        # Portfolio-specific recommendation from real data
        rec = _cascade_portfolio_recommendation()
        if rec:
            st.info(
                f"**Recommended stress tests for this portfolio:**  \n"
                f"**1. Ransomware / Cyber** — {rec['top_pct']}% of portfolio is "
                f"*{rec['top_product']}*. Primary systemic risk.  \n"
                f"**2. Broker concentration** — **{rec['top_broker']}** handles "
                f"{rec['top_broker_n']:,} submissions ({rec['top_broker_p']}% of book). "
                f"Use Custom Scenario → broker *{rec['top_broker']}*."
            )

        # Simplified scenario: 1 predefined + 1 custom
        mode = st.radio(
            "Scenario:", ["🔴 Ransomware / Cyber", "✏️ Custom Scenario"],
            horizontal=True, key="cascade_mode"
        )

        event_type      = "cyber_campaign"
        target_broker   = ""
        custom_keywords = ""

        if mode == "✏️ Custom Scenario":
            from src.data.dashboard_data import broker_performance as _bp
            _brokers = ["— All brokers —"] + _bp(60)["National Broker Name"].tolist()
            col_kw, col_br = st.columns(2)
            with col_kw:
                custom_keywords = st.text_input(
                    "Product keywords (comma-separated):",
                    placeholder="e.g. ProPlus, Liability, Crime",
                    key="cascade_custom_kw",
                    help="Matches against Product Name in the portfolio"
                )
            with col_br:
                _broker_sel = st.selectbox(
                    "Target broker (optional):", _brokers, key="cascade_custom_broker",
                    help="Optional: restrict D1 to this broker's customers"
                )
                target_broker = "" if _broker_sel == "— All brokers —" else _broker_sel
            event_type = "custom"
            if not custom_keywords.strip() and not target_broker:
                st.warning("⚠️ Enter at least one product keyword OR select a broker to run the cascade.")

        run_ok = not (event_type == "custom" and not custom_keywords.strip() and not target_broker)
        if st.button("▶ Run Cascade Simulation", use_container_width=True,
                     type="primary", disabled=not run_ok):
            _run_cascade(event_type, target_broker, 100, custom_keywords)
        elif "cascade_html_network" not in st.session_state:
            _run_cascade("cyber_campaign", None, 100, "")

        _show_cascade()

    else:  # Risk Clusters
        _risk_clusters()
