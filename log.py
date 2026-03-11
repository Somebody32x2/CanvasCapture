from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_data_dir = os.getenv("DATA_DIR", ".")
Path(_data_dir).mkdir(parents=True, exist_ok=True)
LOG_FILE = Path(_data_dir) / "app.log"


def log(msg: str) -> None:
    """Print *msg* to stdout and append a timestamped line to the log file."""
    stamped = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(stamped)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(stamped + "\n")

