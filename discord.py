from __future__ import annotations

import os
import requests

# Discord embed color per event key
_COLOUR = {
    "new_assignment":       0x57F287,  # green
    "assignment_removed":   0xED4245,  # red
    "score_added":          0xFFD700,  # gold
    "score_changed":        0xFEE75C,  # yellow
    "assignment_opened":    0x5865F2,  # blurple
    "assignment_closed":    0x99AAB5,  # grey
}
_DEFAULT_COLOUR = 0x5DADE2  # light blue


def _colour_for(key: str) -> int:
    return _COLOUR.get(key, _DEFAULT_COLOUR)


def send_course_notifications(
    course_id: str,
    sorted_notifs: list[tuple[str, list[dict[str, str]]]],
    *,
    webhook_url: str | None = None,
) -> None:
    """Post one Discord embed per notification event."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK")
    if not url:
        print("DISCORD_WEBHOOK not set: skipping Discord notifications.")
        return

    for _assignment_id, assignment_notifs in sorted_notifs:
        for n in assignment_notifs:
            embed = {
                "description": n["label"],
                "color": _colour_for(n["key"]),
                "footer": {"text": f"Course {course_id}"},
            }
            resp = requests.post(url, json={"embeds": [embed]}, timeout=10)
            resp.raise_for_status()
