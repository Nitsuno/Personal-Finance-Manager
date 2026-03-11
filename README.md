# Personal Finance Manager

A local Streamlit app for parsing Maybank bank statement PDFs, labeling transactions by category, training an ML classifier, and visualising spending patterns — all without sending data to any external service.

## Features

- **PDF parsing** — extracts transactions from bank statement PDFs via `pdfplumber`
- **Review** — filterable transaction table with debit/credit summary metrics
- **Manual labeling** — label transactions one-by-one or in bulk by vendor
- **ML classification** — TF-IDF + Logistic Regression trained on your labeled data; predicts categories for unlabeled transactions with confidence scores
- **Visualise** — interactive Altair charts (spending by category, donut breakdown, monthly trend line) filterable by month and data source

## Tech Stack

- Python 3
- [Streamlit](https://streamlit.io/) — UI
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF parsing
- [pandas](https://pandas.pydata.org/) — data processing
- [scikit-learn](https://scikit-learn.org/) — TF-IDF + Logistic Regression pipeline
- [Altair](https://altair-viz.github.io/) — charts
- SQLite — transaction storage

## Setup

```bash
git clone <repo-url>
cd personal-finance

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Usage

```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

### Workflow

1. **Upload & Process** — upload monthly PDF bank statements, assign month/year, click Process
2. **Review** — browse and filter all parsed transactions
3. **Label** — assign categories to transactions (one-by-one or bulk by vendor)
4. **Predict** — train the model once you have ≥10 labeled samples; run predictions on unlabeled data; accept high-confidence predictions as labels
5. **Visualise** — explore spending charts filtered by month; toggle between labeled, predicted, or combined data

## Project Structure

```
app.py                        — Streamlit UI (5 tabs)
parsers/
  pdf_parser.py               — PDF → SQLite
preprocessing/
  preprocessor.py             — SQLite → data/to_label.csv
ml/
  trainer.py                  — train(), predict(), model_exists()
  model.pkl                   — saved model (generated after first train)
db/
  statements.db               — SQLite database
data/
  to_label.csv                — all parsed transactions
  labeled.csv                 — transactions with user-assigned categories
```

## Notes

- All data stays local — no cloud services involved
- Avoid uploading the same month's PDF twice (creates duplicate rows in the DB)
- The ML model only trains on the canonical category list; the Visualise tab shows all categories including any custom ones added during labeling
