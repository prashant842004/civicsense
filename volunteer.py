from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

import ai
from models import CERTIFICATE_MIN_POINTS, Complaint, User, db, utcnow
from utils import (add_event, haversine, notify, notify_admins, role_required, save_upload,
                   upload_path)

bp = Blueprint("volunteer", __name__, url_prefix="/volunteer")


@bp.route("/tasks")
@role_required("volunteer")
def tasks():
    open_tasks = Complaint.query.filter_by(route="volunteer", status="Submitted").all()
    mine = (Complaint.query.filter_by(volunteer_id=current_user.id)
            .order_by(Complaint.id.desc()).all())
    lat, lng = request.args.get("lat", type=float), request.args.get("lng", type=float)
    rows = []
    for c in open_tasks:
        d = haversine(lat, lng, c.lat, c.lng) if lat is not None and lng is not None else None
        rows.append((c, d))
    rows.sort(key=lambda r: (r[1] is None, r[1] if r[1] is not None else -r[0].id))
    return render_template("volunteer/tasks.html", rows=rows, mine=mine, located=lat is not None)


@bp.route("/accept/<int:cid>", methods=["POST"])
@role_required("volunteer")
def accept(cid):
    c = db.get_or_404(Complaint, cid)
    if c.route != "volunteer" or c.status != "Submitted" or c.volunteer_id:
        flash("This task is no longer available.", "warning")
        return redirect(url_for("volunteer.tasks"))
    c.volunteer_id, c.status = current_user.id, "In Progress"
    add_event(c, f"Accepted by volunteer {current_user.name}")
    notify(c.user_id, f"A volunteer accepted your complaint: {c.title}",
           url_for("citizen.detail", cid=c.id))
    db.session.commit()
    flash("Task accepted. Upload a completion photo when you're done.", "success")
    return redirect(url_for("volunteer.tasks"))


@bp.route("/complete/<int:cid>", methods=["POST"])
@role_required("volunteer")
def complete(cid):
    c = db.get_or_404(Complaint, cid)
    if c.volunteer_id != current_user.id or c.status != "In Progress":
        flash("You can only complete your own in-progress tasks.", "warning")
        return redirect(url_for("volunteer.tasks"))
    try:
        name, _ = save_upload(request.files.get("proof"), allow_video=False)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("volunteer.tasks"))
    c.proof_path, c.status = name, "Resolved"
    c.verify_score, c.verify_note = ai.compare_before_after(
        upload_path(c.media_path), c.media_type, upload_path(name)) if c.media_path else (None, "")
    add_event(c, "Volunteer uploaded completion proof")
    notify_admins(f"Proof uploaded - please verify: {c.title}", url_for("admin.detail", cid=c.id))
    notify(c.user_id, f"Your complaint was marked resolved: {c.title}",
           url_for("citizen.detail", cid=c.id))
    db.session.commit()
    flash("Proof uploaded. Points are added once an admin verifies the work.", "success")
    return redirect(url_for("volunteer.tasks"))


@bp.route("/leaderboard")
@role_required("volunteer", "citizen", "admin")
def leaderboard():
    top = (User.query.filter(User.role.in_(["volunteer", "citizen"]), User.points > 0)
           .order_by(User.points.desc()).limit(20).all())
    return render_template("volunteer/leaderboard.html", top=top)


@bp.route("/certificate")
@role_required("volunteer")
def certificate():
    if current_user.points < CERTIFICATE_MIN_POINTS:
        flash(f"Earn {CERTIFICATE_MIN_POINTS} points to unlock your certificate.", "info")
        return redirect(url_for("volunteer.tasks"))
    done = Complaint.query.filter_by(volunteer_id=current_user.id, status="Verified").count()
    return render_template("volunteer/certificate.html", done=done,
                           now_date=utcnow().strftime("%d %B %Y"))
