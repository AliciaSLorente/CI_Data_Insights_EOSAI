"""
Mass scoring for all 9,078 repeat customers.
Computes risk scores from submission history features without needing PDFs.
Saves results to data/parsed/all_recommendations.csv for dashboard use.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path("data/parsed")
OUT_PATH = DATA / "all_recommendations.csv"


def compute_customer_score(group: pd.DataFrame) -> dict:
    """
    Compute risk score for a single customer from their submission history.
    Returns dict with score, recommendation, confidence, components.
    """
    base = 50.0
    components = {}

    group = group.sort_values("Requested Coverage Effective Date", na_position="last")
    n = len(group)

    # ── Factor 1: Recent decline rate ─────────────────────────────────────────
    recent = group.tail(3)
    declined = (recent["Current Status Description"] == "Declined").sum()
    decline_pts = declined * 12.0
    components["recent_declines"] = decline_pts

    # ── Factor 2: Overall approval trajectory ─────────────────────────────────
    total_bound = group["is_bound"].sum()
    approval_rate = total_bound / n if n > 0 else 0
    if approval_rate >= 0.5:
        traj_pts = -15.0
    elif approval_rate >= 0.25:
        traj_pts = 0.0
    else:
        traj_pts = 15.0
    components["approval_trajectory"] = traj_pts

    # ── Factor 3: Submission frequency (high freq = established = lower risk) ──
    if n >= 5:
        freq_pts = -8.0
    elif n >= 3:
        freq_pts = -4.0
    else:
        freq_pts = 0.0
    components["submission_frequency"] = freq_pts

    # ── Factor 4: Premium size (proxy for complexity) ─────────────────────────
    avg_premium = group["Quoted Premium Amount"].mean()
    if pd.notna(avg_premium) and avg_premium > 0:
        if avg_premium > 500_000:
            prem_pts = 10.0
        elif avg_premium > 100_000:
            prem_pts = 5.0
        else:
            prem_pts = 0.0
    else:
        prem_pts = 0.0
    components["premium_complexity"] = prem_pts

    # ── Factor 5: Latest status ────────────────────────────────────────────────
    latest_status = group["Current Status Description"].iloc[-1]
    status_pts = {
        "Bound": -10.0, "Rated": -5.0, "Quoted": 0.0,
        "Received": 5.0, "Declined": 15.0, "Quote not taken": 8.0,
    }.get(latest_status, 0.0)
    components["latest_status"] = status_pts

    score = base + sum(components.values())
    score = max(0.0, min(100.0, score))

    # ── Recommendation ─────────────────────────────────────────────────────────
    if score < 35:
        rec = "FAST_TRACK"
        conf = round(0.95 - score / 350, 2)
    elif score >= 65:
        rec = "FRESH_UW"
        conf = round(0.75 + (score - 65) / 200, 2)
    else:
        rec = "STANDARD_UW"
        conf = 0.75

    reasoning = (
        f"Approval rate: {approval_rate:.0%}, "
        f"Recent declines: {int(declined)}/3, "
        f"Submissions: {n}, "
        f"Latest: {latest_status}"
    )

    return {
        "risk_score": round(score, 1),
        "recommendation": rec,
        "confidence": min(0.99, conf),
        "reasoning": reasoning,
        **{f"comp_{k}": v for k, v in components.items()},
    }


def run_mass_scoring(force: bool = False) -> pd.DataFrame:
    """
    Score all repeat customers. Cached to CSV — only recomputes if forced.
    """
    if OUT_PATH.exists() and not force:
        return pd.read_csv(OUT_PATH)

    print("Running mass scoring for all repeat customers...")
    subs = pd.read_csv(DATA / "all_submissions.csv", low_memory=False)
    subs["Requested Coverage Effective Date"] = pd.to_datetime(
        subs["Requested Coverage Effective Date"], errors="coerce"
    )
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )

    repeats = pd.read_csv(DATA / "repeat_customers.csv")
    repeat_names = set(repeats["Submission Account Name"])
    subs = subs[subs["Submission Account Name"].isin(repeat_names)]

    results = []
    for company, group in subs.groupby("Submission Account Name"):
        row = compute_customer_score(group)
        row["company_name"] = company
        results.append(row)

    df = pd.DataFrame(results)
    cols = ["company_name", "risk_score", "recommendation", "confidence", "reasoning"]
    comp_cols = [c for c in df.columns if c.startswith("comp_")]
    df = df[cols + comp_cols]
    df.to_csv(OUT_PATH, index=False)
    print(f"Scored {len(df):,} customers -> {OUT_PATH}")
    return df


if __name__ == "__main__":
    df = run_mass_scoring(force=True)
    print(df["recommendation"].value_counts())
    print(f"Score range: {df['risk_score'].min():.1f} – {df['risk_score'].max():.1f}")
    print(f"Mean score: {df['risk_score'].mean():.1f}")
