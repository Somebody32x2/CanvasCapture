import time

from camoufox import Camoufox


def sign_in(username, password, url, browser):
    print(username, password)
    with Camoufox() as browser:
        page = browser.new_page()
        page.goto(url)
        page.fill("#username", username)
        page.fill("#password", password)
        page.click(".btn-primary[type=submit]")
        time.sleep(100)