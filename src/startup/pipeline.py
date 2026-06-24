"""
Pipeline validation and auto-regeneration.

Single responsibility: ensure all required data files exist and are non-empty
before the dashboard or MCP servers start.

Called by start_demo.py before launching any process.
app.py trusts this has already run — it never calls scripts itself.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict

DATA = Path("data/parsed")
ROOT = Path(__file__).parent.parent.parent


# ── File registry ──────────────────────────────────────────────────────────────

REQUIRED_FILES: Dict[str, str] = {
    # Core pipeline — must be generated manually once
    "all_submissions.csv":       "src/data/loader.py (run manually from raw Excel)",
    "all_recommendations.csv":   "src/business/mass_scoring.py",
    "all_deltas.csv":            "src/business/mass_deltas.py",
    "knowledge_graph.pkl":       "scripts/build_knowledge_graph.py",
    "graph_metrics.csv":         "scripts/build_knowledge_graph.py",
    "graph_communities.csv":     "scripts/build_knowledge_graph.py",
}

AUTO_REGENERATE_FILES: Dict[str, str] = {
    # KG pre-computed — auto-regenerated if empty or missing
    "kg_clusters_summary.csv":   "scripts/precompute_kg.py",
    "kg_emerging_risks.csv":     "scripts/precompute_kg.py",
    "kg_whitespace.csv":         "scripts/precompute_kg.py",
    "kg_broker_performance.csv": "scripts/precompute_kg.py",
    # RAG index — auto-built if missing
    "uw_guidelines_index.json":  "src/rag/guidelines_rag.py --build",
}


# ── Status check ───────────────────────────────────────────────────────────────

def check_pipeline() -> Dict[str, dict]:
    """
    Returns status of all data files.
    Each entry: {exists: bool, size_kb: float, ok: bool, source: str}
    """
    results = {}
    for fname, source in {**REQUIRED_FILES, **AUTO_REGENERATE_FILES}.items():
        p = DATA / fname
        exists = p.exists()
        size_kb = p.stat().st_size / 1024 if exists else 0
        ok = exists and size_kb > 0.1
        results[fname] = {
            "exists":   exists,
            "size_kb":  round(size_kb, 1),
            "ok":       ok,
            "source":   source,
            "required": fname in REQUIRED_FILES,
        }
    return results


def pipeline_ready() -> bool:
    """True if all REQUIRED files exist and are non-empty."""
    status = check_pipeline()
    return all(v["ok"] for k, v in status.items() if v["required"])


# ── Auto-regeneration ──────────────────────────────────────────────────────────

def _run(script_args: str, label: str) -> bool:
    """Run a Python script and return True if successful."""
    parts = script_args.split()
    cmd = [sys.executable] + parts
    try:
        result = subprocess.run(cmd, cwd=str(ROOT),
                                capture_output=True, text=True, timeout=300)
        ok = result.returncode == 0
        if not ok:
            print(f"  [!!] {label} failed: {result.stderr[-200:]}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"  [!!] {label} timed out (>5 min)")
        return False
    except Exception as e:
        print(f"  [!!] {label} error: {e}")
        return False


def fix_auto_regenerate(verbose: bool = True) -> bool:
    """
    Auto-regenerate files that are empty or missing (non-critical ones).
    Returns True if all auto-regeneratable files are now OK.
    """
    status = check_pipeline()
    needs_precompute_kg = False
    needs_rag = False

    for fname, source in AUTO_REGENERATE_FILES.items():
        info = status[fname]
        if not info["ok"]:
            if verbose:
                print(f"  [!!] {fname} — {'MISSING' if not info['exists'] else 'EMPTY'}")
            if "precompute_kg" in source:
                needs_precompute_kg = True
            elif "guidelines_rag" in source:
                needs_rag = True

    if needs_precompute_kg:
        if verbose:
            print("  Auto-running: scripts/precompute_kg.py --force")
        _run("scripts/precompute_kg.py --force", "precompute_kg")

    if needs_rag:
        rag_dir = ROOT / "data" / "raw" / "uw_guidelines"
        if rag_dir.exists() and list(rag_dir.glob("*.pdf")):
            if verbose:
                print("  Auto-running: src/rag/guidelines_rag.py --build")
            _run("-m src.rag.guidelines_rag --build", "rag_build")
        else:
            if verbose:
                print("  [skip] RAG: no guideline PDFs found in data/raw/uw_guidelines/")

    # Re-check
    status = check_pipeline()
    return all(
        status[f]["ok"]
        for f in AUTO_REGENERATE_FILES
        if f != "uw_guidelines_index.json"  # RAG is optional
    )


def print_status(verbose: bool = True):
    """Print a human-readable pipeline status table."""
    status = check_pipeline()
    ok_count = sum(1 for v in status.values() if v["ok"])
    total = len(status)
    print(f"\n  Data pipeline: {ok_count}/{total} files OK")
    if verbose:
        for fname, info in status.items():
            tag = "OK  " if info["ok"] else ("MISS" if not info["exists"] else "EMPT")
            size = f"{info['size_kb']:.0f}KB" if info["ok"] else "---"
            print(f"  [{tag}] {fname:<40} {size:>7}")
    print()
