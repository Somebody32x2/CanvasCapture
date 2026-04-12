"""
Notification event keys and human-readable labels.
Each entry maps a machine-readable key to a label template.
Placeholders are fully qualified prop names prefixed with old_ or new_,
e.g. {old_title}, {new_title}, {old_score}, {new_due_date}, etc.
"""

LABELS: dict[str, dict[str, str]] = {
        "assignments": {
            "new_assignment": "New assignment: {new_title}",
            "assignment_removed": "Assignment removed: {old_title}",

            "title_changed": '"{old_title}" was renamed to "{new_title}"',

            "score_added": "{new_title}: graded - {new_score} / {new_max_points}",
            "score_changed": "{new_title}: score changed from {old_score} to {new_score}",
            "max_points_changed": "{new_title}: max points changed from {old_max_points} to {new_max_points}",

            "due_date_changed": "{new_title}: due date changed from {old_due_date} to {new_due_date}",
            "due_date_added": "{new_title}: due date set to {new_due_date}",
            "due_date_removed": "{old_title}: due date removed",

            "open_date_changed": "{new_title}: open date changed from {old_open_date} to {new_open_date}",
            "open_date_added": "{new_title}: open date set to {new_open_date}",
            "open_date_removed": "{old_title}: open date removed",

            "close_date_changed": "{new_title}: close date changed from {old_close_date} to {new_close_date}",
            "close_date_added": "{new_title}: close date set to {new_close_date}",
            "close_date_removed": "{old_title}: close date removed",

            "assignment_opened": "{new_title} is now open",  # was "not available until", now past/gone
            "assignment_closed": "{new_title} is now closed",  # now past close_date

            "due_date_reminder": "Reminder: {new_title} - {offset_label} before due ({new_due_date})",
        },
        "announcements": {
            "new_announcement": "New announcement: {new_title}",
        },
    }




# Fields that are compared field-by-field for changes.
# Each entry: (field_name, added_key, changed_key, removed_key)
# A key of None means that event doesn't exist (skip it).
_FIELD_EVENTS: list[tuple[str, str | None, str | None, str | None]] = [
    ("title",       None,               "title_changed",        None),
    ("score",       "score_added",      "score_changed",        None),
    ("max_points",  None,               "max_points_changed",   None),
    ("due_date",    "due_date_added",   "due_date_changed",     "due_date_removed"),
    ("open_date",   "open_date_added",  "open_date_changed",    "open_date_removed"),
    ("close_date",  "close_date_added", "close_date_changed",   "close_date_removed"),
]


def diff_assignments(
    old: dict[str, dict],
    new: dict[str, dict],
) -> dict[str, list[dict[str, str]]]:
    """
    Compare two snapshots of assignments and return all detected changes.

    Returns a dict keyed by assignment id, each value being a list of
    notification dicts::

        {
            "123": [{"key": "score_added", "label": "Homework 1: graded - 95 / 100"}],
            "456": [{"key": "assignment_removed", "label": "Assignment removed: Quiz 3"}],
        }
    """

    def _fmt(key: str, old_a: dict | None, new_a: dict | None) -> dict[str, str]:
        a_old = old_a or {}
        a_new = new_a or {}
        kwargs = {f"old_{k}": v for k, v in a_old.items()}
        kwargs.update({f"new_{k}": v for k, v in a_new.items()})
        return {"key": key, "label": format_notification("assignments", key, **kwargs)}

    result: dict[str, list[dict[str, str]]] = {}

    old_ids = set(old)
    new_ids = set(new)

    # --- Removed assignments
    for aid in old_ids - new_ids:
        result[aid] = [_fmt("assignment_removed", old[aid], None)]

    # --- New assignments
    for aid in new_ids - old_ids:
        result[aid] = [_fmt("new_assignment", None, new[aid])]

    # --- Changed assignments
    for aid in old_ids & new_ids:
        old_a = old[aid]
        new_a = new[aid]
        notifs: list[dict[str, str]] = []

        for field, added_key, changed_key, removed_key in _FIELD_EVENTS:
            old_val = old_a.get(field)
            new_val = new_a.get(field)

            if old_val == new_val:
                continue

            if old_val is None and new_val is not None:
                # Value was added
                if added_key:
                    notifs.append(_fmt(added_key, old_a, new_a))

            elif old_val is not None and new_val is None:
                # Value was removed - check for synthetic open/close events first.
                if field == "open_date":    # TODO: RECONSIDER THIS LOGIC
                    # open_date gone -> assignment is now open; suppress plain open_date_removed
                    notifs.append(_fmt("assignment_opened", old_a, new_a))
                elif field == "close_date":
                    # close_date gone -> assignment is now closed; suppress plain close_date_removed
                    notifs.append(_fmt("assignment_closed", old_a, new_a))
                elif removed_key:
                    notifs.append(_fmt(removed_key, old_a, new_a))

            else:
                # Value changed
                if changed_key:
                    notifs.append(_fmt(changed_key, old_a, new_a))

        if notifs:
            result[aid] = notifs

    return result


def filter_enabled(
    notifs: dict[str, list[dict[str, str]]],
    enabled: dict[str, bool] | None,
) -> dict[str, list[dict[str, str]]]:
    """Filter a notification dict to only include events enabled in config."""
    if enabled is None:
        return notifs
    filtered = {
        aid: [n for n in ns if enabled.get(n["key"], True)]
        for aid, ns in notifs.items()
    }
    return {aid: ns for aid, ns in filtered.items() if ns}


def format_notification(category: str, key: str, **kwargs) -> str:
    """Return a formatted notification string for the given category and event key."""
    category_labels = LABELS.get(category)
    if category_labels is None:
        raise KeyError(f"Unknown notification category: '{category}'")
    template = category_labels.get(key)
    if template is None:
        raise KeyError(f"Unknown notification key: '{key}' in category '{category}'")
    return template.format_map(kwargs)


def diff_announcements(
    old: dict[str, dict],
    new: dict[str, dict],
) -> list[dict]:
    """
    Return a list of newly-appeared announcement dicts.

    Each returned dict is the full announcement (id, title, content, posted_at).
    """
    new_ids = set(new) - set(old)
    return [new[aid] for aid in sorted(new_ids)]
