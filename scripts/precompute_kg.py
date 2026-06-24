"""
Pre-compute all KG analytics offline and save to CSVs.
Run this once after mass_scoring.py and mass_deltas.py.

Output files (data/parsed/):
  kg_clusters.csv            - Risk cluster assignment for each customer
  kg_clusters_summary.csv    - Cluster summary stats (3 rows)
  kg_emerging_risks.csv      - Emerging risk signals (broker/sector trends)
  kg_whitespace.csv          - Growth whitespace opportunities
  kg_retention_risk.csv      - Retention risk scores per customer
  kg_reapplication.csv       - Re-application analysis
  kg_cascade_vulnerable.csv  - Cascade vulnerability scores per customer
  kg_concentration.csv       - Broker x product concentration pivot
  kg_leading_indicators.csv  - Sectors with systematic deterioration
"""

import pandas as pd
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

DATA = Path("data/parsed")


def run(label: str, fn, out_path: Path, force: bool = False):
    if out_path.exists() and not force:
        print(f"  SKIP {out_path.name} (already exists — use force=True to regenerate)")
        return
    print(f"  Computing {label}...", end=" ", flush=True)
    try:
        result = fn()
        if isinstance(result, pd.DataFrame):
            result.to_csv(out_path, index=False)
            print(f"OK ({len(result):,} rows)")
        elif isinstance(result, tuple):
            # concentration_heatmap returns (pivot, metrics)
            pivot, metrics = result
            pivot.to_csv(out_path, index=True)
            metrics_df = pd.DataFrame([metrics])
            metrics_df.to_csv(str(out_path).replace(".csv", "_metrics.csv"), index=False)
            print(f"OK (pivot {pivot.shape})")
        else:
            print(f"SKIP (unexpected type: {type(result)})")
    except Exception as e:
        print(f"ERROR: {e}")


def main(force: bool = False):
    print("=" * 60)
    print("KG Pre-compute Pipeline")
    print("=" * 60)

    # ── 1. KG clusters ────────────────────────────────────────────
    print("\n[1/8] Risk Clusters")
    from src.models.kg_real import compute_risk_clusters, risk_clusters_summary
    run("cluster assignments", compute_risk_clusters,
        DATA / "kg_clusters.csv", force)
    run("cluster summary", risk_clusters_summary,
        DATA / "kg_clusters_summary.csv", force)

    # ── 2. Emerging risks ─────────────────────────────────────────
    print("\n[2/8] Emerging Risks")
    from src.models.kg_real import detect_emerging_risks
    def emerging_df():
        signals = detect_emerging_risks()
        return pd.DataFrame(signals) if signals else pd.DataFrame()
    run("emerging risk signals", emerging_df,
        DATA / "kg_emerging_risks.csv", force)

    # ── 3. Growth whitespace ──────────────────────────────────────
    print("\n[3/8] Growth Whitespace")
    from src.models.kg_real import find_growth_whitespace
    def whitespace_df():
        opps = find_growth_whitespace()
        rows = []
        for o in opps:
            row = {k: v for k, v in o.items() if k != "examples"}
            rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    run("whitespace opportunities", whitespace_df,
        DATA / "kg_whitespace.csv", force)

    # ── 4. Retention risk ─────────────────────────────────────────
    print("\n[4/8] Retention Risk")
    from src.models.kg_metrics import retention_risk_customers
    run("retention risk scores", lambda: retention_risk_customers(top_n=500),
        DATA / "kg_retention_risk.csv", force)

    # ── 5. Re-application analysis ────────────────────────────────
    print("\n[5/8] Re-application Analysis")
    from src.models.kg_metrics import reapplication_analysis
    run("reapplication outcomes", reapplication_analysis,
        DATA / "kg_reapplication.csv", force)

    # ── 6. Cascade vulnerability ──────────────────────────────────
    print("\n[6/8] Cascade Vulnerability")
    from src.models.cascade_risk import predict_cascade_vulnerable
    run("cascade vulnerability scores", lambda: predict_cascade_vulnerable(top_n=500),
        DATA / "kg_cascade_vulnerable.csv", force)

    # ── 7. Concentration heatmap ──────────────────────────────────
    print("\n[7/8] Concentration Heatmap")
    from src.models.cascade_risk import concentration_heatmap
    run("concentration pivot", concentration_heatmap,
        DATA / "kg_concentration.csv", force)

    # ── 8. Leading indicators ─────────────────────────────────────
    print("\n[8/8] Leading Indicators")
    from src.models.cascade_risk import leading_indicators
    run("leading indicators", leading_indicators,
        DATA / "kg_leading_indicators.csv", force)

    # ── Bonus: broker performance ─────────────────────────────────
    print("\n[+] Broker Performance")
    from src.data.dashboard_data import broker_performance
    run("broker performance", lambda: broker_performance(30),
        DATA / "kg_broker_performance.csv", force)

    print("\n" + "=" * 60)
    print("Done. Files written to data/parsed/kg_*.csv")
    print("Run 'Refresh Data' in the dashboard to reload.")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Recompute even if output files already exist")
    args = parser.parse_args()
    main(force=args.force)
