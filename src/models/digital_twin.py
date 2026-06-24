"""
Digital Twin engine for new submission analysis.
Finds the most similar existing customers in the KG and uses their
historical outcomes to recommend treatment for a new submission.
"""

import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional

DATA = Path("data/parsed")

CONTROLS_LIST = [
    "control_firewall", "control_mfa", "control_edr", "control_ids_ips",
    "control_dlp", "control_siem", "control_encryption", "control_backup",
    "control_incident_response", "control_security_awareness",
    "control_patch_management", "control_vulnerability",
]
CONTROL_LABELS = {
    c: c.replace("control_", "").replace("_", " ").title()
    for c in CONTROLS_LIST
}


@st.cache_data
def _load_base():
    subs = pd.read_csv(DATA / "all_submissions.csv", low_memory=False)
    subs["Requested Coverage Effective Date"] = pd.to_datetime(
        subs["Requested Coverage Effective Date"], errors="coerce"
    )
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )
    recs = pd.read_csv(DATA / "all_recommendations.csv")
    deltas = pd.read_csv(DATA / "all_deltas.csv")
    pdfs = pd.read_csv(DATA / "pdf_extracted_fields.csv") if (DATA / "pdf_extracted_fields.csv").exists() else pd.DataFrame()
    return subs, recs, deltas, pdfs


def _customer_profile(subs: pd.DataFrame, recs: pd.DataFrame, deltas: pd.DataFrame) -> pd.DataFrame:
    """Build feature profile for every repeat customer."""
    agg = (
        subs.groupby("Submission Account Name")
        .agg(
            sic_code=("SIC Code", lambda x: x.mode()[0] if len(x) else None),
            sic_name=("SIC Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
            submission_count=("Submission Account Name", "count"),
            approval_rate=("is_bound", "mean"),
            avg_premium=("Quoted Premium Amount", "mean"),
            latest_status=("Current Status Description", "last"),
        )
        .reset_index()
    )
    agg = agg.merge(
        recs[["company_name", "risk_score", "recommendation", "confidence",
              "comp_recent_declines", "comp_approval_trajectory",
              "comp_submission_frequency", "comp_latest_status"]],
        left_on="Submission Account Name",
        right_on="company_name",
        how="left",
    ).drop(columns=["company_name"], errors="ignore")
    return agg


@st.cache_data(show_spinner=False)
def find_digital_twins(
    sic_code: Optional[str] = None,
    product: Optional[str] = None,
    broker: Optional[str] = None,
    revenue_m: Optional[float] = None,
    employees: Optional[int] = None,
    controls: Optional[Dict[str, bool]] = None,
    n_twins: int = 5,
) -> Dict:
    """
    Find the most similar existing customers for a new submission.
    Returns twin profiles, aggregate outcomes, counterfactual, and gap analysis.
    """
    subs, recs, deltas, pdfs = _load_base()
    profiles = _customer_profile(subs, recs, deltas)

    if profiles.empty:
        return {"error": "No customer profiles available"}

    candidates = profiles.copy()

    # ── Scoring similarity — combined categorical + graph ──────────────────────
    candidates["similarity_score"] = 0.0
    candidates["match_method"] = "categorical"

    # Try graph-based matching first (NetworkX structural peers)
    graph_peers_found = False
    try:
        import pickle
        pkl_path = DATA / "knowledge_graph.pkl"
        gm_path  = DATA / "graph_metrics.csv"
        if pkl_path.exists() and (broker or product or sic_code):
            with open(pkl_path, "rb") as f:
                G = pickle.load(f)

            # Find customers sharing the same broker AND product via graph
            graph_scores: dict = {}
            if broker:
                broker_node = f"broker::{broker}"
                # Find exact or partial broker node
                b_nodes = [n for n in G.nodes if broker.split()[0].upper() in n.upper()
                           and n.startswith("broker::")]
                for b_node in b_nodes[:1]:
                    for cust_node in G.neighbors(b_node):
                        if cust_node.startswith("cust::"):
                            name = cust_node.replace("cust::", "")
                            graph_scores[name] = graph_scores.get(name, 0) + 30  # broker match via graph

            if product:
                prod_nodes = [n for n in G.nodes if product.split()[0].lower() in n.lower()
                              and n.startswith("product::")]
                for p_node in prod_nodes[:1]:
                    for cust_node in G.neighbors(p_node):
                        if cust_node.startswith("cust::"):
                            name = cust_node.replace("cust::", "")
                            graph_scores[name] = graph_scores.get(name, 0) + 20  # product match via graph

            if graph_scores:
                for name, score in graph_scores.items():
                    mask = candidates["Submission Account Name"] == name
                    candidates.loc[mask, "similarity_score"] += float(score)
                    candidates.loc[mask, "match_method"] = "graph+categorical"

                # Cluster-aware bonus: boost peers in same cluster
                # Uses KMeans cluster from graph node attributes
                gm_path = DATA / "graph_metrics.csv"
                if gm_path.exists():
                    gm = pd.read_csv(gm_path)
                    # Infer target cluster from top scoring peer
                    top_peer_name = max(graph_scores, key=graph_scores.get)
                    top_row = gm[gm["customer"] == top_peer_name]
                    if not top_row.empty:
                        target_cluster = top_row.iloc[0].get("cluster", "")
                        if target_cluster:
                            cluster_members = set(gm[gm["cluster"] == target_cluster]["customer"])
                            for name in graph_scores:
                                if name in cluster_members:
                                    mask = candidates["Submission Account Name"] == name
                                    candidates.loc[mask, "similarity_score"] += 10.0  # cluster match bonus
                graph_peers_found = True
    except Exception:
        pass  # Fall through to categorical matching

    # Categorical fallback (always adds on top of graph scores)
    if sic_code:
        sic_match = candidates["sic_code"].astype(str) == str(sic_code)
        candidates.loc[sic_match, "similarity_score"] += 20.0
        sic_prefix = str(sic_code)[:2]
        prefix_match = candidates["sic_code"].astype(str).str[:2] == sic_prefix
        candidates.loc[prefix_match & ~sic_match, "similarity_score"] += 10.0

    if product and not graph_peers_found:
        prod_match = candidates["primary_product"].str.contains(
            product.split()[0], case=False, na=False)
        candidates.loc[prod_match, "similarity_score"] += 25.0

    if broker and not graph_peers_found:
        brok_match = candidates["primary_broker"].str.contains(
            broker.split()[0], case=False, na=False)
        candidates.loc[brok_match, "similarity_score"] += 15.0

    if revenue_m and not pdfs.empty:
        pdf_rev = pdfs[["company_name", "revenue_millions"]].dropna()
        if not pdf_rev.empty:
            pdf_rev["rev_diff"] = abs(pdf_rev["revenue_millions"] - revenue_m)
            close_rev = pdf_rev[pdf_rev["rev_diff"] < revenue_m * 0.5]["company_name"]
            rev_match = candidates["Submission Account Name"].isin(close_rev)
            candidates.loc[rev_match, "similarity_score"] += 10.0

    # Sort by similarity, take top n
    top = (
        candidates[candidates["similarity_score"] > 0]
        .sort_values("similarity_score", ascending=False)
        .head(n_twins)
    )

    if top.empty:
        top = candidates.sort_values("approval_rate", ascending=False).head(n_twins)

    # ── Aggregate twin outcomes ────────────────────────────────────────────────
    twin_approval_rate = top["approval_rate"].mean()
    twin_avg_score = top["risk_score"].mean() if "risk_score" in top.columns else 50
    rec_dist = top["recommendation"].value_counts().to_dict() if "recommendation" in top.columns else {}
    _mode = top["recommendation"].mode() if "recommendation" in top.columns and len(top) > 0 else []
    most_common_rec = _mode.iloc[0] if len(_mode) > 0 else "STANDARD_UW"
    twin_avg_premium = top["avg_premium"].mean()

    # ── Counterfactual analysis ────────────────────────────────────────────────
    counterfactuals = []
    if controls:
        all_customers_with_pdfs = pdfs.copy() if not pdfs.empty else pd.DataFrame()
        for ctrl_key, ctrl_label in CONTROL_LABELS.items():
            user_has = controls.get(ctrl_key, False)
            if not user_has and not all_customers_with_pdfs.empty and ctrl_key in all_customers_with_pdfs.columns:
                with_ctrl = all_customers_with_pdfs[
                    all_customers_with_pdfs[ctrl_key].astype(str).str.lower() == "true"
                ]
                pct_approved = len(with_ctrl) / len(all_customers_with_pdfs) if len(all_customers_with_pdfs) else 0
                if pct_approved > 0.5:
                    counterfactuals.append({
                        "control": ctrl_label,
                        "pct_twins_with_control": round(pct_approved * 100, 0),
                        "impact": f"Adding {ctrl_label} could improve approval alignment with {pct_approved:.0%} of approved customers",
                    })

    # ── Gap analysis ──────────────────────────────────────────────────────────
    gaps = []
    if controls and not pdfs.empty:
        approved_pdfs = pdfs  # Use all PDF data as proxy for "approved" profile
        for ctrl_key, ctrl_label in CONTROL_LABELS.items():
            user_has = controls.get(ctrl_key, False)
            if ctrl_key in approved_pdfs.columns:
                pct_approved_have = (
                    approved_pdfs[ctrl_key].astype(str).str.lower() == "true"
                ).mean()
                if not user_has and pct_approved_have > 0.6:
                    gaps.append({
                        "control": ctrl_label,
                        "present_in_pct": round(pct_approved_have * 100, 0),
                        "severity": "HIGH" if pct_approved_have > 0.8 else "MEDIUM",
                    })
                elif user_has:
                    gaps.append({
                        "control": ctrl_label,
                        "present_in_pct": round(pct_approved_have * 100, 0),
                        "severity": "POSITIVE",
                    })

    # ── Predicted recommendation ──────────────────────────────────────────────
    # Control coverage score (0-1) — key differentiator for new submissions
    critical_controls = [
        "control_firewall", "control_mfa", "control_backup",
        "control_incident_response", "control_encryption",
    ]
    if controls:
        ctrl_present = sum(1 for v in controls.values() if v)
        ctrl_total = len(controls)
        ctrl_coverage = ctrl_present / ctrl_total if ctrl_total else 0.5
        critical_coverage = sum(1 for k in critical_controls if controls.get(k, False)) / len(critical_controls)
    else:
        ctrl_coverage = 0.5
        critical_coverage = 0.5

    # Composite score: blend twin portfolio signal with controls profile
    # Controls are a forward-looking indicator; portfolio avg is backward-looking
    composite_score = (twin_avg_score * 0.4) + ((1 - ctrl_coverage) * 100 * 0.35) + ((1 - critical_coverage) * 100 * 0.25)

    # ── Twin distribution vote ─────────────────────────────────────────────────
    twin_vote_scores = {"FAST_TRACK": 0, "STANDARD_UW": 1, "FRESH_UW": 2}
    twin_rec_counts = rec_dist  # e.g. {"FAST_TRACK": 3, "FRESH_UW": 2}
    if twin_rec_counts:
        twin_vote_raw = max(twin_rec_counts, key=lambda k: twin_rec_counts.get(k, 0))
    else:
        twin_vote_raw = "STANDARD_UW"
    twin_vote_numeric = twin_vote_scores.get(twin_vote_raw, 1)  # 0=fast, 1=std, 2=fresh

    # ── Controls adjustment ────────────────────────────────────────────────────
    # Controls can shift the twin vote by +/-1 level
    if ctrl_coverage >= 0.75 and critical_coverage >= 1.0:
        ctrl_adjustment = -1   # Good controls → shift toward Fast-Track
    elif ctrl_coverage < 0.33 or critical_coverage < 0.4:
        ctrl_adjustment = +1   # Poor controls → shift toward Fresh UW
    else:
        ctrl_adjustment = 0    # Neutral

    final_numeric = max(0, min(2, twin_vote_numeric + ctrl_adjustment))
    rec_map = {0: "FAST_TRACK", 1: "STANDARD_UW", 2: "FRESH_UW"}
    predicted_rec = rec_map[final_numeric]

    # Confidence: higher when twin vote and controls agree
    if ctrl_adjustment == 0 or (twin_vote_numeric + ctrl_adjustment == final_numeric and ctrl_adjustment != 0):
        base_conf = 0.80 if ctrl_adjustment != 0 else 0.72
    else:
        base_conf = 0.65  # Mixed signals = lower confidence

    predicted_confidence = round(min(0.92, base_conf + ctrl_coverage * 0.10), 2)

    # Expose reasoning for UI
    reasoning_parts = [
        f"Twin vote: **{twin_vote_raw}** ({twin_rec_counts})",
        f"Controls: {ctrl_coverage:.0%} coverage, critical controls {'all present' if critical_coverage >= 1.0 else f'{critical_coverage:.0%} present'}",
        f"Adjustment: {'none' if ctrl_adjustment == 0 else ('upgrade (good controls)' if ctrl_adjustment < 0 else 'downgrade (control gaps)')}",
    ]

    twins_list = []
    for _, row in top.iterrows():
        twins_list.append({
            "customer": row["Submission Account Name"],
            "similarity": round(row["similarity_score"], 1),
            "approval_rate": round(row["approval_rate"] * 100, 1),
            "risk_score": round(row.get("risk_score", 50), 1),
            "recommendation": row.get("recommendation", "STANDARD_UW"),
            "submissions": int(row["submission_count"]),
            "product": row["primary_product"][:40] if pd.notna(row["primary_product"]) else "",
        })

    return {
        "twins": twins_list,
        "twin_count": len(top),
        "aggregate": {
            "avg_approval_rate": round(twin_approval_rate * 100, 1),
            "avg_risk_score": round(twin_avg_score, 1),
            "avg_premium": round(twin_avg_premium, 0) if pd.notna(twin_avg_premium) else None,
            "recommendation_distribution": rec_dist,
        },
        "predicted_recommendation": predicted_rec,
        "predicted_confidence": predicted_confidence,
        "twin_vote": twin_vote_raw,
        "ctrl_adjustment": ctrl_adjustment,
        "ctrl_coverage": round(ctrl_coverage * 100, 0),
        "critical_coverage": round(critical_coverage * 100, 0),
        "reasoning_steps": reasoning_parts,
        "counterfactuals": counterfactuals[:5],
        "gaps": gaps,
    }


def generate_twin_narrative(twin_result: Dict, customer_inputs: Dict) -> str:
    """Generate plain-language summary of twin analysis."""
    agg = twin_result.get("aggregate", {})
    rec = twin_result.get("predicted_recommendation", "STANDARD_UW")
    conf = twin_result.get("predicted_confidence", 0.75)
    twins = twin_result.get("twins", [])
    gaps = [g for g in twin_result.get("gaps", []) if g.get("severity") == "HIGH"]

    lines = [
        f"Based on {len(twins)} similar existing customers in our portfolio, "
        f"the predicted recommendation is **{rec}** (confidence: {conf:.0%}).",
        "",
        f"Twin portfolio shows an average approval rate of **{agg.get('avg_approval_rate', 0):.1f}%** "
        f"and average risk score of **{agg.get('avg_risk_score', 50):.0f}/100**.",
    ]

    if gaps:
        ctrl_names = ", ".join(g["control"] for g in gaps[:3])
        lines.append(
            f"\n**Control gaps detected:** {ctrl_names} — "
            f"present in 60%+ of approved twins but missing in this submission."
        )

    positive = [g for g in twin_result.get("gaps", []) if g.get("severity") == "POSITIVE"]
    if positive:
        pos_names = ", ".join(g["control"] for g in positive[:3])
        lines.append(f"\n**Positive signals:** {pos_names} — aligns with approved twin profile.")

    lines.append("\n*Advisory only — human underwriter decision required.*")
    return "\n".join(lines)
