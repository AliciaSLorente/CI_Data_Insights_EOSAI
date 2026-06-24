"""
AI Governance module — EU AI Act aligned.
Provides: audit trail, bias metrics, human oversight tracking, compliance checklist.
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

DB_PATH = Path("data/parsed/cache.db")
DATA_DIR = Path("data/parsed")

EU_ACT_CHECKLIST = [
    {
        "article": "Art. 9 — Risk Management",
        "requirement": "Continuous risk management system in place",
        "status": "partial",
        "notes": "Rule-based scoring provides auditable risk assessment. Full lifecycle monitoring pending.",
    },
    {
        "article": "Art. 10 — Data Governance",
        "requirement": "Training/validation data quality controls",
        "status": "partial",
        "notes": "Parsed CSVs from validated sources. Full data lineage documentation needed.",
    },
    {
        "article": "Art. 13 — Transparency",
        "requirement": "Users informed they are interacting with an AI system",
        "status": "compliant",
        "notes": "All recommendations labelled 'Advisory only — Human review required'.",
    },
    {
        "article": "Art. 14 — Human Oversight",
        "requirement": "Humans can intervene, override, and halt AI decisions",
        "status": "compliant",
        "notes": "All outputs are advisory. Override flag captured in audit log per recommendation.",
    },
    {
        "article": "Art. 15 — Accuracy & Robustness",
        "requirement": "System performs consistently and handles edge cases",
        "status": "partial",
        "notes": "Confidence thresholds implemented. Full adversarial testing pending.",
    },
    {
        "article": "Art. 52 — Transparency Obligations",
        "requirement": "AI-generated content clearly labelled",
        "status": "compliant",
        "notes": "All Claude-generated narratives include AI disclosure banner.",
    },
    {
        "article": "Annex III — High-Risk Classification",
        "requirement": "System registered as high-risk AI (insurance risk assessment)",
        "status": "pending",
        "notes": "Must register with EU AI Act database before production deployment.",
    },
    {
        "article": "Art. 17 — Quality Management",
        "requirement": "Post-market monitoring and incident reporting",
        "status": "pending",
        "notes": "Audit log in place. Formal incident reporting process to be defined.",
    },
]


class AuditLogger:
    def __init__(self, db_path: str = str(DB_PATH)):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                customer_name TEXT,
                risk_score REAL,
                recommendation TEXT,
                confidence REAL,
                components TEXT,
                human_reviewed INTEGER DEFAULT 0,
                human_decision TEXT,
                override_reason TEXT,
                session_id TEXT
            )
        """)
        self.conn.commit()

    def log_recommendation(
        self,
        customer_name: str,
        risk_score: float,
        recommendation: str,
        confidence: float,
        components: Dict = None,
        session_id: str = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO audit_log
              (timestamp, customer_name, risk_score, recommendation,
               confidence, components, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                customer_name,
                risk_score,
                recommendation,
                confidence,
                json.dumps(components or {}),
                session_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def mark_human_reviewed(
        self,
        log_id: int,
        human_decision: str,
        override_reason: str = None,
    ):
        self.conn.execute(
            """
            UPDATE audit_log
            SET human_reviewed=1, human_decision=?, override_reason=?
            WHERE id=?
            """,
            (human_decision, override_reason, log_id),
        )
        self.conn.commit()

    def get_audit_log(self, limit: int = 100) -> pd.DataFrame:
        df = pd.read_sql(
            f"SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT {limit}",
            self.conn,
        )
        return df

    def get_human_override_rate(self) -> Dict:
        df = self.get_audit_log(limit=10000)
        if df.empty:
            return {"total": 0, "reviewed": 0, "overridden": 0, "override_rate": 0.0, "review_rate": 0.0}

        total = len(df)
        reviewed = df["human_reviewed"].sum()
        overridden = ((df["human_reviewed"] == 1) & (df["human_decision"] != df["recommendation"])).sum()

        return {
            "total": total,
            "reviewed": int(reviewed),
            "overridden": int(overridden),
            "override_rate": round(overridden / reviewed, 3) if reviewed > 0 else 0.0,
            "review_rate": round(reviewed / total, 3) if total > 0 else 0.0,
        }


def compute_bias_metrics(df_recs: pd.DataFrame = None) -> Dict:
    """
    Compute approval-rate bias metrics across available dimensions.
    Uses sample_recommendations.csv if no df provided.
    """
    if df_recs is None:
        path = DATA_DIR / "sample_recommendations.csv"
        if path.exists():
            df_recs = pd.read_csv(path)
        else:
            return {"error": "No recommendation data available"}

    if df_recs.empty:
        return {"error": "Empty dataset"}

    total = len(df_recs)
    fast_track_rate = (df_recs["recommendation"] == "FAST_TRACK").sum() / total
    fresh_uw_rate = (df_recs["recommendation"] == "FRESH_UW").sum() / total
    mean_score = df_recs["risk_score"].mean()
    std_score = df_recs["risk_score"].std()

    # Score distribution by recommendation bucket
    dist = df_recs.groupby("recommendation")["risk_score"].agg(["mean", "count", "std"]).round(2)

    return {
        "total_scored": total,
        "fast_track_rate": round(fast_track_rate, 3),
        "fresh_uw_rate": round(fresh_uw_rate, 3),
        "mean_risk_score": round(mean_score, 1),
        "std_risk_score": round(std_score, 1),
        "distribution_by_recommendation": dist.to_dict(),
        "bias_flags": _check_bias_flags(df_recs, fast_track_rate, fresh_uw_rate),
    }


def _check_bias_flags(df: pd.DataFrame, fast_rate: float, fresh_rate: float) -> List[Dict]:
    flags = []

    if fast_rate > 0.5:
        flags.append({
            "flag": "HIGH_FAST_TRACK_RATE",
            "severity": "MEDIUM",
            "message": f"{fast_rate:.0%} of submissions are Fast-Track — validate thresholds are not too permissive",
        })

    if fresh_rate > 0.4:
        flags.append({
            "flag": "HIGH_FRESH_UW_RATE",
            "severity": "MEDIUM",
            "message": f"{fresh_rate:.0%} of submissions require Fresh UW — check for data quality issues",
        })

    score_range = df["risk_score"].max() - df["risk_score"].min()
    if score_range < 10:
        flags.append({
            "flag": "LOW_SCORE_VARIANCE",
            "severity": "LOW",
            "message": "Score range is narrow — scoring rules may not be discriminative enough",
        })

    return flags


def eu_act_compliance_status() -> List[Dict]:
    return EU_ACT_CHECKLIST


def compliance_summary() -> Dict:
    checklist = eu_act_compliance_status()
    by_status = {"compliant": 0, "partial": 0, "pending": 0}
    for item in checklist:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    total = len(checklist)
    score = (by_status["compliant"] + 0.5 * by_status["partial"]) / total
    return {
        "total_requirements": total,
        "compliant": by_status["compliant"],
        "partial": by_status["partial"],
        "pending": by_status["pending"],
        "compliance_score": round(score, 2),
        "overall_status": "COMPLIANT" if score >= 0.8 else ("PARTIAL" if score >= 0.5 else "NON_COMPLIANT"),
    }
