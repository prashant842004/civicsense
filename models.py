from datetime import datetime, timezone
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

STATUSES = ["Submitted", "Assigned", "In Progress", "Resolved", "Verified"]
POINTS = {"High": 30, "Medium": 20, "Low": 10}
BADGES = [(300, "City Champion"), (150, "Neighbourhood Hero"),
          (50, "Clean City Helper"), (10, "Getting Started")]
CERTIFICATE_MIN_POINTS = 50


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="citizen")  # citizen|admin|volunteer
    points = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def badges(self):
        return [b for p, b in sorted(BADGES) if self.points >= p]

    @property
    def top_badge(self):
        for p, b in BADGES:
            if self.points >= p:
                return b
        return None


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(40), nullable=False, default="other")
    priority = db.Column(db.String(10), nullable=False, default="Low")
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(255), default="")
    media_path = db.Column(db.String(255))
    media_type = db.Column(db.String(10))  # image|video
    status = db.Column(db.String(20), nullable=False, default="Submitted")
    route = db.Column(db.String(15), nullable=False, default="municipal")  # municipal|volunteer
    department = db.Column(db.String(60), default="")
    ai_source = db.Column(db.String(30), default="")
    ai_confidence = db.Column(db.Float)
    ai_note = db.Column(db.String(255), default="")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    volunteer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    proof_path = db.Column(db.String(255))
    verify_score = db.Column(db.Float)
    verify_note = db.Column(db.String(255), default="")
    rating = db.Column(db.Integer)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    resolved_at = db.Column(db.DateTime)

    reporter = db.relationship("User", foreign_keys=[user_id], backref="complaints")
    volunteer = db.relationship("User", foreign_keys=[volunteer_id], backref="tasks")
    events = db.relationship("ComplaintEvent", backref="complaint", order_by="ComplaintEvent.id",
                             cascade="all, delete-orphan")

    def to_dict(self):
        from ai import label
        return dict(id=self.id, title=self.title, category=label(self.category),
                    priority=self.priority, status=self.status, route=self.route,
                    lat=self.lat, lng=self.lng)


class ComplaintEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaint.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255))
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
