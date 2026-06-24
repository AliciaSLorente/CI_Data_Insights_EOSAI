# Hyper Challenge 2026 — Technical Summary

---

## Team

- **Team name:** `CI_Data_Insights_EOSAI`
- **Use case:** `CI_Data_Insights` — Leveraging Historical Data to Improve New Business Decisions (Specialties Underwriting)
- **Platform used:** `claude_api` (custom Python · Streamlit · MCP)
- **Team members:**
  - Alicia Sanchez Lorente, a.sanchezlorente@zurich.com

---

## Where to find your submission

| Artifact | Filename or URL |
|---|---|
| GitHub repo | https://github.com/AliciaSLorente/CI_Data_Insights_EOSAI |
| Demo video | `EOSAI_CI_Data_Insights.mp4` |
| Video transcript | `EOSAI_CI_Data_Insights_transcript.md` |
| Pitch deck | `EOSAI_CI_Data_Insights.pdf` |
| Technical summary | `CI_Data_Insights_EOSAI.md` |
| Process design map | `EOSAI_ProcessDesignMap.png` |

---

## Models & tools summary

| Stage | Model / Tool | Purpose |
|---|---|---|
| Agent orchestration & narrative | `eu.anthropic.claude-sonnet-4-6` | ReAct reasoning, tool selection, narrative generation, reflexion |
| RAG embeddings (build-time only) | `text-embedding-3-large` | 64-chunk index from 3 Zurich UW guideline PDFs |
| Knowledge Graph | NetworkX | Graph build, Louvain community detection, cascade simulation, peer matching |
| Tool transport | MCP (FastMCP SSE/HTTP) | 4 standalone servers on ports 8601–8604, dynamic schema discovery |
| Dashboard | Streamlit | 5-page interactive UW interface, cache pre-warm, session state |
| Data storage | SQLite · CSV · JSON | Submission cache, pre-computed KG analytics, audit logs, entity memory |
| PDF parsing | pypdf + regex | 26 structured fields from 162 submission PDFs |
| Visualisation | Plotly Express | Inline agent charts: bar · pie · line · scatter · heatmap |

---

## 1. What did you build?

**EOS AI** is an agentic AI platform for Zurich Specialties underwriters that applies **renewal-like intelligence to New Business decisions**. Zurich Specialties sees the same customer multiple times as New Business but treats each submission as net-new — losing 5+ years of historical context. A UW currently spends 55–80 minutes per repeat submission doing manual research. EOS AI delivers that analysis in under 3 minutes.

**When a UW receives a new submission, the system surfaces:**
1. Is this a repeat customer? Full submission history (2021–2026)
2. What changed since their last submission — controls, broker, revenue, premium
3. Should this be Fast-Tracked, Standard UW, or Fresh UW? (score 0–100 + tier)
4. Who are their structural peers in the Knowledge Graph, and what were their outcomes?
5. What is the cascade risk to the portfolio if a hazard event occurs?

**Key components (Phase 2 — active):**
- **18-tool ReAct agent** (Claude Sonnet 4.6) — parallel asyncio tool execution, 4-layer memory, reflexion governance
- **Knowledge Graph** — NetworkX: 10,232 nodes, 36,312 edges; Louvain community detection; KMeans k=3 risk clusters
- **4 MCP servers** (ports 8601–8604) — modular tool servers with dynamic schema discovery
- **Event-driven watcher** — background process auto-analyses new PDF submissions every 30 seconds
- **RAG** on 3 Zurich UW guideline PDFs — 64 chunks, grounding recommendations in policy
- **5 Streamlit pages** — Customer Intelligence (landing) · Ask EOS AI · Portfolio Analytics · Portfolio Risk Map · New Submission

**All outputs are advisory. Human underwriter decision required. (EU AI Act Art. 14)**

---

## 2. How did you build it?

**Agent loop (per message):**

```
Memory read (customer_memory.json + decisions_log.jsonl[-100 lines])
→ Tool discovery (_get_tools() → discover_mcp_tools() from running MCP servers)
→ ReAct loop (MAX_TURNS=10, 3-retry backoff, 4000-char result cap)
    → Parallel tool execution when >1 tool called (asyncio.gather via call_tools_parallel_mcp())
    → Sequential fallback: _run_tool() → MCP HTTP (~5ms) or stdio subprocess (~480ms)
→ Reflexion (_reflect(): 2 governance checks, max_tokens=80)
→ Log decision (decisions_log.jsonl — Art. 12 EU AI Act)
→ Entity memory upsert (customer_memory.json)
```

**Parallel execution:** when the agent batches multiple tools in one turn (e.g. `get_customer_history` + `get_risk_score` + `find_structural_peers`), `asyncio.gather` runs them concurrently within the same event loop — ~60–70% latency reduction vs sequential for complex queries.

**Risk scoring — deterministic, not ML:**
```python
score = 100 - (revenue_delta * 0.5) - (control_regression * 10)
# FAST_TRACK: ≥70  |  STANDARD_UW: 40–69  |  FRESH_UW: <40
```
The LLM orchestrates tools and writes narratives — it never computes the risk score.

**MCP architecture:** 4 standalone HTTP servers started by `start_demo.py --mcp`. Tool schemas discovered dynamically at runtime from live servers. HTTP SSE transport (~5ms warm) with stdio fallback. Data loaded once per server process — CSVs cached at server level.

**Data pipeline (offline, pre-computed):**
- Dataset 1: 46,318 Specialties submissions (Excel) → SQLite + scored CSVs (9,078 repeat customers, 34% of book)
- Dataset 2: 162 PDFs across 25 Cyber customers → 26 structured fields (revenue, 12 security controls, broker, policy dates)
- 9 pre-computed KG analytics CSVs → dashboard loads in <300ms

**Startup pre-warm:** `_prewarm()` (`@st.cache_resource` in `app.py`) pre-populates all `@st.cache_data` loaders on server start — first page load is instant.

**Technologies:** Python 3.12 · Streamlit · Claude Sonnet 4.6 (Zurich GenAI proxy) · NetworkX · FastMCP · SQLite · pypdf · Pydantic · asyncio · Plotly Express · OpenAI SDK (API-compatible)

---

## 3. How do you control and evaluate it?

**EU AI Act compliance — classified High-Risk AI (Annex III: insurance risk assessment):**

| Article | Requirement | Status | Implementation |
|---|---|---|---|
| Art. 12 | Logging & record-keeping | ✅ | `decisions_log.jsonl` — every interaction logged with timestamp, tools called, recommendation, confidence, UW decision |
| Art. 13 | Transparency | ✅ | Reflexion enforces advisory disclaimer on every response; chain-of-thought visible in dashboard expander |
| Art. 14 | Human oversight | ✅ | UW Decision Capture (Approve/Override/Decline) in Customer Drill-Down; all outputs labelled advisory |
| Art. 10 | Data governance & bias | ✅ | Bias analysis tab in Portfolio Analytics: approval rate by sector and broker |
| Art. 15 | Accuracy & robustness | ⚠️ | Bind rate by tier: FAST_TRACK 68% · STANDARD_UW 41% · FRESH_UW 12% — formal validation pending |

**Quality controls:**
- Rule-based scoring is deterministic — identical inputs always produce identical outputs; no model drift
- LLM used only for tool orchestration and narrative — the risk score is never model-generated
- Score waterfall chart in Customer Drill-Down — UW sees exactly which factors drove the score (Art. 13 explainability)
- Memory log capped at 100 episodic entries — prevents context bloat and cost escalation
- TTL badge cache (30s) for new submission notifications — no unnecessary polling

**Known risks:**

| Risk | Mitigation |
|---|---|
| LLM hallucination in narrative | Score is rule-based and primary; narrative is post-hoc, clearly labelled advisory |
| Historical bias in approval rates | Bias analysis tab; quarterly audit planned |
| Automation bias (UW over-trusts score) | Mandatory advisory labelling; UW decision capture before any log entry |
| Data privacy | Customers anonymised (Company 1, 2…); no PII in prompts; `data/raw/` and `data/parsed/` excluded from repo |

---

## 4. How do you scale it? — Industrialization Roadmap

*AI Solution Architect perspective — three horizons to production.*

---

### Horizon 1 — Production Readiness (0–3 months)

**Infrastructure hardening:**
- Containerise all 4 MCP servers with Docker; deploy on K8s with health probes, readiness checks, and horizontal pod autoscaling
- Replace SQLite with PostgreSQL (connection pooling via PgBouncer; write-ahead logging for audit durability)
- Move secrets from `.env` file to Azure Key Vault (or equivalent); rotate API keys on a schedule
- CI/CD pipeline (GitHub Actions): lint → unit tests → integration tests → staging deploy → production promote

**Authentication & multi-tenancy:**
- Integrate Azure AD SSO for UW authentication — each session tied to a user identity
- Role-based access: UW (read + recommend), Team Lead (read + override + approve), Admin (full)
- Session isolation: each UW sees their own chat history; shared KG and data

**Observability stack:**
- Structured logging (JSON) from all MCP servers and orchestrator → centralised log aggregator (Azure Monitor / Datadog)
- Token usage tracking per query — cost attribution per UW, per team
- Latency dashboards: P50/P95/P99 per tool, per agent turn
- Alert on: agent errors > 1%, reflexion failures, MCP server down, KG load > 5s

**Testing:**
- Unit tests for scoring rules (deterministic — 100% coverage required)
- Integration tests for each MCP tool with real data fixtures
- End-to-end agent smoke test: known query → expected recommendation tier

---

### Horizon 2 — Scale & Reliability (3–6 months)

**Data architecture:**
- Replace manual CSV ingestion with an automated pipeline triggered by source system events (Zurich submission platform → Kafka topic → ingestion service)
- Separate read replicas for dashboard queries vs. write path for new submissions
- Data versioning: every pipeline run tagged with a version; rollback capability if scoring rules change
- RAG index: move from local JSON to a managed vector store (Azure AI Search or Pinecone) for horizontal scale and automatic re-indexing when guidelines update

**Agent architecture:**
- Replace Streamlit frontend with React + FastAPI backend — proper WebSocket streaming, concurrent sessions, mobile-ready
- Introduce an **Agent Gateway** layer: rate limiting per user, request queuing, circuit breaker for Claude API failures
- Tool result caching at the gateway: identical tool calls within a session return cached results (reduces token cost ~30%)
- Prompt versioning: every system prompt change tracked, A/B testable, rollback on regression

**Knowledge Graph:**
- Migrate NetworkX to a persistent graph store (Neo4j or Amazon Neptune) with timestamped edges
- Implement `snapshot_at(date)` queries for historical risk trajectory — *who was this customer's risk profile 2 years ago?*
- Scheduled KG refresh (nightly) from updated submission data; incremental edge updates on new approvals

**Watcher → Event-driven ingestion:**
- Replace 30s poll with Kafka consumer subscribed to submission events from source system
- Parallel PDF processing workers (Celery or K8s Jobs) for burst handling
- Dead-letter queue for failed extractions; human review queue for low-confidence extractions

---

### Horizon 3 — Intelligent System (6–12 months)

**Multi-agent architecture:**

```
Orchestrator Agent (Claude Sonnet 4.6 — reasoning + coordination)
    ├── Data Agent         → submission history, delta computation, PDF extraction
    ├── Risk Agent         → scoring, anomaly detection, peer comparison
    ├── KG Agent           → graph queries, cascade simulation, community detection
    └── Governance Agent   → reflexion, bias check, EU AI Act audit, Art. 12 logging
```

Each agent has its own tool set, memory scope, and quality gate. The orchestrator plans, delegates, and synthesises — it never executes tool calls directly.

**Feedback loop (GDPR-safe):**
- UW decisions captured → aggregated into scoring model improvement signals (never individual UW identifiers)
- Monthly model review: compare score distributions vs. baseline; human sign-off required before any scoring rule update
- Drift detection: automatic alert when FAST_TRACK bind rate deviates >10% from historical baseline

**External signals:**
- Threat intelligence feeds (cyber attack indicators, vulnerability disclosures) → KG enrichment
- Financial news (company financials, sector events) → risk signal layer
- Human review gate before any external source is trusted: source audit, bias check, confidence threshold

**EU AI Act — full compliance path:**
- Register system in EU AI Act database as High-Risk AI (Annex III)
- Conduct Data Protection Impact Assessment (DPIA) — confirm no PII in model inputs
- Define RACI: who is accountable when AI recommendation is wrong
- Art. 43 conformity assessment: engage third-party auditor; estimate 4–8 weeks, ~€15–30K
- Post-market monitoring plan: quarterly bias audit, annual accuracy review, incident reporting SLA

---

### Architecture evolution summary

| Dimension | Prototype (now) | Production (H1–H2) | Intelligent (H3) |
|---|---|---|---|
| Frontend | Streamlit | React + FastAPI | React + personalised UW view |
| Agent | Single orchestrator | Single + Gateway | Multi-agent + orchestrator |
| Tools | 18 via MCP | 18+ containerised | Specialised per agent |
| Data store | SQLite + CSV | PostgreSQL + vector DB | PostgreSQL + graph DB + vector DB |
| KG | NetworkX in-memory | Neo4j persistent | Temporal MultiDiGraph |
| Ingestion | File watcher 30s | Kafka event-driven | Real-time + external signals |
| Auth | None | Azure AD SSO | RBAC + audit per user |
| Observability | Print logs | Structured + dashboards | Full MLOps stack |
| Governance | Art.10–14 built in | + DPIA + RACI | + Art.43 + drift monitoring |
| Monthly LLM cost | ~$30 (dev) | ~$375 (50 UW) | ~$1,500 (200 UW, multi-agent) |

**Current tested scale:** 25 customers · 162 PDFs · 46,318 submissions · 10,232 KG nodes · <300ms dashboard load · <1s PDF parse

---

## 5. Cost considerations

**Build cost (prototype):** ~$30–80 in API calls (RAG index build + iterative agent testing)

**Runtime per query:**
- ~5,000 input tokens + ~800 output tokens (Claude Sonnet 4.6 via Zurich proxy) → ~$0.015–0.03/query
- **Token-lean by design:** tool results capped at 4,000 chars · reflexion max_tokens=80 · episodic memory last 100 lines · risk scoring runs locally (zero LLM tokens)

**At scale (50 UW × 10 queries/day = 500 queries/day):**
- ~$375/month in LLM costs
- RAG: one-time ~$0.50 index build; zero cost at query time (local vector search)
- Infrastructure: Streamlit Community Cloud for pilot; production K8s ~$200–500/month

The LLM is used surgically for reasoning and narrative — not as a compute-heavy pipeline step.

---

## 6. Learnings

**What worked:**
- **MCP architecture** gives clean separation between agent logic and tool implementation — each server can be developed, tested, and deployed independently. Right pattern for enterprise AI tooling.
- **asyncio.gather for parallel tools** — ~60–70% latency reduction on multi-tool queries. Critical for complex portfolio questions requiring 3+ tools simultaneously.
- **Rule-based scoring over ML** — fully auditable, EU AI Act compliant from day 1, immediately trusted by reviewers because the formula is readable.
- **EU AI Act compliance as architecture** — reflexion, audit logs, advisory labelling baked into the agent loop from the start. Much cheaper than retrofitting post-build.
- **4-layer memory** (session + episodic + entity + semantic) — personalisation and governance logging with zero PII in prompts. Reusable pattern for other Zurich AI use cases.

**What we would do differently:**
- Add timestamped edges to the KG from day 1 — avoids a schema migration when building temporal risk trajectories in Phase 3.
- Earlier UW user-testing — some interface decisions (landing page, chat ordering, briefing placement) were optimised late based on review feedback rather than upfront research.
- Build the streaming chain from MCP servers through to the UI from the start — tools already execute in parallel but results are currently batched before streaming.

---

*Submitted by: Alicia Sanchez Lorente · a.sanchezlorente@zurich.com · June 2026*
