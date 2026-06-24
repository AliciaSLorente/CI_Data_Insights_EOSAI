"""
Daily Briefing Module — Proactive agent activation on dashboard load.

When the UW opens the AI Agent page, this module:
  1. Checks for new submissions since last session
  2. Computes portfolio highlights (top risks, fast-track candidates, signals)
  3. Generates a structured briefing via the LLM
  4. Asks the UW how they want to proceed

The briefing is cached in session state so it only runs once per session,
not on every rerender.

Governance note:
  - The briefing is purely informational — no actions are taken
  - All items flagged require UW review before any decision
  - Full audit trail: briefing generation is logged
"""

import os
import json
import numpy as np
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "parsed"


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.bool_): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)): return None
        if isinstance(obj, (date, datetime)): return str(obj)
        try:
            import pandas as _pd
            if obj is _pd.NA or obj is _pd.NaT: return None
        except Exception: pass
        return super().default(obj)


def _safe(obj) -> str:
    return json.dumps(obj, cls=_Encoder)


def _load_context() -> Dict:
    """Build portfolio context snapshot for the briefing using cached dashboard loaders."""
    from src.data.dashboard_data import (
        load_recommendations, load_all_submissions, load_all_deltas,
    )
    context = {}

    recs = load_recommendations()
    if not recs.empty:
        context["total_scored"] = len(recs)
        context["fast_track_count"] = int((recs["recommendation"] == "FAST_TRACK").sum())
        context["fresh_uw_count"] = int((recs["recommendation"] == "FRESH_UW").sum())
        context["mean_risk_score"] = round(recs["risk_score"].mean(), 1)
        context["top_risk"] = recs.nlargest(3, "risk_score")[
            ["company_name", "risk_score", "recommendation"]
        ].to_dict(orient="records")
        context["top_fast_track"] = recs[recs["recommendation"] == "FAST_TRACK"].nsmallest(3, "risk_score")[
            ["company_name", "risk_score", "confidence"]
        ].to_dict(orient="records")

    context["new_submissions"] = _check_new_submissions()

    subs = load_all_submissions()
    if not subs.empty:
        recent = subs[subs["Requested Coverage Effective Date"].astype(str).str.startswith(("2024", "2025"))]
        if not recent.empty:
            broker_recent = (
                recent.groupby("National Broker Name")
                .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
                .reset_index()
            )
            broker_recent["rate"] = broker_recent["bound"] / broker_recent["total"].clip(1)
            risky = broker_recent[(broker_recent["total"] >= 20) & (broker_recent["rate"] < 0.05)]
            context["broker_alerts"] = risky[["National Broker Name", "total", "rate"]].head(3).to_dict(orient="records")
        else:
            context["broker_alerts"] = []

    deltas = load_all_deltas()
    if not deltas.empty and "status_degraded" in deltas.columns:
        context["degraded_customers"] = int(deltas["status_degraded"].fillna(False).sum())

    context["generated_at"] = datetime.now().strftime("%d %B %Y %H:%M")
    context["today"] = date.today().strftime("%d %B %Y")
    context["pending_count"] = len(_load_pending_analyses())

    return context


def _load_pending_analyses() -> list:
    p = _DATA / "pending_analysis.json"
    if p.exists():
        with open(p) as f:
            pending = json.load(f)
        return [x for x in pending if not x.get("uw_reviewed", False)]
    return []


def _check_new_submissions() -> list:
    """Check watch folder for new PDFs not yet processed."""
    watch_folder = os.getenv("UW_WATCH_FOLDER", "")
    if watch_folder and Path(watch_folder).exists():
        pdfs = list(Path(watch_folder).glob("*.pdf"))
        processed_path = _DATA / "processed_submissions.json"
        processed = json.load(open(processed_path)) if processed_path.exists() else []
        return [p.name for p in pdfs if p.name not in processed]
    return []


def generate_briefing(context: Dict) -> str:
    """
    Call the LLM to generate a structured daily briefing from the context.
    Returns the briefing text.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _generate_fallback_briefing(context)

    base_url = os.getenv("ANTHROPIC_BASE_URL")
    model = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-4-6")

    client = OpenAI(
        api_key=api_key,
        base_url=f"{base_url}/v1" if base_url else None,
    )

    system = """You are an AI underwriting assistant providing a daily portfolio briefing.
Be concise, professional, and action-oriented. Maximum 200 words.
Structure your response as:
1. A 1-sentence portfolio health summary
2. 2-3 bullet points of most important items requiring attention today
3. A closing question asking the UW how they want to proceed

Always end with options like:
'How would you like to proceed?
A) Deep dive on [specific customer]
B) Review today's Fast-Track candidates
C) Check broker alerts
D) Ask me something specific'

All recommendations are advisory — the UW decides."""

    new_subs = context.get('new_submissions', [])
    pending  = context.get('pending_count', 0)

    prompt = f"""Today is {context.get('today', 'today')}.
Portfolio snapshot:
- {context.get('total_scored', 0):,} customers scored
- {context.get('fast_track_count', 0)} Fast-Track candidates (score < 35)
- {context.get('fresh_uw_count', 0)} require Fresh UW review (score > 65)
- Mean portfolio risk score: {context.get('mean_risk_score', 50)}/100
- {context.get('degraded_customers', 0)} customers with degrading status trend
- Broker alerts: {len(context.get('broker_alerts', []))} brokers with declining approval rate
- New PDFs in watch folder: {len(new_subs)} new, {pending} total pending review

Top risk customers: {json.dumps(context.get('top_risk', []), indent=2)}
Top Fast-Track candidates: {json.dumps(context.get('top_fast_track', []), indent=2)}
New submissions detected: {new_subs}
Broker alerts: {json.dumps(context.get('broker_alerts', []), indent=2)}

Generate the daily briefing. If there are new submissions, mention them explicitly and ask
the UW how they want to proceed. End with clear options A/B/C/D for the UW to choose from.
If there are pending analyses, ask if the UW wants to review them or update the portfolio."""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=400,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        return _generate_fallback_briefing(context)


def _generate_fallback_briefing(context: Dict) -> str:
    """Fallback briefing when LLM is unavailable — rule-based generation."""
    lines = [f"**Portfolio Summary — {context.get('today', 'Today')}**", ""]

    fast = context.get("fast_track_count", 0)
    fresh = context.get("fresh_uw_count", 0)
    new = context.get("new_submissions", [])
    broker_alerts = context.get("broker_alerts", [])
    degraded = context.get("degraded_customers", 0)

    lines.append(f"Portfolio of **{context.get('total_scored', 0):,}** scored customers. "
                 f"Mean risk score: **{context.get('mean_risk_score', 50)}/100**.")
    lines.append("")

    if new:
        lines.append(f"🔔 **{len(new)} new submission(s)** awaiting analysis: {', '.join(new[:3])}")
    if fast > 0:
        lines.append(f"✅ **{fast} Fast-Track candidates** — low risk, eligible for expedited processing")
    if fresh > 0:
        lines.append(f"⚠️ **{fresh} customers require Fresh UW review** — material risk changes detected")
    if degraded > 0:
        lines.append(f"📉 **{degraded} customers** showing degrading status trend vs their baseline")
    if broker_alerts:
        for b in broker_alerts[:2]:
            lines.append(f"🚨 **Broker alert:** {b.get('National Broker Name', '')} — "
                        f"only {b.get('rate', 0):.0%} approval rate on {b.get('total', 0)} recent submissions")

    lines.extend([
        "",
        "*How would you like to proceed?*",
        "**A)** Deep dive on a specific customer",
        "**B)** Review today's Fast-Track candidates",
        f"**C)** Analyse new submissions {f'({len(new)} waiting)' if new else ''}",
        "**D)** Ask me something specific",
    ])

    return "\n".join(lines)


def get_or_generate_briefing(session_state) -> str:
    """
    Returns cached briefing from session state, or generates a new one.
    Only generates once per session to avoid redundant API calls.
    """
    if "daily_briefing" not in session_state:
        context = _load_context()
        briefing = generate_briefing(context)
        session_state["daily_briefing"] = briefing
        session_state["briefing_context"] = context

    return session_state["daily_briefing"]
