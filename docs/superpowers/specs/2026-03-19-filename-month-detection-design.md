# Filename-Based Month Detection for Bank Statement Upload

**Date:** 2026-03-19
**Status:** Approved

## Overview

Replace the manual month/year selectors in the Upload & Process tab with automatic parsing from the uploaded PDF filename. Users name their files with a 3-letter month abbreviation and a 4-digit year; the app detects both and proceeds — or blocks with a clear error if either is missing.

---

## Parsing Logic

A helper function `parse_month_label(filename: str) -> tuple[str | None, str | None]` added to `app.py`:

1. Extract the filename stem using `pathlib.Path(filename).stem` — this strips any extension case-insensitively (handles `.pdf`, `.PDF`, etc.)
2. Scan for any 3-letter month abbreviation from `MONTHS` (`Jan`–`Dec`) using a **case-insensitive substring scan**: `month.lower() in stem.lower()` for each `month` in `MONTHS`, iterating in list order. Resolution is by **position in the `MONTHS` list**, not by position of the substring in the filename — `"Jan"` always beats `"Mar"` regardless of which appears first in the stem. The first list-order match wins silently; no warning is shown to the user.
3. Scan for a standalone 4-digit year using regex `(?<!\d)(\d{4})(?!\d)`. The lookbehind `(?<!\d)` and lookahead `(?!\d)` prevent matching 4-digit runs inside longer digit strings (e.g. `20251234` does not yield `2025` because `1` immediately follows). Collect all matches, filter to the range 2020–2030 **inclusive on both ends**, and take the first match.
4. If both found → return `("YYYY-MM", None)` where `MM` is zero-padded via `MONTH_MAP`
5. If either or both missing → collect all applicable error strings, join with `" "` (one space, no additional separator), and return `(None, "<combined error string>")`

**Examples:**
- `Jan2025.pdf` → `("2025-01", None)`
- `statement_Mar_2025.pdf` → `("2025-03", None)`
- `eStatement_February_2025.pdf` → `("2025-02", None)` — `"Feb"` matched as substring of `"February"`
- `March2025.pdf` → `("2025-03", None)` — `"Mar"` matched as substring of `"March"`
- `JanMar2025.pdf` → `("2025-01", None)` — `"Jan"` wins (position 0 in `MONTHS`, before `"Mar"` at position 2)
- `Mar2025Jan_ref.pdf` → `("2025-01", None)` — `"Jan"` still wins (position 0 in `MONTHS`), even though `"Mar"` appears first in the filename
- `doc_98271.pdf` → `(None, "Could not detect a month in filename. Rename to include e.g. 'Jan', 'Feb', etc. Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'.")`
- `ref_20251234.pdf` → `(None, "Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'.")` — `2025` is immediately followed by `1` (a digit), so the lookahead blocks the match

---

## Data Flow

The existing `file_configs: list[tuple[file, str, int]]` (file, month, year) is replaced by:

```python
parsed: list[tuple[file, str | None, str | None]]  # (file, month_label, error)
```

Built as:
```python
parsed = [(f, *parse_month_label(f.name)) for f in uploaded_files]
all_ok = all(label is not None for _, label, _ in parsed)
```

The processing loop replaces `for idx, (f, month, year) in enumerate(file_configs)` with `for f, month_label, _ in parsed`, using `month_label` directly in place of the constructed `f"{year}-{MONTH_MAP[month]}"` string.

---

## UI Changes (Tab 1 — Upload & Process)

### Preserved (unchanged)
- `st.header("Upload Bank Statements")`
- `st.caption("Upload one or more monthly PDF bank statements to parse and store them.")`
- The `st.file_uploader` widget itself

### Removed (from inside `if uploaded_files:`)
- `st.subheader("Assign months")`
- The `st.columns([3, 2, 2])` loop with month selectbox and year number_input per file
- The `file_configs` list construction

### Added (inside `if uploaded_files:`)

1. **Naming hint** — `st.info` at the top:
   > `"Name your files with a 3-letter month and 4-digit year, e.g. Jan2025.pdf or statement_Mar_2025.pdf"`

2. **Results rows** — one row per file using `st.columns([3, 2])`:
   - Column 1: `st.markdown(f"**{f.name}**")`
   - Column 2: `col.success("2025-01 ✓")` on success, or `col.error("<error message> ✗")` on failure. ✓ = U+2713, ✗ = U+2717.

3. **Process PDFs button** — `st.button("Process PDFs", type="primary", disabled=not all_ok)`. Disabled (`disabled=True`) when one or more files failed parsing; enabled (`disabled=False`) when all files parsed successfully. The per-row error display is sufficient user feedback — no additional summary above the button is added.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| No month abbreviation found | Error string: `"Could not detect a month in filename. Rename to include e.g. 'Jan', 'Feb', etc."` |
| No valid year found | Error string: `"Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'."` |
| Both missing | Both strings joined with one space `" "` — no newline, bullet, or dash — rendered as a single `col.error(...)` call |
| Duplicate month (already in DB) | Existing behaviour: post-processing `st.warning(f"{month_label} already exists in the database — skipped.")` |
| Two files resolve to same month | Allowed at parse time; second file hits existing duplicate guard in `pgdb.save_transactions` |

**Session state:** `parse_month_label` is called fresh on every render. No session state is introduced — re-uploading files automatically re-evaluates all rows.

---

## What Is Not Changed

- `parsers/pdf_parser.py` — no changes
- `preprocessing/preprocessor.py` — no changes
- `db/postgres.py` — no changes
- `ml/trainer.py` — no changes
- The `month_label` format (`"YYYY-MM"`) passed to `pgdb.save_transactions` — unchanged
- Duplicate month detection logic in `pgdb.save_transactions` — unchanged

---

## Scope

This change is limited to the Upload & Process tab in `app.py`. Approximately:
- Add `parse_month_label()` helper (~15 lines)
- Replace the per-file month/year input block and `file_configs` construction with the `parsed` list and results display (~25 lines changed)
- Add the naming hint callout (~3 lines)
