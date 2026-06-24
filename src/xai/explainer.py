"""
XAI (Explainable AI) module.
Rule-contribution waterfall charts + Claude-generated narratives.

Note: Since scoring is rule-based (not a black-box ML model), we use
contribution decomposition — equivalent to SHAP for linear/additive models.
"""

import os
import json
import plotly.graph_objects as go
from typing import Dict, List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

BASELINE_SCORE = 50.0  # Neutral starting point in ScoringRules


def waterfall_chart(
    components: Dict[str, float],
    final_score: float,
    customer_name: str = "Customer",
    baseline: float = BASELINE_SCORE,
) -> go.Figure:
    """
    Build a SHAP-style waterfall chart from rule contribution components.

    components: {"revenue_delta": 15.0, "control_changes": -5.0, "decision_change": 10.0}
    final_score: the final clamped score (0-100)
    """
    labels = ["Baseline"]
    values = [baseline]
    measures = ["absolute"]
    text = [f"{baseline:.0f}"]
    colors = ["#636EFA"]

    for name, contribution in components.items():
        label = name.replace("_", " ").title()
        labels.append(label)
        values.append(contribution)
        measures.append("relative")
        sign = "+" if contribution >= 0 else ""
        text.append(f"{sign}{contribution:.1f}")
        colors.append("#EF553B" if contribution > 0 else "#00CC96")

    # Final bar — show actual final score, not computed sum (due to clamping)
    labels.append("Final Score")
    values.append(final_score)
    measures.append("total")
    text.append(f"{final_score:.0f}")
    colors.append("#AB63FA")

    fig = go.Figure(go.Waterfall(
        name="Score",
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        text=text,
        textposition="outside",
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        increasing={"marker": {"color": "#EF553B"}},
        decreasing={"marker": {"color": "#00CC96"}},
        totals={"marker": {"color": "#AB63FA"}},
    ))

    fig.update_layout(
        title=f"Risk Score Breakdown — {customer_name}",
        yaxis_title="Score (0–100)",
        yaxis=dict(range=[0, 110]),
        showlegend=False,
        height=400,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(size=13),
    )

    # Add threshold lines
    fig.add_hline(y=35, line_dash="dot", line_color="#00CC96",
                  annotation_text="Fast-Track threshold (35)", annotation_position="right")
    fig.add_hline(y=65, line_dash="dot", line_color="#EF553B",
                  annotation_text="Fresh UW threshold (65)", annotation_position="right")

    return fig


def generate_narrative(
    customer_name: str,
    score: float,
    recommendation: str,
    components: Dict[str, float],
    reasoning: List[str],
    peer_approval_rate: Optional[float] = None,
) -> str:
    """
    Generate a plain-language XAI narrative using Claude API.
    Returns markdown text suitable for display.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_narrative(customer_name, score, recommendation, components, reasoning)

    client = anthropic.Anthropic(api_key=api_key)

    component_text = "\n".join(
        f"  - {k.replace('_', ' ').title()}: {v:+.1f} points"
        for k, v in components.items()
    )
    reasoning_text = "\n".join(f"  - {r}" for r in reasoning)
    peer_text = f"\n- Peer group approval rate: {peer_approval_rate:.0%}" if peer_approval_rate else ""

    prompt = f"""You are an expert insurance underwriting assistant. Generate a concise, professional explanation
of an AI risk assessment for an underwriter.

Customer: {customer_name}
Risk Score: {score:.0f}/100 (0=lowest risk, 100=highest risk)
Recommendation: {recommendation}
Score Components (from baseline of 50):
{component_text}
Rule Reasoning:
{reasoning_text}{peer_text}

Write a 3-4 sentence explanation in plain English that:
1. States the recommendation and score clearly
2. Explains the 1-2 most significant drivers (positive and negative)
3. Notes any specific risk or opportunity for the underwriter to focus on
4. Ends with a reminder that human review is required

Format: plain paragraphs, no bullet points, professional tone. Max 120 words."""

    try:
        model = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-4-6")
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        client = OpenAI(
            api_key=api_key,
            base_url=f"{base_url}/v1" if base_url else None,
        )
        response = client.chat.completions.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.choices[0].message.content
        return narrative + "\n\n*⚠️ Advisory only — human underwriter decision required.*"
    except Exception as e:
        return _fallback_narrative(customer_name, score, recommendation, components, reasoning)


def _fallback_narrative(
    customer_name: str,
    score: float,
    recommendation: str,
    components: Dict[str, float],
    reasoning: List[str],
) -> str:
    top_driver = max(components.items(), key=lambda x: abs(x[1]), default=("N/A", 0))
    direction = "elevated" if top_driver[1] > 0 else "reduced"
    return (
        f"**{customer_name}** received a risk score of **{score:.0f}/100**, "
        f"resulting in a **{recommendation}** recommendation. "
        f"The primary driver was **{top_driver[0].replace('_', ' ')}** "
        f"({top_driver[1]:+.1f} pts), which {direction} the score from baseline. "
        f"\n\n*⚠️ Advisory only — human underwriter decision required.*"
    )


def explain(
    customer_name: str,
    score: float,
    recommendation: str,
    components: Dict[str, float],
    reasoning: List[str] = None,
    peer_approval_rate: Optional[float] = None,
) -> Dict:
    """
    Full XAI explanation: waterfall chart + narrative.
    Returns {"chart": go.Figure, "narrative": str}.
    """
    reasoning = reasoning or []
    chart = waterfall_chart(components, score, customer_name)
    narrative = generate_narrative(
        customer_name, score, recommendation, components, reasoning, peer_approval_rate
    )
    return {"chart": chart, "narrative": narrative}
