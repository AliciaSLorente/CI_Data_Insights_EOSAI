"""
Cascade Risk Intelligence Module.

Analyses hidden correlated risks that propagate through the portfolio
after an initial hazard event.

Capabilities:
  1. Cascade Simulator     — propagate a shock through broker/sector graph
  2. Concentration Heatmap — identify accumulation risk pockets
  3. Leading Indicators    — detect clusters in systematic deterioration
  4. Predictive Early Warning — score each customer's cascade vulnerability
  5. Mitigation Actions    — actionable recommendations per customer
"""

import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA = Path("data/parsed")

# ── Event library ─────────────────────────────────────────────────────────────
CASCADE_EVENTS = {
    "cyber_campaign": {
        "label": "Ransomware / Cyber Campaign",
        "affected_products": ["Cyber", "ZCIP"],
        "affected_controls": ["control_edr", "control_incident_response", "control_backup"],
        "propagation": "sector",
        "description": "Coordinated attack targeting sector-wide vulnerabilities (e.g. shared SaaS vendor, common attack vector)",
    },
    "financial_contagion": {
        "label": "Financial Market Contagion",
        "affected_products": ["Financial Lines", "Crime", "D&O"],
        "affected_controls": ["control_siem", "control_dlp"],
        "propagation": "broker",
        "description": "Market shock propagating through financial sector clients and shared broker networks",
    },
    "supply_chain": {
        "label": "Supply Chain Disruption",
        "affected_products": ["Cyber", "Technology"],
        "affected_controls": ["control_patch_management", "control_vulnerability"],
        "propagation": "sector",
        "description": "Critical vendor or cloud provider failure cascading across dependent customers",
    },
    "broker_failure": {
        "label": "Broker Portfolio Shock",
        "affected_products": [],
        "affected_controls": [],
        "propagation": "broker",
        "description": "Quality deterioration in a broker's portfolio, triggering correlated adverse selection",
    },
    "regulatory": {
        "label": "Regulatory / Compliance Wave",
        "affected_products": ["Financial Lines", "Crime", "Security", "Privacy"],
        "affected_controls": ["control_encryption", "control_dlp", "policy_privacy_policy"],
        "propagation": "sector",
        "description": "New regulation (e.g. EU AI Act, NIS2) creating compliance pressure across a sector simultaneously",
    },
}


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
    return subs, recs, deltas


# ── 1. Cascade Simulator ──────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def simulate_cascade(
    event_key: str,
    target_sector: Optional[str] = None,
    target_broker: Optional[str] = None,
    severity: float = 1.0,
) -> Dict:
    """
    Simulate a cascade event propagating through the portfolio.
    Returns affected customers by degree (1st, 2nd, 3rd order).
    """
    subs, recs, _ = _load()
    event = CASCADE_EVENTS.get(event_key, CASCADE_EVENTS["cyber_campaign"])

    # Build customer feature table
    customers = (
        subs.groupby("Submission Account Name")
        .agg(
            primary_product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
            sic_name=("SIC Name", lambda x: x.mode()[0] if len(x) else ""),
            sic_code=("SIC Code", lambda x: x.mode()[0] if len(x) else None),
            submission_count=("Submission Account Name", "count"),
            approval_rate=("is_bound", "mean"),
            total_premium=("Quoted Premium Amount", "sum"),
        )
        .reset_index()
    )
    customers = customers.merge(
        recs[["company_name", "risk_score", "recommendation"]],
        left_on="Submission Account Name", right_on="company_name", how="left"
    ).drop(columns=["company_name"], errors="ignore")
    customers["risk_score"] = customers["risk_score"].fillna(50)

    # ── Degree 1: Directly exposed ────────────────────────────────────────────
    d1_mask = pd.Series(False, index=customers.index)

    if event["propagation"] == "sector" or target_sector:
        # Use exact/stricter matching — require ALL keywords in product name
        for prod_keyword in (event["affected_products"] or []):
            # Require the keyword to appear as a standalone word/phrase (not substring of ProPlus)
            exact = customers["primary_product"].str.lower().str.split().apply(
                lambda words: prod_keyword.lower() in words
                if isinstance(words, list) else False
            )
            d1_mask |= exact

        if target_sector:
            d1_mask |= customers["sic_name"].str.contains(
                target_sector, case=False, na=False
            )

    if target_broker:
        d1_mask |= customers["primary_broker"].str.contains(
            target_broker, case=False, na=False
        )
    elif event["propagation"] == "broker" and event.get("affected_products"):
        # No specific broker — use product keywords for D1, then cascade via brokers
        for prod_keyword in event["affected_products"]:
            exact = customers["primary_product"].str.lower().str.split().apply(
                lambda words: prod_keyword.lower() in words
                if isinstance(words, list) else False
            )
            d1_mask |= exact

    degree1 = customers[d1_mask].copy()
    degree1["cascade_degree"] = 1
    degree1["cascade_score"] = (degree1["risk_score"] * severity).clip(0, 100)

    # ── Degree 2: Same broker as D1 customers ─────────────────────────────────
    d1_brokers = set(degree1["primary_broker"].unique())
    d2_mask = (
        customers["primary_broker"].isin(d1_brokers)
        & ~d1_mask
    )
    degree2 = customers[d2_mask].copy()
    degree2["cascade_degree"] = 2
    degree2["cascade_score"] = (degree2["risk_score"] * severity * 0.6).clip(0, 100)

    # ── Degree 3: Same sector as D2 customers ─────────────────────────────────
    d2_sectors = set(degree2["sic_name"].dropna().unique())
    d3_mask = (
        customers["sic_name"].isin(d2_sectors)
        & ~d1_mask & ~d2_mask
        & (customers["risk_score"] >= 50)
    )
    degree3 = customers[d3_mask].copy()
    degree3["cascade_degree"] = 3
    degree3["cascade_score"] = (degree3["risk_score"] * severity * 0.3).clip(0, 100)

    all_affected = pd.concat([degree1, degree2, degree3], ignore_index=True)

    # Premium at risk
    premium_at_risk = all_affected["total_premium"].sum()
    d1_premium = degree1["total_premium"].sum()

    return {
        "event": event,
        "severity": severity,
        "summary": {
            "total_affected": len(all_affected),
            "degree1_count": len(degree1),
            "degree2_count": len(degree2),
            "degree3_count": len(degree3),
            "premium_at_risk": round(premium_at_risk, 0),
            "d1_premium": round(d1_premium, 0),
            "high_risk_affected": int((all_affected["risk_score"] >= 65).sum()),
        },
        "degree1": degree1[["Submission Account Name", "primary_broker", "primary_product",
                             "risk_score", "cascade_score", "recommendation"]].head(20),
        "degree2": degree2[["Submission Account Name", "primary_broker", "primary_product",
                             "risk_score", "cascade_score", "recommendation"]].head(20),
        "degree3": degree3[["Submission Account Name", "primary_product",
                             "risk_score", "cascade_score", "recommendation"]].head(15),
        "all_affected": all_affected,
    }


# ── 2. Concentration Heatmap ──────────────────────────────────────────────────

@st.cache_data
def concentration_heatmap() -> Tuple[pd.DataFrame, Dict]:
    """
    Broker × Top-Product exposure matrix.
    Returns pivot table and concentration metrics.
    """
    subs, recs, _ = _load()

    # Top products
    top_prods = subs["Product Name"].value_counts().head(6).index.tolist()

    pivot = (
        subs[subs["Product Name"].isin(top_prods)]
        .groupby(["National Broker Name", "Product Name"])
        .size()
        .reset_index(name="count")
        .pivot(index="National Broker Name", columns="Product Name", values="count")
        .fillna(0)
    )
    # Keep top 10 brokers by total
    pivot["_total"] = pivot.sum(axis=1)
    pivot = pivot.nlargest(10, "_total").drop(columns="_total")

    # Concentration metrics
    broker_totals = subs.groupby("National Broker Name").size()
    top3_brokers = broker_totals.nlargest(3)
    top3_pct = top3_brokers.sum() / len(subs) * 100

    sector_totals = subs.groupby("SIC Name").size()
    top3_sectors = sector_totals.nlargest(3)
    top3_sector_pct = top3_sectors.sum() / len(subs) * 100

    product_totals = subs.groupby("Product Name").size()
    top3_products = product_totals.nlargest(3)
    top3_product_pct = top3_products.sum() / len(subs) * 100

    metrics = {
        "top3_broker_concentration": round(top3_pct, 1),
        "top3_sector_concentration": round(top3_sector_pct, 1),
        "top3_product_concentration": round(top3_product_pct, 1),
        "top_broker": top3_brokers.index[0],
        "top_broker_pct": round(top3_brokers.iloc[0] / len(subs) * 100, 1),
        "hhi_broker": round(((broker_totals / len(subs)) ** 2).sum() * 10000, 0),
    }
    return pivot, metrics


# ── 3. Leading Indicators ─────────────────────────────────────────────────────

@st.cache_data
def leading_indicators() -> pd.DataFrame:
    """
    Detect clusters / sectors / brokers showing systematic risk deterioration.
    A cluster is flagged if it shows 2+ consecutive years of worsening metrics.
    """
    subs, recs, _ = _load()

    yearly = (
        subs[subs["Year"].between(2021, 2025)]
        .groupby(["SIC Name", "Year"])
        .agg(
            total=("is_bound", "count"),
            bound=("is_bound", "sum"),
            declined=("Current Status Description", lambda x: (x == "Declined").sum()),
        )
        .reset_index()
    )
    yearly["approval_rate"] = yearly["bound"] / yearly["total"].clip(1)
    yearly["decline_rate"] = yearly["declined"] / yearly["total"].clip(1)

    signals = []
    for sector in yearly["SIC Name"].unique():
        s = yearly[yearly["SIC Name"] == sector].sort_values("Year")
        if len(s) < 3:
            continue
        rates = s["approval_rate"].tolist()
        # Check for 2+ consecutive years of decline
        consecutive_drops = sum(
            1 for i in range(1, len(rates)) if rates[i] < rates[i - 1] - 0.05
        )
        if consecutive_drops >= 2:
            trend = rates[-1] - rates[0]
            total_subs = s["total"].sum()
            if total_subs < 20:
                continue
            signals.append({
                "Sector": sector,
                "Total Submissions": int(total_subs),
                "2021 Approval Rate (%)": round(rates[0] * 100, 1) if rates else None,
                "Latest Approval Rate (%)": round(rates[-1] * 100, 1),
                "Trend": round(trend * 100, 1),
                "Consecutive Drops": consecutive_drops,
                "Severity": "HIGH" if trend < -0.15 else "MEDIUM",
            })

    return pd.DataFrame(signals).sort_values("Trend").reset_index(drop=True) if signals else pd.DataFrame()


# ── 4. Predictive Early Warning ───────────────────────────────────────────────

@st.cache_data
def predict_cascade_vulnerable(top_n: int = 50) -> pd.DataFrame:
    """
    Score each customer's vulnerability to cascade events.
    Uses structural position in portfolio + historical trend + control gaps.

    Cascade Vulnerability Score (0-100):
      - broker_concentration_risk: how exposed if their broker has a portfolio shock
      - sector_corr_risk: how many peers in same sector with high risk
      - trajectory_risk: is their approval rate trending down?
      - control_gap_risk: missing critical controls
      - recency_risk: recent declines in a previously good account
    """
    subs, recs, deltas = _load()

    # Per-customer base features
    customers = (
        subs.groupby("Submission Account Name")
        .agg(
            primary_broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
            sic_name=("SIC Name", lambda x: x.mode()[0] if len(x) else ""),
            primary_product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            submission_count=("Submission Account Name", "count"),
            approval_rate=("is_bound", "mean"),
            recent_declined=("Current Status Description", lambda x: (x.tail(3) == "Declined").sum()),
            latest_status=("Current Status Description", "last"),
        )
        .reset_index()
    )
    customers = customers.merge(
        recs[["company_name", "risk_score", "recommendation", "confidence"]],
        left_on="Submission Account Name", right_on="company_name", how="left"
    ).drop(columns=["company_name"], errors="ignore")
    customers["risk_score"] = customers["risk_score"].fillna(50)

    # ── Broker concentration risk ─────────────────────────────────────────────
    broker_size = subs["National Broker Name"].value_counts()
    broker_total = len(subs)
    customers["broker_concentration"] = customers["primary_broker"].map(
        lambda b: broker_size.get(b, 0) / broker_total * 100
    )

    # ── Sector peer risk ──────────────────────────────────────────────────────
    sector_high_risk = (
        customers[customers["risk_score"] >= 65]
        .groupby("sic_name")
        .size()
        .rename("sector_high_risk_count")
    )
    customers = customers.merge(
        sector_high_risk, left_on="sic_name", right_index=True, how="left"
    )
    customers["sector_high_risk_count"] = customers["sector_high_risk_count"].fillna(0)
    sector_total = customers.groupby("sic_name").size().rename("sector_total")
    customers = customers.merge(
        sector_total, left_on="sic_name", right_index=True, how="left"
    )
    customers["sector_corr_risk"] = (
        customers["sector_high_risk_count"] / customers["sector_total"].clip(1) * 100
    )

    # ── Trajectory risk (from deltas) ─────────────────────────────────────────
    customers = customers.merge(
        deltas[["company_name", "status_degraded", "months_span"]],
        left_on="Submission Account Name", right_on="company_name", how="left"
    ).drop(columns=["company_name"], errors="ignore")
    customers["status_degraded"] = customers["status_degraded"].fillna(False)

    # ── Compute Cascade Vulnerability Score ───────────────────────────────────
    # Component weights (sum to 100)
    w_broker = 0.20   # Broker concentration
    w_sector = 0.25   # Sector correlated risk
    w_score  = 0.25   # Individual risk score
    w_recent = 0.20   # Recent declines
    w_degrad = 0.10   # Status degradation

    broker_norm = (customers["broker_concentration"] / 30).clip(0, 1) * 100
    sector_norm = (customers["sector_corr_risk"] / 80).clip(0, 1) * 100
    score_norm = customers["risk_score"]
    recent_norm = (customers["recent_declined"] / 3).clip(0, 1) * 100
    degrad_norm = customers["status_degraded"].astype(float) * 100

    customers["cascade_vulnerability_score"] = (
        w_broker * broker_norm
        + w_sector * sector_norm
        + w_score  * score_norm
        + w_recent * recent_norm
        + w_degrad * degrad_norm
    ).round(1)

    customers["vulnerability_tier"] = pd.cut(
        customers["cascade_vulnerability_score"],
        bins=[0, 33, 66, 100],
        labels=["LOW", "MEDIUM", "HIGH"],
        include_lowest=True,
    )

    top = customers.nlargest(top_n, "cascade_vulnerability_score")

    return top[[
        "Submission Account Name", "cascade_vulnerability_score", "vulnerability_tier",
        "risk_score", "recommendation", "broker_concentration", "sector_corr_risk",
        "recent_declined", "status_degraded", "primary_broker", "primary_product", "sic_name",
    ]].rename(columns={
        "Submission Account Name": "Customer",
        "cascade_vulnerability_score": "Cascade Vulnerability Score",
        "vulnerability_tier": "Tier",
        "risk_score": "Risk Score",
        "recommendation": "Recommendation",
        "broker_concentration": "Broker Concentration (%)",
        "sector_corr_risk": "Sector Peer Risk (%)",
        "recent_declined": "Recent Declines",
        "status_degraded": "Degrading",
        "primary_broker": "Broker",
        "primary_product": "Product",
        "sic_name": "Sector",
    })


# ── 5. Mitigation Actions ─────────────────────────────────────────────────────

def mitigation_actions(customer_row: pd.Series) -> List[Dict]:
    """
    Generate prioritised mitigation recommendations for a specific customer.
    """
    actions = []
    score = customer_row.get("Cascade Vulnerability Score", 50)
    broker_conc = customer_row.get("Broker Concentration (%)", 0)
    sector_risk = customer_row.get("Sector Peer Risk (%)", 0)
    recent_dec = customer_row.get("Recent Declines", 0)
    degrading = customer_row.get("Degrading", False)
    rec = customer_row.get("Recommendation", "STANDARD_UW")

    if broker_conc > 20:
        actions.append({
            "priority": "HIGH",
            "category": "Broker Concentration",
            "action": f"Flag for aggregate review — broker represents {broker_conc:.1f}% of portfolio volume. "
                      "Consider sublimit or co-insurance if broker portfolio experiences systemic shock.",
            "timeline": "Next renewal cycle",
        })

    if sector_risk > 50:
        actions.append({
            "priority": "HIGH",
            "category": "Sector Correlated Risk",
            "action": f"{sector_risk:.0f}% of sector peers are high-risk. "
                      "Request updated security posture assessment. "
                      "Validate controls specifically for sector-wide attack vectors.",
            "timeline": "Before binding",
        })

    if recent_dec >= 2:
        actions.append({
            "priority": "HIGH",
            "category": "Retention & Re-engagement",
            "action": f"{int(recent_dec)} recent declines detected. "
                      "Proactive outreach recommended: understand root cause, "
                      "offer risk improvement program, prevent client from shopping elsewhere.",
            "timeline": "Immediate (within 30 days)",
        })

    if degrading:
        actions.append({
            "priority": "MEDIUM",
            "category": "Trajectory Monitoring",
            "action": "Customer shows status degradation vs first submission. "
                      "Schedule quarterly touchpoint. Flag for enhanced monitoring in next submission.",
            "timeline": "Ongoing",
        })

    if rec == "FRESH_UW":
        actions.append({
            "priority": "MEDIUM",
            "category": "Underwriting Review",
            "action": "Fresh UW required. Request full updated application, "
                      "current financial statements, and security controls evidence.",
            "timeline": "Before quote",
        })

    if score > 70:
        actions.append({
            "priority": "HIGH",
            "category": "Early Warning Alert",
            "action": f"Cascade vulnerability score {score:.0f}/100. "
                      "This customer sits at the intersection of multiple risk vectors. "
                      "Recommend risk engineering visit and sublimit review.",
            "timeline": "Before next renewal",
        })

    if not actions:
        actions.append({
            "priority": "LOW",
            "category": "Standard Monitoring",
            "action": "No elevated cascade risk signals. Continue standard monitoring cadence.",
            "timeline": "Next renewal",
        })

    return sorted(actions, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["priority"]])
