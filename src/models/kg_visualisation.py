"""
Knowledge Graph Visualisation module — pyvis-based interactive network views.

Two main views:
  1. cascade_network_html()  — Shows cascade propagation through portfolio after a hazard event.
     Broker hubs at centre, customers colored by KMeans cluster + cascade degree.

  2. cluster_life_html()     — Shows each KMeans cluster as a visual group.
     Internal broker connections visible, cross-cluster bridges highlighted.

Both return HTML strings for st.components.v1.html().
"""

import pickle
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from typing import Dict, List, Optional

DATA = Path("data/parsed")


def _load_graph():
    pkl = DATA / "knowledge_graph.pkl"
    if not pkl.exists():
        return None
    with open(pkl, "rb") as f:
        return pickle.load(f)


def _load_metrics() -> pd.DataFrame:
    p = DATA / "graph_metrics.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


# ── 1. Cascade Network Visualisation ─────────────────────────────────────────

def cascade_network_html(
    event_type: str = "cyber_campaign",
    target_broker: Optional[str] = None,
    target_sector: Optional[str] = None,
    max_nodes: int = 80,
    height: str = "550px",
    custom_products: Optional[List[str]] = None,
) -> str:
    """
    Build a pyvis HTML string showing cascade propagation through the portfolio.

    Layout:
      - Broker nodes = large orange hubs at centre
      - D1 customers (directly exposed) = red, larger
      - D2 customers (broker cascade) = orange, medium
      - D3 customers (sector cascade) = yellow, small
      - Unaffected customers = grey (sample only to avoid overload)
      - KMeans cluster shown as node border colour

    Returns HTML string for st.components.v1.html().
    """
    from pyvis.network import Network

    G = _load_graph()
    gm = _load_metrics()
    if G is None:
        return "<p>Graph not available. Run: python scripts/build_knowledge_graph.py</p>"

    # Build cluster + recommendation lookup
    cust_info = {}
    if not gm.empty:
        for _, row in gm.iterrows():
            cust_info[row["customer"]] = {
                "cluster": row.get("cluster", ""),
                "risk_score": row.get("risk_score", 50),
                "rec": row.get("recommendation", "STANDARD_UW"),
                "approval": row.get("approval_rate", 0),
            }

    # ── Determine D1 customers based on event/broker/sector ──────────────────
    EVENT_PRODUCTS = {
        "cyber_campaign":      ["Cyber", "ZCIP", "Security"],
        "financial_contagion": ["Financial Lines", "Crime", "D&O"],
        "supply_chain":        ["Cyber", "Technology"],
        "broker_failure":      [],
    }
    affected_products = custom_products if custom_products else EVENT_PRODUCTS.get(event_type, ["Security"])

    d1_nodes = set()
    d2_nodes = set()
    d3_nodes = set()

    # D1: match by product or broker
    for cust_node in G.nodes:
        if not cust_node.startswith("cust::"):
            continue
        nbs = list(G.neighbors(cust_node))
        prod_nodes = [n for n in nbs if n.startswith("product::")]
        brok_nodes  = [n for n in nbs if n.startswith("broker::")]

        has_broker  = bool(target_broker) and any(
            target_broker.upper()[:6] in n.upper() for n in brok_nodes)
        has_product = bool(affected_products) and any(
            kw.lower() in p_node.lower() for kw in affected_products for p_node in prod_nodes)

        if event_type == "broker_failure":
            if has_broker:
                d1_nodes.add(cust_node)
        elif target_broker:
            if has_broker and has_product:
                d1_nodes.add(cust_node)
        elif has_product:
            d1_nodes.add(cust_node)

    # D2: other customers sharing broker with D1
    d1_brokers = set()
    for d1 in d1_nodes:
        for nb in G.neighbors(d1):
            if nb.startswith("broker::"):
                d1_brokers.add(nb)

    for broker_node in d1_brokers:
        for cust_node in G.neighbors(broker_node):
            if cust_node.startswith("cust::") and cust_node not in d1_nodes:
                d2_nodes.add(cust_node)

    # D3: customers sharing sector with D2
    d2_sectors = set()
    for d2 in list(d2_nodes)[:50]:
        for nb in G.neighbors(d2):
            if nb.startswith("sector::"):
                d2_sectors.add(nb)

    for sector_node in list(d2_sectors)[:10]:
        for cust_node in G.neighbors(sector_node):
            if (cust_node.startswith("cust::") and
                    cust_node not in d1_nodes and cust_node not in d2_nodes):
                d3_nodes.add(cust_node)

    # ── Build pyvis network ───────────────────────────────────────────────────
    net = Network(height=height, width="100%",
                  bgcolor="#0F1117", font_color="#F9FAFB",
                  directed=False)
    net.set_options("""
    {
      "nodes": {
        "borderWidth": 2,
        "shadow": {"enabled": true, "size": 12, "color": "rgba(0,0,0,0.6)"},
        "font": {"size": 11, "bold": true}
      },
      "edges": {
        "color": {"opacity": 0.45},
        "width": 1.5,
        "smooth": {"type": "dynamic"},
        "selectionWidth": 3
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -55,
          "centralGravity": 0.012,
          "springLength": 110,
          "springConstant": 0.08,
          "damping": 0.42
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"enabled": true, "iterations": 100, "updateInterval": 10, "fit": true}
      },
      "interaction": {"hover": true, "tooltipDelay": 80, "hideEdgesOnDrag": true}
    }
    """)

    CLUSTER_BORDER = {
        "Low Risk":      "#22C55E",
        "Moderate Risk": "#F97316",
        "High Risk":     "#EF4444",
    }
    CASCADE_COLOR = {
        "D1": "#EF4444",   # red  — directly hit
        "D2": "#F97316",   # orange — broker cascade
        "D3": "#EAB308",   # yellow — sector cascade
    }

    added_nodes = set()

    def _add_customer(cust_node: str, degree: str, size: int):
        if cust_node in added_nodes:
            return
        name = cust_node.replace("cust::", "")
        info = cust_info.get(name, {})
        cluster = info.get("cluster", "")
        rec = info.get("rec", "")
        score = info.get("risk_score", 50)
        fill = CASCADE_COLOR.get(degree, "#6B7280")
        border = CLUSTER_BORDER.get(cluster, "#6B7280")
        tooltip = (f"{name}\n"
                   f"Cluster: {cluster}\n"
                   f"Score: {score}/100\n"
                   f"Rec: {rec}\n"
                   f"Cascade: {degree}")
        net.add_node(cust_node, label=name[:18], color={"background": fill, "border": border},
                     size=size, title=tooltip, borderWidth=3)
        added_nodes.add(cust_node)

    # Add broker hub nodes
    added_brokers = set()
    for b_node in d1_brokers:
        bname = b_node.replace("broker::", "")[:20]
        n_cust = sum(1 for nb in G.neighbors(b_node) if nb.startswith("cust::"))
        net.add_node(b_node, label=bname, color={"background": "#F97316", "border": "#EA580C"},
                     size=35, shape="diamond",
                     title=f"BROKER: {bname}\n{n_cust} connected customers")
        added_brokers.add(b_node)

    # Limit nodes to max_nodes
    d1_sample = list(d1_nodes)[:min(25, max_nodes // 3)]
    d2_sample = list(d2_nodes)[:min(30, max_nodes // 3)]
    d3_sample = list(d3_nodes)[:min(20, max_nodes // 4)]

    for n in d1_sample: _add_customer(n, "D1", 18)
    for n in d2_sample: _add_customer(n, "D2", 12)
    for n in d3_sample: _add_customer(n, "D3", 8)

    # Add edges between brokers and customers
    for b_node in added_brokers:
        for cust_node in G.neighbors(b_node):
            if cust_node in added_nodes:
                net.add_edge(b_node, cust_node,
                             color={"color": "#6B7280", "opacity": 0.4}, width=1)

    # D1 → D1 sector links
    for i, c1 in enumerate(d1_sample[:15]):
        for c2 in d1_sample[i+1:16]:
            shared = set(G.neighbors(c1)) & set(G.neighbors(c2))
            if any(n.startswith("sector::") for n in shared):
                net.add_edge(c1, c2, color={"color": "#EF4444", "opacity": 0.6}, width=2,
                             title="Shared sector")

    html = net.generate_html()
    return html


# ── 1b. Ripple Effect Visualisation ──────────────────────────────────────────

def cascade_ripple_html(
    event_type: str = "cyber_campaign",
    target_broker: Optional[str] = None,
    target_sector: Optional[str] = None,
    max_nodes: int = 80,
    height: str = "750px",
    custom_products: Optional[List[str]] = None,
) -> str:
    """
    Academic-style cascade ripple visualization.

    Visual principles (based on network failure research):
      - Node SIZE     = degree (number of connections) — not cascade tier
        Larger circles have more connections; reveals WHY a node is dangerous
      - Node COLOUR   = ripple distance from event origin (gradient: dark → light)
        D1 deep red → D2 orange → D3 amber → unaffected dark grey
      - Origin node   = star shape — the disrupted epicentre
      - Background    = small dark unaffected nodes for full network context

    Key insight visible from this view:
      A small-degree broker (small star) can still trigger a large cascade
      because of its strategic position — not just its size.
    """
    from pyvis.network import Network
    import random as _random

    G  = _load_graph()
    gm = _load_metrics()
    if G is None:
        return "<p>Graph not available.</p>"

    # Degree lookup — drives node size
    degree_map: Dict[str, int] = {}
    if not gm.empty and "degree" in gm.columns:
        degree_map = dict(zip(gm["customer"], gm["degree"].fillna(4).astype(int)))

    # Customer info for tooltips
    cust_info: Dict[str, dict] = {}
    if not gm.empty:
        for _, row in gm.iterrows():
            cust_info[row["customer"]] = {
                "cluster":    row.get("cluster", ""),
                "risk_score": row.get("risk_score", 50),
                "rec":        row.get("recommendation", "STANDARD_UW"),
            }

    # ── Identify cascade tiers (same logic as cascade_network_html) ──────────
    EVENT_PRODUCTS = {
        "cyber_campaign":      ["Security", "ZCIP", "Cyber"],
        "financial_contagion": ["ProPlus", "Crime", "Professional", "Liability"],
        "supply_chain":        ["Security", "ZCIP"],
        "broker_failure":      [],
    }
    affected_products = custom_products if custom_products else EVENT_PRODUCTS.get(event_type, ["Security"])

    d1_nodes: set = set()
    d2_nodes: set = set()
    d3_nodes: set = set()

    for cust_node in G.nodes:
        if not cust_node.startswith("cust::"):
            continue
        nbs        = list(G.neighbors(cust_node))
        prod_nodes = [n for n in nbs if n.startswith("product::")]
        brok_nodes = [n for n in nbs if n.startswith("broker::")]
        has_broker  = bool(target_broker) and any(
            target_broker.upper()[:6] in n.upper() for n in brok_nodes)
        has_product = bool(affected_products) and any(
            kw.lower() in p_node.lower() for kw in affected_products for p_node in prod_nodes)

        if event_type == "broker_failure":
            if has_broker:
                d1_nodes.add(cust_node)
        elif target_broker:
            if has_broker and has_product:
                d1_nodes.add(cust_node)
        elif has_product:
            d1_nodes.add(cust_node)

    d1_brokers: set = set()
    for d1 in d1_nodes:
        for nb in G.neighbors(d1):
            if nb.startswith("broker::"):
                d1_brokers.add(nb)

    for broker_node in d1_brokers:
        for cust_node in G.neighbors(broker_node):
            if cust_node.startswith("cust::") and cust_node not in d1_nodes:
                d2_nodes.add(cust_node)

    d2_sectors: set = set()
    for d2 in list(d2_nodes)[:50]:
        for nb in G.neighbors(d2):
            if nb.startswith("sector::"):
                d2_sectors.add(nb)
    for sector_node in list(d2_sectors)[:10]:
        for cust_node in G.neighbors(sector_node):
            if cust_node.startswith("cust::") and cust_node not in d1_nodes and cust_node not in d2_nodes:
                d3_nodes.add(cust_node)

    # ── High-contrast palette — 5 visually distinct states ──────────────────
    RIPPLE = {
        "D1": {"bg": "#7F1D1D", "border": "#450A0A"},   # dark maroon   — immediate danger
        "D2": {"bg": "#F97316", "border": "#C2410C"},   # bright orange — clear step away
        "D3": {"bg": "#FDE047", "border": "#D97706"},   # bright yellow — peripheral risk
    }
    UNAFFECTED_BG     = "#F8FAFC"   # near-white — ghost nodes, almost invisible
    UNAFFECTED_BORDER = "#CBD5E1"

    # ── Concentric ring layout helpers ────────────────────────────────────────
    import math as _math

    def _ring_pos(i: int, total: int, radius: float, jitter: float = 0.0):
        """Place node i of total on a ring of given radius, with optional jitter."""
        angle = 2 * _math.pi * i / max(total, 1)
        r = radius + (_random.uniform(-jitter, jitter) if jitter else 0)
        return round(r * _math.cos(angle), 1), round(r * _math.sin(angle), 1)

    # ── Build network — physics OFF, positions fixed ──────────────────────────
    net = Network(height=height, width="100%",
                  bgcolor="#FAFAFA", font_color="#1E293B", directed=False)
    net.set_options("""
    {
      "nodes": {
        "borderWidth": 2,
        "font": {"size": 10, "color": "#1E293B",
                 "strokeWidth": 2, "strokeColor": "#FFFFFF"}
      },
      "edges": {
        "color": {"color": "#D1D5DB", "opacity": 0.55},
        "width": 0.8,
        "smooth": {"type": "continuous"},
        "selectionWidth": 2
      },
      "physics": {"enabled": false},
      "interaction": {
        "hover": true, "tooltipDelay": 80,
        "zoomView": true, "dragView": true
      }
    }
    """)

    added_nodes: set = set()

    def _size(name: str, scale: float = 2.0) -> int:
        """Circle size = network degree — core visual principle."""
        return max(7, min(45, int(degree_map.get(name, 4) * scale)))

    def _add_ripple_node(cust_node: str, ripple: str, x: float, y: float):
        if cust_node in added_nodes:
            return
        name = cust_node.replace("cust::", "")
        info = cust_info.get(name, {})
        col  = RIPPLE[ripple]
        size = _size(name)
        deg  = degree_map.get(name, "?")
        tip  = (f"{name}\n"
                f"Ripple: {ripple}\n"
                f"Degree: {deg} connections\n"
                f"Score: {info.get('risk_score','?')}/100\n"
                f"Rec: {info.get('rec','?')}")
        label = name[:12] if size >= 18 else ""
        net.add_node(cust_node, label=label,
                     color={"background": col["bg"], "border": col["border"]},
                     size=size, title=tip, borderWidth=2,
                     x=x, y=y, physics=False)
        added_nodes.add(cust_node)

    # ── Origin broker — dark centre circle ───────────────────────────────────
    added_brokers: set = set()
    for b_node in d1_brokers:
        bname  = b_node.replace("broker::", "")[:22]
        n_cust = sum(1 for nb in G.neighbors(b_node) if nb.startswith("cust::"))
        size   = max(22, min(55, n_cust * 2))
        net.add_node(
            b_node, label=bname,
            color={"background": "#111827", "border": "#FFFFFF"},
            size=size, shape="dot", borderWidth=4,
            x=0, y=0, physics=False,
            title=(f"CASCADE ORIGIN — BROKER\n{bname}\n"
                   f"Portfolio connections: {n_cust} customers\n"
                   f"Even a small circle here can cascade far if strategically positioned.")
        )
        added_brokers.add(b_node)

    # ── Concentric rings: D1=220, D2=430, D3=640 ─────────────────────────────
    d1_s = list(d1_nodes)[:min(30, max_nodes // 3)]
    d2_s = list(d2_nodes)[:min(35, max_nodes // 3)]
    d3_s = list(d3_nodes)[:min(25, max_nodes // 5)]

    for i, n in enumerate(d1_s):
        x, y = _ring_pos(i, len(d1_s), 220, jitter=22)
        _add_ripple_node(n, "D1", x, y)

    for i, n in enumerate(d2_s):
        x, y = _ring_pos(i, len(d2_s), 430, jitter=35)
        _add_ripple_node(n, "D2", x, y)

    for i, n in enumerate(d3_s):
        x, y = _ring_pos(i, len(d3_s), 640, jitter=40)
        _add_ripple_node(n, "D3", x, y)

    # ── Unaffected — ghost nodes on outer ring ────────────────────────────────
    all_cust = [n for n in G.nodes if n.startswith("cust::")]
    unaffected = [n for n in all_cust
                  if n not in d1_nodes and n not in d2_nodes and n not in d3_nodes]
    _random.seed(42)
    ua_sample = _random.sample(unaffected, min(35, len(unaffected)))
    for i, n in enumerate(ua_sample):
        if n in added_nodes:
            continue
        name = n.replace("cust::", "")
        size = max(4, min(11, int(degree_map.get(name, 3) * 0.65)))
        x, y = _ring_pos(i, len(ua_sample), 860, jitter=80)
        net.add_node(n, label="",
                     color={"background": UNAFFECTED_BG, "border": UNAFFECTED_BORDER},
                     size=size, borderWidth=1, x=x, y=y, physics=False,
                     title=f"{name}\n(Unaffected)")
        added_nodes.add(n)

    # ── Edges — colour matches tier, weight matches proximity ─────────────────
    for b_node in added_brokers:
        for cust_node in G.neighbors(b_node):
            if cust_node not in added_nodes:
                continue
            if cust_node in d1_nodes:
                net.add_edge(b_node, cust_node,
                             color={"color": "#7F1D1D", "opacity": 0.65}, width=1.5)
            elif cust_node in d2_nodes:
                net.add_edge(b_node, cust_node,
                             color={"color": "#F97316", "opacity": 0.4}, width=1.0)
            else:
                net.add_edge(b_node, cust_node,
                             color={"color": "#D1D5DB", "opacity": 0.25}, width=0.5)

    # D1 intra-sector links — visible shared exposure
    for i, c1 in enumerate(d1_s[:15]):
        for c2 in d1_s[i+1:16]:
            shared = set(G.neighbors(c1)) & set(G.neighbors(c2))
            if any(n.startswith("sector::") for n in shared):
                net.add_edge(c1, c2,
                             color={"color": "#7F1D1D", "opacity": 0.3},
                             width=0.8, title="Shared sector exposure")

    return net.generate_html()


# ── 2. Cluster Life Visualisation ─────────────────────────────────────────────

def cluster_life_html(
    highlight_bridges: bool = True,
    max_nodes_per_cluster: int = 20,
    height: str = "600px",
) -> str:
    """
    Build a pyvis HTML showing all 3 KMeans clusters as visual groups.
    Customers colored by cluster. Broker nodes connect across clusters.
    Bridge customers (High Risk connected to Low Risk via broker) highlighted.

    Returns HTML string.
    """
    from pyvis.network import Network
    from src.models.kg_graph_analytics import find_cluster_bridges

    G = _load_graph()
    gm = _load_metrics()
    if G is None or gm.empty:
        return "<p>Graph not available.</p>"

    # Bridge customers
    bridges_df = find_cluster_bridges(top_n=30) if highlight_bridges else pd.DataFrame()
    bridge_set = set(bridges_df["high_risk_customer"].tolist()) if not bridges_df.empty else set()

    net = Network(height=height, width="100%",
                  bgcolor="#0F1117", font_color="#F9FAFB")
    net.set_options("""
    {
      "nodes": {
        "shadow": {"enabled": true, "size": 10, "color": "rgba(0,0,0,0.5)"},
        "font": {"size": 11, "bold": true}
      },
      "edges": {
        "color": {"opacity": 0.3},
        "smooth": {"type": "curvedCW", "roundness": 0.25},
        "selectionWidth": 3
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -45,
          "centralGravity": 0.005,
          "springLength": 140,
          "springConstant": 0.06,
          "damping": 0.4
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"enabled": true, "iterations": 150, "updateInterval": 15, "fit": true}
      },
      "interaction": {"hover": true, "tooltipDelay": 80, "hideEdgesOnDrag": true}
    }
    """)

    CLUSTER_COLOR = {
        "Low Risk":      {"bg": "#22C55E", "border": "#16A34A"},
        "Moderate Risk": {"bg": "#F97316", "border": "#EA580C"},
        "High Risk":     {"bg": "#EF4444", "border": "#DC2626"},
    }
    REC_SHAPE = {"FAST_TRACK": "dot", "STANDARD_UW": "square", "FRESH_UW": "triangle"}

    added = set()
    added_brokers = set()

    for cluster_label, col in CLUSTER_COLOR.items():
        cluster_members = gm[gm["cluster"] == cluster_label].head(max_nodes_per_cluster)
        for _, row in cluster_members.iterrows():
            cust_name = row["customer"]
            cust_node = f"cust::{cust_name}"
            if cust_node not in G.nodes or cust_node in added:
                continue

            is_bridge = cust_name in bridge_set
            bg = "#FF00FF" if is_bridge else col["bg"]   # magenta for bridges
            border = "#FFFFFF" if is_bridge else col["border"]
            size = 28 if is_bridge else 10
            rec = row.get("recommendation", "STANDARD_UW")
            score = row.get("risk_score", 50)
            tooltip = (f"{cust_name}\n"
                      f"Cluster: {cluster_label}\n"
                      f"Score: {score}/100\nRec: {rec}"
                      + ("\n⚡ BRIDGE NODE" if is_bridge else ""))

            net.add_node(cust_node, label=cust_name[:15],
                         color={"background": bg, "border": border},
                         size=size,
                         shape=REC_SHAPE.get(rec, "dot"),
                         title=tooltip)
            added.add(cust_node)

            # Add connected brokers
            for nb in G.neighbors(cust_node):
                if nb.startswith("broker::") and nb not in added_brokers:
                    bname = nb.replace("broker::", "")[:18]
                    n_cust = sum(1 for n in G.neighbors(nb) if n.startswith("cust::"))
                    if n_cust >= 5:  # only significant brokers
                        net.add_node(nb, label=bname,
                                     color={"background": "#F97316", "border": "#C2410C"},
                                     size=25, shape="diamond",
                                     title=f"Broker: {bname}\n{n_cust} portfolio customers")
                        added_brokers.add(nb)

    # Add broker → customer edges
    for b_node in added_brokers:
        for cust_node in G.neighbors(b_node):
            if cust_node in added:
                cust_cluster = gm[gm["customer"] == cust_node.replace("cust::", "")]["cluster"].values
                cl = cust_cluster[0] if len(cust_cluster) > 0 else ""
                edge_col = {"Low Risk": "#22C55E", "High Risk": "#EF4444"}.get(cl, "#6B7280")
                net.add_edge(b_node, cust_node,
                             color={"color": edge_col, "opacity": 0.3}, width=1)

    # Bridge cross-cluster edges (magenta)
    if highlight_bridges and not bridges_df.empty:
        for _, row in bridges_df.head(10).iterrows():
            hr_node = f"cust::{row['high_risk_customer']}"
            broker_node = f"broker::{row['broker']}"
            if hr_node in added and broker_node in added_brokers:
                net.add_edge(hr_node, broker_node,
                             color={"color": "#FF00FF", "opacity": 0.8},
                             width=3, title="BRIDGE: High Risk → Low Risk path")

    return net.generate_html()
