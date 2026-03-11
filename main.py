import os
import time

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox

import sign_in
import read_data
import parse_assignments

load_dotenv()

courses_env = os.getenv("COURSE_IDS", "")
courses_list = [c.strip() for c in courses_env.split(",") if c.strip()]

data = read_data.load_data(courses_list)




with Camoufox() as browser:
    # browser.new_page().url
    page = sign_in.sign_in(os.getenv('CANVAS_USERNAME'), os.getenv('CANVAS_PASSWORD'), os.getenv('CANVAS_URL'), browser)

    new_assignments = []
    for course_old in [data.get("courses", [])[0]]: # for now just do one
        course_id = course_old.get("id")
        print(f"Course ID: {course_id}")
        page.goto(f"{os.getenv('CANVAS_URL')}/courses/{course_id}/assignments")
        page.wait_for_load_state("networkidle")
        assignment_rows = page.query_selector_all(".ig-row")
        for row in assignment_rows:
            assignment = parse_assignments.parse_assignment_row(row)
            print(assignment)
            new_assignments.append(assignment)
        time.sleep(100)


