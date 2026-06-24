# Architecture — EOS AI System

> Updated June 2026 — Phase 2 active. See docs/USER_MANUAL.md for full documentation.

## Current state

```
app.py (~120 lines — routing + pre-warm + badge + toast)
    ├── _prewarm()              @st.cache_resource — populates @st.cache_data on server start
    ├── get_badge_count()       TTL-cached badge (30s) via watcher.py
    ├── get_latest_pending_alert() → st.toast() on new submission
    │
    ├── src/pages/customer.py       Customer Intelligence: LANDING PAGE
    │     Briefing banner + bind rate proof + Queue/Drill-Down/Side-by-Side
    ├── src/pages/agent.py          Ask EOS AI: 18-tool chat
    │     MVP_SUGGESTED (4 tabs) + SUGGESTED (5 tabs) + inline charts (W5)
    ├── src/pages/portfolio.py      Portfolio Analytics: bias analysis + accuracy
    ├── src/pages/graph.py          Portfolio Risk Map: cascade + clusters
    └── src/pages/new_submission.py New Submission: auto-scan + digital twin

src/agent/orchestrator.py           18 tools, parallel asyncio tools, reflexion, memory
src/agent/mcp_client.py             HTTP routing + call_tools_parallel_mcp() (asyncio.gather)
src/mcp_servers/                    4 HTTP servers (ports 8601-8604)
src/rag/guidelines_rag.py           Zurich UW guideline retrieval
src/startup/pipeline.py             Data validation + auto-regeneration
start_demo.py                       Single entry point, starts MCP + watcher + dashboard
```

## Separation of responsibilities

| Layer | Files | Responsibility |
|---|---|---|
| **Routing** | `app.py` | Which page, sidebar, session init |
| **UI / Rendering** | `src/pages/*.py` | Page layout, Streamlit widgets |
| **Agent** | `src/agent/orchestrator.py` | Tool selection, reflexion, memory injection |
| **Reflexion** | `_reflect()` in orchestrator | Disclaimer + guidelines compliance after every response |
| **Memory** | `agent.py` singleton + memory layers | Session, episodic, entity, semantic storage |
| **MCP Transport** | `src/agent/mcp_client.py` | HTTP vs inline routing |
| **Tools (servers)** | `src/mcp_servers/*.py` | Tool implementation across 5 groups |
| **RAG** | `src/rag/guidelines_rag.py` | UW guideline retrieval |
| **Watcher** | `src/mcp_servers/watcher_server.py` + background process | Event-driven PDF scanning + auto-analysis |
| **Data models** | `src/models/*.py` | NetworkX, KMeans, cascade, digital twin |
| **Data access** | `src/data/*.py` | CSV loading, caching |
| **Startup** | `src/startup/pipeline.py` | File validation, process management |
| **Launch** | `start_demo.py` | MCP servers + background watcher |

## Memory system

Four-layer architecture injected into every agent call:

| Layer | Storage | Content | Inject point |
|---|---|---|---|
| **Session** | `st.session_state['chat_history']` | Current conversation turns | Every LLM call |
| **Episodic** | `decisions_log.jsonl` | UW decisions, recommendations, outcomes (Art. 12 EU AI Act) | Reflexion layer |
| **Entity** | `customer_memory.json` | Per-customer facts, trends, risk flags | Before KG discovery tools |
| **Semantic** | RAG index + embeddings | Zurich UW guidelines, policy context | Query rewriting |

## Phase roadmap

| | Phase 1 | Phase 2 (active) | Phase 3 (vision) |
|---|---|---|---|
| Agent | Reactive | Proactive briefing + reflexion + parallel tools | Multi-agent |
| Tools | 6 inline | 18 via MCP + asyncio.gather parallelism | Specialised agents |
| Memory | None | 4 layers + entity memory upsert | Feedback loop |
| UX | AI Agent landing | Customer Intelligence landing + briefing banner | Personalised per UW |
| Performance | Cold cache | Pre-warm on start + TTL badge cache | Redis shared cache |
| KG | Pandas | NetworkX runtime + cascade custom scenarios | Temporal MultiDiGraph |
| RAG | No | UW guidelines (64 chunks) | Full corpus |
| Governance | Separate tab | Art.10/12/13/14/15 embedded · bias analysis | Art. 43 conformity |

See docs/USER_MANUAL.md for complete documentation.

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI Layer                        │
│    5 pages: Agent · Customer · Portfolio · Risk Map · Upload │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴──────────────┐
        │                           │
┌───────▼──────────────┐    ┌──────▼──────────────┐
│  Memory System       │    │  Recommendation     │
│  (4 layers)          │    │  Engine + Reflexion │
└───────┬──────────────┘    └──────┬──────────────┘
        │                          │
        └────────────┬─────────────┘
                     │
        ┌────────────▼────────────────────┐
        │   Knowledge Graph (NetworkX)     │
        │  - Risk clusters                │
        │  - Control impact               │
        │  - Broker patterns              │
        │  - Cascade simulation           │
        │  - Temporal snapshots (future)  │
        └────────────┬────────────────────┘
                     │
        ┌────────────▼────────────────────┐
        │   Business Logic Layer           │
        │  - Scoring rules                │
        │  - Delta computation            │
        │  - Feature engineering          │
        │  - RAG grounding                │
        └────────────┬────────────────────┘
                     │
        ┌────────────▼────────────────────┐
        │   Data Processing Layer          │
        │  - PDF parsing (pypdf + regex)  │
        │  - Excel ingestion              │
        │  - Field normalization          │
        │  - Control detection            │
        └────────────┬────────────────────┘
                     │
        ┌────────────▼────────────────────┐
        │   Data Layer                     │
        │  - SQLite cache                 │
        │  - Parsed CSVs                  │
        │  - Submission archives          │
        │  - Embeddings index (RAG)       │
        └─────────────────────────────────┘
```

## Components

### 1. Data Layer (`src/data/`)
- `loader.py` — Ingest Excel (Dataset 1) into SQLite cache
- `pdf_parser.py` — Parse PDFs (Dataset 2), extract structured fields + security controls
- `normalizer.py` — Standardize field values (revenue ranges, control names, etc.)

### 2. Business Logic (`src/business/`)
- `models.py` — Pydantic models: `Submission`, `Customer`, `Delta`, `RiskScore`
- `scoring.py` — Explicit scoring rules: `score = 100 - (revenue_delta * 0.5) - (control_regression * 10)`
- `rules.py` — UW decision logic: `if score < 50 → recommend_fresh_underwriting()`
- `delta_calc.py` — Compare submissions: which fields changed, by how much

### 3. Knowledge Graph (`src/models/`)
- `graph_builder.py` — Build NetworkX graph from parsed data
  - Nodes: Customer, Submission, Control, Broker, RiskCluster
  - Edges: relationships with metadata (confidence, impact weight)
  - Future: timestamped edges for temporal snapshots
- `pattern_discovery.py` — Query graph:
  - `find_similar_customers()` — peer-group analysis
  - `detect_risk_clusters()` — community detection
  - `compute_control_impact()` — which controls drive approval
  - `flag_anomalies()` — submissions breaking cluster patterns
  - `simulate_cascade()` — hazard propagation through portfolio

### 4. Agent (`src/agent/orchestrator.py`)
- **18 tools** across 5 groups:
  - Data Curation (search, history)
  - UW Metrics (scoring, deltas)
  - KG Discovery (peers, clusters, cascade, XAI)
  - Guidelines RAG (policy retrieval)
  - Watcher (new submission analysis + approval)
- **Memory injection**: session → episodic → entity → semantic
- **Reflexion**: `_reflect()` runs post-response, checks:
  - Disclaimer present (Art. 14)
  - Guidelines cited (Art. 13)
  - No over-confident claims
- **Tool discovery**: `_get_tools()` fetches schemas from MCP servers in HTTP mode

### 5. Memory System
- **Agent singleton** (`@st.cache_resource` in `agent.py`) — data loaded once per process
- **Session layer** (`st.session_state['chat_history']`) — current conversation
- **Episodic layer** (`decisions_log.jsonl`) — Art. 12 governance log (UW decision + agent recommendation + confidence)
- **Entity layer** (`customer_memory.json`) — per-customer facts, trends, risk flags
- **Semantic layer** (RAG embeddings) — policy context, guideline passage retrieval

### 6. Background Watcher Process
- Started by `start_demo.py --mcp` as separate process
- Polls `UW_WATCH_FOLDER` every 30 seconds for new PDFs
- On detection: auto-runs full agent analysis
- Stores results in `pending_analysis.json` with: extraction + recommendation + risk analysis
- Dashboard notifies UW; approval triggers pipeline re-run
- Implements Art. 14 (notification requirement) + Art. 12 (logging)

### 7. RAG (`src/rag/guidelines_rag.py`)
- Source: 3 Zurich UW guideline PDFs
- Index: 64 chunks, embeddings via `text-embedding-3-large`
- Query integration: agent injects question → retrieves + cites source passages
- Governance: Art. 13 compliance (source citations)

### 8. UI (`app.py` + `src/pages/`)
- **AI Agent** — Briefing + chat + new submission notifications
- **Customer Intelligence** — Prioritization Queue + Drill-Down + Side-by-Side views
- **Portfolio** — Overview + recommendation accuracy chart (Art. 15 bind rate by tier)
- **Portfolio Risk Map** — Customer Network + Cascade Simulation (2 styles) + Risk Clusters
- **New Submission** — Upload + digital twin + gap analysis + recommendation

## Data Flow

```
Dataset 1 (Excel)  ─────┐
Dataset 2 (PDFs)   ─────┼──> Data Layer ──> SQLite + CSVs
                         │
                    Normalizer

SQLite + CSVs ──> Feature Engineering ──> Parsed Records

Parsed Records ──> Business Rules ──> Risk Scores + Deltas
              ──> KG Builder ──> NetworkX Graph
              ──> Recommendation Engine + Reflexion ──> Per-submission recommendation
              ──> Memory Layers (episode + entity) ──> Logged & injected

Recommendations + KG + Memory ──> Streamlit Dashboard + Agent Chat
              ↓
         New PDFs detected in folder ──> Background watcher ──> Auto-analysis ──> pending_analysis.json
                                                                   ↓
                                          User approval ──> Pipeline re-run ──> Updated KG + cache
```

## Key Design Decisions

1. **Rule-driven over ML**: Explainability first. ML (anomaly detection) is optional enhancement.
2. **NetworkX over Neo4j**: Local, lightweight, sufficient for current scale. Future: temporal snapshots.
3. **4-layer memory**: Session (UX) + episodic (governance) + entity (personalization) + semantic (grounding).
4. **Reflexion post-response**: Every agent output audited for compliance before user sees it.
5. **Background watcher**: Event-driven submission monitoring without blocking chat.
6. **Pydantic models**: Type-safe, self-documenting, easy to validate data.
7. **SQLite cache**: Fast repeated queries, no server overhead.
8. **Streamlit for UI**: Minimal code, interactive, shareable notebooks.

## Extensibility

- **New query type**: Add function to `orchestrator.py` tools + optional new page in Streamlit.
- **New scoring rule**: Update `scoring.py`; no code changes needed elsewhere.
- **New memory layer**: Add storage (vector DB, file, etc.) + inject in `_build_context()`.
- **Production migration**: Replace SQLite with Postgres, NetworkX with temporal graph DB (DuckDB/PyArrow), Streamlit with React.
- **Temporal KG** (Phase 3): Add timestamped edges to NetworkX; implement `snapshot_at(date)` queries for historical risk analysis.

## Scalability Notes

- Current scope: 25 customers, ~150 submissions, 10K+ KG nodes.
- Tested scale: NetworkX handles 50K nodes comfortably; parsing stays <1 second per PDF.
- Memory footprint: ~300MB for full dataset + KG + RAG index.
- Bottleneck: PDF parsing. Mitigation: batch processing or async parsing if needed.
- Watcher: 30s poll interval sufficient for <100 new PDFs/day; scales to async event queue in Phase 3.

---

Generated 18 June 2026 for Zurich hackathon MVP.
