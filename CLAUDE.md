# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

```bash
source venv/bin/activate
pip install -r requirements.txt  # pdfplumber, pandas, streamlit, altair, scikit-learn, joblib, fpdf2, psycopg2-binary
export DATABASE_URL="postgresql://user:password@localhost:5432/personal_finance"
```

## Running the App

```bash
# Launch the Streamlit UI (covers the full pipeline)
streamlit run app.py
```

The preprocessor can still be run standalone against a local SQLite DB (legacy CLI path, unchanged):

```bash
python parsers/pdf_parser.py       # parse a hardcoded monthly PDF → SQLite
python preprocessing/preprocessor.py  # regenerate data/to_label.csv from SQLite
```

## Architecture

All persistent state lives in PostgreSQL. The `db/postgres.py` module owns every DB interaction; no other module reads or writes files for state.

```
Bank Statement PDFs
        ↓
parsers/pdf_parser.py          — extracts transactions via pdfplumber → raw DataFrame
        ↓
preprocessing/preprocessor.py  — preprocess_df() normalizes amounts, splits vendors
        ↓
db/postgres.py                 — save_transactions(), load_transactions(), etc.
        ↓
PostgreSQL tables:
  transactions   — preprocessed transactions (replaces statements.db + to_label.csv)
  labels         — labeled transactions with Category (replaces labeled.csv)
  budget_limits  — per-category monthly limits (replaces budget_limits.json)
  models         — trained sklearn pipeline as BYTEA (replaces model.pkl)
```

### PostgreSQL Schema

```sql
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    "Date" TEXT NOT NULL,        -- "YYYY-MM" month label
    "Vendor" TEXT, "Details" TEXT, "Location" TEXT,
    "Sale Type" TEXT, "Amount" TEXT,
    "Debit_amt" FLOAT, "Credit_amt" FLOAT, "Account" TEXT
);

CREATE TABLE labels (
    id SERIAL PRIMARY KEY,
    "Date" TEXT NOT NULL, "Vendor" TEXT NOT NULL, "Amount" TEXT NOT NULL,
    "Category" TEXT NOT NULL,
    "Details" TEXT, "Location" TEXT, "Sale Type" TEXT,
    "Debit_amt" FLOAT, "Credit_amt" FLOAT, "Account" TEXT,
    UNIQUE ("Date", "Vendor", "Amount")
);

CREATE TABLE budget_limits (
    category TEXT PRIMARY KEY,
    limit_amount FLOAT NOT NULL DEFAULT 0.0
);

CREATE TABLE models (
    id INTEGER PRIMARY KEY DEFAULT 1,
    model_data BYTEA NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Streamlit App (app.py)

Six tabs:

- **Upload & Process** — upload PDFs, assign month/year per file, runs `preprocess_df` + `pgdb.save_transactions`; guards against duplicate months
- **Review** — filterable table with summary metrics (debits, credits, period); filters by month, sale type, vendor, amount range
- **Label** — progress bar, two labeling modes:
  - *One by one*: shows transaction details + category radio buttons, Save/Skip/Back navigation
  - *Bulk by vendor*: group unlabeled transactions by vendor (sorted by frequency), assign category to all at once
  - Labeled data saved via `pgdb.save_labeled_batch()`; downloadable as CSV from within the tab
- **Predict** — train/retrain the ML model, run predictions on unlabeled transactions with confidence threshold, accept predictions as labels
- **Visualise** — Altair charts of categorised spending (bar, donut, monthly trend line); filterable by month; supports labeled-only, predicted-only, or combined data sources with confidence gating
- **Budget & Report** — three sections:
  - *Set Monthly Limits*: per-category number inputs (MYR), persisted via `pgdb.save_budget_limits()`
  - *Monthly Report*: month selector, data source toggle, summary metrics, styled budget-vs-actual table, progress bars, grouped bar chart (Altair 5 `xOffset`), over-budget alerts
  - *Export PDF*: generates an in-memory PDF via `fpdf2` with title, summary, budget table, exceeded limits, and top 10 transactions; served via `st.download_button`

## Key Implementation Details

**db/postgres.py** — single module owning all PostgreSQL I/O. Reads `DATABASE_URL` env var. Key functions:
- `init_db()` — CREATE TABLE IF NOT EXISTS for all 4 tables; called once at app startup (before `st.set_page_config`)
- `save_transactions(df, month_label)` — sets `Date = month_label`, bulk inserts; returns 0 if month already exists
- `save_labeled_batch(df)` — bulk upsert on `(Date, Vendor, Amount)` unique constraint
- `save_model(pipeline)` / `load_model()` — serialize via `io.BytesIO` + `joblib`; stored as BYTEA at `id=1`
- `clear_all()` — truncates all tables; used by `seed_demo_data`

**pdf_parser.py** — `get_master_lists(pdf_path)` and `clean_desc_robust(desc_list, amount_list)` are importable. `save_to_db(df, month_label, db_path)` still exists for the standalone SQLite CLI path but is not called from `app.py`. Module-level execution is guarded by `if __name__ == "__main__":`. Transaction types recognized: `SALE DEBIT`, `PYMT FROM A/C`, `FUND TRANSFER`, `FPX PAYMENT`, `PAYMENT VIA MYDEBIT`, `PRE-AUTH REFUND`.

**preprocessor.py** — `preprocess_df(raw_df)` is the primary importable function: pure in-memory normalization (no DB reads/writes). Vendor standardization (e.g. `"Ezypay"` → `"ANYTIME FITNESS"`), debit/credit parsing (+/- suffixes), missing details filled with `"No Details"`. `run_preprocessing(db_path, out_csv)` wraps it for the standalone SQLite CLI path.

**ml/trainer.py** — `train()` loads labeled data via `pgdb.load_labeled()`, fits TF-IDF + Logistic Regression, saves model via `pgdb.save_model()`, returns CV metrics. `predict(df)` loads model via `pgdb.load_model()`, returns `(labels, confidence_scores)`. `model_exists()` delegates to `pgdb.model_exists()`. No file paths; no `MODEL_PATH` or `LABELED_CSV` constants.

**build_viz_df(view_mode, conf_threshold)** in `app.py` — assembles the dataframe for the Visualise tab. Handles three modes: `"Labeled only"`, `"Predicted only"` (runs model on unlabeled, filters by confidence), `"Combined"` (merges both). Gates predicted modes on `model_exists()`.

**Labeling identity** — a transaction is considered already-labeled if `(Date, Vendor, Amount)` matches a row in the `labels` table (enforced by UNIQUE constraint). The `get_unlabeled()` helper in `app.py` applies the same check in-memory to filter the transactions DataFrame.

**CATEGORIES** — canonical list defined in both `app.py` and `ml/trainer.py`. The Visualise tab intentionally shows all categories found in data (including non-canonical ones) — do not filter to the canonical list there.

**Budget helpers** — `load_budget_limits()` in `app.py` wraps `pgdb.load_budget_limits()` and fills in `0.0` defaults for any category not yet in the DB. `build_budget_report(month_df, limits)` iterates CATEGORIES so every canonical category always appears in the report table. Status logic: `"Over budget"` if spent ≥ limit, `"Warning"` if spent ≥ 80% of limit, `"OK"` otherwise, `"No limit"` if limit == 0.

**PDF export** — `generate_pdf_report` uses `fpdf2` (`from fpdf import FPDF`). Returns `bytes(pdf.output())` for direct use with `st.download_button`. Only budget rows where `Limit > 0` are included in the PDF table.

**seed_demo_data.py** — calls `pgdb.init_db()` then `pgdb.clear_all()` at the start, generates synthetic rows via `preprocess_df`, inserts via `pgdb.save_transactions`, labels via `pgdb.save_labeled_batch`, sets budget limits via `pgdb.save_budget_limits`.

## Deployment (Railway)

1. Push repo to GitHub
2. Create Railway project → Deploy from GitHub repo
3. Add a PostgreSQL service — Railway auto-injects `DATABASE_URL`
4. Railway builds from `Dockerfile`; `PORT` is injected automatically
5. App is live at `<project>.railway.app`
