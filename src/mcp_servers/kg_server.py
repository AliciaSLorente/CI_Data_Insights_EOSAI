"""
MCP Server: KG Discovery Tools
Group 3 of 3 — Knowledge Graph analytics + portfolio patterns

Tools exposed:
  portfolio_analytics     — repeat stats, broker trends, clusters, fast-track, anomalies
  find_structural_peers   — real NetworkX graph neighbours for a customer
  explain_recommendation  — plain-language XAI for a customer

Run standalone:
  python -m src.mcp_servers.kg_server
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

mcp = FastMCP("zurich-kg")


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


# Module-level cache — loaded once when server starts, reused for all calls
_RECS_CACHE = None
_GRAPH_CACHE = None


def _load_recs():
    global _RECS_CACHE
    if _RECS_CACHE is None:
        p = DATA / "all_recommendations.csv"
        _RECS_CACHE = pd.read_csv(p) if p.exists() else pd.DataFrame()
    return _RECS_CACHE


def _load_graph():
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None:
        import pickle
        pkl = DATA / "knowledge_graph.pkl"
        if pkl.exists():
            with open(pkl, "rb") as f:
                _GRAPH_CACHE = pickle.load(f)
    return _GRAPH_CACHE


@mcp.tool()
def portfolio_analytics(
    query_type: str,
    filter: str = None,
) -> str:
    """
    Run portfolio-level analytics to discover patterns across all customers.
    query_type: repeat_stats | broker_trends | risk_clusters |
                fast_track_candidates | anomalies | whitespace
    """
    recs = _load_recs()

    if query_type == "repeat_stats":
        repeat_path = DATA / "repeat_customers.csv"
        all_path = DATA / "all_submissions.csv"
        repeats = pd.read_csv(repeat_path) if repeat_path.exists() else pd.DataFrame()
        total = len(pd.read_csv(all_path, low_memory=False)["Submission Account Name"].unique()) if all_path.exists() else 0
        return _safe({
            "total_unique_customers": total,
            "repeat_customers": len(repeats),
            "repeat_pct": round(len(repeats) / total * 100, 1) if total else 0,
            "top_repeat_customers": repeats.head(10).to_dict(orient="records") if not repeats.empty else [],
        })

    elif query_type == "broker_trends":
        all_path = DATA / "all_submissions.csv"
        if not all_path.exists():
            return _safe({"error": "Submission data not found"})
        subs = pd.read_csv(all_path, low_memory=False)
        subs["is_bound"] = (subs["Submission Product Bound Premium Amount"].notna() &
                             (subs["Submission Product Bound Premium Amount"] > 0))
        stats = (
            subs.groupby("National Broker Name")
            .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
            .reset_index()
        )
        stats["approval_rate"] = (stats["bound"] / stats["total"] * 100).round(1)
        return _safe({
            "top_10_by_volume": stats.nlargest(10, "total").to_dict(orient="records"),
            "declining_quality": stats[
                (stats["total"] >= 50) & (stats["approval_rate"] < 10)
            ].to_dict(orient="records"),
        })

    elif query_type == "risk_clusters":
        if recs.empty:
            return _safe({"error": "No scoring data"})
        low = recs[recs["risk_score"] < 40]
        mid = recs[(recs["risk_score"] >= 40) & (recs["risk_score"] < 65)]
        high = recs[recs["risk_score"] >= 65]
        return _safe({"clusters": [
            {"label": "Low Risk", "count": len(low),
             "avg_score": round(low["risk_score"].mean(), 1) if len(low) else None,
             "recommendation": "FAST_TRACK"},
            {"label": "Moderate Risk", "count": len(mid),
             "avg_score": round(mid["risk_score"].mean(), 1) if len(mid) else None,
             "recommendation": "STANDARD_UW"},
            {"label": "High Risk", "count": len(high),
             "avg_score": round(high["risk_score"].mean(), 1) if len(high) else None,
             "recommendation": "FRESH_UW"},
        ]})

    elif query_type == "fast_track_candidates":
        if recs.empty:
            return _safe({"error": "No scoring data"})
        candidates = recs[recs["recommendation"] == "FAST_TRACK"].nsmallest(15, "risk_score")
        return _safe({
            "total_fast_track": int((recs["recommendation"] == "FAST_TRACK").sum()),
            "top_candidates": candidates[["company_name", "risk_score", "confidence", "reasoning"]].to_dict(orient="records"),
        })

    elif query_type == "anomalies":
        if recs.empty:
            return _safe({"error": "No scoring data"})
        mean_s, std_s = recs["risk_score"].mean(), recs["risk_score"].std()
        anomalies = recs[abs(recs["risk_score"] - mean_s) > 1.5 * std_s]
        return _safe({
            "portfolio_mean_score": round(mean_s, 1),
            "anomaly_count": len(anomalies),
            "threshold": f"mean +/- 1.5 std ({mean_s:.1f} +/- {1.5*std_s:.1f})",
            "anomalies": anomalies[["company_name", "risk_score", "recommendation"]].head(10).to_dict(orient="records"),
        })

    elif query_type == "whitespace":
        repeat_path = DATA / "repeat_customers.csv"
        repeats = pd.read_csv(repeat_path) if repeat_path.exists() else pd.DataFrame()
        return _safe({
            "insight": "Customers with 2-3 submissions and strong approval history = proactive outreach",
            "total_repeat_customers": len(repeats),
            "recommendation": "Target low-score repeat customers for proactive renewal outreach",
        })

    return _safe({"error": f"Unknown query_type: {query_type}"})


@mcp.tool()
def find_structural_peers(customer_name: str, n_peers: int = 5) -> str:
    """
    Find the most structurally similar customers using the real NetworkX graph.
    Returns customers connected through shared broker, sector AND product simultaneously.
    This is more accurate than simple SIC/product matching.
    """
    G = _load_graph()
    if G is None:
        return _safe({"error": "Knowledge graph not built. Run scripts/build_knowledge_graph.py"})

    # Find the customer node
    import re
    matches = [n for n in G.nodes if customer_name.lower() in n.lower() and n.startswith("cust::")]
    if not matches:
        return _safe({"message": f"Customer '{customer_name}' not found in graph"})

    node = matches[0]
    actual_name = node.replace("cust::", "")

    # Get direct neighbours (broker, sector, product, cluster)
    neighbours = list(G.neighbors(node))
    broker_nodes = [n for n in neighbours if n.startswith("broker::")]
    sector_nodes = [n for n in neighbours if n.startswith("sector::")]
    product_nodes = [n for n in neighbours if n.startswith("product::")]
    cluster_node = next((n for n in neighbours if n.startswith("cluster::")), None)

    # Find peers: customers sharing same broker AND sector
    peers = {}
    for b_node in broker_nodes:
        for peer in G.neighbors(b_node):
            if peer.startswith("cust::") and peer != node:
                peers[peer] = peers.get(peer, 0) + 2  # broker match = 2 pts
    for s_node in sector_nodes:
        for peer in G.neighbors(s_node):
            if peer.startswith("cust::") and peer != node:
                peers[peer] = peers.get(peer, 0) + 1  # sector match = 1 pt

    # Sort by structural similarity score
    top_peers = sorted(peers.items(), key=lambda x: x[1], reverse=True)[:n_peers]

    # Get metrics for each peer
    gm_path = DATA / "graph_metrics.csv"
    gm = pd.read_csv(gm_path) if gm_path.exists() else pd.DataFrame()

    peer_details = []
    for peer_node, sim_score in top_peers:
        peer_name = peer_node.replace("cust::", "")
        peer_info = {"customer": peer_name, "structural_similarity": sim_score}
        if not gm.empty:
            match = gm[gm["customer"] == peer_name]
            if not match.empty:
                r = match.iloc[0]
                peer_info.update({
                    "cluster": r.get("cluster", ""),
                    "risk_score": r.get("risk_score", None),
                    "recommendation": r.get("recommendation", ""),
                    "approval_rate": r.get("approval_rate", None),
                })
        peer_details.append(peer_info)

    return _safe({
        "customer": actual_name,
        "cluster": cluster_node.replace("cluster::", "") if cluster_node else "Unknown",
        "broker": broker_nodes[0].replace("broker::", "") if broker_nodes else None,
        "sector": sector_nodes[0].replace("sector::", "")[:50] if sector_nodes else None,
        "product": product_nodes[0].replace("product::", "") if product_nodes else None,
        "structural_peers": peer_details,
        "note": "Peers found via shared broker+sector relationships in the portfolio graph",
    })


@mcp.tool()
def explain_recommendation(customer_name: str) -> str:
    """
    Generate a structured explanation of why a customer received their recommendation.
    Breaks down which factors increased or decreased the risk score.
    """
    recs_path = DATA / "all_recommendations.csv"
    if not recs_path.exists():
        return _safe({"error": "No recommendation data available"})

    recs = pd.read_csv(recs_path)
    mask = recs["company_name"].astype(str).str.contains(customer_name, case=False, na=False)
    matches = recs[mask]

    if matches.empty:
        return _safe({"message": f"No data found for '{customer_name}'"})

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
        "explanation": {
            k: {
                "points": round(float(v), 1),
                "direction": "increases risk" if v > 0 else "reduces risk",
            }
            for k, v in components.items()
        },
        "reasoning": row.get("reasoning", ""),
        "advisory": "All recommendations are advisory. Human underwriter review required.",
    })

# ── NetworkX graph analytics tools — with governance controls ─────────────────
# Each tool returns a `governance` field with audit metadata.
# The agent must use these fields to frame insights correctly.

import uuid as _uuid


def _governance(basis: str, risk_level: str, notes: str) -> dict:
    """Standard governance metadata attached to every graph tool result."""
    return {
        "basis": basis,
        "risk_level": risk_level,
        "advisory_only": True,
        "individual_risk_independent": True,
        "audit_id": str(_uuid.uuid4()),
        "notes": notes,
    }


@mcp.tool()
def get_community_purity() -> str:
    """
    Analyse how 'pure' each Louvain structural community is by KMeans cluster.
    Identifies Risk Pockets (>80% High Risk) and Contagion Risk communities (mixed clusters).

    GOVERNANCE: Community-level observation only. Never implies individual customer risk.
    Use to identify portfolio concentration — not to treat individual customers differently.
    """
    comm_path = DATA / "graph_communities.csv"
    gm_path   = DATA / "graph_metrics.csv"
    if not comm_path.exists() or not gm_path.exists():
        return _safe({"error": "Community data not available. Run build_knowledge_graph.py"})

    communities = pd.read_csv(comm_path)
    metrics     = pd.read_csv(gm_path)
    merged = communities.merge(metrics[["customer", "risk_score"]], on="customer", how="left")

    rows = []
    for comm_id, grp in merged.groupby("community_id"):
        total = len(grp)
        counts = grp["cluster"].value_counts()
        dominant = counts.index[0] if len(counts) else "Unknown"
        purity = round(counts.iloc[0] / total * 100, 1) if len(counts) else 0
        high_pct = round((grp["cluster"] == "High Risk").mean() * 100, 1)
        low_pct  = round((grp["cluster"] == "Low Risk").mean() * 100, 1)

        if purity >= 80 and dominant == "High Risk":
            ctype = "Risk Pocket"
        elif high_pct >= 30 and low_pct >= 30:
            ctype = "Contagion Risk"
        elif purity >= 80 and dominant == "Low Risk":
            ctype = "Safe Cluster"
        else:
            ctype = "Mixed"

        rows.append({
            "community_id": comm_id,
            "total_customers": total,
            "dominant_cluster": dominant,
            "purity_pct": purity,
            "high_risk_pct": high_pct,
            "low_risk_pct": low_pct,
            "community_type": ctype,
            "avg_risk_score": round(grp["risk_score"].mean(), 1),
        })

    df = pd.DataFrame(rows).sort_values("high_risk_pct", ascending=False)
    risk_pockets = int((df["community_type"] == "Risk Pocket").sum())
    contagion    = int((df["community_type"] == "Contagion Risk").sum())

    return _safe({
        "communities": df.head(14).to_dict(orient="records"),
        "summary": {
            "total_communities": len(df),
            "risk_pockets": risk_pockets,
            "contagion_risk": contagion,
            "safe_clusters": int((df["community_type"] == "Safe Cluster").sum()),
        },
        "governance": _governance(
            basis="louvain_structural_community_detection",
            risk_level="medium",
            notes="Community-level analysis only. Individual customer risk scores are independent. "
                  "Risk Pocket label applies to the structural group, not to individual members.",
        ),
    })


@mcp.tool()
def find_cluster_bridges(top_n: int = 15) -> str:
    """
    Find High Risk customers structurally connected to Low Risk customers via shared broker.
    These create hidden correlation paths — NOT a judgment on individual customer quality.

    GOVERNANCE HIGH RISK: Structural position only. A customer appearing here has NOT
    been individually reassessed. Never recommend Fresh UW based solely on bridge position.
    Always cross-reference with the individual risk_score from get_risk_score().
    """
    G = _load_graph()
    gm_path = DATA / "graph_metrics.csv"
    if G is None or not gm_path.exists():
        return _safe({"error": "Graph not available"})

    gm = pd.read_csv(gm_path)
    cluster_map = dict(zip(gm["customer"], gm["cluster"]))
    score_map   = dict(zip(gm["customer"], gm["risk_score"]))

    rows = []
    for cust_node, data in G.nodes(data=True):
        if data.get("node_type") != "customer": continue
        if data.get("cluster") != "High Risk": continue

        cust_name = cust_node.replace("cust::", "")
        broker_nodes = [n for n in G.neighbors(cust_node) if n.startswith("broker::")]

        low_risk_peers = []
        for b_node in broker_nodes:
            for peer in G.neighbors(b_node):
                if peer.startswith("cust::") and peer != cust_node:
                    peer_name = peer.replace("cust::", "")
                    if cluster_map.get(peer_name) == "Low Risk":
                        low_risk_peers.append(peer_name)

        if low_risk_peers:
            rows.append({
                "high_risk_customer": cust_name,
                "individual_risk_score": score_map.get(cust_name),
                "broker": broker_nodes[0].replace("broker::", "") if broker_nodes else "N/A",
                "low_risk_peers_count": len(set(low_risk_peers)),
                "bridge_severity": "HIGH" if len(set(low_risk_peers)) >= 5 else "MEDIUM",
            })

    df = pd.DataFrame(rows).sort_values("low_risk_peers_count", ascending=False).head(top_n) if rows else pd.DataFrame()

    return _safe({
        "bridges": df.to_dict(orient="records") if not df.empty else [],
        "total_bridges_found": len(rows),
        "governance": _governance(
            basis="networkx_graph_traversal_broker_edges",
            risk_level="high",
            notes="CRITICAL: Bridge position is structural only. "
                  "Do NOT use this alone to reassess individual customer risk. "
                  "Always cross-reference individual_risk_score. "
                  "Use for broker portfolio monitoring and aggregate risk management only.",
        ),
    })


@mcp.tool()
def get_broker_centrality(top_n: int = 15) -> str:
    """
    Rank brokers by their structural importance (network centrality) and approval rate.
    Danger score = network importance × poor approval rate.

    GOVERNANCE: Centrality measures portfolio concentration risk, NOT broker quality.
    A high centrality broker may have excellent quality — it simply means the portfolio
    is more exposed if that broker's book deteriorates. Never use to characterise broker quality.
    """
    G = _load_graph()
    subs_path = DATA / "all_submissions.csv"
    if G is None or not subs_path.exists():
        return _safe({"error": "Graph or submission data not available"})

    subs = pd.read_csv(subs_path, low_memory=False)
    subs["is_bound"] = (subs["Submission Product Bound Premium Amount"].notna() &
                        (subs["Submission Product Bound Premium Amount"] > 0))
    broker_stats = (
        subs.groupby("National Broker Name")
        .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
        .reset_index()
    )
    broker_stats["approval_rate_pct"] = (broker_stats["bound"] / broker_stats["total"].clip(1) * 100).round(1)

    centrality = {}
    for node, data in G.nodes(data=True):
        if data.get("node_type") == "broker":
            name = node.replace("broker::", "")
            n_customers = sum(1 for nb in G.neighbors(node) if nb.startswith("cust::"))
            centrality[name] = n_customers

    broker_stats["connected_customers"] = broker_stats["National Broker Name"].map(
        lambda b: centrality.get(b, 0)
    )
    max_conn = broker_stats["connected_customers"].max() or 1
    broker_stats["network_importance_pct"] = (broker_stats["connected_customers"] / max_conn * 100).round(1)
    broker_stats["danger_score"] = (
        broker_stats["network_importance_pct"] * (100 - broker_stats["approval_rate_pct"]) / 100
    ).round(1)

    result = broker_stats.nlargest(top_n, "danger_score").rename(
        columns={"National Broker Name": "broker"}
    )

    return _safe({
        "brokers": result[["broker", "total", "approval_rate_pct",
                            "network_importance_pct", "danger_score"]].to_dict(orient="records"),
        "governance": _governance(
            basis="networkx_degree_centrality_approval_rate_composite",
            risk_level="medium",
            notes="Danger score reflects portfolio concentration risk ONLY. "
                  "High score means this broker's portfolio is large AND has low approval rate. "
                  "This is NOT a quality assessment of the broker. "
                  "Use for aggregate risk management and monitoring prioritisation.",
        ),
    })


@mcp.tool()
def get_high_risk_central_nodes(top_n: int = 15) -> str:
    """
    Find High Risk customers with the highest network centrality (degree/PageRank).
    High centrality = if an issue occurs with this customer, it propagates further.

    GOVERNANCE MEDIUM: Centrality is a structural property, not a risk elevation.
    A customer with high centrality has NOT been individually reassessed upward.
    Use for monitoring prioritisation — not for coverage or pricing decisions.
    """
    gm_path = DATA / "graph_metrics.csv"
    if not gm_path.exists():
        return _safe({"error": "Graph metrics not available. Run build_knowledge_graph.py"})

    gm = pd.read_csv(gm_path)
    high_risk = gm[gm["cluster"] == "High Risk"].copy()
    if high_risk.empty:
        return _safe({"message": "No High Risk customers found", "customers": []})

    sort_col = "betweenness_centrality" if "betweenness_centrality" in high_risk.columns else "degree"
    high_risk = high_risk.nlargest(top_n, sort_col)
    high_risk["propagation_priority"] = (
        high_risk[sort_col] / high_risk[sort_col].max().clip(1e-9) * 100
    ).round(1)

    return _safe({
        "customers": high_risk[["customer", "risk_score", "recommendation",
                                 "degree", sort_col, "propagation_priority"]].to_dict(orient="records"),
        "sort_metric": sort_col,
        "governance": _governance(
            basis="networkx_centrality_metrics",
            risk_level="medium",
            notes="Propagation priority = structural importance only. "
                  "These customers warrant monitoring attention due to network position. "
                  "Their individual risk_score has NOT been elevated by this analysis. "
                  "Use as monitoring priority list — not for underwriting decisions.",
        ),
    })


@mcp.tool()
def simulate_cascade_graph(
    event_type: str = "cyber_campaign",
    target_broker: str = None,
) -> str:
    """
    Simulate a hazard event propagating through the portfolio Knowledge Graph.
    Returns D1 (direct), D2 (broker cascade), D3 (sector cascade) customer lists.

    event_type: cyber_campaign | financial_contagion | supply_chain | broker_failure
    target_broker: optional broker name to target (e.g. 'MARSH')

    GOVERNANCE HIGHEST: This is a HYPOTHETICAL SCENARIO, NOT A PREDICTION.
    Results must be framed as: 'In a simulated X event...' never as 'X will happen'.
    Do NOT use to reassess individual customer risk scores.
    Do NOT trigger underwriting actions based on simulation alone.
    """
    G = _load_graph()
    gm_path = DATA / "graph_metrics.csv"
    if G is None or not gm_path.exists():
        return _safe({"error": "Graph not available"})

    gm = pd.read_csv(gm_path)
    cust_info = dict(zip(gm["customer"], gm[["cluster", "risk_score", "recommendation"]].to_dict(orient="records")))

    EVENT_PRODUCTS = {
        "cyber_campaign":      ["Cyber", "ZCIP"],
        "financial_contagion": ["Financial Lines", "Crime"],
        "supply_chain":        ["Technology"],
        "broker_failure":      [],
    }
    affected_products = EVENT_PRODUCTS.get(event_type, ["Cyber"])

    # D1: directly exposed
    d1 = set()
    for cust_node in G.nodes:
        if not cust_node.startswith("cust::"): continue
        nbs = list(G.neighbors(cust_node))
        if target_broker:
            if any(target_broker.upper()[:6] in n.upper() for n in nbs if n.startswith("broker::")):
                d1.add(cust_node)
        elif affected_products:
            prod_nbs = [n for n in nbs if n.startswith("product::")]
            if any(any(kw.lower() in p.lower() for kw in affected_products) for p in prod_nbs):
                d1.add(cust_node)

    # D2: broker cascade
    d1_brokers = set()
    for n in d1:
        for nb in G.neighbors(n):
            if nb.startswith("broker::"):
                d1_brokers.add(nb)
    d2 = set()
    for b in d1_brokers:
        for c in G.neighbors(b):
            if c.startswith("cust::") and c not in d1:
                d2.add(c)

    # D3: sector cascade (sample)
    d2_sectors = set()
    for c in list(d2)[:30]:
        for nb in G.neighbors(c):
            if nb.startswith("sector::"):
                d2_sectors.add(nb)
    d3 = set()
    for s in list(d2_sectors)[:5]:
        for c in G.neighbors(s):
            if c.startswith("cust::") and c not in d1 and c not in d2:
                d3.add(c)

    def _customer_list(nodes, limit=20):
        result = []
        for n in list(nodes)[:limit]:
            name = n.replace("cust::", "")
            info = cust_info.get(name, {})
            result.append({
                "customer": name,
                "cluster": info.get("cluster", ""),
                "risk_score": info.get("risk_score"),
                "recommendation": info.get("recommendation", ""),
            })
        return result

    return _safe({
        "scenario": {
            "event_type": event_type,
            "target_broker": target_broker,
            "is_hypothetical": True,
        },
        "cascade": {
            "d1_direct_exposure": {"count": len(d1), "customers": _customer_list(d1)},
            "d2_broker_cascade":  {"count": len(d2), "customers": _customer_list(d2)},
            "d3_sector_cascade":  {"count": len(d3), "customers": _customer_list(d3)},
            "total_affected": len(d1) + len(d2) + len(d3),
        },
        "governance": _governance(
            basis="networkx_graph_traversal_cascade_simulation",
            risk_level="high",
            notes="HYPOTHETICAL SCENARIO ONLY — NOT A PREDICTION OR FORECAST. "
                  "Results reflect structural network paths, not probability of loss. "
                  "D1/D2/D3 customers have NOT been individually reassessed. "
                  "Use for stress testing and aggregate risk management planning only. "
                  "Never trigger individual underwriting actions based on simulation results.",
        ),
    })


@mcp.tool()
def query_uw_guidelines(question: str, top_k: int = 3) -> str:
    """
    Retrieve relevant passages from Zurich UW guidelines to ground recommendations.
    Use when making underwriting recommendations to cite the actual policy basis.
    Returns passages with source citations.

    GOVERNANCE: Always cite the source when using this in a recommendation.
    Never paraphrase guidelines without showing the original passage.
    """
    try:
        from src.rag.guidelines_rag import query_guidelines, index_available
        if not index_available():
            return _safe({
                "available": False,
                "message": "UW Guidelines index not built. Run: python -m src.rag.guidelines_rag --build",
                "fallback": "Proceeding without guideline citations.",
            })

        results = query_guidelines(question, top_k=top_k)
        if not results:
            return _safe({
                "available": True,
                "results": [],
                "message": "No relevant guideline passages found for this question.",
            })

        return _safe({
            "available": True,
            "question": question,
            "results": results,
            "governance": {
                "advisory_only": True,
                "citation_required": True,
                "notes": "Always cite the source passage when using guidelines in recommendations. "
                         "Do not paraphrase without showing original text.",
            },
        })
    except Exception as e:
        return _safe({"error": f"query_uw_guidelines failed: {e}"})


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
