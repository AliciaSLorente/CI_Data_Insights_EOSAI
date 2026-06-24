"""
MCP Server layer for Zurich NB Intelligence System.

Three standalone MCP servers, each exposing a group of tools:
  submissions_server.py  — Data Curation tools (search_portfolio, get_customer_history)
  scoring_server.py      — UW Metrics tools (get_risk_score, get_submission_delta)
  kg_server.py           — KG Discovery tools (portfolio_analytics, explain_recommendation)

Each server can run as a standalone process:
  python -m src.mcp_servers.submissions_server
  python -m src.mcp_servers.scoring_server
  python -m src.mcp_servers.kg_server

The orchestrator connects to them via USE_MCP=true in .env
"""
