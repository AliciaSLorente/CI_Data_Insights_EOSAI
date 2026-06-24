"""
KG-derived business metrics for underwriting intelligence.
Metric 1: Retention Risk Score
Metric 3: Re-application Intelligence
Metric 6: Peer Benchmarking
"""

import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from typing import Dict, List

DATA = Path("data/parsed")


@st.cache_data
def _load():
    subs = pd.read_csv(DATA / "all_submissions.csv", low_memory=False)
    subs["Requested Coverage Effective Date"] = pd.to_datetime(
        subs["Requested Coverage Effective Date"], errors="coerce"
    )
    subs["Year"] = subs["Requested Coverage Effective Date"].dt.year
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )
    recs = pd.read_csv(DATA / "all_recommendations.csv")
    deltas = pd.read_csv(DATA / "all_deltas.csv")
    repeats = pd.read_csv(DATA / "repeat_customers.csv")
    return subs, recs, deltas, repeats


# ── Metric 1: Retention Risk ────────────────────────────────────────────────────

@st.cache_data
def retention_risk_customers(top_n: int = 50) -> pd.DataFrame:
    """
    Customers with historically good profiles (approval_rate > 30%)
    who have recent declines — likely to shop the risk elsewhere.
    """
    subs, recs, deltas, _ = _load()

    # Per-customer features
    features = (
        subs.groupby("Submission Account Name")
        .agg(
            total=("is_bound", "count"),
            bound=("is_bound", "sum"),
            recent_status=("Current Status Description", "last"),
            primary_product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
            latest_year=("Year", "max"),
        )
        .reset_index()
    )
    features["approval_rate"] = features["bound"] / features["total"]

    # Recent performance: last 3 submissions
    recent = (
        subs.sort_values("Requested Coverage Effective Date")
        .groupby("Submission Account Name")
        .tail(3)
        .groupby("Submission Account Name")
        .agg(
            recent_bound=("is_bound", "sum"),
            recent_declined=("Current Status Description", lambda x: (x == "Declined").sum()),
            recent_total=("is_bound", "count"),
        )
        .reset_index()
    )
    features = features.merge(recent, on="Submission Account Name", how="left")
    features["recent_approval_rate"] = features["recent_bound"] / features["recent_total"].clip(1)

    # Retention risk: good history + recent struggle
    at_risk = features[
        (features["approval_rate"] >= 0.3)
        & (features["recent_declined"] >= 2)
        & (features["total"] >= 3)
    ].copy()

    # Retention risk score: 0-100 (higher = more at risk of churning)
    at_risk["retention_risk_score"] = (
        (at_risk["recent_declined"] / at_risk["recent_total"].clip(1)) * 50
        + (1 - at_risk["recent_approval_rate"]) * 30
        + (at_risk["approval_rate"] * 20)  # higher historical = more valuable to retain
    ).clip(0, 100).round(1)

    # Merge with recommendations
    at_risk = at_risk.merge(
        recs[["company_name", "risk_score", "recommendation"]],
        left_on="Submission Account Name",
        right_on="company_name",
        how="left",
    ).drop(columns=["company_name"], errors="ignore")

    return (
        at_risk[["Submission Account Name", "retention_risk_score", "approval_rate",
                 "recent_declined", "recent_total", "primary_product",
                 "primary_broker", "risk_score", "recommendation"]]
        .sort_values("retention_risk_score", ascending=False)
        .head(top_n)
        .rename(columns={
            "Submission Account Name": "Customer",
            "retention_risk_score": "Retention Risk Score",
            "approval_rate": "Historical Approval Rate",
            "recent_declined": "Recent Declines",
            "recent_total": "Recent Submissions",
            "primary_product": "Product",
            "primary_broker": "Broker",
            "risk_score": "AI Risk Score",
            "recommendation": "Recommendation",
        })
    )


@st.cache_data
def retention_risk_summary() -> Dict:
    df = retention_risk_customers(1000)
    if df.empty:
        return {"total": 0, "high": 0, "medium": 0}
    high = (df["Retention Risk Score"] >= 60).sum()
    medium = ((df["Retention Risk Score"] >= 40) & (df["Retention Risk Score"] < 60)).sum()
    return {
        "total": len(df),
        "high": int(high),
        "medium": int(medium),
        "avg_score": round(df["Retention Risk Score"].mean(), 1),
    }


# ── Metric 3: Re-application Intelligence ──────────────────────────────────────

@st.cache_data
def reapplication_analysis() -> pd.DataFrame:
    """
    Customers who were declined and reapplied.
    Shows whether they improved, how many times, and current status.
    """
    subs, recs, deltas, _ = _load()

    # Find customers whose first submission was Declined
    first_sub = (
        subs.sort_values("Requested Coverage Effective Date")
        .groupby("Submission Account Name")
        .first()
        .reset_index()
    )
    first_declined = first_sub[
        first_sub["Current Status Description"] == "Declined"
    ]["Submission Account Name"]

    # Get their full history
    reapplied = subs[subs["Submission Account Name"].isin(first_declined)].copy()
    reapplied_agg = (
        reapplied.groupby("Submission Account Name")
        .agg(
            total_submissions=("Submission Account Name", "count"),
            times_declined=("Current Status Description", lambda x: (x == "Declined").sum()),
            ever_bound=("is_bound", "any"),
            latest_status=("Current Status Description", "last"),
            primary_product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
        )
        .reset_index()
    )

    # Merge with deltas for improvement flag
    reapplied_agg = reapplied_agg.merge(
        deltas[["company_name", "status_improved", "status_degraded", "months_span"]],
        left_on="Submission Account Name",
        right_on="company_name",
        how="left",
    ).drop(columns=["company_name"], errors="ignore")

    reapplied_agg["outcome"] = reapplied_agg.apply(
        lambda r: "Converted" if r["ever_bound"]
        else ("Improving" if r["status_improved"] else
              ("Persistent" if r["total_submissions"] >= 3 else "Single retry")),
        axis=1
    )

    return reapplied_agg.sort_values("total_submissions", ascending=False).rename(columns={
        "Submission Account Name": "Customer",
        "total_submissions": "Total Submissions",
        "times_declined": "Times Declined",
        "ever_bound": "Ever Bound",
        "latest_status": "Latest Status",
        "primary_product": "Product",
        "primary_broker": "Broker",
        "status_improved": "Improved",
        "months_span": "Months Active",
        "outcome": "Outcome",
    })


@st.cache_data
def reapplication_summary() -> Dict:
    df = reapplication_analysis()
    if df.empty:
        return {}
    outcomes = df["Outcome"].value_counts().to_dict()
    return {
        "total_reapplied": len(df),
        "converted": int(outcomes.get("Converted", 0)),
        "improving": int(outcomes.get("Improving", 0)),
        "persistent": int(outcomes.get("Persistent", 0)),
        "conversion_rate": round(outcomes.get("Converted", 0) / len(df) * 100, 1),
        "outcomes": outcomes,
    }


# ── Metric 6: Peer Benchmarking ─────────────────────────────────────────────────

@st.cache_data
def peer_benchmark(customer_name: str) -> Dict:
    """
    Compare a specific customer against their KG cluster peers.
    Returns how the customer ranks vs their peer group.
    """
    subs, recs, deltas, _ = _load()

    from src.models.kg_real import compute_risk_clusters
    clusters = compute_risk_clusters()

    # Find customer's cluster
    cust_row = clusters[clusters["Submission Account Name"] == customer_name]
    if cust_row.empty:
        return {"error": f"Customer '{customer_name}' not found in clusters"}

    cust = cust_row.iloc[0]
    cluster_label = cust["cluster_label"]

    # Get all peers in the same cluster
    peers = clusters[clusters["cluster_label"] == cluster_label].copy()
    n_peers = len(peers)

    # Customer metrics
    cust_approval = cust["approval_rate"]
    cust_subs = cust["submission_count"]
    cust_score = cust.get("risk_score", 50) if "risk_score" in cust else None

    # Merge scores from recs
    peers = peers.merge(
        recs[["company_name", "risk_score"]],
        left_on="Submission Account Name",
        right_on="company_name",
        how="left",
    ).drop(columns=["company_name"], errors="ignore")

    # Peer averages
    peer_avg_approval = peers["approval_rate"].mean()
    peer_avg_subs = peers["submission_count"].mean()
    peer_avg_score = peers["risk_score"].mean() if "risk_score" in peers.columns else 50

    # Percentile rank
    approval_pct = (peers["approval_rate"] <= cust_approval).mean() * 100
    score_pct = (peers["risk_score"] <= (cust_score or 50)).mean() * 100 if "risk_score" in peers.columns else 50

    # Top peers (similar approval rate)
    top_peers = (
        peers[peers["Submission Account Name"] != customer_name]
        .nlargest(5, "approval_rate")[["Submission Account Name", "approval_rate", "submission_count"]]
        .rename(columns={
            "Submission Account Name": "Peer Customer",
            "approval_rate": "Approval Rate",
            "submission_count": "Submissions",
        })
    )
    top_peers["Approval Rate"] = (top_peers["Approval Rate"] * 100).round(1)

    return {
        "customer": customer_name,
        "cluster": cluster_label,
        "peer_count": n_peers,
        "customer_metrics": {
            "approval_rate": round(cust_approval * 100, 1),
            "submission_count": int(cust_subs),
            "risk_score": round(cust_score, 1) if cust_score else None,
        },
        "peer_averages": {
            "approval_rate": round(peer_avg_approval * 100, 1),
            "submission_count": round(peer_avg_subs, 1),
            "risk_score": round(peer_avg_score, 1),
        },
        "percentile_rank": {
            "approval_rate": round(approval_pct, 0),
            "risk_score": round(score_pct, 0),
        },
        "top_peers": top_peers.to_dict(orient="records"),
        "verdict": (
            "Above average" if cust_approval > peer_avg_approval
            else "Below average"
        ) + f" vs {cluster_label} cluster peers",
    }
