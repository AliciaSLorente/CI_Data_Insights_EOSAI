"""
Knowledge graph builder: Construct NetworkX graph from parsed submissions.
Supports pattern discovery, clustering, and anomaly detection.
"""

import networkx as nx
from typing import Dict, List, Tuple
import logging
from sklearn.cluster import KMeans
import numpy as np

logger = logging.getLogger(__name__)

class KnowledgeGraphBuilder:
    def __init__(self):
        self.G = nx.DiGraph()
        self.clusters = {}  # {customer_id: cluster_id}
    
    def add_customer_node(self, customer_id: str, name: str, lob: str, **attrs):
        """Add customer node to graph."""
        self.G.add_node(
            f"cust_{customer_id}",
            node_type="customer",
            name=name,
            lob=lob,
            **attrs
        )
    
    def add_submission_node(self, submission_id: str, customer_id: str, 
                           date: str, status: str, risk_score: float, **attrs):
        """Add submission node to graph."""
        self.G.add_node(
            f"sub_{submission_id}",
            node_type="submission",
            customer_id=customer_id,
            date=date,
            status=status,
            risk_score=risk_score,
            **attrs
        )
        # Link submission to customer
        self.G.add_edge(
            f"cust_{customer_id}",
            f"sub_{submission_id}",
            relationship="submitted",
            weight=1.0
        )
    
    def add_control_node(self, control_name: str, category: str, maturity: int = 3):
        """Add control node to graph."""
        node_id = f"ctrl_{control_name.lower().replace(' ', '_')}"
        self.G.add_node(
            node_id,
            node_type="control",
            name=control_name,
            category=category,
            maturity=maturity
        )
        return node_id
    
    def add_submission_control_edge(self, submission_id: str, control_node_id: str, 
                                   present: bool = True, maturity: int = 3):
        """Link submission to control."""
        self.G.add_edge(
            f"sub_{submission_id}",
            control_node_id,
            relationship="has_control",
            present=present,
            maturity=maturity
        )
    
    def add_broker_node(self, broker_name: str, approval_rate: float = 0.5):
        """Add broker node to graph."""
        node_id = f"broker_{broker_name.lower().replace(' ', '_')}"
        self.G.add_node(
            node_id,
            node_type="broker",
            name=broker_name,
            approval_rate=approval_rate
        )
        return node_id
    
    def add_customer_broker_edge(self, customer_id: str, broker_node_id: str):
        """Link customer to broker."""
        self.G.add_edge(
            f"cust_{customer_id}",
            broker_node_id,
            relationship="works_with"
        )
    
    def detect_risk_clusters(self, features_dict: Dict[str, np.ndarray], n_clusters: int = 3):
        """
        Cluster customers by risk profile (revenue, controls, history).
        
        Args:
            features_dict: {customer_id: feature_vector}
            n_clusters: number of clusters
        """
        customer_ids = list(features_dict.keys())
        X = np.array([features_dict[cid] for cid in customer_ids])
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        labels = kmeans.fit_predict(X)
        
        for i, cid in enumerate(customer_ids):
            cluster_id = labels[i]
            self.clusters[cid] = cluster_id
            cluster_node = f"cluster_{cluster_id}"
            
            # Add cluster node if not exists
            if not self.G.has_node(cluster_node):
                self.G.add_node(cluster_node, node_type="cluster", id=cluster_id)
            
            # Link customer to cluster
            self.G.add_edge(f"cust_{cid}", cluster_node, relationship="belongs_to")
        
        logger.info(f"Detected {n_clusters} risk clusters")
        return self.clusters
    
    def find_similar_customers(self, customer_id: str, n_similar: int = 5) -> List[str]:
        """Find customers in same cluster."""
        cluster_id = self.clusters.get(customer_id)
        if cluster_id is None:
            return []
        
        cluster_node = f"cluster_{cluster_id}"
        similar_custs = []
        
        for node in self.G.predecessors(cluster_node):
            if node.startswith("cust_") and node != f"cust_{customer_id}":
                similar_custs.append(node.replace("cust_", ""))
                if len(similar_custs) >= n_similar:
                    break
        
        return similar_custs
    
    def compute_control_impact(self) -> Dict[str, float]:
        """
        Compute impact of each control on approval rates.
        Returns {control_name: impact_score}
        """
        control_impact = {}
        
        # Iterate through control nodes
        for node in self.G.nodes():
            if self.G.nodes[node].get("node_type") == "control":
                # Find submissions with this control
                submissions_with = list(self.G.predecessors(node))
                if submissions_with:
                    # Estimate impact (placeholder: higher maturity = positive impact)
                    maturity = self.G.nodes[node].get("maturity", 3)
                    control_impact[self.G.nodes[node].get("name")] = maturity / 5.0
        
        return control_impact
    
    def flag_anomalies(self, threshold: float = 0.7) -> List[Tuple[str, float]]:
        """
        Flag submissions that break their cluster patterns.
        Returns [(submission_id, anomaly_score)]
        """
        anomalies = []
        
        # Placeholder: submissions with very different risk score from cluster average
        for cluster_id in set(self.clusters.values()):
            cluster_node = f"cluster_{cluster_id}"
            members = [n.replace("cust_", "") for n in self.G.predecessors(cluster_node)]
            
            # Get average risk in cluster
            avg_risk = 0
            submissions_in_cluster = []
            for cust_id in members:
                for sub_node in self.G.successors(f"cust_{cust_id}"):
                    if sub_node.startswith("sub_"):
                        risk_score = self.G.nodes[sub_node].get("risk_score", 50)
                        avg_risk += risk_score
                        submissions_in_cluster.append((sub_node, risk_score))
            
            if submissions_in_cluster:
                avg_risk /= len(submissions_in_cluster)
                
                # Flag outliers
                for sub_node, risk_score in submissions_in_cluster:
                    if abs(risk_score - avg_risk) / avg_risk > threshold:
                        anomaly_score = min(1.0, abs(risk_score - avg_risk) / avg_risk)
                        anomalies.append((sub_node, anomaly_score))
        
        logger.info(f"Flagged {len(anomalies)} anomalies")
        return anomalies
    
    def get_graph_stats(self) -> dict:
        """Return graph statistics."""
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "clusters": len(set(self.clusters.values())),
        }
    
    def export_graph(self, filepath: str):
        """Export graph to file (GraphML format)."""
        nx.write_graphml(self.G, filepath)
        logger.info(f"Exported graph to {filepath}")

    # ── Knowledge Discovery Queries ────────────────────────────────────────────

    def find_risk_clusters_summary(self) -> list:
        """
        Summarise each detected risk cluster.
        Returns list of dicts with cluster id, size, avg risk, top controls.
        """
        if not self.clusters:
            return []

        cluster_ids = set(self.clusters.values())
        summaries = []

        for cid in sorted(cluster_ids):
            members = [k for k, v in self.clusters.items() if v == cid]
            risk_scores = []
            controls_seen = []

            for cust in members:
                for sub_node in self.G.successors(f"cust_{cust}"):
                    if sub_node.startswith("sub_"):
                        risk_scores.append(self.G.nodes[sub_node].get("risk_score", 50))
                        for ctrl_node in self.G.successors(sub_node):
                            if ctrl_node.startswith("ctrl_"):
                                controls_seen.append(self.G.nodes[ctrl_node].get("name", ctrl_node))

            from collections import Counter
            top_controls = [c for c, _ in Counter(controls_seen).most_common(3)]
            summaries.append({
                "cluster_id": cid,
                "customer_count": len(members),
                "avg_risk_score": round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else None,
                "top_controls": top_controls,
                "customers": members[:5],
            })

        return summaries

    def detect_emerging_risks(self, df_submissions=None, sector: str = None) -> list:
        """
        Detect correlated risk signals across customers in the graph.
        Looks for customers sharing the same broker with simultaneous control degradation.
        Returns list of risk signal dicts.
        """
        signals = []

        # Find brokers connected to multiple customers
        broker_nodes = [n for n in self.G.nodes if n.startswith("broker_")]
        for broker_node in broker_nodes:
            customers = [n for n in self.G.predecessors(broker_node) if n.startswith("cust_")]
            if len(customers) < 2:
                continue

            # Check how many have high-risk submissions
            high_risk_custs = []
            for cust in customers:
                for sub in self.G.successors(cust):
                    if sub.startswith("sub_"):
                        score = self.G.nodes[sub].get("risk_score", 0)
                        if score >= 65:
                            high_risk_custs.append(cust.replace("cust_", ""))
                            break

            if len(high_risk_custs) >= 2:
                broker_name = self.G.nodes[broker_node].get("name", broker_node)
                signals.append({
                    "signal_type": "correlated_broker_risk",
                    "broker": broker_name,
                    "affected_customers": high_risk_custs,
                    "count": len(high_risk_custs),
                    "severity": "HIGH" if len(high_risk_custs) >= 3 else "MEDIUM",
                    "recommendation": f"Review all {broker_name} submissions — {len(high_risk_custs)} customers show simultaneous risk elevation",
                })

        # Cluster-level risk drift: clusters where avg score has increased
        for summary in self.find_risk_clusters_summary():
            if summary["avg_risk_score"] and summary["avg_risk_score"] > 60:
                signals.append({
                    "signal_type": "cluster_risk_drift",
                    "cluster_id": summary["cluster_id"],
                    "avg_score": summary["avg_risk_score"],
                    "severity": "HIGH" if summary["avg_risk_score"] > 75 else "MEDIUM",
                    "recommendation": f"Cluster {summary['cluster_id']} avg score {summary['avg_risk_score']} — proactive review recommended",
                })

        return signals

    def find_growth_whitespace(self, df_submissions=None) -> list:
        """
        Identify low-risk customer segments that are underrepresented (growth opportunities).
        Returns list of opportunity dicts.
        """
        opportunities = []

        # Low-risk customers with few submissions = untapped potential
        low_risk_customers = []
        for cust_node in self.G.nodes:
            if not cust_node.startswith("cust_"):
                continue
            submissions = [n for n in self.G.successors(cust_node) if n.startswith("sub_")]
            scores = [self.G.nodes[s].get("risk_score", 50) for s in submissions]
            avg_score = sum(scores) / len(scores) if scores else 50

            if avg_score < 45 and len(submissions) <= 2:
                low_risk_customers.append({
                    "customer": cust_node.replace("cust_", ""),
                    "submission_count": len(submissions),
                    "avg_score": round(avg_score, 1),
                })

        if low_risk_customers:
            opportunities.append({
                "opportunity_type": "low_risk_underserved",
                "description": "Customers with excellent risk profile and low submission frequency",
                "count": len(low_risk_customers),
                "examples": low_risk_customers[:5],
                "action": "Proactive outreach — offer streamlined renewal or expanded coverage",
            })

        # Brokers with high approval rate but low volume
        for broker_node in self.G.nodes:
            if not broker_node.startswith("broker_"):
                continue
            approval_rate = self.G.nodes[broker_node].get("approval_rate", 0)
            customers = list(self.G.predecessors(broker_node))
            if approval_rate >= 0.7 and len(customers) <= 3:
                broker_name = self.G.nodes[broker_node].get("name", broker_node)
                opportunities.append({
                    "opportunity_type": "high_quality_broker_low_volume",
                    "broker": broker_name,
                    "approval_rate": approval_rate,
                    "current_customer_count": len(customers),
                    "action": f"Deepen relationship with {broker_name} — {approval_rate:.0%} approval rate with room to grow",
                })

        return opportunities


# Usage example
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    kg = KnowledgeGraphBuilder()
    
    # Add some test data
    kg.add_customer_node("cust_001", "Acme Corp", "Cyber")
    kg.add_submission_node("sub_001", "cust_001", "2022-01-15", "Rated", 45.0)
    kg.add_submission_node("sub_002", "cust_001", "2024-01-15", "Quoted", 52.0)
    
    ctrl = kg.add_control_node("Firewall", "network_security", maturity=4)
    kg.add_submission_control_edge("sub_001", ctrl, present=True, maturity=4)
    kg.add_submission_control_edge("sub_002", ctrl, present=True, maturity=5)
    
    print(kg.get_graph_stats())
