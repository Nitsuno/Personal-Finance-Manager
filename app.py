import sys
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "db" / "statements.db"
TO_LABEL_CSV = DATA_DIR / "to_label.csv"
LABELED_CSV = DATA_DIR / "labeled.csv"

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

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_MAP = {m: f"{i+1:02d}" for i, m in enumerate(MONTHS)}


# ── helpers ──────────────────────────────────────────────────────────────────

def load_transactions() -> pd.DataFrame:
    if TO_LABEL_CSV.exists():
        return pd.read_csv(TO_LABEL_CSV)
    return pd.DataFrame()


def load_labeled() -> pd.DataFrame:
    if LABELED_CSV.exists():
        return pd.read_csv(LABELED_CSV)
    return pd.DataFrame()


def save_labeled(df: pd.DataFrame):
    df.to_csv(LABELED_CSV, index=False)


def build_viz_df(view_mode: str, conf_threshold: float = 0.5) -> pd.DataFrame:
    from ml.trainer import predict, model_exists, MODEL_PATH
    df = load_transactions()
    labeled = load_labeled()

    if view_mode == "Labeled only":
        return labeled.copy() if not labeled.empty else pd.DataFrame()

    if view_mode == "Predicted only":
        unlabeled = get_unlabeled(df, labeled)
        if unlabeled.empty or not model_exists(MODEL_PATH):
            return pd.DataFrame()
        labels, scores = predict(unlabeled, MODEL_PATH)
        unlabeled = unlabeled.copy()
        unlabeled["Category"] = labels
        unlabeled["Confidence"] = scores
        return unlabeled[unlabeled["Confidence"] >= conf_threshold].drop(columns=["Confidence"])

    # Combined
    parts = []
    if not labeled.empty:
        parts.append(labeled.copy())
    unlabeled = get_unlabeled(df, labeled)
    if not unlabeled.empty and model_exists(MODEL_PATH):
        labels, scores = predict(unlabeled, MODEL_PATH)
        unlabeled = unlabeled.copy()
        unlabeled["Category"] = labels
        unlabeled["Confidence"] = scores
        predicted = unlabeled[unlabeled["Confidence"] >= conf_threshold].drop(columns=["Confidence"])
        parts.append(predicted)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def get_unlabeled(df: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    if labeled.empty:
        return df.copy()
    keys = set(zip(labeled["Date"], labeled["Vendor"], labeled["Amount"]))
    mask = df.apply(lambda r: (r["Date"], r["Vendor"], r["Amount"]) not in keys, axis=1)
    return df[mask].reset_index(drop=True)


# ── page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Personal Finance", layout="wide", page_icon="💰")
st.title("Personal Finance Manager")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Upload & Process", "Review", "Label", "Predict", "Visualise"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Upload & Process
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.header("Upload Bank Statements")
    st.caption("Upload one or more monthly PDF bank statements to parse and store them.")

    uploaded_files = st.file_uploader(
        "Select PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.subheader("Assign months")
        file_configs = []
        for f in uploaded_files:
            col_name, col_month, col_year = st.columns([3, 2, 2])
            with col_name:
                st.markdown(f"**{f.name}**")
            with col_month:
                month = st.selectbox("Month", MONTHS, key=f"month_{f.name}")
            with col_year:
                year = st.number_input("Year", min_value=2020, max_value=2030,
                                       value=2025, key=f"year_{f.name}")
            file_configs.append((f, month, int(year)))

        if st.button("Process PDFs", type="primary"):
            from parsers.pdf_parser import get_master_lists, clean_desc_robust, save_to_db
            from preprocessing.preprocessor import run_preprocessing

            progress_bar = st.progress(0)
            status = st.empty()
            total_new = 0
            errors = []

            for idx, (f, month, year) in enumerate(file_configs):
                status.info(f"Parsing {f.name} …")
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(f.read())
                        tmp_path = tmp.name

                    desc_list, amount_list = get_master_lists(tmp_path)

                    # Strip trailing summary rows (balance, credit total, debit total)
                    if len(amount_list) >= 3 and len(desc_list) >= 3:
                        for _ in range(3):
                            amount_list.pop()
                            desc_list.pop()

                    df_parsed = clean_desc_robust(desc_list, amount_list)
                    month_label = f"{year}-{MONTH_MAP[month]}"
                    save_to_db(df_parsed, month_label=month_label, db_path=str(DB_PATH))
                    total_new += len(df_parsed)
                except Exception as e:
                    errors.append(f"{f.name}: {e}")

                progress_bar.progress((idx + 1) / len(file_configs))

            status.info("Running preprocessor …")
            try:
                run_preprocessing(db_path=DB_PATH)
                status.empty()
                if errors:
                    for err in errors:
                        st.error(err)
                st.success(f"Done — {total_new} transactions added. CSV updated.")
            except Exception as e:
                st.error(f"Preprocessor failed: {e}")

    # Show current DB stats
    df_current = load_transactions()
    if not df_current.empty:
        st.divider()
        st.caption(f"Current dataset: **{len(df_current)}** transactions "
                   f"({df_current['Date'].min()} – {df_current['Date'].max()})")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Review
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    df = load_transactions()

    if df.empty:
        st.info("No transaction data found. Upload PDF statements in the first tab.")
    else:
        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Transactions", f"{len(df):,}")
        c2.metric("Total Debits", f"RM {df['Debit_amt'].sum():,.2f}")
        c3.metric("Total Credits", f"RM {df['Credit_amt'].sum():,.2f}")
        c4.metric("Period", f"{df['Date'].min()} – {df['Date'].max()}")

        st.divider()

        # Filters
        with st.expander("Filters", expanded=False):
            fc1, fc2, fc3, fc4, fc5 = st.columns([2, 2, 2, 1, 1])
            with fc1:
                months_opts = ["All"] + sorted(df["Date"].unique().tolist())
                sel_month = st.selectbox("Month", months_opts)
            with fc2:
                type_opts = ["All"] + sorted(df["Sale Type"].unique().tolist())
                sel_type = st.selectbox("Sale Type", type_opts)
            with fc3:
                vendor_q = st.text_input("Search vendor")
            with fc4:
                min_amt = st.number_input("Min amount", min_value=0.0, value=0.0, step=1.0)
            with fc5:
                max_amt = st.number_input("Max amount", min_value=0.0, value=0.0, step=1.0,
                                          help="0 = no upper limit")

        filtered = df.copy()
        if sel_month != "All":
            filtered = filtered[filtered["Date"] == sel_month]
        if sel_type != "All":
            filtered = filtered[filtered["Sale Type"] == sel_type]
        if vendor_q:
            filtered = filtered[filtered["Vendor"].str.contains(vendor_q, case=False, na=False)]
        if min_amt > 0:
            filtered = filtered[filtered["Debit_amt"] >= min_amt]
        if max_amt > 0:
            filtered = filtered[filtered["Debit_amt"] <= max_amt]

        st.dataframe(
            filtered[["Date", "Vendor", "Details", "Location", "Sale Type",
                       "Debit_amt", "Credit_amt"]].rename(columns={
                "Debit_amt": "Debit (RM)", "Credit_amt": "Credit (RM)"}),
            width="stretch",
            hide_index=True,
        )
        st.caption(f"Showing {len(filtered):,} of {len(df):,} transactions")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Label
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    df = load_transactions()
    labeled_df = load_labeled()

    if df.empty:
        st.info("No transaction data found. Upload PDF statements in the first tab.")
    else:
        unlabeled = get_unlabeled(df, labeled_df)
        total = len(df)
        labeled_count = total - len(unlabeled)

        # Progress
        pct = labeled_count / total if total else 0
        st.progress(pct, text=f"{labeled_count} of {total} labeled  ({pct*100:.0f}%)")

        if unlabeled.empty:
            st.success("All transactions have been labeled!")
        else:
            mode = st.radio("Labeling mode", ["One by one", "Bulk by vendor"],
                            horizontal=True)
            st.divider()

            # ── One by one ────────────────────────────────────────────────────
            if mode == "One by one":
                if "label_idx" not in st.session_state:
                    st.session_state.label_idx = 0
                idx = min(st.session_state.label_idx, len(unlabeled) - 1)
                row = unlabeled.iloc[idx]

                left, right = st.columns([1, 1])

                with left:
                    st.markdown(f"**{idx + 1} of {len(unlabeled)} remaining**")
                    st.markdown("---")
                    st.markdown(f"**Vendor** &nbsp;&nbsp; {row['Vendor']}")
                    amount_str = (f"RM {row['Debit_amt']:.2f} (debit)"
                                  if row['Debit_amt'] > 0
                                  else f"RM {row['Credit_amt']:.2f} (credit)")
                    st.markdown(f"**Amount** &nbsp;&nbsp; {amount_str}")
                    st.markdown(f"**Date** &nbsp;&nbsp; {row['Date']}")
                    st.markdown(f"**Details** &nbsp;&nbsp; {row['Details']}")
                    st.markdown(f"**Location** &nbsp;&nbsp; {row['Location']}")
                    st.markdown(f"**Type** &nbsp;&nbsp; {row['Sale Type']}")

                with right:
                    selected_cat = st.radio("Assign category", CATEGORIES,
                                            key=f"cat_{idx}")
                    st.markdown("")
                    btn_save, btn_skip, btn_back = st.columns(3)
                    with btn_save:
                        if st.button("Save & Next", type="primary", width="stretch"):
                            new_row = row.to_dict()
                            new_row["Category"] = selected_cat
                            labeled_df = pd.concat(
                                [labeled_df, pd.DataFrame([new_row])], ignore_index=True)
                            save_labeled(labeled_df)
                            st.session_state.label_idx = idx + 1
                            st.rerun()
                    with btn_skip:
                        if st.button("Skip", width="stretch"):
                            st.session_state.label_idx = idx + 1
                            st.rerun()
                    with btn_back:
                        if st.button("Back", width="stretch", disabled=idx == 0):
                            st.session_state.label_idx = max(0, idx - 1)
                            st.rerun()

            # ── Bulk by vendor ────────────────────────────────────────────────
            else:
                vendor_counts = unlabeled["Vendor"].value_counts()
                sel_vendor = st.selectbox(
                    "Select vendor",
                    vendor_counts.index.tolist(),
                    format_func=lambda v: f"{v}  ({vendor_counts[v]} transactions)",
                )

                vendor_rows = unlabeled[unlabeled["Vendor"] == sel_vendor]
                st.dataframe(
                    vendor_rows[["Date", "Debit_amt", "Credit_amt", "Details",
                                 "Location"]].rename(columns={
                        "Debit_amt": "Debit (RM)", "Credit_amt": "Credit (RM)"}),
                    width="stretch",
                    hide_index=True,
                )

                bulk_cat = st.selectbox("Category", CATEGORIES, key="bulk_cat")

                if st.button(f"Label all {len(vendor_rows)} '{sel_vendor}' transactions",
                             type="primary"):
                    new_rows = vendor_rows.copy()
                    new_rows["Category"] = bulk_cat
                    labeled_df = pd.concat([labeled_df, new_rows], ignore_index=True)
                    save_labeled(labeled_df)
                    st.success(f"Labeled {len(new_rows)} transactions as '{bulk_cat}'")
                    st.rerun()

        # ── Labeled data viewer ───────────────────────────────────────────────
        if not labeled_df.empty:
            st.divider()
            with st.expander(f"View labeled transactions ({len(labeled_df)})"):
                st.dataframe(
                    labeled_df[["Date", "Vendor", "Debit_amt", "Credit_amt",
                                "Category"]].rename(columns={
                        "Debit_amt": "Debit (RM)", "Credit_amt": "Credit (RM)"}),
                    width="stretch",
                    hide_index=True,
                )
                st.download_button(
                    "Download labeled.csv",
                    data=labeled_df.to_csv(index=False),
                    file_name="labeled.csv",
                    mime="text/csv",
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Predict
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    from ml.trainer import train, predict, model_exists, MODEL_PATH, CATEGORIES as ML_CATEGORIES

    df = load_transactions()
    labeled_df = load_labeled()

    if df.empty:
        st.info("No transaction data found. Upload PDF statements in the first tab.")
    else:
        # ── Train section ─────────────────────────────────────────────────────
        st.subheader("Model Training")

        valid_labeled = (
            labeled_df[labeled_df["Category"].isin(ML_CATEGORIES)]
            if not labeled_df.empty else pd.DataFrame()
        )
        n_valid = len(valid_labeled)
        n_classes = valid_labeled["Category"].nunique() if n_valid else 0

        col_status, col_train = st.columns([2, 1])
        with col_status:
            if model_exists():
                st.success(f"Model trained on **{n_valid}** samples across **{n_classes}** categories.")
            else:
                st.warning("No trained model found. Train one below.")
            st.caption(f"Valid labeled samples available: {n_valid}")

        with col_train:
            if st.button("Train / Retrain Model", type="primary", disabled=n_valid < 10):
                with st.spinner("Training …"):
                    try:
                        metrics = train()
                        acc = metrics["cv_accuracy"]
                        f1 = metrics["cv_f1_weighted"]
                        acc_str = f"{acc*100:.1f}%" if acc is not None else "N/A"
                        f1_str = f"{f1*100:.1f}%" if f1 is not None else "N/A"
                        st.success(
                            f"Trained on {metrics['n_samples']} samples — "
                            f"CV accuracy: {acc_str}  |  F1: {f1_str} "
                            f"({metrics['n_splits']}-fold)"
                        )
                        with st.expander("Class distribution"):
                            st.dataframe(
                                pd.DataFrame.from_dict(
                                    metrics["class_counts"], orient="index",
                                    columns=["count"]
                                ).sort_values("count", ascending=False),
                                width="stretch",
                            )
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        if n_valid < 10:
            st.caption("Need at least 10 labeled samples to train. Label more data in the Label tab.")

        st.divider()

        # ── Prediction section ────────────────────────────────────────────────
        st.subheader("Predictions")

        if not model_exists():
            st.info("Train the model above to see predictions.")
        else:
            unlabeled = get_unlabeled(df, labeled_df)

            if unlabeled.empty:
                st.success("All transactions are already labeled — nothing to predict.")
            else:
                conf_threshold = st.slider(
                    "Confidence threshold", min_value=0.0, max_value=1.0,
                    value=0.5, step=0.05,
                    help="Only show predictions at or above this confidence level.",
                )

                with st.spinner("Running predictions …"):
                    labels, confidence = predict(unlabeled)

                results = unlabeled.copy()
                results["Predicted Category"] = labels
                results["Confidence"] = confidence.round(3)

                high_conf = results[results["Confidence"] >= conf_threshold]
                low_conf = results[results["Confidence"] < conf_threshold]

                st.caption(
                    f"{len(high_conf)} predictions at ≥{conf_threshold:.0%} confidence  |  "
                    f"{len(low_conf)} below threshold"
                )

                if not high_conf.empty:
                    display_cols = ["Date", "Vendor", "Debit_amt", "Credit_amt",
                                    "Details", "Predicted Category", "Confidence"]
                    st.dataframe(
                        high_conf[display_cols].rename(columns={
                            "Debit_amt": "Debit (RM)", "Credit_amt": "Credit (RM)"}),
                        width="stretch",
                        hide_index=True,
                    )

                    if st.button(
                        f"Accept {len(high_conf)} predictions as labels",
                        type="primary",
                        disabled=high_conf.empty,
                    ):
                        accepted = high_conf.copy()
                        accepted["Category"] = accepted["Predicted Category"]
                        accepted = accepted.drop(columns=["Predicted Category", "Confidence"])
                        labeled_df = pd.concat([labeled_df, accepted], ignore_index=True)
                        save_labeled(labeled_df)
                        st.success(f"Saved {len(accepted)} predicted labels to labeled.csv.")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Visualise
# ══════════════════════════════════════════════════════════════════════════════

with tab5:
    from ml.trainer import model_exists, MODEL_PATH

    st.header("Spending Visualisation")

    has_model = model_exists(MODEL_PATH)

    # ── Controls ──────────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3 = st.columns([2, 3, 2])

    with ctrl1:
        mode_options = ["Labeled only"]
        if has_model:
            mode_options += ["Predicted only", "Combined"]
        view_mode = st.radio("Data source", mode_options, horizontal=False)
        if not has_model and len(mode_options) == 1:
            st.caption("Train a model in the Predict tab to enable predicted/combined views.")

    with ctrl3:
        conf_threshold = 0.5
        if view_mode != "Labeled only" and has_model:
            conf_threshold = st.slider(
                "Confidence threshold",
                min_value=0.0, max_value=1.0, value=0.5, step=0.05,
                help="Exclude predictions below this confidence level.",
            )

    # Build the working dataframe
    try:
        working_df = build_viz_df(view_mode, conf_threshold)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        working_df = load_labeled()
        if not working_df.empty:
            st.caption("Falling back to labeled-only data.")

    if working_df.empty:
        st.info("No categorised transactions to visualise. Label some data in the Label tab or train and run predictions.")
        st.stop()

    with ctrl2:
        month_options = sorted(working_df["Date"].unique().tolist())
        sel_months = st.multiselect("Filter by month", month_options,
                                    placeholder="All months")

    # Apply month filter
    if sel_months:
        filtered_df = working_df[working_df["Date"].isin(sel_months)].copy()
    else:
        filtered_df = working_df.copy()

    if filtered_df.empty:
        st.info("No transactions for selected filters.")
        st.stop()

    # ── Metric cards ──────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    total_spend = filtered_df["Debit_amt"].sum()
    total_income = filtered_df["Credit_amt"].sum()
    m1.metric("Transactions", f"{len(filtered_df):,}")
    m2.metric("Total Spending", f"RM {total_spend:,.2f}")
    m3.metric("Total Income", f"RM {total_income:,.2f}")
    m4.metric("Net", f"RM {total_income - total_spend:,.2f}")

    st.divider()

    # ── Charts row ────────────────────────────────────────────────────────────
    debits_df = filtered_df[filtered_df["Debit_amt"] > 0].copy()

    chart_left, chart_right = st.columns([3, 2])

    with chart_left:
        st.subheader("Spending by Category")
        if debits_df.empty:
            st.caption("No debit transactions found in the selected data.")
        else:
            cat_totals = (
                debits_df.groupby("Category", as_index=False)["Debit_amt"].sum()
                .sort_values("Debit_amt", ascending=False)
            )
            bar = (
                alt.Chart(cat_totals)
                .mark_bar()
                .encode(
                    x=alt.X("Debit_amt:Q", title="Total Spending (RM)"),
                    y=alt.Y("Category:N", sort="-x"),
                    color=alt.Color("Category:N", legend=None),
                    tooltip=["Category", alt.Tooltip("Debit_amt:Q", format=",.2f", title="RM")],
                )
                .properties(height=max(200, len(cat_totals) * 30))
            )
            st.altair_chart(bar, use_container_width=True)

    with chart_right:
        st.subheader("Category Breakdown")
        if debits_df.empty:
            st.caption("No debit transactions found in the selected data.")
        else:
            cat_totals_donut = (
                debits_df.groupby("Category", as_index=False)["Debit_amt"].sum()
                .sort_values("Debit_amt", ascending=False)
            )
            if len(cat_totals_donut) > 10:
                top10 = cat_totals_donut.iloc[:10].copy()
                other_sum = cat_totals_donut.iloc[10:]["Debit_amt"].sum()
                top10 = pd.concat(
                    [top10, pd.DataFrame([{"Category": "Other", "Debit_amt": other_sum}])],
                    ignore_index=True,
                )
            else:
                top10 = cat_totals_donut.copy()

            donut = (
                alt.Chart(top10)
                .mark_arc(innerRadius=60)
                .encode(
                    theta="Debit_amt:Q",
                    color="Category:N",
                    tooltip=["Category", alt.Tooltip("Debit_amt:Q", format=",.2f", title="RM")],
                )
            )
            st.altair_chart(donut, use_container_width=True)

    st.divider()

    # ── Monthly Trend ─────────────────────────────────────────────────────────
    st.subheader("Monthly Trend")
    n_months = filtered_df["Date"].nunique()
    if n_months < 2:
        st.info("Select at least 2 months to see the trend chart.")
    elif debits_df.empty:
        st.caption("No debit transactions to plot a trend.")
    else:
        monthly = (
            debits_df.groupby(["Date", "Category"], as_index=False)["Debit_amt"].sum()
        )
        line = (
            alt.Chart(monthly)
            .mark_line(point=True)
            .encode(
                x=alt.X("Date:O", title="Month"),
                y=alt.Y("Debit_amt:Q", title="Spending (RM)"),
                color="Category:N",
                tooltip=["Date", "Category", alt.Tooltip("Debit_amt:Q", format=",.2f", title="RM")],
            )
            .properties(height=350)
        )
        st.altair_chart(line, use_container_width=True)

    st.divider()

    # ── Raw data expander ─────────────────────────────────────────────────────
    with st.expander(f"Raw data ({len(filtered_df):,} transactions)"):
        display_cols = ["Date", "Vendor", "Debit_amt", "Credit_amt", "Category"]
        st.dataframe(
            filtered_df[display_cols].rename(columns={
                "Debit_amt": "Debit (RM)", "Credit_amt": "Credit (RM)"}),
            width="stretch",
            hide_index=True,
        )
