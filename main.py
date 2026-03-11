import os
import json
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox

import discord
import sign_in
import read_data
import parse_assignments
import notifications
import config

load_dotenv()

courses_env = os.getenv("COURSE_IDS", "")
courses_list = [c.strip() for c in courses_env.split(",") if c.strip()]

cfg = config.load()
enabled_notifications = cfg.get("notifications", {}).get("assignments")
headless = cfg.get("headless", True)
interval_seconds = cfg.get("check_interval_minutes", 30) * 60


def is_night_time(night_cfg: dict) -> bool:
    """Return True if the current local time falls within the night window."""
    now_hour = datetime.now().hour
    start = night_cfg["start_hour"]
    end = night_cfg["end_hour"]
    if start > end:  # window crosses midnight (e.g. 23 -> 7)
        return now_hour >= start or now_hour < end
    return start <= now_hour < end


def seconds_until_night_end(night_cfg: dict) -> float:
    """Return seconds from now until the night window ends (i.e. daytime resumes)."""
    end_hour = night_cfg["end_hour"]
    now = datetime.now()
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
        print(f"Night mode active - sleeping {sleep / 60:.1f} minutes.")
        return sleep

    return interval_seconds

canvas_url = os.getenv("CANVAS_URL")
username = os.getenv("CANVAS_USERNAME")
password = os.getenv("CANVAS_PASSWORD")


def run_checks(page):
    """Scrape all courses, diff assignments, send notifications, persist data."""
    data = read_data.load_data(courses_list)

    for course in data.get("courses", []):
        course_id = course.get("id")
        print(f"Checking course {course_id}...")
        page.goto(f"{canvas_url}/courses/{course_id}/assignments")
        page.wait_for_load_state("networkidle")
        assignment_rows = page.query_selector_all(".ig-row")

        new_assignments_list = [
            a for row in assignment_rows
            if (a := parse_assignments.parse_assignment_row(row)) is not None
        ]

        old_map = {a["id"]: a for a in course.get("assignments", [])}
        new_map = {a["id"]: a for a in new_assignments_list}

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
                print(f"  [{assignment_id}] {n['label']}")

        discord.send_course_notifications(course_id, sorted_notifs)

        course["assignments"] = new_assignments_list

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


with Camoufox(headless=headless) as browser:
    page = sign_in.sign_in(username, password, canvas_url, browser)

    while True:
        try:
            run_checks(page)
        except Exception as e:
            print(f"Error during check: {e}")
            print("Attempting to re-sign in...")
            try:
                page = sign_in.sign_in(username, password, canvas_url, browser)
                run_checks(page)
            except Exception as e2:
                print(f"Re-sign in failed: {e2}")

        sleep_secs = get_sleep_seconds()
        print(f"Sleeping {sleep_secs / 60:.1f} minutes...")
        time.sleep(sleep_secs)
