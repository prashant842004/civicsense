import os

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from ai import CATEGORIES, DEPARTMENTS, category_choices, label
from config import Config
from models import STATUSES, Complaint, Notification, User, db


def home_for(user):
    return url_for({"admin": "admin.dashboard", "volunteer": "volunteer.tasks"}
                   .get(user.role, "citizen.dashboard"))


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    lm = LoginManager(app)
    lm.login_view = "login"
    lm.login_message_category = "warning"

    @lm.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from admin import bp as admin_bp
    from citizen import bp as citizen_bp
    from volunteer import bp as volunteer_bp
    for b in (citizen_bp, admin_bp, volunteer_bp):
        app.register_blueprint(b)

    @app.context_processor
    def inject():
        unread = 0
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, read=False).count()
        return dict(unread=unread, label=label, STATUSES=STATUSES, CATEGORIES=CATEGORIES,
                    category_choices=category_choices(), DEPARTMENTS=DEPARTMENTS)

    # ------------------------------------------------------------ public pages
    @app.route("/")
    def index():
        stats = dict(
            total=Complaint.query.count(),
            resolved=Complaint.query.filter(Complaint.status.in_(["Resolved", "Verified"])).count(),
            volunteers=User.query.filter_by(role="volunteer").count())
        return render_template("index.html", stats=stats)

    @app.route("/health")
    def health():
        """Database connectivity check: GET /health"""
        from sqlalchemy import text
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database=db.engine.dialect.name)
        except Exception as e:  # noqa: BLE001
            return jsonify(status="error", detail=str(e.__class__.__name__)), 500

    @app.route("/api/complaints")
    def api_complaints():
        rows = Complaint.query.order_by(Complaint.id.desc()).limit(500).all()
        return jsonify([c.to_dict() for c in rows])

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            f = request.form
            name, email = f.get("name", "").strip(), f.get("email", "").strip().lower()
            pw, role = f.get("password", ""), f.get("role", "citizen")
            if role not in ("citizen", "volunteer"):
                role = "citizen"
            if not name or "@" not in email:
                flash("Enter your name and a valid email.", "danger")
            elif len(pw) < 6:
                flash("Password must be at least 6 characters.", "danger")
            elif User.query.filter_by(email=email).first():
                flash("That email is already registered.", "danger")
            else:
                u = User(name=name, email=email, role=role, password_hash=generate_password_hash(pw))
                db.session.add(u)
                db.session.commit()
                login_user(u)
                flash(f"Welcome, {u.name}!", "success")
                return redirect(home_for(u))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            u = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
            if u and check_password_hash(u.password_hash, request.form.get("password", "")):
                login_user(u)
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else home_for(u))
            flash("Invalid email or password.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/notifications")
    @login_required
    def notifications():
        items = (Notification.query.filter_by(user_id=current_user.id)
                 .order_by(Notification.id.desc()).limit(50).all())
        html = render_template("notifications.html", items=items)
        Notification.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
        db.session.commit()
        return html

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, msg="You don't have access to this page."), 403

    @app.errorhandler(404)
    def missing(_):
        return render_template("error.html", code=404, msg="Page not found."), 404

    with app.app_context():
        db.create_all()
    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
