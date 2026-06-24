"""
Dashboard data loader — reads real parsed CSVs and computes derived metrics.
All functions are cached for Streamlit performance.
"""

import pandas as pd
import streamlit as st
from pathlib import Path

DATA = Path("data/parsed")


@st.cache_data
def load_all_submissions() -> pd.DataFrame:
    df = pd.read_csv(DATA / "all_submissions.csv", low_memory=False)
    df.columns = df.columns.str.strip()
    df["Requested Coverage Effective Date"] = pd.to_datetime(
        df["Requested Coverage Effective Date"], errors="coerce"
    )
    df["Year"] = df["Requested Coverage Effective Date"].dt.year
    df["is_bound"] = df["Submission Product Bound Premium Amount"].notna() & (
        df["Submission Product Bound Premium Amount"] > 0
    )
    return df


@st.cache_data
def load_repeat_customers() -> pd.DataFrame:
    return pd.read_csv(DATA / "repeat_customers.csv")


@st.cache_data
def load_recommendations() -> pd.DataFrame:
    full = DATA / "all_recommendations.csv"
    sample = DATA / "sample_recommendations.csv"
    path = full if full.exists() else sample
    return pd.read_csv(path)


@st.cache_data
def load_broker_relationships() -> pd.DataFrame:
    return pd.read_csv(DATA / "customer_broker_relationships.csv")


@st.cache_data
def load_pdf_companies() -> set:
    path = DATA / "companies_with_pdfs.csv"
    if path.exists():
        df = pd.read_csv(path)
        col = df.columns[0]
        return set(df[col].str.strip().tolist())
    return set()


@st.cache_data
def load_pdf_fields(company_name: str) -> pd.DataFrame:
    path = DATA / "pdf_extracted_fields.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["company_name"] = df["company_name"].str.strip()
    # Cast control/policy columns to bool — CSV stores as 1.0/0.0 (float),
    # which causes heatmap and side-by-side to misread values as False
    for col in df.columns:
        if col.startswith("control_") or col.startswith("policy_"):
            df[col] = df[col].fillna(False).astype(bool)
    return df[df["company_name"] == company_name.strip()]


@st.cache_data
def load_all_deltas() -> pd.DataFrame:
    path = DATA / "all_deltas.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


@st.cache_data
def load_product_trends() -> pd.DataFrame:
    return pd.read_csv(DATA / "product_trends.csv")


@st.cache_data
def load_status_by_product() -> pd.DataFrame:
    return pd.read_csv(DATA / "status_by_product.csv")


@st.cache_data
def overview_metrics() -> dict:
    subs = load_all_submissions()
    repeats = load_repeat_customers()
    recs = load_recommendations()

    total_submissions = len(subs)
    total_repeat_customers = len(repeats)
    total_customers = subs["Submission Account Name"].nunique()
    repeat_pct = total_repeat_customers / total_customers * 100 if total_customers else 0

    # Approval rate (bound / total quoted)
    quoted = subs[subs["Current Status Description"].isin(["Quoted", "Bound", "Rated"])]
    bound = subs[subs["is_bound"]]
    approval_rate = len(bound) / len(quoted) * 100 if len(quoted) else 0

    # Avg risk score from recommendations
    avg_score = recs["risk_score"].mean() if not recs.empty else 0
    fast_track = (recs["recommendation"] == "FAST_TRACK").sum()
    fast_track_pct = fast_track / len(recs) * 100 if not recs.empty else 0

    # Top broker
    brokers = load_broker_relationships()
    top_broker = brokers.groupby("National Broker Name")["count"].sum().idxmax() if not brokers.empty else "N/A"

    # Top product
    top_product = (
        subs["Product Name"].value_counts().idxmax()
        if "Product Name" in subs.columns else "N/A"
    )

    return {
        "total_submissions": total_submissions,
        "total_repeat_customers": total_repeat_customers,
        "total_customers": total_customers,
        "repeat_pct": round(repeat_pct, 1),
        "approval_rate": round(approval_rate, 1),
        "avg_risk_score": round(avg_score, 1),
        "fast_track_count": int(fast_track),
        "fast_track_pct": round(fast_track_pct, 1),
        "top_broker": top_broker,
        "top_product": top_product,
    }


@st.cache_data
def submission_volume_by_year() -> pd.DataFrame:
    subs = load_all_submissions()
    return subs.groupby("Year").size().reset_index(name="Submissions").dropna()


@st.cache_data
def status_distribution() -> pd.DataFrame:
    subs = load_all_submissions()
    df = subs["Current Status Description"].value_counts().reset_index().head(8)
    df.columns = ["Status", "Count"]
    return df


@st.cache_data
def top_products(n: int = 10) -> pd.DataFrame:
    subs = load_all_submissions()
    df = subs["Product Name"].value_counts().head(n).reset_index()
    df.columns = ["Product", "Count"]
    return df


@st.cache_data
def broker_performance(n: int = 15) -> pd.DataFrame:
    subs = load_all_submissions()
    brokers = (
        subs.groupby("National Broker Name")
        .agg(
            submissions=("Submission Account Name", "count"),
            bound=("is_bound", "sum"),
            customers=("Submission Account Name", "nunique"),
        )
        .reset_index()
    )
    brokers["approval_rate"] = (brokers["bound"] / brokers["submissions"] * 100).round(1)
    return brokers.sort_values("submissions", ascending=False).head(n)


@st.cache_data
def prioritization_queue(limit: int = 500) -> pd.DataFrame:
    subs = load_all_submissions()
    repeats = load_repeat_customers()
    recs = load_recommendations()

    # Start from repeat customers
    df = repeats.merge(
        subs.groupby("Submission Account Name").agg(
            latest_date=("Requested Coverage Effective Date", "max"),
            product=("Product Name", lambda x: x.mode()[0] if len(x) else ""),
            broker=("National Broker Name", lambda x: x.mode()[0] if len(x) else ""),
            status=("Current Status Description", "last"),
            premium=("Quoted Premium Amount", "sum"),
        ).reset_index(),
        on="Submission Account Name",
        how="left",
    )

    # Merge recommendations where available
    df = df.merge(
        recs[["company_name", "risk_score", "recommendation", "confidence"]],
        left_on="Submission Account Name",
        right_on="company_name",
        how="left",
    )
    df.drop(columns=["company_name"], errors="ignore", inplace=True)

    # Fill missing scores with neutral value
    df["risk_score"] = df["risk_score"].fillna(50)
    df["recommendation"] = df["recommendation"].fillna("STANDARD_UW")
    df["confidence"] = df["confidence"].fillna(0.75)

    # Return full dataset — sorting/filtering done in the dashboard
    df["latest_date"] = df["latest_date"].dt.strftime("%Y-%m-%d")
    return df


@st.cache_data
def customer_history(customer_name: str) -> pd.DataFrame:
    subs = load_all_submissions()
    mask = subs["Submission Account Name"] == customer_name
    history = subs[mask].sort_values("Requested Coverage Effective Date")
    history["date_str"] = history["Requested Coverage Effective Date"].dt.strftime("%Y-%m-%d")
    return history


@st.cache_data
def repeat_customer_list(n: int = 100) -> list:
    repeats = load_repeat_customers()
    return repeats["Submission Account Name"].head(n).tolist()


# ── Pre-computed KG analytics (fast CSV reads) ─────────────────────────────────

def _load_kg(filename: str) -> pd.DataFrame:
    """Load a pre-computed KG CSV if it exists, else return empty DataFrame."""
    path = DATA / filename
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


@st.cache_data
def kg_clusters() -> pd.DataFrame:
    return _load_kg("kg_clusters.csv")


@st.cache_data
def kg_clusters_summary() -> pd.DataFrame:
    return _load_kg("kg_clusters_summary.csv")


@st.cache_data
def kg_emerging_risks() -> pd.DataFrame:
    return _load_kg("kg_emerging_risks.csv")


@st.cache_data
def kg_whitespace() -> pd.DataFrame:
    return _load_kg("kg_whitespace.csv")


@st.cache_data
def kg_retention_risk() -> pd.DataFrame:
    return _load_kg("kg_retention_risk.csv")


@st.cache_data
def kg_reapplication() -> pd.DataFrame:
    return _load_kg("kg_reapplication.csv")


@st.cache_data
def kg_cascade_vulnerable() -> pd.DataFrame:
    return _load_kg("kg_cascade_vulnerable.csv")


@st.cache_data
def kg_leading_indicators() -> pd.DataFrame:
    return _load_kg("kg_leading_indicators.csv")


@st.cache_data
def kg_concentration() -> pd.DataFrame:
    return _load_kg("kg_concentration.csv")


def kg_precomputed_available() -> bool:
    """Returns True if KG CSVs have been pre-computed."""
    return (DATA / "kg_clusters_summary.csv").exists()


def kg_graph_available() -> bool:
    """Returns True if NetworkX graph has been built."""
    return (DATA / "knowledge_graph.graphml").exists()


@st.cache_resource
def load_kg_graph():
    """Load the pre-built NetworkX graph. Prefers pickle (fast) over GraphML (slow XML)."""
    import networkx as nx, pickle
    pkl = DATA / "knowledge_graph.pkl"
    graphml = DATA / "knowledge_graph.graphml"
    if pkl.exists():
        with open(pkl, "rb") as f:
            return pickle.load(f)
    if graphml.exists():
        return nx.read_graphml(str(graphml))
    return None


@st.cache_data
def kg_graph_metrics() -> pd.DataFrame:
    return _load_kg("graph_metrics.csv")


@st.cache_data
def kg_graph_communities() -> pd.DataFrame:
    return _load_kg("graph_communities.csv")


@st.cache_data
def kg_broker_performance() -> pd.DataFrame:
    """Pre-computed broker performance — falls back to live."""
    df = _load_kg("kg_broker_performance.csv")
    if not df.empty:
        return df
    return broker_performance(30)  # live fallback


@st.cache_data
def recommendation_accuracy() -> pd.DataFrame:
    """
    Validate AI recommendations against actual bind outcomes.
    For each recommendation tier, compute: how many customers were bound vs not.
    Answers the jury question: 'does the model actually work?'
    """
    subs = load_all_submissions()
    recs = load_recommendations()
    if subs.empty or recs.empty:
        return pd.DataFrame()

    latest = (
        subs.sort_values("Requested Coverage Effective Date")
        .groupby("Submission Account Name")
        .last()
        .reset_index()[["Submission Account Name", "is_bound"]]
    )
    merged = recs[["company_name", "recommendation", "risk_score"]].merge(
        latest, left_on="company_name", right_on="Submission Account Name", how="inner"
    )
    result = (
        merged.groupby("recommendation")
        .agg(
            customers=("company_name", "count"),
            bound=("is_bound", "sum"),
            avg_score=("risk_score", "mean"),
        )
        .reset_index()
    )
    result["bind_rate"] = (result["bound"] / result["customers"] * 100).round(1)
    result["avg_score"] = result["avg_score"].round(1)
    order = {"FAST_TRACK": 0, "STANDARD_UW": 1, "FRESH_UW": 2}
    result["_order"] = result["recommendation"].map(order)
    return result.sort_values("_order").drop(columns="_order")


@st.cache_data
def bias_analysis() -> dict:
    """
    Score distribution by broker and SIC — EU AI Act Art.10 data governance evidence.
    Shows whether the scoring model treats different groups equitably.
    """
    recs = load_recommendations()
    subs = load_all_submissions()
    if recs.empty or subs.empty:
        return {}

    latest = (subs.sort_values("Requested Coverage Effective Date")
              .groupby("Submission Account Name").last().reset_index())
    merged = recs.merge(
        latest[["Submission Account Name", "National Broker Name", "SIC Name"]],
        left_on="company_name", right_on="Submission Account Name", how="left"
    )

    by_broker = (merged.groupby("National Broker Name")["risk_score"]
                 .agg(mean="mean", count="count").reset_index()
                 .rename(columns={"mean": "avg_score", "National Broker Name": "broker"})
                 .nlargest(12, "count"))
    by_broker["avg_score"] = by_broker["avg_score"].round(1)

    by_sic = (merged.dropna(subset=["SIC Name"])
              .groupby("SIC Name")["risk_score"]
              .agg(mean="mean", count="count").reset_index()
              .rename(columns={"mean": "avg_score", "SIC Name": "sic"})
              .nlargest(10, "count"))
    by_sic["avg_score"] = by_sic["avg_score"].round(1)

    return {"by_broker": by_broker, "by_sic": by_sic,
            "total": len(merged), "mean": round(merged["risk_score"].mean(), 1),
            "std": round(merged["risk_score"].std(), 1)}
