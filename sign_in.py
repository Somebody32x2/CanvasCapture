import time

from log import log


def sign_in(username, password, url, browser):
    # log(username, password)
    page = browser.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    # debug save the current state of the page for dev
    open("log.txt", "a", encoding="utf-8").write(page.url + "\n" + page.content() + "\n\n")
    if url not in page.url:
        page.fill("#username", username)
        page.fill("#password", password)
        page.click(".btn-primary[type=submit]")
        page.wait_for_load_state("networkidle")
        if url not in page.url:
            open("log.txt", "a", encoding="utf-8").write(page.url + "\n" + page.content() + "\n\n")
            raise Exception("Login failed.")
        log("Logged in")
    else:
        log("Already logged in")
    return page
