import re
from pathlib import Path

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_MAP = {m: f"{i+1:02d}" for i, m in enumerate(MONTHS)}


def parse_month_label(filename: str) -> tuple[str | None, str | None]:
    """Parse a YYYY-MM label from a filename.

    Returns (month_label, None) on success, (None, error_string) on failure.
    Month: case-insensitive substring scan of MONTHS in list order; first match wins.
    Year: standalone 4-digit number (not adjacent to other digits), range 2020-2030 inclusive.
    """
    stem = Path(filename).stem
    stem_lower = stem.lower()

    matched_month = None
    for month in MONTHS:
        if month.lower() in stem_lower:
            matched_month = month
            break

    year_matches = re.findall(r"(?<!\d)(\d{4})(?!\d)", stem)
    matched_year = next((y for y in year_matches if 2020 <= int(y) <= 2030), None)

    errors = []
    if matched_month is None:
        errors.append(
            "Could not detect a month in filename. Rename to include e.g. 'Jan', 'Feb', etc."
        )
    if matched_year is None:
        errors.append(
            "Could not detect a year in filename. Rename to include a 4-digit year e.g. '2025'."
        )

    if errors:
        return None, " ".join(errors)
    return f"{matched_year}-{MONTH_MAP[matched_month]}", None
