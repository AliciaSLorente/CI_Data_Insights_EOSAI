"""
Event-driven file watcher — monitors UW_WATCH_FOLDER for new PDF submissions.

When a new PDF is detected:
  1. Parses the PDF (pdf_parser.py)
  2. Checks if it's a repeat customer (search_portfolio)
  3. Scores and generates recommendation
  4. Stores result in data/parsed/pending_analysis.json
  5. Dashboard picks up the badge "X new submissions analysed"

Configuration:
  UW_WATCH_FOLDER = path to folder to monitor (set in .env)

Governance:
  - Agent analyses but NEVER acts — only stores advisory recommendation
  - Full audit trail: every analysis logged with timestamp
  - UW must review before any action

Run in background:
  python -m src.agent.watcher
"""

import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [WATCHER] %(message)s")
logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "parsed"
PENDING_PATH = DATA / "pending_analysis.json"
PROCESSED_PATH = DATA / "processed_submissions.json"


def _load_processed() -> List[str]:
    if PROCESSED_PATH.exists():
        with open(PROCESSED_PATH) as f:
            return json.load(f)
    return []


def _save_processed(processed: List[str]):
    with open(PROCESSED_PATH, "w") as f:
        json.dump(processed, f)


def _load_pending() -> List[Dict]:
    if PENDING_PATH.exists():
        with open(PENDING_PATH) as f:
            return json.load(f)
    return []


def _save_pending(pending: List[Dict]):
    with open(PENDING_PATH, "w") as f:
        json.dump(pending, f, indent=2)


def analyse_new_pdf(pdf_path: Path) -> Dict:
    """
    Run the full analysis pipeline on a new PDF.
    Returns a structured analysis result.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.data.pdf_parser import parse_pdf_from_upload
    import pandas as pd

    logger.info(f"Analysing: {pdf_path.name}")
    result = {
        "filename": pdf_path.name,
        "analysed_at": datetime.now().isoformat(),
        "status": "pending_review",
    }

    # Step 1: Parse PDF
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        subs_path = DATA / "all_submissions.csv"
        recs_path = DATA / "all_recommendations.csv"

        products = []
        brokers = []
        if subs_path.exists():
            subs = pd.read_csv(subs_path, low_memory=False)
            products = sorted(subs["Product Name"].dropna().unique().tolist())
            brokers = sorted(subs["National Broker Name"].dropna().unique().tolist())

        extracted = parse_pdf_from_upload(pdf_bytes, pdf_path.name, products, brokers)
        result["extraction"] = extracted
        result["extraction_success"] = extracted.get("extraction_success", False)

        if not extracted.get("extraction_success"):
            result["status"] = "extraction_failed"
            result["error"] = "Could not extract text from PDF"
            return result

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        return result

    # Step 2: Check if repeat customer
    try:
        if subs_path.exists():
            subs = pd.read_csv(subs_path, low_memory=False)
            # Try to match by product (best we can do without company name)
            product = extracted.get("product", "")
            broker = extracted.get("broker", "")

            if product:
                matching = subs[subs["Product Name"].astype(str).str.contains(
                    product.split()[0], case=False, na=False
                )]
                result["matching_product_submissions"] = len(matching)
                result["is_likely_repeat"] = len(matching) > 0
            else:
                result["is_likely_repeat"] = False
    except Exception as e:
        logger.warning(f"Repeat check failed: {e}")

    # Step 3: Quick risk assessment based on controls
    controls = extracted.get("controls", {})
    critical = ["Firewall", "MFA", "Backup", "Incident Response", "Encryption"]
    critical_present = sum(1 for c in critical if controls.get(c, False))
    ctrl_total = sum(1 for v in controls.values() if v)

    if critical_present >= 5 and ctrl_total >= 8:
        quick_rec = "FAST_TRACK"
        quick_rationale = f"Strong controls: {critical_present}/5 critical + {ctrl_total}/12 total"
    elif critical_present < 3 or ctrl_total < 4:
        quick_rec = "FRESH_UW"
        quick_rationale = f"Weak controls: only {critical_present}/5 critical present"
    else:
        quick_rec = "STANDARD_UW"
        quick_rationale = f"Moderate controls: {critical_present}/5 critical, {ctrl_total}/12 total"

    result["quick_recommendation"] = quick_rec
    result["quick_rationale"] = quick_rationale
    result["controls_summary"] = {
        "critical_present": critical_present,
        "total_present": ctrl_total,
        "missing_critical": [c for c in critical if not controls.get(c, False)],
    }
    result["status"] = "analysed"

    logger.info(f"  -> {quick_rec} | Controls: {ctrl_total}/12 | {quick_rationale}")
    return result


def watch_folder(folder_path: str, interval: int = 30):
    """
    Watch a folder for new PDF files and analyse them automatically.
    Runs indefinitely until interrupted.

    Args:
        folder_path: Path to the folder to watch
        interval: Check interval in seconds (default 30)
    """
    folder = Path(folder_path)
    if not folder.exists():
        logger.error(f"Watch folder does not exist: {folder}")
        return

    logger.info(f"Watching folder: {folder}")
    logger.info(f"Check interval: {interval}s")
    logger.info("Press Ctrl+C to stop")

    processed = _load_processed()

    while True:
        try:
            pdf_files = list(folder.glob("*.pdf"))
            new_pdfs = [p for p in pdf_files if p.name not in processed]

            if new_pdfs:
                logger.info(f"Found {len(new_pdfs)} new PDF(s)")
                pending = _load_pending()

                for pdf_path in new_pdfs:
                    analysis = analyse_new_pdf(pdf_path)
                    pending.append(analysis)
                    processed.append(pdf_path.name)

                _save_pending(pending)
                _save_processed(processed)
                logger.info(f"Saved {len(new_pdfs)} analyses to pending_analysis.json")
            else:
                logger.debug("No new PDFs found")

            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Watcher stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in watch loop: {e}")
            time.sleep(interval)


def get_pending_analyses() -> List[Dict]:
    """Get all pending analyses waiting for UW review."""
    return _load_pending()


_badge_cache: Dict[str, Any] = {"count": 0, "ts": 0.0}


def get_badge_count() -> int:
    """
    Total items needing UW attention: unreviewed analyses + unprocessed PDFs.
    Module-level TTL cache (30s) — avoids two JSON reads on every Streamlit render.
    """
    now = time.time()
    if now - _badge_cache["ts"] < 30:
        return _badge_cache["count"]
    watch_env = os.getenv("UW_WATCH_FOLDER", "")
    watch = Path(watch_env) if watch_env else DATA.parent / "raw" / "new_submissions"
    unreviewed  = sum(1 for p in _load_pending() if not p.get("uw_reviewed", False))
    unprocessed = sum(
        1 for f in watch.glob("*.pdf") if f.name not in _load_processed()
    ) if watch.exists() else 0
    _badge_cache["count"] = unreviewed + unprocessed
    _badge_cache["ts"]    = now
    return _badge_cache["count"]


def get_latest_pending_alert(previous_count: int) -> Optional[Dict]:
    """
    Returns toast-ready dict if a new unreviewed submission appeared since last check.
    Encapsulates data logic so app.py stays routing-only.
    Returns None if no new submission.
    """
    current = get_badge_count()
    if current <= previous_count:
        return None
    pending = _load_pending()
    latest  = next((p for p in reversed(pending) if not p.get("uw_reviewed", False)), None)
    if not latest:
        return None
    return {
        "filename": latest.get("filename", "new submission"),
        "recommendation": latest.get("agent_recommendation",
                                     latest.get("quick_recommendation", "")),
        "count": current,
    }


def mark_reviewed(filename: str, uw_decision: str, uw_notes: str = ""):
    """Mark a pending analysis as reviewed by the UW."""
    pending = _load_pending()
    for item in pending:
        if item.get("filename") == filename:
            item["uw_reviewed"] = True
            item["uw_decision"] = uw_decision
            item["uw_notes"] = uw_notes
            item["reviewed_at"] = datetime.now().isoformat()
    _save_pending(pending)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Watch folder for new submission PDFs")
    parser.add_argument("folder", nargs="?",
                        default=os.getenv("UW_WATCH_FOLDER", "data/raw/new_submissions"),
                        help="Folder to watch (or set UW_WATCH_FOLDER in .env)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Check interval in seconds (default: 30)")
    args = parser.parse_args()
    watch_folder(args.folder, args.interval)
