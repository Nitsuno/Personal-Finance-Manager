import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline

import db.postgres as pgdb

CATEGORIES = [
    "Dining & Food",
    "Transport",
    "Fitness & Health",
    "Groceries",
    "Retail & Shopping",
    "Utilities & Bills",
    "Transfer",
    "Entertainment",
    "Medical",
    "Income",
    "Other",
]


def build_text_features(df: pd.DataFrame) -> pd.Series:
    """Concatenate Vendor, Details, and Sale Type into a single text field."""
    return (
        df["Vendor"].fillna("").str.upper() + " "
        + df["Details"].fillna("") + " "
        + df["Sale Type"].fillna("")
    )


def train() -> dict:
    """Train the classifier on labeled data stored in PostgreSQL. Returns metrics."""
    df = pgdb.load_labeled()
    df = df[df["Category"].isin(CATEGORIES)].copy()

    if len(df) < 10:
        raise ValueError(f"Only {len(df)} valid labeled samples — label more data first.")

    X = build_text_features(df)
    y = df["Category"]

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=1.0,
            solver="lbfgs",
        )),
    ])

    # Cross-validation — cap folds at smallest class count
    min_class = y.value_counts().min()
    n_splits = min(5, int(min_class))
    if n_splits >= 2:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        results = cross_validate(pipe, X, y, cv=cv,
                                 scoring=["accuracy", "f1_weighted"],
                                 return_train_score=False)
        cv_accuracy = results["test_accuracy"].mean()
        cv_f1 = results["test_f1_weighted"].mean()
    else:
        cv_accuracy = cv_f1 = None

    # Fit on all data and save to PostgreSQL
    pipe.fit(X, y)
    pgdb.save_model(pipe)

    return {
        "n_samples": len(df),
        "n_classes": y.nunique(),
        "class_counts": y.value_counts().to_dict(),
        "cv_accuracy": cv_accuracy,
        "cv_f1_weighted": cv_f1,
        "n_splits": n_splits,
    }


def predict(df: pd.DataFrame):
    """
    Returns (predicted_labels, confidence_scores) arrays aligned with df.
    Raises ValueError if model hasn't been trained yet.
    """
    pipe = pgdb.load_model()
    if pipe is None:
        raise ValueError("No trained model found. Train one first.")
    X = build_text_features(df)
    labels = pipe.predict(X)
    proba = pipe.predict_proba(X)
    confidence = proba.max(axis=1)
    return labels, confidence


def model_exists() -> bool:
    return pgdb.model_exists()
