"""
MCP Server: UW Metrics Tools
Group 2 of 3 — covers scoring, recommendations and deltas (Dataset 2)

Tools exposed:
  get_risk_score         — AI risk score + recommendation + components
  get_submission_delta   — what changed first→latest submission

Run standalone:
  python -m src.mcp_servers.scoring_server
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

mcp = FastMCP("zurich-scoring")


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


# Module-level cache — loaded once per server process, reused for all calls
_RECS_CACHE = None
_DELTAS_CACHE = None


def _get_recs():
    global _RECS_CACHE
    if _RECS_CACHE is None:
        p = DATA / "all_recommendations.csv"
        _RECS_CACHE = pd.read_csv(p) if p.exists() else pd.DataFrame()
    return _RECS_CACHE


def _get_deltas():
    global _DELTAS_CACHE
    if _DELTAS_CACHE is None:
        p = DATA / "all_deltas.csv"
        _DELTAS_CACHE = pd.read_csv(p) if p.exists() else pd.DataFrame()
    return _DELTAS_CACHE


@mcp.tool()
def get_risk_score(customer_name: str) -> str:
    """
    Get the AI risk score and recommendation for a customer.
    Returns score 0-100, recommendation (FAST_TRACK / STANDARD_UW / FRESH_UW),
    confidence, and breakdown of score components.
    Use to answer: should this customer be fast-tracked? what drove the score?
    """
    recs = _get_recs()
    if recs.empty:
        return _safe({"error": "Recommendations data not available"})
    mask = recs["company_name"].astype(str).str.contains(customer_name, case=False, na=False)
    matches = recs[mask]

    if matches.empty:
        return _safe({"message": f"No risk score found for '{customer_name}'"})

    row = matches.iloc[0]
    comp_cols = [c for c in recs.columns if c.startswith("comp_")]
    components = {
        c.replace("comp_", "").replace("_", " ").title(): float(row[c])
        for c in comp_cols if c in row.index and pd.notna(row[c])
    }

    return _safe({
        "customer": row["company_name"],
        "risk_score": row["risk_score"],
        "recommendation": row["recommendation"],
        "confidence": row["confidence"],
        "reasoning": row.get("reasoning", ""),
        "score_components": components,
        "interpretation": {
            "FAST_TRACK": "Low risk — stable submission, expedite processing",
            "STANDARD_UW": "Moderate risk — standard underwriting process",
            "FRESH_UW": "High risk — material changes, requires full review",
        }.get(row["recommendation"], ""),
    })


@mcp.tool()
def get_submission_delta(customer_name: str) -> str:
    """
    Get the delta (what changed) between the first and latest submission for a customer.
    Returns: status improved or degraded, premium change %, broker changed,
    months between submissions.
    Use to answer: has this customer improved since we last saw them?
    """
    deltas = _get_deltas()
    if deltas.empty:
        return _safe({"error": "Delta data not available. Run mass_deltas.py first."})
    mask = deltas["company_name"].astype(str).str.contains(customer_name, case=False, na=False)
    matches = deltas[mask]

    if matches.empty:
        return _safe({"message": f"No delta data for '{customer_name}'"})

    row = matches.iloc[0]
    result = {k: (None if pd.isna(v) else v) for k, v in row.items()}

    # Add human-readable interpretation
    if result.get("status_improved"):
        trajectory = "IMPROVING — customer moved to better status over time"
    elif result.get("status_degraded"):
        trajectory = "DEGRADING — customer moved to worse status over time"
    else:
        trajectory = "STABLE — no significant status change"

    result["trajectory_interpretation"] = trajectory
    return _safe(result)


@mcp.tool()
def get_control_delta(customer_name: str) -> str:
    """
    Show which security controls were present or absent across a customer's PDF submissions.
    Directly answers: 'What datapoints fell off or are missing on the most recent application?'
    Compares controls across all available PDF submissions for this customer.

    Use when: 'what controls changed?', 'what was present before?', 'what fell off?'
    """
    pdfs_path = DATA / "pdf_extracted_fields.csv"
    if not pdfs_path.exists():
        return _safe({"error": "PDF extracted fields not available."})

    pdfs = pd.read_csv(pdfs_path)
    mask = pdfs["company_name"].astype(str).str.contains(customer_name, case=False, na=False)
    customer_pdfs = pdfs[mask].copy()

    if customer_pdfs.empty:
        return _safe({
            "message": f"No PDF data for '{customer_name}' — not in Dataset 2 (25 Cyber companies).",
            "fallback": "Use get_submission_delta() — covers all 9,078 repeat customers from Dataset 1.",
        })

    control_cols = [c for c in pdfs.columns if c.startswith("control_") or c.startswith("policy_")]
    matched_name = customer_pdfs["company_name"].iloc[0]

    # Build per-submission control snapshot
    snapshots = []
    for _, row in customer_pdfs.iterrows():
        snapshot = {
            "pdf_file": row.get("pdf_file", ""),
            "date": row.get("policy_effective_date", ""),
            "revenue_m": row.get("revenue_millions"),
        }
        for col in control_cols:
            label = col.replace("control_", "").replace("policy_", "Policy: ").replace("_", " ").title()
            snapshot[label] = bool(row.get(col, False))
        snapshots.append(snapshot)

    # Compute what changed first → latest
    if len(snapshots) >= 2:
        first, latest = snapshots[0], snapshots[-1]
        added   = [k for k in control_cols if not first.get(k.replace("control_","").replace("policy_","Policy: ").replace("_"," ").title(), False)
                   and latest.get(k.replace("control_","").replace("policy_","Policy: ").replace("_"," ").title(), False)]
        removed = [k for k in control_cols if first.get(k.replace("control_","").replace("policy_","Policy: ").replace("_"," ").title(), False)
                   and not latest.get(k.replace("control_","").replace("policy_","Policy: ").replace("_"," ").title(), False)]
        delta_summary = {
            "controls_added_since_first":   [c.replace("control_","").replace("_"," ").title() for c in added],
            "controls_removed_since_first": [c.replace("control_","").replace("_"," ").title() for c in removed],
            "net_change": len(added) - len(removed),
            "interpretation": (
                "Controls improved" if len(added) > len(removed) else
                "Controls degraded" if len(removed) > len(added) else
                "No net change in controls"
            ),
        }
    else:
        delta_summary = {"note": "Only one PDF submission available — no delta computable"}

    return _safe({
        "customer": matched_name,
        "pdf_submissions": len(snapshots),
        "snapshots": snapshots,
        "delta_summary": delta_summary,
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


