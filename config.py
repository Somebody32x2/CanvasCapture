"""
config.py - load, save, and interactively configure settings.

Config file: config.json (in DATA_DIR specified by .env, or current directory)
If no file exists, DEFAULT_CONFIG is used as the baseline.

Run this file directly to launch the setup wizard:
    python config.py

"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from notifications import LABELS

load_dotenv()

# Use DATA_DIR from environment, default to current directory
data_dir = os.getenv("DATA_DIR", ".")
Path(data_dir).mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(data_dir) / "config.json"

# Defaults

DEFAULT_NOTIFICATION_OVERRIDES: dict[str, dict[str, bool]] = {
    "assignments": {
        "new_assignment":       True,
        "assignment_removed":   True,
        "title_changed":        False,
        "score_added":          True,
        "score_changed":        True,
        "max_points_changed":   False,
        "due_date_added":       True,
        "due_date_changed":     True,
        "due_date_removed":     True,
        "open_date_added":      False,
        "open_date_changed":    False,
        "open_date_removed":    False,
        "close_date_added":     False,
        "close_date_changed":   False,
        "close_date_removed":   False,
        "assignment_opened":    False,
        "assignment_closed":    False,
    }
}

def build_default_notifications() -> dict[str, dict[str, bool]]:
    """
    Return a notifications dict that covers every key in LABELS,
    applying the overrides above and falling back to False for anything new.
    """
    result: dict[str, dict[str, bool]] = {}
    for category, events in LABELS.items():
        overrides = DEFAULT_NOTIFICATION_OVERRIDES.get(category, {})
        result[category] = {key: overrides.get(key, False) for key in events}
    return result


DEFAULT_CONFIG: dict[str, Any] = {
    "check_interval_minutes": 30,
    "headless": True,
    "notifications": build_default_notifications(),
    "night_mode": {
        "enabled": True,
        "start_hour": 23,
        "end_hour": 7,
        "check_interval_minutes": 180,
    },
}


def load() -> dict[str, Any]:
    """
    Load config from disk, falling back to DEFAULT_CONFIG if the file is
    missing.  Any keys present in the default but absent from the file are
    filled in automatically (forward-compatible).
    """
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

    with CONFIG_PATH.open(encoding="utf-8") as fh:
        on_disk: dict[str, Any] = json.load(fh)

    # Merge: ensure every default key exists in the loaded config.
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # start from defaults
    deep_merge(config, on_disk)
    return config


def save(config: dict[str, Any]) -> None:
    """Write *config* to disk as pretty-printed JSON."""
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    print(f"Config saved to {CONFIG_PATH}")


def deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


# Interactive setup wizard

yes = {"y", "yes", "1", "true", "on"}
no  = {"n", "no", "0", "false", "off"}


def prompt_bool(label: str, default: bool) -> bool:
    default_str = "Y/n" if default else "y/N"
    while True:
        raw = input(f"  {label}  [{default_str}]: ").strip().lower()
        if raw == "":
            return default
        if raw in yes:
            return True
        if raw in no:
            return False
        print("    Please enter y or n.")


def prompt_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            print("    Please enter a whole number.")


def run_wizard() -> None:
    print("=" * 60)
    print("  CanvasCapture - configuration wizard")
    print("  Press Enter to keep the current/default value.")
    print("=" * 60)

    config = load()

    # General settings
    print("\n-- General ------------------------------------------------------")
    config["check_interval_minutes"] = prompt_int(
        "How often to check for changes (minutes)?",
        config.get("check_interval_minutes", DEFAULT_CONFIG["check_interval_minutes"]),
    )
    config["headless"] = prompt_bool(
        "Run browser headless (no visible window)?",
        config.get("headless", DEFAULT_CONFIG["headless"]),
    )

    # Notification events
    print("\n-- Notifications ------------------------------------------------")
    print("Choose which events trigger a notification.\n")

    notifications: dict[str, dict[str, bool]] = config.setdefault("notifications", {})

    for category, events in LABELS.items():
        print(f"  [ {category} ]")
        cat_cfg = notifications.setdefault(category, {})
        for key, label in events.items():
            # Strip placeholder tokens from the label for a cleaner prompt.
            clean_label = label.replace("{old_", "{").replace("{new_", "{")
            # Remove remaining {...} tokens so the prompt reads naturally.
            import re
            clean_label = re.sub(r"\{[^}]+\}", "...", clean_label)
            default_val = cat_cfg.get(key, DEFAULT_CONFIG["notifications"].get(category, {}).get(key, False))
            cat_cfg[key] = prompt_bool(clean_label, default_val)
        print()

    save(config)
    print("\nDone!  Edit config.json directly at any time.")

if __name__ == "__main__":
    run_wizard()

