from __future__ import annotations

import os
import random
import time
from datetime import datetime

import requests

from log import log

# Discord embed color per event key
_COLOR = {
    "new_assignment":       0x57F287,  # green
    "assignment_removed":   0xED4245,  # red
    "score_added":          0xFFD700,  # gold
    "score_changed":        0xFEE75C,  # yellow
    "assignment_opened":    0x5865F2,  # blurple
    "assignment_closed":    0x99AAB5,  # grey
    "new_announcement":     0x5865F2,  # blurple
}
_DEFAULT_COLOR = 0x5DADE2  # light blue


def _color_for(key: str) -> int:
    return _COLOR.get(key, _DEFAULT_COLOR)


def _send_message(
    embed: dict,
    webhook_url: str | None = None,
) -> None:
    """Send a single Discord embed via webhook with retry/backoff."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK")
    if not url:
        log("DISCORD_WEBHOOK not set: skipping Discord notification.")
        return

    max_retries = 5
    base_backoff = 1.0   # seconds
    max_backoff  = 30.0  # seconds

    attempt = 0
    while True:
        try:
            resp = requests.post(url, json={"embeds": [embed]}, timeout=10)

            if resp.status_code == 429:
                retry_after = 0.0
                try:
                    retry_after = float(resp.json().get("retry_after", 0))
                except (ValueError, TypeError, requests.JSONDecodeError):
                    pass

                if attempt >= max_retries:
                    log(f"Discord 429: max retries reached; skipping event.")
                    break

                if retry_after <= 0:
                    retry_after = min(max_backoff, base_backoff * (2 ** attempt))
                    retry_after += random.uniform(0, 0.5)

                log(f"Discord rate-limited (429). Retrying in {retry_after:.2f}s...")
                time.sleep(retry_after)
                attempt += 1
                continue

            if 500 <= resp.status_code < 600:
                if attempt >= max_retries:
                    log(f"Discord {resp.status_code}: max retries reached; skipping event.")
                    break
                backoff = min(max_backoff, base_backoff * (2 ** attempt)) + random.uniform(0, 0.5)
                log(f"Discord server error {resp.status_code}. Retrying in {backoff:.2f}s...")
                time.sleep(backoff)
                attempt += 1
                continue

            resp.raise_for_status()
            break

        except requests.RequestException as exc:
            if attempt >= max_retries:
                log(f"Discord request failed after {max_retries} retries: {exc}; skipping event.")
                break
            backoff = min(max_backoff, base_backoff * (2 ** attempt)) + random.uniform(0, 0.5)
            log(f"Discord request error: {exc}. Retrying in {backoff:.2f}s...")
            time.sleep(backoff)
            attempt += 1


def send_course_notifications(
    course_id: str,
    sorted_notifs: list[tuple[str, list[dict[str, str]]]],
    *,
    webhook_url: str | None = None,
) -> None:
    """Post one Discord embed per notification event, with retry/backoff."""
    for _assignment_id, assignment_notifs in sorted_notifs:
        for n in assignment_notifs:
            embed = {
                "description": n["label"],
                "color": _color_for(n["key"]),
                "footer": {"text": f"Course {course_id}"},
            }
            _send_message(embed, webhook_url=webhook_url)


def send_announcement_notifications(
    course_id: str,
    announcements: list[dict],
    *,
    webhook_url: str | None = None,
) -> None:
    """Post one Discord embed per new announcement with title, content, and posted time."""
    for ann in announcements:
        content = ann.get("content") or ""
        if len(content) > 2048:
            content = content[:2045] + "..."
        posted = ann.get("posted_at") or "Unknown"
        embed = {
            "title": ann.get("title") or "New Announcement",
            "description": content,
            "color": _color_for("new_announcement"),
            "footer": {"text": f"Posted: {posted} | Course {course_id}"},
        }
        _send_message(embed, webhook_url=webhook_url)


def send_error_notification(
    error_message: str,
    error_type: str = "generic",
    details: dict[str, str] | None = None,
    *,
    webhook_url: str | None = None,
) -> None:
    """
    Send a webhook notification about an error with details.

    Parameters:
    - error_message: The main error message to display
    - error_type: Type of error ("signin_failure", "check_error", "anomaly", etc.)
    - details: Optional dict of additional field names -> values to include
    - webhook_url: Optional webhook URL (defaults to DISCORD_WEBHOOK env var)
    """
    # Error type configurations
    error_configs = {
        "signin_failure": {
            "title": "❌ Canvas Sign-In Failed",
            "color": 0xED4245,  # red
        },
        "check_error": {
            "title": "⚠️ Canvas Check Error",
            "color": 0xFEE75C,  # yellow
        },
        "anomaly": {
            "title": "⚠️ Data Anomaly Detected",
            "color": 0xFFA500,  # orange
        },
        "generic": {
            "title": "ℹ️ Canvas Error",
            "color": 0x5DADE2,  # light blue
        },
    }

    config = error_configs.get(error_type, error_configs["generic"])

    embed = {
        "title": config["title"],
        "description": error_message,
        "color": config["color"],
    }

    if details:
        embed["fields"] = [
            {
                "name": key,
                "value": value,
                "inline": False
            }
            for key, value in details.items()
        ]

    _send_message(embed, webhook_url=webhook_url)


