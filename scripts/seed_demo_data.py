import sys
import random
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

import db.postgres as pgdb
from preprocessing.preprocessor import preprocess_df

MONTHS = ["2024-10", "2024-11", "2024-12", "2025-01", "2025-02", "2025-03"]
LABEL_MONTHS = {"2024-10", "2024-11", "2024-12", "2025-01"}

VENDOR_POOLS = {
    "Dining & Food": [
        "GRABFOOD", "FOODPANDA", "TEALIVE", "OLD TOWN WHITE COFFEE",
        "MARRYBROWN", "SECRET RECIPE", "PAPA RICH", "WINGSTOP KL",
    ],
    "Transport": [
        "TOUCH N GO", "PETRON CYBERJAYA", "PETRONAS",
        "PLUS EXPRESSWAYS", "MYCAR",
    ],
    "Fitness & Health": [
        "ANYTIME FITNESS", "CELEBRITY FITNESS", "DECATHLON", "GUARDIAN PHARMACY",
    ],
    "Groceries": [
        "JAYA GROCER", "VILLAGE GROCER", "AEON BIG", "LOTUS'S", "NSK TRADE CITY",
    ],
    "Retail & Shopping": [
        "MR DIY", "DAISO", "UNIQLO", "H&M", "ZALORA", "SHOPEE PAYMENT",
    ],
    "Utilities & Bills": [
        "UNIFI BROADBAND", "MAXIS", "CELCOM", "TNB ONLINE", "INDAH WATER", "SYABAS",
    ],
    "Transfer": [
        "AHMAD RIZAL", "FAMILY TRANSFER", "ROOMMATE SPLIT",
    ],
    "Entertainment": [
        "GSC CINEMAS", "TGV CINEMAS", "NETFLIX", "SPOTIFY", "KLOOK",
    ],
    "Medical": [
        "KLINIK KESIHATAN", "COLUMBIA ASIA HOSPITAL", "WATSONS",
    ],
    "Income": [
        "EMPLOYER SALARY SDN BHD", "FREELANCE PAYMENT",
    ],
    "Other": [
        "7-ELEVEN", "RANDOM MINI MART", "PARKING DBKL",
    ],
}

VENDOR_CATEGORY = {
    vendor: cat
    for cat, vendors in VENDOR_POOLS.items()
    for vendor in vendors
}

# count = transactions per month for this category
CATEGORY_CONFIG = {
    "Dining & Food": {
        "count": 10,
        "amount_range": (15.0, 65.0),
        "sale_types": ["SALE DEBIT", "PAYMENT VIA MYDEBIT"],
        "is_credit": False,
    },
    "Transport": {
        "count": 6,
        "amount_range": (15.0, 120.0),
        "sale_types": ["SALE DEBIT", "PAYMENT VIA MYDEBIT", "FPX PAYMENT FR A/"],
        "is_credit": False,
    },
    "Fitness & Health": {
        "count": 1,
        "amount_range": (175.0, 175.0),
        "sale_types": ["PYMT FROM A/C"],
        "is_credit": False,
    },
    "Groceries": {
        "count": 4,
        "amount_range": (30.0, 80.0),
        "sale_types": ["SALE DEBIT", "PAYMENT VIA MYDEBIT"],
        "is_credit": False,
    },
    "Retail & Shopping": {
        "count": 3,
        "amount_range": (15.0, 65.0),
        "sale_types": ["SALE DEBIT", "FPX PAYMENT FR A/"],
        "is_credit": False,
    },
    "Utilities & Bills": {
        "count": 4,
        "amount_range": (60.0, 130.0),
        "sale_types": ["FPX PAYMENT FR A/", "PYMT FROM A/C"],
        "is_credit": False,
    },
    "Transfer": {
        "count": 2,
        "amount_range": (50.0, 500.0),
        "sale_types": ["IBK FUND TFR FR A/C", "FUND TRANSFER TO A/"],
        "is_credit": False,
    },
    "Entertainment": {
        "count": 3,
        "amount_range": (12.0, 60.0),
        "sale_types": ["SALE DEBIT", "FPX PAYMENT FR A/"],
        "is_credit": False,
    },
    "Medical": {
        "count": 1,
        "amount_range": (20.0, 200.0),
        "sale_types": ["SALE DEBIT", "PAYMENT VIA MYDEBIT"],
        "is_credit": False,
    },
    "Income": {
        "count": 1,
        "amount_range": (3500.0, 5000.0),
        "sale_types": ["PYMT FROM A/C"],
        "is_credit": True,
    },
    "Other": {
        "count": 4,
        "amount_range": (3.0, 30.0),
        "sale_types": ["SALE DEBIT", "PAYMENT VIA MYDEBIT"],
        "is_credit": False,
    },
}

BUDGET_LIMITS = {
    "Dining & Food": 400.0,
    "Transport": 200.0,
    "Fitness & Health": 200.0,
    "Groceries": 300.0,
    "Retail & Shopping": 150.0,
    "Utilities & Bills": 500.0,
    "Transfer": 0.0,
    "Entertainment": 100.0,
    "Medical": 0.0,
    "Income": 0.0,
    "Other": 0.0,
}


def generate_transactions() -> list[dict]:
    random.seed(42)
    rows = []
    for month in MONTHS:
        for cat, cfg in CATEGORY_CONFIG.items():
            vendors = VENDOR_POOLS[cat]
            lo, hi = cfg["amount_range"]
            for _ in range(cfg["count"]):
                vendor = random.choice(vendors)
                amount = lo if lo == hi else round(random.uniform(lo, hi), 2)
                suffix = "+" if cfg["is_credit"] else "-"
                amt_str = f"{amount:.2f}{suffix}"
                sale_type = random.choice(cfg["sale_types"])
                rows.append({
                    "Sale Type": sale_type,
                    "Vendor": vendor,
                    "Location": "",
                    "Account": "",
                    "Amount": amt_str,
                    "_month": month,
                })
    return rows


def seed_demo_data():
    # Wipe existing data and reinitialise schema
    pgdb.init_db()
    pgdb.clear_all()

    # Generate and insert transactions month by month
    rows = generate_transactions()
    df_all = pd.DataFrame(rows)

    for month in MONTHS:
        month_df = (
            df_all[df_all["_month"] == month]
            .drop(columns=["_month"])
            .reset_index(drop=True)
        )
        clean_df = preprocess_df(month_df)
        pgdb.save_transactions(clean_df, month_label=month)

    # Build labeled data: label transactions from the first 4 months (~67%)
    to_label_df = pgdb.load_transactions()
    labeled_df = to_label_df[to_label_df["Date"].isin(LABEL_MONTHS)].copy()
    labeled_df["Category"] = labeled_df["Vendor"].map(VENDOR_CATEGORY)
    labeled_df.dropna(subset=["Category"], inplace=True)
    pgdb.save_labeled_batch(labeled_df)

    # Write demo budget limits
    pgdb.save_budget_limits(BUDGET_LIMITS)

    total = len(to_label_df)
    n_labeled = len(labeled_df)
    print(f"Seeded {total} transactions across {len(MONTHS)} months.")
    print(f"Labeled: {n_labeled}/{total} ({n_labeled / total * 100:.0f}%)")


if __name__ == "__main__":
    seed_demo_data()
    print("Demo data seeded successfully.")
