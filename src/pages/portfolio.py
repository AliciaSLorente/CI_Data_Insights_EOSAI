"""
Portfolio Analytics page — visual charts only.
Reuses cached loaders from dashboard_data.py. Zero new data logic.
For deeper analysis the UW navigates to AI Agent.
"""

import streamlit as st
import plotly.express as px


def render():
    from src.data.dashboard_data import (
        overview_metrics, submission_volume_by_year, status_distribution,
        top_products, broker_performance,
        kg_precomputed_available, kg_clusters_summary, kg_emerging_risks,
        recommendation_accuracy, bias_analysis,
    )
    from src.models.kg_real import (
        risk_clusters_summary as _live_clusters,
        detect_emerging_risks as _live_emerging,
    )

    st.subheader("📊 Portfolio Analytics")

    # ── Key metrics ───────────────────────────────────────────────────────────
    m = overview_metrics()
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Submissions", f"{m['total_submissions']:,}")
    with col2: st.metric("Repeat Customers",  f"{m['total_repeat_customers']:,}",
                         delta=f"{m['repeat_pct']}% of book")
    with col3: st.metric("Approval Rate",     f"{m['approval_rate']}%")
    with col4: st.metric("Top Broker",        m["top_broker"][:22])

    st.divider()

    # ── Submission trends ─────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        vol = submission_volume_by_year()
        vol = vol[vol["Year"].between(2019, 2025)]
        fig = px.bar(vol, x="Year", y="Submissions", text="Submissions",
                     title="Submission Volume 2019–2025",
                     color_discrete_sequence=["#4C9BE8"])
        fig.update_xaxes(type="category")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        status = status_distribution()
        fig = px.pie(status, names="Status", values="Count",
                     title="Status Distribution", hole=0.35)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # ── Products & brokers ────────────────────────────────────────────────────
    col3, col4 = st.columns(2)
    with col3:
        prods = top_products(8)
        fig = px.bar(prods, x="Count", y="Product", orientation="h",
                     title="Top 8 Products", color="Count",
                     color_continuous_scale="Blues")
        fig.update_layout(showlegend=False, height=400,
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        brokers = broker_performance(12)
        fig = px.scatter(brokers, x="submissions", y="approval_rate",
                         size="customers", hover_name="National Broker Name",
                         title="Broker: Volume vs Approval Rate",
                         color="approval_rate", color_continuous_scale="RdYlGn",
                         labels={"submissions": "Submissions",
                                 "approval_rate": "Approval Rate (%)"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Risk clusters (KG) ────────────────────────────────────────────────────
    st.markdown("#### Risk Cluster Overview")
    _precomputed = kg_precomputed_available()
    clusters_df = kg_clusters_summary() if _precomputed else _live_clusters()

    if not clusters_df.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(clusters_df, x="cluster_label", y="customers",
                         color="cluster_label",
                         color_discrete_map={"Low Risk": "#22C55E",
                                             "Moderate Risk": "#F97316",
                                             "High Risk": "#EF4444"},
                         title="Customers by Risk Cluster",
                         labels={"cluster_label": "Cluster", "customers": "Customers"})
            fig.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(clusters_df, x="cluster_label", y="avg_approval_rate",
                         color="cluster_label",
                         color_discrete_map={"Low Risk": "#22C55E",
                                             "Moderate Risk": "#F97316",
                                             "High Risk": "#EF4444"},
                         title="Avg Approval Rate by Cluster (%)",
                         labels={"cluster_label": "Cluster",
                                 "avg_approval_rate": "Approval Rate (%)"})
            fig.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig, use_container_width=True)

    # ── Submission deltas overview ────────────────────────────────────────────
    st.divider()
    st.markdown("#### Submission Deltas — What Changed?")
    st.caption("Comparison of first vs latest submission per repeat customer.")
    from src.data.dashboard_data import load_all_deltas
    deltas = load_all_deltas()
    if not deltas.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            improved = int(deltas["status_improved"].sum()) if "status_improved" in deltas.columns else 0
            st.metric("Status Improved", improved, help="Status moved to better outcome since first submission")
        with col2:
            degraded = int(deltas["status_degraded"].sum()) if "status_degraded" in deltas.columns else 0
            st.metric("Status Degraded", degraded, help="Status moved to worse outcome since first submission")
        with col3:
            broker_changed = int(deltas["broker_changed"].sum()) if "broker_changed" in deltas.columns else 0
            st.metric("Broker Changed", broker_changed, help="Customer changed broker between submissions")

        # Distribution of status trajectories
        if "status_improved" in deltas.columns and "status_degraded" in deltas.columns:
            trajectory = deltas.apply(
                lambda r: "Improved" if r["status_improved"]
                else ("Degraded" if r["status_degraded"] else "Stable"), axis=1
            ).value_counts().reset_index()
            trajectory.columns = ["Trajectory","Count"]
            col_t1, col_t2 = st.columns([1, 2])
            with col_t1:
                fig = px.pie(trajectory, names="Trajectory", values="Count",
                             title="Status trajectories",
                             color="Trajectory",
                             color_discrete_map={"Improved":"#22C55E",
                                                 "Stable":"#6B7280",
                                                 "Degraded":"#EF4444"},
                             hole=0.35)
                fig.update_layout(height=360)
                st.plotly_chart(fig, use_container_width=True)
            with col_t2:
                fig = px.bar(trajectory, x="Trajectory", y="Count",
                             color="Trajectory",
                             color_discrete_map={"Improved":"#22C55E",
                                                 "Stable":"#6B7280",
                                                 "Degraded":"#EF4444"},
                             title="Trajectory count breakdown",
                             text="Count")
                fig.update_traces(textposition="outside")
                fig.update_layout(showlegend=False, height=360)
                st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Model accuracy validation (Art. 15 EU AI Act) ─────────────────────────
    st.markdown("#### AI Recommendation Accuracy — Bind Rate by Tier")
    st.caption("Validates that FAST_TRACK customers bind more than FRESH_UW — evidence the model works.")
    acc = recommendation_accuracy()
    if not acc.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                acc, x="recommendation", y="bind_rate",
                color="recommendation",
                color_discrete_map={"FAST_TRACK": "#22C55E",
                                    "STANDARD_UW": "#F97316",
                                    "FRESH_UW": "#EF4444"},
                text="bind_rate",
                title="Bind Rate (%) by AI Recommendation",
                labels={"recommendation": "Recommendation", "bind_rate": "Bind Rate (%)"},
            )
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.bar(
                acc, x="recommendation", y="avg_score",
                color="recommendation",
                color_discrete_map={"FAST_TRACK": "#22C55E",
                                    "STANDARD_UW": "#F97316",
                                    "FRESH_UW": "#EF4444"},
                text="avg_score",
                title="Average Risk Score by Recommendation Tier",
                labels={"recommendation": "Recommendation", "avg_score": "Avg Score"},
            )
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_layout(showlegend=False, height=380)
            st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Based on {int(acc['customers'].sum()):,} scored customers. "
            "Higher bind rate for FAST_TRACK vs FRESH_UW confirms the model separates risk correctly."
        )

    st.divider()

    # ── Bias Analysis — EU AI Act Art.10 ─────────────────────────────────────
    st.markdown("#### AI Score Bias Analysis")
    st.caption(
        "Verifies the scoring model treats different brokers and industries equitably. "
        "Required under EU AI Act Art.10 (data governance). "
        "Significant score differences between groups may indicate data bias."
    )
    bias = bias_analysis()
    if bias and not bias["by_broker"].empty:
        col_b, col_s = st.columns(2)
        with col_b:
            fig = px.bar(bias["by_broker"], x="avg_score", y="broker",
                         orientation="h", color="avg_score",
                         color_continuous_scale="RdYlGn_r",
                         title=f"Avg Risk Score by Broker (portfolio mean: {bias['mean']})",
                         labels={"avg_score": "Avg Score", "broker": ""},
                         text="avg_score")
            fig.update_traces(textposition="outside")
            fig.update_layout(height=420, showlegend=False,
                              yaxis=dict(autorange="reversed"),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        with col_s:
            if not bias["by_sic"].empty:
                fig = px.bar(bias["by_sic"], x="avg_score", y="sic",
                             orientation="h", color="avg_score",
                             color_continuous_scale="RdYlGn_r",
                             title="Avg Risk Score by Industry (SIC)",
                             labels={"avg_score": "Avg Score", "sic": ""},
                             text="avg_score")
                fig.update_traces(textposition="outside")
                fig.update_layout(height=420, showlegend=False,
                                  yaxis=dict(autorange="reversed"),
                                  coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Portfolio: {bias['total']:,} customers · Mean score {bias['mean']} · "
            f"Std dev {bias['std']} · "
            "Flag groups with score > 1 std dev from mean for manual review."
        )

    st.divider()

    # ── Emerging risks ────────────────────────────────────────────────────────
    signals = (kg_emerging_risks().to_dict(orient="records")
               if _precomputed else _live_emerging())
    if signals:
        st.markdown("#### Emerging Risk Signals")
        for s in signals[:5]:
            entity = s.get("entity", s.get("National Broker Name", ""))
            detail = s.get("detail", "")
            sev    = s.get("severity", "MEDIUM")
            msg    = f"**{entity}** — {detail}"
            st.error(msg) if sev == "HIGH" else st.warning(msg)

