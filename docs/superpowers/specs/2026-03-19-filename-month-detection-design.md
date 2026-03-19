# Filename-Based Month Detection for Bank Statement Upload

**Date:** 2026-03-19
**Status:** Approved

## Overview

Replace the manual month/year selectors in the Upload & Process tab with automatic parsing from the uploaded PDF filename. Users name their files with a 3-letter month abbreviation and a 4-digit year; the app detects both and proceeds — or blocks with a clear error if either is missing.

---

## Parsing Logic

A helper function `parse_month_label(filename: str) -> tuple[str | None, str | None]` added to `app.py`:

1. Strip the `.pdf` extension, work on the filename stem
2. Scan case-insensitively for any 3-letter month abbreviation from `MONTHS` (`Jan`–`Dec`)
3. Scan for a 4-digit year (`\d{4}`) in the range 2020–2030
4. If both found → return `("YYYY-MM", None)`
5. If either or both missing → return `(None, "<reason string>")`

**Ambiguity rule:** if multiple months or years appear in the filename, take the first match of each.

**Examples:**
- `Jan2025.pdf` → `("2025-01", None)`
- `statement_Mar_2025.pdf` → `("2025-03", None)`
- `eStatement_February_2025.pdf` → `("2025-02", None)` _(Feb matched)_
- `doc_98271.pdf` → `(None, "No month found. No valid year found.")`
- `March2025.pdf` → `(None, "No month found...")` _(full word, not 3-letter)_ — user must rename

---

## UI Changes (Tab 1 — Upload & Process)

### Removed
- Month selectbox per file
- Year number_input per file
- "Assign months" subheader

### Added

1. **Naming hint** — persistent `st.info` shown whenever files are uploaded:
   > _"Name your files with a 3-letter month and 4-digit year, e.g. `Jan2025.pdf` or `statement_Mar_2025.pdf`"_

2. **Results table** — one row per file with columns:
   - **File** — filename
   - **Detected** — resolved label (e.g. `2025-01`) with ✓, or error message with ✗

3. **Process PDFs button** — disabled if any file has a parse error; only active when all files resolve cleanly

---

## Error Handling

| Condition | Error Message |
|---|---|
| No month abbreviation found | `"Could not detect a month in filename. Rename to include e.g. 'Jan', 'Feb', etc."` |
| No valid year found | `"Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'."` |
| Both missing | Both reasons combined in one message |
| Duplicate month (already in DB) | Existing behaviour: `"{month_label} already exists in the database — skipped."` (post-processing warning) |
| Two files resolve to same month | Allowed at parse time; second file hits existing duplicate guard in `pgdb.save_transactions` |

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
- Replace the per-file month/year input block with the results display (~20 lines changed)
- Add the naming hint callout (~3 lines)
