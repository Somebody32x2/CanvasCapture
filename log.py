from __future__ import annotations

import os
import sys
from datetime import datetime, tzinfo
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_data_dir = os.getenv("DATA_DIR", ".")
Path(_data_dir).mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(_data_dir) / "app.log"

# Timezone for logging - will be set by main.py
_log_tz: tzinfo | None = None


def set_log_timezone(tz: tzinfo) -> None:
    """Set the timezone to use for all log timestamps."""
    global _log_tz
    _log_tz = tz


def log(msg: str) -> None:
    """Print *msg* to stdout and append a timestamped line to the log file."""
    if _log_tz is not None:
        now = datetime.now(_log_tz)
    else:
        now = datetime.now()
    stamped = f"{now:%Y-%m-%d %H:%M:%S}  {msg}"
    print(stamped)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(stamped + "\n")

