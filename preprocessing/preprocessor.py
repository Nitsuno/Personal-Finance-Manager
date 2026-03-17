import pandas as pd
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "db" / "statements.db"


def load_from_db(db_path=DB_PATH):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql("SELECT * FROM transactions", conn)


def preprocess_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Pure in-memory normalization — no DB reads or CSV writes.

    Input: raw DataFrame from clean_desc_robust (or similar) with at least
           columns: Vendor, Amount, Sale Type, Location, Account.
    Output: cleaned DataFrame with Debit_amt, Credit_amt, Details columns added.
    """
    df = raw_df.copy()

    clean_amount = df['Amount'].str.replace(',', '')

    debit_strings = clean_amount.where(clean_amount.str.endswith('-')).str.rstrip('-')
    df['Debit_amt'] = pd.to_numeric(debit_strings, errors='coerce').fillna(0.0)

    credit_strings = clean_amount.where(clean_amount.str.endswith('+')).str.rstrip('+')
    df['Credit_amt'] = pd.to_numeric(credit_strings, errors='coerce').fillna(0.0)

    split_vendor = df['Vendor'].str.split('*', n=1, expand=True)
    df['Vendor'] = split_vendor[0].str.strip()
    df['Details'] = split_vendor[1].str.strip() if 1 in split_vendor.columns else pd.Series("", index=df.index)

    df['Details'] = df['Details'].replace('', 'No Details')
    df['Vendor'] = df['Vendor'].str.replace('Ezypay', 'ANYTIME FITNESS')
    df['Vendor'] = df['Vendor'].str.split('-').str[0]
    df['Vendor'] = df['Vendor'].str.split(',').str[0]
    df["Details"] = df["Details"].fillna("No Details")
    df.dropna(how='any', inplace=True)
    df.replace({"Vendor": {'': '7-ELEVEN'}}, inplace=True)

    return df


def run_preprocessing(db_path=DB_PATH, out_csv=None):
    if out_csv is None:
        out_csv = BASE_DIR / "data" / "to_label.csv"
    raw_df = load_from_db(db_path)
    raw_df = raw_df.rename(columns={"month": "Date"})
    df = preprocess_df(raw_df)
    df.to_csv(out_csv, index=False)
    return df


if __name__ == "__main__":
    run_preprocessing()
