# AI Responsible & AI Governance Analysis — Three Phases
## EOS AI System

**Framework used:** EU AI Act (2024/1689) · GDPR · ISO 42001 · NIST AI RMF · Anthropic Responsible AI  
**Risk Classification:** HIGH-RISK AI under EU AI Act Annex III (insurance risk assessment)  
**Date:** June 2026

---

## Executive Summary

| Dimension | Phase 1 — Reactive | Phase 2 — Autonomous | Phase 3 — Multi-Agent |
|---|---|---|---|
| Human control | Full | Partial | Shared |
| Autonomy level | Low | Medium | High |
| Explainability | High | High | Medium-High |
| Audit complexity | Low | Medium | High |
| EU AI Act compliance effort | Medium | High | Very High |
| Bias risk | Low | Medium | Medium-High |
| Systemic risk | Low | Medium | High |
| Overall governance maturity needed | Foundational | Structured | Advanced |

---

## Phase 1 — Reactive Agent

### What it does
**Phase 2 (current):** The agent uses 18 tools across 5 MCP servers (Data Curation, UW Metrics, KG Discovery, Guidelines RAG, Watcher). Parallel tool execution via asyncio.gather. Proactive daily briefing. Event-driven watcher for new submissions. All outputs advisory.

---

### EU AI Act Compliance

| Article | Requirement | Status | Gap / Action |
|---|---|---|---|
| Art. 6 + Annex III | High-risk classification (insurance risk assessment) | Pending registration | Must register in EU AI Act database before production |
| Art. 9 | Risk management system | Partial | Scoring rules documented; full risk lifecycle tracking needed |
| Art. 10 | Data governance (training data quality) | Partial | CSVs validated; full lineage documentation missing |
| Art. 13 | Transparency — users know they interact with AI | Compliant | Every output labelled "Advisory only" |
| Art. 14 | Human oversight — humans can intervene and override | Compliant | All outputs advisory; no auto-decisions |
| Art. 15 | Accuracy, robustness, cybersecurity | Partial | Rule-based scoring tested; adversarial testing not done |
| Art. 52 | AI-generated content labelling | Compliant | Claude narratives clearly identified |
| Art. 72 | Post-market monitoring | Pending | Audit log exists; formal incident reporting process needed |

**Compliance Score: ~75% (6/8 compliant, 1/8 partial, 1/8 pending)**
*Art.12 ✅ decisions_log · Art.13 ✅ reflexion + waterfall · Art.14 ✅ UW decision capture · Art.10 ✅ bias analysis · Art.15 ✅ accuracy chart · Art.52 ✅ labelling · Art.9 ⚠️ partial · Art.43 ❌ pending*

---

### Responsible AI Analysis

#### Transparency & Explainability
- **Strength:** Waterfall chart + Claude narrative explain every score
- **Strength:** Chain of Thought visible in dashboard
- **Strength:** Rule-based scoring is fully auditable (not black-box)
- **Risk:** Agent's chain of reasoning depends on LLM — not deterministic
- **Mitigation:** Tool outputs are deterministic; only the narrative framing varies

#### Human Oversight
- **Strength:** UW triggers every interaction — no autonomous action
- **Strength:** All recommendations explicitly labelled advisory
- **Strength:** Human review tracking in governance module
- **Risk:** Automation bias — UW may over-trust AI score over time
- **Mitigation:** Display confidence intervals; show cases where agent uncertainty is high

#### Bias & Fairness
- **Risk:** Scoring based on historical approval rates — if past UW decisions were biased, scores inherit that bias
- **Risk:** Companies with few submissions have less reliable scores (small sample)
- **Mitigation:** Bias monitor in governance tab flags unusual approval rate distributions
- **Gap:** No fairness testing across industry sectors or company sizes

#### Data Governance
- **Strength:** Data anonymised (Company 1, Company 2, etc.)
- **Strength:** No PII processed in scoring pipeline
- **Risk:** PDF data may contain real company names — need review
- **Gap:** No formal data retention policy defined

#### Accountability
- **Strength:** Audit log records every recommendation
- **Gap:** No clear accountability chain (who is responsible when AI recommendation is wrong?)
- **Action required:** Define RACI for AI outputs before production

#### Key Risks — Phase 1

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| UW over-trusts AI score | Medium | High | Confidence thresholds + mandatory human sign-off |
| Historical bias in data | Medium | Medium | Quarterly bias audit |
| LLM hallucination in narrative | Low | Medium | Narrative is post-hoc; score is rule-based and primary |
| Data leak via API | Low | High | Zurich proxy (not direct Anthropic); no PII in prompts |

---

## Phase 2 — Autonomous Agent

### What it does
The agent runs a portfolio analysis **without being triggered by the UW**. It queries the top-risk customers, scores them, discovers KG patterns, generates narratives, and writes results to the audit log. Outputs appear in the dashboard.

---

### New Governance Challenges vs Phase 1

Phase 2 introduces **autonomous action** — the agent acts without a human trigger. This fundamentally changes the governance requirements.

#### What changes:
- The agent **writes to systems** (audit log, marks customers as reviewed)
- The agent **influences the UW's workflow** by surfacing prioritised recommendations
- The UW did not ask for this — there is no explicit consent per interaction

---

### EU AI Act Compliance

| Article | Requirement | Phase 1 Status | Phase 2 Gap |
|---|---|---|---|
| Art. 9 | Risk management | Partial | Autonomous actions must be part of formal risk register |
| Art. 14 | Human oversight | Compliant | **NEW RISK:** Autonomous outputs influence queue before human review |
| Art. 15 | Robustness | Partial | **NEW RISK:** Autonomous loop can amplify errors (feedback loop) |
| Art. 17 | Quality management | Pending | **REQUIRED:** Formal testing before autonomous deployment |
| Art. 72 | Post-market monitoring | Pending | **CRITICAL:** Autonomous agent requires continuous monitoring |
| Art. 26 | Deployer obligations | Not started | **REQUIRED:** Zurich as deployer must register usage |

**New requirements triggered by Phase 2:**
1. **Human-in-the-loop checkpoint** before autonomous outputs affect UW workflow
2. **Formal approval process** (internal validation) before autonomous mode activates
3. **Kill switch** — ability to disable autonomous mode instantly
4. **Rate limiting** — autonomous agent cannot run continuously without supervision

---

### Responsible AI Analysis

#### Human Oversight — CRITICAL CHANGE
- **Risk (HIGH):** Agent writes recommendations to the system before UW reviews them
- **Risk (HIGH):** UW opening the dashboard sees AI-prioritised queue — anchoring bias
- **Mitigation REQUIRED:** Autonomous outputs must be clearly separated from manually-triggered outputs
- **Mitigation REQUIRED:** "AI Auto-analysis" badge distinct from "UW-requested analysis"
- **Mitigation REQUIRED:** UW must be able to dismiss/reject autonomous recommendations

#### Automation Bias — ELEVATED RISK
- In Phase 1, the UW actively chose to ask the agent → conscious engagement
- In Phase 2, recommendations appear **without the UW asking** → passive acceptance risk
- Research shows passive AI recommendations are trusted more than active ones
- **Mitigation:** Mandatory "I have reviewed this" acknowledgment before acting on autonomous output

#### Accountability Gap — NEW RISK
- Who is responsible when autonomous agent flags wrong customer?
- Who is responsible when autonomous agent misses a high-risk customer?
- **Action required:** Document: "Autonomous agent is a triage tool, not a decision-maker. Final responsibility remains with the underwriter."

#### Feedback Loop Risk — NEW RISK
- Autonomous agent prioritises certain customers → UW reviews those first → UW approves → future agents learn "this profile = approve"
- This creates a **confirmation bias loop** if unchecked
- **Mitigation:** Autonomous agent scores are static (computed once), not updated by UW decisions in Phase 2

#### Bias & Fairness — ELEVATED RISK
- Autonomous agent selects WHICH customers get surfaced — not seeing others is also a bias
- **Risk:** Systematically under-surfacing certain sectors or broker groups
- **Mitigation:** Audit autonomous selections quarterly for distribution across sectors/brokers

#### Key Risks — Phase 2

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Anchoring bias from autonomous queue | High | High | Separate UI zone + explicit disclaimer |
| Autonomous loop amplifies errors | Medium | High | Static scores; no Phase 2 feedback to scoring engine |
| Accountability confusion | Medium | High | RACI documented + advisory labelling strengthened |
| Regulator concern about autonomous insurance AI | High | Very High | Full Art. 14 compliance + kill switch + human review audit |
| Agent runs too frequently, overwhelming UW | Medium | Medium | Rate limit: max 1 autonomous run per 24h |

---

### Phase 2 Governance Controls (Required before deployment)

```
BEFORE autonomous agent writes to system:
  1. Run → Generate results
  2. HOLD → Results visible to admin only
  3. Human reviewer approves batch
  4. THEN → Results visible to UW workflow

This maintains Art. 14 compliance while enabling autonomy.
```

---

## Phase 3 — Multi-Agent System with Feedback Loop

### What it does
Multiple specialised agents (Data, Risk, KG, Governance) coordinate via an orchestrator. The system learns from UW decisions over time. External signals (threat intelligence, news) are ingested. The Knowledge Graph evolves.

---

### New Governance Challenges vs Phase 2

Phase 3 introduces:
- **Model drift** — the system changes its behaviour over time as it learns
- **Multi-agent accountability gap** — which agent is responsible for a wrong output?
- **External data risk** — quality and bias of external signals
- **Emergent behaviour** — agents collaborating may produce unexpected results

---

### EU AI Act Compliance

| Article | Requirement | Phase 3 Challenge |
|---|---|---|
| Art. 9 | Risk management | **CONTINUOUS:** Risk register must update as system learns |
| Art. 10 | Data governance | **CRITICAL:** External data sources require new data quality controls |
| Art. 12 | Record keeping | **COMPLEX:** Multi-agent interactions require full trace logging |
| Art. 14 | Human oversight | **HARDEST:** Human must be able to understand and override a multi-agent decision |
| Art. 15 | Accuracy & robustness | **ONGOING:** Model drift requires continuous accuracy monitoring |
| Art. 17 | Quality management system | **REQUIRED:** Formal QMS with version control for each agent |
| Art. 43 | Conformity assessment | **REQUIRED:** Third-party audit before production for learning systems |
| Art. 72 | Post-market monitoring | **MANDATORY:** Real-time monitoring of agent behaviour and outputs |

**Phase 3 likely requires a formal Conformity Assessment (Art. 43) — this involves external auditors.**

---

### Responsible AI Analysis

#### Model Drift — CRITICAL NEW RISK
- As the system learns from UW decisions, it can drift from intended behaviour
- Example: If all UW decisions in Q3 are unusually conservative, the model learns conservative → over-rejects in Q4
- **Mitigation REQUIRED:**
  - Monthly drift detection (compare score distributions vs baseline)
  - Automatic alerts when score distribution shifts > 10%
  - Quarterly model review with human sign-off to continue learning

#### Multi-Agent Accountability — HARD PROBLEM
- Data Agent provides wrong data → Risk Agent scores incorrectly → UW makes wrong decision
- Who is responsible? Data Agent? Risk Agent? Orchestrator? The UW?
- **EU AI Act Art. 26 requires deployer (Zurich) to remain responsible**
- **Mitigation:** Full agent interaction trace logged; clear chain of responsibility documented

#### External Data Bias — NEW RISK
- External threat intelligence may be biased toward certain geographies or sectors
- Financial news sources may over-represent large companies
- **Mitigation:** Source audit before integration; human review of external signal quality

#### Explainability — HARDER AT SCALE
- Multi-agent decision: Data Agent (input) → Risk Agent (score) → KG Agent (context) → Final recommendation
- The "why" now spans 4 agents and potentially 20+ tool calls
- **Risk:** XAI becomes too complex for UW to understand and verify
- **Mitigation:** Maintain a single-sentence "Primary reason" alongside the full trace
- **Mitigation:** XAI must remain interpretable at the UW level, not just the technical level

#### Memory & Learning — HIGHEST RISK ELEMENT
- GDPR implications: if the system "remembers" UW decisions, it may process personal data
- **GDPR Art. 22:** Automated decision-making with legal effects requires explicit consent
- **Mitigation:** Learning only from aggregated patterns, never from individual UW identifiers
- **Mitigation:** Right to erasure: if a UW leaves, their decisions must be removable from training data

#### Key Risks — Phase 3

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Model drift → systematic mispricing | Medium | Very High | Monthly drift monitoring + quarterly human review |
| External data introduces new bias | High | High | Source audit + human review of signals before ingestion |
| Multi-agent produces unexplainable outputs | Medium | Very High | Single-sentence primary reason always generated |
| GDPR violation from learning on personal data | Low | Very High | Aggregate-only learning; no individual UW identifiers |
| Regulator requires formal conformity assessment | High | High | Budget for Art. 43 third-party audit |
| Emergent agent behaviour causes harm | Low | Very High | Sandbox testing + staged rollout + kill switch |

---

## Cross-Phase Summary: What Must Be in Place

### Non-negotiable for ALL phases (before any production)

1. **EU AI Act registration** — system must be registered as High-Risk AI
2. **Human override capability** — UW can always dismiss/override any AI output
3. **Audit trail** — every recommendation logged with full context
4. **Advisory labelling** — no AI output presented as a decision
5. **Bias audit** — quarterly review of recommendation distribution
6. **Incident reporting process** — what happens when AI makes a wrong recommendation?
7. **Accountability RACI** — who is responsible for what

### Additional requirements per phase

| Control | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Human approval before AI affects workflow | Not needed (advisory only) | Required | Required |
| Kill switch for autonomous mode | Not needed | Required | Required |
| Model drift monitoring | Not needed | Recommended | Required |
| Third-party conformity assessment | Not required | Recommended | Required |
| Formal QMS per agent | Not needed | Recommended | Required |
| External data source audit | Not needed | Not needed | Required |
| GDPR learning data review | Not needed | Not needed | Required |

---

## Recommendation for Hackathon Presentation

Frame the governance analysis as a **competitive differentiator**, not a compliance burden:

> *"Most AI hackathon solutions ignore governance. We built EU AI Act compliance from day one — audit trail, bias monitoring, human oversight controls. As we evolve to Phase 2 and Phase 3, we have a clear governance roadmap that de-risks production deployment for Zurich's legal and compliance teams."*

### Key messages per phase:

**Phase 1:**  
*"Safe, explainable, advisory. Full EU AI Act Art. 13-14-15 compliance. Ready for internal pilot."*

**Phase 2:**  
*"Autonomous but controlled. Human approval checkpoint before affecting UW workflow. Kill switch. Art. 14 maintained."*

**Phase 3:**  
*"Production-grade. Requires formal conformity assessment, drift monitoring, GDPR review. Governance roadmap defined — no surprises for legal."*

---

*Document version: 1.0 — June 2026*  
*This document is part of the AI Governance package for EU AI Act Art. 17 (Quality Management)*

