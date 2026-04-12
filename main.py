import os
import json
import time
from datetime import datetime, timedelta

from dateutil import parser as du_parser
from pathlib import Path

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox
from platformdirs import user_data_dir

import discord
import sign_in
import read_data
import parse_site
import notifications
import config
from log import log, verbose, set_log_timezone, log_exception

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


def _humanize_seconds_before_due(offset_s: int) -> str:
    """Short label for Discord, e.g. '1 week', '1 day 3 hours'."""
    sec = int(offset_s)
    if sec <= 0:
        return f"{offset_s}s"
    remainder = sec
    parts: list[str] = []
    for name, unit in (
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
    ):
        if remainder >= unit:
            n, remainder = divmod(remainder, unit)
            if n:
                parts.append(f"{n} {name}{'s' if n != 1 else ''}")
    if remainder:
        parts.append(f"{remainder} second{'s' if remainder != 1 else ''}")
    if not parts:
        return f"{offset_s} second{'s' if offset_s != 1 else ''}"
    return " ".join(parts)


def _assignment_score_percent(a: dict) -> float | None:
    """
    Best-effort percentage 0–100: score/max_points*100 when both exist,
    else raw score if no max_points (treat as already a percent-like value).
    """
    score = a.get("score")
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    max_p = a.get("max_points")
    if max_p is not None:
        try:
            mp = float(max_p)
            if mp > 0:
                return (s / mp) * 100.0
        except (TypeError, ValueError):
            pass
    return s


def _should_send_deadline_reminder(a: dict) -> bool:
    """
    Prefer false negatives over false positives: remind if we are unsure,
    if there is no submission, or if the grade is below 75%.
    """
    pct = _assignment_score_percent(a)
    if pct is not None and pct < 75:
        return True
    submitted = a.get("submitted")
    if submitted is None:
        return True
    if submitted is False:
        return True
    return False


def _maybe_send_due_reminders(course: dict, course_id: str, assignments: list[dict]) -> None:
    """
    Send Discord reminders when now >= due_date - offset for each configured offset,
    if the assignment may still need attention: unknown submission status, not submitted,
    or score below 75% (as percent of max points when available).
    """
    raw_offsets = cfg.get("due_reminder_offsets_seconds") or []
    if not raw_offsets:
        return
    if enabled_assignment_notifs is not None and not enabled_assignment_notifs.get(
        "due_date_reminder", True
    ):
        return

    try:
        offsets = sorted({int(x) for x in raw_offsets if int(x) > 0})
    except (TypeError, ValueError):
        log(
            "[ERROR] config 'due_reminder_offsets_seconds' must be a list of positive integers (seconds)."
        )
        return

    sent_map: dict = course.setdefault("due_reminder_sent", {})
    valid_ids = {str(a.get("id")) for a in assignments if a.get("id") is not None}
    for key in list(sent_map.keys()):
        if str(key) not in valid_ids:
            del sent_map[key]

    now = datetime.now(tz)
    reminders_out: list[dict] = []

    for a in assignments:
        aid = a.get("id")
        if aid is None:
            continue
        aid_str = str(aid)

        if a.get("closed"):
            continue
        if not _should_send_deadline_reminder(a):
            continue

        due_iso = a.get("due_date")
        if not due_iso:
            continue

        try:
            due_dt = du_parser.parse(due_iso)
        except (TypeError, ValueError) as exc:
            verbose(f"due reminder: skip assignment {aid_str}, bad due_date {due_iso!r}: {exc}")
            continue

        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=tz)
        else:
            due_dt = due_dt.astimezone(tz)

        if now >= due_dt:
            continue

        prev = sent_map.get(aid_str, sent_map.get(aid, []))
        if not isinstance(prev, list):
            prev = []
        already_sent: set[int] = set()
        for x in prev:
            try:
                already_sent.add(int(x))
            except (TypeError, ValueError):
                continue

        new_offsets: list[int] = []
        for off in offsets:
            if off in already_sent:
                continue
            remind_at = due_dt - timedelta(seconds=off)
            if now >= remind_at:
                new_offsets.append(off)

        if not new_offsets:
            continue

        title = a.get("title") or f"Assignment {aid_str}"
        due_display = due_dt.strftime("%Y-%m-%d %H:%M %Z")
        base_url = (canvas_url or "").rstrip("/")
        assignment_url = (
            f"{base_url}/courses/{course_id}/assignments/{aid_str}" if base_url else ""
        )

        for off in new_offsets:
            label = _humanize_seconds_before_due(off)
            reminders_out.append(
                {
                    "title": title,
                    "offset_seconds": off,
                    "offset_label": f"{label} before due",
                    "due_date_display": due_display,
                    "assignment_url": assignment_url,
                }
            )
            already_sent.add(off)
            log(f"  [due reminder] {title!r} — {label} before due ({off}s)")

        sent_map[aid_str] = sorted(already_sent)

    if reminders_out:
        discord.send_deadline_reminder_notifications(course_id, reminders_out)


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
        if (a := parse_site.parse_assignment_row(row)) is not None
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

    _maybe_send_due_reminders(course, course_id, new_list)

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
        if (a := parse_site.parse_announcement_row(row)) is not None
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



camoufox_wrapper = Camoufox(headless=headless, user_data_dir=Path(data_dir) / "camoufox_data")
browser = camoufox_wrapper.__enter__()
log(f"Starting: username={username} canvas_url={canvas_url} data_dir={data_dir}")
try:
    page, browser = sign_in.sign_in(username, password, canvas_url, browser)
except Exception as e1:
    log_exception("[ERROR] Error during initial sign in", e1)
    discord.send_error_notification(
        str(e1),
        error_type="signin_failure",
        details={"exception": repr(e1)},
    )
    try:
        browser.close()
    except Exception:
        pass
    time.sleep(3 * 60 * 60)
    exit(1)

try:
    while True:
        try:
            run_checks(page)
        except Exception as e:
            log_exception("[ERROR] Error during check", e)
            log("Attempting to re-sign in...")
            try:
                page, browser = sign_in.sign_in(username, password, canvas_url, browser)
                run_checks(page)
            except Exception as e2:
                log_exception("[ERROR] Re-sign in failed", e2)
                discord.send_error_notification(
                    str(e2),
                    error_type="signin_failure",
                    details={"exception": repr(e2)},
                )
                time.sleep(3 * 60 * 60)
                browser.close()
                exit(1) # we are unrecoverable, so exit for the script to restart


        sleep_secs = get_sleep_seconds()
        log(f"Sleeping {sleep_secs / 60:.1f} minutes...")
        time.sleep(sleep_secs)
finally:
    try:
        browser.close()
    except Exception:
        pass
