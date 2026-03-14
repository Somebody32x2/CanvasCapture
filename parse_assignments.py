from pathlib import Path
from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from log import log



def parse_canvas_date(raw: str | None, field: str) -> str | None:
    """Parse a Canvas date string flexibly. Returns ISO 8601 string or None.
    Raises ValueError with a descriptive message if parsing fails."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        dt = dateutil_parser.parse(text, default=dateutil_parser.parse("Jan 1 2026"))
        return dt.isoformat()
    except (ParserError, ValueError) as e:
        raise ValueError(f"Could not parse {field} date '{text}': {e}") from e


def parse_score(row) -> dict:
    """Extract score and max_points from a .js-score element."""
    score_el = row.query_selector(".js-score .score-display")
    if not score_el:
        return {"score": None, "max_points": None}
    text = score_el.inner_text().strip()
    # Formats: "100/100 pts", "-/10 pts", "50/100 pts", "-/10 pts | Not Yet Graded"
    # Strip any grade-display suffix (e.g. "| Not Yet Graded")
    text = text.split("|")[0].strip()
    parts = text.replace(" pts", "").split("/")
    if len(parts) == 2:
        raw_score, raw_max = parts[0].strip(), parts[1].strip()
        score = None if raw_score == "-" else (float(raw_score) if "." in raw_score else int(raw_score))
        try:
            max_points = float(raw_max) if "." in raw_max else int(raw_max)
        except ValueError:
            max_points = None
        return {"score": score, "max_points": max_points}
    return {"score": None, "max_points": None}


def parse_assignment_row(row) -> dict | None:
    """Parse a single assignment row. Returns None and logs on error."""
    assignment_id = row.get_attribute("data-item-id")
    try:
        # Title
        title_el = row.query_selector(".ig-title")
        title = title_el.inner_text().strip() if title_el else None

        # Due date - prefer the tooltip attribute, fall back to inner text
        due_el = row.query_selector(".assignment-date-due [data-html-tooltip-title]")
        if due_el:
            due_raw = due_el.get_attribute("data-html-tooltip-title")
        else:
            due_span = row.query_selector(".assignment-date-due span:not(.screenreader-only)")
            due_raw = due_span.inner_text().strip() if due_span else None
        due_date = parse_canvas_date(due_raw, "due")

        # Open/close date derived from "Not available until" / "Available until" / "Closed"
        avail_el = row.query_selector(".assignment-date-available [data-html-tooltip-title]")
        if avail_el:
            avail_raw = avail_el.get_attribute("data-html-tooltip-title")
        else:
            avail_span = row.query_selector(".assignment-date-available span:not(.screenreader-only):not(.status-description)")
            avail_raw = avail_span.inner_text().strip() if avail_span else None

        status_el = row.query_selector(".assignment-date-available .status-description")
        avail_label = status_el.inner_text().strip().lower() if status_el else None

        # "Closed" means the close date has passed - no date is shown
        if avail_label == "closed":
            open_date = None
            close_date = None
            closed = True
        else:
            avail_date = parse_canvas_date(avail_raw, "available")
            closed = False
            if avail_label == "not available until":
                open_date = avail_date
                close_date = None
            elif avail_label == "available until":
                open_date = None
                close_date = avail_date
            else:
                open_date = None
                close_date = None

        score_info = parse_score(row)

        return {
            "id": assignment_id,
            "title": title,
            "due_date": due_date,
            "open_date": open_date,
            "close_date": close_date,
            "closed": closed,
            "score": score_info["score"],
            "max_points": score_info["max_points"],
        }

    except Exception as e:
        log(f"[ERROR] Failed to parse assignment id={assignment_id!r}: {e}")
        return None
