import os
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from log import log

load_dotenv()

# Verbose log file for sign-in debug HTML
_data_dir = os.getenv("DATA_DIR", ".")
Path(_data_dir).mkdir(parents=True, exist_ok=True)
_verbose_log = Path(_data_dir) / "app-verbose.log"


def _write_verbose_log(page_url: str, page_content: str) -> None:
    """Write page URL and HTML content to verbose log."""
    with _verbose_log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n{'='*80}\n")
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.write(f"URL: {page_url}\n")
        fh.write(f"{'='*80}\n")
        fh.write(page_content)
        fh.write("\n")


def sign_in(username, password, url, browser):
    # log(username, password)
    page = browser.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    if url not in page.url:
        _write_verbose_log(page.url + f" not yet at {url}", page.content())
        page.fill("#username", username)
        page.fill("#password", password)
        page.click(".btn-primary[type=submit]")
        page.wait_for_load_state("networkidle")
        if url not in page.url:
            _write_verbose_log(page.url + f" not yet at {url} after submission", page.content())
            error_msg = f"Login failed. Final URL: {page.url}"
            raise Exception(error_msg)
        log("Logged in")
    else:
        log("Already logged in")
    return page
