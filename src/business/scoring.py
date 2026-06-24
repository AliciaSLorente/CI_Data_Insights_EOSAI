"""
Risk scoring and recommendation logic.
Explicit, auditable rules for underwriting decisions.
"""

from src.business.models import Submission, Delta, RiskScore
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ScoringRules:
    """Explicit scoring rules for risk assessment."""
    
    # Weights
    REVENUE_DELTA_WEIGHT = 0.5  # % change matters
    EMPLOYEE_DELTA_WEIGHT = 0.3
    CONTROL_REGRESSION_WEIGHT = 10.0  # Each regressed control = 10 points
    CONTROL_IMPROVEMENT_WEIGHT = -5.0  # Each improved control = -5 points
    DECISION_CHANGE_WEIGHT = 15.0  # Declined to Quoted = big red flag
    
    @staticmethod
    def compute_revenue_delta_risk(delta_pct: Optional[float]) -> float:
        """
        Revenue change impact on risk.
        
        Logic:
        - ±5% = normal, no impact
        - ±20% = moderate, +/- 10 points
        - ±50%+ = significant, +/- 25 points
        """
        if delta_pct is None:
            return 0.0
        
        abs_delta = abs(delta_pct)
        if abs_delta <= 5:
            return 0.0
        elif abs_delta <= 20:
            return (abs_delta - 5) / 15 * 10 * (1 if delta_pct > 0 else -1)
        else:
            return 25 * (1 if delta_pct > 0 else -1)
    
    @staticmethod
    def compute_control_regression_risk(controls_degraded: List[str], 
                                       controls_improved: List[str]) -> float:
        """
        Control changes impact on risk.
        
        Logic:
        - Each degraded control = +10 points
        - Each improved control = -5 points
        """
        degradation_risk = len(controls_degraded) * ScoringRules.CONTROL_REGRESSION_WEIGHT
        improvement_credit = len(controls_improved) * ScoringRules.CONTROL_IMPROVEMENT_WEIGHT
        return degradation_risk + improvement_credit
    
    @staticmethod
    def compute_decision_change_risk(decision_from: Optional[str], 
                                    decision_to: Optional[str]) -> float:
        """
        Decision pattern impact on risk.
        
        Logic:
        - Declined → Quoted = +25 (why did they reapply after decline?)
        - Quoted → Declined = +20 (we changed appetite?)
        - Rated → Quoted = +10 (backsliding)
        - Quoted → Rated = -15 (good progress)
        """
        if not decision_from or not decision_to or decision_from == decision_to:
            return 0.0
        
        pattern = f"{decision_from}→{decision_to}"
        weights = {
            "Declined→Quoted": 25,
            "Quoted→Declined": 20,
            "Rated→Quoted": 10,
            "Quoted→Rated": -15,
            "Declined→Rated": -10,
        }
        return weights.get(pattern, 5)
    
    @staticmethod
    def base_score_from_delta(delta: Delta) -> float:
        """
        Compute risk score (0-100) from submission delta.
        
        Base = 50 (neutral)
        Add/subtract points based on changes
        """
        base = 50.0
        
        # Revenue change
        base += ScoringRules.compute_revenue_delta_risk(delta.revenue_delta_pct)
        
        # Employee change (employees often correlate with complexity)
        if delta.employee_delta is not None:
            pct_change = (delta.employee_delta / 100) if delta.employee_delta != 0 else 0
            base += ScoringRules.compute_revenue_delta_risk(pct_change * 100)
        
        # Control changes
        base += ScoringRules.compute_control_regression_risk(
            delta.controls_degraded,
            delta.controls_improved
        )
        
        # Decision history
        base += ScoringRules.compute_decision_change_risk(
            delta.decision_from,
            delta.decision_to
        )
        
        # Clamp to 0-100
        return max(0, min(100, base))


class Recommender:
    """Generate underwriting recommendations based on risk score."""
    
    # Thresholds
    FAST_TRACK_THRESHOLD = 35  # score < 35 = low risk
    FRESH_UW_THRESHOLD = 65  # score >= 65 = high risk, needs fresh review
    
    @staticmethod
    def recommend(risk_score: RiskScore, 
                 peer_approval_rate: Optional[float] = None,
                 is_anomaly: bool = False) -> Dict:
        """
        Generate recommendation with reasoning.
        
        Args:
            risk_score: RiskScore object
            peer_approval_rate: Approval rate of similar customers (0-1)
            is_anomaly: Is this submission flagged as anomalous?
        
        Returns:
            {
                "recommendation": "FAST_TRACK" | "STANDARD_UW" | "FRESH_UW",
                "confidence": 0-1,
                "reasoning": [list of reasons],
            }
        """
        score = risk_score.score
        reasoning = []
        
        # Check anomaly first
        if is_anomaly:
            return {
                "recommendation": "FRESH_UW",
                "confidence": 0.95,
                "reasoning": [
                    "Submission breaks peer-group patterns → anomalous risk profile",
                    "Recommend fresh underwriting review"
                ]
            }
        
        # Score-based recommendation
        if score < Recommender.FAST_TRACK_THRESHOLD:
            recommendation = "FAST_TRACK"
            confidence = 1.0 - (score / Recommender.FAST_TRACK_THRESHOLD * 0.1)
            reasoning.append(
                f"Low risk score ({score:.0f}) indicates stable, low-change submission"
            )
            
            if peer_approval_rate and peer_approval_rate >= 0.8:
                reasoning.append(
                    f"Similar customers have {peer_approval_rate:.0%} approval rate → precedent for approval"
                )
                confidence = min(1.0, confidence + 0.1)
        
        elif score >= Recommender.FRESH_UW_THRESHOLD:
            recommendation = "FRESH_UW"
            confidence = min(1.0, (score - Recommender.FRESH_UW_THRESHOLD) / 35 * 0.2 + 0.8)
            reasoning.append(
                f"High risk score ({score:.0f}) indicates material changes → requires fresh underwriting"
            )
            
            if peer_approval_rate and peer_approval_rate <= 0.5:
                reasoning.append(
                    f"Peer group has {peer_approval_rate:.0%} approval rate → heightened scrutiny recommended"
                )
                confidence = min(1.0, confidence + 0.1)
        
        else:
            recommendation = "STANDARD_UW"
            confidence = 0.75
            reasoning.append(
                f"Moderate risk score ({score:.0f}) → standard underwriting process"
            )
        
        # Add component breakdown
        if risk_score.components:
            reasoning.append("Score breakdown:")
            for component, value in risk_score.components.items():
                if value != 0:
                    reasoning.append(f"  - {component}: {value:+.1f}")
        
        return {
            "recommendation": recommendation,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
        }
    
    @staticmethod
    def batch_recommend(risk_scores: List[RiskScore], 
                       peer_rates: Dict[str, float] = None,
                       anomalies: List[str] = None) -> List[Dict]:
        """
        Recommend for multiple submissions.
        
        Returns list of recommendation dicts, one per risk_score.
        """
        if peer_rates is None:
            peer_rates = {}
        if anomalies is None:
            anomalies = []
        
        recommendations = []
        for rs in risk_scores:
            is_anom = rs.submission_id in anomalies
            peer_rate = peer_rates.get(rs.customer_id)
            rec = Recommender.recommend(rs, peer_approval_rate=peer_rate, is_anomaly=is_anom)
            rec["submission_id"] = rs.submission_id
            recommendations.append(rec)
        
        return recommendations


# Usage example
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create a delta
    delta = Delta(
        from_submission_id="sub_001",
        to_submission_id="sub_002",
        months_between=24,
        revenue_delta_pct=15.0,  # Revenue up 15%
        controls_degraded=["MFA"],
        controls_improved=["Firewall"],
        decision_from="Rated",
        decision_to="Quoted"
    )
    
    # Score it
    score_value = ScoringRules.base_score_from_delta(delta)
    risk_score = RiskScore(
        submission_id="sub_002",
        customer_id="cust_001",
        score=score_value,
        components={
            "revenue_delta": ScoringRules.compute_revenue_delta_risk(delta.revenue_delta_pct),
            "control_changes": ScoringRules.compute_control_regression_risk(
                delta.controls_degraded, delta.controls_improved
            ),
            "decision_change": ScoringRules.compute_decision_change_risk(
                delta.decision_from, delta.decision_to
            ),
        }
    )
    
    # Recommend
    recommendation = Recommender.recommend(risk_score, peer_approval_rate=0.85)
    print(f"Score: {risk_score.score:.1f}")
    print(f"Recommendation: {recommendation['recommendation']}")
    print(f"Confidence: {recommendation['confidence']}")
    print("Reasoning:")
    for r in recommendation['reasoning']:
        print(f"  - {r}")
