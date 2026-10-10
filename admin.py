import csv
import io
from collections import Counter
from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for

import ai
from models import POINTS, STATUSES, Complaint, User, db, utcnow
from utils import add_event, notify, role_required, save_upload, upload_path

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@role_required("admin")
def dashboard():
    q = Complaint.query
    stats = dict(total=q.count(),
                 pending=q.filter_by(status="Submitted").count(),
                 progress=q.filter(Complaint.status.in_(["Assigned", "In Progress"])).count(),
                 awaiting=q.filter_by(status="Resolved").count(),
                 verified=q.filter_by(status="Verified").count(),
                 high=q.filter(Complaint.priority == "High",
                               Complaint.status.notin_(["Resolved", "Verified"])).count())
    recent = q.order_by(Complaint.id.desc()).limit(8).all()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


@bp.route("/api/stats")
@role_required("admin")
def api_stats():
    rows = Complaint.query.all()
    by_cat = Counter(ai.label(c.category) for c in rows)
    by_status = Counter(c.status for c in rows)
    by_prio = Counter(c.priority for c in rows)
    by_dept = Counter(c.department for c in rows)
    rated = [c.rating for c in rows if c.rating]
    return jsonify(category=by_cat, status={s: by_status.get(s, 0) for s in STATUSES},
                   priority={p: by_prio.get(p, 0) for p in ai.LEVELS}, department=by_dept,
                   avg_rating=round(sum(rated) / len(rated), 2) if rated else None)


@bp.route("/complaints")
@role_required("admin")
def complaints():
    q = Complaint.query
    f = {k: request.args.get(k, "") for k in ("status", "category", "priority", "route")}
    for k, v in f.items():
        if v:
            q = q.filter(getattr(Complaint, k) == v)
    items = q.order_by(Complaint.id.desc()).all()
    return render_template("admin/complaints.html", items=items, f=f)


@bp.route("/export.csv")
@role_required("admin")
def export():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "title", "category", "priority", "status", "route", "department",
                "lat", "lng", "created", "resolved", "rating"])
    for c in Complaint.query.order_by(Complaint.id):
        w.writerow([c.id, c.title, ai.label(c.category), c.priority, c.status, c.route,
                    c.department, c.lat, c.lng, c.created_at, c.resolved_at or "", c.rating or ""])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=complaints.csv"})


@bp.route("/complaint/<int:cid>", methods=["GET", "POST"])
@role_required("admin")
def detail(cid):
    c = db.get_or_404(Complaint, cid)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            _update(c, request.form)
        elif action == "proof":
            _proof(c)
        elif action == "verify":
            _verify(c)
        db.session.commit()
        return redirect(url_for("admin.detail", cid=cid))
    return render_template("admin/detail.html", c=c)


def _update(c, f):
    status, route, dept = f.get("status"), f.get("route"), f.get("department", "").strip()
    note = f.get("note", "").strip()
    if status in ("Verified",):
        flash("Use the Verify button once proof is uploaded.", "warning")
        status = c.status
    if route in ("municipal", "volunteer") and route != c.route:
        c.route = route
        if route == "volunteer":
            dept, c.volunteer_id, c.status = "Community Volunteers", None, "Submitted"
            status = "Submitted"
        add_event(c, f"Re-routed to {'volunteers' if route == 'volunteer' else 'Municipal Corporation'} by admin")
    if dept and dept != c.department:
        c.department = dept
        add_event(c, f"Department set to {dept}")
    if status in STATUSES and status != c.status:
        c.status = status
        if status == "Resolved":
            c.resolved_at = utcnow()
        add_event(c, f"Status changed to {status}")
        notify(c.user_id, f"Status of '{c.title}' is now {status}", url_for("citizen.detail", cid=c.id))
    if note:
        add_event(c, f"Admin note: {note[:200]}")
        notify(c.user_id, f"Update on '{c.title}': {note[:120]}", url_for("citizen.detail", cid=c.id))
    flash("Complaint updated.", "success")


def _proof(c):
    try:
        name, _ = save_upload(request.files.get("proof"), allow_video=False)
    except ValueError as e:
        flash(str(e), "danger")
        return
    c.proof_path, c.status, c.resolved_at = name, "Resolved", utcnow()
    if c.media_path:
        c.verify_score, c.verify_note = ai.compare_before_after(
            upload_path(c.media_path), c.media_type, upload_path(name))
    add_event(c, "Completion proof uploaded by admin")
    notify(c.user_id, f"Your complaint was resolved: {c.title}", url_for("citizen.detail", cid=c.id))
    flash("Proof uploaded. Review it, then verify.", "success")


def _verify(c):
    if c.status != "Resolved" or not c.proof_path:
        flash("Only resolved complaints with proof can be verified.", "warning")
        return
    c.status = "Verified"
    add_event(c, "Resolution verified by admin")
    notify(c.user_id, f"Verified: '{c.title}' is fixed. Please rate the resolution.",
           url_for("citizen.detail", cid=c.id))
    reporter = db.session.get(User, c.user_id)
    reporter.points += 10
    if c.volunteer_id:
        v = db.session.get(User, c.volunteer_id)
        earned = POINTS.get(c.priority, 10)
        v.points += earned
        notify(v.id, f"Verified! You earned {earned} points for '{c.title}'",
               url_for("volunteer.tasks"))
    flash("Verified. Points awarded.", "success")
