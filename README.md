# Personal Finance Manager

A Streamlit app for parsing Maybank bank statement PDFs, labeling transactions by category, training an ML classifier, and visualising spending patterns. Deployable to [Railway](https://railway.app/) with PostgreSQL for persistent storage.

## Features

- **PDF parsing** — extracts transactions from bank statement PDFs via `pdfplumber`
- **Review** — filterable transaction table with debit/credit summary metrics
- **Manual labeling** — label transactions one-by-one or in bulk by vendor
- **ML classification** — TF-IDF + Logistic Regression trained on your labeled data; predicts categories for unlabeled transactions with confidence scores
- **Visualise** — interactive Altair charts (spending by category, donut breakdown, monthly trend line) filterable by month and data source
- **Budget & Report** — set monthly spending limits per category, view a budget vs actual report with progress bars and alerts, and export a PDF summary

## Tech Stack

- Python 3.12
- [Streamlit](https://streamlit.io/) — UI
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF parsing
- [pandas](https://pandas.pydata.org/) — data processing
- [scikit-learn](https://scikit-learn.org/) — TF-IDF + Logistic Regression pipeline
- [joblib](https://joblib.readthedocs.io/) — model serialization
- [Altair](https://altair-viz.github.io/) — charts
- [fpdf2](https://py-pdf.github.io/fpdf2/) — PDF report generation
- [psycopg2](https://www.psycopg.org/) — PostgreSQL driver
- PostgreSQL — persistent storage (transactions, labels, model, budget limits)

## Local Development

```bash
git clone <repo-url>
cd personal-finance

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set the `DATABASE_URL` environment variable pointing to a local or remote PostgreSQL instance:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/personal_finance"
streamlit run app.py
```

The app creates all required tables on startup via `db/postgres.py:init_db()`.

### Demo Data

No bank statements? Use the built-in demo data loader in the **Upload & Process** tab — it seeds 6 months of synthetic Malaysian transactions (Oct 2024 – Mar 2025) across all spending categories.

## Docker

```bash
docker build -t personal-finance .
docker run -p 8501:8501 -e DATABASE_URL="postgresql://..." personal-finance
```

Open `http://localhost:8501`.

## Railway Deployment

1. Push the repo to GitHub
2. Create a new Railway project → **Deploy from GitHub repo**
3. Add a **PostgreSQL** service to the project (Railway UI)
4. Railway auto-sets `DATABASE_URL` in the app service's environment
5. Railway reads the `Dockerfile`, builds the image, and deploys — `PORT` is injected automatically
6. App is live at `<project>.railway.app`

## Workflow

1. **Upload & Process** — upload monthly PDF bank statements, assign month/year, click Process; or load built-in demo data
2. **Review** — browse and filter all parsed transactions
3. **Label** — assign categories to transactions (one-by-one or bulk by vendor)
4. **Predict** — train the model once you have ≥10 labeled samples; run predictions on unlabeled data; accept high-confidence predictions as labels
5. **Visualise** — explore spending charts filtered by month; toggle between labeled, predicted, or combined data
6. **Budget & Report** — set per-category monthly limits, review a budget vs actual table with progress bars and over-budget alerts, export a PDF report

## Project Structure

```
app.py                        — Streamlit UI (6 tabs)
Dockerfile                    — Railway/Docker build config
db/
  postgres.py                 — PostgreSQL adapter (all DB I/O)
parsers/
  pdf_parser.py               — PDF → raw transaction DataFrame
preprocessing/
  preprocessor.py             — preprocess_df() + run_preprocessing() (SQLite CLI path)
ml/
  trainer.py                  — train(), predict(), model_exists() — model stored in PostgreSQL
scripts/
  seed_demo_data.py           — generates 6 months of synthetic demo transactions
```

## Notes

- Avoid uploading the same month's PDF twice — the app guards against duplicate months at insert time
- The ML model is stored as a BYTEA blob in PostgreSQL alongside all other state; container restarts do not lose data
- The ML model only trains on the canonical category list; the Visualise tab shows all categories found in data including any custom ones added during labeling
