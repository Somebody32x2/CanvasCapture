import time

from dotenv import load_dotenv
from log import log, verbose

load_dotenv()

_PAGE_LOAD_RETRIES = 2       # reload attempts if login form doesn't appear
_SIGN_IN_RETRIES = 2         # full sign-in retries on any failure
_SIGN_IN_RETRY_WAIT = 5 * 60  # seconds between full sign-in retries


def _attempt_sign_in(username, password, url, browser):
    """
    One attempt at the full sign-in flow.
    Raises on failure. Returns the logged-in page on success.
    """
    page = browser.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")

    if url in page.url:
        log("Already logged in")
        return page

    # Wait for login form - retry page load up to _PAGE_LOAD_RETRIES times
    for load_attempt in range(_PAGE_LOAD_RETRIES + 1):
        try:
            page.wait_for_selector("#username", timeout=10_000)
            break
        except Exception:
            verbose(f"URL: {page.url} (login form not found, attempt {load_attempt + 1})\n{page.content()}")
            if load_attempt == _PAGE_LOAD_RETRIES:
                raise Exception(f"Login form (#username) not found after {_PAGE_LOAD_RETRIES + 1} page loads")
            log(f"Login form not found, reloading ({load_attempt + 1}/{_PAGE_LOAD_RETRIES})...")
            page.goto(url)
            page.wait_for_load_state("networkidle")

    verbose(f"URL: {page.url} (not yet at {url})\n{page.content()}")
    page.fill("#username", username)
    page.fill("#password", password)
    page.click(".btn-primary[type=submit]")
    page.wait_for_load_state("networkidle")

    if url not in page.url:
        verbose(f"URL: {page.url} (not yet at {url} after submission)\n{page.content()}")
        raise Exception(f"Login failed. Final URL: {page.url}")

    log("Logged in")
    return page


def sign_in(username, password, url, browser):
    for attempt in range(_SIGN_IN_RETRIES + 1):
        try:
            return _attempt_sign_in(username, password, url, browser)
        except Exception as exc:
            if attempt == _SIGN_IN_RETRIES:
                raise
            log(f"[ERROR] Sign-in attempt {attempt + 1} failed: {exc}")
            log(f"  Retrying in {_SIGN_IN_RETRY_WAIT // 60} minutes... ({attempt + 1}/{_SIGN_IN_RETRIES})")
            time.sleep(_SIGN_IN_RETRY_WAIT)
