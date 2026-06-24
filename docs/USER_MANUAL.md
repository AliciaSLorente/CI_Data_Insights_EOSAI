# EOS AI — User Manual

**Version:** Hackathon MVP · Phase 2 Active  
**Date:** June 2026  
**Use case:** Leveraging Historical Data to make better New Business decisions (Specialties Underwriting)

---

## Table of Contents

1. [What this system does](#1-what-this-system-does)
2. [How to run](#2-how-to-run)
3. [Project structure](#3-project-structure)
4. [The dashboard — 5 pages](#4-the-dashboard)
5. [The agent — 18 tools](#5-the-agent)
6. [Memory system](#6-memory-system)
7. [Event-driven watcher](#7-event-driven-watcher)
8. [MCP servers](#8-mcp-servers)
9. [RAG — UW Guidelines](#9-rag)
10. [Data pipeline](#10-data-pipeline)
11. [Phase roadmap](#11-phase-roadmap)

---

## 1. What this system does

Zurich Specialties sees the same customer multiple times as New Business but treats each submission as net new — losing 5+ years of historical context. This system applies **renewal-like intelligence to New Business decisions**.

**Core capability:** When a UW receives a new submission, the agent surfaces:
- Full historical context for repeat customers
- Delta analysis (what changed since last submission)
- Structural peers from the Knowledge Graph
- Grounded recommendations citing Zurich UW guidelines (RAG)
- Cascade risk if a hazard event occurs

**All recommendations are advisory. Human underwriter decision required.**  
*(EU AI Act Art. 14 — Human Oversight)*

---

## 2. How to run

### Prerequisites

```bash
# Run the data pipeline once (required before first launch):
python src/business/mass_scoring.py
python src/business/mass_deltas.py
python scripts/precompute_kg.py
python scripts/build_knowledge_graph.py

# Build RAG index from UW guidelines:
python -m src.rag.guidelines_rag --build
```

### Launch modes

```bash
# Phase 1 — inline tools (fast, no MCP servers needed):
python start_demo.py

# Phase 2 — MCP HTTP servers (persistent, architecture demo):
python start_demo.py --mcp

# Stop everything:
python start_demo.py --stop
```

### Environment variables (`.env`)

```
ANTHROPIC_API_KEY=sk-...              # Zurich GenAI proxy key
ANTHROPIC_BASE_URL=https://genai-lounge-nx-litellm-uat-emea.zurich.com
ANTHROPIC_MODEL=eu.anthropic.claude-sonnet-4-6
USE_MCP=false                         # true = route tools to MCP HTTP servers
UW_WATCH_FOLDER=data/raw/new_submissions  # folder monitored for new PDFs
```

---

## 3. Project structure

```
app.py                          # Entry point: routing + sidebar (107 lines)
start_demo.py                   # Launcher: validates data + starts 4 MCP + watcher + Streamlit
.env                            # API keys (git-ignored)

src/
  pages/
    agent.py                    # Ask EOS AI page (chat + suggested questions, @st.cache_resource singleton)
    customer.py                 # Customer Intelligence (Queue / Drill-Down / Side-by-Side)
    portfolio.py                # Portfolio Analytics (charts + recommendation accuracy)
    graph.py                    # Portfolio Risk Map (Customer Network / Cascade / Risk Clusters)
    new_submission.py           # New Submission (auto-scan + PDF + digital twin)

  agent/
    orchestrator.py             # Orchestrator: 18 tools, MCP routing, reflexion, memory
    mcp_client.py               # MCP HTTP client + discover_mcp_tools()
    briefing.py                 # Daily proactive briefing (uses dashboard_data loaders)
    watcher.py                  # Event-driven watcher: get_badge_count(), watch_folder() 30s

  mcp_servers/
    submissions_server.py       # Port 8601: search_portfolio, get_customer_history, get_underwriter_patterns
    scoring_server.py           # Port 8602: get_risk_score, get_submission_delta, get_control_delta
    kg_server.py                # Port 8603: 9 KG tools + query_uw_guidelines (RAG)
    watcher_server.py           # Port 8604: scan_new_submissions, get_pending_analyses, approve_portfolio_update

  rag/
    guidelines_rag.py           # RAG: embed + retrieve Zurich UW guideline PDFs

  startup/
    pipeline.py                 # Data file validation + auto-regeneration

  models/
    kg_graph_analytics.py       # NetworkX: communities, bridges, centrality
    kg_visualisation.py         # pyvis HTML generators
    digital_twin.py             # Digital twin: graph-enhanced peer matching
    cascade_risk.py             # Cascade simulation (portfolio-level)
    model_metrics.py            # KMeans validation, score distribution

  data/
    dashboard_data.py           # Cached data loaders (@st.cache_data)
    pdf_parser.py               # PDF text extraction + control detection

data/
  raw/
    uw_guidelines/              # Zurich UW guideline PDFs (RAG source)
    new_submissions/            # Watch folder for new submission PDFs

  parsed/
    all_submissions.csv         # 46,318 submissions (2021-2026)
    all_recommendations.csv     # 9,078 customers scored
    all_deltas.csv              # First → latest submission delta
    knowledge_graph.pkl         # NetworkX graph (10,232 nodes, 36,312 edges)
    graph_metrics.csv           # PageRank, betweenness, degree per customer
    graph_communities.csv       # Louvain community assignments
    uw_guidelines_index.json    # RAG embeddings index (text-embedding-3-large)
    kg_*.csv                    # Pre-computed KG analytics (fast dashboard loads)
    pending_analysis.json       # Watcher: agent-analysed PDFs awaiting review
    decisions_log.jsonl         # AI interactions audit trail (Art. 12 EU AI Act)
    customer_memory.json        # Entity memory per customer (review count, recommendations)
```

---

## 4. The dashboard

Five pages, each a standalone module in `src/pages/`. Navigation: **Customer → Ask EOS AI → Portfolio → Portfolio Risk Map → New Submission**.

### Customer Intelligence (landing page)

The first page the UW sees on opening the app.

**Daily Briefing banner** (top, collapsible)
- Pre-generated at startup via `briefing.py` — portfolio highlights, new submissions, broker alerts
- "Ask agent about this →" button navigates to Ask EOS AI with context
- "Mark read" collapses the banner for the rest of the session

**Prioritization Queue tab**
- Model validation bar at top: **FAST_TRACK bind: 68% · STANDARD_UW: 41% · FRESH_UW: 12%** (EU AI Act Art.15 proof)
- Full portfolio queue (9,078 customers) with sort + period filter (All / Last 7 / 30 / 90 days)
- Metrics from full dataset: Total / Fast-Track / Standard UW / Fresh UW counts
- Recommendation distribution pie + risk score histogram with thresholds

**Drill-Down**
- Select customer → AI recommendation headline (colour-coded, score + confidence)
- Metrics: Submissions / Products / Latest Status
- Pre-Call Brief button → sends to AI Agent with pre-filled prompt
- Submission frequency bar chart + decision history pie chart
- Delta metrics: Span / Trend / Premium delta / Broker changed
- Controls evolution heatmap (green = present, red = absent)
- **UW Decision Capture**: Approve / Override / Decline → logged to `decisions_log.jsonl` (Art. 14)

**Side-by-Side**
- Field-by-field comparison: first vs latest PDF submission per customer
- Changed values highlighted. Inline agent call — answers "what changed?" without navigating away.

### Portfolio Analytics

- Key metrics: Total Submissions / Repeat Customers / Approval Rate / Top Broker
- Submission volume 2019–2025 bar chart + Status Distribution pie
- Top 8 Products + Broker scatter (Volume vs Approval Rate)
- Risk Clusters: customers by cluster + avg approval rate per cluster
- Delta trajectories: Improved / Stable / Degraded pie + bar
- **Recommendation Accuracy**: bind rate (%) by FAST_TRACK / STANDARD_UW / FRESH_UW (Art. 15)
- Emerging Risk Signals: top 5 KG alerts

### Portfolio Risk Map

Three views (radio selector):

**Customer Network**
- Select any customer → 2-hop network (direct connections + structural peers)
- Nodes: Customer (blue) · Broker (orange) · Sector (green) · Product (purple) · High Risk (red)
- `Show peers` checkbox: depth 1 (connections only) vs depth 2 (includes peer customers)
- AI Graph Explanation: Claude explains network position and risk implications

**Cascade Simulation**
- Event: Ransomware/Cyber · Financial Contagion · Supply Chain · Broker Failure
- Optional: target specific broker (e.g. MARSH)
- **Two visualization styles**: Network Cascade (operational) + Ripple Effect (academic, node size = degree)
- D1/D2/D3 business context always visible + Impact metrics (D1 count / D2 count / Premium at Risk)

**Risk Clusters**
- Full portfolio segmented by KMeans k=3 (Low/Moderate/High Risk)
- Bridge nodes (magenta): High Risk customers connected to Low Risk via shared broker
- AI Cluster Explanation: portfolio-level narrative via `generate_cluster_xai()`

### New Submission Analyzer

1. **Auto-scan** — on every page load, scans `UW_WATCH_FOLDER` for new unanalysed PDFs
2. **Rescan button** — manual trigger with explicit "X new PDFs found / No new PDFs" feedback
3. **Agent pre-analysis** — pre-analysed PDFs shown with recommendation + deep dive button
4. **PDF upload** — extracts: revenue, employees, 12 security controls, product, broker, policy dates
5. **Digital twin** — finds structurally similar historical customers via KG
6. **Gap analysis** — missing controls vs approved twin profile
7. **Portfolio cascade impact** — hypothetical cascade if this customer is approved

---

## 5. The agent

Single orchestrator (`src/agent/orchestrator.py`) with **18 tools** across 5 groups. Agent singleton via `@st.cache_resource` in `agent.py` — data loaded once per process.

### Ask EOS AI page

Accessible from nav. Not the landing page — UW navigates here for deeper analysis.

1. **Free text input** — UW types any question. Agent uses 18 tools and RAG.
2. **Suggested questions — 2 sections:**
   - `📊 MVP Coverage` — 4 tabs: MVP-1 Portfolio · MVP-2 Deltas · MVP-3 Scoring · KG & Risk  
     Covers hackathon success criteria
   - `💼 UW Workflow` — 5 tabs: Customer Analysis · Portfolio Trends · Opportunities · Cascade & Hazard · KG & Guidelines  
     Daily underwriter use cases
3. **Chat order** — newest response shown first (reverse chronological)
4. **Chain of thought** — every tool call visible in "Agent Reasoning Chain" expander
5. **Inline charts** — 5 types rendered via Plotly (`eos_chart` JSON blocks). Type is mandatory-selected by the agent:
   - `line` — time series, score evolution over years (triggered by date/year data)
   - `scatter` — correlation between two numeric variables (revenue vs score, controls vs bind rate)
   - `heatmap` — risk matrix across two dimensions (sector × broker, customer × control)
   - `bar` — simple named comparisons without time axis
   - `pie` — percentage/share distributions (parts of a whole)

### Agent loop (per message)

```
_load_customer_memory()  →  inject episodic + entity context into system prompt
_get_tools()             →  fetch tool schemas from MCP servers (or TOOLS fallback)
while turn < 10:         →  ReAct loop (MAX_TURNS = 10, 3-retry backoff)
    LLM call → text or tool_calls (batched in one turn when possible)
    if MCP mode + multiple tools → call_tools_parallel_mcp() via asyncio.gather
    else → sequential _run_tool() → MCP HTTP or inline fallback → result[:4000]
_reflect()               →  2-check governance: disclaimer? guidelines cited?
_log_decision()          →  append to decisions_log.jsonl (Art. 12)
_upsert_entity_memory()  →  update customer_memory.json
```

### Tools

| Group | Tool | What it returns |
|---|---|---|
| **Data Curation** | `search_portfolio` | Filter 46,318 submissions |
| | `get_customer_history` | Full submission history |
| | `get_underwriter_patterns` | UW approval rates, decision patterns |
| **UW Metrics** | `get_risk_score` | Score 0-100 + components |
| | `get_submission_delta` | First vs latest delta |
| | `get_control_delta` | Security control changes (25 PDF customers) |
| **KG Discovery** | `portfolio_analytics` | Clusters, anomalies, whitespace |
| | `find_structural_peers` | NetworkX graph neighbors |
| | `get_community_purity` | Louvain × KMeans analysis |
| | `find_cluster_bridges` | High Risk → Low Risk paths |
| | `get_broker_centrality` | Danger score = centrality × poor approval |
| | `get_high_risk_central_nodes` | Most central high-risk customers |
| | `simulate_cascade_graph` | Hazard event propagation |
| | `explain_recommendation` | XAI: why this recommendation |
| **Guidelines (RAG)** | `query_uw_guidelines` | Retrieves Zurich policy passages with citation |
| **Watcher** | `scan_new_submissions` | Scans folder + full agent analysis |
| | `get_pending_analyses` | Returns analysed PDFs awaiting review |
| | `approve_portfolio_update` | Re-runs pipeline (UW explicit approval required) |

### Governance rules (embedded in system prompt)

- **Cascade tools**: always "hypothetical scenario, not prediction" (EU AI Act Art. 15)
- **Bridge/centrality tools**: structural position only, never individual risk reassessment
- **RAG**: always cite the source passage; never paraphrase without original text
- **Portfolio update**: ONLY called after explicit UW confirmation ("yes", "approve", "update")
- **Reflexion**: after every response, `_reflect()` checks disclaimer + guidelines + completeness
- **Planner rule**: for multi-customer or complex queries, agent outputs a plan before executing

---

## 6. Memory system

Four layers injected into every agent call:

| Layer | Storage | Written when | Read when |
|---|---|---|---|
| **Session** | `st.session_state['chat_history']` (last 20 turns) | Every message | Every message |
| **Episodic** | `decisions_log.jsonl` | After every `chat()` | Query mentions known customer |
| **Entity** | `customer_memory.json` | After every `chat()` | Query mentions known customer |
| **Semantic** | RAG vector index | Once at build time | `query_uw_guidelines` tool |

**Episodic record** (per interaction):
```json
{"ts": "...", "query": "...", "tools_called": [...],
 "ai_recommendation": "STANDARD_UW", "uw_decision": null}
```
`uw_decision` is filled when UW logs their decision via the Drill-Down capture button.

**Entity record** (per customer):
```json
{"Company 7130": {"review_count": 3, "last_reviewed": "2026-06-17",
                  "ai_recommendations": ["STD", "STD", "FAST_TRACK"]}}
```

**Context injection** at session start — if query mentions a customer name:
```
Prior context:
  Entity memory — Company 7130: reviewed 3x, last 2026-06-17, AI: ['STD','STD','FAST']
  [2026-06-15] AI: STANDARD_UW | UW decision: FAST_TRACK | Query: "risk profile..."
```

---

## 7. Event-driven watcher

The watcher runs as a **background process** started alongside the MCP servers.

```bash
# Started automatically by:
python start_demo.py --mcp

# Polls UW_WATCH_FOLDER (default: data/raw/new_submissions/) every 30 seconds
# Command: python -m src.agent.watcher
```

**Flow when PDF arrives:**
1. `watch_folder()` detects new file (not in `processed_submissions.json`)
2. `analyse_new_pdf()` runs: PDF parse → product/broker extraction → quick risk assessment
3. Result saved to `pending_analysis.json` (includes `quick_recommendation`, `quick_rationale`, `controls_summary`)
4. `get_badge_count()` called by `app.py` on next Streamlit render → badge updates in sidebar
5. New Submission page shows the pre-analysed result
6. UW clicks "Add to portfolio?" → agent asks `approve_portfolio_update` → full pipeline re-run
7. `mark_reviewed()` closes the loop

---

## 8. MCP servers

Four standalone HTTP servers (SSE transport). Started by `start_demo.py --mcp`.

| Server | Port | Tools |
|---|---|---|
| `submissions_server.py` | 8601 | search_portfolio, get_customer_history, get_underwriter_patterns |
| `scoring_server.py` | 8602 | get_risk_score, get_submission_delta, get_control_delta |
| `kg_server.py` | 8603 | portfolio_analytics, find_structural_peers, explain_recommendation, get_community_purity, find_cluster_bridges, get_broker_centrality, get_high_risk_central_nodes, simulate_cascade_graph, query_uw_guidelines |
| `watcher_server.py` | 8604 | scan_new_submissions, get_pending_analyses, approve_portfolio_update |

**Transport logic** (`mcp_client.py`):
1. Check if HTTP server is running on expected port (TCP socket, 0.5s timeout)
2. If YES → HTTP SSE session (cached, ~5ms warm)
3. If NO → stdio subprocess fallback (~480ms)

Data is cached at server level — CSVs loaded once per server process.

---

## 9. RAG

Source documents: 3 Zurich UW guideline PDFs in `data/raw/uw_guidelines/`:
- `Global CI Cyber UW Guideline.pdf`
- `ZNA PL&C MM Cyber Playbook 2.01.26.pdf`
- `Zurich Cyber Brochure - Oct18.pdf`

**Index**: 64 chunks, embeddings via `text-embedding-3-large` (Zurich proxy).

**Usage**: the agent calls `query_uw_guidelines(question)` when making recommendations, particularly for Fresh UW decisions. Returns top passages with source citation.

**Governance**: agent must always cite the source. Never paraphrase without showing original text.

**Rebuild index**:
```bash
python -m src.rag.guidelines_rag --build --force
```

---

## 10. Data pipeline

All heavy computation runs **offline, once**. The dashboard reads pre-computed files.

### Execution order

```bash
# 1. Ingest raw Excel (Dataset 1):
python src/data/loader.py

# 2. Extract PDF controls (Dataset 2):
python extract_pdfs.py

# 3. Score all 9,078 repeat customers:
python src/business/mass_scoring.py

# 4. Compute first→latest deltas:
python src/business/mass_deltas.py

# 5. Pre-compute KG analytics (fast dashboard loading):
python scripts/precompute_kg.py

# 6. Build real NetworkX graph:
python scripts/build_knowledge_graph.py

# 7. Build RAG index:
python -m src.rag.guidelines_rag --build

# 8. Generate demo test PDF:
python scripts/generate_sample_submission.py
```

### Auto-regeneration

`start_demo.py` calls `src/startup/pipeline.py` which:
- Validates all required files exist and are non-empty
- Auto-regenerates empty KG pre-computed CSVs
- Auto-builds RAG index if guidelines PDFs are present
- Fails gracefully with clear instructions if core files are missing

---

## 11. Phase roadmap

### Phase 1 — Proof of Value ✅

Single reactive agent + inline tools. Dashboard with basic pages. RAG on UW guidelines.

### Phase 2 — Agentic + KG ✅ (ACTIVE)

- **18 tools** across 5 groups via MCP HTTP servers (ports 8601-8604)
- **5 dashboard pages** — Customer Intelligence (landing) · Ask EOS AI · Portfolio · Portfolio Risk Map · New Submission
- **Background watcher** — event-driven PDF monitoring (30s poll)
- **4-layer memory** — session, episodic (`decisions_log.jsonl`), entity (`customer_memory.json`), semantic (RAG)
- **Reflexion** — `_reflect()` after every response: 2 governance checks (lighter, faster)
- **Batching rule** — Claude calls multiple tools in one turn; executed in parallel via `asyncio.gather`
- **Parallel tool execution** — `call_tools_parallel_mcp()` in `mcp_client.py` uses asyncio.gather
- **Planner rule** — structured multi-step queries
- **Dynamic tool discovery** — `_get_tools()` fetches schemas from MCP servers
- **Agent singleton** — `@st.cache_resource`, data loaded once per process
- **Cache pre-warm** — `_prewarm()` in `app.py` populates all @st.cache_data on server start
- **EU AI Act**: Art. 12 (decisions_log) ✅ · Art. 13 (reflexion) ✅ · Art. 14 (UW capture) ✅ · Art. 10 (bias analysis) ✅ · Art. 15 (accuracy chart) ✅
- **Dual cascade visualization** — Network Cascade + Ripple Effect (academic style, degree-based)
- **Recommendation accuracy chart** — bind rate by tier visible in Customer queue header (Art. 15)
- **Bias analysis** — score distribution by broker and SIC (Art. 10 data governance)
- **Score waterfall** — component breakdown in Customer Drill-Down (Art. 13 explainability)
- **Suggested questions** — 2 sections: MVP Coverage (4 tabs) + UW Workflow (5 tabs)
- **Briefing banner** — daily briefing shown as collapsible banner on Customer Intelligence landing

### Phase 3 — Multi-agent + Temporal KG (vision)

- **Temporal KG** — NetworkX MultiDiGraph with timestamped edges; `snapshot_at(date)` queries; portfolio evolution time-slider
- **Customer timeline** — Plotly Gantt of submission events, controls evolution over time
- **Broker trend lines** — approval rate per broker per year
- **Multi-agent** — Orchestrator + Data Agent + Risk Agent + KG Agent + Governance Agent
- **Feedback loop** — UW decisions improve scoring model
- **Art. 43 conformity assessment** — formal documentation for EU AI Act registration

---

*Zurich Insurance Hackathon MVP · June 2026*  
*All AI recommendations are ADVISORY ONLY — human underwriter decision required (EU AI Act Art. 14)*

