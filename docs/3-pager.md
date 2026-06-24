Specialties — Leveraging Historical Data to Improve New Business (NB) Decisions
================================================================================

Executive summary
-----------------
Zurich's ask: recognize repeat submissions in New Business and apply renewal-like intelligence so underwriters (UW) can make better, faster decisions. Using two provided datasets — a universe of Specialties submissions (2021–2026) and 4–5 years of submission PDFs for ~25 repeat Cyber customers — we can build a low-resource, high-impact prototype that: (1) detects repeat customers, (2) extracts and normalizes submission attributes from PDFs, (3) computes "delta" reports vs first-seen baseline, and (4) surfaces actionable signals (missing datapoints, deterioration/improvement of controls, broker/UW patterns) for underwriters.

Key possibilities (low-to-medium resource)
-----------------------------------------
- Deterministic repeat-detection and analytics across Dataset 1 (Excel): frequency, cadence, LOB hotspots, broker patterns.
- Rule-based PDF parsing (pypdf + regex/NLP) to extract structured fields (revenue, employees, controls, policies, financials, security controls).
- Delta computation: compare current vs baseline submission per insured, flag fields added/removed/changed; compute numerical deltas (rev, employees).
- Lightweight scoring: heuristic or small scikit-learn model to estimate whether a submission is "renewal-like" (low delta) vs "material change" (higher risk), enabling prioritized human review.
- Explainability: present per-field reasons and simple feature importances (SHAP optional) for trust and audit.
- Demo: interactive Jupyter notebook and exported CSVs + a short slide deck; optional Streamlit dashboard if extra time.

Recommended initial use cases (start small, show value fast)
-------------------------------------------------------------
1. Repeat-customer detection & analytics (MVP-1)
   - Ingest Dataset 1, identify customers seen >1 time, compute repeat rates by LOB and broker, and cadence histograms.
   - Deliver: notebook + charts + CSV of repeat customers.
   - Impact: quick business metric demonstrating prevalence and where to focus.

2. Submission delta extraction for 5 pilot Cyber customers (MVP-2)
   - From Dataset 2 PDFs, parse 4–5 historical apps per insured, extract core fields, compute deltas vs first submission, and generate human-readable delta reports.
   - Deliver: parsed CSVs + per-account PDF/HTML delta report examples for underwriters.
   - Impact: concrete examples UWs can validate; shows how renewal intelligence can be applied.

3. Prioritization & simple scoring (MVP-3)
   - Build small model or heuristics to score submissions for "reuse of prior knowledge" vs "requires fresh underwriting".
   - Deliver: scoring function, threshold recommendations, sample ranked list of repeat submissions.
   - Impact: reduces UW workload by prioritizing low-risk repeat submissions for faster processing.

How the AI solution might look (architecture & components)
---------------------------------------------------------
- Input
  - `Dataset 1` (Excel): batch ingestion to identify repeats and create master index.
  - `Dataset 2` (PDFs): per-account PDF package folders.

- Data engineering
  - Lightweight ETL scripts (`src/ingest_excel.py`, `src/parse_pdfs.py`) using `pandas`, `pypdf`, `regex`, and small NLP (spaCy optional) to extract form fields and normalize values.
  - Store parsed outputs as CSV/Parquet in `data/parsed/`.

- Processing & modeling
  - Delta calculator: align fields across versions, compute categorical differences and numeric deltas.
  - Scoring: heuristic rules (missing key fields, security control regressions, revenue/employee jumps) and optional small ML model (logistic/regression tree) trained on labeled outcomes from Dataset 1 (status changes: Declined→Rated etc.).

- Explainability & reporting
  - Per-account delta reports (HTML/PDF) with highlighted changes and summary score.
  - Notebook-driven dashboards and example charts for slides.

- Deployment & demo
  - Keep local: Jupyter notebooks + static HTML reports, or a lightweight Streamlit app for live demo.
  - GitHub: document everything, include `requirements.txt`, `notebooks/`, `src/`, and example outputs in `outputs/`.

Roles & responsibilities (hackathon-sized)
------------------------------------------
- AI Solution Architect: define scope, data contracts, end-to-end design, and demo narrative.
- Data Engineer: ingest Excel, implement PDF extraction pipeline, normalize and store parsed data.
- Data Scientist: exploratory analysis, delta definitions, simple scoring model, and evaluation metrics.
- Claims/UW/Pricing Expert Analyst: define which fields matter, validate parsed fields, and craft business rules/thresholds.
- Business Analyst: write the demo storyline, prepare slides and ensure outputs answer UW questions.

Data & governance considerations
-------------------------------
- Use anonymized identifiers only; avoid PII and follow confidentiality constraints.
- Track provenance: keep original PDFs intact, store parsed outputs with source file references and extraction confidence scores.
- Keep models simple and interpretable; capture decision logic as rules for auditing.

Minimal tech stack & local setup (fast)
--------------------------------------
- Python 3.10+ with: pandas, pypdf, scikit-learn, jupyter, matplotlib/plotly, optionally spaCy and streamlit.
- Repo scaffold: `notebooks/`, `src/`, `data/raw/`, `data/parsed/`, `outputs/`, `docs/`.
- Estimated compute: laptop with ~4–8 CPU cores, 8–16GB RAM sufficient for the hackathon prototype.

Proposed 10-day timeline to 22 June (prioritized)
-------------------------------------------------
Day 1–2: Ingest `Dataset 1`, run repeat-customer analytics, deliver notebook & charts.
Day 3–5: Parse PDFs for pilot 5 customers, produce parsed CSVs and per-account delta reports.
Day 6–7: Extend parsing to all 25 customers, refine extraction rules, and build scoring heuristics.
Day 8: Build demo notebook/Streamlit app showing prioritized list and sample delta reports.
Day 9: Prepare slides and rehearse pitch.
Day 10: Final polish, package repo for GitHub, create README and usage instructions.

Success criteria (for hackathon judges)
--------------------------------------
- Demonstrable prevalence of repeat submissions and clear prioritization strategy.
- Successful extraction and delta reports for multiple real examples (5+).
- Simple scoring or heuristic that meaningfully separates low-change vs high-change submissions.
- Clear, reproducible repo and demo that judges can run locally.

Next steps (pick one)
---------------------
- I can scaffold the repo now and create starter notebooks and scripts.
- Or I can begin by running EDA on `Dataset 1` (please provide path or put file in `c:\PROJECT\data\raw\`).
- Or I can start parsing the 25 submission PDFs (please provide the folder path where they are stored).

--
Generated for the Zurich hackathon MVP plan. Please tell me which next step you want me to perform and I will proceed.