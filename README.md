## Setup
pip install -U camoufox
pip install dotenv
camoufox fetch
(python -m camoufox fetch on linux)

### To Do
- [x] Fewer Checks at Night
- [ ] Grades page/comments
- [ ] Assignment reminders
  - [ ] Check if assignment has submissions (likely requires navigation to assignment page, save submission status)
  - [ ] Flexible config for reminders (course black/whitelist, frequency, start/end time, etc.)
- [ ] Consider alternate notification service support (ntfy, etc.)
- [ ] Automatic course detection and name mapping at startup
- [ ] Adaptive assignment special handling (e.g. external/autograding, online quiz) detection/regex, no new grade notifications
- Potentially: 
- [ ] WebUI/status page/method for user input other than files/env vars (e.g. for reminders)