"""
Compute deltas for all repeat customers from all_submissions.csv.
For each customer, compare their latest submission against their first.
Saves to data/parsed/all_deltas.csv.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path("data/parsed")
OUT_PATH = DATA / "all_deltas.csv"


def compute_all_deltas(force: bool = False) -> pd.DataFrame:
    if OUT_PATH.exists() and not force:
        return pd.read_csv(OUT_PATH)

    print("Computing deltas for all repeat customers...")
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
        group = group.sort_values("Requested Coverage Effective Date", na_position="last")
        if len(group) < 2:
            continue

        first = group.iloc[0]
        last = group.iloc[-1]

        # Premium delta
        p_first = first["Quoted Premium Amount"]
        p_last = last["Quoted Premium Amount"]
        if pd.notna(p_first) and pd.notna(p_last) and p_first > 0:
            premium_delta_pct = round((p_last - p_first) / p_first * 100, 1)
        else:
            premium_delta_pct = None

        # Status trajectory
        first_status = first["Current Status Description"]
        last_status = last["Current Status Description"]
        improved = (
            (first_status in ["Declined", "Quote not taken"] and last_status in ["Bound", "Rated", "Quoted"])
        )
        degraded = (
            (first_status in ["Bound", "Rated"] and last_status in ["Declined", "Quote not taken"])
        )

        # Months between first and last
        try:
            months = int((last["Requested Coverage Effective Date"] - first["Requested Coverage Effective Date"]).days / 30)
        except Exception:
            months = 0

        # Product change
        product_changed = first["Product Name"] != last["Product Name"]

        # Broker change
        broker_changed = first["National Broker Name"] != last["National Broker Name"]

        # Approval rate overall
        approval_rate = group["is_bound"].mean()

        results.append({
            "company_name": company,
            "submission_count": len(group),
            "months_span": months,
            "first_status": first_status,
            "latest_status": last_status,
            "status_improved": improved,
            "status_degraded": degraded,
            "premium_delta_pct": premium_delta_pct,
            "product_changed": product_changed,
            "broker_changed": broker_changed,
            "approval_rate": round(approval_rate, 3),
            "total_bound": int(group["is_bound"].sum()),
            "primary_broker": group["National Broker Name"].mode()[0] if len(group) else "",
            "primary_product": group["Product Name"].mode()[0] if len(group) else "",
            "first_year": int(first["Requested Coverage Effective Date"].year) if pd.notna(first["Requested Coverage Effective Date"]) else None,
            "latest_year": int(last["Requested Coverage Effective Date"].year) if pd.notna(last["Requested Coverage Effective Date"]) else None,
        })

    df = pd.DataFrame(results)
    df.to_csv(OUT_PATH, index=False)
    print(f"Computed {len(df):,} deltas -> {OUT_PATH}")
    return df


if __name__ == "__main__":
    df = compute_all_deltas(force=True)
    print(df.head(5).to_string())
    print("\nStatus improved:", df["status_improved"].sum())
    print("Status degraded:", df["status_degraded"].sum())
    print("Broker changed:", df["broker_changed"].sum())
