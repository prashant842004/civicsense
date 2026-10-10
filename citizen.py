from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import ai
from models import Complaint, db
from utils import add_event, notify_admins, parse_coords, role_required, save_upload, upload_path

bp = Blueprint("citizen", __name__, url_prefix="/citizen")


@bp.route("/dashboard")
@role_required("citizen", "volunteer")
def dashboard():
    items = (Complaint.query.filter_by(user_id=current_user.id)
             .order_by(Complaint.id.desc()).all())
    counts = {"total": len(items),
              "open": sum(c.status in ("Submitted", "Assigned", "In Progress") for c in items),
              "done": sum(c.status in ("Resolved", "Verified") for c in items)}
    return render_template("citizen/dashboard.html", items=items, counts=counts)


@bp.route("/report", methods=["GET", "POST"])
@role_required("citizen", "volunteer")
def report():
    if request.method == "POST":
        f = request.form
        try:
            title = f.get("title", "").strip()
            if len(title) < 4:
                raise ValueError("Please give the complaint a short title")
            lat, lng = parse_coords(f.get("lat"), f.get("lng"))
            name, kind = save_upload(request.files.get("media"))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("citizen/report.html", form=f), 400

        result = ai.analyze(upload_path(name), kind, f.get("category", "auto"),
                            f"{title}. {f.get('description', '')}", current_app.config["YOLO_WEIGHTS"])
        route, dept = ai.route_complaint(result["category"], result["priority"])
        c = Complaint(title=title, description=f.get("description", "").strip(),
                      category=result["category"], priority=result["priority"],
                      lat=lat, lng=lng, address=f.get("address", "").strip()[:255],
                      media_path=name, media_type=kind, route=route, department=dept,
                      ai_source=result["source"], ai_confidence=result["confidence"],
                      ai_note=result["note"], user_id=current_user.id)
        db.session.add(c)
        add_event(c, "Complaint submitted by citizen")
        add_event(c, f"AI analysis: {ai.label(c.category)}, {c.priority} priority ({c.ai_source})")
        add_event(c, "Routed to community volunteers" if route == "volunteer"
                  else f"Routed to Municipal Corporation: {dept}")
        current_user.points += 5
        db.session.flush()
        notify_admins(f"New {c.priority}-priority complaint: {c.title}",
                      url_for("admin.detail", cid=c.id))
        db.session.commit()
        flash("Complaint submitted. You earned 5 points!", "success")
        return redirect(url_for("citizen.detail", cid=c.id))
    return render_template("citizen/report.html", form={})


@bp.route("/complaint/<int:cid>")
@login_required
def detail(cid):
    c = db.get_or_404(Complaint, cid)
    if current_user.role == "citizen" and c.user_id != current_user.id:
        abort(403)
    return render_template("citizen/detail.html", c=c)


@bp.route("/complaint/<int:cid>/feedback", methods=["POST"])
@role_required("citizen", "volunteer")
def feedback(cid):
    c = db.get_or_404(Complaint, cid)
    if c.user_id != current_user.id:
        abort(403)
    if c.status not in ("Resolved", "Verified"):
        flash("You can leave feedback once the issue is resolved.", "warning")
    else:
        try:
            rating = int(request.form.get("rating", 0))
        except ValueError:
            rating = 0
        if not 1 <= rating <= 5:
            flash("Pick a rating from 1 to 5.", "danger")
        else:
            c.rating, c.feedback = rating, request.form.get("feedback", "").strip()[:1000]
            add_event(c, f"Citizen feedback: {rating}/5")
            db.session.commit()
            flash("Thanks for your feedback!", "success")
    return redirect(url_for("citizen.detail", cid=cid))
