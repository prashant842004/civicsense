import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from app import create_app
from models import POINTS, Complaint, User, db


def img_bytes(seed=0, size=(200, 200)):
    rng = np.random.default_rng(seed)
    arr = (rng.random((*size, 3)) * 255).astype("uint8")
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "PNG")
    b.seek(0)
    return b


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "UPLOAD_FOLDER": self.tmp.name,
                               "SQLALCHEMY_DATABASE_URI": "sqlite://", "SECRET_KEY": "t"})
        with self.app.app_context():
            from seed import USERS
            from werkzeug.security import generate_password_hash
            for n, e, p, r in USERS:
                db.session.add(User(name=n, email=e, role=r, password_hash=generate_password_hash(p)))
            db.session.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, email, pw):
        c = self.app.test_client()
        r = c.post("/login", data={"email": email, "password": pw})
        self.assertEqual(r.status_code, 302)
        return c

    def report(self, c, title, category, desc="", seed=1):
        return c.post("/citizen/report", data={
            "title": title, "category": category, "description": desc, "lat": "21.15", "lng": "79.09",
            "media": (img_bytes(seed), "p.png")}, content_type="multipart/form-data")

    def test_public_pages(self):
        c = self.app.test_client()
        for url in ("/", "/login", "/register", "/api/complaints"):
            self.assertEqual(c.get(url).status_code, 200, url)
        self.assertEqual(c.get("/admin/").status_code, 302)

    def test_register_and_role_guard(self):
        c = self.app.test_client()
        r = c.post("/register", data={"name": "A", "email": "a@x.com", "password": "secret1", "role": "admin"})
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(email="a@x.com").one().role, "citizen")
        self.assertEqual(c.get("/admin/").status_code, 403)

    def test_bad_inputs(self):
        c = self.login("citizen@civicsense.local", "citizen123")
        r = c.post("/citizen/report", data={"title": "Pothole here", "lat": "", "lng": "",
                   "media": (img_bytes(), "p.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        r = c.post("/citizen/report", data={"title": "Pothole here", "lat": "21", "lng": "79",
                   "media": (io.BytesIO(b"not an image"), "x.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        r = c.post("/citizen/report", data={"title": "Pothole here", "lat": "21", "lng": "79",
                   "media": (io.BytesIO(b"x"), "x.exe")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_routing(self):
        c = self.login("citizen@civicsense.local", "citizen123")
        self.assertEqual(self.report(c, "Big pothole on road", "pothole").status_code, 302)
        self.assertEqual(self.report(c, "Plastic litter in park", "litter", seed=2).status_code, 302)
        with self.app.app_context():
            a, b = Complaint.query.order_by(Complaint.id).all()
            self.assertEqual((a.route, a.department), ("municipal", "Roads & Traffic"))
            self.assertEqual(b.route, "volunteer")
            self.assertEqual(User.query.filter_by(role="citizen").one().points, 10)

    def test_full_volunteer_lifecycle(self):
        cit = self.login("citizen@civicsense.local", "citizen123")
        self.report(cit, "Plastic litter in park", "litter")
        vol = self.login("volunteer@civicsense.local", "volunteer123")
        self.assertIn(b"Plastic litter", vol.get("/volunteer/tasks?lat=21.15&lng=79.09").data)
        vol.post("/volunteer/accept/1")
        r = vol.post("/volunteer/complete/1", data={"proof": (img_bytes(9), "after.png")},
                     content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            c = db.session.get(Complaint, 1)
            self.assertEqual(c.status, "Resolved")
            self.assertIsNotNone(c.verify_score)
        adm = self.login("admin@civicsense.local", "admin123")
        self.assertEqual(adm.get("/admin/complaint/1").status_code, 200)
        adm.post("/admin/complaint/1", data={"action": "verify"})
        with self.app.app_context():
            self.assertEqual(db.session.get(Complaint, 1).status, "Verified")
            v = User.query.filter_by(role="volunteer").one()
            self.assertEqual(v.points, POINTS[db.session.get(Complaint, 1).priority])
        cit.post("/citizen/complaint/1/feedback", data={"rating": "5", "feedback": "great"})
        with self.app.app_context():
            self.assertEqual(db.session.get(Complaint, 1).rating, 5)
        self.assertEqual(cit.get("/citizen/complaint/1").status_code, 200)
        self.assertEqual(vol.get("/volunteer/leaderboard").status_code, 200)

    def test_admin_views_and_municipal_path(self):
        cit = self.login("citizen@civicsense.local", "citizen123")
        self.report(cit, "Drain overflowing badly", "overflowing_drain", "urgent, children nearby")
        adm = self.login("admin@civicsense.local", "admin123")
        for url in ("/admin/", "/admin/complaints", "/admin/complaints?status=Submitted&priority=High",
                    "/admin/api/stats", "/admin/export.csv", "/admin/complaint/1"):
            self.assertEqual(adm.get(url).status_code, 200, url)
        adm.post("/admin/complaint/1", data={"action": "update", "status": "In Progress",
                 "route": "municipal", "department": "Drainage & Sewerage", "note": "Crew dispatched"})
        adm.post("/admin/complaint/1", data={"action": "proof", "proof": (img_bytes(5), "a.png")},
                 content_type="multipart/form-data")
        adm.post("/admin/complaint/1", data={"action": "verify"})
        with self.app.app_context():
            self.assertEqual(db.session.get(Complaint, 1).status, "Verified")
        self.assertEqual(cit.get("/notifications").status_code, 200)

    def test_citizen_cannot_see_others(self):
        cit = self.login("citizen@civicsense.local", "citizen123")
        self.report(cit, "Pothole near school", "pothole")
        other = self.app.test_client()
        other.post("/register", data={"name": "B", "email": "b@x.com", "password": "secret1", "role": "citizen"})
        self.assertEqual(other.get("/citizen/complaint/1").status_code, 403)
        self.assertEqual(other.get("/volunteer/tasks").status_code, 403)


if __name__ == "__main__":
    unittest.main()
