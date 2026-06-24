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

## 4. How do you scale it?

**Infrastructure path to production:**
- SQLite → PostgreSQL (multi-user write safety, connection pooling)
- In-process NetworkX → temporal graph DB (DuckDB/PyArrow) with timestamped edges and `snapshot_at(date)` queries
- Streamlit → React frontend for concurrent sessions and proper authentication
- MCP servers → containerised microservices (Docker/K8s) with health checks and load balancing
- File-based watcher → event queue (RabbitMQ/Kafka) for high-volume PDF ingestion
- `@st.cache_resource` → Redis shared cache for multi-node deployment

**Phase 3 vision (governance roadmap defined in `docs/AI_GOVERNANCE_BY_PHASE.md`):**
- Multi-agent system: Orchestrator + Data Agent + Risk Agent + KG Agent + Governance Agent
- Feedback loop from aggregated UW decisions (no individual UW identifiers — GDPR Art. 22 compliant)
- External signal ingestion: threat intelligence, financial news
- Formal EU AI Act Art. 43 conformity assessment before production

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
