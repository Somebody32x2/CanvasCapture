"""
Notification event keys and human-readable labels for assignment changes.
Each entry maps a machine-readable key to a label template.
Placeholders are fully qualified assignment prop names prefixed with old_ or new_,
e.g. {old_title}, {new_title}, {old_score}, {new_due_date}, etc.
e.g. {old_title}, {new_title}, {old_score}, {new_due_date}, etc.
"""

# --- Event keys ---

NEW_ASSIGNMENT = "new_assignment"
ASSIGNMENT_REMOVED = "assignment_removed"

TITLE_CHANGED = "title_changed"

SCORE_ADDED = "score_added"
SCORE_CHANGED = "score_changed"
MAX_POINTS_CHANGED = "max_points_changed"

DUE_DATE_CHANGED = "due_date_changed"
DUE_DATE_ADDED = "due_date_added"
DUE_DATE_REMOVED = "due_date_removed"

OPEN_DATE_CHANGED = "open_date_changed"
OPEN_DATE_ADDED = "open_date_added"
OPEN_DATE_REMOVED = "open_date_removed"

CLOSE_DATE_CHANGED = "close_date_changed"
CLOSE_DATE_ADDED = "close_date_added"
CLOSE_DATE_REMOVED = "close_date_removed"

ASSIGNMENT_OPENED = "assignment_opened"  # was "not available until", now past/gone
ASSIGNMENT_CLOSED = "assignment_closed"  # now past close_date

# --- Human-readable labels ---

LABELS: dict[str, str] = {
    NEW_ASSIGNMENT: "New assignment: {new_title}",
    ASSIGNMENT_REMOVED: "Assignment removed: {old_title}",

    TITLE_CHANGED: '"{old_title}" was renamed to "{new_title}"',

    SCORE_ADDED: "{new_title}: graded — {new_score} / {new_max_points}",
    SCORE_CHANGED: "{new_title}: score changed from {old_score} to {new_score}",
    MAX_POINTS_CHANGED: "{new_title}: max points changed from {old_max_points} to {new_max_points}",

    DUE_DATE_CHANGED: "{new_title}: due date changed from {old_due_date} to {new_due_date}",
    DUE_DATE_ADDED: "{new_title}: due date set to {new_due_date}",
    DUE_DATE_REMOVED: "{old_title}: due date removed",

    OPEN_DATE_CHANGED: "{new_title}: open date changed from {old_open_date} to {new_open_date}",
    OPEN_DATE_ADDED: "{new_title}: open date set to {new_open_date}",
    OPEN_DATE_REMOVED: "{old_title}: open date removed",

    CLOSE_DATE_CHANGED: "{new_title}: close date changed from {old_close_date} to {new_close_date}",
    CLOSE_DATE_ADDED: "{new_title}: close date set to {new_close_date}",
    CLOSE_DATE_REMOVED: "{old_title}: close date removed",

    ASSIGNMENT_OPENED: "{new_title} is now open",
    ASSIGNMENT_CLOSED: "{new_title} is now closed",
}


def format_notification(key: str, **kwargs) -> str:
    """Return a formatted notification string for the given event key."""
    template = LABELS.get(key)
    if template is None:
        raise KeyError(f"Unknown notification key: '{key}'")
    return template.format_map(kwargs)
