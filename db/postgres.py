import io
import os

import joblib
import pandas as pd
import psycopg2
import psycopg2.extras


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    "Date" TEXT NOT NULL,
                    "Vendor" TEXT,
                    "Details" TEXT,
                    "Location" TEXT,
                    "Sale Type" TEXT,
                    "Amount" TEXT,
                    "Debit_amt" FLOAT,
                    "Credit_amt" FLOAT,
                    "Account" TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS labels (
                    id SERIAL PRIMARY KEY,
                    "Date" TEXT NOT NULL,
                    "Vendor" TEXT NOT NULL,
                    "Amount" TEXT NOT NULL,
                    "Category" TEXT NOT NULL,
                    "Details" TEXT,
                    "Location" TEXT,
                    "Sale Type" TEXT,
                    "Debit_amt" FLOAT,
                    "Credit_amt" FLOAT,
                    "Account" TEXT,
                    UNIQUE ("Date", "Vendor", "Amount")
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS budget_limits (
                    category TEXT PRIMARY KEY,
                    limit_amount FLOAT NOT NULL DEFAULT 0.0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    model_data BYTEA NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)


def load_transactions() -> pd.DataFrame:
    with _conn() as conn:
        df = pd.read_sql('SELECT * FROM transactions ORDER BY "Date"', conn)
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def month_exists(month_label: str) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM transactions WHERE "Date" = %s', (month_label,))
            return cur.fetchone()[0] > 0


def save_transactions(df: pd.DataFrame, month_label: str) -> int:
    if month_exists(month_label):
        return 0
    df = df.copy()
    df["Date"] = month_label
    cols = ["Date", "Vendor", "Details", "Location", "Sale Type", "Amount", "Debit_amt", "Credit_amt", "Account"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    rows = df[cols].where(pd.notnull(df[cols]), None).to_dict("records")
    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO transactions ("Date", "Vendor", "Details", "Location", "Sale Type", "Amount", "Debit_amt", "Credit_amt", "Account")
                VALUES (%(Date)s, %(Vendor)s, %(Details)s, %(Location)s, %(Sale Type)s, %(Amount)s, %(Debit_amt)s, %(Credit_amt)s, %(Account)s)
            """, rows)
    return len(rows)


def load_labeled() -> pd.DataFrame:
    with _conn() as conn:
        df = pd.read_sql("SELECT * FROM labels", conn)
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def save_labeled_batch(df: pd.DataFrame):
    cols = ["Date", "Vendor", "Amount", "Category", "Details", "Location", "Sale Type", "Debit_amt", "Credit_amt", "Account"]
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = None
    rows = df[cols].where(pd.notnull(df[cols]), None).to_dict("records")
    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO labels ("Date", "Vendor", "Amount", "Category", "Details", "Location", "Sale Type", "Debit_amt", "Credit_amt", "Account")
                VALUES (%(Date)s, %(Vendor)s, %(Amount)s, %(Category)s, %(Details)s, %(Location)s, %(Sale Type)s, %(Debit_amt)s, %(Credit_amt)s, %(Account)s)
                ON CONFLICT ("Date", "Vendor", "Amount") DO UPDATE SET
                    "Category" = EXCLUDED."Category",
                    "Details" = EXCLUDED."Details",
                    "Location" = EXCLUDED."Location",
                    "Sale Type" = EXCLUDED."Sale Type",
                    "Debit_amt" = EXCLUDED."Debit_amt",
                    "Credit_amt" = EXCLUDED."Credit_amt",
                    "Account" = EXCLUDED."Account"
            """, rows)


def load_budget_limits() -> dict:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT category, limit_amount FROM budget_limits")
            rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}


def save_budget_limits(limits: dict):
    rows = [{"category": cat, "limit_amount": float(amt)} for cat, amt in limits.items()]
    with _conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO budget_limits (category, limit_amount)
                VALUES (%(category)s, %(limit_amount)s)
                ON CONFLICT (category) DO UPDATE SET limit_amount = EXCLUDED.limit_amount
            """, rows)


def save_model(pipeline):
    buf = io.BytesIO()
    joblib.dump(pipeline, buf)
    model_bytes = buf.getvalue()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO models (id, model_data, updated_at)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET model_data = EXCLUDED.model_data, updated_at = NOW()
            """, (psycopg2.Binary(model_bytes),))


def load_model():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT model_data FROM models WHERE id = 1")
            row = cur.fetchone()
    if row is None:
        return None
    buf = io.BytesIO(bytes(row[0]))
    return joblib.load(buf)


def model_exists() -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM models WHERE id = 1")
            return cur.fetchone()[0] > 0


def clear_all():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE transactions, labels, budget_limits, models RESTART IDENTITY")
