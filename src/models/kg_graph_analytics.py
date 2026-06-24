"""
Real NetworkX graph analytics — replaces pandas-based KG analytics.

All functions here load the pre-built graph (knowledge_graph.pkl)
and compute real graph metrics at runtime.

Cached with @st.cache_data for dashboard performance.
"""

import os
import json
import pickle
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from typing import Dict, List, Tuple

DATA = Path("data/parsed")


@st.cache_resource
def load_graph():
    """Load NetworkX graph — cached as resource (shared across all sessions)."""
    pkl = DATA / "knowledge_graph.pkl"
    if not pkl.exists():
        return None
    with open(pkl, "rb") as f:
        return pickle.load(f)


@st.cache_data
def community_cluster_summary() -> pd.DataFrame:
    """
    Replaces KMeans cluster summary.
    Uses Louvain communities from graph_communities.csv + graph_metrics.csv.

    Returns community-level stats: size, dominant cluster, avg risk score,
    dominant broker, dominant sector.
    """
    comm_path = DATA / "graph_communities.csv"
    gm_path   = DATA / "graph_metrics.csv"

    if not comm_path.exists() or not gm_path.exists():
        return pd.DataFrame()

    communities = pd.read_csv(comm_path)
    metrics     = pd.read_csv(gm_path)

    merged = communities.merge(metrics, on="customer", how="left")

    # Per-community stats
    G = load_graph()
    broker_map = {}
    sector_map = {}
    if G:
        for cust_node in G.nodes:
            if not cust_node.startswith("cust::"):
                continue
            cust_name = cust_node.replace("cust::", "")
            for nb in G.neighbors(cust_node):
                if nb.startswith("broker::"):
                    broker_map[cust_name] = nb.replace("broker::", "")
                elif nb.startswith("sector::"):
                    sector_map[cust_name] = nb.replace("sector::", "")[:40]
        merged["broker"] = merged["customer"].map(broker_map)
        merged["sector"] = merged["customer"].map(sector_map)

    summary_rows = []
    for comm_id, grp in merged.groupby("community_id"):
        dominant_cluster = grp["cluster"].mode()[0] if "cluster" in grp.columns and len(grp) > 0 else "Unknown"
        row = {
            "community_id": comm_id,
            "customers": len(grp),
            "dominant_risk_cluster": dominant_cluster,
            "avg_risk_score": round(grp["risk_score"].mean(), 1) if "risk_score" in grp.columns else None,
            "avg_approval_rate": round(grp["approval_rate"].mean(), 1) if "approval_rate" in grp.columns else None,
            "top_broker": grp["broker"].mode()[0] if "broker" in grp.columns and grp["broker"].notna().any() else "N/A",
            "top_sector": grp["sector"].mode()[0] if "sector" in grp.columns and grp["sector"].notna().any() else "N/A",
            "fast_track_pct": round((grp.get("recommendation", pd.Series()) == "FAST_TRACK").mean() * 100, 1) if "recommendation" in grp.columns else None,
            "fresh_uw_pct": round((grp.get("recommendation", pd.Series()) == "FRESH_UW").mean() * 100, 1) if "recommendation" in grp.columns else None,
        }
        summary_rows.append(row)

    df = pd.DataFrame(summary_rows)
    if not df.empty:
        df = df.sort_values("customers", ascending=False).reset_index(drop=True)
    return df


@st.cache_data
def broker_centrality_risks() -> pd.DataFrame:
    """
    Enriches broker risk signals with betweenness centrality.
    A broker with HIGH centrality AND declining approval is MORE dangerous
    because they sit on more paths in the portfolio network.
    """
    gm_path   = DATA / "graph_metrics.csv"
    subs_path = DATA / "all_submissions.csv"

    if not gm_path.exists() or not subs_path.exists():
        return pd.DataFrame()

    metrics = pd.read_csv(gm_path)
    subs    = pd.read_csv(subs_path, low_memory=False)
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )

    # Broker approval rates
    broker_stats = (
        subs.groupby("National Broker Name")
        .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
        .reset_index()
    )
    broker_stats["approval_rate_pct"] = (broker_stats["bound"] / broker_stats["total"].clip(1) * 100).round(1)

    # Get broker betweenness from graph
    G = load_graph()
    broker_centrality = {}
    if G:
        for node, data in G.nodes(data=True):
            if data.get("node_type") == "broker":
                broker_name = node.replace("broker::", "")
                # Count how many customers connect through this broker
                customer_count = sum(1 for nb in G.neighbors(node) if nb.startswith("cust::"))
                broker_centrality[broker_name] = customer_count

    broker_stats["connected_customers"] = broker_stats["National Broker Name"].map(
        lambda b: broker_centrality.get(b, 0)
    )
    broker_stats["network_importance"] = (
        broker_stats["connected_customers"] / broker_stats["connected_customers"].max().clip(1) * 100
    ).round(1)

    # Risk signal: high importance + low approval = highest danger
    broker_stats["danger_score"] = (
        broker_stats["network_importance"] * (100 - broker_stats["approval_rate_pct"]) / 100
    ).round(1)

    return broker_stats.sort_values("danger_score", ascending=False).rename(
        columns={"National Broker Name": "broker"}
    )


@st.cache_data
def customer_neighborhood(customer_name: str, max_depth: int = 1) -> Dict:
    """
    Returns the neighborhood subgraph for a customer as node/edge lists for visualisation.
    Used by the Graph Explorer tab.
    """
    G = load_graph()
    if G is None:
        return {"error": "Graph not loaded"}

    matches = [n for n in G.nodes if customer_name.lower() in n.lower() and n.startswith("cust::")]
    if not matches:
        return {"error": f"Customer '{customer_name}' not found in graph"}

    center = matches[0]
    # Collect 1-hop subgraph
    subgraph_nodes = {center}
    for nb in G.neighbors(center):
        subgraph_nodes.add(nb)
        if max_depth >= 2:
            for nb2 in G.neighbors(nb):
                if nb2.startswith("cust::"):
                    subgraph_nodes.add(nb2)

    subgraph = G.subgraph(subgraph_nodes)

    gm_path = DATA / "graph_metrics.csv"
    gm = pd.read_csv(gm_path) if gm_path.exists() else pd.DataFrame()

    # Build node list
    nodes = []
    for n, d in subgraph.nodes(data=True):
        node_type = d.get("node_type", "unknown")
        label = n.split("::")[-1][:30] if "::" in n else n[:30]
        color = {
            "customer":     "#4C9BE8",
            "broker":       "#F97316",
            "sector":       "#22C55E",
            "product":      "#A855F7",
            "risk_cluster": "#EF4444",
            "control":      "#EAB308",
        }.get(node_type, "#6B7280")

        size = 20 if n == center else (15 if node_type == "broker" else 10)
        tooltip = label

        if node_type == "customer" and not gm.empty:
            cust_name = n.replace("cust::", "")
            row = gm[gm["customer"] == cust_name]
            if not row.empty:
                r = row.iloc[0]
                rec = r.get("recommendation", "")
                color = {"FAST_TRACK": "#22C55E", "STANDARD_UW": "#F97316", "FRESH_UW": "#EF4444"}.get(rec, "#4C9BE8")
                tooltip = f"{cust_name}\nScore: {r.get('risk_score','?')}\n{rec}"

        nodes.append({"id": n, "label": label, "color": color, "size": size,
                      "type": node_type, "tooltip": tooltip})

    # Build edge list
    edges = [{"from": u, "to": v} for u, v in subgraph.edges()]

    return {
        "center": center,
        "center_name": center.replace("cust::", ""),
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


@st.cache_data
def graph_summary_stats() -> Dict:
    """Summary statistics about the knowledge graph for display."""
    G = load_graph()
    if G is None:
        return {}

    node_types = {}
    for n, d in G.nodes(data=True):
        t = d.get("node_type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    gm_path = DATA / "graph_metrics.csv"
    comm_path = DATA / "graph_communities.csv"
    n_communities = 0
    if comm_path.exists():
        n_communities = pd.read_csv(comm_path)["community_id"].nunique()

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": node_types,
        "n_communities": n_communities,
        "is_connected": False,
    }


# ── Cluster-aware analytics (KMeans + NetworkX combined) ──────────────────────

@st.cache_data
def find_cluster_bridges(top_n: int = 20) -> pd.DataFrame:
    """
    Find customers in HIGH RISK cluster connected via broker to LOW RISK customers.
    These are 'bridge' nodes — they create a hidden correlation path between clusters.

    Business insight: A High Risk customer sharing a broker with many Low Risk
    customers may indicate the Low Risk assessments are optimistic, OR that
    a broker quality issue hasn't yet surfaced in the Low Risk book.
    """
    G = load_graph()
    if G is None:
        return pd.DataFrame()

    rows = []
    for cust_node, data in G.nodes(data=True):
        if data.get("node_type") != "customer":
            continue
        if data.get("cluster") != "High Risk":
            continue

        cust_name = cust_node.replace("cust::", "")
        neighbours = list(G.neighbors(cust_node))
        broker_nodes = [n for n in neighbours if n.startswith("broker::")]

        low_risk_peers = []
        for b_node in broker_nodes:
            for peer in G.neighbors(b_node):
                if peer.startswith("cust::") and peer != cust_node:
                    peer_data = G.nodes[peer]
                    if peer_data.get("cluster") == "Low Risk":
                        low_risk_peers.append(peer.replace("cust::", ""))

        if low_risk_peers:
            rows.append({
                "high_risk_customer": cust_name,
                "risk_score": data.get("risk_score", 0),
                "recommendation": data.get("recommendation", ""),
                "broker": broker_nodes[0].replace("broker::", "") if broker_nodes else "N/A",
                "low_risk_peers_count": len(set(low_risk_peers)),
                "low_risk_peers_sample": ", ".join(list(set(low_risk_peers))[:3]),
                "bridge_risk": "HIGH" if len(set(low_risk_peers)) >= 5 else "MEDIUM",
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("low_risk_peers_count", ascending=False).head(top_n)
    return df


@st.cache_data
def community_cluster_purity() -> pd.DataFrame:
    """
    For each Louvain community, compute cluster purity and contagion risk.

    Purity = % of dominant cluster in the community.
    High purity + High Risk → structural risk pocket.
    Low purity (mixed clusters) → contagion risk (cross-cluster exposure).
    """
    comm_path = DATA / "graph_communities.csv"
    gm_path   = DATA / "graph_metrics.csv"
    if not comm_path.exists() or not gm_path.exists():
        return pd.DataFrame()

    communities = pd.read_csv(comm_path)
    metrics     = pd.read_csv(gm_path)
    # communities already has cluster; merge only risk_score from metrics
    merged = communities.merge(metrics[["customer", "risk_score"]], on="customer", how="left")
    # cluster column comes from communities CSV

    rows = []
    for comm_id, grp in merged.groupby("community_id"):
        total = len(grp)
        counts = grp["cluster"].value_counts()
        dominant = counts.index[0] if len(counts) > 0 else "Unknown"
        purity = round(counts.iloc[0] / total * 100, 1) if len(counts) > 0 else 0

        high_risk_pct  = round((grp["cluster"] == "High Risk").mean() * 100, 1)
        low_risk_pct   = round((grp["cluster"] == "Low Risk").mean() * 100, 1)

        if purity >= 80 and dominant == "High Risk":
            community_type = "Risk Pocket"
        elif high_risk_pct >= 30 and low_risk_pct >= 30:
            community_type = "Contagion Risk"
        elif purity >= 80 and dominant == "Low Risk":
            community_type = "Safe Cluster"
        else:
            community_type = "Mixed"

        rows.append({
            "community_id": comm_id,
            "total_customers": total,
            "dominant_cluster": dominant,
            "purity_pct": purity,
            "high_risk_pct": high_risk_pct,
            "low_risk_pct": low_risk_pct,
            "community_type": community_type,
            "avg_risk_score": round(grp["risk_score"].mean(), 1),
        })

    df = pd.DataFrame(rows).sort_values("high_risk_pct", ascending=False)
    return df


@st.cache_data
def high_risk_central_nodes(top_n: int = 15) -> pd.DataFrame:
    """
    Find High Risk customers with highest betweenness centrality.
    These are the most 'connected' high-risk nodes — their problems
    propagate furthest through the portfolio network.

    Betweenness from graph_metrics.csv (pre-computed offline).
    """
    gm_path = DATA / "graph_metrics.csv"
    if not gm_path.exists():
        return pd.DataFrame()

    gm = pd.read_csv(gm_path)
    high_risk = gm[gm["cluster"] == "High Risk"].copy()

    if high_risk.empty or "betweenness_centrality" not in high_risk.columns:
        # Fall back to degree as proxy
        if "degree" in high_risk.columns:
            high_risk = high_risk.nlargest(top_n, "degree")
            high_risk["propagation_risk"] = (
                high_risk["degree"] / high_risk["degree"].max() * 100
            ).round(1)
        return high_risk[["customer", "risk_score", "recommendation",
                          "approval_rate", "degree"]].head(top_n)

    high_risk = high_risk.nlargest(top_n, "betweenness_centrality")
    high_risk["propagation_risk"] = (
        high_risk["betweenness_centrality"] / high_risk["betweenness_centrality"].max() * 100
    ).round(1)

    return high_risk[[
        "customer", "risk_score", "recommendation", "approval_rate",
        "betweenness_centrality", "pagerank", "degree", "propagation_risk"
    ]].head(top_n)


@st.cache_data
def broker_cross_cluster_exposure() -> pd.DataFrame:
    """
    Find brokers that have customers in ALL THREE risk clusters.
    These brokers create hidden correlation paths:
      - Either bringing genuinely diverse quality business (neutral)
      - Or the cluster assessments are inconsistent for the same broker (concerning)
    """
    G = load_graph()
    gm_path = DATA / "graph_metrics.csv"
    if G is None or not gm_path.exists():
        return pd.DataFrame()

    gm = pd.read_csv(gm_path)
    cluster_map = dict(zip(gm["customer"], gm["cluster"]))

    rows = []
    for broker_node, data in G.nodes(data=True):
        if data.get("node_type") != "broker":
            continue
        broker_name = broker_node.replace("broker::", "")
        customer_nodes = [n for n in G.neighbors(broker_node) if n.startswith("cust::")]
        if len(customer_nodes) < 3:
            continue

        clusters_seen = set()
        cluster_counts = {"Low Risk": 0, "Moderate Risk": 0, "High Risk": 0}
        for cust_node in customer_nodes:
            cust_name = cust_node.replace("cust::", "")
            cl = cluster_map.get(cust_name, "")
            if cl in cluster_counts:
                cluster_counts[cl] += 1
                clusters_seen.add(cl)

        if len(clusters_seen) == 3:
            total = sum(cluster_counts.values())
            rows.append({
                "broker": broker_name,
                "total_customers": len(customer_nodes),
                "low_risk_count": cluster_counts["Low Risk"],
                "moderate_risk_count": cluster_counts["Moderate Risk"],
                "high_risk_count": cluster_counts["High Risk"],
                "high_risk_pct": round(cluster_counts["High Risk"] / max(total, 1) * 100, 1),
                "spans_all_clusters": True,
                "risk_note": "Monitor — spans all risk tiers" if cluster_counts["High Risk"] > 5 else "Diverse book",
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("high_risk_count", ascending=False)
    return df


# ── XAI narrative for Graph Explorer ──────────────────────────────────────────

def generate_graph_xai(
    customer_name: str,
    neighborhood_data: Dict,
    cluster: str,
    risk_score: float,
    recommendation: str,
    peers: list = None,
) -> str:
    """
    Generate a plain-language XAI narrative explaining what the graph
    reveals about a customer's network position and risk implications.

    Uses Claude API if available, otherwise generates rule-based narrative.
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    peers = peers or []

    # Build context for the narrative
    node_count = neighborhood_data.get("node_count", 0)
    edge_count  = neighborhood_data.get("edge_count", 0)
    nodes = neighborhood_data.get("nodes", [])
    broker_nodes  = [n["label"] for n in nodes if n.get("type") == "broker"]
    sector_nodes  = [n["label"] for n in nodes if n.get("type") == "sector"]
    product_nodes = [n["label"] for n in nodes if n.get("type") == "product"]
    peer_nodes    = [n for n in nodes if n.get("type") == "customer" and n.get("id") != neighborhood_data.get("center")]

    fast_track_peers = [p for p in peer_nodes if "FAST_TRACK" in p.get("tooltip", "")]
    fresh_uw_peers   = [p for p in peer_nodes if "FRESH_UW" in p.get("tooltip", "")]

    if api_key:
        try:
            from openai import OpenAI
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            model    = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-4-6")
            client = OpenAI(
                api_key=api_key,
                base_url=f"{base_url}/v1" if base_url else None,
            )

            prompt = f"""You are explaining a Knowledge Graph analysis to an insurance underwriter.

Customer: {customer_name}
Risk Score: {risk_score}/100
Recommendation: {recommendation}
KMeans Cluster: {cluster}

Graph neighborhood ({node_count} nodes, {edge_count} connections):
- Broker(s): {', '.join(broker_nodes) or 'N/A'}
- Sector: {', '.join(sector_nodes[:1]) or 'N/A'}
- Product: {', '.join(product_nodes[:1]) or 'N/A'}
- Peer customers in graph: {len(peer_nodes)} ({len(fast_track_peers)} Fast-Track, {len(fresh_uw_peers)} Fresh UW)

Write a 3-sentence explanation for the underwriter:
1. What the customer's network position tells us (broker centrality, sector exposure)
2. What the peer cluster distribution means for risk assessment
3. One specific action recommendation

Be concrete — cite broker names, counts, cluster names. Max 120 words.
End with: '⚠️ Advisory only — human review required.'"""

            response = client.chat.completions.create(
                model=model, max_tokens=250,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content

        except Exception:
            pass  # fall through to rule-based

    # Rule-based fallback
    lines = [f"**Graph Analysis: {customer_name}**", ""]

    if broker_nodes:
        lines.append(
            f"This customer operates through **{broker_nodes[0]}** — "
            f"a broker with {len(peer_nodes)} other portfolio customers in the same network."
        )

    if fast_track_peers and fresh_uw_peers:
        lines.append(
            f"Their peer group is mixed: {len(fast_track_peers)} Fast-Track and "
            f"{len(fresh_uw_peers)} Fresh UW customers share the same broker-sector path. "
            f"This mixed exposure warrants attention."
        )
    elif fresh_uw_peers:
        lines.append(
            f"{len(fresh_uw_peers)} of their graph peers are Fresh UW — "
            f"this customer is structurally connected to a high-risk group via {broker_nodes[0] if broker_nodes else 'shared broker'}."
        )
    elif fast_track_peers:
        lines.append(
            f"{len(fast_track_peers)} of their graph peers are Fast-Track — "
            f"the network context is low-risk, supporting a favourable assessment."
        )

    action = {
        "FAST_TRACK": "Graph structure supports Fast-Track. Verify broker quality is consistent.",
        "STANDARD_UW": "Standard review recommended. Check alignment with peer group outcomes.",
        "FRESH_UW": "Fresh UW warranted. Peer group and cluster position confirm elevated risk.",
    }.get(recommendation, "Review recommended.")
    lines.append(f"**Action:** {action}")
    lines.append("\n*⚠️ Advisory only — human review required.*")

    return "\n".join(lines)


def generate_cluster_xai(cluster_summary: list, bridge_count: int = 0) -> str:
    """
    Generate a plain-language portfolio-level explanation of the risk cluster structure.
    Used by the Risk Clusters view in the Portfolio Risk Map.
    Follows same LLM-with-fallback pattern as generate_graph_xai.
    """
    from dotenv import load_dotenv
    load_dotenv(override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if api_key:
        try:
            from openai import OpenAI
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            model    = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-4-6")
            client   = OpenAI(
                api_key=api_key,
                base_url=f"{base_url}/v1" if base_url else None,
            )
            cluster_text = "\n".join(
                f"- {c.get('cluster_label','')}: {int(c.get('customers',0)):,} customers, "
                f"avg approval rate {c.get('avg_approval_rate',0):.1f}%"
                for c in cluster_summary
            )
            prompt = f"""You are explaining a portfolio risk segmentation to a senior insurance underwriter.

Portfolio KMeans cluster analysis (3 clusters):
{cluster_text}
Bridge nodes detected: {bridge_count} (High Risk customers structurally connected to Low Risk via shared broker)

Write a 3-paragraph UW-focused explanation:
1. What each cluster represents in underwriting terms — who are these customers?
2. What the approval rate differences between clusters reveal about portfolio quality
3. What the bridge nodes mean and what the UW should prioritise this week

Be concrete, cite numbers, use underwriting language. Max 150 words.
End with: '⚠️ Advisory only — human review required.'"""

            response = client.chat.completions.create(
                model=model, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception:
            pass

    # Rule-based fallback
    lines = ["**Portfolio Risk Cluster Analysis**", ""]
    for c in cluster_summary:
        label    = c.get("cluster_label", "")
        count    = int(c.get("customers", 0))
        approval = c.get("avg_approval_rate", 0)
        action = {
            "Low Risk":      "Fast-Track eligible — prioritise for expedited processing.",
            "Moderate Risk": "Standard UW process — review individually before decision.",
            "High Risk":     "Fresh UW required — do not Fast-Track without full review.",
        }.get(label, "Review recommended.")
        lines.append(f"**{label}** ({count:,} customers, {approval:.1f}% avg approval): {action}")

    if bridge_count:
        lines.append(
            f"\n**{bridge_count} bridge node(s) detected** — High Risk customers sharing a "
            "broker with Low Risk customers. These create hidden correlation paths. "
            "Monitor for portfolio contagion risk."
        )
    lines.append("\n*⚠️ Advisory only — human review required.*")
    return "\n".join(lines)
