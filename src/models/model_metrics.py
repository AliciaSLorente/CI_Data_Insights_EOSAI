"""
Model Metrics module — honest evaluation of the scoring and clustering models.

Provides:
  1. Scoring model metrics  — score distribution, recommendation breakdown,
                             score vs actual decision consistency
  2. KMeans optimisation    — elbow method + silhouette score to validate k
  3. Feature importance     — which scoring components drive the score most
  4. Calibration check      — are FAST_TRACK scores really different from FRESH_UW?

All metrics are computed from pre-computed CSVs (offline data).
No retraining happens here — purely diagnostic / transparency layer.
"""

import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from typing import Tuple, List, Dict

DATA = Path("data/parsed")


@st.cache_data
def _load_recs() -> pd.DataFrame:
    p = DATA / "all_recommendations.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data
def _load_subs() -> pd.DataFrame:
    p = DATA / "all_submissions.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, low_memory=False)
    df["is_bound"] = (
        df["Submission Product Bound Premium Amount"].notna()
        & (df["Submission Product Bound Premium Amount"] > 0)
    )
    return df


# ── 1. Score distribution ──────────────────────────────────────────────────────

@st.cache_data
def score_distribution() -> Dict:
    """
    Returns score distribution stats and recommendation breakdown.
    Key question: do scores discriminate? Are they spread across 0-100
    or clustered around 50 (no discrimination)?
    """
    recs = _load_recs()
    if recs.empty:
        return {}

    total = len(recs)
    rec_counts = recs["recommendation"].value_counts().to_dict()

    return {
        "total": total,
        "mean": round(recs["risk_score"].mean(), 1),
        "std": round(recs["risk_score"].std(), 1),
        "min": round(recs["risk_score"].min(), 1),
        "max": round(recs["risk_score"].max(), 1),
        "median": round(recs["risk_score"].median(), 1),
        "pct_below_35": round((recs["risk_score"] < 35).sum() / total * 100, 1),
        "pct_35_65":    round(((recs["risk_score"] >= 35) & (recs["risk_score"] < 65)).sum() / total * 100, 1),
        "pct_above_65": round((recs["risk_score"] >= 65).sum() / total * 100, 1),
        "recommendation_counts": rec_counts,
        "scores": recs["risk_score"].tolist(),
        "recommendations": recs["recommendation"].tolist(),
    }


# ── 2. Score vs actual decision consistency ────────────────────────────────────

@st.cache_data
def score_vs_decision() -> pd.DataFrame:
    """
    Compares model recommendation vs actual submission status (Bound/Declined/etc).
    Key question: do Fast-Track customers actually get bound more often?
    This validates whether the scoring logic correlates with real outcomes.
    """
    recs = _load_recs()
    subs = _load_subs()

    if recs.empty or subs.empty:
        return pd.DataFrame()

    # Get latest status per customer
    latest_status = (
        subs.sort_values("Requested Coverage Effective Date")
        .groupby("Submission Account Name")["Current Status Description"]
        .last()
        .reset_index()
    )

    merged = recs.merge(
        latest_status,
        left_on="company_name",
        right_on="Submission Account Name",
        how="inner"
    )

    # Group by recommendation, show status breakdown
    result = (
        merged.groupby(["recommendation", "Current Status Description"])
        .size()
        .reset_index(name="count")
    )

    # Add approval rate per recommendation bucket
    merged["is_bound"] = merged["Current Status Description"].isin(["Bound", "Rated"])
    approval = (
        merged.groupby("recommendation")["is_bound"]
        .mean()
        .reset_index()
        .rename(columns={"is_bound": "actual_approval_rate"})
    )
    approval["actual_approval_rate"] = (approval["actual_approval_rate"] * 100).round(1)

    return approval


# ── 3. Feature importance ──────────────────────────────────────────────────────

@st.cache_data
def feature_importance() -> pd.DataFrame:
    """
    Shows which scoring components (comp_*) drive the final score most.
    Uses mean absolute contribution as importance proxy.
    Key question: is the model balanced or dominated by one component?
    """
    recs = _load_recs()
    if recs.empty:
        return pd.DataFrame()

    comp_cols = [c for c in recs.columns if c.startswith("comp_")]
    if not comp_cols:
        return pd.DataFrame()

    importance = []
    for col in comp_cols:
        vals = recs[col].dropna()
        importance.append({
            "Component": col.replace("comp_", "").replace("_", " ").title(),
            "Mean Contribution": round(vals.mean(), 2),
            "Mean Abs Contribution": round(vals.abs().mean(), 2),
            "Std": round(vals.std(), 2),
            "Pct Non-Zero": round((vals != 0).mean() * 100, 1),
        })

    return pd.DataFrame(importance).sort_values("Mean Abs Contribution", ascending=False)


# ── 4. KMeans optimisation ────────────────────────────────────────────────────

@st.cache_data
def kmeans_optimisation(max_k: int = 8) -> Tuple[pd.DataFrame, int]:
    """
    Runs elbow method and silhouette scores to find optimal k.
    Returns:
      - DataFrame with k, inertia, silhouette_score for each k tested
      - recommended_k: the k with highest silhouette score

    This is the data science validation of the k=3 choice.
    """
    subs = _load_subs()
    recs = _load_recs()

    if subs.empty or recs.empty:
        return pd.DataFrame(), 3

    # Build same feature matrix as compute_risk_clusters()
    features = (
        subs.groupby("Submission Account Name")
        .agg(
            submission_count=("Submission Account Name", "count"),
            approval_rate=("is_bound", "mean"),
            avg_premium=("Quoted Premium Amount", "mean"),
            years_active=("Requested Coverage Effective Date", lambda x:
                         pd.to_datetime(x, errors="coerce").dt.year.nunique()),
            recent_declined=("Current Status Description",
                            lambda x: (x.tail(3) == "Declined").sum()),
        )
        .reset_index()
    )

    repeat_names = set(recs["company_name"])
    features = features[features["Submission Account Name"].isin(repeat_names)].fillna(0)

    feature_cols = ["submission_count", "approval_rate", "avg_premium",
                    "years_active", "recent_declined"]
    X = features[feature_cols].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    results = []
    for k in range(2, min(max_k + 1, len(X))):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels) if k > 1 else 0
        results.append({
            "k": k,
            "inertia": round(km.inertia_, 1),
            "silhouette_score": round(sil, 4),
        })

    df = pd.DataFrame(results)
    # Recommended k = highest silhouette score
    recommended_k = int(df.loc[df["silhouette_score"].idxmax(), "k"])
    return df, recommended_k


@st.cache_data
def cluster_quality_summary(k: int = None) -> Dict:
    """
    Summary of cluster quality for the chosen k.
    If k is None, uses the recommended k from kmeans_optimisation.
    """
    _, recommended_k = kmeans_optimisation()
    k = k or recommended_k

    df_opt, _ = kmeans_optimisation()
    if df_opt.empty:
        return {}

    row = df_opt[df_opt["k"] == k]
    if row.empty:
        return {}

    r = row.iloc[0]
    sil = r["silhouette_score"]

    # Interpret silhouette
    if sil >= 0.7:
        interpretation = "Strong — clusters are well-separated"
    elif sil >= 0.5:
        interpretation = "Reasonable — moderate separation"
    elif sil >= 0.25:
        interpretation = "Weak — clusters overlap significantly"
    else:
        interpretation = "Poor — clusters are not meaningful"

    return {
        "k_used": k,
        "recommended_k": recommended_k,
        "silhouette_score": sil,
        "inertia": r["inertia"],
        "interpretation": interpretation,
        "note": "k=3 was used in production for simplicity. "
                f"Optimal k={recommended_k} based on silhouette score.",
    }
