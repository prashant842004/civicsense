"""Create demo data:  python seed.py   (admin@civicsense.local / admin123)"""
from werkzeug.security import generate_password_hash

import ai
from app import create_app
from models import Complaint, ComplaintEvent, User, db

USERS = [("Municipal Admin", "admin@civicsense.local", "admin123", "admin"),
         ("Demo Citizen", "citizen@civicsense.local", "citizen123", "citizen"),
         ("Demo Volunteer", "volunteer@civicsense.local", "volunteer123", "volunteer")]

SAMPLES = [  # title, category, description, lat, lng, address
    ("Deep pothole on Wardha Road", "pothole", "Large pothole, dangerous for two-wheelers", 21.1204, 79.0572, "Wardha Road, Nagpur"),
    ("Garbage pile near Sitabuldi market", "garbage", "Waste not collected for days", 21.1466, 79.0849, "Sitabuldi, Nagpur"),
    ("Streetlight not working", "broken_streetlight", "Whole lane is dark at night", 21.1610, 79.0980, "Dharampeth, Nagpur"),
    ("Plastic litter at Futala Lake", "litter", "Plastic wrappers along the footpath", 21.1583, 79.0436, "Futala Lake, Nagpur"),
]


def run():
    app = create_app()
    with app.app_context():
        for name, email, pw, role in USERS:
            if not User.query.filter_by(email=email).first():
                db.session.add(User(name=name, email=email, role=role,
                                    password_hash=generate_password_hash(pw)))
        db.session.commit()
        citizen = User.query.filter_by(email="citizen@civicsense.local").first()
        if Complaint.query.count() == 0:
            for title, cat, desc, lat, lng, addr in SAMPLES:
                prio = ai.LEVELS[ai.CATEGORIES[cat][3]]
                route, dept = ai.route_complaint(cat, prio)
                c = Complaint(title=title, description=desc, category=cat, priority=prio, lat=lat,
                              lng=lng, address=addr, route=route, department=dept, ai_source="seed",
                              ai_note="Sample data", user_id=citizen.id)
                c.events.append(ComplaintEvent(text="Complaint submitted (sample data)"))
                db.session.add(c)
            db.session.commit()
        print("Seeded. Admin login: admin@civicsense.local / admin123")


if __name__ == "__main__":
    run()
