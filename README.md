# CivicSense AI

AI-powered civic issue reporting and volunteer coordination for Municipal Corporations
(MCA project, KDK College of Engineering, Nagpur).

Stack: Flask, SQLAlchemy (MySQL or SQLite), OpenCV, optional YOLO (Ultralytics), Bootstrap, Leaflet + OpenStreetMap, Chart.js.

## Run (5 commands)
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed.py                                       # demo users + sample complaints
python app.py                                        # http://127.0.0.1:5000
python -m unittest discover -s tests                 # optional: run tests
```
Demo logins (from `seed.py`):

| Role | Email | Password |
|---|---|---|
| Admin | admin@civicsense.local | admin123 |
| Citizen | citizen@civicsense.local | citizen123 |
| Volunteer | volunteer@civicsense.local | volunteer123 |

Change these and set `SECRET_KEY` before any real deployment.

## Connect to MySQL
1. Install and start MySQL, then copy the settings file:
```bash
cp .env.example .env        # Windows: copy .env.example .env
```
2. Edit `.env` and set `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (or a single `DATABASE_URL`).
3. Create the database + tables and verify the connection:
```bash
pip install -r requirements.txt
python db_check.py          # creates the `civicsense` database if missing, then all tables
python seed.py              # demo users + sample complaints
python app.py
```
Open `http://127.0.0.1:5000/health` - it returns `{"status": "ok", "database": "mysql"}` when connected.
If neither `DB_HOST` nor `DATABASE_URL` is set, the app uses a local SQLite file instead.

## Features by role
- **Citizen**: register, report with photo/video + map pin (or browser GPS), AI category/priority, live timeline, notifications, feedback rating, points.
- **Municipal admin**: dashboard (stats, charts, issue map), filters, re-route, assign department, update status, upload proof, verify (awards points), CSV export.
- **Volunteer**: open community tasks (sort by nearest), accept, upload completion proof, points, badges, leaderboard, printable certificate (50+ points).

## Workflow
Report -> AI analysis (category + priority) -> routing -> Municipal department **or** volunteers -> resolution proof -> before/after check -> admin verification -> citizen feedback -> analytics.

Routing rules live in `ai.py` (`CATEGORIES`): litter and park cleaning always go to volunteers;
garbage and illegal dumping go to volunteers only when priority is Low; everything else goes to the Municipal department.
Points: High 30 / Medium 20 / Low 10 per verified task; citizens get 5 per report and 10 when it is verified.

## About the AI (important)
`ai.py` has two engines:
1. **YOLO** - used automatically if `weights/civic_yolo.pt` exists and `ultralytics` is installed.
   Train on your own labelled dataset (Roboflow Universe / Kaggle) with class names equal to the keys in
   `ai.CATEGORIES` (`pothole`, `garbage`, `overflowing_drain`, ...). Priority then also uses how much of the frame the defect covers.
2. **Rule-based fallback** (default) - category from the citizen's dropdown or description keywords; priority from
   category, urgent words ("children", "accident", ...) and a simple OpenCV texture cue. It is **not** a trained
   detector, so in your viva describe it as the baseline until YOLO weights are added.

The before/after check (`compare_before_after`) is a histogram/pixel-difference heuristic that only helps the admin
spot identical photos; the admin always makes the final verification.

## Structure
```
app.py        app factory, auth, public pages     ai.py       detection, priority, routing, verification
citizen.py    report / track / feedback           models.py   User, Complaint, ComplaintEvent, Notification
config.py     database + app settings (.env)      db_check.py test connection, create DB + tables
admin.py      dashboard, manage, verify, CSV      utils.py    uploads, notifications, haversine
volunteer.py  tasks, proof, leaderboard, cert     seed.py     demo data
templates/  static/  tests/  weights/
```

## Production notes
Run behind gunicorn + nginx, set `SECRET_KEY`, use MySQL, serve `static/uploads` from nginx, add CSRF protection (Flask-WTF) and rate limiting.
