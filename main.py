import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox

import discord
import sign_in
import read_data
import parse_assignments
import notifications
import config
from log import log, set_log_timezone

load_dotenv()

# Use DATA_DIR from environment, default to current directory
data_dir = os.getenv("DATA_DIR", ".")
Path(data_dir).mkdir(parents=True, exist_ok=True)
data_file = Path(data_dir) / "data.json"

courses_env = os.getenv("COURSE_IDS", "")
courses_list = [c.strip() for c in courses_env.split(",") if c.strip()]

cfg = config.load()
enabled_notifications = cfg.get("notifications", {}).get("assignments")
headless = cfg.get("headless", True)
interval_seconds = cfg.get("check_interval_minutes", 30) * 60
timezone_str = cfg.get("timezone", config.DEFAULT_CONFIG["timezone"])
try:
    tz = config.parse_timezone(timezone_str)
except ValueError as exc:
    fallback_tz_name = config.DEFAULT_CONFIG["timezone"]
    log(f"Invalid configured timezone '{timezone_str}': {exc}")
    log(f"Falling back to '{fallback_tz_name}'.")
    tz = config.parse_timezone(fallback_tz_name)

set_log_timezone(tz)


def is_night_time(night_cfg: dict) -> bool:
    now = datetime.now(tz)
    now_hour = now.hour
    start = night_cfg["start_hour"]
    end = night_cfg["end_hour"]
    if start > end:  # window crosses midnight (e.g. 23 -> 7)
        return now_hour >= start or now_hour < end
    return start <= now_hour < end


def seconds_until_night_end(night_cfg: dict) -> float:
    """Return seconds from now until the night window ends (i.e. daytime resumes)."""
    end_hour = night_cfg["end_hour"]
    now = datetime.now(tz)
    end_today = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if end_today <= now:
        end_today += timedelta(days=1)
    return (end_today - now).total_seconds()


def get_sleep_seconds() -> float:
    """
    Return how long to sleep before the next check.

    During night hours the interval is longer, but we cap the sleep so we
    don't overshoot the end of the night window (we wake up right at day-start
    instead of sleeping through it).
    """
    night_cfg = cfg.get("night_mode", {})
    night_enabled = night_cfg.get("enabled", True)

    if night_enabled and is_night_time(night_cfg):
        night_interval = night_cfg.get("check_interval_minutes", 180) * 60
        time_to_day = seconds_until_night_end(night_cfg)
        sleep = min(night_interval, time_to_day)
        log(f"Night mode active - sleeping {sleep / 60:.1f} minutes.")
        return sleep

    return interval_seconds

canvas_url = os.getenv("CANVAS_URL")
username = os.getenv("CANVAS_USERNAME")
password = os.getenv("CANVAS_PASSWORD")


def _check_mass_change_anomaly(
    course_id: str,
    old_count: int,
    new_count: int,
    removed_count: int,
    added_count: int,
) -> bool:
    """
    Detect if there's a mass change in assignments suggesting data corruption.

    Returns True if anomaly detected (should skip notifications and updates).
    Returns False if everything looks normal.
    """
    # If we went from having assignments to having none
    if old_count > 0 and new_count == 0:
        log(f"ANOMALY Course {course_id}: Mass assignment loss detected")
        log(f"  Previously had {old_count} assignments, now have {new_count}")
        log("  This may indicate a data corruption or scraping failure")
        log("  Skipping notifications and data persistence to prevent data loss")
        discord.send_error_notification(
            f"Mass assignment loss in course {course_id}",
            error_type="anomaly",
            details={
                "Previous Count": str(old_count),
                "Current Count": str(new_count),
                "Issue": "All assignments disappeared - possible scraping failure"
            }
        )
        return True

    # If we suddenly got way more assignments than we had
    if old_count > 0 and added_count >= old_count:
        log(f"ANOMALY Course {course_id}: Mass assignment gain detected")
        log(f"  Previously had {old_count} assignments, now have {new_count}")
        log(f"  Added {added_count} new assignments in a single check")
        log("  This may indicate recovery from data corruption or scraping failure")
        log("  Skipping notifications and data persistence to prevent data loss")
        discord.send_error_notification(
            f"Mass assignment gain in course {course_id}",
            error_type="anomaly",
            details={
                "Previous Count": str(old_count),
                "Current Count": str(new_count),
                "Added": str(added_count),
                "Issue": "Too many new assignments - possible recovery from corruption"
            }
        )
        return True

    return False


def run_checks(page):
    """Scrape all courses, diff assignments, send notifications, persist data."""
    data = read_data.load_data(courses_list)

    for course in data.get("courses", []):
        course_id = course.get("id")
        log(f"Checking course {course_id}...")
        page.goto(f"{canvas_url}/courses/{course_id}/assignments")
        page.wait_for_load_state("networkidle")
        assignment_rows = page.query_selector_all(".ig-row")

        new_assignments_list = [
            a for row in assignment_rows
            if (a := parse_assignments.parse_assignment_row(row)) is not None
        ]

        old_map = {a["id"]: a for a in course.get("assignments", [])}
        new_map = {a["id"]: a for a in new_assignments_list}

        # Check for mass changes before processing
        old_ids = set(old_map.keys())
        new_ids = set(new_map.keys())
        removed_count = len(old_ids - new_ids)
        added_count = len(new_ids - old_ids)

        if _check_mass_change_anomaly(course_id, len(old_map), len(new_map), removed_count, added_count):
            log(f"  Skipping course {course_id} due to anomaly.")
            continue

        notifs = notifications.diff_assignments(old_map, new_map, enabled=enabled_notifications)
        sorted_notifs = sorted(
            notifs.items(),
            key=lambda item: (
                new_map.get(item[0], old_map.get(item[0], {})).get("due_date") or "9999",
                new_map.get(item[0], old_map.get(item[0], {})).get("title") or "",
            ),
        )
        for assignment_id, assignment_notifs in sorted_notifs:
            for n in assignment_notifs:
                log(f"  [{assignment_id}] {n['label']}")

        discord.send_course_notifications(course_id, sorted_notifs)

        course["assignments"] = new_assignments_list

        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)



with Camoufox(headless=headless) as browser:
    log(f"Starting: username={username} canvas_url={canvas_url} data_dir={data_dir}")
    try:
        page = sign_in.sign_in(username, password, canvas_url, browser)
    except Exception as e1:
        log(f"[ERROR] Error during initial sign in: {e1}")
        discord.send_error_notification(str(e1), error_type="signin_failure")
        time.sleep(100000)
        exit(1)

    while True:
        try:
            run_checks(page)
        except Exception as e:
            log(f"[ERROR] Error during check: {e}")
            log("Attempting to re-sign in...")
            try:
                page = sign_in.sign_in(username, password, canvas_url, browser)
                run_checks(page)
            except Exception as e2:
                log(f"[ERROR] Re-sign in failed: {e2}")
                discord.send_error_notification(str(e2), error_type="signin_failure")
                time.sleep(200)

        sleep_secs = get_sleep_seconds()
        log(f"Sleeping {sleep_secs / 60:.1f} minutes...")
        time.sleep(sleep_secs)
