"""
MCP Client — connects the orchestrator to standalone MCP servers.

Two transport modes (auto-detected):

  HTTP/SSE (fast, Phase 2 demo):
    Servers run persistently. Start with: python start_demo.py --mcp
    Latency: ~5ms per tool call (no subprocess spawn).
    Ports: submissions=8601, scoring=8602, kg=8603

  stdio (fallback, Phase 1):
    Spawns a new subprocess per tool call (~480ms).
    Used automatically when HTTP servers are not reachable.

Tool → server mapping:
  submissions_server (8601) → search_portfolio, get_customer_history
  scoring_server     (8602) → get_risk_score, get_submission_delta
  kg_server          (8603) → portfolio_analytics, find_structural_peers, explain_recommendation
"""

import asyncio
import json
import sys
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_KG_SERVER      = "src/mcp_servers/kg_server.py"
_KG_PORT        = 8603
_WATCHER_SERVER = "src/mcp_servers/watcher_server.py"
_WATCHER_PORT   = 8604

TOOL_SERVER_MAP: Dict[str, str] = {
    # Group 1 — Data Curation
    "search_portfolio":             "src/mcp_servers/submissions_server.py",
    "get_customer_history":         "src/mcp_servers/submissions_server.py",
    # Group 2 — UW Metrics
    "get_risk_score":               "src/mcp_servers/scoring_server.py",
    "get_submission_delta":         "src/mcp_servers/scoring_server.py",
    "get_control_delta":            "src/mcp_servers/scoring_server.py",
    "get_underwriter_patterns":     "src/mcp_servers/submissions_server.py",
    # Group 3 — KG Discovery (all on kg_server)
    "portfolio_analytics":          _KG_SERVER,
    "find_structural_peers":        _KG_SERVER,
    "explain_recommendation":       _KG_SERVER,
    # Group 3 extended — NetworkX graph analytics
    "get_community_purity":         _KG_SERVER,
    "find_cluster_bridges":         _KG_SERVER,
    "get_broker_centrality":        _KG_SERVER,
    "get_high_risk_central_nodes":  _KG_SERVER,
    "simulate_cascade_graph":       _KG_SERVER,
    "query_uw_guidelines":          _KG_SERVER,
    # Watcher server (port 8604)
    "scan_new_submissions":         _WATCHER_SERVER,
    "get_pending_analyses":         _WATCHER_SERVER,
    "approve_portfolio_update":     _WATCHER_SERVER,
}

TOOL_PORT_MAP: Dict[str, int] = {
    "search_portfolio":             8601,
    "get_customer_history":         8601,
    "get_risk_score":               8602,
    "get_submission_delta":         8602,
    "get_control_delta":            8602,
    "get_underwriter_patterns":     8601,
    "portfolio_analytics":          _KG_PORT,
    "find_structural_peers":        _KG_PORT,
    "explain_recommendation":       _KG_PORT,
    "get_community_purity":         _KG_PORT,
    "find_cluster_bridges":         _KG_PORT,
    "get_broker_centrality":        _KG_PORT,
    "get_high_risk_central_nodes":  _KG_PORT,
    "simulate_cascade_graph":       _KG_PORT,
    "query_uw_guidelines":          _KG_PORT,
    "scan_new_submissions":         _WATCHER_PORT,
    "get_pending_analyses":         _WATCHER_PORT,
    "approve_portfolio_update":     _WATCHER_PORT,
}


def _server_is_running(port: int) -> bool:
    """Quick TCP check — returns True if an MCP HTTP server is listening."""
    import socket
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except (OSError, ConnectionRefusedError):
        return False


# ── HTTP/SSE transport with connection cache ──────────────────────────────────
# Sessions are cached per port so the TCP+MCP handshake only happens once.
# Each subsequent call reuses the existing session → ~5ms instead of ~2000ms.

_session_cache: Dict[int, Any] = {}   # port → (session, context_stack)
_session_lock = None                   # created lazily per event loop


async def _get_or_create_session(port: int):
    """Return a cached MCP ClientSession, creating one if needed."""
    global _session_cache
    from mcp.client.sse import sse_client
    from mcp.client.session import ClientSession
    from contextlib import AsyncExitStack

    if port not in _session_cache:
        url = f"http://localhost:{port}/sse"
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(sse_client(url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        _session_cache[port] = (session, stack)
        logger.info(f"MCP HTTP session created for port {port}")

    return _session_cache[port][0]


async def _call_http_async(port: int, tool_name: str, arguments: Dict) -> str:
    global _session_cache
    try:
        session = await _get_or_create_session(port)
        result = await session.call_tool(tool_name, arguments)
        if hasattr(result, "content") and result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    return item.text
        return json.dumps({"result": str(result)})
    except Exception as e:
        # Session may have expired — clear cache and retry once
        if port in _session_cache:
            try:
                _, stack = _session_cache.pop(port)
                await stack.aclose()
            except Exception:
                pass
        logger.warning(f"MCP session reset for port {port}: {e}")
        # Single retry with fresh session
        session = await _get_or_create_session(port)
        result = await session.call_tool(tool_name, arguments)
        if hasattr(result, "content") and result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    return item.text
        return json.dumps({"result": str(result)})


# ── stdio transport (fallback) ────────────────────────────────────────────────

async def _call_stdio_async(server_script: str, tool_name: str, arguments: Dict) -> str:
    from mcp.client.stdio import stdio_client
    from mcp.client.session import ClientSession
    from mcp import StdioServerParameters

    params = StdioServerParameters(command=sys.executable, args=[server_script], env=None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if hasattr(result, "content") and result.content:
                for item in result.content:
                    if hasattr(item, "text"):
                        return item.text
            return json.dumps({"result": str(result)})


# ── Unified entry point ───────────────────────────────────────────────────────

# Persistent event loop — created once, reused across all calls
_event_loop: Any = None


def _get_loop():
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_event_loop)
    return _event_loop


def call_tool_via_mcp(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Call an MCP tool. Uses HTTP with session caching if server is running (~5ms),
    else stdio fallback (~480ms). Returns JSON string.
    """
    server = TOOL_SERVER_MAP.get(tool_name)
    port   = TOOL_PORT_MAP.get(tool_name)

    if not server:
        return json.dumps({"error": f"No MCP server for tool: {tool_name}"})

    loop = _get_loop()
    try:
        if port and _server_is_running(port):
            logger.info(f"MCP HTTP [{port}]: {tool_name}")
            return loop.run_until_complete(_call_http_async(port, tool_name, tool_input))

        # Fallback: stdio
        server_path = Path(server)
        if not server_path.exists():
            return json.dumps({"error": f"MCP server not found: {server}"})
        logger.info(f"MCP stdio fallback: {tool_name}")
        # stdio needs fresh loop (subprocesses conflict with cached sessions)
        tmp_loop = asyncio.new_event_loop()
        try:
            return tmp_loop.run_until_complete(
                _call_stdio_async(str(server_path), tool_name, tool_input)
            )
        finally:
            tmp_loop.close()

    except Exception as e:
        logger.error(f"MCP error ({tool_name}): {e}")
        return json.dumps({"error": f"MCP call failed: {e}"})


async def _list_tools_from_server(port: int) -> list:
    """Call tools/list on a running MCP server, return OpenAI-format tool schemas."""
    session = await _get_or_create_session(port)
    result = await session.list_tools()
    tools = []
    for t in result.tools:
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            }
        })
    return tools


def discover_mcp_tools() -> list:
    """
    Discover all tools from all running MCP servers via tools/list.
    Returns OpenAI-format tool definitions — the source of truth is the server,
    not the hardcoded TOOLS list in orchestrator.py.
    Falls back to empty list if no servers are running.
    """
    loop = _get_loop()
    all_tools = []
    for port in [8601, 8602, 8603, 8604]:
        if _server_is_running(port):
            try:
                tools = loop.run_until_complete(_list_tools_from_server(port))
                all_tools.extend(tools)
                logger.info(f"Discovered {len(tools)} tools from port {port}")
            except Exception as e:
                logger.warning(f"Could not discover tools from port {port}: {e}")
    return all_tools


async def _gather_tool_calls(tool_calls: list) -> list:
    """Run multiple MCP HTTP tool calls concurrently via asyncio.gather."""
    async def _one(tool_name: str, tool_input: Dict, tc_id: str) -> tuple:
        port = TOOL_PORT_MAP.get(tool_name)
        try:
            if port and _server_is_running(port):
                result = await _call_http_async(port, tool_name, tool_input)
            else:
                # stdio fallback in executor — non-blocking
                import functools
                loop = asyncio.get_event_loop()
                server = TOOL_SERVER_MAP.get(tool_name, "")
                result = await loop.run_in_executor(
                    None,
                    functools.partial(
                        lambda n, i: asyncio.new_event_loop().run_until_complete(
                            _call_stdio_async(TOOL_SERVER_MAP[n], n, i)
                        ) if n in TOOL_SERVER_MAP else json.dumps({"error": f"No server for {n}"}),
                        tool_name, tool_input
                    )
                )
        except Exception as e:
            result = json.dumps({"error": str(e)})
        return tc_id, result

    return await asyncio.gather(*[_one(n, i, tc_id) for n, i, tc_id in tool_calls])


def call_tools_parallel_mcp(tool_calls: list) -> list:
    """
    Parallel MCP execution using asyncio.gather — thread-safe, no event loop conflicts.
    tool_calls: [(tool_name, tool_input_dict, tool_call_id), ...]
    Returns:    [(tool_call_id, result_json_str), ...]
    """
    loop = _get_loop()
    return loop.run_until_complete(_gather_tool_calls(tool_calls))


def mcp_status() -> Dict:
    """Return health status of all MCP servers."""
    return {
        "submissions": {"port": 8601, "running": _server_is_running(8601),
                        "tools": ["search_portfolio", "get_customer_history"]},
        "scoring":     {"port": 8602, "running": _server_is_running(8602),
                        "tools": ["get_risk_score", "get_submission_delta"]},
        "kg":          {"port": 8603, "running": _server_is_running(8603),
                        "tools": ["portfolio_analytics", "find_structural_peers",
                                  "explain_recommendation"]},
    }


def test_mcp_connection(tool_name: str = "get_risk_score", args: Dict = None) -> Dict:
    """Test a single tool call and return status."""
    if args is None:
        args = {"customer_name": "Company 7130"}
    try:
        response = call_tool_via_mcp(tool_name, args)
        parsed = json.loads(response)
        port = TOOL_PORT_MAP.get(tool_name)
        return {
            "tool": tool_name,
            "transport": "http" if (port and _server_is_running(port)) else "stdio",
            "status": "error" if "error" in parsed else "ok",
            "response": parsed,
        }
    except Exception as e:
        return {"tool": tool_name, "status": "error", "error": str(e)}
