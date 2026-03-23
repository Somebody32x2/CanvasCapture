import time

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox
from log import log, verbose

load_dotenv()

_PAGE_LOAD_RETRIES = 2       # reload attempts if login form doesn't appear
_SIGN_IN_RETRIES = 2         # full sign-in retries on any failure
_SIGN_IN_RETRY_WAIT = 5 * 60  # seconds between full sign-in retries


def _is_browser_closed(browser):
    """Check if the browser instance is closed."""
    try:
        # Try to access a property that would fail if browser is closed
        _ = browser.is_closed() if hasattr(browser, 'is_closed') else False
        return False
    except Exception:
        return True


def _create_new_browser():
    """Create a new browser instance with the same configuration."""
    try:
        from config import load as load_config
        cfg = load_config()
        headless = cfg.get("headless", True)
        log("[INFO] Creating new browser instance...")
        return Camoufox(headless=headless)
    except Exception as exc:
        log(f"[ERROR] Failed to create new browser: {exc}")
        raise


def _attempt_sign_in(username, password, url, browser_ref):
    """
    One attempt at the full sign-in flow.
    Raises on failure. Returns tuple of (logged-in page, browser instance).
    browser_ref is a dict containing the current browser, which may be replaced if closed.
    """
    browser = browser_ref["browser"]

    # Check if browser is closed and create a new one if necessary
    if _is_browser_closed(browser):
        log("[WARN] Browser was closed, creating a new instance...")
        old_browser = browser
        browser = _create_new_browser()
        browser_ref["browser"] = browser
        try:
            old_browser.close()
        except Exception:
            pass  # Browser was already closed

    page = browser.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")

    if url in page.url:
        log("Already logged in")
        return page, browser

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
    return page, browser


def sign_in(username, password, url, browser):
    """
    Sign in to Canvas, handling browser disconnection by creating a new instance.

    Args:
        username: Canvas username
        password: Canvas password
        url: Canvas base URL
        browser: Browser instance (may be replaced if closed)

    Returns:
        Tuple of (page, browser) where browser may be a new instance if the original was closed.
    """
    browser_ref = {"browser": browser}

    for attempt in range(_SIGN_IN_RETRIES + 1):
        try:
            return _attempt_sign_in(username, password, url, browser_ref)
        except Exception as exc:
            if attempt == _SIGN_IN_RETRIES:
                raise
            log(f"[ERROR] Sign-in attempt {attempt + 1} failed: {exc}")
            log(f"  Retrying in {_SIGN_IN_RETRY_WAIT // 60} minutes... ({attempt + 1}/{_SIGN_IN_RETRIES})")
            time.sleep(_SIGN_IN_RETRY_WAIT)
