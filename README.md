# Zurich Repeat New Business Intelligence System
## Hackathon MVP: Leveraging Historical Data to Improve NB Decisions

**Deadline**: 22 June 2026  
**Team Size**: 5 roles (AI Architect, Data Engineer, Data Scientist, UW/Claims Expert, Business Analyst)  
**Local Development**: Windows + Python 3.12, no cloud required.

---

## Quick Start

```bash
# Clone & setup
git clone <repo>
cd c:\PROJECT

# Install dependencies
pip install -r requirements.txt

# Run data ingestion (populate cache from Dataset 1 & 2)
python src/data/loader.py

# Run knowledge graph builder
python src/models/graph_builder.py

# Launch dashboard
streamlit run app.py
```

The dashboard will open at `http://localhost:8501`.

---

## Problem Statement

**Zurich repeats submissions frequently, but treats each as "new."**
- Same customer, same line of business (LOB), different year = we ignore prior knowledge.
- Opportunity: detect repeats, extract historical deltas, and recommend fast-track approval for low-risk renewals.

**Goal**: Build an underwriting decision-support system that surfaces:
1. Which submissions are repeat customers?
2. What has changed (revenue, controls, risk profile)?
3. Should this be fast-tracked or require fresh underwriting?
4. Who are the peer customers and what was their outcome?

---

## Solution Overview

**Architecture**: Rule-driven system + knowledge graph + dashboard.

```
Inputs:
  - Dataset 1: Excel with 5 years of Specialties submissions (2021–2026)
  - Dataset 2: PDF submission packages for 25 repeat Cyber customers

Processing:
  1. Parse Excel → identify repeat customers, compute trends
  2. Parse PDFs → extract fields (revenue, controls, policies, etc.)
  3. Compute deltas vs baseline submission
  4. Build knowledge graph → detect risk clusters, broker patterns, control impact
  5. Score recommendations → FAST-TRACK | STANDARD-UW | FRESH-UW

Outputs:
  - Prioritized queue of 25 customers (sortable by risk, LOB, broker)
  - Per-customer risk trajectory (2022–2026 timeline)
  - Peer-group analysis (similar customers + approval rates)
  - Recommendation + reasoning for each submission
  - Dashboard + exportable reports
```

---

## Deliverables

| Phase | Timeline | Deliverable | Impact |
|-------|----------|-------------|--------|
| **MVP-1** | Days 1–3 | Repeat-customer analytics + Excel insights | Establishes scale of opportunity |
| **MVP-2** | Days 4–5 | PDF parsing + delta extraction | Proves data quality + field relevance |
| **MVP-3** | Days 6–7 | Knowledge graph + risk clusters | Shows pattern discovery depth |
| **MVP-4** | Days 8–9 | Dashboard + recommendation engine | Live demo ready |
| **Polish** | Days 10–12 | Slides + dry run + repo documentation | Pitch-ready |

---

## Timeline: 10 June → 22 June (12 days)

```
Days 1–3: Data Engineering
  - Ingest Dataset 1 (Excel) → SQLite cache
  - Initial EDA: repeat rates by LOB, broker, cadence
  - Deliverable: Jupyter notebook + charts

Days 4–5: PDF Parsing & Feature Engineering
  - Parse Dataset 2 PDFs (25 customers, 4–5 submissions each)
  - Extract fields: revenue, employees, controls, policies, financials
  - Compute deltas vs first submission per customer
  - Deliverable: Parsed CSVs + per-customer delta reports

Days 6–7: Knowledge Graph & Risk Scoring
  - Build NetworkX graph: nodes (customer, submission, control, broker), edges (relationships)
  - Implement clustering: detect risk groups
  - Compute scoring rules: revenue_delta, control_regression, decision_history
  - Deliverable: Graph object + cluster assignments + sample recommendations

Days 8–9: Dashboard & Recommendation Engine
  - Build Streamlit dashboard:
    - Prioritization queue (sorted by recommendation)
    - Risk trajectories (per customer)
    - KG insights (peers, clusters, control impact)
  - Wire recommendation engine to dashboard
  - Deliverable: Live demo + 5 example customers

Days 10–11: Polish & Slides
  - Dry run demo (5 min pitch)
  - Prepare slides: problem → solution → results
  - Document code + create usage guide
  - Test on different machines
  - Deliverable: Slide deck + README

Day 12: Submission & Final Checks
  - Push to GitHub
  - Final polish on demo
  - Ready for presentation
```

---

## Project Structure

```
c:\PROJECT\
├── data/
│   ├── raw/                      # Original datasets (Dataset1.xlsx, Dataset2_PDFs/)
│   └── parsed/                   # Processed CSVs, SQLite cache
├── src/
│   ├── __init__.py
│   ├── data/
│   │   ├── loader.py             # Ingest Excel + PDFs
│   │   ├── pdf_parser.py         # Extract fields from PDFs
│   │   └── normalizer.py         # Standardize values
│   ├── business/
│   │   ├── models.py             # Pydantic: Submission, Customer, Delta
│   │   ├── scoring.py            # Risk scoring rules
│   │   ├── rules.py              # UW decision logic
│   │   ├── delta_calc.py         # Compare submissions
│   │   └── recommender.py        # Generate recommendations
│   ├── models/
│   │   ├── graph_builder.py      # Build NetworkX knowledge graph
│   │   └── pattern_discovery.py  # Query & analyze KG
│   └── query/
│       └── engine.py             # Route queries to data/KG/rules
├── notebooks/
│   ├── 01_eda.ipynb              # Exploratory analysis (Dataset 1)
│   └── 02_delta_analysis.ipynb   # Delta computation examples
├── app.py                         # Streamlit dashboard (main UI)
├── requirements.txt               # Python dependencies
├── README.md                      # This file
├── docs/
│   ├── 3-pager.md                # Use case + possibilities
│   └── ARCHITECTURE.md            # System design
└── outputs/
    └── (exported reports, CSVs, screenshots)
```

---

## Key Features

### 1. Repeat-Customer Detection
- Identify customers appearing >1 time in 5-year dataset.
- Metrics: repeat rate by LOB, by broker, by cadence (annual, biannual, etc.).

### 2. Submission Delta Analysis
- Compare each submission vs first baseline.
- Track: revenue (↑/↓ %), employees, control maturity, security policies.
- Highlight fields added/removed/changed.

### 3. Knowledge Graph Pattern Discovery
- **Risk Clustering**: Group customers by control + revenue profile.
- **Broker Intelligence**: Which brokers send high-quality submissions? Approval rates?
- **Control Impact**: Which controls predict approval? Which regressions are red flags?
- **Anomaly Detection**: Submissions breaking their peer-group patterns.

### 4. Recommendation Engine
- Per-submission scoring: 0–100 (higher = lower risk).
- Output: **FAST-TRACK** (score >75), **STANDARD-UW** (50–75), **FRESH-UW** (<50).
- Reasoning: "Matches low-risk cluster (similar customers had 85% approval) + controls stable vs 2024."

### 5. Interactive Dashboard
- Sortable queue of 25 customers by recommendation + risk score.
- Risk trajectories: timeline showing revenue, employees, controls, UW decisions.
- Peer insights: "Similar customers" + approval rates.
- Drill-down: click customer → all submissions + deltas + KG cluster details.

---

## Technology Stack

| Component | Tool | Rationale |
|-----------|------|-----------|
| Data Processing | pandas, openpyxl, pypdf | Standard, lightweight, local |
| Data Models | Pydantic | Type safety + validation |
| Knowledge Graph | NetworkX | Local, fast, no server overhead |
| Scoring + ML | scikit-learn | Simple rules + optional anomaly detection |
| Dashboard | Streamlit | Minimal code, interactive, shareable |
| Database | SQLite | Fast local cache, no setup |
| Optional: NLU | spaCy | Lightweight intent classification (future) |
| Optional: Explainability | Claude API | Generate narrative explanations (future) |

---

## Success Criteria (for Judges)

- ✅ **Repeat-customer prevalence**: Show metric — "X% of submissions are repeats; here's where concentrated."
- ✅ **Data quality**: Successfully parsed 25 customers with 4–5 submissions each; fields validated.
- ✅ **Knowledge graph insights**: Demonstrate clustering + peer-group analysis on real examples.
- ✅ **Actionable recommendations**: For 5+ example customers, show why → FAST-TRACK vs FRESH-UW.
- ✅ **Interactive demo**: Judges can click dashboard, see deltas, understand logic.
- ✅ **Clean repo**: Code readable, documented, reproducible on judge's local machine.

---

## Getting Data Ready

### Dataset 1 (Excel): Specialties Submissions 2021–2026
- File: `data/raw/Dataset1.xlsx` or similar
- Expected columns: Company, Effective Date, NAICS, SIC, Product, Broker, Status, Quoted Premium
- First task: `src/data/loader.py` reads this → SQLite

### Dataset 2 (PDFs): 25 Repeat Cyber Customers
- Folder: `data/raw/Dataset2_PDFs/Customer_001/`, `Customer_002/`, etc.
- Each folder: 4–5 PDF submission applications (2021–2026)
- Second task: `src/data/pdf_parser.py` extracts fields → CSVs

**To get started:**
1. Place `Dataset1.xlsx` in `data/raw/`
2. Place PDF folders in `data/raw/Dataset2_PDFs/`
3. Run `python src/data/loader.py`

---

## Roles & Responsibilities

| Role | Tasks |
|------|-------|
| **AI Solution Architect** | Define scope, data contracts, system design; oversee integration; demo narrative |
| **Data Engineer** | Build ingestion pipelines (Excel, PDF), normalize data, maintain SQLite cache |
| **Data Scientist** | EDA, feature engineering, scoring rules, KG analysis, model evaluation |
| **UW/Claims Expert** | Validate extracted fields, define scoring rules, test recommendations, domain expertise |
| **Business Analyst** | Craft demo story, prepare slides, ensure outputs answer UW questions, business messaging |

---

## Escape Hatches (if running behind)

- **If PDF parsing is slow**: pre-parse a subset (5 customers) to demo; show full parsing runs async.
- **If KG is taking too long**: ship Tier 1 (scoring + dashboard) without KG; still competitive.
- **If dashboard is complex**: export CSVs + static HTML reports; judges can open in browser.

---

## Next Steps

1. **Data Readiness**: Place Dataset 1 & 2 in `data/raw/`.
2. **Run Setup**: `pip install -r requirements.txt`
3. **Day 1 Sprint**: Data loading + EDA notebook.
4. **Sync Daily**: Track progress against 12-day timeline; identify blockers early.

---

## Contact & Notes

- **Architecture**: See `docs/ARCHITECTURE.md`
- **Use Case**: See `docs/3-pager.md`
- **Questions**: Refer to inline code comments + docstrings.
- **Demo**: Streamlit app runs locally; judges can run `streamlit run app.py` after `pip install -r requirements.txt`.

---

**Generated**: 10 June 2026  
**Team**: Zurich Hackathon Participants  
**Mission**: Make underwriting smarter, faster, more explainable.
