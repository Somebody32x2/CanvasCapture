from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, tzinfo
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_data_dir = os.getenv("DATA_DIR", ".")
Path(_data_dir).mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(_data_dir) / "app.log"
VERBOSE_LOG_FILE = Path(_data_dir) / "app-verbose.log"

# Timezone for logging - will be set by main.py
_log_tz: tzinfo | None = None


def set_log_timezone(tz: tzinfo) -> None:
    """Set the timezone to use for all log timestamps."""
    global _log_tz
    _log_tz = tz


def _timestamp() -> str:
    now = datetime.now(_log_tz) if _log_tz is not None else datetime.now()
    return f"{now:%Y-%m-%d %H:%M:%S}"


def log(msg: str) -> None:
    """Print *msg* to stdout and append a timestamped line to the log file."""
    stamped = f"{_timestamp()}  {msg}"
    print(stamped)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(stamped + "\n")


def verbose(msg: str) -> None:
    """Append a timestamped line to the verbose log file only (not stdout)."""
    stamped = f"{_timestamp()}  {msg}"
    with VERBOSE_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(stamped + "\n")


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def log_exception(prefix: str, exc: BaseException) -> None:
    """Log a short error line to stdout plus full traceback to verbose log."""
    log(f"{prefix}: {exc!r}")
    verbose(f"{prefix}: {exc!r}\n{format_exception(exc)}")

