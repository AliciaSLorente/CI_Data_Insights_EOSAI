# EOS AI — Agentic Underwriting Intelligence
## Zurich Hyper Challenge 2026 · CI_Data_Insights

---

# Slide 1: Problem & Solution

## The Problem

- Zurich Specialties treats repeat customers as new business every year
- Underwriters spend **55–80 minutes per submission** doing manual research
- **46,318 submissions (2021–2026)** contain the answer — unused
- 9,078 repeat customers = **34% of the book** — invisible to today's workflow

## The Solution: EOS AI

- 18-tool ReAct agent powered by **Claude Sonnet 4.6**
- **Knowledge Graph** — 10,232 nodes · 36,312 edges · real-time risk clusters
- **4 MCP servers** — parallel tool execution via asyncio.gather
- **RAG** on 3 Zurich UW guideline PDFs — recommendations grounded in policy
- **Event-driven watcher** — auto-analyses new PDF submissions in 30 seconds
- **EU AI Act compliant** — Art.10 · 12 · 13 · 14 · 15 built in from day one

---

# Slide 2: Results & Key Insights

## 55–80 minutes → under 3 minutes per repeat submission

## Validated on 9,078 repeat customers

| Tier | Bind Rate |
|---|---|
| FAST_TRACK | 48.1% |
| STANDARD_UW | 4.4% |
| FRESH_UW | 0.0% |

## Key Insights

- Knowledge Graph reveals hidden cascade risks — broker failure → portfolio contagion
- Digital twin matching: new submissions instantly matched to structural peers
- Full chain of thought visible to UW — no black box
- Every interaction logged in audit trail (EU AI Act Art. 12)
- Bias analysis across sectors and brokers built into dashboard (Art. 10)

---

# Slide 3: Industrialization Roadmap

## Horizon 1 — Production Ready (0–3 months)

- Docker/K8s for all 4 MCP servers · PostgreSQL · Azure AD SSO
- CI/CD pipeline: lint → tests → staging → production
- Observability: structured logging · token cost tracking · latency dashboards
- Azure Key Vault for secrets · role-based access (UW / Team Lead / Admin)

## Horizon 2 — Scale & Reliability (3–6 months)

- React + FastAPI frontend · WebSocket streaming · Agent Gateway with rate limiting
- Kafka event-driven ingestion (replace 30s file watcher)
- Neo4j persistent KG with timestamped edges · `snapshot_at(date)` queries
- Azure AI Search managed vector store · automated RAG re-indexing on guideline updates
- Cost at scale: **~$375/month** LLM · ~$200–500/month infrastructure

## Horizon 3 — Intelligent System (6–12 months)

- **Multi-agent:** Orchestrator + Data Agent + Risk Agent + KG Agent + Governance Agent
- Feedback loop from aggregated UW decisions (GDPR Art. 22 compliant)
- External signals: threat intelligence feeds · financial news → KG enrichment
- EU AI Act Art. 43 conformity assessment (third-party audit · ~€15–30K · 4–8 weeks)
- Monthly drift detection · DPIA · RACI documented

> *"We built EU AI Act governance from day one. No surprises for legal."*

---

# One-Pager

**Team:** EOSAI
**Use Case:** CI_Data_Insights — Leveraging Historical Data to Improve New Business Decisions
**Team Member:** Alicia Sanchez Lorente · a.sanchezlorente@zurich.com

**How our approach solves the problem:**
EOS AI applies renewal-like intelligence to New Business decisions. When a UW receives a repeat submission, the agent surfaces full historical context, delta analysis, structural peers from a Knowledge Graph, and a risk score grounded in Zurich UW guidelines — all in under 3 minutes.

**Results of the prototype:**
9,078 repeat customers identified (34% of book). Bind rate validation: FAST_TRACK 48.1% · STANDARD_UW 4.4% · FRESH_UW 0.0%. 18-tool ReAct agent operational with parallel execution. Knowledge Graph with 10,232 nodes and 36,312 edges. EU AI Act Art.10/12/13/14/15 compliant.

**Next steps for scaling:**
Phase 3 multi-agent system, feedback loop from UW decisions, temporal Knowledge Graph, EU AI Act Art. 43 conformity assessment, production infrastructure (PostgreSQL, React, K8s).

**Main learning:**
Building EU AI Act compliance as an architectural concern — not a post-hoc audit — is significantly cheaper and builds UW trust from day one. MCP + asyncio.gather is the right pattern for enterprise AI tooling.
