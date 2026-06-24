"""
Demo startup script — launches all processes for the EOS AI demo.

Usage:
    python start_demo.py           # Phase 1 — inline tools, no MCP servers needed
    python start_demo.py --mcp     # Phase 2 — MCP HTTP servers (4 servers + dashboard)
    python start_demo.py --stop    # Kill all running demo processes

On startup the script:
    1. Kills any leftover Python processes on the MCP ports (prevents Errno 10048)
    2. Validates all required data files
    3. Starts MCP HTTP servers if --mcp (submissions/scoring/kg/watcher)
    4. Starts Streamlit dashboard
    5. Opens browser automatically
"""

import sys
import os
import socket
import subprocess
import time
import webbrowser
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "parsed"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

DASHBOARD_PORT = 8501
MCP_SERVERS = {
    "submissions": ("src/mcp_servers/submissions_server.py", 8601),
    "scoring":     ("src/mcp_servers/scoring_server.py",     8602),
    "kg":          ("src/mcp_servers/kg_server.py",           8603),
    "watcher":     ("src/mcp_servers/watcher_server.py",      8604),
}


# ── Utilities ──────────────────────────────────────────────────────────────────

def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "OK" if ok else "!!"
    print(f"  [{icon}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.3):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def free_port(port: int):
    """Kill any process listening on the given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"],
                                capture_output=True)
                time.sleep(0.3)
    except Exception:
        pass


def free_all_ports():
    """Free MCP ports before starting — prevents Errno 10048."""
    all_ports = [p for _, p in MCP_SERVERS.values()] + [DASHBOARD_PORT]
    occupied = [p for p in all_ports if port_in_use(p)]
    if occupied:
        print(f"\n  Freeing occupied ports: {occupied}")
        for p in occupied:
            free_port(p)
        time.sleep(1)


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_data() -> bool:
    """Delegate to pipeline module — single source of truth."""
    sys.path.insert(0, str(ROOT))
    from src.startup.pipeline import (
        pipeline_ready, fix_auto_regenerate, print_status
    )
    print("\n[1/4] Validating data files...")
    print_status(verbose=True)

    if not pipeline_ready():
        print("\n  CRITICAL files missing. Run the pipeline first:")
        print("    python src/business/mass_scoring.py")
        print("    python src/business/mass_deltas.py")
        print("    python scripts/build_knowledge_graph.py")
        return False

    # Auto-fix regeneratable files (KG pre-computed + RAG)
    fix_auto_regenerate(verbose=True)
    return True


# ── MCP servers ────────────────────────────────────────────────────────────────

def start_mcp_servers() -> list:
    """Start all 4 MCP HTTP servers + background watcher. Returns list of Popen processes."""
    print("\n[2/4] Starting MCP HTTP servers + event-driven watcher...")
    LOG_DIR = ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    processes = []
    for name, (script, port) in MCP_SERVERS.items():
        try:
            log_file = open(LOG_DIR / f"mcp_{name}.log", "a")
            proc = subprocess.Popen(
                [PYTHON, script, "--transport", "sse", "--port", str(port)],
                cwd=str(ROOT),
                stdout=log_file,
                stderr=log_file,
            )
            for _ in range(10):
                if port_in_use(port):
                    break
                time.sleep(0.5)
            running = port_in_use(port)
            check(f"MCP {name}", running, f"http://localhost:{port}  [log: logs/mcp_{name}.log]")
            processes.append(proc)
        except Exception as e:
            check(f"MCP {name}", False, str(e))

    # Background watcher
    try:
        log_file = open(LOG_DIR / "watcher.log", "a")
        proc = subprocess.Popen(
            [PYTHON, "-m", "src.agent.watcher"],
            cwd=str(ROOT),
            stdout=log_file,
            stderr=log_file,
        )
        check("Watcher", True, "event-driven · polls every 30s · log: logs/watcher.log")
        processes.append(proc)
    except Exception as e:
        check("Watcher", False, str(e))

    return processes


# ── Dashboard ──────────────────────────────────────────────────────────────────

def start_dashboard(mcp_mode: bool) -> subprocess.Popen:
    print(f"\n[3/4] Starting dashboard (USE_MCP={'true' if mcp_mode else 'false'})...")
    env = os.environ.copy()
    env["USE_MCP"] = "true" if mcp_mode else "false"
    proc = subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run", "app.py",
         "--server.port", str(DASHBOARD_PORT),
         "--server.headless", "true"],
        cwd=str(ROOT),
        env=env,
    )
    return proc


def wait_for_dashboard(timeout: int = 20) -> bool:
    import urllib.request
    url = f"http://localhost:{DASHBOARD_PORT}"
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(1)
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EOS AI — Demo Launcher")
    parser.add_argument("--mcp",  action="store_true", help="Phase 2: start 4 MCP HTTP servers")
    parser.add_argument("--stop", action="store_true", help="Stop all demo processes")
    args = parser.parse_args()

    if args.stop:
        print("Stopping all demo processes...")
        # Kill by port first (clean)
        all_ports = [p for _, p in MCP_SERVERS.values()] + [DASHBOARD_PORT]
        for port in all_ports:
            if port_in_use(port):
                free_port(port)
                print(f"  Freed port {port}")
        # Also kill any leftover python processes from our scripts
        subprocess.run(["taskkill", "/f", "/im", "python.exe", "/t"],
                        capture_output=True)
        print("Done.")
        return

    mode_label = "Phase 2 — MCP HTTP" if args.mcp else "Phase 1 — Inline tools"
    print("=" * 60)
    print(f"  EOS AI — {mode_label}")
    print("=" * 60)

    # Always free ports first to avoid Errno 10048
    free_all_ports()

    # 1. Validate data
    if not validate_data():
        print("\nAborting — missing data files.")
        sys.exit(1)

    mcp_processes = []

    # 2. Start MCP servers (Phase 2 only)
    if args.mcp:
        mcp_processes = start_mcp_servers()
        all_running = all(port_in_use(p) for _, p in MCP_SERVERS.values())
        if not all_running:
            print("\n  WARNING: Some MCP servers failed to start.")
            print("  The dashboard will fall back to inline tools for those.")
    else:
        print("\n[2/4] MCP servers — skipped (Phase 1 inline mode)")

    # 3. Start dashboard
    dash_proc = start_dashboard(args.mcp)

    # 4. Wait and open browser
    print("\n[4/4] Waiting for dashboard to be ready...")
    ready = wait_for_dashboard(timeout=20)
    url = f"http://localhost:{DASHBOARD_PORT}"

    print()
    if ready:
        check("Dashboard", True, url)
        webbrowser.open(url)
    else:
        check("Dashboard", False, "timeout — check terminal for errors")

    print("\n" + "=" * 60)
    print(f"  Dashboard:  {url}")
    if args.mcp:
        for name, (_, port) in MCP_SERVERS.items():
            status = "RUNNING" if port_in_use(port) else "FAILED"
            print(f"  MCP {name:<12}: http://localhost:{port}  [{status}]")
    print()
    print("  Ctrl+C to stop all processes")
    print("=" * 60 + "\n")

    try:
        dash_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        dash_proc.terminate()
        for p in mcp_processes:
            try:
                p.terminate()
            except Exception:
                pass
        # Free ports on exit
        for _, port in MCP_SERVERS.values():
            free_port(port)
        print("All processes stopped.")


if __name__ == "__main__":
    main()

