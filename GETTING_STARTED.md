# Getting Started — EOS AI

## Prerequisites

- Python 3.12+
- Windows (tested) or Linux/Mac
- API credentials for Zurich GenAI proxy (or Anthropic API key)

---

## Step 1 — Install dependencies

```bash
cd c:\PROJECT
pip install -r requirements.txt
```

---

## Step 2 — Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_BASE_URL=https://genai-lounge-nx-litellm-uat-emea.zurich.com
ANTHROPIC_MODEL=eu.anthropic.claude-sonnet-4-6
UW_WATCH_FOLDER=data/raw/new_submissions
```

---

## Step 3 — Place raw data

```
data/raw/Dataset1.xlsx              # Specialties submissions 2021-2026
data/raw/Dataset2_PDFs/             # PDF folders per customer
  └── Customer_001/
      ├── submission_2022.pdf
      └── submission_2024.pdf
data/raw/uw_guidelines/             # Zurich UW guideline PDFs (for RAG)
```

---

## Step 4 — Run the data pipeline (once)

```bash
python src/data/loader.py                    # Ingest Excel → CSVs
python extract_pdfs.py                       # Parse PDFs → pdf_extracted_fields.csv
python src/business/mass_scoring.py          # Score 9,078 repeat customers
python src/business/mass_deltas.py           # Compute first→latest deltas
python scripts/build_knowledge_graph.py      # Build NetworkX KG (10K nodes)
python scripts/precompute_kg.py              # Pre-compute KG analytics for fast dashboard
python -m src.rag.guidelines_rag --build     # Build RAG index from guideline PDFs
```

`start_demo.py` validates these files at startup and will tell you which are missing.

---

## Step 5 — Launch the demo

```bash
# Phase 2 — MCP servers + background watcher (recommended):
python start_demo.py --mcp

# Phase 1 — inline tools only (no MCP servers needed):
python start_demo.py
```

The dashboard opens at `http://localhost:8501`.

**What starts with `--mcp`:**
- `submissions_server.py` on port 8601
- `scoring_server.py` on port 8602
- `kg_server.py` on port 8603
- `watcher_server.py` on port 8604
- `watcher.py` as background process (polls `UW_WATCH_FOLDER` every 30s)
- Streamlit dashboard on port 8501

---

## Step 6 — Test new submission watcher

Drop a PDF into `data/raw/new_submissions/`. Within 30 seconds the watcher will analyse it and the badge in the sidebar will update. Open New Submission to see the pre-analysis.

---

## Stop

```bash
python start_demo.py --stop
```

---

## Directory structure

```
app.py                     Streamlit entry point (107 lines, routing only)
start_demo.py              Launch script
.env                       API keys (git-ignored)
requirements.txt           Python dependencies

src/
  pages/                   5 Streamlit pages
  agent/                   Orchestrator + MCP client + briefing + watcher
  mcp_servers/             4 MCP HTTP servers (ports 8601-8604)
  data/                    CSV loaders + PDF parser
  models/                  NetworkX KG + visualisation + digital twin
  rag/                     RAG index builder + retrieval
  business/                Scoring + delta computation
  startup/                 Pipeline validation

data/
  raw/                     Source data (git-ignored)
  parsed/                  Generated files (git-ignored)
```

See `docs/USER_MANUAL.md` for full documentation.
See `docs/ARCHITECTURE.md` for system design.
