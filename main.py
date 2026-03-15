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
from log import log, verbose, set_log_timezone

load_dotenv()

# Use DATA_DIR from environment, default to current directory
data_dir = os.getenv("DATA_DIR", ".")
Path(data_dir).mkdir(parents=True, exist_ok=True)
data_file = Path(data_dir) / "data.json"

courses_env = os.getenv("COURSE_IDS", "")
courses_list = [c.strip() for c in courses_env.split(",") if c.strip()]

cfg = config.load()
enabled_assignment_notifs = cfg.get("notifications", {}).get("assignments")
enabled_announcement_notifs = cfg.get("notifications", {}).get("announcements")
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
    item_type: str,
    old_count: int,
    new_count: int,
    removed_count: int,
    added_count: int,
) -> str | None:
    """
    Detect a mass change in items suggesting data corruption.

    Returns:
        None   - no anomaly, proceed normally.
        "skip" - anomaly; skip notifications AND do not persist data.
        "save" - anomaly; skip notifications but still persist data.
    """
    if old_count > 0 and new_count == 0:
        log(f"ANOMALY Course {course_id}: Found 0 {item_type} (previously had {old_count})")
        log("  This may indicate a data corruption or scraping failure")
        log("  Skipping notifications and data persistence to prevent data loss")
        discord.send_error_notification(
            f"Found 0 {item_type} in course {course_id} (previously had {old_count})",
            error_type="anomaly",
            details={
                "Previous Count": str(old_count),
                "Found": str(new_count),
                "Issue": f"All {item_type} disappeared - possible scraping failure",
            },
        )
        return "skip"

    if added_count > 3 and (old_count == 0 or added_count >= old_count):
        log(f"ANOMALY Course {course_id}: Found {added_count} new {item_type} in a single check (previously had {old_count})")
        log("  This could be from initial setup, or recovery from a scraping failure")
        log("  Skipping notifications but saving data")
        discord.send_error_notification(
            f"Found {added_count} new {item_type} in course {course_id} in a single check",
            error_type="anomaly",
            details={
                "Previous Count": str(old_count),
                "Found": str(new_count),
                "Added": str(added_count),
                "Note": "This could be from initial setup, or recovery from a scraping failure. "
                        "Skipping notifications but saving data.",
            },
        )
        return "save"

    return None


def _check_and_notify_assignments(course, course_id, page, data):
    """Scrape assignments for a course, diff, notify, and persist."""
    page.goto(f"{canvas_url}/courses/{course_id}/assignments")
    page.wait_for_load_state("networkidle")
    assignment_rows = page.query_selector_all(".ig-row")

    new_list = [
        a for row in assignment_rows
        if (a := parse_assignments.parse_assignment_row(row)) is not None
    ]

    old_map = {a["id"]: a for a in course.get("assignments", [])}
    new_map = {a["id"]: a for a in new_list}

    old_ids = set(old_map)
    new_ids = set(new_map)

    anomaly = _check_mass_change_anomaly(
        course_id, "assignments",
        len(old_map), len(new_map),
        len(old_ids - new_ids), len(new_ids - old_ids),
    )
    if anomaly == "skip":
        return

    if anomaly is None:
        all_notifs = notifications.diff_assignments(old_map, new_map)
        sorted_all = sorted(
            all_notifs.items(),
            key=lambda item: (
                new_map.get(item[0], old_map.get(item[0], {})).get("due_date") or "9999",
                new_map.get(item[0], old_map.get(item[0], {})).get("title") or "",
            ),
        )
        for assignment_id, assignment_notifs in sorted_all:
            for n in assignment_notifs:
                log(f"  [{assignment_id}] {n['label']}")
                old_a = old_map.get(assignment_id)
                new_a = new_map.get(assignment_id)
                if old_a:
                    verbose(f"  [{assignment_id}] old: {old_a}")
                if new_a:
                    verbose(f"  [{assignment_id}] new: {new_a}")

        enabled_notifs = notifications.filter_enabled(all_notifs, enabled_assignment_notifs)
        sorted_enabled = sorted(
            enabled_notifs.items(),
            key=lambda item: (
                new_map.get(item[0], old_map.get(item[0], {})).get("due_date") or "9999",
                new_map.get(item[0], old_map.get(item[0], {})).get("title") or "",
            ),
        )
        discord.send_course_notifications(course_id, sorted_enabled)

    course["assignments"] = new_list

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _check_and_notify_announcements(course, course_id, page, data):
    """Scrape announcements for a course, diff, notify, and persist."""
    page.goto(f"{canvas_url}/courses/{course_id}/announcements")
    page.wait_for_load_state("networkidle")
    try:
        page.wait_for_selector(".ic-announcement-row")
    except Exception:
        log(f"  No announcements found for course {course_id}.")
        return
    rows = page.query_selector_all(".ic-announcement-row")
    log(f"  Found {len(rows)} announcements.")

    new_list = [
        a for row in rows
        if (a := parse_assignments.parse_announcement_row(row)) is not None
    ]

    old_map = {a["id"]: a for a in course.get("announcements", [])}
    new_map = {a["id"]: a for a in new_list}

    old_ids = set(old_map)
    new_ids = set(new_map)

    anomaly = _check_mass_change_anomaly(
        course_id, "announcements",
        len(old_map), len(new_map),
        len(old_ids - new_ids), len(new_ids - old_ids),
    )
    if anomaly == "skip":
        return

    if anomaly is None:
        all_new = notifications.diff_announcements(old_map, new_map)
        for ann in all_new:
            log(f"  [announcement {ann['id']}] {ann['title']}")
            verbose(f"  [announcement {ann['id']}] {ann}")

        if enabled_announcement_notifs is None or enabled_announcement_notifs.get("new_announcement", True):
            discord.send_announcement_notifications(course_id, all_new)
        else:
            log(f"  Announcement notifications disabled, skipping {len(all_new)} notification(s).")

    course["announcements"] = new_list

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_checks(page):
    """Scrape all courses, diff items, send notifications, persist data."""
    data = read_data.load_data(courses_list)

    for course in data.get("courses", []):
        course_id = course.get("id")
        log(f"Checking course {course_id}...")
        _check_and_notify_assignments(course, course_id, page, data)
        _check_and_notify_announcements(course, course_id, page, data)



with Camoufox(headless=headless) as browser:
    log(f"Starting: username={username} canvas_url={canvas_url} data_dir={data_dir}")
    try:
        page = sign_in.sign_in(username, password, canvas_url, browser)
    except Exception as e1:
        log(f"[ERROR] Error during initial sign in: {e1}")
        discord.send_error_notification(str(e1), error_type="signin_failure")
        time.sleep(3 * 60 * 60)
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
