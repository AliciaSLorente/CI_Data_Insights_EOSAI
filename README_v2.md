# EOS AI — Agentic AI for Underwriting
## Zurich Hackathon MVP: Leveraging Historical Data to Improve New Business Decisions

**Deadline**: 22 June 2026
**Stack**: Python 3.12 · Streamlit · NetworkX · Claude Sonnet 4.6 · MCP · RAG
**Local only**: no cloud required

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL

# 3. Run data pipeline (first time only)
python src/business/mass_scoring.py
python src/business/mass_deltas.py
python scripts/build_knowledge_graph.py
python scripts/precompute_kg.py
python -m src.rag.guidelines_rag --build

# 4. Launch demo
python start_demo.py --mcp        # Phase 2: MCP servers + background watcher
python start_demo.py              # Phase 1: inline tools only

# 5. Stop
python start_demo.py --stop
```

Dashboard opens at `http://localhost:8501`.

---

## Problem Statement

Zurich Specialties receives repeat submissions from the same customers year after year but treats each as new business — ignoring 5+ years of historical context. A UW currently spends 55–80 minutes per repeat submission doing manual research that EOS AI delivers in 3 minutes.

**The system answers:**
1. Is this a repeat customer? What is their full history?
2. What changed since their last submission (controls, broker, status, premium)?
3. Should this be Fast-Tracked, Standard UW, or Fresh UW?
4. Who are their structural peers and what were their outcomes?
5. What is the cascade risk to the portfolio if a hazard event occurs?

---

## Solution

**EOS AI** is an agentic AI platform with 5 pages, 18 tools, a real-time Knowledge Graph, RAG on Zurich guidelines, and an event-driven new submission watcher.

```
Inputs
  Dataset 1: 46,318 Specialties submissions (2021–2026)
  Dataset 2: 162 PDFs across 25 repeat Cyber customers

Processing
  → Repeat customer detection (9,078 customers, 34% of book)
  → PDF extraction (26 fields: revenue, controls, policies, dates)
  → Delta computation (first vs latest submission per customer)
  → Risk scoring (0-100 + FAST_TRACK / STANDARD_UW / FRESH_UW)
  → Knowledge Graph (10,232 nodes, 36,312 edges, KMeans k=3)
  → RAG index (64 chunks from Zurich UW guidelines)

Output
  → AI Agent: 18 tools, memory, reflexion, EU AI Act governance
  → Dashboard: 5 interactive pages
  → Event-driven watcher: auto-analyses new PDF submissions
```

---

## Architecture

```
start_demo.py --mcp
  ├── submissions_server.py  :8601
  ├── scoring_server.py      :8602
  ├── kg_server.py           :8603
  ├── watcher_server.py      :8604
  ├── watcher.py             [background, polls folder every 30s]
  └── Streamlit              :8501
        app.py (~120 lines — routing + pre-warm + badge + toast)
          ├── customer.py      Customer Intelligence: briefing banner + Queue/Drill-Down/Side-by-Side  ← LANDING
          ├── agent.py         Ask EOS AI: MVP questions + UW workflow chat
          ├── portfolio.py     Portfolio Analytics: charts + accuracy validation
          ├── graph.py         Portfolio Risk Map: Customer Network/Cascade/Risk Clusters
          └── new_submission.py New Submission: auto-scan + digital twin
```

**Startup pre-warm:** `_prewarm()` (`@st.cache_resource` in app.py) populates all `@st.cache_data` loaders on server start — first page load is instant.

**Agent loop per message:**
```
Memory read (customer_memory.json + decisions_log.jsonl[-100 lines])
→ Tool discovery (_get_tools() → MCP servers via discover_mcp_tools())
→ ReAct loop (max 10 turns, retry, error boundary, 4000-char result cap)
  → Parallel tool execution when >1 tool called (asyncio.gather via call_tools_parallel_mcp())
→ Reflexion (_reflect(): 2 checks, max_tokens=80 — lightweight governance audit)
→ Log decision (decisions_log.jsonl — Art. 12 EU AI Act)
→ Entity memory upsert (customer_memory.json)
```

---

## Dashboard Pages

| Page | Key features |
|---|---|
| **Customer Intelligence** *(landing)* | Daily briefing banner (expandable, "Mark read"), bind rate proof in queue header, Prioritization queue (period filter: All/7/30/90 days), Drill-Down (AI recommendation headline + UW decision capture), Side-by-Side (inline agent) |
| **Ask EOS AI** | MVP Coverage expander (4 tabs, 12 targeted questions) + UW Workflow expander (5 tabs), newest-first chat, reasoning chain expander, inline Plotly charts (bar · pie · line · scatter · heatmap) |
| **Portfolio Analytics** | Submission trends 2019–2025, broker performance, risk clusters, delta trajectories, recommendation accuracy chart (bind rate by tier) |
| **Portfolio Risk Map** | Customer Network (show peers, depth 2), Cascade Simulation (Network Cascade + Ripple Effect views), Risk Clusters (bridge nodes + AI cluster explanation) |
| **New Submission** | Auto-scan watch folder, PDF upload + extraction, digital twin peer matching, portfolio cascade impact |

---

## The 18 Agent Tools

| Group | Tools |
|---|---|
| Data Curation | search_portfolio, get_customer_history, get_underwriter_patterns |
| UW Metrics | get_risk_score, get_submission_delta, get_control_delta |
| KG Discovery | portfolio_analytics, explain_recommendation, find_structural_peers, get_community_purity, find_cluster_bridges, get_broker_centrality, get_high_risk_central_nodes, simulate_cascade_graph |
| Guidelines (RAG) | query_uw_guidelines |
| Watcher | scan_new_submissions, get_pending_analyses, approve_portfolio_update |

---

## Memory System

| Layer | Storage | Written | Read |
|---|---|---|---|
| Session | chat_history (session state) | Every message | Every message |
| Episodic | decisions_log.jsonl | After every chat() | At chat() start if customer mentioned |
| Entity | customer_memory.json | After every chat() | At chat() start if customer mentioned |
| Semantic | RAG vector index | Once (build time) | query_uw_guidelines tool |

---

## EU AI Act Compliance

| Article | Requirement | Status |
|---|---|---|
| Art. 12 | Logging & record-keeping | ✅ decisions_log.jsonl — every AI interaction logged |
| Art. 13 | Transparency | ✅ Reflexion enforces advisory disclaimer on every response |
| Art. 14 | Human oversight | ✅ UW Decision Capture button in Customer Drill-Down |
| Art. 15 | Accuracy & robustness | ⚠️ Accuracy chart (bind rate by tier) exists; formal validation pending |
| Art. 10 | Data governance | ✅ Bias analysis tab in Portfolio Analytics |

**All recommendations are advisory. Human underwriter decision required.**

---

## Repository Structure

```
app.py                    Streamlit entry point (~120 lines, routing + _prewarm + badge + toast)
start_demo.py             Launch script (Phase 1 / Phase 2 --mcp / --stop)
src/
  agent/
    orchestrator.py       18 tools, ReAct loop, memory, parallel tools, reflexion (MAX_TURNS=10)
    mcp_client.py         MCP HTTP routing + discover_mcp_tools() + call_tools_parallel_mcp()
    briefing.py           Daily briefing (uses dashboard_data.py loaders)
    watcher.py            Event-driven PDF watcher + get_badge_count() (TTL 30s) + get_latest_pending_alert()
  pages/
    customer.py           Customer Intelligence — LANDING: briefing banner + bind rate + queue + drill-down
    agent.py              Ask EOS AI: MVP Coverage expander (4 tabs) + UW Workflow expander (5 tabs)
    portfolio.py          Portfolio Analytics (recommendation_accuracy chart + bias analysis)
    graph.py              Portfolio Risk Map (3 views, dual cascade)
    new_submission.py     New Submission (_auto_scan on every render)
  mcp_servers/
    submissions_server.py :8601 — search_portfolio, get_customer_history, get_underwriter_patterns
    scoring_server.py     :8602 — get_risk_score, get_submission_delta, get_control_delta
    kg_server.py          :8603 — 9 KG + RAG tools
    watcher_server.py     :8604 — scan_new_submissions, get_pending_analyses, approve_portfolio_update
  data/
    dashboard_data.py     30 @st.cache_data loaders
    pdf_parser.py         PDF field extraction (26 fields including policy dates)
  models/
    kg_visualisation.py   cascade_network_html, cascade_ripple_html, cluster_life_html
    kg_graph_analytics.py NetworkX analytics, generate_graph_xai, generate_cluster_xai
    digital_twin.py       Peer matching for new submissions
  rag/
    guidelines_rag.py     RAG on Zurich UW guidelines (64 chunks)
data/
  raw/
    new_submissions/      Drop PDFs here — watcher auto-analyses every 30s
    uw_guidelines/        Zurich UW guideline PDFs for RAG index
  parsed/                 Generated CSVs, KG pickle, audit logs (gitignored recommended)
docs/
  ARCHITECTURE.md         System design
  USER_MANUAL.md          Full operational documentation
  AI_GOVERNANCE_BY_PHASE.md  EU AI Act compliance roadmap
  3-pager.md              Original use case brief
```

---

## Data Files

| File | Content | Size |
|---|---|---|
| all_submissions.csv | Full submission universe | 46,318 rows |
| all_recommendations.csv | Risk scores + FAST/STD/FRESH | 9,078 rows |
| all_deltas.csv | First→latest deltas per customer | 9,078 rows |
| knowledge_graph.pkl | NetworkX MultiGraph | 10,232 nodes, 36,312 edges |
| graph_metrics.csv | PageRank, cluster, risk score | 9,078 rows |
| pdf_extracted_fields.csv | Controls + dates from PDFs | 162 rows (25 companies) |
| decisions_log.jsonl | AI interactions audit trail (Art.12) | grows |
| customer_memory.json | Entity memory per customer | grows |
| pending_analysis.json | Watcher queue | grows |
