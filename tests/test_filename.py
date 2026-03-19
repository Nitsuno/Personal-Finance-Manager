from utils.filename import parse_month_label


# ── Happy path ────────────────────────────────────────────────────────────────

def test_simple_month_and_year():
    assert parse_month_label("Jan2025.pdf") == ("2025-01", None)

def test_month_and_year_with_separators():
    assert parse_month_label("statement_Mar_2025.pdf") == ("2025-03", None)

def test_month_embedded_in_longer_word():
    # "Feb" is a substring of "February"
    assert parse_month_label("eStatement_February_2025.pdf") == ("2025-02", None)

def test_month_as_start_of_longer_word():
    # "Mar" is a substring of "March"
    assert parse_month_label("March2025.pdf") == ("2025-03", None)

def test_uppercase_extension_stripped():
    assert parse_month_label("Jan2025.PDF") == ("2025-01", None)

def test_case_insensitive_month():
    assert parse_month_label("jan2025.pdf") == ("2025-01", None)

def test_year_at_range_boundary_low():
    assert parse_month_label("Jan2020.pdf") == ("2020-01", None)

def test_year_at_range_boundary_high():
    assert parse_month_label("Jan2030.pdf") == ("2030-01", None)

def test_december():
    assert parse_month_label("Dec2024.pdf") == ("2024-12", None)


# ── Ambiguity resolution ───────────────────────────────────────────────────────

def test_multiple_months_first_in_months_list_wins():
    # "Jan" (index 0) beats "Mar" (index 2) regardless of filename order
    assert parse_month_label("JanMar2025.pdf") == ("2025-01", None)

def test_multiple_months_list_order_wins_even_if_later_in_filename():
    # "Mar" appears first in stem but "Jan" is earlier in MONTHS
    assert parse_month_label("Mar2025Jan_ref.pdf") == ("2025-01", None)

def test_multiple_years_first_match_wins():
    # Two standalone years — first one (left-to-right) wins
    assert parse_month_label("Jan2024_copy2025.pdf") == ("2024-01", None)


# ── Year regex edge cases ──────────────────────────────────────────────────────

def test_year_inside_long_digit_run_not_matched():
    # "20251234" — 2025 immediately followed by 1 (digit), lookahead blocks match
    assert parse_month_label("ref_Jan20251234.pdf") == (
        None,
        "Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'.",
    )

def test_year_below_range_not_matched():
    assert parse_month_label("Jan2019.pdf") == (
        None,
        "Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'.",
    )

def test_year_above_range_not_matched():
    assert parse_month_label("Jan2031.pdf") == (
        None,
        "Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'.",
    )


# ── Error cases ────────────────────────────────────────────────────────────────

def test_no_month_found():
    label, err = parse_month_label("statement_2025.pdf")
    assert label is None
    assert "Could not detect a month" in err

def test_no_year_found():
    label, err = parse_month_label("Jan_statement.pdf")
    assert label is None
    assert "Could not detect a year" in err

def test_both_missing():
    label, err = parse_month_label("doc_98271.pdf")
    assert label is None
    assert "Could not detect a month" in err
    assert "Could not detect a year" in err

def test_both_missing_joined_with_space_not_newline():
    label, err = parse_month_label("doc_98271.pdf")
    assert "\n" not in err
    assert "etc. Could" in err  # confirms single-space separator between the two messages
    # Month error must come before year error
    assert err.index("Could not detect a month") < err.index("Could not detect a year")
