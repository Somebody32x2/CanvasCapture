import os
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Use DATA_DIR from environment, default to current directory
data_dir = os.getenv("DATA_DIR", ".")
Path(data_dir).mkdir(parents=True, exist_ok=True)
data_file = Path(data_dir) / "data.json"


def load_data(courses_list):
    if not data_file.exists():
        default_courses = [{"id": c, "assignments": [], "announcements": [], "grades": []} for c in courses_list]
        default = {"courses": default_courses}
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ensure any courses from .env exist in data.json
    existing_ids = {course.get("id") for course in data.get("courses", [])}
    added = False
    for c in courses_list:
        if c not in existing_ids:
            data.setdefault("courses", []).append({"id": c, "assignments": [], "announcements": [], "grades": []})
            added = True

    if added:
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data

