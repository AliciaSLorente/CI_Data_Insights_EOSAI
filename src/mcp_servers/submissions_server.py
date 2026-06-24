"""
MCP Server: Data Curation Tools
Group 1 of 3 — covers Dataset 1 (all_submissions.csv)

Tools exposed:
  search_portfolio       — filter 46K submissions by customer/product/broker/status
  get_customer_history   — full submission history for a specific customer

Run standalone:
  python -m src.mcp_servers.submissions_server

The orchestrator connects to this server when USE_MCP=true.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import pandas as pd
import numpy as np
from pathlib import Path as DataPath
from mcp.server import FastMCP

DATA = DataPath("data/parsed")

mcp = FastMCP("zurich-submissions")


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.bool_): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        try:
            import pandas as _pd
            if obj is _pd.NA or obj is _pd.NaT: return None
        except Exception: pass
        return super().default(obj)


def _safe(obj) -> str:
    return json.dumps(obj, cls=_Encoder)


def _load_subs():
    p = DATA / "all_submissions.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, low_memory=False)
    df["is_bound"] = (
        df["Submission Product Bound Premium Amount"].notna()
        & (df["Submission Product Bound Premium Amount"] > 0)
    )
    return df


def _load_recs():
    p = DATA / "all_recommendations.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@mcp.tool()
def search_portfolio(
    customer_name: str = None,
    product: str = None,
    broker: str = None,
    status: str = None,
    limit: int = 15,
) -> str:
    """
    Search and filter the full submission portfolio (Dataset 1 — 46,318 submissions).
    Use to answer: how many repeat customers? which LOBs see most repeats?
    broker submission volumes? product trends? cadence of repeat submissions?
    """
    df = _load_subs()
    recs = _load_recs()

    if df.empty:
        return _safe({"error": "No submission data available"})

    # Merge with scores
    if not recs.empty:
        latest = (
            df.sort_values("Requested Coverage Effective Date")
            .groupby("Submission Account Name").last().reset_index()
        )
        latest = latest.merge(
            recs[["company_name", "risk_score", "recommendation"]],
            left_on="Submission Account Name", right_on="company_name", how="left"
        ).drop(columns=["company_name"], errors="ignore")
        df = latest

    if customer_name:
        df = df[df["Submission Account Name"].astype(str).str.contains(customer_name, case=False, na=False)]
    if product:
        col = next((c for c in ["Product Name"] if c in df.columns), None)
        if col:
            df = df[df[col].astype(str).str.contains(product, case=False, na=False)]
    if broker:
        col = next((c for c in ["National Broker Name"] if c in df.columns), None)
        if col:
            df = df[df[col].astype(str).str.contains(broker, case=False, na=False)]
    if status:
        col = next((c for c in ["Current Status Description"] if c in df.columns), None)
        if col:
            df = df[df[col].astype(str).str.contains(status, case=False, na=False)]

    cols = ["Submission Account Name", "Product Name", "National Broker Name",
            "Current Status Description", "Quoted Premium Amount", "risk_score", "recommendation"]
    cols = [c for c in cols if c in df.columns]
    result = df[cols].head(limit).rename(columns={
        "Submission Account Name": "customer", "Product Name": "product",
        "National Broker Name": "broker", "Current Status Description": "status",
        "Quoted Premium Amount": "premium",
    })
    return _safe({"count": len(df), "showing": len(result),
                  "results": result.to_dict(orient="records")})


@mcp.tool()
def get_customer_history(customer_name: str) -> str:
    """
    Get the full submission history for a specific repeat customer.
    Use to answer: how many times has this customer submitted? what changed
    between submissions? what was decided each time?
    """
    all_subs_path = DATA / "all_submissions.csv"
    if not all_subs_path.exists():
        return _safe({"error": "all_submissions.csv not found"})

    df = pd.read_csv(all_subs_path, low_memory=False)
    mask = df["Submission Account Name"].astype(str).str.contains(customer_name, case=False, na=False)
    history = df[mask].sort_values("Requested Coverage Effective Date")

    if history.empty:
        return _safe({"message": f"No history found for '{customer_name}'"})

    matched = history["Submission Account Name"].iloc[0]
    years = pd.to_datetime(history["Requested Coverage Effective Date"], errors="coerce").dt.year
    status_counts = history["Current Status Description"].value_counts().to_dict() if "Current Status Description" in history.columns else {}

    cols = ["Requested Coverage Effective Date", "Product Name", "National Broker Name",
            "Current Status Description", "Quoted Premium Amount", "Underwriter Name"]
    cols = [c for c in cols if c in history.columns]

    return _safe({
        "customer": matched,
        "total_submissions": len(history),
        "years_active": int(years.nunique()) if not years.isna().all() else None,
        "first_submission": str(history["Requested Coverage Effective Date"].iloc[0]),
        "latest_submission": str(history["Requested Coverage Effective Date"].iloc[-1]),
        "products_seen": history["Product Name"].unique().tolist() if "Product Name" in history.columns else [],
        "brokers_seen": history["National Broker Name"].unique().tolist() if "National Broker Name" in history.columns else [],
        "status_counts": status_counts,
        "last_5_submissions": history[cols].tail(5).to_dict(orient="records"),
    })


@mcp.tool()
def get_underwriter_patterns(
    customer_name: str = None,
    product: str = None,
    top_n: int = 10,
) -> str:
    """
    Analyse underwriter decision patterns.
    Answers: 'Do decisions differ by UW? What patterns do we see on brokers?'

    Without customer_name: returns portfolio-wide UW approval rates.
    With customer_name: returns which UWs handled this customer and their decisions.

    Use when: 'which UW has highest approval rate?', 'who handled Company X?',
    'do UW decisions differ?', 'UW patterns'
    """
    all_subs_path = DATA / "all_submissions.csv"
    if not all_subs_path.exists():
        return _safe({"error": "all_submissions.csv not found"})

    subs = pd.read_csv(all_subs_path, low_memory=False)
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )

    if customer_name:
        # Which UWs handled this customer and what did they decide?
        mask = subs["Submission Account Name"].astype(str).str.contains(
            customer_name, case=False, na=False)
        customer_subs = subs[mask]
        if customer_subs.empty:
            return _safe({"message": f"No data found for '{customer_name}'"})

        matched = customer_subs["Submission Account Name"].iloc[0]
        uw_decisions = (
            customer_subs.groupby("Underwriter Name")
            .agg(
                submissions=("Underwriter Name", "count"),
                bound=("is_bound", "sum"),
                decisions=("Current Status Description", lambda x: x.value_counts().to_dict()),
            )
            .reset_index()
        )
        uw_decisions["approval_rate_pct"] = (
            uw_decisions["bound"] / uw_decisions["submissions"].clip(1) * 100
        ).round(1)
        return _safe({
            "customer": matched,
            "underwriter_breakdown": uw_decisions.to_dict(orient="records"),
        })

    # Portfolio-wide UW patterns
    if product:
        subs = subs[subs["Product Name"].astype(str).str.contains(product, case=False, na=False)]

    uw_stats = (
        subs.groupby("Underwriter Name")
        .agg(
            total_submissions=("Underwriter Name", "count"),
            bound=("is_bound", "sum"),
            unique_customers=("Submission Account Name", "nunique"),
        )
        .reset_index()
    )
    uw_stats["approval_rate_pct"] = (
        uw_stats["bound"] / uw_stats["total_submissions"].clip(1) * 100
    ).round(1)
    uw_stats = uw_stats.sort_values("total_submissions", ascending=False).head(top_n)

    avg_rate = subs["is_bound"].mean() * 100
    return _safe({
        "portfolio_avg_approval_pct": round(avg_rate, 1),
        "top_underwriters": uw_stats.to_dict(orient="records"),
        "note": "High variance between UWs may indicate inconsistent decision patterns.",
    })


if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--transport", default="stdio", choices=["stdio","sse"])
    _p.add_argument("--port", type=int, default=8600)
    _a = _p.parse_args()
    if _a.transport == "sse":
        mcp.settings.port = _a.port
        mcp.settings.host = "0.0.0.0"
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
