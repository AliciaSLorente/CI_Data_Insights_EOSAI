"""
AI Orchestrator Agent using Claude API with tool use.
Converts existing scoring/KG functions into callable tools.
"""

import json
import os
import re
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Generator, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv


class _SafeEncoder(json.JSONEncoder):
    """Converts numpy/pandas types to native Python before JSON serialisation."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        # pandas NA / NaT
        try:
            import pandas as _pd
            if obj is _pd.NA or obj is _pd.NaT:
                return None
        except Exception:
            pass
        return super().default(obj)


def _safe_json(obj) -> str:
    return json.dumps(obj, cls=_SafeEncoder)

load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data" / "parsed"
DECISIONS_LOG = DATA_DIR / "decisions_log.jsonl"
MAX_TURNS = 10
_TOOLS_CACHE = None  # module-level: survives re-instantiation, reset on server restart

# ── 7 Tools across 3 groups ────────────────────────────────────────────────────
# Group 1 — Data Curation   (Dataset 1: submission universe)
# Group 2 — UW Metrics      (Dataset 2: scoring, delta, recommendation)
# Group 3 — KG Discovery    (patterns, clusters, broker analysis, graph traversal)

TOOLS = [
    # ── Group 1: Data Curation ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_portfolio",
            "description": (
                "Search and filter the full submission portfolio (Dataset 1 — 46,318 submissions). "
                "Use to answer: how many repeat customers? which LOBs see most repeats? "
                "broker submission volumes? product trends? cadence of repeat submissions?"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Partial customer name filter"},
                    "product": {"type": "string", "description": "Product/LOB filter e.g. Cyber, Financial Lines"},
                    "broker": {"type": "string", "description": "Broker name filter"},
                    "status": {"type": "string", "description": "Status filter: Declined, Quoted, Bound, Rated"},
                    "year_from": {"type": "integer", "description": "Filter submissions from this year"},
                    "limit": {"type": "integer", "description": "Max rows to return (default 15)"},
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_history",
            "description": (
                "Get the full submission history for a specific repeat customer (Dataset 1 + Dataset 2). "
                "Use to answer: how many times has this customer submitted? what changed between submissions? "
                "what was decided each time? which underwriter handled it?"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer name (exact or partial)"},
                },
                "required": ["customer_name"]
            }
        }
    },
    # ── Group 2: UW Metrics ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_risk_score",
            "description": (
                "Get the AI risk score and recommendation for a customer. "
                "Returns score 0-100, recommendation (FAST_TRACK / STANDARD_UW / FRESH_UW), "
                "confidence, and breakdown of score components. "
                "Use to answer: should this customer be fast-tracked? what drove the score?"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer name (exact or partial)"},
                },
                "required": ["customer_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_submission_delta",
            "description": (
                "Get the delta (what changed) between the first and latest submission for a customer (Dataset 2). "
                "Returns: status improved or degraded, premium change %, broker changed, months between submissions. "
                "Use to answer: has this customer improved since we last saw them? what changed?"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer name (exact or partial)"},
                },
                "required": ["customer_name"]
            }
        }
    },
    # ── Group 3: KG Discovery ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "portfolio_analytics",
            "description": (
                "Run portfolio-level analytics to discover patterns across all customers. "
                "query_type options: "
                "'repeat_stats' = how many repeat customers, by LOB, cadence; "
                "'broker_trends' = broker approval rates, year-over-year changes; "
                "'risk_clusters' = customer segmentation by risk profile (KMeans); "
                "'fast_track_candidates' = customers ready for expedited processing; "
                "'anomalies' = customers behaving differently from their peer group; "
                "'whitespace' = low-risk segments with growth potential."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["repeat_stats", "broker_trends", "risk_clusters",
                                 "fast_track_candidates", "anomalies", "whitespace"],
                    },
                    "filter": {"type": "string", "description": "Optional product or broker filter"},
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_recommendation",
            "description": (
                "Generate a plain-language explanation of why a customer received their recommendation. "
                "Breaks down which factors increased or decreased the risk score. "
                "Use after get_risk_score to explain the 'why' to the underwriter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                },
                "required": ["customer_name"]
            }
        }
    },
    # ── Group 3 extra: real NetworkX graph traversal ──────────────────────────
    {
        "type": "function",
        "function": {
            "name": "find_structural_peers",
            "description": (
                "Find structurally similar customers using the real NetworkX Knowledge Graph. "
                "More accurate than simple SIC/product matching — finds customers connected through "
                "shared broker AND sector AND product simultaneously. "
                "Use when: 'who is similar to this customer?', 'find comparable companies', "
                "'which customers have similar profiles?', 'show me peer companies'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "n_peers": {"type": "integer", "description": "Number of peers (default 5)"}
                },
                "required": ["customer_name"]
            }
        }
    },
    # ── Use case gap tools ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_control_delta",
            "description": (
                "Show which security controls were present or absent across a customer's "
                "PDF submissions — answers 'what datapoints fell off on the most recent app?'. "
                "Compares controls (Firewall, MFA, EDR, SIEM, etc.) across all available PDFs. "
                "Use when: 'what controls changed?', 'what was present before?', 'what fell off?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer name"}
                },
                "required": ["customer_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_underwriter_patterns",
            "description": (
                "Analyse underwriter decision patterns across the portfolio. "
                "Answers: 'Do decisions differ by UW? What patterns do we see?' "
                "Without customer_name: portfolio-wide UW approval rates. "
                "With customer_name: which UWs handled this customer and their decisions. "
                "Use when: 'UW patterns', 'which UW?', 'decisions differ by underwriter?'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Optional: specific customer"},
                    "product": {"type": "string", "description": "Optional: filter by product"},
                    "top_n": {"type": "integer", "description": "Top N underwriters (default 10)"}
                }
            }
        }
    },
    # ── Watcher tools ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "scan_new_submissions",
            "description": (
                "Scan the UW watch folder for new PDF submissions and run full agent analysis. "
                "Call this in the daily briefing and when the UW asks about new submissions. "
                "Returns: number of new PDFs found, their recommendations, total pending review."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_analyses",
            "description": (
                "Get all submissions already analysed but waiting for UW review. "
                "Use to show the UW what has been processed while they were away."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_portfolio_update",
            "description": (
                "Trigger portfolio re-scoring after UW explicitly approves incorporating new submissions. "
                "ONLY call this after the UW says 'yes', 'approve', 'update', or similar affirmative. "
                "NEVER call automatically. Runs mass_scoring + mass_deltas + precompute_kg."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be true — only set true after explicit UW approval"
                    }
                },
                "required": ["confirmed"]
            }
        }
    },
    # ── RAG: UW Guidelines ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "query_uw_guidelines",
            "description": (
                "Retrieve relevant passages from Zurich UW guidelines to ground recommendations. "
                "Use this to cite the actual policy basis when making underwriting recommendations. "
                "ALWAYS use this when recommending Fresh UW or when controls are missing. "
                "Use when: 'what does the guideline say about X?', 'what's the policy for Y?', "
                "'cite the Zurich guideline for Z'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The underwriting question to look up in guidelines"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of passages to return (default 3)"
                    }
                },
                "required": ["question"]
            }
        }
    },
    # ── NetworkX graph analytics (with governance controls) ───────────────────
    {
        "type": "function",
        "function": {
            "name": "get_community_purity",
            "description": (
                "Analyse how structurally pure each Louvain community is by KMeans risk cluster. "
                "Identifies Risk Pockets (>80% High Risk) and Contagion Risk communities (mixed clusters). "
                "Use when: 'are there risk pockets?', 'which communities are dangerous?', "
                "'show me portfolio risk concentration', 'community risk analysis'."
            ),
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_cluster_bridges",
            "description": (
                "Find High Risk customers structurally connected to Low Risk customers via shared broker. "
                "These create hidden correlation paths. STRUCTURAL ANALYSIS ONLY — not individual reassessment. "
                "Use when: 'hidden risks', 'broker correlation', 'which high risk customers connect to safe ones', "
                "'cluster bridges', 'hidden risk paths'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "Max results (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_broker_centrality",
            "description": (
                "Rank brokers by network centrality × poor approval rate (danger score). "
                "High danger = large portfolio footprint AND low approval rate. "
                "STRUCTURAL CONCENTRATION RISK — not a quality assessment of the broker. "
                "Use when: 'which brokers are most dangerous?', 'broker risk', 'broker concentration'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "Max results (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_high_risk_central_nodes",
            "description": (
                "Find High Risk customers with highest network centrality (degree/PageRank). "
                "High centrality = if an issue occurs, it propagates furthest. MONITORING PRIORITY ONLY. "
                "Use when: 'most dangerous high risk customers', 'network centrality', "
                "'which high risk customers have most connections', 'propagation risk'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "Max results (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_cascade_graph",
            "description": (
                "Simulate a hazard event cascading through the real NetworkX portfolio graph. "
                "Returns D1 (direct), D2 (broker cascade), D3 (sector cascade) customer lists. "
                "THIS IS A HYPOTHETICAL SCENARIO — NOT A PREDICTION OR FORECAST. "
                "Use when: 'what if a cyber attack hits?', 'cascade risk', 'which companies would be affected', "
                "'broker failure impact', 'stress test the portfolio'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": ["cyber_campaign", "financial_contagion", "supply_chain", "broker_failure"],
                        "description": "Type of hazard event to simulate"
                    },
                    "target_broker": {
                        "type": "string",
                        "description": "Optional: specific broker to target (e.g. 'MARSH')"
                    }
                },
                "required": ["event_type"]
            }
        }
    },
]

SYSTEM_PROMPT = """You are an AI underwriting assistant for Zurich Insurance's Specialties team.

Your role: help underwriters apply renewal-like intelligence to New Business decisions for repeat customers.
The core insight: when a customer submits new business, Zurich has seen them before. You help surface that history.

You have 18 tools across 5 groups:
- Data Curation:    search_portfolio, get_customer_history, get_underwriter_patterns
- UW Metrics:       get_risk_score, get_submission_delta, get_control_delta
- KG Discovery:     portfolio_analytics, explain_recommendation, find_structural_peers,
                    get_community_purity, find_cluster_bridges, get_broker_centrality,
                    get_high_risk_central_nodes, simulate_cascade_graph
- Guidelines (RAG): query_uw_guidelines
- Watcher:          scan_new_submissions, get_pending_analyses, approve_portfolio_update

Guidelines:
- Start with what the UW needs to know, not with what data you found
- Always cite specific numbers (scores, counts, %, years) — never vague
- For individual customers: use get_customer_history + get_risk_score + get_submission_delta together
- get_control_delta only works for the 25 Cyber customers with PDF data (Dataset 2)
  If it returns "No PDF data found", use get_submission_delta instead — it works for all 9,078 customers
- NEVER try to read raw PDF files — all data is in pre-computed CSVs
- For portfolio questions: use portfolio_analytics
- For cascade/hazard events: use simulate_cascade_graph() — ALWAYS introduce as "In a hypothetical scenario..."
- For hidden risks / bridges: use find_cluster_bridges() — ALWAYS note this is structural position, not individual reassessment
- For broker risk: use get_broker_centrality() — ALWAYS note this is concentration risk, not broker quality
- For monitoring priorities: use get_high_risk_central_nodes() — ALWAYS frame as monitoring, not risk elevation
- For community analysis: use get_community_purity()
- For peer comparison: use find_structural_peers()
- Flag anomalies and concerns proactively
- End every response with: the recommendation and 1-sentence action for the UW
- All recommendations are advisory — human decision required

RAG GUIDELINES RULES (mandatory):
- query_uw_guidelines: call when recommending Fresh UW or when controls are missing
- ALWAYS cite the returned passage: "Per [source]: [text excerpt]"
- Never paraphrase guidelines without showing the original passage
- If index not available, proceed without citation but note it

WATCHER GOVERNANCE RULES (mandatory):
- scan_new_submissions: call in EVERY briefing to check for new PDFs
- approve_portfolio_update: ONLY call if the UW explicitly says yes/approve/update
  NEVER call automatically — this modifies portfolio data
- After presenting analysis of ANY new submission, ALWAYS ask:
  "Would you like to add [customer/filename] to the portfolio? This will update the
   scoring, delta, and queue data so it appears in the prioritisation queue.
   Reply 'yes' or 'add to portfolio' to confirm."
- After portfolio update completes, confirm: "Portfolio updated — [customer] now appears in the queue."

GRAPH ANALYTICS GOVERNANCE RULES (mandatory):
1. simulate_cascade_graph: ALWAYS say "In a hypothetical [event] scenario..." — never present as a prediction
2. find_cluster_bridges: ALWAYS include "structural position only — individual risk score unchanged"
3. get_broker_centrality: ALWAYS say "concentration risk, not a quality assessment of the broker"
4. get_high_risk_central_nodes: ALWAYS frame as "monitoring priority due to network position"
5. For ALL graph tools: cite the governance.notes field from the tool result in your response
6. NEVER recommend a coverage or pricing change based solely on graph analytics

When calling a tool, state in one sentence why you are calling it.

PLANNING RULE:
For queries that involve more than one customer, comparisons, rankings, or multi-step
analysis ("pre-call brief", "full analysis", "compare X and Y", "top N customers"),
first output your plan before calling any tools:
  "PLAN: Step 1 → tool(args) | Step 2 → tool(args) | Step 3 → synthesize"
Then execute each step in order. This ensures complete, structured responses.

BATCHING RULE:
When you need multiple tools for the SAME customer or the SAME question, call them ALL
in a single response turn — not in separate turns. This reduces waiting time.
Example: for customer analysis, call get_customer_history + get_risk_score +
get_submission_delta together in ONE response, not three separate responses.

CHART RULE:
When your response includes quantitative data that benefits from visual comparison, append ONE chart block
at the very end of your response using EXACTLY this format:
```eos_chart
{"type":"...","title":"...","x_label":"...","y_label":"...","data":[...]}
```

MANDATORY type selection — do NOT default to bar:
- Data has years/dates (2021, 2022, Q1, Jan…)? → MUST use "line". data: [{"x":"2021","y":72,"series":"Customer A"}] — include "series" for multiple customers on same chart
- Data shows correlation between TWO numeric variables? → MUST use "scatter". data: [{"name":"Company 1","x":45,"y":72}]
- Data is a matrix (rows = one dimension, columns = another, e.g. sector × broker)? → MUST use "heatmap". data: [{"x":"Broker A","y":"Cyber","value":0.85}]
- Data is a percentage/share breakdown (parts of a whole, sums to 100%)? → use "pie". data: [{"name":"...","value":72}]
- Data is simple named comparisons with no time axis and no correlation? → use "bar". data: [{"name":"...","value":72}]

Maximum 15 data points for bar/pie/scatter. Maximum 20 cells for heatmap. Numeric values only.
Do NOT include a chart for simple single-value answers or text-only responses."""


class UnderwritingAgent:
    """
    Orchestrator agent.

    Modes (controlled by USE_MCP in .env):
      USE_MCP=false (default) — tools implemented inline in this class (Phase 1)
      USE_MCP=true            — tools dispatched to standalone MCP servers (Phase 2)

    MCP servers (run independently):
      src/mcp_servers/submissions_server.py  — search_portfolio, get_customer_history
      src/mcp_servers/scoring_server.py      — get_risk_score, get_submission_delta
      src/mcp_servers/kg_server.py           — portfolio_analytics, find_structural_peers, explain_recommendation
    """

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        self.client = OpenAI(
            api_key=api_key,
            base_url=f"{base_url}/v1" if base_url else None,
        )
        self.model = os.getenv("ANTHROPIC_MODEL", "eu.anthropic.claude-sonnet-4-6")
        self._submissions = None
        self._all_submissions = None
        self._recommendations = None
        self._deltas = None

    def _get_tools(self) -> list:
        """
        Return tool definitions for the LLM.
        MCP mode: discover schemas live from running servers (single source of truth).
        Inline mode: use the hardcoded TOOLS fallback.
        Module-level cache avoids re-discovery on every message (agent is re-instantiated per turn).
        """
        global _TOOLS_CACHE
        if os.getenv("USE_MCP", "false").lower() == "true":
            if _TOOLS_CACHE is None:
                from src.agent.mcp_client import discover_mcp_tools
                discovered = discover_mcp_tools()
                _TOOLS_CACHE = discovered if discovered else TOOLS
            return _TOOLS_CACHE
        return TOOLS

    def _load_data(self):
        if self._submissions is None:
            # Full scored dataset
            recs_path = DATA_DIR / "all_recommendations.csv"
            if not recs_path.exists():
                recs_path = DATA_DIR / "sample_recommendations.csv"

            # All submissions (rich data)
            all_subs_path = DATA_DIR / "all_submissions.csv"
            subs_path = DATA_DIR / "repeat_customers.csv"

            # Deltas
            deltas_path = DATA_DIR / "all_deltas.csv"
            if not deltas_path.exists():
                deltas_path = DATA_DIR / "sample_deltas.csv"

            self._recommendations = pd.read_csv(recs_path) if recs_path.exists() else pd.DataFrame()
            self._deltas = pd.read_csv(deltas_path) if deltas_path.exists() else pd.DataFrame()

            # Build rich submissions: merge all_submissions with recommendations
            if all_subs_path.exists():
                all_subs = pd.read_csv(all_subs_path, low_memory=False)
                all_subs["Requested Coverage Effective Date"] = pd.to_datetime(
                    all_subs["Requested Coverage Effective Date"], errors="coerce"
                )
                self._all_submissions = all_subs  # cache full dataset for history lookups
                # Latest submission per customer
                latest = (
                    all_subs.sort_values("Requested Coverage Effective Date")
                    .groupby("Submission Account Name")
                    .last()
                    .reset_index()
                )
                # Merge with scores
                self._submissions = latest.merge(
                    self._recommendations[["company_name", "risk_score", "recommendation", "confidence"]],
                    left_on="Submission Account Name",
                    right_on="company_name",
                    how="left",
                ).drop(columns=["company_name"], errors="ignore")
            else:
                self._submissions = pd.read_csv(subs_path) if subs_path.exists() else pd.DataFrame()

    def _run_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        # ── MCP mode: route to standalone MCP servers ─────────────────────────
        if os.getenv("USE_MCP", "false").lower() == "true":
            from src.agent.mcp_client import call_tool_via_mcp, TOOL_SERVER_MAP
            # Only route tools that have MCP servers; fall through for others
            if tool_name in TOOL_SERVER_MAP:
                return call_tool_via_mcp(tool_name, tool_input)

        # ── Inline mode (Phase 1 default) ─────────────────────────────────────
        self._load_data()
        dispatch = {
            # Group 1 — Data Curation
            "search_portfolio":      self._tool_search_portfolio,
            "get_customer_history":  self._tool_get_customer_history,
            # Group 2 — UW Metrics
            "get_risk_score":        self._tool_get_risk_score,
            "get_submission_delta":  self._tool_get_submission_delta,
            # Group 3 — KG Discovery
            "portfolio_analytics":          self._tool_portfolio_analytics,
            "explain_recommendation":       self._tool_explain_recommendation,
            "find_structural_peers":        self._tool_find_structural_peers,
            # Use case gap tools
            "get_control_delta":            self._tool_get_control_delta,
            "get_underwriter_patterns":     self._tool_get_underwriter_patterns,
            # RAG tool
            "query_uw_guidelines":          self._tool_query_uw_guidelines,
            # Watcher tools (inline fallbacks)
            "scan_new_submissions":         self._tool_scan_new_submissions,
            "get_pending_analyses":         self._tool_get_pending_analyses,
            "approve_portfolio_update":     self._tool_approve_portfolio_update,
            # Group 3 extended — NetworkX graph analytics (inline fallbacks)
            "get_community_purity":         self._tool_get_community_purity,
            "find_cluster_bridges":         self._tool_find_cluster_bridges,
            "get_broker_centrality":        self._tool_get_broker_centrality,
            "get_high_risk_central_nodes":  self._tool_get_high_risk_central_nodes,
            "simulate_cascade_graph":       self._tool_simulate_cascade_graph,
        }
        fn = dispatch.get(tool_name)
        if fn:
            return fn(**tool_input)
        return _safe_json({"error": f"Unknown tool: {tool_name}"})

    # ── Group 1: Data Curation ─────────────────────────────────────────────────

    def _tool_search_portfolio(self, customer_name: str = None, product: str = None,
                               broker: str = None, status: str = None,
                               year_from: int = None, lob: str = None, limit: int = 15) -> str:
        df = self._submissions.copy()
        if df.empty:
            return _safe_json({"error": "No submission data available"})
        product = product or lob  # alias
        if customer_name:
            df = df[df["Submission Account Name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)]
        if product:
            df = df[df.get("Product Name", pd.Series(dtype=str)).astype(str).str.contains(product, case=False, na=False)]
        if broker:
            df = df[df.get("National Broker Name", pd.Series(dtype=str)).astype(str).str.contains(broker, case=False, na=False)]
        if status:
            df = df[df.get("Current Status Description", pd.Series(dtype=str)).astype(str).str.contains(status, case=False, na=False)]

        cols = ["Submission Account Name", "Product Name", "National Broker Name",
                "Current Status Description", "Quoted Premium Amount", "risk_score", "recommendation"]
        cols = [c for c in cols if c in df.columns]
        result = df[cols].head(limit).rename(columns={
            "Submission Account Name": "customer", "Product Name": "product",
            "National Broker Name": "broker", "Current Status Description": "status",
            "Quoted Premium Amount": "premium",
        })
        return _safe_json({
            "count": len(df),
            "showing": len(result),
            "results": result.to_dict(orient="records"),
        })

    def _tool_get_customer_history(self, customer_name: str) -> str:
        self._load_data()
        if self._all_submissions is None:
            all_subs_path = DATA_DIR / "all_submissions.csv"
            if not all_subs_path.exists():
                return _safe_json({"error": "all_submissions.csv not found"})
            self._all_submissions = pd.read_csv(all_subs_path, low_memory=False)
        all_subs = self._all_submissions
        mask = all_subs["Submission Account Name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)
        history = all_subs[mask].sort_values("Requested Coverage Effective Date")
        if history.empty:
            return _safe_json({"message": f"No history found for '{customer_name}'"})

        matched_name = history["Submission Account Name"].iloc[0]
        cols = ["Requested Coverage Effective Date", "Product Name", "National Broker Name",
                "Current Status Description", "Quoted Premium Amount", "Underwriter Name"]
        cols = [c for c in cols if c in history.columns]
        return _safe_json({
            "customer": matched_name,
            "total_submissions": len(history),
            "years_active": int(history["Requested Coverage Effective Date"].apply(
                lambda x: pd.to_datetime(x, errors="coerce")).dt.year.nunique()) if "Requested Coverage Effective Date" in history.columns else None,
            "products_seen": history["Product Name"].unique().tolist() if "Product Name" in history.columns else [],
            "brokers_seen": history["National Broker Name"].unique().tolist() if "National Broker Name" in history.columns else [],
            "status_counts": history["Current Status Description"].value_counts().to_dict() if "Current Status Description" in history.columns else {},
            "submissions": history[cols].tail(5).to_dict(orient="records"),
        })

    # ── Group 2: UW Metrics ────────────────────────────────────────────────────

    def _tool_get_risk_score(self, customer_name: str) -> str:
        df = self._recommendations.copy()
        if df.empty:
            return _safe_json({"error": "No recommendation data available"})
        mask = df["company_name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)
        matches = df[mask]
        if matches.empty:
            return _safe_json({"message": f"No risk score found for '{customer_name}'"})
        row = matches.iloc[0]
        comp_cols = [c for c in df.columns if c.startswith("comp_")]
        components = {c.replace("comp_", "").replace("_", " "): float(row[c])
                      for c in comp_cols if c in row.index and pd.notna(row[c])}
        return _safe_json({
            "customer": row["company_name"],
            "risk_score": row["risk_score"],
            "recommendation": row["recommendation"],
            "confidence": row["confidence"],
            "reasoning": row.get("reasoning", ""),
            "score_components": components,
        })

    def _tool_get_submission_delta(self, customer_name: str) -> str:
        if self._deltas.empty:
            return _safe_json({"error": "Delta data not available"})
        mask = self._deltas["company_name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)
        matches = self._deltas[mask]
        if matches.empty:
            return _safe_json({"message": f"No delta data for '{customer_name}'"})
        row = matches.iloc[0]
        result = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        return _safe_json(result)

    # ── Group 3: KG Discovery ──────────────────────────────────────────────────

    def _tool_portfolio_analytics(self, query_type: str, filter: str = None,
                                   sector: str = None) -> str:
        recs = self._recommendations
        subs = self._submissions

        if query_type in ("repeat_stats",):
            repeat_path = DATA_DIR / "repeat_customers.csv"
            all_subs_path = DATA_DIR / "all_submissions.csv"
            repeats = pd.read_csv(repeat_path) if repeat_path.exists() else pd.DataFrame()
            total = len(pd.read_csv(all_subs_path, low_memory=False)["Submission Account Name"].unique()) if all_subs_path.exists() else 0
            return _safe_json({
                "total_unique_customers": total,
                "repeat_customers": len(repeats),
                "repeat_pct": round(len(repeats) / total * 100, 1) if total else 0,
                "top_repeat_customers": repeats.head(10).to_dict(orient="records") if not repeats.empty else [],
            })

        elif query_type == "broker_trends":
            all_subs_path = DATA_DIR / "all_submissions.csv"
            if not all_subs_path.exists():
                return _safe_json({"error": "No submission data"})
            all_subs = pd.read_csv(all_subs_path, low_memory=False)
            all_subs["is_bound"] = (all_subs["Submission Product Bound Premium Amount"].notna() &
                                     (all_subs["Submission Product Bound Premium Amount"] > 0))
            broker_stats = (
                all_subs.groupby("National Broker Name")
                .agg(total=("is_bound", "count"), bound=("is_bound", "sum"))
                .reset_index()
            )
            broker_stats["approval_rate"] = (broker_stats["bound"] / broker_stats["total"] * 100).round(1)
            top = broker_stats.nlargest(10, "total")
            return _safe_json({
                "top_brokers_by_volume": top.to_dict(orient="records"),
                "declining_brokers": broker_stats[
                    (broker_stats["total"] >= 50) & (broker_stats["approval_rate"] < 10)
                ].to_dict(orient="records"),
            })

        elif query_type == "risk_clusters":
            if recs.empty:
                return _safe_json({"error": "No scoring data"})
            low = recs[recs["risk_score"] < 40]
            mid = recs[(recs["risk_score"] >= 40) & (recs["risk_score"] < 65)]
            high = recs[recs["risk_score"] >= 65]
            return _safe_json({"clusters": [
                {"label": "Low Risk", "count": len(low), "avg_score": round(low["risk_score"].mean(), 1) if len(low) else None, "recommendation": "FAST_TRACK"},
                {"label": "Moderate Risk", "count": len(mid), "avg_score": round(mid["risk_score"].mean(), 1) if len(mid) else None, "recommendation": "STANDARD_UW"},
                {"label": "High Risk", "count": len(high), "avg_score": round(high["risk_score"].mean(), 1) if len(high) else None, "recommendation": "FRESH_UW"},
            ]})

        elif query_type == "fast_track_candidates":
            if recs.empty:
                return _safe_json({"error": "No scoring data"})
            candidates = recs[recs["recommendation"] == "FAST_TRACK"].nsmallest(15, "risk_score")
            return _safe_json({
                "total_fast_track": int((recs["recommendation"] == "FAST_TRACK").sum()),
                "top_candidates": candidates[["company_name", "risk_score", "confidence", "reasoning"]].to_dict(orient="records"),
            })

        elif query_type == "anomalies":
            if recs.empty:
                return _safe_json({"error": "No scoring data"})
            mean_s, std_s = recs["risk_score"].mean(), recs["risk_score"].std()
            anomalies = recs[abs(recs["risk_score"] - mean_s) > 1.5 * std_s]
            return _safe_json({
                "portfolio_mean_score": round(mean_s, 1),
                "anomaly_count": len(anomalies),
                "threshold": f"mean +/- 1.5 std ({mean_s:.1f} +/- {1.5*std_s:.1f})",
                "anomalies": anomalies[["company_name", "risk_score", "recommendation"]].head(10).to_dict(orient="records"),
            })

        elif query_type == "whitespace":
            if subs.empty:
                return _safe_json({"error": "No submission data"})
            repeat_path = DATA_DIR / "repeat_customers.csv"
            repeats = pd.read_csv(repeat_path) if repeat_path.exists() else pd.DataFrame()
            return _safe_json({
                "insight": "Customers with 2-3 submissions and strong approval history = proactive outreach opportunities",
                "total_repeat_customers": len(repeats),
                "recommendation": "Target low-score repeat customers for proactive renewal outreach before they go to market",
            })

        return _safe_json({"error": f"Unknown query_type: {query_type}"})

    def _tool_explain_recommendation(self, customer_name: str = None,
                                      score: float = None, recommendation: str = None,
                                      components: Dict = None, reasoning: list = None) -> str:
        self._load_data()  # ensure data available when called internally
        reasoning_str = ""

        # Auto-lookup score if only customer name given
        if customer_name and score is None:
            try:
                result_str = self._tool_get_risk_score(customer_name)
                if result_str:
                    result = json.loads(result_str)
                    if "error" in result or "message" in result:
                        return _safe_json(result)
                    score = result.get("risk_score", 50)
                    recommendation = result.get("recommendation", "STANDARD_UW")
                    components = result.get("score_components", {})
                    reasoning_str = result.get("reasoning", "")
            except Exception as e:
                return _safe_json({"error": f"Could not look up score for '{customer_name}': {e}"})
        else:
            reasoning_str = " | ".join(reasoning or [])

        if score is None:
            return _safe_json({"error": f"No score data found for '{customer_name}'"})

        return _safe_json({
            "customer": customer_name,
            "risk_score": score,
            "recommendation": recommendation,
            "explanation": {
                k: {"points": round(float(v), 1), "direction": "increases risk" if v > 0 else "reduces risk"}
                for k, v in (components or {}).items()
            },
            "reasoning": reasoning_str,
            "advisory": "Human underwriter review required before any decision.",
        })

    def _tool_find_structural_peers(self, customer_name: str, n_peers: int = 5) -> str:
        """
        Real NetworkX graph traversal — finds structurally similar customers.
        Customers connected through shared broker AND sector simultaneously.
        More accurate than categorical matching.
        """
        import pickle
        pkl_path = DATA_DIR / "knowledge_graph.pkl"
        if not pkl_path.exists():
            return _safe_json({"error": "Knowledge graph not built. Run: python scripts/build_knowledge_graph.py"})

        try:
            with open(pkl_path, "rb") as f:
                G = pickle.load(f)
        except Exception as e:
            return _safe_json({"error": f"Could not load graph: {e}"})

        # Find customer node
        matches = [n for n in G.nodes if customer_name.lower() in n.lower() and n.startswith("cust::")]
        if not matches:
            return _safe_json({"message": f"Customer '{customer_name}' not found in graph. Try a partial name."})

        node = matches[0]
        actual_name = node.replace("cust::", "")
        neighbours = list(G.neighbors(node))

        broker_nodes  = [n for n in neighbours if n.startswith("broker::")]
        sector_nodes  = [n for n in neighbours if n.startswith("sector::")]
        product_nodes = [n for n in neighbours if n.startswith("product::")]
        cluster_node  = next((n for n in neighbours if n.startswith("cluster::")), None)

        # Score peers: broker match = 2pts, sector match = 1pt
        peers: Dict[str, int] = {}
        for b in broker_nodes:
            for p in G.neighbors(b):
                if p.startswith("cust::") and p != node:
                    peers[p] = peers.get(p, 0) + 2
        for s in sector_nodes:
            for p in G.neighbors(s):
                if p.startswith("cust::") and p != node:
                    peers[p] = peers.get(p, 0) + 1

        top_peers = sorted(peers.items(), key=lambda x: x[1], reverse=True)[:n_peers]

        # Enrich with scores from graph_metrics.csv
        gm_path = DATA_DIR / "graph_metrics.csv"
        gm = pd.read_csv(gm_path) if gm_path.exists() else pd.DataFrame()

        peer_details = []
        for peer_node, sim_score in top_peers:
            peer_name = peer_node.replace("cust::", "")
            info = {"customer": peer_name, "structural_similarity_score": sim_score}
            if not gm.empty:
                row = gm[gm["customer"] == peer_name]
                if not row.empty:
                    r = row.iloc[0]
                    info["cluster"] = r.get("cluster", "")
                    info["risk_score"] = r.get("risk_score", None)
                    info["recommendation"] = r.get("recommendation", "")
                    info["approval_rate_pct"] = r.get("approval_rate", None)
            peer_details.append(info)

        return _safe_json({
            "customer": actual_name,
            "cluster": cluster_node.replace("cluster::", "") if cluster_node else "Unknown",
            "connected_broker": broker_nodes[0].replace("broker::", "") if broker_nodes else None,
            "connected_sector": sector_nodes[0].replace("sector::", "")[:60] if sector_nodes else None,
            "connected_product": product_nodes[0].replace("product::", "") if product_nodes else None,
            "structural_peers": peer_details,
            "method": "NetworkX graph traversal — broker+sector edge matching",
            "note": f"Found {len(peer_details)} peers connected through shared broker and sector relationships",
        })

    # ── Use case gap tools — inline fallbacks ────────────────────────────────

    def _tool_get_control_delta(self, customer_name: str) -> str:
        try:
            from pathlib import Path as _P
            pdfs_path = DATA_DIR / "pdf_extracted_fields.csv"
            if not pdfs_path.exists():
                return _safe_json({"error": "PDF extracted fields not available."})
            pdfs = pd.read_csv(pdfs_path)
            mask = pdfs["company_name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)
            customer_pdfs = pdfs[mask]
            if customer_pdfs.empty:
                return _safe_json({
                    "message": f"No PDF data for '{customer_name}' — this customer is not in Dataset 2 (25 Cyber companies).",
                    "fallback": "Use get_submission_delta() instead — it covers all 9,078 repeat customers from Dataset 1.",
                })
            control_cols = [c for c in pdfs.columns if c.startswith("control_")]
            snapshots = []
            for _, row in customer_pdfs.iterrows():
                snap = {"pdf_file": row.get("pdf_file",""), "date": row.get("policy_effective_date","")}
                for col in control_cols:
                    label = col.replace("control_","").replace("_"," ").title()
                    snap[label] = bool(row.get(col, False))
                snapshots.append(snap)
            delta = {}
            if len(snapshots) >= 2:
                first, latest = snapshots[0], snapshots[-1]
                removed = [k for k in first if k not in ("pdf_file","date") and first[k] and not latest.get(k,False)]
                added   = [k for k in latest if k not in ("pdf_file","date") and latest[k] and not first.get(k,False)]
                delta = {"controls_added": added, "controls_removed": removed,
                         "interpretation": "Controls improved" if len(added)>len(removed) else
                                           "Controls degraded" if removed else "Stable"}
            return _safe_json({"customer": customer_pdfs["company_name"].iloc[0],
                               "pdf_submissions": len(snapshots),
                               "snapshots": snapshots, "delta_summary": delta})
        except Exception as e:
            return _safe_json({"error": f"get_control_delta failed: {e}"})

    def _tool_get_underwriter_patterns(self, customer_name: str = None,
                                        product: str = None, top_n: int = 10) -> str:
        try:
            subs_path = DATA_DIR / "all_submissions.csv"
            if not subs_path.exists():
                return _safe_json({"error": "all_submissions.csv not found"})
            subs = pd.read_csv(subs_path, low_memory=False)
            subs["is_bound"] = (subs["Submission Product Bound Premium Amount"].notna() &
                                 (subs["Submission Product Bound Premium Amount"] > 0))
            if customer_name:
                mask = subs["Submission Account Name"].astype(str).str.contains(rf'\b{re.escape(customer_name)}\b', case=False, na=False)
                customer_subs = subs[mask]
                if customer_subs.empty:
                    return _safe_json({"message": f"No data for '{customer_name}'"})
                uw = (customer_subs.groupby("Underwriter Name")
                      .agg(submissions=("Underwriter Name","count"), bound=("is_bound","sum"))
                      .reset_index())
                uw["approval_rate_pct"] = (uw["bound"]/uw["submissions"].clip(1)*100).round(1)
                return _safe_json({"customer": customer_subs["Submission Account Name"].iloc[0],
                                   "underwriter_breakdown": uw.to_dict(orient="records")})
            if product:
                subs = subs[subs["Product Name"].astype(str).str.contains(product, case=False, na=False)]
            uw_stats = (subs.groupby("Underwriter Name")
                        .agg(total=("Underwriter Name","count"), bound=("is_bound","sum"),
                             customers=("Submission Account Name","nunique"))
                        .reset_index())
            uw_stats["approval_rate_pct"] = (uw_stats["bound"]/uw_stats["total"].clip(1)*100).round(1)
            uw_stats = uw_stats.sort_values("total", ascending=False).head(top_n)
            return _safe_json({"portfolio_avg_approval_pct": round(subs["is_bound"].mean()*100,1),
                               "top_underwriters": uw_stats.to_dict(orient="records")})
        except Exception as e:
            return _safe_json({"error": f"get_underwriter_patterns failed: {e}"})

    # ── RAG inline fallback ───────────────────────────────────────────────────

    def _tool_query_uw_guidelines(self, question: str, top_k: int = 3) -> str:
        try:
            from src.rag.guidelines_rag import query_guidelines, index_available
            if not index_available():
                return _safe_json({
                    "available": False,
                    "message": "UW Guidelines index not built. Run: python -m src.rag.guidelines_rag --build",
                })
            results = query_guidelines(question, top_k=top_k)
            return _safe_json({
                "available": True,
                "question": question,
                "results": results,
                "governance": {
                    "citation_required": True,
                    "notes": "Always cite the source passage when using in recommendations.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"query_uw_guidelines failed: {e}"})

    # ── Watcher inline fallbacks ──────────────────────────────────────────────

    def _tool_scan_new_submissions(self) -> str:
        try:
            from src.agent.watcher import get_pending_analyses, analyse_new_pdf, _load_processed, _save_processed, _save_pending, _load_pending
            import os
            from pathlib import Path
            watch = Path(os.getenv("UW_WATCH_FOLDER", "data/raw/new_submissions"))
            watch.mkdir(parents=True, exist_ok=True)
            processed = _load_processed()
            pending   = _load_pending()
            new_pdfs  = [p for p in watch.glob("*.pdf") if p.name not in processed]
            newly = []
            for pdf in new_pdfs:
                result = analyse_new_pdf(pdf)
                pending.append(result)
                processed.append(pdf.name)
                newly.append({"filename": result["filename"],
                              "recommendation": result.get("quick_recommendation", "STANDARD_UW"),
                              "status": result.get("status", "")})
            _save_pending(pending); _save_processed(processed)
            unreviewed = [p for p in pending if not p.get("uw_reviewed", False)]
            return _safe_json({"new_found": len(new_pdfs), "newly_analysed": newly,
                               "total_pending": len(unreviewed),
                               "message": f"Found {len(new_pdfs)} new PDF(s). {len(unreviewed)} pending review."})
        except Exception as e:
            return _safe_json({"error": f"scan_new_submissions failed: {e}"})

    def _tool_get_pending_analyses(self) -> str:
        try:
            from src.agent.watcher import get_pending_analyses
            pending = get_pending_analyses()
            unreviewed = [p for p in pending if not p.get("uw_reviewed", False)]
            summary = [{"filename": p["filename"],
                        "recommendation": p.get("quick_recommendation", "STANDARD_UW"),
                        "analysed_at": p.get("analysed_at", ""),
                        "status": p.get("status", "")} for p in unreviewed]
            return _safe_json({"pending_count": len(unreviewed), "submissions": summary})
        except Exception as e:
            return _safe_json({"error": f"get_pending_analyses failed: {e}"})

    def _tool_approve_portfolio_update(self, confirmed: bool = True) -> str:
        if not confirmed:
            return _safe_json({"status": "cancelled", "message": "Portfolio update cancelled."})
        try:
            import subprocess
            results = []
            for name, script in [("mass_scoring", "src/business/mass_scoring.py"),
                                   ("mass_deltas",  "src/business/mass_deltas.py"),
                                   ("precompute_kg","scripts/precompute_kg.py")]:
                proc = subprocess.run([sys.executable, script, "--force"],
                                      capture_output=True, text=True, timeout=300,
                                      cwd=str(ROOT))
                results.append({"script": name, "success": proc.returncode == 0})
            all_ok = all(r["success"] for r in results)
            return _safe_json({"status": "completed" if all_ok else "partial",
                               "steps": results,
                               "message": "Portfolio updated. Refresh dashboard to see new insights."
                               if all_ok else "Some steps failed.",
                               "governance": {"triggered_by": "UW_EXPLICIT_APPROVAL"}})
        except Exception as e:
            return _safe_json({"error": f"approve_portfolio_update failed: {e}"})

    # ── NetworkX graph analytics — inline fallbacks ───────────────────────────

    def _tool_get_community_purity(self) -> str:
        try:
            from src.models.kg_graph_analytics import community_cluster_purity
            df = community_cluster_purity()
            if df.empty:
                return _safe_json({"error": "Community data not available"})
            return _safe_json({
                "communities": df.head(14).to_dict(orient="records"),
                "summary": {
                    "risk_pockets":   int((df["community_type"] == "Risk Pocket").sum()),
                    "contagion_risk": int((df["community_type"] == "Contagion Risk").sum()),
                },
                "governance": {
                    "advisory_only": True,
                    "basis": "louvain_structural_communities",
                    "notes": "Community-level only. Individual customer risk scores are independent.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"get_community_purity failed: {e}"})

    def _tool_find_cluster_bridges(self, top_n: int = 15) -> str:
        try:
            from src.models.kg_graph_analytics import find_cluster_bridges
            df = find_cluster_bridges(top_n=top_n)
            return _safe_json({
                "bridges": df.to_dict(orient="records") if not df.empty else [],
                "total": len(df),
                "governance": {
                    "advisory_only": True,
                    "basis": "networkx_broker_edge_traversal",
                    "notes": "Structural position only. Do NOT reassess individual risk based on bridge position.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"find_cluster_bridges failed: {e}"})

    def _tool_get_broker_centrality(self, top_n: int = 15) -> str:
        try:
            from src.models.kg_graph_analytics import broker_centrality_risks
            df = broker_centrality_risks()
            cols = [c for c in ["broker", "total", "approval_rate_pct",
                                 "network_importance", "danger_score"] if c in df.columns]
            return _safe_json({
                "brokers": df.head(top_n)[cols].to_dict(orient="records"),
                "governance": {
                    "advisory_only": True,
                    "basis": "networkx_degree_centrality",
                    "notes": "Danger score = concentration risk, NOT a quality assessment of the broker.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"get_broker_centrality failed: {e}"})

    def _tool_get_high_risk_central_nodes(self, top_n: int = 15) -> str:
        try:
            from src.models.kg_graph_analytics import high_risk_central_nodes
            df = high_risk_central_nodes(top_n=top_n)
            return _safe_json({
                "customers": df.to_dict(orient="records") if not df.empty else [],
                "governance": {
                    "advisory_only": True,
                    "basis": "networkx_centrality_metrics",
                    "notes": "Propagation priority only. Individual risk scores have NOT been elevated.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"get_high_risk_central_nodes failed: {e}"})

    def _tool_simulate_cascade_graph(self, event_type: str = "cyber_campaign",
                                      target_broker: str = None) -> str:
        try:
            # Fast path: use precomputed data (avoids 30s full graph traversal)
            gm_path = DATA_DIR / "graph_metrics.csv"
            subs_path = DATA_DIR / "all_submissions.csv"
            if not gm_path.exists() or not subs_path.exists():
                return _safe_json({"error": "Graph metrics not available"})

            gm = pd.read_csv(gm_path)
            subs = pd.read_csv(subs_path, low_memory=False)
            subs["is_bound"] = (subs["Submission Product Bound Premium Amount"].notna() &
                                 (subs["Submission Product Bound Premium Amount"] > 0))

            EVENT_PRODUCTS = {
                "cyber_campaign":      ["Cyber", "ZCIP"],
                "financial_contagion": ["Financial Lines", "Crime"],
                "supply_chain":        ["Technology"],
                "broker_failure":      [],
            }
            affected = EVENT_PRODUCTS.get(event_type, ["Cyber"])

            # D1: customers with matching product or broker
            if target_broker:
                d1_names = subs[subs["National Broker Name"].astype(str).str.contains(
                    target_broker, case=False, na=False)]["Submission Account Name"].unique()
            elif affected:
                mask = subs["Product Name"].astype(str).apply(
                    lambda p: any(kw.lower() in p.lower() for kw in affected))
                d1_names = subs[mask]["Submission Account Name"].unique()
            else:
                d1_names = []

            # D1 enriched with graph metrics
            d1_enriched = gm[gm["customer"].isin(d1_names)][
                ["customer","cluster","risk_score","recommendation"]].head(20).to_dict(orient="records")

            # D2: customers sharing broker with D1
            d1_brokers = subs[subs["Submission Account Name"].isin(d1_names)]["National Broker Name"].unique()
            d2_names = subs[subs["National Broker Name"].isin(d1_brokers) &
                             ~subs["Submission Account Name"].isin(d1_names)]["Submission Account Name"].unique()
            d2_enriched = gm[gm["customer"].isin(d2_names)][
                ["customer","cluster","risk_score","recommendation"]].head(20).to_dict(orient="records")

            return _safe_json({
                "scenario": {"event_type": event_type, "is_hypothetical": True,
                              "target_broker": target_broker},
                "cascade": {
                    "d1_direct_count":  len(d1_names),
                    "d2_broker_count":  len(d2_names),
                    "total_affected":   len(d1_names) + len(d2_names),
                    "d1_sample":        d1_enriched,
                    "d2_sample":        d2_enriched,
                    "d1_brokers_involved": list(d1_brokers[:5]),
                },
                "governance": {
                    "advisory_only": True,
                    "basis": "csv_product_broker_matching",
                    "notes": "HYPOTHETICAL SCENARIO ONLY — NOT A PREDICTION. "
                             "Fast approximation using product/broker matching. "
                             "For full graph traversal use the MCP kg_server.",
                },
            })
        except Exception as e:
            return _safe_json({"error": f"simulate_cascade_graph failed: {e}"})

    def chat(self, user_message: str, history: list = None) -> Generator[Dict, None, None]:
        """
        Run the agent. Yields dicts with type: 'tool_call'|'tool_result'|'text'|'done'.
        history: list of {"role": "user"|"assistant", "content": str} for multi-turn.
        """
        # Memory: inject prior session context if relevant customer mentioned
        memory_context = self._load_customer_memory(user_message)
        system = SYSTEM_PROMPT + (f"\n\n{memory_context}" if memory_context else "")

        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-20:])  # keep last 20 turns to bound context growth
        messages.append({"role": "user", "content": user_message})

        full_response = ""
        tools_called = []
        turn = 0

        while turn < MAX_TURNS:
            turn += 1
            # Retry with exponential backoff on transient API errors
            response = None
            for _attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        max_tokens=2048,
                        tools=self._get_tools(),
                        messages=messages,
                    )
                    break
                except Exception as _e:
                    if _attempt == 2:
                        raise
                    import time as _time
                    _time.sleep(2 ** _attempt)

            msg = response.choices[0].message

            # Emit text content
            if msg.content:
                full_response += msg.content
                yield {"type": "text", "content": msg.content}

            # Handle tool calls
            if msg.tool_calls:
                messages.append(msg)

                # Parallel via asyncio.gather in MCP mode — safe with shared event loop
                use_parallel = (
                    len(msg.tool_calls) > 1 and
                    os.getenv("USE_MCP", "false").lower() == "true"
                )

                if use_parallel:
                    from src.agent.mcp_client import call_tools_parallel_mcp
                    call_list = [
                        (tc.function.name, json.loads(tc.function.arguments), tc.id)
                        for tc in msg.tool_calls
                    ]
                    result_map = dict(call_tools_parallel_mcp(call_list))
                    for tc in msg.tool_calls:
                        tool_name  = tc.function.name
                        tool_input = json.loads(tc.function.arguments)
                        result     = result_map.get(tc.id, _safe_json({"error": "parallel exec failed"}))
                        tools_called.append(tool_name)
                        yield {"type": "tool_call", "tool": tool_name, "input": tool_input}
                        yield {"type": "tool_result", "tool": tool_name, "result": result}
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": result[:4000]})
                else:
                    # Sequential — inline mode or single tool
                    for tc in msg.tool_calls:
                        tool_name  = tc.function.name
                        tool_input = json.loads(tc.function.arguments)
                        tools_called.append(tool_name)
                        yield {"type": "tool_call", "tool": tool_name, "input": tool_input}
                        try:
                            result = self._run_tool(tool_name, tool_input)
                        except Exception as e:
                            result = _safe_json({"error": f"Tool {tool_name} failed: {e}"})
                        yield {"type": "tool_result", "tool": tool_name, "result": result}
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": result[:4000],
                    })
            else:
                # Reflexion: self-review for completeness + governance compliance
                addition = self._reflect(user_message, tools_called, full_response)
                if addition:
                    yield {"type": "text", "content": f"\n\n---\n*Agent review:* {addition}"}
                self._log_decision(user_message, tools_called, full_response)
                self._upsert_entity_memory(tools_called, full_response)
                yield {"type": "done"}
                break
        else:
            # MAX_TURNS reached
            self._log_decision(user_message, tools_called, full_response)
            yield {"type": "text", "content": "\n\n⚠️ *Analysis reached maximum steps — partial response above.*"}
            yield {"type": "done"}

    def _reflect(self, query: str, tools_called: list, response: str) -> str | None:
        """Governance compliance check — 2 critical EU AI Act checks only (faster, lighter)."""
        try:
            review = self.client.chat.completions.create(
                model=self.model,
                max_tokens=80,
                messages=[{"role": "user", "content": f"""Check this underwriting agent response:
TOOLS: {tools_called}
RESPONSE: {response[:400]}

Check ONLY these 2 governance rules:
1. If FRESH_UW recommended → was query_uw_guidelines called?
2. Does response include "advisory" or "human review"?

Reply: COMPLETE — or one correction max 40 words."""}]
            )
            text = review.choices[0].message.content.strip()
            return None if text.upper().startswith("COMPLETE") else text
        except Exception:
            return None  # reflexion must never block the main response

    def _upsert_entity_memory(self, tools_called: list, response: str) -> None:
        """Update per-customer structured memory from this session (A-MEM3)."""
        customer_memory_path = DATA_DIR / "customer_memory.json"
        match = re.search(r'\b(FAST_TRACK|STANDARD_UW|FRESH_UW)\b', response)
        recommendation = match.group(1) if match else None

        # Extract customer names from tools_called results — use customers from history/score calls
        customers = set(re.findall(
            r'Company\s+\d+|[A-Z][A-Za-z0-9\s]{3,30}(?=\s)',
            response
        ))

        if not customers or not recommendation:
            return

        try:
            memory = {}
            if customer_memory_path.exists():
                with open(customer_memory_path, "r", encoding="utf-8") as f:
                    memory = json.load(f)

            from datetime import datetime as _dt
            ts = _dt.now().isoformat()[:10]
            for customer in list(customers)[:3]:  # cap at 3 per session
                customer = customer.strip()
                if len(customer) < 4:
                    continue
                rec = memory.get(customer, {
                    "review_count": 0,
                    "ai_recommendations": [],
                    "last_reviewed": None,
                })
                rec["review_count"] += 1
                rec["last_reviewed"] = ts
                if recommendation:
                    rec["ai_recommendations"].append(recommendation)
                    rec["ai_recommendations"] = rec["ai_recommendations"][-10:]  # keep last 10
                memory[customer] = rec

            with open(customer_memory_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2)
        except Exception:
            pass  # entity memory must never crash the agent

    def _load_customer_memory(self, query: str) -> str:
        """
        Build prior context for the agent from two sources:
        1. decisions_log.jsonl — episodic memory (past sessions)
        2. customer_memory.json — entity memory (structured per-customer summary)
        """
        # Match: "Company XXXX", known brokers, or capitalised multi-word names
        mentions = re.findall(
            r'Company\s+\d+'                                       # "Company 7130"
            r'|(?:MARSH|AON|GALLAGHER|WILLIS|LOCKTON|CHUBB|AIG)'  # top brokers
            r'|[A-Z][A-Za-z0-9]{2,}\s+[A-Z][A-Za-z0-9]{2,}'      # "MeridianTech Corp"
            r'|[A-Z][A-Za-z0-9\s]{3,28}(?=\s+(?:risk|score|history|submission|customer|delta|brief|exposure|cascade|peer|profile))',
            query, re.IGNORECASE
        )
        mentions = list({m.strip() for m in mentions if len(m.strip()) > 3})
        if not mentions:
            return ""

        lines = []

        # Source 1: entity memory (structured, fast lookup)
        entity_path = DATA_DIR / "customer_memory.json"
        if entity_path.exists():
            try:
                with open(entity_path, "r", encoding="utf-8") as f:
                    entity_mem = json.load(f)
                for m in mentions:
                    rec = next((v for k, v in entity_mem.items() if m.lower() in k.lower()), None)
                    if rec:
                        recs = rec.get("ai_recommendations", [])
                        lines.append(
                            f"Entity memory — {m}: reviewed {rec['review_count']}x, "
                            f"last {rec['last_reviewed']}, "
                            f"AI recommendations: {recs[-3:]}"
                        )
            except Exception:
                pass

        # Source 2: episodic memory (decisions log, last 5 relevant entries)
        if DECISIONS_LOG.exists():
            try:
                past = []
                with open(DECISIONS_LOG, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-100:]  # last 100 entries — keeps scan fast as log grows
                for line in lines:
                    try:
                        rec = json.loads(line.strip())
                        if any(m.lower() in json.dumps(rec).lower() for m in mentions):
                            past.append(rec)
                    except Exception:
                        continue
                for s in past[-5:]:
                    ts     = s.get("ts", "")[:10]
                    uw_dec = s.get("uw_decision") or "not captured"
                    ai_rec = s.get("ai_recommendation") or ""
                    lines.append(
                        f"[{ts}] AI: {ai_rec} | UW decision: {uw_dec} | "
                        f"Query: \"{s.get('query','')[:60]}\""
                    )
            except Exception:
                pass

        if not lines:
            return ""
        return "Prior context:\n" + "\n".join(f"  {l}" for l in lines)

    def _log_decision(self, query: str, tools_called: list, response: str) -> None:
        """Append interaction record to decisions_log.jsonl (Art. 12 EU AI Act)."""
        from datetime import datetime as _dt
        match = re.search(r'\b(FAST_TRACK|STANDARD_UW|FRESH_UW)\b', response)
        record = {
            "ts": _dt.now().isoformat(),
            "query": query[:300],
            "tools_called": tools_called,
            "model": self.model,
            "ai_recommendation": match.group(1) if match else None,
            "response_preview": response[:200],
            "uw_decision": None,   # filled by UW decision capture in dashboard
            "uw_note": None,
        }
        try:
            DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # logging must never crash the agent
