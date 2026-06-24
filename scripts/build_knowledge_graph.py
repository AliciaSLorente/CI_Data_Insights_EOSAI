"""
Build the Knowledge Graph using KMeans + NetworkX on all 9,078 repeat customers.

This is the Phase 2 extension of notebook 03_kg_construction.ipynb.
The notebook only used 162 PDF companies — this script uses all repeat customers.

Pipeline:
  1. KMeans clustering on 9,078 repeat customers (submission features)
  2. Build NetworkX graph: Customer → Broker → Sector → Product → RiskCluster
  3. Annotate graph nodes with cluster labels, risk scores, approval rates
  4. Pre-compute graph metrics: degree centrality, betweenness, PageRank
  5. Detect communities (Louvain / greedy modularity)
  6. Export: knowledge_graph.graphml + graph_metrics.csv + graph_communities.csv

Outputs (data/parsed/):
  knowledge_graph.graphml     - Full NetworkX graph (loadable by dashboard/agent)
  graph_metrics.csv           - Node-level metrics (centrality, cluster, risk)
  graph_communities.csv       - Community membership per customer
  control_impact.csv          - Control vs approval rate correlation
"""

import pandas as pd
import numpy as np
import networkx as nx
import sys
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA = Path("data/parsed")


# ── 1. Load data ───────────────────────────────────────────────────────────────

def load_data():
    print("Loading data...")
    subs = pd.read_csv(DATA / "all_submissions.csv", low_memory=False)
    subs["Requested Coverage Effective Date"] = pd.to_datetime(
        subs["Requested Coverage Effective Date"], errors="coerce"
    )
    subs["Year"] = subs["Requested Coverage Effective Date"].dt.year
    subs["is_bound"] = (
        subs["Submission Product Bound Premium Amount"].notna()
        & (subs["Submission Product Bound Premium Amount"] > 0)
    )

    repeats = pd.read_csv(DATA / "repeat_customers.csv")
    recs = pd.read_csv(DATA / "all_recommendations.csv")
    pdfs = pd.read_csv(DATA / "pdf_extracted_fields.csv")
    brokers = pd.read_csv(DATA / "customer_broker_relationships.csv")

    print(f"  Submissions: {len(subs):,}")
    print(f"  Repeat customers: {len(repeats):,}")
    print(f"  Recommendations: {len(recs):,}")
    print(f"  PDF records: {len(pdfs):,}")
    return subs, repeats, recs, pdfs, brokers


# ── 2. KMeans clustering on all 9,078 repeat customers ────────────────────────

def compute_clusters(subs, repeats, recs, n_clusters=3):
    print(f"\nComputing KMeans clusters (k={n_clusters}) on {len(repeats):,} customers...")

    features = (
        subs.groupby("Submission Account Name")
        .agg(
            submission_count=("Submission Account Name", "count"),
            approval_rate=("is_bound", "mean"),
            avg_premium=("Quoted Premium Amount", "mean"),
            years_active=("Year", lambda x: x.nunique()),
            recent_declined=("Current Status Description", lambda x: (x.tail(3) == "Declined").sum()),
        )
        .reset_index()
    )

    # Only repeat customers
    repeat_names = set(repeats["Submission Account Name"])
    features = features[features["Submission Account Name"].isin(repeat_names)].copy()
    features["avg_premium"] = features["avg_premium"].fillna(0)

    # Merge risk scores
    features = features.merge(
        recs[["company_name", "risk_score", "recommendation", "confidence"]],
        left_on="Submission Account Name", right_on="company_name", how="left"
    ).drop(columns=["company_name"], errors="ignore")
    features["risk_score"] = features["risk_score"].fillna(50)

    # KMeans
    feature_cols = ["submission_count", "approval_rate", "avg_premium", "years_active", "recent_declined"]
    X = features[feature_cols].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    features["cluster_id"] = kmeans.fit_predict(X_scaled)

    # Label clusters by approval rate (highest = Low Risk)
    cluster_approval = features.groupby("cluster_id")["approval_rate"].mean().sort_values(ascending=False)
    label_map = {
        cluster_approval.index[0]: "Low Risk",
        cluster_approval.index[1]: "Moderate Risk",
        cluster_approval.index[2]: "High Risk",
    }
    features["cluster_label"] = features["cluster_id"].map(label_map)

    # Print summary
    for label in ["Low Risk", "Moderate Risk", "High Risk"]:
        sub = features[features["cluster_label"] == label]
        print(f"  {label}: {len(sub):,} customers | "
              f"avg approval {sub['approval_rate'].mean():.0%} | "
              f"avg risk score {sub['risk_score'].mean():.0f}")

    return features


# ── 3. Build NetworkX graph ────────────────────────────────────────────────────

def build_graph(subs, features, pdfs, brokers):
    print("\nBuilding NetworkX graph...")
    G = nx.Graph()

    # ── Customer nodes ─────────────────────────────────────────────────────────
    for _, row in features.iterrows():
        G.add_node(
            f"cust::{row['Submission Account Name']}",
            node_type="customer",
            name=row["Submission Account Name"],
            cluster=row.get("cluster_label", "Unknown"),
            risk_score=float(row.get("risk_score", 50)),
            recommendation=row.get("recommendation", "STANDARD_UW"),
            approval_rate=float(row["approval_rate"]),
            submission_count=int(row["submission_count"]),
        )

    # ── Broker nodes + edges ───────────────────────────────────────────────────
    broker_stats = (
        subs.groupby("National Broker Name")
        .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
        .reset_index()
    )
    broker_stats["approval_rate"] = broker_stats["bound"] / broker_stats["total"].clip(1)

    for _, row in broker_stats.iterrows():
        bnode = f"broker::{row['National Broker Name']}"
        G.add_node(bnode, node_type="broker",
                   name=row["National Broker Name"],
                   approval_rate=float(row["approval_rate"]),
                   total_submissions=int(row["total"]))

    # Customer → Broker edges
    cust_broker = (
        subs.groupby("Submission Account Name")["National Broker Name"]
        .agg(lambda x: x.mode()[0] if len(x) else None)
        .reset_index()
    )
    repeat_names = set(features["Submission Account Name"])
    for _, row in cust_broker.iterrows():
        if row["Submission Account Name"] in repeat_names and pd.notna(row["National Broker Name"]):
            G.add_edge(
                f"cust::{row['Submission Account Name']}",
                f"broker::{row['National Broker Name']}",
                relationship="works_with"
            )

    # ── Sector (SIC) nodes + edges ─────────────────────────────────────────────
    sic_lookup = (
        subs[subs["SIC Code"].notna() & subs["SIC Name"].notna()]
        .groupby("Submission Account Name")
        .agg(sic_code=("SIC Code", "first"), sic_name=("SIC Name", "first"))
        .reset_index()
    )
    sic_summary = (
        subs.groupby("SIC Name")
        .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
        .reset_index()
    )
    sic_summary["approval_rate"] = sic_summary["bound"] / sic_summary["total"].clip(1)

    for _, row in sic_summary.iterrows():
        if pd.notna(row["SIC Name"]):
            G.add_node(f"sector::{row['SIC Name']}", node_type="sector",
                       name=row["SIC Name"],
                       approval_rate=float(row["approval_rate"]),
                       total_submissions=int(row["total"]))

    for _, row in sic_lookup.iterrows():
        if row["Submission Account Name"] in repeat_names and pd.notna(row["sic_name"]):
            G.add_edge(
                f"cust::{row['Submission Account Name']}",
                f"sector::{row['sic_name']}",
                relationship="operates_in"
            )

    # ── Product nodes + edges ──────────────────────────────────────────────────
    prod_summary = (
        subs.groupby("Product Name")
        .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
        .reset_index()
    )
    prod_summary["approval_rate"] = prod_summary["bound"] / prod_summary["total"].clip(1)

    cust_product = (
        subs.groupby("Submission Account Name")["Product Name"]
        .agg(lambda x: x.mode()[0] if len(x) else None)
        .reset_index()
    )

    for _, row in prod_summary.iterrows():
        if pd.notna(row["Product Name"]):
            G.add_node(f"product::{row['Product Name']}", node_type="product",
                       name=row["Product Name"],
                       approval_rate=float(row["approval_rate"]))

    for _, row in cust_product.iterrows():
        if row["Submission Account Name"] in repeat_names and pd.notna(row["Product Name"]):
            G.add_edge(
                f"cust::{row['Submission Account Name']}",
                f"product::{row['Product Name']}",
                relationship="submitted_for"
            )

    # ── Risk Cluster nodes + edges ─────────────────────────────────────────────
    for cluster_label in ["Low Risk", "Moderate Risk", "High Risk"]:
        G.add_node(f"cluster::{cluster_label}", node_type="risk_cluster", name=cluster_label)

    for _, row in features.iterrows():
        G.add_edge(
            f"cust::{row['Submission Account Name']}",
            f"cluster::{row['cluster_label']}",
            relationship="belongs_to"
        )

    # ── Control nodes + edges (from PDFs) ─────────────────────────────────────
    control_cols = [c for c in pdfs.columns if c.startswith("control_")]
    for ctrl in control_cols:
        label = ctrl.replace("control_", "").replace("_", " ").title()
        G.add_node(f"control::{ctrl}", node_type="control", name=label)

    for _, row in pdfs.iterrows():
        cust_node = f"cust::{row['company_name']}"
        if G.has_node(cust_node):
            for ctrl in control_cols:
                if str(row.get(ctrl, "False")).lower() == "true":
                    G.add_edge(cust_node, f"control::{ctrl}", relationship="has_control")

    print(f"  Nodes: {G.number_of_nodes():,}")
    print(f"  Edges: {G.number_of_edges():,}")
    breakdown = {}
    for n, d in G.nodes(data=True):
        t = d.get("node_type", "unknown")
        breakdown[t] = breakdown.get(t, 0) + 1
    for t, count in sorted(breakdown.items()):
        print(f"    {t}: {count:,}")

    return G


# ── 4. Compute graph metrics ───────────────────────────────────────────────────

def compute_graph_metrics(G, features):
    print("\nComputing graph metrics...")

    # Degree centrality (fast, all nodes)
    print("  Degree centrality...", end=" ", flush=True)
    degree_cent = nx.degree_centrality(G)
    print("OK")

    # PageRank (fast)
    print("  PageRank...", end=" ", flush=True)
    pagerank = nx.pagerank(G, max_iter=100)
    print("OK")

    # Betweenness centrality — expensive on full graph, use approximation
    print("  Betweenness centrality (sampled k=200)...", end=" ", flush=True)
    try:
        betweenness = nx.betweenness_centrality(G, k=200, normalized=True)
        print("OK")
    except Exception as e:
        print(f"SKIP ({e})")
        betweenness = {n: 0.0 for n in G.nodes()}

    # Build metrics DataFrame for customer nodes only
    rows = []
    for _, row in features.iterrows():
        node_id = f"cust::{row['Submission Account Name']}"
        if G.has_node(node_id):
            rows.append({
                "customer": row["Submission Account Name"],
                "cluster": row["cluster_label"],
                "risk_score": row.get("risk_score", 50),
                "recommendation": row.get("recommendation", "STANDARD_UW"),
                "approval_rate": round(row["approval_rate"] * 100, 1),
                "submission_count": row["submission_count"],
                "degree_centrality": round(degree_cent.get(node_id, 0), 6),
                "pagerank": round(pagerank.get(node_id, 0), 8),
                "betweenness_centrality": round(betweenness.get(node_id, 0), 8),
                "degree": G.degree(node_id),
            })

    metrics_df = pd.DataFrame(rows)

    # Top nodes by PageRank
    top_pr = metrics_df.nlargest(5, "pagerank")[["customer", "cluster", "pagerank", "degree"]]
    print("\n  Top 5 customers by PageRank (most structurally central):")
    print(top_pr.to_string(index=False))

    return metrics_df


# ── 5. Community detection ────────────────────────────────────────────────────

def detect_communities(G, features):
    print("\nDetecting communities...")

    try:
        from networkx.algorithms.community import greedy_modularity_communities
        communities = list(greedy_modularity_communities(G))
        print(f"  Found {len(communities)} communities")

        community_map = {}
        for i, community in enumerate(communities):
            for node in community:
                community_map[node] = i

        rows = []
        for _, row in features.iterrows():
            node_id = f"cust::{row['Submission Account Name']}"
            rows.append({
                "customer": row["Submission Account Name"],
                "community_id": community_map.get(node_id, -1),
                "cluster": row["cluster_label"],
            })

        comm_df = pd.DataFrame(rows)
        comm_sizes = comm_df["community_id"].value_counts()
        print(f"  Community sizes: min={comm_sizes.min()}, max={comm_sizes.max()}, median={comm_sizes.median():.0f}")
        return comm_df

    except Exception as e:
        print(f"  Community detection failed: {e}")
        return pd.DataFrame()


# ── 6. Control impact analysis ────────────────────────────────────────────────

def compute_control_impact(subs, pdfs):
    print("\nComputing control impact on approval rates...")

    control_cols = [c for c in pdfs.columns if c.startswith("control_")]
    merged = pdfs.merge(
        subs.groupby("Submission Account Name")["is_bound"].mean().reset_index(),
        left_on="company_name", right_on="Submission Account Name", how="inner"
    )

    rows = []
    for ctrl in control_cols:
        if ctrl not in merged.columns:
            continue
        has = merged[merged[ctrl].astype(str).str.lower() == "true"]["is_bound"]
        not_has = merged[merged[ctrl].astype(str).str.lower() != "true"]["is_bound"]
        rows.append({
            "control": ctrl.replace("control_", "").replace("_", " ").title(),
            "control_key": ctrl,
            "pct_customers_with": round(len(has) / len(merged) * 100, 1),
            "approval_rate_with": round(has.mean() * 100, 1) if len(has) > 0 else None,
            "approval_rate_without": round(not_has.mean() * 100, 1) if len(not_has) > 0 else None,
            "sample_with": len(has),
            "sample_without": len(not_has),
        })

    impact_df = pd.DataFrame(rows)
    impact_df["approval_lift"] = (
        impact_df["approval_rate_with"].fillna(0) - impact_df["approval_rate_without"].fillna(0)
    ).round(1)
    impact_df = impact_df.sort_values("pct_customers_with", ascending=False)

    print("  Top controls by prevalence:")
    print(impact_df[["control", "pct_customers_with", "approval_rate_with"]].head(5).to_string(index=False))

    return impact_df


# ── 7. Save outputs ───────────────────────────────────────────────────────────

def save_outputs(G, metrics_df, comm_df, impact_df, force=False):
    print("\nSaving outputs...")

    import pickle
    outputs = {
        # Pickle is ~10x faster to load than GraphML (binary vs XML)
        "knowledge_graph.pkl": lambda: pickle.dump(G, open(DATA / "knowledge_graph.pkl", "wb"), protocol=4),
        # Keep graphml as backup for interoperability
        "knowledge_graph.graphml": lambda: nx.write_graphml(G, DATA / "knowledge_graph.graphml"),
        "graph_metrics.csv": lambda: metrics_df.to_csv(DATA / "graph_metrics.csv", index=False),
        "graph_communities.csv": lambda: comm_df.to_csv(DATA / "graph_communities.csv", index=False) if not comm_df.empty else None,
        "control_impact.csv": lambda: impact_df.to_csv(DATA / "control_impact.csv", index=False),
    }

    for fname, fn in outputs.items():
        path = DATA / fname
        if path.exists() and not force:
            print(f"  SKIP {fname} (exists — use --force to regenerate)")
            continue
        try:
            fn()
            size = path.stat().st_size / 1024 if path.exists() else 0
            print(f"  OK   {fname} ({size:.0f} KB)")
        except Exception as e:
            print(f"  ERR  {fname}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(force=False):
    print("=" * 60)
    print("Knowledge Graph Build Pipeline (Phase 2)")
    print("KMeans + NetworkX on all repeat customers")
    print("=" * 60)

    subs, repeats, recs, pdfs, brokers = load_data()
    features = compute_clusters(subs, repeats, recs, n_clusters=3)
    G = build_graph(subs, features, pdfs, brokers)
    metrics_df = compute_graph_metrics(G, features)
    comm_df = detect_communities(G, features)
    impact_df = compute_control_impact(subs, pdfs)
    save_outputs(G, metrics_df, comm_df, impact_df, force=force)

    print("\n" + "=" * 60)
    print("Done.")
    print(f"  Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    print(f"  Metrics: {len(metrics_df):,} customers with graph metrics")
    if not comm_df.empty:
        print(f"  Communities: {comm_df['community_id'].nunique()} detected")
    print("\nNext: run 'Refresh Data' in the dashboard.")
    print("=" * 60)

    return G, metrics_df, comm_df, impact_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build Knowledge Graph (KMeans + NetworkX)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()
    main(force=args.force)
