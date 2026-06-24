"""
MCP Server: Watcher Tools (port 8604)
Monitors the UW folder for new submission PDFs and runs full agent analysis.

Tools exposed:
  scan_new_submissions()      — scan folder, run agent analysis on new PDFs
  get_pending_analyses()      — return completed analyses awaiting UW review
  approve_portfolio_update()  — trigger re-scoring + precompute after UW approval

This replaces the standalone watcher.py process.
Run: python src/mcp_servers/watcher_server.py --transport sse --port 8604
"""

import sys
import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from pathlib import Path as DataPath
from mcp.server import FastMCP
from dotenv import load_dotenv

load_dotenv(override=True)

DATA      = DataPath(__file__).resolve().parent.parent.parent / "data" / "parsed"
PENDING   = DATA / "pending_analysis.json"
PROCESSED = DATA / "processed_submissions.json"
WATCH_FOLDER = Path(os.getenv("UW_WATCH_FOLDER",
                   str(DataPath(__file__).resolve().parent.parent.parent / "data" / "raw" / "new_submissions")))

mcp = FastMCP("zurich-watcher")
logger = logging.getLogger(__name__)


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


def _load_processed() -> list:
    if PROCESSED.exists():
        with open(PROCESSED) as f: return json.load(f)
    return []


def _save_processed(lst: list):
    DATA.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED, "w") as f: json.dump(lst, f)


def _load_pending() -> list:
    if PENDING.exists():
        with open(PENDING) as f: return json.load(f)
    return []


def _save_pending(lst: list):
    DATA.mkdir(parents=True, exist_ok=True)
    with open(PENDING, "w") as f: json.dump(lst, f, indent=2)


def _run_agent_analysis(pdf_path: Path) -> dict:
    """
    Run full agent analysis on a PDF using the orchestrator.
    The agent uses its tools: parse → history → delta → peers → recommend.
    """
    from src.data.pdf_parser import parse_pdf_from_upload

    result = {
        "filename": pdf_path.name,
        "analysed_at": datetime.now().isoformat(),
        "status": "pending_review",
        "uw_reviewed": False,
        "analysis_id": str(uuid.uuid4()),
    }

    # Step 1: Parse PDF
    try:
        subs_path = DATA / "all_submissions.csv"
        products = brokers = []
        if subs_path.exists():
            subs = pd.read_csv(subs_path, low_memory=False)
            products = sorted(subs["Product Name"].dropna().unique().tolist())
            brokers  = sorted(subs["National Broker Name"].dropna().unique().tolist())

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        extracted = parse_pdf_from_upload(pdf_bytes, pdf_path.name, products, brokers)
        result["extraction"] = {
            "success":    extracted.get("extraction_success", False),
            "revenue_m":  extracted.get("revenue_millions"),
            "employees":  extracted.get("employee_count"),
            "product":    extracted.get("product"),
            "broker":     extracted.get("broker"),
            "controls":   extracted.get("controls", {}),
        }

        if not extracted.get("extraction_success"):
            result["status"] = "extraction_failed"
            return result

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        return result

    # Step 2: Run agent analysis
    try:
        from src.agent.orchestrator import UnderwritingAgent

        agent = UnderwritingAgent()
        product  = extracted.get("product", "")
        broker   = extracted.get("broker", "")
        revenue  = extracted.get("revenue_millions")
        controls = {k: bool(v) for k, v in extracted.get("controls", {}).items()}

        prompt = (
            f"A new submission PDF has arrived: {pdf_path.name}. "
            f"Extracted profile: product={product}, broker={broker}, revenue={revenue}M. "
            f"Controls present: {[k for k,v in controls.items() if v]}. "
            f"Missing controls: {[k for k,v in controls.items() if not v]}. "
            "Please: 1) Check if this is a repeat customer using search_portfolio. "
            "2) If repeat, get their history and delta. "
            "3) Find structural peers. "
            "4) Provide a recommendation with XAI reasoning. "
            "Be concise — this is an automated pre-analysis for the UW."
        )

        agent_response = ""
        tool_calls_made = []
        for event in agent.chat(prompt):
            if event["type"] == "text":
                agent_response += event["content"]
            elif event["type"] == "tool_call":
                tool_calls_made.append(event["tool"])

        result["agent_analysis"] = agent_response
        result["tools_used"] = tool_calls_made

        # Extract recommendation from response (simple heuristic)
        resp_upper = agent_response.upper()
        if "FAST_TRACK" in resp_upper:
            result["agent_recommendation"] = "FAST_TRACK"
        elif "FRESH_UW" in resp_upper or "FRESH UW" in resp_upper:
            result["agent_recommendation"] = "FRESH_UW"
        else:
            result["agent_recommendation"] = "STANDARD_UW"

        result["status"] = "analysed"

    except Exception as e:
        # If agent fails, fall back to rule-based quick assessment
        logger.warning(f"Agent analysis failed for {pdf_path.name}: {e}")
        controls = extracted.get("controls", {})
        critical = ["Firewall", "MFA", "Backup", "Incident Response", "Encryption"]
        n_critical = sum(1 for c in critical if controls.get(c, False))
        n_total = sum(1 for v in controls.values() if v)

        result["agent_recommendation"] = (
            "FAST_TRACK" if n_critical >= 5 and n_total >= 8 else
            "FRESH_UW" if n_critical < 3 else "STANDARD_UW"
        )
        result["agent_analysis"] = (
            f"Quick assessment (agent unavailable): "
            f"{n_critical}/5 critical controls, {n_total}/12 total. "
            f"Recommendation: {result['agent_recommendation']}"
        )
        result["status"] = "analysed_fallback"

    return result


@mcp.tool()
def scan_new_submissions() -> str:
    """
    Scan the UW watch folder for new PDF submissions and run full agent analysis.
    Each new PDF triggers: parse → search_portfolio → get_customer_history →
    get_submission_delta → find_structural_peers → recommendation with XAI.

    Returns: list of newly analysed submissions + count of total pending.
    The agent should call this in the daily briefing and when the UW asks about new submissions.
    """
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)
    processed = _load_processed()
    pending   = _load_pending()

    pdf_files = list(WATCH_FOLDER.glob("*.pdf"))
    new_pdfs  = [p for p in pdf_files if p.name not in processed]

    newly_analysed = []
    for pdf_path in new_pdfs:
        logger.info(f"Analysing: {pdf_path.name}")
        analysis = _run_agent_analysis(pdf_path)
        pending.append(analysis)
        processed.append(pdf_path.name)
        newly_analysed.append({
            "filename":           analysis["filename"],
            "recommendation":     analysis.get("agent_recommendation", "STANDARD_UW"),
            "status":             analysis["status"],
            "product":            analysis.get("extraction", {}).get("product"),
            "broker":             analysis.get("extraction", {}).get("broker"),
        })

    _save_pending(pending)
    _save_processed(processed)

    unreviewed = [p for p in pending if not p.get("uw_reviewed", False)]

    return _safe({
        "new_submissions_found":  len(new_pdfs),
        "newly_analysed":         newly_analysed,
        "total_pending_review":   len(unreviewed),
        "watch_folder":           str(WATCH_FOLDER),
        "message": (
            f"Found {len(new_pdfs)} new PDF(s). "
            f"{len(unreviewed)} submission(s) awaiting UW review."
            if new_pdfs else
            "No new submissions found."
        ),
    })


@mcp.tool()
def get_pending_analyses() -> str:
    """
    Return all completed agent analyses awaiting UW review.
    Use to show the UW what new submissions have been processed.
    """
    pending   = _load_pending()
    unreviewed = [p for p in pending if not p.get("uw_reviewed", False)]

    summary = [
        {
            "filename":       p["filename"],
            "recommendation": p.get("agent_recommendation", "STANDARD_UW"),
            "analysed_at":    p.get("analysed_at", ""),
            "status":         p.get("status", ""),
            "product":        p.get("extraction", {}).get("product"),
            "broker":         p.get("extraction", {}).get("broker"),
            "analysis_id":    p.get("analysis_id", ""),
        }
        for p in unreviewed
    ]

    return _safe({
        "pending_count": len(unreviewed),
        "submissions":   summary,
    })


@mcp.tool()
def approve_portfolio_update(confirmed: bool = True) -> str:
    """
    Trigger portfolio re-scoring and analytics update after UW approves new submissions.
    Runs: mass_scoring → mass_deltas → precompute_kg.
    Should ONLY be called after explicit UW approval.

    GOVERNANCE: This action modifies the portfolio analytics.
    The UW must explicitly say 'yes' or 'approve' before calling this tool.
    Never call this automatically — always wait for UW confirmation.
    """
    if not confirmed:
        return _safe({
            "status": "cancelled",
            "message": "Portfolio update cancelled. No changes made.",
        })

    results = []
    start   = datetime.now()

    scripts = [
        ("mass_scoring",    "src/business/mass_scoring.py"),
        ("mass_deltas",     "src/business/mass_deltas.py"),
        ("precompute_kg",   "scripts/precompute_kg.py"),
    ]

    import subprocess
    python = sys.executable

    for name, script in scripts:
        try:
            proc = subprocess.run(
                [python, script, "--force"],
                cwd=str(Path(__file__).parent.parent.parent),
                capture_output=True, text=True, timeout=300
            )
            ok = proc.returncode == 0
            results.append({"script": name, "success": ok,
                             "output": proc.stdout[-200:] if proc.stdout else ""})
        except subprocess.TimeoutExpired:
            results.append({"script": name, "success": False, "output": "Timeout (>5min)"})
        except Exception as e:
            results.append({"script": name, "success": False, "output": str(e)})

    elapsed = round((datetime.now() - start).total_seconds(), 1)
    all_ok  = all(r["success"] for r in results)

    return _safe({
        "status":           "completed" if all_ok else "partial_failure",
        "elapsed_seconds":  elapsed,
        "steps":            results,
        "message": (
            f"Portfolio updated successfully in {elapsed}s. "
            "Refresh the dashboard to see updated insights."
            if all_ok else
            "Some steps failed. Check the results for details."
        ),
        "governance": {
            "triggered_by":  "UW_EXPLICIT_APPROVAL",
            "advisory_only": False,
            "audit_note":    "Portfolio update executed following explicit UW approval.",
        },
    })


if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--transport", default="stdio", choices=["stdio", "sse"])
    _p.add_argument("--port", type=int, default=8604)
    _a = _p.parse_args()
    if _a.transport == "sse":
        mcp.settings.port = _a.port
        mcp.settings.host = "0.0.0.0"
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
