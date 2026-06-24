# EOS AI — Video Transcript
## Hyper Challenge 2026 · CI_Data_Insights · Team EOSAI

---

**[0:00 — Problem]**

Zurich Specialties receives repeat cyber insurance submissions from the same customers every year — but treats each one as new business. That means a Zurich underwriter spends 55 to 80 minutes per repeat submission manually searching for historical context that already exists in our own data. We have 46,000 submissions going back to 2021. We just weren't using them.

EOS AI fixes that.

---

**[0:25 — Solution overview]**

EOS AI is an agentic AI platform that applies renewal-like intelligence to new business decisions. It gives Zurich underwriters a full historical picture of any repeat customer in under 3 minutes — with an explainable risk score, a delta analysis, peer comparisons, and recommendations grounded in Zurich's own underwriting guidelines.

The system is built on Claude Sonnet 4.6 with 18 tools, a real-time Knowledge Graph of 10,000 nodes and 36,000 edges, RAG on 3 Zurich UW guideline PDFs, and an event-driven watcher that auto-analyses new PDF submissions as they arrive.

---

**[0:55 — Dashboard walkthrough]**

Let me show you the dashboard.

The landing page is Customer Intelligence. The first thing the UW sees is the daily briefing — portfolio health, critical risk accounts, pending submissions — generated automatically each morning.

In the Prioritization Queue, the UW sees all 9,000+ customers ranked by risk tier. The bind rate proof is right there at the top: Fast-Track customers bind at 68%, Fresh UW at 12%. That's the Art. 15 EU AI Act validation built directly into the workflow.

Clicking into a customer shows the full Drill-Down: risk score with waterfall breakdown, delta since last submission, controls evolution, structural peers from the Knowledge Graph. The UW captures their decision — Approve, Override, or Decline — which feeds directly into the audit log.

The Portfolio Risk Map shows the full customer network. You can simulate a cascade: what happens to our portfolio if MARSH fails today, or if a ransomware attack hits our highest-risk cluster.

And the New Submission page — drop a PDF into the watch folder and within 30 seconds EOS AI has analysed it, matched it to a digital twin, and surfaced a recommendation ready for UW review.

---

**[1:55 — Agentic AI architecture]**

The agent uses a ReAct loop with parallel tool execution via asyncio.gather. When the UW asks a complex question, the agent batches multiple tool calls — history, scoring, peer matching — and runs them concurrently. That's how we achieve sub-3-minute analysis.

We use Model Context Protocol — 4 standalone MCP servers — which means each tool group is independently deployable. That's the right architecture for scaling this to production.

Every agent response goes through a reflexion layer that audits for advisory disclaimers and guideline citations before the UW sees it. The audit trail is in decisions_log.jsonl — full EU AI Act Art. 12 compliance built into the agent loop, not added afterwards.

---

**[2:35 — Why this matters and next steps]**

EOS AI turns 5 years of Zurich's own data into a competitive advantage. It doesn't replace the underwriter — it gives them the context to make better decisions, faster, with full explainability and governance.

The Phase 3 roadmap is already defined: multi-agent system, feedback loop learning from UW decisions, and a temporal Knowledge Graph for risk trajectory analysis.

We built EU AI Act compliance from day one. We're ready for an internal pilot today, and the governance roadmap de-risks the path to production for Zurich's legal and compliance teams.

Thank you.

---

*Duration: ~2 min 50 sec · Team EOSAI · Zurich Hyper Challenge 2026*
