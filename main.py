import os

from dotenv import load_dotenv
from camoufox.sync_api import Camoufox

import sign_in

load_dotenv()

# with Camoufox() as browser:
sign_in.sign_in(os.getenv('CANVAS_USERNAME'), os.getenv('CANVAS_PASSWORD'), os.getenv('CANVAS_URL'), 0)